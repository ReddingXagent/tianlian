"""
WebSocket 统一连接管理器
整合三个现有实现的连接管理逻辑

Phase34:
- 心跳保活机制 (ping/pong, 30s interval)
- 连接数限制 (默认每频道 100, 总连接 500)
- 自动清理过期连接
"""
from fastapi import WebSocket
from typing import Dict, List, Set, Optional
import os
from datetime import datetime, timezone
import asyncio
import logging

from app.ws.schemas import WebSocketMessage

logger = logging.getLogger(__name__)

# ─── 连接数限制 ───
MAX_CHANNEL_CONNECTIONS = int(os.getenv("WS_MAX_CHANNEL", "100"))  # 单频道最大连接数
MAX_TOTAL_CONNECTIONS = int(os.getenv("WS_MAX_TOTAL", "500"))      # 总连接数上限
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))  # 心跳间隔(秒)
WS_HEARTBEAT_TIMEOUT = int(os.getenv("WS_HEARTBEAT_TIMEOUT", "90"))      # 心跳超时(秒)
WS_SEND_TIMEOUT = float(os.getenv("WS_SEND_TIMEOUT", "5"))               # 单次发送超时(秒), 防「半死客户端」无限阻塞
WS_CLOSE_TIMEOUT = float(os.getenv("WS_CLOSE_TIMEOUT", "2"))             # 驱逐时 close 的短超时(秒)


