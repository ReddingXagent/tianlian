"""
Module 5: 断网续传
- 网络中断时本地缓存数据
- 恢复后自动补传
- SQLite 本地存储
- 缓存大小和时长管理
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import aiosqlite
from app.core.config import config
from app.core.http_client import cloud_client
from app.core.logging import logger


class OfflineBuffer:
    """断网续传缓存管理器"""

    def __init__(self):
        self.buffer_config = config.offline_buffer
        self._db: Optional[aiosqlite.Connection] = None
        self._retry_task: Optional[asyncio.Task] = None
        self._running = False
        self._online: bool = True
        self._total_buffered: int = 0
        self._total_retried: int = 0
        self._total_flushed: int = 0

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "online": self._online,
            "total_buffered": self._total_buffered,
            "total_retried": self._total_retried,
            "total_flushed": self._total_flushed,
        }

    async def _init_db(self):
        """初始化本地缓存数据库"""
        db_path = Path(self.buffer_config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(str(db_path))
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS offline_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                last_retry_at TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_buffer_status
            ON offline_buffer(status, created_at)
        """)
        await self._db.commit()
        logger.info(f"离线缓存数据库已初始化 [{db_path}]")

    async def store(self, endpoint: str, payload: Dict[str, Any]) -> bool:
        """存储数据到本地缓存"""
        if not self._db:
            return False

        try:
            await self._db.execute(
                """INSERT INTO offline_buffer (endpoint, payload, created_at, status)
                   VALUES (?, ?, ?, 'pending')""",
                (endpoint, json.dumps(payload), datetime.utcnow().isoformat()),
            )
            await self._db.commit()
            self._total_buffered += 1

            # 检查缓存大小
            await self._enforce_size_limit()
            return True
        except Exception as e:
            logger.error(f"缓存存储失败: {e}")
            return False

    async def _enforce_size_limit(self):
        """执行缓存大小限制"""
        if not self._db:
            return

        max_bytes = self.buffer_config.max_buffer_size_mb * 1024 * 1024

        # 获取数据库文件大小
        db_path = Path(self.buffer_config.db_path)
        if db_path.exists() and db_path.stat().st_size > max_bytes:
            # 删除最旧的数据
            await self._db.execute("""
                DELETE FROM offline_buffer WHERE id IN (
                    SELECT id FROM offline_buffer
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT (SELECT COUNT(*) * 0.2 FROM offline_buffer)
                )
            """)
            await self._db.execute("VACUUM")
            await self._db.commit()
            logger.warning("离线缓存已超过大小限制，已清理旧数据")

    async def _enforce_age_limit(self):
        """执行缓存时长限制"""
        if not self._db:
            return

        cutoff = (datetime.utcnow() - timedelta(
            hours=self.buffer_config.max_buffer_age_hours
        )).isoformat()

        await self._db.execute(
            "DELETE FROM offline_buffer WHERE created_at < ? AND status = 'pending'",
            (cutoff,),
        )
        await self._db.commit()

    async def get_pending_count(self) -> int:
        """获取待发送数据数量"""
        if not self._db:
            return 0

        cursor = await self._db.execute(
            "SELECT COUNT(*) as cnt FROM offline_buffer WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def flush_pending(self, batch_size: int = 50) -> int:
        """批量发送缓存数据"""
        if not self._db:
            return 0

        # 获取待发送数据
        cursor = await self._db.execute(
            """SELECT id, endpoint, payload, retry_count
               FROM offline_buffer
               WHERE status = 'pending'
               ORDER BY created_at ASC
               LIMIT ?""",
            (batch_size,),
        )
        rows = await cursor.fetchall()

        if not rows:
            return 0

        flushed = 0
        for row in rows:
            try:
                payload = json.loads(row["payload"])
                result = await cloud_client.post(row["endpoint"], payload)

                if result:
                    # 标记为已发送
                    await self._db.execute(
                        "UPDATE offline_buffer SET status = 'flushed' WHERE id = ?",
                        (row["id"],),
                    )
                    flushed += 1
                    self._total_flushed += 1
                else:
                    # 更新重试次数
                    new_count = row["retry_count"] + 1
                    if new_count >= 10:
                        # 超过最大重试次数，标记为失败
                        await self._db.execute(
                            """UPDATE offline_buffer
                               SET status = 'failed', retry_count = ?,
                                   last_retry_at = ?, error_message = 'Max retries exceeded'
                               WHERE id = ?""",
                            (new_count, datetime.utcnow().isoformat(), row["id"]),
                        )
                    else:
                        await self._db.execute(
                            """UPDATE offline_buffer
                               SET retry_count = ?, last_retry_at = ?
                               WHERE id = ?""",
                            (new_count, datetime.utcnow().isoformat(), row["id"]),
                        )
                    self._total_retried += 1

            except Exception as e:
                logger.error(f"缓存数据发送异常 [id={row['id']}]: {e}")
                await self._db.execute(
                    """UPDATE offline_buffer
                       SET retry_count = retry_count + 1,
                           last_retry_at = ?, error_message = ?
                       WHERE id = ?""",
                    (datetime.utcnow().isoformat(), str(e)[:500], row["id"]),
                )

        await self._db.commit()

        if flushed > 0:
            logger.info(f"离线缓存已补传: {flushed}/{len(rows)} 条")

        return flushed

    async def _connectivity_monitor(self):
        """网络连通性监控"""
        while self._running:
            try:
                was_online = self._online
                self._online = await cloud_client.check_connectivity()

                if not was_online and self._online:
                    # 网络恢复
                    logger.info("网络已恢复，开始补传缓存数据")
                    await self.flush_pending(batch_size=100)
                elif was_online and not self._online:
                    # 网络中断
                    logger.warning("网络已中断，数据将缓存到本地")

                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"连通性监控异常: {e}")
                await asyncio.sleep(5)

    async def _retry_loop(self):
        """定期重试发送缓存数据"""
        while self._running:
            try:
                await asyncio.sleep(self.buffer_config.retry_interval_seconds)

                if self._online:
                    pending = await self.get_pending_count()
                    if pending > 0:
                        logger.debug(f"离线缓存待发送: {pending} 条")
                        await self.flush_pending(batch_size=50)

                # 定期清理过期数据
                await self._enforce_age_limit()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"重试循环异常: {e}")

    async def start(self):
        """启动断网续传"""
        if not self.buffer_config.enabled:
            logger.info("断网续传已禁用")
            return

        self._running = True
        await self._init_db()

        # 启动连通性监控
        asyncio.create_task(self._connectivity_monitor())

        # 启动重试循环
        self._retry_task = asyncio.create_task(self._retry_loop())

        logger.info("断网续传已启动")

    async def stop(self):
        """停止断网续传"""
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

        logger.info("断网续传已停止")


# 全局断网续传管理器
offline_buffer = OfflineBuffer()
