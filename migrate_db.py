#!/usr/bin/env python3
"""Database migration: ensure all V3 tables and columns exist.
Safe to run multiple times (IF NOT EXISTS / IF NOT EXISTS column)."""

import sqlite3
import sys
import os

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/gateway.db"


def migrate(db_path: str):
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}, will be created on first run.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Ensure alarm_cache table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alarm_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            synced INTEGER DEFAULT 0,
            cloud_synced INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0
        )
    """)

    # 2. Ensure telemetry_cache table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            synced INTEGER DEFAULT 0,
            cloud_synced INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0
        )
    """)

    # 3. Ensure gateway_state table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gateway_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # 4. Add cloud_synced column if missing (older DBs)
    for table in ["telemetry_cache", "alarm_cache"]:
        try:
            cur.execute(f"SELECT cloud_synced FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN cloud_synced INTEGER DEFAULT 0")
            print(f"  Added cloud_synced column to {table}")

    # 5. Add priority column if missing
    for table in ["telemetry_cache", "alarm_cache"]:
        try:
            cur.execute(f"SELECT priority FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN priority INTEGER DEFAULT 0")
            print(f"  Added priority column to {table}")

    # 6. Create indexes
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_cloud_synced
        ON telemetry_cache(cloud_synced, priority DESC, id ASC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_alarm_cloud_synced
        ON alarm_cache(cloud_synced, id ASC)
    """)

    conn.commit()
    conn.close()
    print(f"Migration complete: {db_path}")


if __name__ == "__main__":
    migrate(DB_PATH)