class WebSocketManager:
    """统一WebSocket连接管理器"""

    def __init__(self):
        # 按频道分组的连接
        self.channel_connections: Dict[str, List[WebSocket]] = {
            "realtime": [],
            "digital_twin": [],
            "dashboard": [],
            "alerts": [],
            "workorders": [],
            "devices": [],
            "fleet_queue": [],
            "fleet_v2g": [],
            "large_screen": [],  # (卡 0bef02bc) 缺此键导致该频道 get_channel_count 恒 0
        }

        # 按站点分组的连接(数字孪生)
        self.station_connections: Dict[int, Set[WebSocket]] = {}

        # 按设备订阅的连接(数字孪生)
        self.device_subscriptions: Dict[int, Set[WebSocket]] = {}

        # 所有活跃连接(用于全局广播)
        self.all_connections: Set[WebSocket] = set()

        # 连接元数据
        self.connection_metadata: Dict[WebSocket, Dict] = {}

        # 心跳状态
        self._last_heartbeat: Dict[WebSocket, float] = {}

        # 心跳任务引用
        self._heartbeat_task: Optional[asyncio.Task] = None

        # connect 串行化锁: 保证 连接数检查 → accept → 登记 三步原子,
        # 避免并发 connect 在 await accept 让出期间越过连接数上限
        # 延迟创建, 见 _connect_lock 属性(Python<3.10 在无运行 loop 的线程
        # 中构造 asyncio.Lock() 会抛 RuntimeError, 故不在 __init__ 直接 new)
        self._connect_lock_instance: Optional[asyncio.Lock] = None

        logger.info(
            "WebSocket管理器初始化: max_channel=%s max_total=%s heartbeat=%ss",
            MAX_CHANNEL_CONNECTIONS, MAX_TOTAL_CONNECTIONS, WS_HEARTBEAT_INTERVAL,
        )

    @property
    def _connect_lock(self) -> asyncio.Lock:
        """
        延迟创建 connect 串行化锁。

        Python<3.10 下 ``asyncio.Lock()`` 在构造时即调用 ``get_event_loop()``
        绑定事件循环; 若在 ``__init__`` 中直接构造, 当实例在无运行 loop 的上下文中
        创建 (例如模块导入期或非主线程) 会抛
        ``RuntimeError: There is no current event loop``。

        延迟到首次 ``async with self._connect_lock`` 才构造 —— 该访问必然发生在
        协程内 (有运行 loop), 既兼容 3.9 测试环境, 又绑定到实际运行的 loop。
        3.10+ 的 ``asyncio.Lock`` 本就是 lazy, 行为一致。
        """
        if self._connect_lock_instance is None:
            self._connect_lock_instance = asyncio.Lock()
        return self._connect_lock_instance

    async def connect(
        self,
        websocket: WebSocket,
        channel: str = "realtime",
        station_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ):
        """连接到指定频道"""
        # ─── 串行化: 检查 → accept → 登记 必须原子 ───
        # 否则并发 connect 会在 await accept 让出期间双双通过上限检查
        async with self._connect_lock:
            # ─── 连接数检查 ───
            if len(self.all_connections) >= MAX_TOTAL_CONNECTIONS:
                logger.warning("总连接数已达上限(%s), 拒绝新连接", MAX_TOTAL_CONNECTIONS)
                await websocket.close(code=1013, reason="连接数已达上限")
                return {"channel": channel, "station_id": station_id, "rejected": True}

            if channel in self.channel_connections and len(self.channel_connections[channel]) >= MAX_CHANNEL_CONNECTIONS:
                logger.warning("频道 %s 连接数已达上限(%s)", channel, MAX_CHANNEL_CONNECTIONS)
                await websocket.close(code=1013, reason=f"频道{channel}连接数已达上限")
                return {"channel": channel, "station_id": station_id, "rejected": True}

            await websocket.accept()

            # 加入频道连接列表
            if channel in self.channel_connections:
                self.channel_connections[channel].append(websocket)

            # 数字孪生站点连接
            if station_id is not None:
                if station_id not in self.station_connections:
                    self.station_connections[station_id] = set()
                self.station_connections[station_id].add(websocket)

            # 加入全局连接集合
            self.all_connections.add(websocket)

            # 存储连接元数据
            now_ts = datetime.now(timezone.utc).isoformat()
            self.connection_metadata[websocket] = {
                "channel": channel,
                "station_id": station_id,
                "connected_at": now_ts,
                "last_activity_at": now_ts,
                "metadata": metadata or {},
            }

            # 初始化心跳时间戳
            self._last_heartbeat[websocket] = datetime.now(timezone.utc).timestamp()

            logger.info(
                "WebSocket连接成功: channel=%s, station_id=%s, channel_count=%s, active_connections=%s",
                channel, station_id,
                len(self.channel_connections.get(channel, [])),
                len(self.all_connections),
            )

            return {"channel": channel, "station_id": station_id}

    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        # 获取连接元数据
        meta = self.connection_metadata.get(websocket, {})
        channel = meta.get("channel", "realtime")
        station_id = meta.get("station_id")

        # 从频道列表移除
        if channel in self.channel_connections:
            if websocket in self.channel_connections[channel]:
                self.channel_connections[channel].remove(websocket)

        # 从站点连接移除 (空集合清键, 防长运行 dict 无限增长 — 卡51cdf2e4)
        if station_id and station_id in self.station_connections:
            self.station_connections[station_id].discard(websocket)
            if not self.station_connections[station_id]:
                del self.station_connections[station_id]

        # 从设备订阅移除 (空集合清键, 同上)
        for device_id in list(self.device_subscriptions.keys()):
            self.device_subscriptions[device_id].discard(websocket)
            if not self.device_subscriptions[device_id]:
                del self.device_subscriptions[device_id]

        # 从全局集合移除
        self.all_connections.discard(websocket)

        # 清理元数据
        self.connection_metadata.pop(websocket, None)
        self._last_heartbeat.pop(websocket, None)

        logger.info(
            "WebSocket断开连接: channel=%s, station_id=%s, channel_count=%s, active_connections=%s",
            channel, station_id,
            len(self.channel_connections.get(channel, [])),
            len(self.all_connections),
        )

    def _is_ws_alive(self, websocket: WebSocket) -> bool:
        """检查 WebSocket 是否应被认为存活 (基于心跳)"""
        last = self._last_heartbeat.get(websocket)
        if last is None:
            return False
        return (datetime.now(timezone.utc).timestamp() - last) < WS_HEARTBEAT_TIMEOUT

    async def _evict(self, connection: WebSocket, reason: str):
        """驱逐慢/坏连接: 短超时 close + disconnect, 永不向上抛 (卡 faead57b)"""
        logger.warning("驱逐连接 (%s)", reason)
        await self._close_with_timeout(connection, code=1001, reason="发送超时")
        self.disconnect(connection)

    @staticmethod
    async def _timed(coro, timeout: float) -> Optional[BaseException]:
        """带超时跑协程, 返回其异常 (None=成功); 返回 asyncio.TimeoutError() 表示超时。

        故意不用 asyncio.wait_for: CPython 3.11 的 wait_for 在「外层 task 被 cancel
        且内部 future 恰已完成」的竞态下会吞掉 CancelledError 直接返回结果,
        导致路由层的推送循环取消不掉、永远活着 (实测: pytest teardown 挂 120s)。
        asyncio.wait 不吞外层 cancel; 外层 cancel 到来时同步取消内部任务再传播。
        """
        task = asyncio.ensure_future(coro)
        try:
            await asyncio.wait({task}, timeout=timeout)
        except asyncio.CancelledError:
            task.cancel()
            raise
        if not task.done():
            task.cancel()
            return asyncio.TimeoutError()
        if task.cancelled():
            return asyncio.CancelledError()
        return task.exception()

    async def _close_with_timeout(self, connection: WebSocket, code: int = 1000, reason: str = ""):
        """短超时 close, 失败/超时都吞掉 (仅记 debug)"""
        err = await self._timed(connection.close(code=code, reason=reason), timeout=WS_CLOSE_TIMEOUT)
        if err is not None:
            logger.debug("close 失败 (忽略): %s", err)

    async def _send_with_timeout(self, connection: WebSocket, message: WebSocketMessage) -> bool:
        """带超时发送: 成功 True; 超时/异常 False (由调用方驱逐) — 卡 faead57b

        半死客户端 (TCP 存活但不读) 会让裸 await send_json 无限阻塞;
        超时后驱逐该连接, 不打断其余连接的广播循环。
        """
        err = await self._timed(connection.send_json(message.dict()), timeout=WS_SEND_TIMEOUT)
        if err is None:
            return True
        logger.warning(
            "发送%s, 驱逐客户端: %s, err=%s",
            "超时 (>%ss)" % WS_SEND_TIMEOUT if isinstance(err, asyncio.TimeoutError) else "失败",
            connection, err,
        )
        return False

    async def _heartbeat_pass_once(self):
        """心跳单轮逻辑 (从 _heartbeat_loop 抽出以便单测)"""
        now = datetime.now(timezone.utc).timestamp()

        stale_connections = []
        for ws in list(self.all_connections):
            last = self._last_heartbeat.get(ws, 0)
            elapsed = now - last

            if elapsed > WS_HEARTBEAT_TIMEOUT:
                # 超时: 标记为过期
                stale_connections.append(ws)
                continue

            if not await self._send_with_timeout(
                ws,
                WebSocketMessage(
                    type="heartbeat",
                    channel="realtime",
                    payload={"ping": "send"},
                ),
            ):
                # ping 超时/失败 → 视为过期 (与原 except Exception 同路)
                stale_connections.append(ws)

        # 清理过期连接
        for ws in stale_connections:
            logger.info("心跳超时，清理连接: elapsed=%.0fs", now - self._last_heartbeat.get(ws, 0))
            await self._close_with_timeout(ws, code=1000, reason="心跳超时")
            self.disconnect(ws)

        if stale_connections:
            logger.info("心跳清理完成: 清理 %s 个过期连接, 剩余 %s", len(stale_connections), len(self.all_connections))

    async def _heartbeat_loop(self):
        """后台心跳保活循环"""
        while True:
            try:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                await self._heartbeat_pass_once()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("心跳循环异常: %s", e)
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)

    async def start_heartbeat(self):
        """启动心跳保活 (由 startup 事件调用)"""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("心跳保活任务已启动 (间隔=%ss, 超时=%ss)", WS_HEARTBEAT_INTERVAL, WS_HEARTBEAT_TIMEOUT)

    async def stop_heartbeat(self):
        """停止心跳保活"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("心跳保活任务已停止")

    def record_heartbeat(self, websocket: WebSocket):
        """记录客户端心跳"""
        self._last_heartbeat[websocket] = datetime.now(timezone.utc).timestamp()
        meta = self.connection_metadata.get(websocket)
        if meta:
            meta["last_activity_at"] = datetime.now(timezone.utc).isoformat()

    def subscribe_device(self, websocket: WebSocket, device_id: int):
        """订阅特定设备的实时数据"""
        if device_id not in self.device_subscriptions:
            self.device_subscriptions[device_id] = set()
        self.device_subscriptions[device_id].add(websocket)
        logger.info("订阅设备: device_id=%s", device_id)

    def unsubscribe_device(self, websocket: WebSocket, device_id: int):
        """取消订阅设备"""
        if device_id in self.device_subscriptions:
            self.device_subscriptions[device_id].discard(websocket)
            logger.info("取消订阅设备: device_id=%s", device_id)

    async def send_personal_message(self, message: WebSocketMessage, websocket: WebSocket):
        """发送个人消息"""
        if not await self._send_with_timeout(websocket, message):
            await self._evict(websocket, "send_personal_message 超时/失败")

    async def broadcast_channel(self, message: WebSocketMessage, channel: str):
        """广播到指定频道"""
        # 快照遍历: await 期间 disconnect 可能修改 list (参照 broadcast_all)
        for connection in list(self.channel_connections.get(channel, [])):
            if not await self._send_with_timeout(connection, message):
                await self._evict(connection, f"broadcast_channel({channel}) 超时/失败")

    async def broadcast_station(self, station_id: int, message: WebSocketMessage):
        """广播到指定站点的所有连接"""
        # 快照遍历: await 期间 disconnect 可能修改 set (参照 broadcast_all)
        for connection in set(self.station_connections.get(station_id, set())):
            if not await self._send_with_timeout(connection, message):
                await self._evict(connection, f"broadcast_station({station_id}) 超时/失败")

    async def broadcast_device_subscribers(self, device_id: int, message: WebSocketMessage):
        """广播到订阅了特定设备的所有连接"""
        # 快照遍历: await 期间 disconnect 可能修改 set (参照 broadcast_all)
        for connection in set(self.device_subscriptions.get(device_id, set())):
            if not await self._send_with_timeout(connection, message):
                await self._evict(connection, f"broadcast_device_subscribers({device_id}) 超时/失败")

    async def broadcast_all(self, message: WebSocketMessage):
        """全局广播"""
        for connection in list(self.all_connections):
            if not await self._send_with_timeout(connection, message):
                await self._evict(connection, "broadcast_all 超时/失败")

    async def broadcast_team_scoped(self, message: WebSocketMessage, team_id=None):
        """团队作用域广播 (卡 434f741a): 只发 team_id 匹配的连接 + 平台 admin 连接。

        过滤依据 connection_metadata 的 metadata.team_id / metadata.role:
          - 连接属主为平台 admin (metadata.team_id 为 None) → 收全量;
          - 否则只收 metadata.team_id == team_id 的连接;
          - 消息 team_id 为 None (工单无归属站点) → 只发 admin 连接。
        与 broadcast_all 同为快照遍历: await 期间 disconnect 可能修改 set。
        """
        for connection in list(self.all_connections):
            meta = self.connection_metadata.get(connection, {}).get("metadata", {})
            conn_team = meta.get("team_id")
            if conn_team is None:
                # 平台 admin 连接 (connect 时 metadata.team_id 归一为 None) → 收全量
                pass
            elif team_id is not None and conn_team == team_id:
                # 团队级连接, 归属匹配 → 收
                pass
            else:
                continue
            if not await self._send_with_timeout(connection, message):
                await self._evict(connection, f"broadcast_team_scoped(team_id={team_id}) 超时/失败")

    def get_channel_count(self, channel: str) -> int:
        """获取频道连接数"""
        return len(self.channel_connections.get(channel, []))

    def get_station_count(self, station_id: int) -> int:
        """获取站点连接数"""
        return len(self.station_connections.get(station_id, set()))

    def get_device_subscriber_count(self, device_id: int) -> int:
        """获取设备订阅者数量"""
        return len(self.device_subscriptions.get(device_id, set()))

    def get_total_count(self) -> int:
        """获取总连接数"""
        return len(self.all_connections)

    def get_status(self) -> dict:
        """获取连接池状态"""
        return {
            "total": len(self.all_connections),
            "channels": {k: len(v) for k, v in self.channel_connections.items()},
            "stations": {k: len(v) for k, v in self.station_connections.items()},
            "device_subscriptions": {k: len(v) for k, v in self.device_subscriptions.items()},
            "max_channel": MAX_CHANNEL_CONNECTIONS,
            "max_total": MAX_TOTAL_CONNECTIONS,
            "heartbeat_interval": WS_HEARTBEAT_INTERVAL,
        }