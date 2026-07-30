"""Local SQLite cache for offline resilience

Features:
- Batch cache and batch sync operations (T-1102)
- Priority-aware caching (alarms > telemetry)
- Automatic cleanup with configurable retention
- Sync state tracking and recovery
- Cache statistics for monitoring
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from config import StorageConfig
from models import TelemetryPoint

logger = logging.getLogger(__name__)


class TelemetryCache:
    """SQLite-backed cache for telemetry data with enhanced offline resilience"""

    def __init__(self, config: StorageConfig):
        self.config = config
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()  # protect SQLite from concurrent async access

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self.config.db_path,
                check_same_thread=False,  # allow async threads from MQTT/callbacks
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")  # faster writes
            self._conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
            self._init_db()
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        # Telemetry cache table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_cache (
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
            CREATE INDEX IF NOT EXISTS idx_telemetry_synced
            ON telemetry_cache(synced, priority DESC, id ASC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_cloud_synced
            ON telemetry_cache(cloud_synced, priority DESC, id ASC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_device
            ON telemetry_cache(device_id, synced)
        """)

        # Alarm cache table (higher priority)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alarm_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                cached_at REAL NOT NULL,
                retry_count INTEGER DEFAULT 0,
                synced INTEGER DEFAULT 0,
                cloud_synced INTEGER DEFAULT 0
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

        # Gateway state metadata
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gateway_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        conn.commit()

    # ── Telemetry Operations ────────────────────────────────────────

    def cache_telemetry(self, point: TelemetryPoint, priority: int = 0) -> None:
        """Cache a single telemetry point locally"""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO telemetry_cache (device_id, payload, created_at, cached_at, priority) "
                "VALUES (?, ?, ?, ?, ?)",
                (point.device_id, json.dumps(point.to_api_payload()),
                 point.timestamp, time.time(), priority),
            )
            conn.commit()
            self._enforce_cache_limit(conn)

    def cache_telemetry_batch(self, points: list[TelemetryPoint], priority: int = 0) -> int:
        """Cache multiple telemetry points in a single transaction (T-1102)

        Args:
            points: List of TelemetryPoint to cache
            priority: Higher priority = synced first

        Returns:
            Number of points cached
        """
        if not points:
            return 0

        with self._lock:
            conn = self._get_conn()
            now = time.time()
            rows = [
                (p.device_id, json.dumps(p.to_api_payload()), p.timestamp, now, priority)
                for p in points
            ]
            conn.executemany(
                "INSERT INTO telemetry_cache (device_id, payload, created_at, cached_at, priority) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            self._enforce_cache_limit(conn)
        logger.debug("Cached %d telemetry points (priority=%d)", len(rows), priority)
        return len(rows)

    def get_unsynced(self, limit: int = 100, priority_only: bool = False) -> list[dict]:
        """Get unsynced telemetry points, ordered by priority then time"""
        with self._lock:
            conn = self._get_conn()
            if priority_only:
                cursor = conn.execute(
                    "SELECT id, device_id, payload, created_at, retry_count, priority "
                    "FROM telemetry_cache "
                    "WHERE synced = 0 AND retry_count < ? AND priority > 0 "
                    "ORDER BY priority DESC, id ASC LIMIT ?",
                    (self.config.max_retries, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, device_id, payload, created_at, retry_count, priority "
                    "FROM telemetry_cache "
                    "WHERE synced = 0 AND retry_count < ? "
                    "ORDER BY priority DESC, id ASC LIMIT ?",
                    (self.config.max_retries, limit),
                )
            return [
                {
                    "id": row[0],
                    "device_id": row[1],
                    "payload": json.loads(row[2]),
                    "created_at": row[3],
                    "retry_count": row[4],
                    "priority": row[5],
                }
                for row in cursor.fetchall()
            ]

    def get_unsynced_count(self) -> int:
        """Get total unsynced count (telemetry + alarms)"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM telemetry_cache WHERE synced = 0")
            tel_count = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM alarm_cache WHERE synced = 0")
            alarm_count = cursor.fetchone()[0]
            return tel_count + alarm_count

    def mark_synced(self, ids: list[int]) -> None:
        """Mark telemetry points as synced"""
        if not ids:
            return
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                "UPDATE telemetry_cache SET synced = 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()

    def mark_synced_batch(self, ids: list[int]) -> None:
        """Alias for mark_synced - batch operation"""
        self.mark_synced(ids)

    def increment_retry(self, ids: list[int]) -> None:
        """Increment retry count for failed syncs"""
        if not ids:
            return
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                "UPDATE telemetry_cache SET retry_count = retry_count + 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()

    # ── Alarm Operations ────────────────────────────────────────────

    def cache_alarm(self, device_id: str, alarm_payload: dict) -> int:
        """Cache an alarm event for offline resilience"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "INSERT INTO alarm_cache (device_id, payload, created_at, cached_at) "
                "VALUES (?, ?, ?, ?)",
                (device_id, json.dumps(alarm_payload),
                 alarm_payload.get("timestamp", datetime.now(UTC).isoformat()),
                 time.time()),
            )
            conn.commit()
            return cursor.lastrowid

    def get_unsynced_alarms(self, limit: int = 50) -> list[dict]:
        """Get unsynced alarm events"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT id, device_id, payload, created_at, retry_count "
                "FROM alarm_cache WHERE synced = 0 AND retry_count < ? "
                "ORDER BY id ASC LIMIT ?",
                (self.config.max_retries, limit),
            )
            return [
                {
                    "id": row[0],
                    "device_id": row[1],
                    "payload": json.loads(row[2]),
                    "created_at": row[3],
                    "retry_count": row[4],
                }
                for row in cursor.fetchall()
            ]

    def mark_alarms_synced(self, ids: list[int]) -> None:
        """Mark alarm events as synced"""
        if not ids:
            return
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                "UPDATE alarm_cache SET synced = 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()

    def increment_alarm_retry(self, ids: list[int]) -> None:
        """Increment retry count for failed alarm syncs"""
        if not ids:
            return
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                "UPDATE alarm_cache SET retry_count = retry_count + 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()

    # ── Gateway State ───────────────────────────────────────────────

    def save_state(self, key: str, value: str) -> None:
        """Persist gateway state key-value"""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO gateway_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, time.time()),
            )
            conn.commit()

    def load_state(self, key: str, default: str = "") -> str:
        """Load gateway state key-value"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT value FROM gateway_state WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else default

    def load_all_state(self) -> dict[str, str]:
        """Load all gateway state key-values"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT key, value FROM gateway_state")
            return {row[0]: row[1] for row in cursor.fetchall()}

    # ── Cloud Sync Operations (separate from MQTT sync) ────────────

    def get_cloud_unsynced(self, limit: int = 100) -> list[dict]:
        """Get telemetry points not yet synced to cloud (cloud_synced=0)"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT id, device_id, payload, created_at, retry_count, priority "
                "FROM telemetry_cache "
                "WHERE cloud_synced = 0 AND retry_count < ? "
                "ORDER BY priority DESC, id ASC LIMIT ?",
                (self.config.max_retries, limit),
            )
            return [
                {
                    "id": row[0],
                    "device_id": row[1],
                    "payload": json.loads(row[2]),
                    "created_at": row[3],
                    "retry_count": row[4],
                    "priority": row[5],
                }
                for row in cursor.fetchall()
            ]

    def mark_cloud_synced(self, ids: list[int]) -> None:
        """Mark telemetry points as synced to cloud"""
        if not ids:
            return
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                "UPDATE telemetry_cache SET cloud_synced = 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()

    def get_cloud_unsynced_alarms(self, limit: int = 50) -> list[dict]:
        """Get alarm events not yet synced to cloud"""
        with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT id, device_id, payload, created_at, retry_count "
                "FROM alarm_cache WHERE cloud_synced = 0 AND retry_count < ? "
                "ORDER BY id ASC LIMIT ?",
                (self.config.max_retries, limit),
            )
            return [
                {
                    "id": row[0],
                    "device_id": row[1],
                    "payload": json.loads(row[2]),
                    "created_at": row[3],
                    "retry_count": row[4],
                }
                for row in cursor.fetchall()
            ]

    def mark_alarms_cloud_synced(self, ids: list[int]) -> None:
        """Mark alarm events as synced to cloud"""
        if not ids:
            return
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                "UPDATE alarm_cache SET cloud_synced = 1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()

    # ── Maintenance & Stats ─────────────────────────────────────────

    def get_cache_size(self) -> int:
        """Get total unsynced entries count (telemetry + alarms)"""
        return self.get_unsynced_count()

    def get_stats(self) -> dict:
        """Get detailed cache statistics for monitoring"""
        with self._lock:
            conn = self._get_conn()

            # Telemetry stats
            cursor = conn.execute(
                "SELECT "
                "COUNT(*) as total, "
                "SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) as unsynced, "
                "SUM(CASE WHEN retry_count >= ? THEN 1 ELSE 0 END) as failed, "
                "SUM(CASE WHEN synced = 1 THEN 1 ELSE 0 END) as synced "
                "FROM telemetry_cache",
                (self.config.max_retries,)
            )
            row = cursor.fetchone()
            tel_stats = {"total": row[0], "unsynced": row[1] or 0, "failed": row[2] or 0, "synced": row[3] or 0}

            # Alarm stats
            cursor = conn.execute(
                "SELECT "
                "COUNT(*) as total, "
                "SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) as unsynced, "
                "SUM(CASE WHEN retry_count >= ? THEN 1 ELSE 0 END) as failed, "
                "SUM(CASE WHEN synced = 1 THEN 1 ELSE 0 END) as synced "
                "FROM alarm_cache",
                (self.config.max_retries,)
            )
            row = cursor.fetchone()
            alarm_stats = {"total": row[0], "unsynced": row[1] or 0, "failed": row[2] or 0, "synced": row[3] or 0}

            # DB file size
            db_path = Path(self.config.db_path)
            db_size = db_path.stat().st_size if db_path.exists() else 0

            return {
                "telemetry": tel_stats,
                "alarms": alarm_stats,
                "db_size_bytes": db_size,
                "db_path": str(db_path),
            }

    def _enforce_cache_limit(self, conn: sqlite3.Connection) -> None:
        """Keep total telemetry_cache rows within max_cache_size.

        Eviction strategy: delete oldest entries with lowest priority first.
        Uses a 5% buffer to avoid evicting on every insert.
        Runs inside _lock.
        """
        max_size = self.config.max_cache_size
        # Only trigger when exceeding by > 5% to batch evictions
        threshold = int(max_size * 1.05)
        cursor = conn.execute("SELECT COUNT(*) FROM telemetry_cache")
        total = cursor.fetchone()[0]
        if total <= threshold:
            return

        overflow = total - max_size
        # Delete oldest, lowest-priority entries
        conn.execute(
            "DELETE FROM telemetry_cache WHERE id IN ("
            "SELECT id FROM telemetry_cache "
            "ORDER BY priority ASC, cached_at ASC LIMIT ?"
            ")",
            (overflow,),
        )
        conn.commit()
        logger.warning(
            "Cache limit exceeded (%d > %d): evicted %d oldest entries",
            total, max_size, overflow,
        )

    def cleanup(self, max_age_days: int = 7) -> int:
        """Remove old synced entries and reclaim disk space. Returns count deleted."""
        from datetime import timedelta
        cutoff_dt = datetime.now(UTC) - timedelta(days=max_age_days)
        cutoff = cutoff_dt.isoformat()

        with self._lock:
            conn = self._get_conn()

            cursor = conn.execute(
                "DELETE FROM telemetry_cache WHERE synced = 1 AND created_at < ?",
                (cutoff,),
            )
            tel_deleted = cursor.rowcount

            cursor = conn.execute(
                "DELETE FROM alarm_cache WHERE synced = 1 AND created_at < ?",
                (cutoff,),
            )
            alarm_deleted = cursor.rowcount

            conn.commit()

            # Reclaim disk space if entries were deleted
            if tel_deleted or alarm_deleted:
                conn.execute("VACUUM")
                logger.info("Cache cleanup: %d telemetry + %d alarms purged (VACUUM'd)",
                            tel_deleted, alarm_deleted)

        return tel_deleted + alarm_deleted

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
