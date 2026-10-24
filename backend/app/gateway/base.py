"""
设备适配器基类 - 定义所有设备适配器的标准接口

提供统一的设备通信抽象层，支持 Modbus-RTU、MQTT、OCPP、REST 等多种协议。

v2 变更：
    - 重命名为 DeviceAdapter（ProtocolAdapter 保留为向后兼容别名）
    - 新增 TelemetryPoint dataclass 用于遥测点定义
    - 新增 initialize/shutdown/reset 生命周期方法
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


# ========== 遥测点类型 ==========

class PointType(Enum):
    """遥测点数据类型"""
    VOLTAGE = "voltage"
    CURRENT = "current"
    POWER = "power"
    ENERGY = "energy"
    FREQUENCY = "frequency"
    TEMPERATURE = "temperature"
    PERCENTAGE = "percentage"
    STATUS = "status"
    COUNTER = "counter"
    DURATION = "duration"


@dataclass
class TelemetryPoint:
    """
    遥测点定义
    
    描述设备的一个遥测数据点，包含地址映射、数据类型和解析参数。
    
    Attributes:
        name: 遥测点名称（如 'grid_voltage_a'、'battery_soc'）
        address: 寄存器/数据地址
        point_type: 数据类型
        scale: 缩放因子（原始值 * scale = 实际值）
        unit: 单位（如 'V'、'A'、'kW'、'%'）
        description: 中文描述
        register_count: 占用的寄存器数量（Modbus等）
        is_signed: 是否为有符号数
    
    Example:
        >>> point = TelemetryPoint(
        ...     name="grid_voltage_a",
        ...     address=0,
        ...     point_type=PointType.VOLTAGE,
        ...     scale=0.1,
        ...     unit="V",
        ...     description="A相电压"
        ... )
        >>> raw_value = 2205
        >>> raw_value * point.scale  # 220.5
    """
    name: str
    address: int
    point_type: PointType = PointType.VOLTAGE
    scale: float = 1.0
    unit: str = ""
    description: str = ""
    register_count: int = 1
    is_signed: bool = False
    
    def parse(self, raw_value: int) -> float:
        """将原始值转换为实际物理值"""
        if self.is_signed and raw_value >= (1 << (16 * self.register_count - 1)):
            raw_value -= (1 << (16 * self.register_count))
        return raw_value * self.scale


# ========== 设备适配器基类 ==========

class DeviceAdapter(ABC):
    """
    设备适配器抽象基类（v2）
    
    所有设备适配器必须实现此接口，提供统一的通信和生命周期管理方法。
    
    生命周期：
        1. __init__()      → 创建实例
        2. initialize()    → 初始化资源（如打开串口、加载配置）
        3. connect()       → 建立连接
        4. read_data() / write_command() → 运行时操作
        5. disconnect()    → 断开连接
        6. shutdown()      → 释放所有资源
        7. reset()         → 重置适配器状态
    
    Attributes:
        protocol_type: 协议类型标识（如 'modbus_rtu', 'mqtt', 'ocpp'）
        connected: 连接状态标志
        initialized: 初始化状态标志
        telemetry_points: 遥测点映射表
    """
    
    protocol_type: str = "unknown"
    
    def __init__(self):
        self.connected: bool = False
        self.initialized: bool = False
        self.telemetry_points: Dict[str, TelemetryPoint] = {}
    
    # ===== 生命周期方法 =====
    
    async def initialize(self) -> bool:
        """
        初始化适配器资源
        
        在 connect() 之前调用，用于加载配置、注册遥测点等。
        子类可重载此方法实现自定义初始化逻辑。
        
        Returns:
            bool: 初始化是否成功
        """
        self.initialized = True
        logger.debug("%s: 初始化完成", self.protocol_type)
        return True
    
    async def shutdown(self) -> bool:
        """
        关闭适配器并释放所有资源
        
        优雅关闭流程：先断开连接，再清理资源。
        
        Returns:
            bool: 关闭是否成功
        """
        if self.connected:
            await self.disconnect()
        self.initialized = False
        self.telemetry_points.clear()
        logger.debug("%s: 已关闭", self.protocol_type)
        return True
    
    async def reset(self) -> bool:
        """
        重置适配器状态
        
        断开连接后重新初始化，用于故障恢复。
        
        Returns:
            bool: 重置是否成功
        """
        logger.info("%s: 正在重置...", self.protocol_type)
        await self.shutdown()
        await self.initialize()
        return await self.connect()
    
    # ===== 连接管理 =====
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        建立连接
        
        Returns:
            bool: 连接是否成功
            
        Example:
            >>> adapter = ModbusRTUAdapter(port="/dev/ttyUSB0")
            >>> await adapter.connect()  # 返回 True/False
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        断开连接
        
        Returns:
            bool: 断开是否成功
        """
        pass
    
    # ===== 数据读写 =====
    
    @abstractmethod
    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """
        读取设备数据
        
        Args:
            device_address: 设备地址（Modbus从站地址/MQTT TCU地址）
            
        Returns:
            Dict[str, Any]: 遥测数据字典，包含：
                - timestamp: 采集时间戳
                - device_address: 设备地址
                - 其他协议特定字段
                
        Example:
            >>> data = await adapter.read_data(1)
            >>> print(data['grid_voltage_a'])  # 220.5
        """
        pass
    
    @abstractmethod
    async def write_command(self, device_address: int, command: Dict) -> bool:
        """
        写入控制指令
        
        Args:
            device_address: 设备地址
            command: 控制指令字典
            
        Returns:
            bool: 指令是否成功下发
            
        Example:
            >>> await adapter.write_command(1, {"register": 1024, "value": 0x01})
        """
        pass
    
    # ===== 故障诊断 =====
    
    @abstractmethod
    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """
        解析故障码
        
        Args:
            raw_data: 原始故障数据
            
        Returns:
            Optional[str]: 故障码字符串（如 "0x7E"），无故障返回 None
        """
        pass
    
    # ===== 遥测点管理 =====
    
    def register_telemetry_points(self, points: List[TelemetryPoint]) -> None:
        """
        注册遥测点映射
        
        Args:
            points: 遥测点定义列表
        
        Example:
            >>> adapter.register_telemetry_points([
            ...     TelemetryPoint("grid_voltage_a", 0, PointType.VOLTAGE, 0.1, "V"),
            ...     TelemetryPoint("grid_power", 10, PointType.POWER, 0.1, "kW"),
            ... ])
        """
        for point in points:
            self.telemetry_points[point.name] = point
        logger.debug("%s: 注册 %d 个遥测点", self.protocol_type, len(points))
    
    def get_telemetry_point(self, name: str) -> Optional[TelemetryPoint]:
        """
        获取遥测点定义
        
        Args:
            name: 遥测点名称
            
        Returns:
            Optional[TelemetryPoint]: 遥测点定义，未找到返回 None
        """
        return self.telemetry_points.get(name)
    
    def parse_telemetry_value(self, point_name: str, raw_value: int) -> Optional[float]:
        """
        根据遥测点定义解析原始值
        
        Args:
            point_name: 遥测点名称
            raw_value: 原始整数值
            
        Returns:
            Optional[float]: 解析后的物理值
        """
        point = self.telemetry_points.get(point_name)
        if point is None:
            logger.warning("%s: 未找到遥测点 %s", self.protocol_type, point_name)
            return None
        return point.parse(raw_value)
    
    # ===== 状态查询 =====
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected
    
    def is_initialized(self) -> bool:
        """检查初始化状态"""
        return self.initialized
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康状态信息
        """
        return {
            "protocol": self.protocol_type,
            "connected": getattr(self, 'connected', False),
            "initialized": getattr(self, 'initialized', False),
            "telemetry_points_count": len(getattr(self, 'telemetry_points', {})),
            "status": "healthy" if getattr(self, 'connected', False) else "disconnected"
        }


# ========== 向后兼容别名 ==========

# ProtocolAdapter 保留为 DeviceAdapter 的别名，确保现有代码不受影响
ProtocolAdapter = DeviceAdapter

__all__ = [
    "DeviceAdapter",
    "ProtocolAdapter",  # 向后兼容
    "TelemetryPoint",
    "PointType",
]
