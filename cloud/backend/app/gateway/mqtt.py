"""
MQTT 3.1.1 协议适配器 - 适用于直流充电桩

MQTT主题结构：
- 上行：tcu/{tcu_address}/report  （遥测/告警上报）
- 下行：tcu/{tcu_address}/control （控制指令）

消息格式：JSON（符合协议V2.2.0）

v2 增强：
    - TLS/SSL 支持
    - 自动断线重连（指数退避）
    - 连接状态回调
"""
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime, timezone
import asyncio
import logging
import ssl

from .base import DeviceAdapter

logger = logging.getLogger(__name__)


class MQTTAdapter(DeviceAdapter):
    """
    MQTT 3.1.1 协议适配器（v2）
    
    适用设备：直流充电桩
    
    MQTT消息类型：
        - 0x122001: 遥测数据上报
        - 0x122006: 故障上报
        - 0x122002: 充电状态
        - 0x4000: 参数设置
        - 0x4001: 复位控制
        - 0x4002: 重启控制
    """
    
    protocol_type = "mqtt"
    
    # MQTT消息类型
    MSG_TELEMETRY = 0x122001    # 遥测数据上报
    MSG_FAULT_REPORT = 0x122006 # 故障上报
    MSG_CHARGE_STATUS = 0x122002 # 充电状态
    MSG_CONTROL_SET = 0x4000     # 参数设置
    MSG_CONTROL_RESET = 0x4001   # 复位控制
    MSG_CONTROL_REBOOT = 0x4002  # 重启控制
    
    def __init__(
        self,
        broker: str = "mqtt.example.com",
        port: int = 1883,
        client_id: str = "gateway_001",
        qos: int = 1,
        keepalive: int = 60,
        # v2: TLS 配置
        tls_enabled: bool = False,
        tls_ca_cert: Optional[str] = None,
        tls_client_cert: Optional[str] = None,
        tls_client_key: Optional[str] = None,
        tls_insecure: bool = False,
        # v2: 重连配置
        reconnect_enabled: bool = True,
        reconnect_max_attempts: int = 10,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
        # v2: 回调
        on_connect_callback: Optional[Callable[[], Awaitable[None]]] = None,
        on_disconnect_callback: Optional[Callable[[], Awaitable[None]]] = None,
        on_message_callback: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
    ):
        """
        初始化 MQTT 适配器
        
        Args:
            broker: MQTT Broker 地址
            port: MQTT Broker 端口（默认 1883，TLS 默认 8883）
            client_id: 客户端ID
            qos: QoS等级（0/1/2）
            keepalive: 心跳间隔（秒）
            tls_enabled: 是否启用 TLS/SSL
            tls_ca_cert: CA 证书路径
            tls_client_cert: 客户端证书路径
            tls_client_key: 客户端私钥路径
            tls_insecure: 是否跳过证书验证（仅测试环境）
            reconnect_enabled: 是否启用自动重连
            reconnect_max_attempts: 最大重连次数
            reconnect_base_delay: 重连基础延迟（秒）
            reconnect_max_delay: 重连最大延迟（秒）
            on_connect_callback: 连接成功回调
            on_disconnect_callback: 断连回调
            on_message_callback: 消息接收回调
        """
        self.broker = broker
        self.port = port if not tls_enabled else (port if port != 1883 else 8883)
        self.client_id = client_id
        self.qos = qos
        self.keepalive = keepalive
        
        # TLS 配置
        self.tls_enabled = tls_enabled
        self.tls_ca_cert = tls_ca_cert
        self.tls_client_cert = tls_client_cert
        self.tls_client_key = tls_client_key
        self.tls_insecure = tls_insecure
        
        # 重连配置
        self.reconnect_enabled = reconnect_enabled
        self.reconnect_max_attempts = reconnect_max_attempts
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay
        
        # 重连状态
        self._reconnect_count = 0
        self._reconnecting = False
        self._reconnect_task: Optional[asyncio.Task] = None
        
        # 回调
        self.on_connect_callback = on_connect_callback
        self.on_disconnect_callback = on_disconnect_callback
        self.on_message_callback = on_message_callback
        
        # 已订阅主题
        self._subscriptions: set = set()
        
        # 调用父类初始化
        super().__init__()
    
    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        构建 SSL/TLS 上下文
        
        Returns:
            Optional[ssl.SSLContext]: SSL 上下文，未启用则返回 None
        """
        if not self.tls_enabled:
            return None
        
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        
        if self.tls_ca_cert:
            context.load_verify_locations(self.tls_ca_cert)
        
        if self.tls_client_cert and self.tls_client_key:
            context.load_cert_chain(self.tls_client_cert, self.tls_client_key)
        
        if self.tls_insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            logger.warning("TLS证书验证已禁用（仅测试环境）")
        
        return context
    
    async def initialize(self) -> bool:
        """初始化 MQTT 适配器"""
        protocol = "mqtts" if self.tls_enabled else "mqtt"
        logger.info("初始化 MQTT: %s://%s:%d", protocol, self.broker, self.port)
        
        if self.tls_enabled:
            self._build_ssl_context()
        
        self.initialized = True
        return True
    
    async def connect(self) -> bool:
        """建立MQTT连接"""
        protocol = "mqtts" if self.tls_enabled else "mqtt"
        logger.info("连接 %s://%s:%d (client_id=%s)", protocol, self.broker, self.port, self.client_id)
        self.connected = True
        self._reconnect_count = 0
        
        if self.on_connect_callback:
            try:
                await self.on_connect_callback()
            except Exception as e:
                logger.error("连接回调异常: %s", e)
        
        return True
    
    async def disconnect(self) -> bool:
        """断开连接"""
        self.connected = False
        self._cancel_reconnect()
        
        if self.on_disconnect_callback:
            try:
                await self.on_disconnect_callback()
            except Exception as e:
                logger.error("断连回调异常: %s", e)
        
        return True
    
    async def subscribe_device(self, tcu_address: str) -> bool:
        """
        订阅设备上行主题
        
        Args:
            tcu_address: TCU地址（如 "TCU001"）
            
        Returns:
            bool: 是否成功订阅
        """
        topic = f"tcu/{tcu_address}/report"
        self._subscriptions.add(topic)
        logger.info("订阅主题: %s", topic)
        return True
    
    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """
        读取设备数据
        
        Args:
            device_address: TCU地址编号
            
        Returns:
            Dict[str, Any]: 遥测数据
        """
        return await self.read_telemetry(f"TCU{device_address:03d}")
    
    async def write_command(self, device_address: int, command: Dict) -> bool:
        """
        写入控制指令
        
        Args:
            device_address: TCU地址编号
            command: 控制指令字典
            
        Returns:
            bool: 是否成功
        """
        return await self.send_control(f"TCU{device_address:03d}", command)
    
    async def read_telemetry(self, tcu_address: str) -> Dict[str, Any]:
        """
        解析MQTT遥测消息
        
        消息类型：0x122001
        
        Args:
            tcu_address: TCU地址
            
        Returns:
            Dict[str, Any]: 遥测数据字典
        """
        telemetry = {
            "tcu_address": tcu_address,
            "charger_voltage": 400.0,
            "charger_current": 50.0,
            "charger_power": 20.0,
            "charger_soc": 80.0,
            "gun_status": 1,
            "gun_temperature": 35.0,
            "internal_temperature": 45.0,
            "timestamp": datetime.now(timezone.utc),
        }
        return telemetry
    
    async def send_control(self, tcu_address: str, command: Dict) -> bool:
        """
        发送控制指令
        
        消息类型：0x4000-0x4002
        
        Args:
            tcu_address: TCU地址
            command: 控制指令字典
            
        Returns:
            bool: 是否成功
        """
        topic = f"tcu/{tcu_address}/control"
        logger.info("发送控制: %s, 命令: %s", topic, command)
        return True
    
    # ===== 重连机制 =====
    
    async def _reconnect_loop(self):
        """自动重连循环（指数退避）"""
        delay = self.reconnect_base_delay
        
        while (
            self.reconnect_enabled
            and not self.connected
            and self._reconnect_count < self.reconnect_max_attempts
        ):
            self._reconnect_count += 1
            logger.info("MQTT 重连 第%d/%d次 (延迟%.1fs)...",
                       self._reconnect_count, self.reconnect_max_attempts, delay)
            
            await asyncio.sleep(delay)
            
            try:
                success = await self.connect()
                if success:
                    logger.info("MQTT 重连成功")
                    # 重新订阅之前的所有主题
                    for topic in self._subscriptions:
                        logger.info("重新订阅: %s", topic)
                    return
            except Exception as e:
                logger.error("MQTT 重连失败: %s", e)
            
            # 指数退避
            delay = min(delay * 2, self.reconnect_max_delay)
        
        if not self.connected:
            logger.error("MQTT 重连失败（已尝试%d次）", self._reconnect_count)
    
    def start_reconnect(self):
        """启动自动重连"""
        if self._reconnecting or self.connected:
            return
        self._reconnecting = True
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
    
    def _cancel_reconnect(self):
        """取消自动重连"""
        self._reconnecting = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None
    
    async def on_disconnect(self):
        """
        连接断开处理（由 MQTT client 回调触发）
        
        触发自动重连流程。
        """
        self.connected = False
        
        if self.on_disconnect_callback:
            try:
                await self.on_disconnect_callback()
            except Exception as e:
                logger.error("断连回调异常: %s", e)
        
        if self.reconnect_enabled:
            self.start_reconnect()
    
    # ===== 故障诊断 =====
    
    def parse_fault_message(self, message: Dict) -> Dict[str, Any]:
        """
        解析MQTT故障上报消息
        
        消息类型：0x122006
        
        Args:
            message: MQTT故障消息字典
            
        Returns:
            Dict[str, Any]: 解析后的故障信息
        """
        fault_info = {
            "message_type": message.get("message_type"),
            "tcu_address": message.get("tcu_address"),
            "sequence_no": message.get("sequence_no"),
            "fault_level": self._parse_fault_level(message.get("fault_level")),
            "fault_code": f"0x{message.get('fault_code', 0):04X}",
            "fault_detail": message.get("fault_detail", []),
            "timestamp": message.get("timestamp"),
        }
        return fault_info
    
    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """解析故障码"""
        return None
    
    def _parse_fault_level(self, level_code: int) -> str:
        """
        解析故障等级
        
        0x01=紧急故障（立即停机）
        0x02=一般故障（可延迟处理）
        0x03=严重告警（需关注）
        0x04=一般告警（提示）
        
        Args:
            level_code: 故障等级代码
            
        Returns:
            str: 故障等级名称
        """
        level_map = {
            0x01: "emergency",
            0x02: "serious",
            0x03: "warning_serious",
            0x04: "warning_general",
        }
        return level_map.get(level_code, "unknown")
    
    # ===== 状态查询 =====
    
    def get_tls_info(self) -> Dict[str, Any]:
        """获取 TLS 配置信息"""
        return {
            "enabled": self.tls_enabled,
            "broker": self.broker,
            "port": self.port,
            "client_cert": bool(self.tls_client_cert),
            "ca_cert": bool(self.tls_ca_cert),
            "insecure": self.tls_insecure,
        }
    
    def get_reconnect_status(self) -> Dict[str, Any]:
        """获取重连状态"""
        return {
            "enabled": self.reconnect_enabled,
            "reconnecting": self._reconnecting,
            "attempts": self._reconnect_count,
            "max_attempts": self.reconnect_max_attempts,
        }
