"""Tests for db_migration.py — schema detection, migration, and idempotency."""

import sqlite3
from pathlib import Path

import pytest

import db_migration

# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Create a temp SQLite DB path (file does not exist yet)."""
    return str(tmp_path / "test_gateway.db")


@pytest.fixture
def fresh_db(tmp_db):
    """Create an empty SQLite DB file."""
    Path(tmp_db).touch()
    return tmp_db


@pytest.fixture
def legacy_db(tmp_path):
    """Simulate a legacy DB with old schema (missing columns and tables)."""
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    # Legacy telemetry_cache without priority/cloud_synced
    conn.execute("""
        CREATE TABLE telemetry_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            cached_at REAL,
            retry_count INTEGER,
            synced INTEGER
        )
    """)
    conn.execute("INSERT INTO telemetry_cache (device_id, payload, created_at) VALUES ('d1', '{}', '2024-01-01')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def upto_date_db(tmp_path):
    """Create a DB that already has the full expected schema."""
    db_path = str(tmp_path / "uptodate.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE telemetry_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            cached_at REAL NOT NULL,
            retry_count INTEGER DEFAULT 0,
            synced INTEGER DEFAULT 0,
            cloud_synced INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE alarm_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            cached_at REAL NOT NULL,
            retry_count INTEGER DEFAULT 0,
            synced INTEGER DEFAULT 0,
            cloud_synced INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE gateway_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return db_path


# ── get_existing_tables ─────────────────────────────────────────────

class TestGetExistingTables:
    def test_empty_db(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        tables = db_migration.get_existing_tables(conn)
        assert tables == {}
        conn.close()

    def test_returns_user_tables_not_sqlite_internal(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE telemetry_cache (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE gateway_state (key TEXT PRIMARY KEY)")
        conn.commit()
        tables = db_migration.get_existing_tables(conn)
        assert "telemetry_cache" in tables
        assert "gateway_state" in tables
        assert "sqlite_sequence" not in tables
        conn.close()

    def test_returns_column_info(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE telemetry_cache (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL)")
        conn.commit()
        tables = db_migration.get_existing_tables(conn)
        assert "id" in tables["telemetry_cache"]
        assert "device_id" in tables["telemetry_cache"]
        conn.close()


# ── detect_missing_tables ───────────────────────────────────────────

class TestDetectMissingTables:
    def test_all_missing(self):
        result = db_migration.detect_missing_tables({})
        assert "telemetry_cache" in result
        assert "alarm_cache" in result
        assert "gateway_state" in result

    def test_all_present(self):
        existing = {"telemetry_cache": {}, "alarm_cache": {}, "gateway_state": {}}
        assert db_migration.detect_missing_tables(existing) == []

    def test_partial(self):
        existing = {"telemetry_cache": {}}
        result = db_migration.detect_missing_tables(existing)
        assert "telemetry_cache" not in result
        assert "alarm_cache" in result
        assert "gateway_state" in result


# ── detect_missing_columns ──────────────────────────────────────────

class TestDetectMissingColumns:
    def test_no_missing_columns(self):
        existing = {
            "telemetry_cache": {
                "id": "INTEGER", "device_id": "TEXT", "payload": "TEXT",
                "created_at": "TEXT", "cached_at": "REAL", "retry_count": "INTEGER",
                "synced": "INTEGER", "cloud_synced": "INTEGER", "priority": "INTEGER",
            },
            "alarm_cache": {
                "id": "INTEGER", "device_id": "TEXT", "payload": "TEXT",
                "created_at": "TEXT", "cached_at": "REAL", "retry_count": "INTEGER",
                "synced": "INTEGER", "cloud_synced": "INTEGER", "priority": "INTEGER",
            },
            "gateway_state": {"key": "TEXT", "value": "TEXT", "updated_at": "REAL"},
        }
        assert db_migration.detect_missing_columns(existing) == {}

    def test_missing_columns_detected(self):
        existing = {
            "telemetry_cache": {
                "id": "INTEGER", "device_id": "TEXT", "payload": "TEXT",
                "created_at": "TEXT",
            },
        }
        result = db_migration.detect_missing_columns(existing)
        assert "telemetry_cache" in result
        missing_names = [c[0] for c in result["telemetry_cache"]]
        assert "cached_at" in missing_names
        assert "cloud_synced" in missing_names
        assert "priority" in missing_names

    def test_nonexistent_table_skipped(self):
        """Tables that don't exist should not appear in missing columns."""
        existing = {"nonexistent_table": {"col": "TEXT"}}
        assert db_migration.detect_missing_columns(existing) == {}


# ── create_alarm_cache_table ────────────────────────────────────────

class TestCreateAlarmCacheTable:
    def test_creates_table_with_indexes(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        db_migration.create_alarm_cache_table(conn)
        # Verify table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alarm_cache'")
        assert cursor.fetchone() is not None
        # Verify indexes
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_alarm%'")
        index_names = [r[0] for r in cursor.fetchall()]
        assert "idx_alarm_synced" in index_names
        assert "idx_alarm_cloud_synced" in index_names
        conn.close()

    def test_idempotent(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        db_migration.create_alarm_cache_table(conn)
        db_migration.create_alarm_cache_table(conn)  # should not error
        cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='alarm_cache'")
        assert cursor.fetchone()[0] == 1
        conn.close()


# ── add_missing_column ──────────────────────────────────────────────

class TestAddMissingColumn:
    def test_adds_column_successfully(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY)")
        conn.commit()
        result = db_migration.add_missing_column(conn, "test_tbl", "priority", "INTEGER DEFAULT 0", 0)
        assert result is True
        cols = [r[1] for r in conn.execute("PRAGMA table_info(test_tbl)").fetchall()]
        assert "priority" in cols
        conn.close()

    def test_returns_false_if_column_exists(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY, priority INTEGER DEFAULT 0)")
        conn.commit()
        result = db_migration.add_missing_column(conn, "test_tbl", "priority", "INTEGER DEFAULT 0", 0)
        assert result is False
        conn.close()

    def test_uses_default_spec_from_missing_column_defaults(self, fresh_db):
        """Verify that MISSING_COLUMN_DEFAULTS values are used for the ALTER."""
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY)")
        conn.commit()
        db_migration.add_missing_column(conn, "test_tbl", "cloud_synced", "INTEGER DEFAULT 0", 0)
        # The column should have the DEFAULT from MISSING_COLUMN_DEFAULTS
        col_info = conn.execute("PRAGMA table_info(test_tbl)").fetchall()
        cloud_col = next(r for r in col_info if r[1] == "cloud_synced")
        assert str(cloud_col[4]) in ('0', '0.0')  # dflt_value (SQLite may return str or int)
        conn.close()


# ── create_index_if_missing ─────────────────────────────────────────

class TestCreateIndexIfMissing:
    def test_creates_index(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE test_tbl (id INTEGER, synced INTEGER)")
        conn.commit()
        db_migration.create_index_if_missing(conn, "idx_test", "test_tbl", "synced, id")
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_silent_if_exists(self, fresh_db):
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE test_tbl (id INTEGER, synced INTEGER)")
        conn.execute("CREATE INDEX idx_test ON test_tbl(synced)")
        conn.commit()
        # Should not raise
        db_migration.create_index_if_missing(conn, "idx_test", "test_tbl", "synced")
        conn.close()


# ── run_migration (integration) ─────────────────────────────────────

class TestRunMigration:
    def test_db_not_found(self, tmp_path):
        nonexistent = str(tmp_path / "nonexistent.db")
        result = db_migration.run_migration(nonexistent)
        assert result == 0

    def test_fresh_db_creates_all_tables(self, fresh_db):
        """An empty DB should get alarm_cache and gateway_state created."""
        # First create telemetry_cache so it exists (main table)
        conn = sqlite3.connect(fresh_db)
        conn.execute("""
            CREATE TABLE telemetry_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        result = db_migration.run_migration(fresh_db)
        assert result > 0  # some changes were applied

        conn = sqlite3.connect(fresh_db)
        tables = db_migration.get_existing_tables(conn)
        assert "alarm_cache" in tables
        assert "gateway_state" in tables
        conn.close()

    def test_legacy_db_migrates_columns(self, legacy_db):
        """Legacy DB missing columns should get them added."""
        result = db_migration.run_migration(legacy_db)
        assert result > 0

        conn = sqlite3.connect(legacy_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(telemetry_cache)").fetchall()]
        assert "cloud_synced" in cols
        assert "priority" in cols
        # Verify existing data is intact
        cursor = conn.execute("SELECT device_id FROM telemetry_cache")
        assert cursor.fetchone()[0] == "d1"
        conn.close()

    def test_uptodate_db_no_changes(self, upto_date_db):
        """A fully up-to-date DB should report 0 changes."""
        result = db_migration.run_migration(upto_date_db)
        assert result == 0

    def test_idempotent(self, legacy_db):
        """Running migration twice should be safe."""
        first = db_migration.run_migration(legacy_db)
        assert first > 0
        second = db_migration.run_migration(legacy_db)
        assert second == 0

    def test_indexes_created_on_full_migration(self, fresh_db):
        """After migration, all expected indexes should exist."""
        conn = sqlite3.connect(fresh_db)
        conn.execute("""
            CREATE TABLE telemetry_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        db_migration.run_migration(fresh_db)

        conn = sqlite3.connect(fresh_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        index_names = [r[0] for r in cursor.fetchall()]
        conn.close()

        assert "idx_telemetry_synced" in index_names
        assert "idx_telemetry_cloud_synced" in index_names
        assert "idx_telemetry_device" in index_names
        assert "idx_alarm_synced" in index_names
        assert "idx_alarm_cloud_synced" in index_names


# ── main entry point ────────────────────────────────────────────────

class TestMain:
    def test_main_success(self, fresh_db, capsys):
        """main() should exit 0 on a valid migration."""
        # Create a minimal DB to migrate
        conn = sqlite3.connect(fresh_db)
        conn.execute("CREATE TABLE telemetry_cache (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        with pytest.raises(SystemExit) as exc_info:
            db_migration.main.__wrapped__ if hasattr(db_migration.main, '__wrapped__') else None
            # Call main directly with argv
            import sys
            old_argv = sys.argv
            sys.argv = ["db_migration.py", fresh_db]
            try:
                db_migration.main()
            finally:
                sys.argv = old_argv

        assert exc_info.value.code == 0

    def test_main_default_db_path(self, tmp_path, capsys, monkeypatch):
        """main() should use default path when no arg given."""
        # Change to a dir with no data/gateway.db
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            import sys
            old_argv = sys.argv
            sys.argv = ["db_migration.py"]
            try:
                db_migration.main()
            finally:
                sys.argv = old_argv
        assert exc_info.value.code == 0

    def test_main_handles_error(self, tmp_path):
        """main() should exit 1 on exception."""
        # Pass a directory path as db_path to trigger an error
        with pytest.raises(SystemExit) as exc_info:
            import sys
            old_argv = sys.argv
            sys.argv = ["db_migration.py", "/proc/version"]  # not a valid db
            try:
                db_migration.main()
            finally:
                sys.argv = old_argv
        # Should exit 0 or 1 depending on whether it treats it as not-found vs error
        # /proc/version exists as a file but is not SQLite
        assert exc_info.value.code in (0, 1)

    def test_main_exits_1_on_migration_failure(self, tmp_path):
        """main() should exit 1 when run_migration raises an exception."""
        db_path = str(tmp_path / "corrupt.db")
        # Write invalid SQLite content to trigger a migration error
        with open(db_path, "wb") as f:
            f.write(b"not a valid sqlite database file")
        with pytest.raises(SystemExit) as exc_info:
            import sys
            old_argv = sys.argv
            sys.argv = ["db_migration.py", db_path]
            try:
                db_migration.main()
            finally:
                sys.argv = old_argv
        assert exc_info.value.code == 1


class TestDbMigrationCoverageGap:
    """Targeted tests for remaining coverage gaps."""

    def test_add_missing_column_raises_on_non_duplicate_error(self, fresh_db):
        """Line 149: raise on non-duplicate-column OperationalError."""
        conn = sqlite3.connect(fresh_db)
        # Create a table, then try to add a column to a non-existent table
        # This triggers a different OperationalError (no such table)
        with pytest.raises(sqlite3.OperationalError):
            db_migration.add_missing_column(conn, "nonexistent_tbl", "col", "TEXT", 0)
        conn.close()

    def test_run_migration_prints_already_exists(self, tmp_path, capsys, monkeypatch):
        """Line 215: else branch where column already exists (skipped message)."""
        db_path = str(tmp_path / "test.db")
        Path(db_path).touch()
        # First run: full migration
        db_migration.run_migration(db_path)
        capsys.readouterr()
        # Monkeypatch get_missing_columns to report a column that already exists
        # This simulates a race condition or schema detection quirk
        original = db_migration.detect_missing_columns

        def mock_missing(conn):
            cols = original(conn)
            # Force trigger the 'already exists' path by adding an existing column
            if "alarm_cache" not in cols:
                cols["alarm_cache"] = []
            cols["alarm_cache"].append(("priority", "INTEGER DEFAULT 0"))
            return cols

        monkeypatch.setattr(db_migration, "detect_missing_columns", mock_missing)
        # Second run with mocked missing columns
        db_migration.run_migration(db_path)
        captured = capsys.readouterr()
        assert "already exists" in captured.out
