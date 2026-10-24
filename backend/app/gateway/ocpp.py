"""
OCPP 1.6J 协议适配器 - 适用于电动汽车充电桩

OCPP（Open Charge Point Protocol）1.6 JSON 版本。
基于 WebSocket 通信，消息格式为 JSON。

v2 新增：
    - OCPP 1.6J 核心消息支持
    - BootNotification / Heartbeat / Authorize
    - StartTransaction / StopTransaction
    - MeterValues / StatusNotification
    - RemoteStartTransaction / RemoteStopTransaction
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import asyncio
import logging

from .base import DeviceAdapter

logger = logging.getLogger(__name__)


# ========== 入网状态钩子（任务卡 1256e7fa）==========
def mark_device_online(charge_point_id: str) -> bool:
    """设备首次 BootNotification ACCEPTED 后，将其 provision_status 置 ONLINE。

    匹配键优先 Device.charge_box_id，回退 Device.sn（二者创建时默认相等）。
    用独立短 session，与请求级 session 解耦；任何异常仅记日志、不抛
    （网关入网登记失败不得影响设备正常通信）。返回是否更新到一行。

    模块级、同步：供 connect() 经 ``asyncio.to_thread`` 卸载到线程池调用，
    避免同步 DB IO 阻塞事件循环。
    """
    if not charge_point_id:
        return False
    try:
        from app.models.device import Device, ProvisionStatus
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            device = (
                session.query(Device)
                .filter((Device.charge_box_id == charge_point_id) | (Device.sn == charge_point_id))
                .first()
            )
            if device is None:
                logger.info("OCPP 入网登记跳过：未匹配到设备 charge_point_id=%s", charge_point_id)
                return False
            if device.provision_status == ProvisionStatus.ONLINE:
                return True  # 幂等：已在网，免写
            device.provision_status = ProvisionStatus.ONLINE
            session.commit()
            logger.info("OCPP 入网登记成功：device=%s → online", charge_point_id)
            return True
        finally:
            session.close()
    except Exception as e:  # 网关侧兜底：登记失败不得阻断通信
        logger.warning("OCPP 入网登记失败（不影响通信）charge_point_id=%s: %s", charge_point_id, e)
        return False


# ========== OCPP 消息类型 ==========

class OCPPMessageType:
    """OCPP 1.6J 消息类型常量"""
    CALL = 2          # 请求（Client → Server）
    CALL_RESULT = 3   # 响应（Server → Client）
    CALL_ERROR = 4    # 错误（Server → Client）


class OCPPAction:
    """OCPP 1.6J 动作常量"""
    BOOT_NOTIFICATION = "BootNotification"
    HEARTBEAT = "Heartbeat"
    AUTHORIZE = "Authorize"
    START_TRANSACTION = "StartTransaction"
    STOP_TRANSACTION = "StopTransaction"
    METER_VALUES = "MeterValues"
    STATUS_NOTIFICATION = "StatusNotification"
    DATA_TRANSFER = "DataTransfer"
    REMOTE_START_TRANSACTION = "RemoteStartTransaction"
    REMOTE_STOP_TRANSACTION = "RemoteStopTransaction"
    CHANGE_AVAILABILITY = "ChangeAvailability"
    GET_CONFIGURATION = "GetConfiguration"
    CHANGE_CONFIGURATION = "ChangeConfiguration"
    CLEAR_CACHE = "ClearCache"
    RESET = "Reset"
    UNLOCK_CONNECTOR = "UnlockConnector"


class ChargePointStatus:
    """充电桩状态常量"""
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EVSE = "SuspendedEVSE"
    SUSPENDED_EV = "SuspendedEV"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class RegistrationStatus:
    """注册状态常量"""
    ACCEPTED = "Accepted"
    PENDING = "Pending"
    REJECTED = "Rejected"


# ========== OCPP 适配器 ==========

class OCPPAdapter(DeviceAdapter):
    """
    OCPP 1.6J 协议适配器
    
    适用设备：电动汽车充电桩（符合 OCPP 1.6 JSON 标准）
    
    通信方式：WebSocket (wss://)
    消息格式：JSON-RPC 2.0
    
    典型流程：
        1. ChargePoint → CSMS: BootNotification
        2. CSMS → ChargePoint: BootNotification.conf (Accepted)
        3. ChargePoint → CSMS: Heartbeat (每60秒)
        4. ChargePoint → CSMS: Authorize (插枪后)
        5. ChargePoint → CSMS: StartTransaction (开始充电)
        6. ChargePoint → CSMS: MeterValues (充电中定时上报)
        7. ChargePoint → CSMS: StopTransaction (结束充电)
    """
    
    protocol_type = "ocpp"
    
    def __init__(
        self,
        endpoint: str = "wss://ocpp.example.com/ocpp",
        charge_point_id: str = "CP001",
        auth_token: Optional[str] = None,
        heartbeat_interval: int = 60,
        reconnect_enabled: bool = True,
        max_reconnect_attempts: int = 10,
        base_reconnect_delay: float = 1.0,
    ):
        """
        初始化 OCPP 适配器
        
        Args:
            endpoint: OCPP 中心系统 WebSocket 端点
            charge_point_id: 充电桩 ID
            auth_token: 认证令牌（可选）
            heartbeat_interval: 心跳间隔（秒）
            reconnect_enabled: 是否启用自动重连
            max_reconnect_attempts: 最大重连次数
            base_reconnect_delay: 重连基础延迟（秒）
        """
        self.endpoint = endpoint
        self.charge_point_id = charge_point_id
        self.auth_token = auth_token
        self.heartbeat_interval = heartbeat_interval
        
        # 重连配置
        self.reconnect_enabled = reconnect_enabled
        self.max_reconnect_attempts = max_reconnect_attempts
        self.base_reconnect_delay = base_reconnect_delay
        
        # 调用父类初始化
        super().__init__()
        self._registered = False
        self._transaction_id: Optional[int] = None
        self._meter_start: Optional[int] = None
        self._pending_calls: Dict[str, asyncio.Future] = {}
        self._reconnect_count = 0
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._last_boot_notification: Optional[Dict] = None
        
    # ===== 生命周期 =====
    
    async def initialize(self) -> bool:
        """初始化 OCPP 适配器"""
        logger.info("初始化 OCPP: charge_point=%s, endpoint=%s",
                    self.charge_point_id, self.endpoint)
        self.initialized = True
        return True
    
    async def connect(self) -> bool:
        """
        建立 WebSocket 连接并发送 BootNotification
        
        Returns:
            bool: 连接是否成功
        """
        logger.info("连接 OCPP: %s -> %s", self.charge_point_id, self.endpoint)
        # 模拟 WebSocket 连接
        self.connected = True
        
        # 发送 BootNotification
        boot_result = await self.send_boot_notification()
        if boot_result.get("status") == RegistrationStatus.ACCEPTED:
            self._registered = True
            # 启动心跳
            self._start_heartbeat()
            # 入网登记（任务卡 1256e7fa）：BootNotification 通过 → 置 ONLINE。
            # 同步 DB 写经线程池卸载，不阻塞事件循环；失败仅记日志，不影响通信。
            try:
                await asyncio.to_thread(mark_device_online, self.charge_point_id)
            except Exception as e:
                logger.warning("OCPP 入网登记调度失败 charge_point_id=%s: %s", self.charge_point_id, e)

        return True
    
    async def disconnect(self) -> bool:
        """断开 WebSocket 连接"""
        self.connected = False
        self._registered = False
        self._stop_heartbeat()
        
        # 取消所有待处理调用
        for future in self._pending_calls.values():
            if not future.done():
                future.cancel()
        self._pending_calls.clear()
        
        return True
    
    async def shutdown(self) -> bool:
        """关闭 OCPP 适配器"""
        if self.connected:
            await self.disconnect()
        self.initialized = False
        return True
    
    # ===== OCPP 核心消息 =====
    
    async def send_boot_notification(
        self,
        charge_point_model: str = "DC-60kW",
        charge_point_vendor: str = "Tianlian",
        firmware_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        """
        发送 BootNotification 请求
        
        OCPP 1.6J §8.2: 充电桩启动时向 CSMS 注册
        
        Args:
            charge_point_model: 充电桩型号
            charge_point_vendor: 充电桩制造商
            firmware_version: 固件版本
            
        Returns:
            Dict[str, Any]: 注册响应，包含：
                - status: RegistrationStatus (Accepted/Pending/Rejected)
                - current_time: 服务器当前时间
                - interval: 心跳间隔（秒）
        """
        payload = {
            "chargePointModel": charge_point_model,
            "chargePointVendor": charge_point_vendor,
            "chargePointSerialNumber": self.charge_point_id,
            "firmwareVersion": firmware_version,
        }
        
        logger.info("OCPP BootNotification: model=%s, vendor=%s",
                    charge_point_model, charge_point_vendor)
        
        self._last_boot_notification = payload
        
        # 模拟 CSMS 响应
        response = {
            "status": RegistrationStatus.ACCEPTED,
            "currentTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "interval": self.heartbeat_interval,
        }
        return response
    
    async def send_heartbeat(self) -> Dict[str, Any]:
        """
        发送 Heartbeat 请求
        
        OCPP 1.6J §8.3: 保持连接活跃
        
        Returns:
            Dict[str, Any]: 心跳响应，包含 server 当前时间
        """
        logger.debug("OCPP Heartbeat: charge_point=%s", self.charge_point_id)
        return {
            "currentTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    
    async def send_authorize(self, id_tag: str) -> Dict[str, Any]:
        """
        发送 Authorize 请求
        
        OCPP 1.6J §8.4: 验证用户/RFID 卡授权
        
        Args:
            id_tag: 用户/RFID 卡标识
            
        Returns:
            Dict[str, Any]: 授权响应
        """
        logger.info("OCPP Authorize: idTag=%s", id_tag)
        
        # 模拟授权成功
        return {
            "idTagInfo": {
                "status": "Accepted",
                "expiryDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "parentIdTag": None,
            }
        }
    
    async def start_transaction(
        self,
        connector_id: int,
        id_tag: str,
        meter_start: int = 0,
        reservation_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        发送 StartTransaction 请求
        
        OCPP 1.6J §8.7: 开始充电交易
        
        Args:
            connector_id: 连接器 ID
            id_tag: 用户 ID
            meter_start: 开始时刻表读数
            reservation_id: 预约 ID（可选）
            
        Returns:
            Dict[str, Any]: 交易启动响应
        """
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": meter_start,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if reservation_id is not None:
            payload["reservationId"] = reservation_id
        
        logger.info("OCPP StartTransaction: connector=%d, idTag=%s",
                    connector_id, id_tag)
        
        # 模拟 CSMS 响应
        self._transaction_id = 10001
        self._meter_start = meter_start
        return {
            "idTagInfo": {"status": "Accepted"},
            "transactionId": self._transaction_id,
        }
    
    async def stop_transaction(
        self,
        transaction_id: int,
        meter_stop: int,
        id_tag: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送 StopTransaction 请求
        
        OCPP 1.6J §8.8: 结束充电交易
        
        Args:
            transaction_id: 交易 ID
            meter_stop: 结束时刻表读数
            id_tag: 用户 ID（可选）
            reason: 结束原因（Local/Remote/Other/...）
            
        Returns:
            Dict[str, Any]: 交易结束响应
        """
        # 缺陷1: 时间戳必须 UTC aware（用于计费对账，naive 时间戳会跨时区错乱）
        timestamp = datetime.now(timezone.utc).isoformat()

        # 缺陷2: meter_stop 合理性校验（负值不合理）
        if meter_stop < 0:
            logger.warning(
                "OCPP StopTransaction 拒绝: meter_stop 负值 %d (transaction=%d)",
                meter_stop, transaction_id,
            )
            return {
                "idTagInfo": {"status": "Rejected"},
                "reason": "meter_stop 为负值",
                "timestamp": timestamp,
            }

        # 缺陷2: 必须存在活跃交易
        if self._transaction_id is None:
            logger.warning(
                "OCPP StopTransaction 拒绝: 无活跃交易 (transaction=%d)",
                transaction_id,
            )
            return {
                "idTagInfo": {"status": "Rejected"},
                "reason": "无活跃交易",
                "timestamp": timestamp,
            }

        # 缺陷2: transaction_id 必须与当前活跃交易匹配（原实现任意 ID 静默 Accepted）
        if transaction_id != self._transaction_id:
            logger.warning(
                "OCPP StopTransaction 拒绝: transaction_id 不匹配 (收到=%d, 活跃=%d)",
                transaction_id, self._transaction_id,
            )
            return {
                "idTagInfo": {"status": "Rejected"},
                "reason": "transaction_id 与活跃交易不匹配",
                "timestamp": timestamp,
            }

        # 缺陷2: meter_stop 不得小于 meter_start（表读数倒退）
        if self._meter_start is not None and meter_stop < self._meter_start:
            logger.warning(
                "OCPP StopTransaction 拒绝: meter_stop(%d) < meter_start(%d)",
                meter_stop, self._meter_start,
            )
            return {
                "idTagInfo": {"status": "Rejected"},
                "reason": "meter_stop 小于 meter_start",
                "timestamp": timestamp,
            }

        payload = {
            "transactionId": transaction_id,
            "meterStop": meter_stop,
            "timestamp": timestamp,
        }
        if id_tag is not None:
            payload["idTag"] = id_tag
        if reason is not None:
            payload["reason"] = reason

        logger.info("OCPP StopTransaction: transaction=%d, meter_stop=%d",
                    transaction_id, meter_stop)

        # 正常结束才清空活跃交易（Rejected 时保留，交易仍有效）
        self._transaction_id = None
        self._meter_start = None
        return {
            "idTagInfo": {"status": "Accepted"},
            "transactionId": transaction_id,
            "timestamp": timestamp,
        }
    
    async def send_meter_values(
        self,
        connector_id: int,
        transaction_id: int,
        values: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        发送 MeterValues 请求
        
        OCPP 1.6J §8.9: 上报计量数据
        
        Args:
            connector_id: 连接器 ID
            transaction_id: 交易 ID
            values: 计量数据列表（每个包含 timestamp 和 sampledValue）
            
        Returns:
            Dict[str, Any]: 计量数据上报响应
        """
        # 缺陷3: values 为 None/空列表时原实现 len(values) → TypeError，需防护
        if not values:
            logger.warning(
                "OCPP MeterValues: values 为空，跳过上报 (connector=%d, transaction=%d)",
                connector_id, transaction_id,
            )
            return {"status": "Rejected"}

        logger.debug("OCPP MeterValues: connector=%d, transaction=%d, values=%d",
                     connector_id, transaction_id, len(values))
        return {}
    
    async def send_status_notification(
        self,
        connector_id: int,
        status: str,
        error_code: str = "NoError",
    ) -> Dict[str, Any]:
        """
        发送 StatusNotification 请求
        
        OCPP 1.6J §8.5: 上报连接器状态变更
        
        Args:
            connector_id: 连接器 ID
            status: 充电桩状态
            error_code: 错误码
            
        Returns:
            Dict[str, Any]: 状态通知响应
        """
        
        logger.info("OCPP StatusNotification: connector=%d, status=%s",
                    connector_id, status)
        return {}
    
    async def send_data_transfer(
        self,
        vendor_id: str,
        message_id: Optional[str] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        发送 DataTransfer 请求
        
        OCPP 1.6J §8.14: 自定义数据传输
        
        Args:
            vendor_id: 厂商 ID
            message_id: 消息 ID（可选）
            data: 自定义数据
            
        Returns:
            Dict[str, Any]: 数据传输响应
        """
        payload = {"vendorId": vendor_id}
        if message_id:
            payload["messageId"] = message_id
        if data is not None:
            payload["data"] = data
        
        logger.debug("OCPP DataTransfer: vendor=%s", vendor_id)
        return {"status": "Accepted"}
    
    # ===== 远程控制（CSMS → ChargePoint） =====
    
    async def remote_start_transaction(self, id_tag: str, connector_id: int = 1) -> bool:
        """
        处理 RemoteStartTransaction 请求
        
        OCPP 1.6J §8.10: CSMS 远程启动充电
        
        Args:
            id_tag: 用户 ID
            connector_id: 连接器 ID
            
        Returns:
            bool: 是否接受
        """
        logger.info("OCPP RemoteStartTransaction: idTag=%s, connector=%d",
                    id_tag, connector_id)
        return True
    
    async def remote_stop_transaction(self, transaction_id: int) -> bool:
        """
        处理 RemoteStopTransaction 请求
        
        OCPP 1.6J §8.11: CSMS 远程停止充电
        
        Args:
            transaction_id: 交易 ID
            
        Returns:
            bool: 是否接受
        """
        logger.info("OCPP RemoteStopTransaction: transaction=%d", transaction_id)
        self._transaction_id = None
        return True
    
    async def reset(self, reset_type: str = "Soft") -> bool:
        """
        处理 Reset 请求
        
        OCPP 1.6J §8.12: CSMS 远程重启
        
        Args:
            reset_type: 重启类型（Soft/Hard）
            
        Returns:
            bool: 是否接受
        """
        logger.info("OCPP Reset: type=%s", reset_type)
        return True
    
    async def change_availability(self, connector_id: int, availability: str) -> bool:
        """
        处理 ChangeAvailability 请求
        
        OCPP 1.6J §8.13: 变更连接器可用性
        
        Args:
            connector_id: 连接器 ID
            availability: 可用性（Operative/Inoperative）
            
        Returns:
            bool: 是否接受
        """
        logger.info("OCPP ChangeAvailability: connector=%d, availability=%s",
                    connector_id, availability)
        return True
    
    # ===== 基础接口实现 =====
    
    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """
        读取充电桩数据
        
        Args:
            device_address: 连接器 ID
            
        Returns:
            Dict[str, Any]: 充电桩遥测数据
        """
        return {
            "connector_id": device_address,
            "status": ChargePointStatus.CHARGING if self._transaction_id else ChargePointStatus.AVAILABLE,
            "transaction_id": self._transaction_id,
            "power": 60.0,
            "voltage": 400.0,
            "current": 150.0,
            "soc": 80.0,
            "meter_reading": 10000,
            "registered": self._registered,
            "timestamp": datetime.now(timezone.utc),
        }
    
    async def write_command(self, device_address: int, command: Dict) -> bool:
        """
        写入控制指令
        
        Args:
            device_address: 连接器 ID
            command: 控制指令字典（如 {"action": "remote_start", "id_tag": "USER001"}）
            
        Returns:
            bool: 是否成功
        """
        action = command.get("action", "")
        
        if action == "remote_start":
            return await self.remote_start_transaction(
                command.get("id_tag", ""), device_address
            )
        elif action == "remote_stop":
            return await self.remote_stop_transaction(
                command.get("transaction_id", 0)
            )
        elif action == "reset":
            return await self.reset(command.get("reset_type", "Soft"))
        elif action == "change_availability":
            return await self.change_availability(
                device_address, command.get("availability", "Operative")
            )
        
        logger.warning("OCPP: 未知控制指令 action=%s", action)
        return False
    
    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """OCPP 故障码由 StatusNotification 上报，无需额外解析"""
        return None
    
    # ===== 心跳管理 =====
    
    def _start_heartbeat(self):
        """启动心跳定时任务"""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    def _stop_heartbeat(self):
        """停止心跳定时任务"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
    
    async def _heartbeat_loop(self):
        """心跳定时循环"""
        while self.connected and self._registered:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                await self.send_heartbeat()
            except Exception as e:
                logger.error("OCPP 心跳异常: %s", e)
    
    # ===== 状态查询 =====
    
    def is_registered(self) -> bool:
        """检查是否已注册到 CSMS"""
        return self._registered
    
    def get_transaction_id(self) -> Optional[int]:
        """获取当前交易 ID"""
        return self._transaction_id
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        base_health = await super().health_check()
        base_health.update({
            "registered": self._registered,
            "transaction_active": self._transaction_id is not None,
            "heartbeat_interval": self.heartbeat_interval,
        })
        return base_health
    
    def get_ocpp_info(self) -> Dict[str, Any]:
        """获取 OCPP 连接信息"""
        return {
            "charge_point_id": self.charge_point_id,
            "endpoint": self.endpoint,
            "registered": self._registered,
            "transaction_active": self._transaction_id is not None,
            "heartbeat_interval": self.heartbeat_interval,
            "version": "1.6-J",
            "protocol": "ocpp",
        }
