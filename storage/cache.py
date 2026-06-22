"""Local SQLite cache for offline resilience"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import StorageConfig
from models import TelemetryPoint

logger = logging.getLogger(__name__)


class TelemetryCache:
    """SQLite-backed cache for telemetry data (offline protection)"""

    def __init__(self, config: StorageConfig):
        self.config = config
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.config.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_db()
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                synced INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_synced
            ON telemetry_cache(synced)
        """)
        conn.commit()

    def cache_telemetry(self, point: TelemetryPoint) -> None:
        """Cache a telemetry point locally"""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO telemetry_cache (device_id, payload, created_at) VALUES (?, ?, ?)",
            (point.device_id, json.dumps(point.to_api_payload()), point.timestamp),
        )
        conn.commit()

    def get_unsynced(self, limit: int = 100) -> List[dict]:
        """Get unsynced telemetry points"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, device_id, payload, created_at, retry_count FROM telemetry_cache "
            "WHERE synced = 0 AND retry_count < ? "
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

    def mark_synced(self, ids: List[int]) -> None:
        """Mark telemetry points as synced"""
        conn = self._get_conn()
        conn.executemany(
            "UPDATE telemetry_cache SET synced = 1 WHERE id = ?",
            [(i,) for i in ids],
        )
        conn.commit()

    def increment_retry(self, ids: List[int]) -> None:
        """Increment retry count for failed syncs"""
        conn = self._get_conn()
        conn.executemany(
            "UPDATE telemetry_cache SET retry_count = retry_count + 1 WHERE id = ?",
            [(i,) for i in ids],
        )
        conn.commit()

    def get_cache_size(self) -> int:
        """Get number of cached entries"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM telemetry_cache WHERE synced = 0")
        return cursor.fetchone()[0]

    def cleanup(self, max_age_days: int = 7) -> None:
        """Remove old synced entries"""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM telemetry_cache WHERE synced = 1 AND "
            "created_at < datetime('now', ?)",
            (f"-{max_age_days} days",),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
