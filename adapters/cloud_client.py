"""Cloud API Client — 边缘网关→云端对接

负责网关到云端Mock Server的HTTP通信：
- 网关注册/注销/心跳
- 遥测数据批量上报
- 告警上报
- 失败重试（指数退避）
- 断网时自动降级写入本地缓存
"""

import asyncio
import logging
import time
from typing import List, Optional, TYPE_CHECKING

import httpx

from config import CloudConfig
from models import TelemetryPoint

if TYPE_CHECKING:
    from storage.cache import TelemetryCache

logger = logging.getLogger(__name__)


class CloudClient:
    """云端API客户端

    负责将网关数据推送到云端服务器。
    - 失败时自动重试（指数退避，最多3次）
    - 重试耗尽后降级写入本地缓存（如有）
    - 不影响网关主流程
    """

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5  # seconds, exponential backoff base

    def __init__(self, config: CloudConfig, gateway_id: str,
                 cache: Optional["TelemetryCache"] = None):
        self.config = config
        self.gateway_id = gateway_id
        self.cache = cache  # 可选：断网降级缓存
        self._token: Optional[str] = None
        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """启动云端连接"""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30,
            ),
        )

        if self.config.register_on_startup:
            await self.register()

        if self.config.heartbeat_interval > 0:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 启动缓存恢复同步循环
        if self.cache:
            self._sync_task = asyncio.create_task(self._cache_sync_loop())

        logger.info("CloudClient started, base_url=%s", self.config.base_url)

    async def stop(self) -> None:
        """停止云端连接"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_sync_task') and self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        if self.config.deregister_on_shutdown:
            await self.deregister()

        if self._client:
            await self._client.aclose()

        logger.info("CloudClient stopped")

    async def register(self) -> bool:
        """网关注册"""
        try:
            r = await self._client.post("/api/v1/gateway/register", json={
                "gateway_id": self.gateway_id,
                "gateway_name": f"Gateway-{self.gateway_id}",
                "firmware_version": "0.1.0",
                "capabilities": ["ocpp", "modbus"],
            })
            if r.status_code == 200:
                self._registered = True
                logger.info("Cloud registered: %s", self.gateway_id)
                return True
            logger.warning("Cloud register failed: %d", r.status_code)
        except Exception as e:
            logger.warning("Cloud register error: %s", e)
        return False

    async def deregister(self) -> None:
        """网关注销"""
        if not self._registered:
            return
        try:
            await self._client.post(
                "/api/v1/gateway/deregister",
                params={"gateway_id": self.gateway_id},
            )
            self._registered = False
            logger.info("Cloud deregistered: %s", self.gateway_id)
        except Exception as e:
            logger.warning("Cloud deregister error: %s", e)

    async def push_telemetry_batch(self, points: List[TelemetryPoint]) -> bool:
        """批量推送遥测数据到云端（带重试 + 降级缓存）"""
        if not self._client or not points:
            return False

        payload = {
            "gateway_id": self.gateway_id,
            "timestamp": str(time.time()),
            "telemetry": [p.to_api_payload() for p in points],
        }

        ok = await self._post_with_retry(
            "/api/v1/telemetry/batch", payload, "telemetry_push"
        )
        if ok:
            logger.debug("Cloud telemetry pushed: %d points", len(points))
            return True

        # 云推送失败，主动写入本地缓存，_cache_sync_loop 会定期重试
        if self.cache:
            self.cache.cache_telemetry_batch(points)
            logger.info("Cloud telemetry push failed, %d points cached locally", len(points))
        else:
            logger.warning("Cloud telemetry push failed, no cache available")
        return False

    async def push_alarm(self, device_id: str, alarm_type: str,
                          severity: str, message: str) -> bool:
        """推送单个告警到云端（带重试 + 降级缓存）"""
        return await self.push_alarm_batch([{
            "device_id": device_id,
            "alarm_type": alarm_type,
            "severity": severity,
            "message": message,
        }])

    async def push_alarm_batch(self, alarms: List[dict]) -> bool:
        """批量推送告警到云端（带重试 + 降级缓存）

        Args:
            alarms: List of dicts with keys: device_id, alarm_type, severity, message

        Returns:
            True if all pushed, False if any failed
        """
        if not self._client or not alarms:
            return False

        now = str(time.time())
        payload = {
            "gateway_id": self.gateway_id,
            "timestamp": now,
            "alarms": [
                {
                    **a,
                    "timestamp": now,
                }
                for a in alarms
            ],
        }

        ok = await self._post_with_retry(
            "/api/v1/alarms/batch", payload, "alarm_batch_push"
        )
        if ok:
            logger.info("Cloud alarm batch pushed: %d alarms", len(alarms))
            return True

        # 云推送失败，主动写入本地缓存，_cache_sync_loop 会定期重试
        if self.cache:
            for a in alarms:
                self.cache.cache_alarm(a.get("device_id", "unknown"), a)
            logger.warning("Cloud alarm push failed, %d alarms cached locally", len(alarms))
        else:
            logger.warning("Cloud alarm push failed, no cache available")
        return False

    async def _post_with_retry(self, path: str, payload: dict,
                                 op_name: str) -> bool:
        """带指数退避重试的POST请求"""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                r = await self._client.post(path, json=payload)
                if r.status_code == 200:
                    return True
                # 4xx 不重试（客户端错误）
                if 400 <= r.status_code < 500:
                    logger.warning("%s rejected: %d %s", op_name, r.status_code, r.text[:200])
                    return False
                # 5xx 可重试
                last_error = f"HTTP {r.status_code}"
            except (httpx.ConnectError, httpx.TimeoutException,
                    httpx.RemoteProtocolError) as e:
                last_error = str(e)
            except Exception as e:
                last_error = str(e)

            # 指数退避（最后一次不等待）
            if attempt < self.MAX_RETRIES - 1:
                delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                logger.debug("%s retry %d/%d after %.1fs (%s)",
                             op_name, attempt + 1, self.MAX_RETRIES, delay, last_error)
                await asyncio.sleep(delay)

        logger.warning("%s failed after %d retries: %s",
                       op_name, self.MAX_RETRIES, last_error)
        return False

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            try:
                r = await self._client.post(
                    "/api/v1/gateway/heartbeat",
                    params={"gateway_id": self.gateway_id},
                )
                if r.status_code != 200:
                    logger.warning("Cloud heartbeat failed: %d", r.status_code)
            except Exception as e:
                logger.debug("Cloud heartbeat error: %s", e)

    async def _cache_sync_loop(self) -> None:
        """缓存恢复同步循环 — 网络恢复后自动上传积压数据

        T-1202 优化：
        - 动态间隔：有积压时加快轮询（5s），空闲时放慢（60s）
        - 告警优先同步（比遥测先）
        - 并行推送告警+遥测减少等待
        """
        idle_interval = 60   # 空闲时60秒检查一次
        active_interval = 5  # 有积压时5秒检查一次
        batch_size = 100     # 每次最多同步100条（提升吞吐）
        consecutive_idle = 0

        while True:
            try:
                # 告警优先（更重要）
                alarm_synced = await self._sync_cached_alarms(batch_size)
                # 遥测和告警并行（如果告警没积压）
                if alarm_synced == 0:
                    tel_synced = await self._sync_cached_telemetry(batch_size)
                else:
                    # 有告警积压时，先清告警再处理遥测
                    tel_synced = 0

                total_synced = alarm_synced + tel_synced
                if total_synced > 0:
                    consecutive_idle = 0
                    await asyncio.sleep(active_interval)
                else:
                    consecutive_idle += 1
                    # 连续3次空闲后逐渐增加间隔
                    interval = min(idle_interval, active_interval * (2 ** consecutive_idle))
                    await asyncio.sleep(interval)
            except Exception as e:
                logger.debug("Cache sync loop error: %s", e)
                await asyncio.sleep(active_interval)

    async def _sync_cached_telemetry(self, batch_size: int = 50) -> int:
        """同步积压的遥测缓存数据到云端"""
        if not self.cache or not self._client:
            return 0
        unsynced = self.cache.get_cloud_unsynced(limit=batch_size)
        if not unsynced:
            return 0

        ids = [item["id"] for item in unsynced]
        payload = {
            "gateway_id": self.gateway_id,
            "timestamp": str(time.time()),
            "telemetry": [item["payload"] for item in unsynced],
        }

        ok = await self._post_with_retry(
            "/api/v1/telemetry/batch", payload, "cache_sync_telemetry"
        )
        if ok:
            self.cache.mark_cloud_synced(ids)
            logger.info("Cache sync: %d telemetry points synced", len(ids))
            return len(ids)
        else:
            self.cache.increment_retry(ids)
            return 0

    async def _sync_cached_alarms(self, batch_size: int = 50) -> int:
        """同步积压的告警缓存数据到云端"""
        if not self.cache or not self._client:
            return 0
        unsynced = self.cache.get_cloud_unsynced_alarms(limit=batch_size)
        if not unsynced:
            return 0

        ids = [item["id"] for item in unsynced]
        alarms = [item["payload"] for item in unsynced]

        now = str(time.time())
        payload = {
            "gateway_id": self.gateway_id,
            "timestamp": now,
            "alarms": [{**a, "timestamp": now} for a in alarms],
        }

        ok = await self._post_with_retry(
            "/api/v1/alarms/batch", payload, "cache_sync_alarms"
        )
        if ok:
            self.cache.mark_alarms_cloud_synced(ids)
            logger.info("Cache sync: %d alarms synced", len(ids))
            return len(ids)
        else:
            self.cache.increment_alarm_retry(ids)
            return 0
