"""
充电交易缓存与回传 (卡 83f06883)

职责:
  1. StartTransaction 缓存: 内存 dict + sqlite 持久化 (data/ 下, 防重启丢失)
  2. StopTransaction 组装完整会话 -> 异步回传云端 /charging-sessions
  3. 云端不可达/5xx/超时 -> 本地 outbox sqlite 队列暂存 + 后台任务重传

设计:
  - 复用 cloud_client (已含 X-API-Key header + httpx 异常吞掉返回 None 的模式)
  - 云端幂等键 = transaction_id, 网关侧重传安全, 只管重试不管去重
  - 表 transaction_starts: start 缓存 (transaction_id 幂等键)
  - 表 session_outbox: 待回传 stop 记录 (pending/flushed/failed)
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiosqlite

from app.core.config import config
from app.core.http_client import cloud_client
from app.core.logging import logger


# 云端充电会话 ingestion 端点 (前置卡 d018e3dc 已交付)
CHARGING_SESSIONS_ENDPOINT = "/charging-sessions"

# outbox 最大重试次数 (与 offline_buffer 一致)
MAX_OUTBOX_RETRIES = 10


class TransactionStore:
    """充电交易缓存与云端回传管理器"""

    def __init__(self, db_path: Optional[str] = None):
        # 默认 data/transactions.db; 可注入用于测试隔离
        self._db_path = db_path or "data/transactions.db"
        self._db: Optional[aiosqlite.Connection] = None
        # start 缓存内存镜像: {transaction_id -> record}
        self._start_cache: Dict[str, Dict[str, Any]] = {}
        self._retry_task: Optional[asyncio.Task] = None
        self._running: bool = False
        # 复用断网续传的重试间隔配置
        self._retry_interval = config.offline_buffer.retry_interval_seconds

    @property
    def stats(self) -> Dict[str, Any]:
        return {"start_cache_size": len(self._start_cache)}

    # ---------- 初始化 ----------

    async def _init_db(self):
        """初始化 sqlite: 建表 + 从持久化恢复内存 start 缓存。"""
        db_path = Path(self._db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(str(db_path))
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS transaction_starts (
                transaction_id TEXT PRIMARY KEY,
                charge_point_id TEXT,
                connector_id INTEGER,
                id_tag TEXT,
                meter_start INTEGER,
                timestamp_start TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS session_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_retry_at TEXT,
                error_message TEXT
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbox_status "
            "ON session_outbox(status, created_at)"
        )
        await self._db.commit()

        await self._restore_start_cache()
        logger.info(f"交易缓存数据库已初始化 [{db_path}]")

    async def _restore_start_cache(self):
        """重启后从 sqlite 恢复内存 start 缓存。"""
        if not self._db:
            return
        cursor = await self._db.execute(
            "SELECT transaction_id, charge_point_id, connector_id, id_tag, "
            "meter_start, timestamp_start FROM transaction_starts"
        )
        rows = await cursor.fetchall()
        for row in rows:
            self._start_cache[row["transaction_id"]] = {
                "charge_point_id": row["charge_point_id"],
                "connector_id": row["connector_id"],
                "id_tag": row["id_tag"],
                "meter_start": row["meter_start"],
                "timestamp_start": row["timestamp_start"],
            }
        if rows:
            logger.info(f"从持久化恢复 {len(rows)} 条 start 缓存")

    # ---------- StartTransaction 缓存 ----------

    async def record_start(
        self,
        transaction_id: Any,
        charge_point_id: Optional[str],
        connector_id: int,
        id_tag: str,
        meter_start: Any,
        timestamp_start: Optional[str],
    ):
        """缓存 StartTransaction 信息 (内存 + sqlite 持久化)。"""
        key = str(transaction_id)
        record = {
            "charge_point_id": charge_point_id,
            "connector_id": connector_id,
            "id_tag": id_tag,
            "meter_start": meter_start,
            "timestamp_start": timestamp_start,
        }
        self._start_cache[key] = record

        if self._db:
            await self._db.execute(
                """INSERT OR REPLACE INTO transaction_starts
                   (transaction_id, charge_point_id, connector_id, id_tag,
                    meter_start, timestamp_start, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    key, charge_point_id, connector_id, id_tag,
                    meter_start, timestamp_start, datetime.utcnow().isoformat(),
                ),
            )
            await self._db.commit()

    async def get_start(self, transaction_id: Any) -> Optional[Dict[str, Any]]:
        """按 transaction_id 取 start 缓存: 先内存, 后 sqlite。"""
        key = str(transaction_id)
        if key in self._start_cache:
            return self._start_cache[key]

        if self._db:
            cursor = await self._db.execute(
                "SELECT charge_point_id, connector_id, id_tag, meter_start, "
                "timestamp_start FROM transaction_starts WHERE transaction_id = ?",
                (key,),
            )
            row = await cursor.fetchone()
            if row:
                record = {
                    "charge_point_id": row["charge_point_id"],
                    "connector_id": row["connector_id"],
                    "id_tag": row["id_tag"],
                    "meter_start": row["meter_start"],
                    "timestamp_start": row["timestamp_start"],
                }
                self._start_cache[key] = record
                return record
        return None

    # ---------- StopTransaction 组装 ----------

    async def build_session(
        self, charge_point_id: Optional[str], stop_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """组装完整充电会话记录供云端 ingestion。

        start 缓存缺失时不丢交易: meter_start/timestamp_start 置 null, 记 warning。
        """
        transaction_id = str(stop_payload.get("transactionId", 0))
        meter_stop = stop_payload.get("meterStop", 0)
        timestamp_stop = stop_payload.get("timestamp")
        reason = stop_payload.get("reason", "Local")

        start = await self.get_start(transaction_id)
        if start:
            return {
                "charge_point_id": charge_point_id,
                "connector_id": start.get("connector_id", stop_payload.get("connectorId", 0)),
                "id_tag": start.get("id_tag", stop_payload.get("idTag", "unknown")),
                "transaction_id": transaction_id,
                "meter_start": start.get("meter_start"),
                "meter_stop": meter_stop,
                "timestamp_start": start.get("timestamp_start"),
                "timestamp_stop": timestamp_stop,
                "reason": reason,
                "station_id": config.gateway.station_id,
            }

        logger.warning(
            f"StopTransaction 无 start 缓存 [transaction_id={transaction_id}], "
            f"meter_start/timestamp_start 置空, 不丢交易"
        )
        return {
            "charge_point_id": charge_point_id,
            "connector_id": stop_payload.get("connectorId", 0),
            "id_tag": stop_payload.get("idTag", "unknown"),
            "transaction_id": transaction_id,
            "meter_start": None,
            "meter_stop": meter_stop,
            "timestamp_start": None,
            "timestamp_stop": timestamp_stop,
            "reason": reason,
            "station_id": config.gateway.station_id,
        }

    # ---------- 回传云端 + outbox ----------

    async def submit_session(self, session: Dict[str, Any]) -> bool:
        """回传充电会话到云端; 失败(不可达/5xx/超时)入 outbox 暂存。

        返回 True=已成功回传, False=已入队待重传。
        """
        tx_id = session.get("transaction_id")
        try:
            result = await cloud_client.post(CHARGING_SESSIONS_ENDPOINT, session)
            if result is not None:
                logger.info(f"充电会话已回传云端 [transaction_id={tx_id}]")
                return True
            logger.warning(f"云端回传返回空, 交易入队 [transaction_id={tx_id}]")
            await self._enqueue_outbox(session)
            return False
        except Exception as e:
            logger.error(f"云端回传异常, 交易入队 [transaction_id={tx_id}]: {e}")
            await self._enqueue_outbox(session)
            return False

    async def _enqueue_outbox(self, payload: Dict[str, Any]):
        """入 outbox 队列持久化。"""
        if not self._db:
            logger.error(f"outbox 未初始化, 交易丢失 [transaction_id={payload.get('transaction_id')}]")
            return
        await self._db.execute(
            "INSERT INTO session_outbox (payload, status, created_at) VALUES (?, 'pending', ?)",
            (json.dumps(payload), datetime.utcnow().isoformat()),
        )
        await self._db.commit()

    async def outbox_pending_count(self) -> int:
        """待回传队列长度。"""
        if not self._db:
            return 0
        cursor = await self._db.execute(
            "SELECT COUNT(*) as cnt FROM session_outbox WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def flush_outbox(self, batch_size: int = 50) -> int:
        """批量重传 outbox; 成功的标 flushed, 失败的累加 retry_count。"""
        if not self._db:
            return 0

        cursor = await self._db.execute(
            "SELECT id, payload, retry_count FROM session_outbox "
            "WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
            (batch_size,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        flushed = 0
        for row in rows:
            payload = json.loads(row["payload"])
            try:
                result = await cloud_client.post(CHARGING_SESSIONS_ENDPOINT, payload)
                if result is not None:
                    await self._db.execute(
                        "UPDATE session_outbox SET status = 'flushed' WHERE id = ?",
                        (row["id"],),
                    )
                    flushed += 1
                else:
                    await self._bump_retry(row, "cloud returned None")
            except Exception as e:
                await self._bump_retry(row, str(e)[:500])

        await self._db.commit()
        if flushed > 0:
            logger.info(f"交易 outbox 已补传: {flushed}/{len(rows)} 条")
        return flushed

    async def _bump_retry(self, row: aiosqlite.Row, err: str):
        """单条 outbox 重试计数; 超限标 failed。"""
        new_count = row["retry_count"] + 1
        now = datetime.utcnow().isoformat()
        if new_count >= MAX_OUTBOX_RETRIES:
            await self._db.execute(
                "UPDATE session_outbox SET status = 'failed', retry_count = ?, "
                "last_retry_at = ?, error_message = ? WHERE id = ?",
                (new_count, now, err, row["id"]),
            )
        else:
            await self._db.execute(
                "UPDATE session_outbox SET retry_count = ?, last_retry_at = ?, "
                "error_message = ? WHERE id = ?",
                (new_count, now, err, row["id"]),
            )

    async def _retry_loop(self):
        """后台重传循环 (固定间隔)。"""
        while self._running:
            try:
                await asyncio.sleep(self._retry_interval)
                if await self.outbox_pending_count() > 0:
                    await self.flush_outbox()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易 outbox 重试循环异常: {e}")

    # ---------- 生命周期 ----------

    async def start(self):
        """启动: 初始化 db + 恢复缓存 + 后台重传循环。"""
        self._running = True
        await self._init_db()
        self._retry_task = asyncio.create_task(self._retry_loop())
        logger.info("充电交易缓存与回传已启动")

    async def stop(self):
        """停止: 关闭后台任务与 db 连接。"""
        self._running = False
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
            self._retry_task = None
        if self._db:
            await self._db.close()
            self._db = None
        logger.info("充电交易缓存与回传已停止")


# 全局管理器实例
transaction_store = TransactionStore()
