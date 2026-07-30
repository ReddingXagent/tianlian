#!/usr/bin/env python3
"""
DB Migration Script for tianlian-edge-gateway

Detects and upgrades old gateway.db schema to the latest version.
Non-destructive — only adds missing tables/columns, never drops.

Usage:
    python3 db_migration.py [db_path]

Default db_path: data/gateway.db
"""

import sqlite3
import sys
from pathlib import Path

# ── Expected schema definitions ─────────────────────────────────────

EXPECTED_TABLES = {
    "telemetry_cache": {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "device_id": "TEXT NOT NULL",
        "payload": "TEXT NOT NULL",
        "created_at": "TEXT NOT NULL",
        "cached_at": "REAL NOT NULL",
        "retry_count": "INTEGER DEFAULT 0",
        "synced": "INTEGER DEFAULT 0",
        "cloud_synced": "INTEGER DEFAULT 0",
        "priority": "INTEGER DEFAULT 0",
    },
    "alarm_cache": {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "device_id": "TEXT NOT NULL",
        "payload": "TEXT NOT NULL",
        "created_at": "TEXT NOT NULL",
        "cached_at": "REAL NOT NULL",
        "retry_count": "INTEGER DEFAULT 0",
        "synced": "INTEGER DEFAULT 0",
        "cloud_synced": "INTEGER DEFAULT 0",
        "priority": "INTEGER DEFAULT 0",
    },
    "gateway_state": {
        "key": "TEXT PRIMARY KEY",
        "value": "TEXT NOT NULL",
        "updated_at": "REAL NOT NULL",
    },
}

# Columns that can be safely added via ALTER TABLE with a default value
# Map: column_name -> (type_default_spec, default_value_for_existing_rows)
MISSING_COLUMN_DEFAULTS = {
    "cached_at": ("REAL NOT NULL DEFAULT 0.0", 0.0),
    "retry_count": ("INTEGER DEFAULT 0", 0),
    "synced": ("INTEGER DEFAULT 0", 0),
    "cloud_synced": ("INTEGER DEFAULT 0", 0),
    "priority": ("INTEGER DEFAULT 0", 0),
    "updated_at": ("REAL NOT NULL DEFAULT 0.0", 0.0),
}


def get_existing_tables(conn: sqlite3.Connection) -> dict:
    """Return {table_name: {column_name: column_type}} for all user tables."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = {}
    for (name,) in cursor.fetchall():
        col_cursor = conn.execute(f"PRAGMA table_info({name})")
        columns = {}
        for row in col_cursor.fetchall():
            col_name = row[1]
            col_type = row[2]
            col_notnull = row[3]
            col_default = row[4]
            # Build a type string that includes constraints
            type_str = col_type
            if col_default is not None:
                type_str += f" DEFAULT {col_default}"
            if col_notnull:
                type_str += " NOT NULL"
            columns[col_name] = type_str
        tables[name] = columns
    return tables


def detect_missing_tables(existing: dict) -> list:
    """Return list of table names that should exist but don't."""
    return [t for t in EXPECTED_TABLES if t not in existing]


def detect_missing_columns(existing: dict) -> dict:
    """Return {table_name: [(column_name, expected_type), ...]} for missing columns."""
    missing = {}
    for table_name, expected_cols in EXPECTED_TABLES.items():
        if table_name not in existing:
            continue  # table doesn't exist yet, will be created with all columns
        existing_cols = existing[table_name]
        table_missing = []
        for col_name, col_type in expected_cols.items():
            if col_name not in existing_cols:
                table_missing.append((col_name, col_type))
        if table_missing:
            missing[table_name] = table_missing
    return missing


def create_alarm_cache_table(conn: sqlite3.Connection) -> None:
    """Create the alarm_cache table if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alarm_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            cached_at REAL NOT NULL DEFAULT 0.0,
            retry_count INTEGER DEFAULT 0,
            synced INTEGER DEFAULT 0,
            cloud_synced INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alarm_synced
        ON alarm_cache(synced, id ASC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alarm_cloud_synced
        ON alarm_cache(cloud_synced, id ASC)
    """)


