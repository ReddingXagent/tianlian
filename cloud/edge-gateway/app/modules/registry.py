"""
Module 1: 网关注册心跳
- 网关启动时向云端注册
- 定期心跳上报
- 连接状态管理
"""
import asyncio
from datetime import datetime
from typing import Optional
from app.core.config import config
from app.core.http_client import cloud_client
from app.core.logging import logger


class GatewayRegistry:
    """网关注册与心跳管理器"""

    def __init__(self):
        self.gateway_config = config.gateway
        self.heartbeat_config = config.heartbeat
        self.cloud_config = config.cloud
        self._registered: bool = False
        self._gateway_id: Optional[int] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._last_heartbeat: Optional[datetime] = None
        self._online: bool = False

    @property
    def gateway_id(self) -> Optional[int]:
        return self._gateway_id

    @property
    def is_registered(self) -> bool:
        return self._registered

    @property
    def is_online(self) -> bool:
        return self._online

    async def register(self) -> bool:
        """向云端注册网关"""
        logger.info(f"正在向云端注册网关 [SN: {self.gateway_config.sn}]...")

        payload = {
            "sn": self.gateway_config.sn,
            "name": self.gateway_config.name,
            "model": self.gateway_config.model,
            "manufacturer": self.gateway_config.manufacturer,
            "station_id": self.gateway_config.station_id,
            "status": "online",
            "firmware_version": "1.0.0",
            "location": self.gateway_config.location,
        }

        # 尝试注册
        for attempt in range(1, 4):
            result = await cloud_client.post(
                self.cloud_config.register_endpoint,
                payload,
            )
            if result:
                # 提取网关ID
                data = result.get("data", result)
                if isinstance(data, dict):
                    self._gateway_id = data.get("id")
                self._registered = True
                self._online = True
                self._last_heartbeat = datetime.utcnow()
                logger.info(f"网关注册成功 [ID: {self._gateway_id}, SN: {self.gateway_config.sn}]")
                return True

            logger.warning(f"注册失败，{attempt}/3 次重试...")
            await asyncio.sleep(2 ** attempt)

        logger.error("网关注册失败，已达最大重试次数")
        return False

    async def send_heartbeat(self) -> bool:
        """发送心跳"""
        if not self._registered:
            logger.warning("网关未注册，跳过心跳")
            return False

        payload = {
            "sn": self.gateway_config.sn,
            "status": "online",
            "timestamp": datetime.utcnow().isoformat(),
            "gateway_id": self._gateway_id,
            "metrics": {
                "cpu_percent": await self._get_cpu_usage(),
                "memory_percent": await self._get_memory_usage(),
                "uptime_seconds": await self._get_uptime(),
            },
        }

        try:
            result = await cloud_client.post(
                self.cloud_config.heartbeat_endpoint,
                payload,
            )
            if result:
                self._last_heartbeat = datetime.utcnow()
                self._online = True
                logger.debug(f"心跳上报成功 [SN: {self.gateway_config.sn}]")
                return True
            else:
                self._online = False
                logger.warning("心跳上报失败")
                return False
        except Exception as e:
            self._online = False
            logger.error(f"心跳上报异常: {e}")
            return False

    async def _heartbeat_loop(self):
        """心跳循环"""
        logger.info(
            f"心跳循环已启动 [间隔: {self.heartbeat_config.interval_seconds}s]"
        )
        while True:
            try:
                await asyncio.sleep(self.heartbeat_config.interval_seconds)
                await self.send_heartbeat()
            except asyncio.CancelledError:
                logger.info("心跳循环已停止")
                break
            except Exception as e:
                logger.error(f"心跳循环异常: {e}")

    async def start(self):
        """启动注册与心跳"""
        # 先注册
        success = await self.register()
        if not success:
            logger.warning("注册失败，将在后台重试")

        # 启动心跳循环
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        """停止心跳"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        self._online = False
        logger.info("网关心跳已停止")

    async def _get_cpu_usage(self) -> float:
        """获取 CPU 使用率"""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return 0.0

    async def _get_memory_usage(self) -> float:
        """获取内存使用率"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.percent
        except ImportError:
            return 0.0

    async def _get_uptime(self) -> float:
        """获取运行时长（秒）"""
        try:
            import psutil
            import time
            return time.time() - psutil.boot_time()
        except ImportError:
            return 0.0


# 全局注册管理器
gateway_registry = GatewayRegistry()
