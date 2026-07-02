"""Cloud API Client — 边缘网关→云端对接 (V3 API对齐版)

对接云端 8.134.106.166 天链V3系统：
- Pod注册/心跳 (pod/register, pod/heartbeat)
- 遥测数据批量上报 (telemetry/batch-report)
- 告警上报 (alarms)
- 失败重试（指数退避）
- 断网时自动降级写入本地缓存

API对齐日期: 2026-07-02
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
    """云端API客户端 (V3对齐)

    负责将网关(Pod)数据推送到云端服务器。
    - 失败时自动重试（指数退避，最多3次）
    - 重试耗尽后降级写入本地缓存（如有）
    - 不影响网关主流程
    """

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5  # seconds, exponential backoff base

    def __init__(self, config: CloudConfig, gateway_id: str,
                 cache: Optional["TelemetryCache"] = None):
        self.config = config
        self.gateway_id = gateway_id  # 对应云端的 pod_id
        self.region_id = getattr(config, 'region_id', 'default')
        self.cache = cache
        self._token: Optional[str] = None
        self._csrf_token: str = ""
        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def pod_id(self) -> str:
        """pod_id = gateway_id (V3命名对齐)"""
        return self.gateway_id

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

        # 获取 CSRF token（云端 Django 要求）
        await self._fetch_csrf_token()

        # 设置认证 token
        if self.config.token:
            self._token = self.config.token

        if self.config.register_on_startup:
            await self.register()

        if self.config.heartbeat_interval > 0:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 启动缓存恢复同步循环
        if self.cache:
            self._sync_task = asyncio.create_task(self._cache_sync_loop())

        logger.info("CloudClient started, base_url=%s, pod_id=%s",
                     self.config.base_url, self.pod_id)

    async def _fetch_csrf_token(self) -> None:
        """从云端获取 CSRF token（Django CSRF 中间件要求）"""
        try:
            r = await self._client.get("/api/v1/health")
            self._csrf_token = r.cookies.get("tianlian_csrf_token", "")
            if self._csrf_token:
                logger.debug("CSRF token acquired")
        except Exception:
            self._csrf_token = ""

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

    # ============================================================
    # Pod 注册/注销/心跳 (对齐 V3 pod/ 系列端点)
    # ============================================================

    async def register(self) -> bool:
        """Pod注册 → POST /api/v1/pod/register"""
        try:
            headers = {}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            if self._csrf_token:
                headers["X-CSRF-Token"] = self._csrf_token
                headers["Cookie"] = f"tianlian_csrf_token={self._csrf_token}"
            r = await self._client.post("/api/v1/pod/register", json={
                "pod_id": self.pod_id,
                "region_id": self.region_id,
                "endpoint": f"http://{self.gateway_id}:8080",
                "version": "3.0.0",
            }, headers=headers)
            if r.status_code == 200:
                self._registered = True
                logger.info("Cloud registered: pod_id=%s", self.pod_id)
                return True
            logger.warning("Cloud register failed: %d %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Cloud register error: %s", e)
        return False

    async def deregister(self) -> None:
        """Pod注销 (保留兼容路径，云端暂无deregister端点)"""
        if not self._registered:
            return
        try:
            headers = {}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            if self._csrf_token:
                headers["X-CSRF-Token"] = self._csrf_token
                headers["Cookie"] = f"tianlian_csrf_token={self._csrf_token}"
            r = await self._client.post(
                "/api/v1/pod/heartbeat",
                json={"pod_id": self.pod_id, "load": 0},
                headers=headers,
            )
            self._registered = False
            logger.info("Cloud deregistered: pod_id=%s", self.pod_id)
        except Exception as e:
            logger.warning("Cloud deregister error: %s", e)

    # ============================================================
    # 遥测推送 (对齐 V3 telemetry/batch-report 端点)
    # ============================================================

    async def push_telemetry_batch(self, points: List[TelemetryPoint]) -> bool:
        """批量推送遥测数据到云端 → POST /api/v1/telemetry/batch-report"""
        if not self._client or not points:
            return False

        records = [p.to_api_payload() for p in points]

        payload = {
            "pod_id": self.pod_id,
            "region_id": self.region_id,
            "records": records,
        }

        ok = await self._post_with_retry(
            "/api/v1/telemetry/batch-report", payload, "telemetry_push"
        )
        if ok:
            logger.debug("Cloud telemetry pushed: %d points", len(points))
            return True

        # 云推送失败，主动写入本地缓存
        if self.cache:
            self.cache.cache_telemetry_batch(points)
            logger.info("Cloud telemetry push failed, %d points cached locally", len(points))
        else:
            logger.warning("Cloud telemetry push failed, no cache available")
        return False

    # ============================================================
    # 告警推送 (对齐 V3 alarms 端点，逐条POST)
    # ============================================================

    async def push_alarm(self, device_id: str, alarm_type: str,
                          severity: str, message: str) -> bool:
        """推送单个告警 → POST /api/v1/alarms"""
        if not self._client:
            return False

        payload = {
            "device_id": device_id,
            "alarm_type": alarm_type,
            "level": severity,
            "content": message,
        }

        ok = await self._post_with_retry(
            "/api/v1/alarms", payload, "alarm_push"
        )
        if ok:
            logger.info("Cloud alarm pushed: %s/%s", device_id, alarm_type)
            return True

        # 降级缓存
        if self.cache:
            self.cache.cache_alarm(device_id, {
                "device_id": device_id,
                "alarm_type": alarm_type,
                "severity": severity,
                "message": message,
            })
        return False

    async def push_alarm_batch(self, alarms: List[dict]) -> bool:
        """批量推送告警 → 逐条 POST /api/v1/alarms (云端无batch端点)

        Returns:
            True if ALL pushed, False if any failed
        """
        if not self._client or not alarms:
            return False

        all_ok = True
        for a in alarms:
            payload = {
                "device_id": a.get("device_id", "unknown"),
                "alarm_type": a.get("alarm_type", "unknown"),
                "level": a.get("severity", "info"),
                "content": a.get("message", ""),
            }
            ok = await self._post_with_retry(
                "/api/v1/alarms", payload, "alarm_batch_push"
            )
            if ok:
                logger.debug("Cloud alarm pushed: %s/%s",
                             a.get("device_id"), a.get("alarm_type"))
            else:
                all_ok = False
                if self.cache:
                    self.cache.cache_alarm(a.get("device_id", "unknown"), a)
                logger.warning("Cloud alarm push failed, cached locally")

        if not all_ok and not self.cache:
            logger.warning("Cloud alarm batch push partially failed, no cache available")
        return all_ok

    # ============================================================
    # 内部重试机制
    # ============================================================

    async def _post_with_retry(self, path: str, payload: dict,
                                 op_name: str) -> bool:
        """带指数退避重试的POST请求"""
        last_error = None
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if hasattr(self, "_csrf_token") and self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
            headers["Cookie"] = f"tianlian_csrf_token={self._csrf_token}"
            headers["Referer"] = self.config.base_url + "/"
        for attempt in range(self.MAX_RETRIES):
            try:
                r = await self._client.post(path, json=payload, headers=headers)
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

    # ============================================================
    # 心跳循环
    # ============================================================

    async def _heartbeat_loop(self) -> None:
        """心跳循环 → POST /api/v1/pod/heartbeat"""
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            try:
                headers = {}
                if self._token:
                    headers["Authorization"] = f"Bearer {self._token}"
                if self._csrf_token:
                    headers["X-CSRF-Token"] = self._csrf_token
                    headers["Cookie"] = f"tianlian_csrf_token={self._csrf_token}"
                r = await self._client.post(
                    "/api/v1/pod/heartbeat",
                    json={"pod_id": self.pod_id, "load": 0},
                    headers=headers,
                )
                if r.status_code != 200:
                    logger.warning("Cloud heartbeat failed: %d", r.status_code)
                else:
                    logger.debug("Cloud heartbeat OK: pod_id=%s", self.pod_id)
            except Exception as e:
                logger.debug("Cloud heartbeat error: %s", e)

    # ============================================================
    # 缓存恢复同步循环
    # ============================================================

    async def _cache_sync_loop(self) -> None:
        """缓存恢复同步循环 — 网络恢复后自动上传积压数据"""
        idle_interval = 60
        active_interval = 5
        batch_size = 100
        consecutive_idle = 0

        while True:
            try:
                alarm_synced = await self._sync_cached_alarms(batch_size)
                if alarm_synced == 0:
                    tel_synced = await self._sync_cached_telemetry(batch_size)
                else:
                    tel_synced = 0

                total_synced = alarm_synced + tel_synced
                if total_synced > 0:
                    consecutive_idle = 0
                    await asyncio.sleep(active_interval)
                else:
                    consecutive_idle += 1
                    interval = min(idle_interval, active_interval * (2 ** consecutive_idle))
                    await asyncio.sleep(interval)
            except Exception as e:
                logger.debug("Cache sync loop error: %s", e)
                await asyncio.sleep(active_interval)

    async def _sync_cached_telemetry(self, batch_size: int = 50) -> int:
        """同步积压的遥测缓存数据到云端 → POST /api/v1/telemetry/batch-report"""
        if not self.cache or not self._client:
            return 0
        unsynced = self.cache.get_cloud_unsynced(limit=batch_size)
        if not unsynced:
            return 0

        ids = [item["id"] for item in unsynced]
        records = [item["payload"] for item in unsynced]

        payload = {
            "pod_id": self.pod_id,
            "region_id": self.region_id,
            "records": records,
        }

        ok = await self._post_with_retry(
            "/api/v1/telemetry/batch-report", payload, "cache_sync_telemetry"
        )
        if ok:
            self.cache.mark_cloud_synced(ids)
            logger.info("Cache sync: %d telemetry points synced", len(ids))
            return len(ids)
        else:
            self.cache.increment_retry(ids)
            return 0

    async def _sync_cached_alarms(self, batch_size: int = 50) -> int:
        """同步积压的告警缓存 → 逐条 POST /api/v1/alarms"""
        if not self.cache or not self._client:
            return 0
        unsynced = self.cache.get_cloud_unsynced_alarms(limit=batch_size)
        if not unsynced:
            return 0

        synced_count = 0
        for item in unsynced:
            a = item["payload"]
            payload = {
                "device_id": a.get("device_id", "unknown"),
                "alarm_type": a.get("alarm_type", "unknown"),
                "level": a.get("severity", "info"),
                "content": a.get("message", ""),
            }
            ok = await self._post_with_retry(
                "/api/v1/alarms", payload, "cache_sync_alarms"
            )
            if ok:
                synced_count += 1

        if synced_count > 0:
            synced_ids = [item["id"] for item in unsynced[:synced_count]]
            self.cache.mark_alarms_cloud_synced(synced_ids)
            logger.info("Cache sync: %d alarms synced", synced_count)

        if synced_count < len(unsynced):
            failed_ids = [item["id"] for item in unsynced[synced_count:]]
            self.cache.increment_alarm_retry(failed_ids)

        return synced_count