def add_missing_column(conn: sqlite3.Connection, table: str, col_name: str,
                       col_type: str, default_val) -> bool:
    """Try to add a missing column. Returns True on success, False if already exists."""
    default_spec = MISSING_COLUMN_DEFAULTS.get(col_name)
    if default_spec:
        type_default = default_spec[0]
    else:
        type_default = col_type

    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {type_default}")
        return True
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            return False
        raise


def create_index_if_missing(conn: sqlite3.Connection, index_name: str,
                            table: str, columns: str) -> None:
    """Create an index if it doesn't exist."""
    try:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({columns})"
        )
    except sqlite3.OperationalError:
        pass  # index already exists or table missing


def run_migration(db_path: str) -> int:
    """Run all migration steps. Returns number of changes applied."""
    path = Path(db_path)
    if not path.exists():
        print(f"[INFO] Database file not found at {path}, nothing to migrate.")
        return 0

    conn = sqlite3.connect(str(path))
    changes = 0

    try:
        # ── 1. Detect current state ──
        print(f"[INFO] Migrating database: {path} ({path.stat().st_size} bytes)")
        existing = get_existing_tables(conn)
        print(f"[INFO] Found {len(existing)} existing tables: {', '.join(existing.keys())}")

        missing_tables = detect_missing_tables(existing)
        missing_columns = detect_missing_columns(existing)

        # ── 2. Create missing tables ──
        if "alarm_cache" in missing_tables:
            print("[MIGRATE] Creating missing table: alarm_cache")
            create_alarm_cache_table(conn)
            changes += 1
            print("[MIGRATE]   ✓ alarm_cache table created with indexes")
        else:
            print("[OK] alarm_cache table exists")

        if "gateway_state" in missing_tables:
            print("[MIGRATE] Creating missing table: gateway_state")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gateway_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL DEFAULT 0.0
                )
            """)
            conn.commit()
            changes += 1
            print("[MIGRATE]   ✓ gateway_state table created")
        else:
            print("[OK] gateway_state table exists")

        # ── 3. Add missing columns ──
        for table, cols in sorted(missing_columns.items()):
            for col_name, col_type in cols:
                default_spec = MISSING_COLUMN_DEFAULTS.get(col_name)
                default_val = default_spec[1] if default_spec else 0
                print(f"[MIGRATE] Adding missing column: {table}.{col_name} ({col_type})")
                added = add_missing_column(conn, table, col_name, col_type, default_val)
                if added:
                    changes += 1
                    print(f"[MIGRATE]   ✓ {table}.{col_name} added")
                else:
                    print(f"[MIGRATE]   - {table}.{col_name} already exists (skipped)")

        # ── 4. Ensure indexes exist ──
        index_defs = [
            ("idx_telemetry_synced", "telemetry_cache", "synced, priority DESC, id ASC"),
            ("idx_telemetry_cloud_synced", "telemetry_cache", "cloud_synced, priority DESC, id ASC"),
            ("idx_telemetry_device", "telemetry_cache", "device_id, synced"),
            ("idx_alarm_synced", "alarm_cache", "synced, id ASC"),
            ("idx_alarm_cloud_synced", "alarm_cache", "cloud_synced, id ASC"),
        ]
        for idx_name, table, cols in index_defs:
            if table in existing or table not in missing_tables:
                create_index_if_missing(conn, idx_name, table, cols)

        conn.commit()

        # ── 5. Print final status ──
        print()
        print("=" * 60)
        print("Migration complete")
        print(f"  Changes applied: {changes}")
        print()

        # Re-read schema to show final state
        final = get_existing_tables(conn)
        for table_name in sorted(final.keys()):
            cols = final[table_name]
            print(f"  {table_name}:")
            for col_name, col_type in sorted(cols.items()):
                print(f"    {col_name} {col_type}")

        print()
        if changes == 0:
            print("[OK] Database schema is up to date — no changes needed.")
        else:
            print(f"[DONE] Applied {changes} migration(s).")

        return changes

    finally:
        conn.close()


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/gateway.db"
    try:
        changes = run_migration(db_path)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()