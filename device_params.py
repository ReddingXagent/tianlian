"""Device Params — 设备参数绑定与下发/校验状态机（网关侧）

承接云端参数下发/校验需求的网关执行端：
  云端管理后台 → (直调网关本地 API 或后续命令通道) → 协议适配器 → 设备

表: device_params（gateway.db）
状态机: draft → deployed → verified/mismatch / failed
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_params (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL UNIQUE,
  protocol TEXT,
  config TEXT NOT NULL DEFAULT '{}',
  deploy_status TEXT NOT NULL DEFAULT 'draft',
  deployed_at TEXT,
  deployed_detail TEXT,
  verified_at TEXT,
  verify_result TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class DeviceParamStore:
    """设备参数存储。线程安全（每操作短连接 + 锁）。"""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        with self._lock, self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, device_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM device_params WHERE device_id = ?", (str(device_id),)).fetchone()
        return self._decode(row) if row else None

    def save(self, device_id: str, protocol: str | None = None, config: dict | None = None) -> dict[str, Any]:
        """保存参数（draft）。部分更新：None 字段保留原值；配置变化回到 draft。"""
        device_id = str(device_id)
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM device_params WHERE device_id = ?", (device_id,)).fetchone()
            old = dict(row) if row else None
            new_protocol = protocol if protocol is not None else (old or {}).get("protocol")
            try:
                old_cfg = json.loads((old or {}).get("config") or "{}")
            except (TypeError, ValueError):
                old_cfg = {}
            merged = {**old_cfg, **(config or {})}
            status = "draft" if merged != old_cfg else (old or {}).get("deploy_status", "draft")
            conn.execute(
                """INSERT INTO device_params (device_id, protocol, config, deploy_status)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET
                     protocol = excluded.protocol,
                     config = excluded.config,
                     deploy_status = excluded.deploy_status,
                     updated_at = datetime('now')""",
                (device_id, new_protocol, json.dumps(merged, ensure_ascii=False), status),
            )
            row = conn.execute("SELECT * FROM device_params WHERE device_id = ?", (device_id,)).fetchone()
        return self._decode(row)

    def mark_deployed(self, device_id: str, ok: bool, detail: str = "") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """UPDATE device_params SET deploy_status = ?, deployed_at = datetime('now'),
                     deployed_detail = ?, updated_at = datetime('now')
                   WHERE device_id = ?""",
                ("deployed" if ok else "failed", detail[:500], str(device_id)),
            )

    def mark_verified(self, device_id: str, result: dict[str, Any]) -> None:
        status = "verified" if result.get("match") else "mismatch"
        with self._lock, self._conn() as conn:
            conn.execute(
                """UPDATE device_params SET deploy_status = ?, verified_at = datetime('now'),
                     verify_result = ?, updated_at = datetime('now')
                   WHERE device_id = ?""",
                (status, json.dumps(result, ensure_ascii=False), str(device_id)),
            )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("config", "verify_result"):
            try:
                d[k] = json.loads(d[k]) if d.get(k) else ({} if k == "config" else None)
            except (TypeError, ValueError):
                d[k] = {} if k == "config" else None
        return d
