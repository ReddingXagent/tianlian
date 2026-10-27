"""
Modbus-RTU 协议适配器 - 适用于储能逆变器、PCS、电表

协议参数（默认）：
- 波特率：9600bps
- 数据位：8位
- 校验：无
- 停止位：1位
- 超时：3000ms
- 重试：2次

v2 增强：
    - 寄存器映射配置（RegisterMap）
    - 批量读取优化（按连续地址段分批）
    - 支持 TelemetryPoint 注册
"""
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from .base import DeviceAdapter, TelemetryPoint, PointType

logger = logging.getLogger(__name__)


# ========== 寄存器映射 ==========

@dataclass
class RegisterMap:
    """
    寄存器地址到遥测点的映射配置
    
    Attributes:
        points: 遥测点定义列表（保持顺序）
        description: 映射组描述
    
    Example:
        >>> from app.gateway.base import TelemetryPoint, PointType
        >>> grid_map = RegisterMap(
        ...     points=[
        ...         TelemetryPoint("grid_voltage_a", 0, PointType.VOLTAGE, 0.1, "V", "A相电压"),
        ...         TelemetryPoint("grid_current_a", 1, PointType.CURRENT, 0.01, "A", "A相电流"),
        ...     ],
        ...     description="电网侧遥测"
        ... )
    """
    points: List[TelemetryPoint]
    description: str = ""
    
    def get_address_range(self) -> Tuple[int, int]:
        """获取地址范围 (start, count)"""
        if not self.points:
            return (0, 0)
        addresses = [p.address for p in self.points]
        start = min(addresses)
        end = max(p.address + p.register_count for p in self.points)
        return (start, end - start)
    
    def get_contiguous_groups(self) -> List[List[TelemetryPoint]]:
        """
        将遥测点按连续地址分组，用于批量读取优化
        
        Returns:
            List[List[TelemetryPoint]]: 连续地址的遥测点分组
        """
        if not self.points:
            return []
        
        sorted_points = sorted(self.points, key=lambda p: p.address)
        groups = []
        current_group = [sorted_points[0]]
        current_end = sorted_points[0].address + sorted_points[0].register_count
        
        for point in sorted_points[1:]:
            if point.address <= current_end + 16:  # 允许16个寄存器间隔
                current_group.append(point)
                current_end = max(current_end, point.address + point.register_count)
            else:
                groups.append(current_group)
                current_group = [point]
                current_end = point.address + point.register_count
        
        groups.append(current_group)
        return groups


# ========== ModbusRTUAdapter ==========

class ModbusRTUAdapter(DeviceAdapter):
    """
    Modbus-RTU 协议适配器（v2）
    
    适用设备：储能逆变器（EAHI5-20K）、PCS、电表
    
    功能码定义：
        - 0x02: 读离散量输入（故障状态）
        - 0x03: 读保持寄存器（控制参数）
        - 0x04: 读输入寄存器（遥测数据）
        - 0x06: 写单个寄存器
        - 0x10: 写多个寄存器
    """
    
    protocol_type = "modbus_rtu"
    
    # 功能码定义
    FC_READ_DISCRETE = 0x02  # 读离散量输入（故障状态）
    FC_READ_HOLDING = 0x03   # 读保持寄存器（控制参数）
    FC_READ_INPUT = 0x04     # 读输入寄存器（遥测数据）
    FC_WRITE_SINGLE = 0x06   # 写单个寄存器
    FC_WRITE_MULTIPLE = 0x10 # 写多个寄存器
    
    # 缺省寄存器映射（按功能分组）
    DEFAULT_GRID_MAP = RegisterMap(
        points=[
            TelemetryPoint("grid_voltage_a", 0, PointType.VOLTAGE, 0.1, "V", "A相电压"),
            TelemetryPoint("grid_current_a", 1, PointType.CURRENT, 0.01, "A", "A相电流"),
            TelemetryPoint("grid_power_a", 2, PointType.POWER, 0.1, "kW", "A相功率"),
            TelemetryPoint("grid_voltage_b", 3, PointType.VOLTAGE, 0.1, "V", "B相电压"),
            TelemetryPoint("grid_current_b", 4, PointType.CURRENT, 0.01, "A", "B相电流"),
            TelemetryPoint("grid_power_b", 5, PointType.POWER, 0.1, "kW", "B相功率"),
            TelemetryPoint("grid_voltage_c", 6, PointType.VOLTAGE, 0.1, "V", "C相电压"),
            TelemetryPoint("grid_current_c", 7, PointType.CURRENT, 0.01, "A", "C相电流"),
            TelemetryPoint("grid_power_c", 8, PointType.POWER, 0.1, "kW", "C相功率"),
            TelemetryPoint("grid_frequency", 9, PointType.FREQUENCY, 0.01, "Hz", "电网频率"),
            TelemetryPoint("grid_power_total", 10, PointType.POWER, 0.1, "kW", "总有功功率"),
        ],
        description="电网侧遥测"
    )
    
    DEFAULT_BATTERY_MAP = RegisterMap(
        points=[
            TelemetryPoint("battery_voltage", 100, PointType.VOLTAGE, 0.1, "V", "电池电压"),
            TelemetryPoint("battery_current", 101, PointType.CURRENT, 0.01, "A", "电池电流"),
            TelemetryPoint("battery_power", 102, PointType.POWER, 0.1, "kW", "电池功率"),
            TelemetryPoint("battery_soc", 103, PointType.PERCENTAGE, 0.01, "%", "电池SOC"),
            TelemetryPoint("battery_soh", 104, PointType.PERCENTAGE, 0.01, "%", "电池SOH"),
        ],
        description="电池侧遥测"
    )
    
    DEFAULT_PV_MAP = RegisterMap(
        points=[
            TelemetryPoint("pv1_voltage", 200, PointType.VOLTAGE, 0.1, "V", "PV1电压"),
            TelemetryPoint("pv1_current", 201, PointType.CURRENT, 0.01, "A", "PV1电流"),
            TelemetryPoint("pv1_power", 202, PointType.POWER, 0.1, "kW", "PV1功率"),
            TelemetryPoint("pv2_voltage", 203, PointType.VOLTAGE, 0.1, "V", "PV2电压"),
            TelemetryPoint("pv2_current", 204, PointType.CURRENT, 0.01, "A", "PV2电流"),
            TelemetryPoint("pv2_power", 205, PointType.POWER, 0.1, "kW", "PV2功率"),
        ],
        description="光伏侧遥测"
    )
    
    DEFAULT_TEMP_MAP = RegisterMap(
        points=[
            TelemetryPoint("internal_temperature", 300, PointType.TEMPERATURE, 0.1, "°C", "内部温度"),
            TelemetryPoint("ambient_temperature", 301, PointType.TEMPERATURE, 0.1, "°C", "环境温度"),
        ],
        description="温度遥测"
    )
    
    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        databits: int = 8,
        parity: str = "none",
        stopbits: int = 1,
        timeout_ms: int = 3000,
        retry_count: int = 2,
        register_maps: Optional[List[RegisterMap]] = None
    ):
        """
        初始化 Modbus-RTU 适配器
        
        Args:
            port: 串口设备路径（如 "/dev/ttyUSB0"）
            baudrate: 波特率（默认 9600）
            databits: 数据位（默认 8）
            parity: 校验位（none/odd/even）
            stopbits: 停止位（默认 1）
            timeout_ms: 超时时间（毫秒）
            retry_count: 重试次数
            register_maps: 自定义寄存器映射（可选，默认使用内置映射）
        """
        # 调用父类初始化（设置 connected, initialized, telemetry_points）
        super().__init__()
        
        self.port = port
        self.baudrate = baudrate
        self.databits = databits
        self.parity = parity
        self.stopbits = stopbits
        self.timeout_ms = timeout_ms
        self.retry_count = retry_count
        
        # 寄存器映射
        self.register_maps: Dict[str, RegisterMap] = {}
        self._init_register_maps(register_maps)
    
    def _init_register_maps(self, custom_maps: Optional[List[RegisterMap]] = None):
        """初始化寄存器映射"""
        if custom_maps:
            for rm in custom_maps:
                self.register_maps[rm.description] = rm
        else:
            self.register_maps = {
                "grid": self.DEFAULT_GRID_MAP,
                "battery": self.DEFAULT_BATTERY_MAP,
                "pv": self.DEFAULT_PV_MAP,
                "temperature": self.DEFAULT_TEMP_MAP,
            }
        
        # 同步遥测点到父类
        self._sync_telemetry_points()
    
    def _sync_telemetry_points(self):
        """将寄存器映射同步到父类的 telemetry_points"""
        self.telemetry_points.clear()
        for rm in self.register_maps.values():
            for point in rm.points:
                self.telemetry_points[point.name] = point
    
    def set_register_maps(self, maps: Dict[str, RegisterMap]) -> None:
        """
        设置自定义寄存器映射
        
        Args:
            maps: 映射组名称 -> RegisterMap
        """
        self.register_maps = maps
        self._sync_telemetry_points()
    
    async def initialize(self) -> bool:
        """初始化 Modbus 适配器"""
        logger.info("初始化 Modbus-RTU: %s @ %dbps", self.port, self.baudrate)
        self.initialized = True
        return True
    
    async def connect(self) -> bool:
        """建立RS485连接"""
        logger.info("连接 Modbus-RTU: %s @ %dbps", self.port, self.baudrate)
        self.connected = True
        return True
    
    async def disconnect(self) -> bool:
        """断开连接"""
        self.connected = False
        return True
    
    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """
        读取设备数据
        
        Args:
            device_address: Modbus 从站地址
            
        Returns:
            Dict[str, Any]: 遥测数据
        """
        return await self.read_telemetry(device_address)
    
    async def write_command(self, device_address: int, command: Dict) -> bool:
        """
        写入控制指令
        
        Args:
            device_address: Modbus 从站地址
            command: 控制指令字典，包含 register 和 value
            
        Returns:
            bool: 是否成功
        """
        register = command.get("register")
        value = command.get("value")
        if register is None or value is None:
            logger.error("控制指令缺少 register 或 value")
            return False
        return await self.write_control(device_address, register, value)
    
    async def read_telemetry(self, device_address: int) -> Dict[str, Any]:
        """
        读取逆变器遥测数据（v2 批量读取优化）
        
        使用寄存器映射配置，按连续地址段批量读取。
        
        Args:
            device_address: Modbus 从站地址
            
        Returns:
            Dict[str, Any]: 遥测数据字典
        """
        if not self.connected:
            await self.connect()
        
        telemetry = {}
        
        for map_name, reg_map in self.register_maps.items():
            groups = reg_map.get_contiguous_groups()
            
            for group in groups:
                if not group:
                    continue
                
                start_addr = group[0].address
                end_addr = max(p.address + p.register_count for p in group)
                count = end_addr - start_addr
                
                # 批量读取寄存器
                raw_values = await self._read_registers(device_address, start_addr, count)
                
                if raw_values:
                    for point in group:
                        offset = point.address - start_addr
                        if offset + point.register_count <= len(raw_values):
                            if point.register_count == 1:
                                raw = raw_values[offset]
                            else:
                                # 多寄存器合并（大端）
                                raw = 0
                                for i in range(point.register_count):
                                    raw = (raw << 16) | raw_values[offset + i]
                            
                            telemetry[point.name] = point.parse(raw)
        
        telemetry["timestamp"] = datetime.now(timezone.utc)
        telemetry["device_address"] = device_address
        
        return telemetry
    
    async def read_telemetry_by_map(
        self, device_address: int, map_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        按指定映射组读取遥测数据
        
        Args:
            device_address: Modbus 从站地址
            map_names: 要读取的映射组名称列表（None=全部）
            
        Returns:
            Dict[str, Any]: 遥测数据字典
        """
        if not self.connected:
            await self.connect()
        
        telemetry = {}
        names_to_read = map_names or list(self.register_maps.keys())
        
        for map_name in names_to_read:
            reg_map = self.register_maps.get(map_name)
            if not reg_map:
                continue
            
            groups = reg_map.get_contiguous_groups()
            for group in groups:
                if not group:
                    continue
                
                start_addr = group[0].address
                end_addr = max(p.address + p.register_count for p in group)
                count = end_addr - start_addr
                
                raw_values = await self._read_registers(device_address, start_addr, count)
                
                if raw_values:
                    for point in group:
                        offset = point.address - start_addr
                        if offset + point.register_count <= len(raw_values):
                            raw = raw_values[offset]
                            telemetry[point.name] = point.parse(raw)
        
        return telemetry
    
    async def read_fault_status(self, device_address: int) -> List[str]:
        """
        读取故障状态
        
        使用功能码 0x02 读离散量输入
        返回活跃故障码列表
        
        Args:
            device_address: Modbus 从站地址
            
        Returns:
            List[str]: 故障码列表（如 ["0x7E", "0xA0"]）
        """
        if not self.connected:
            await self.connect()
        
        fault_codes = []
        
        for start_addr in range(0, 224, 100):
            end_addr = min(start_addr + 100, 224)
            discrete_data = await self._read_discrete(device_address, start_addr, end_addr - start_addr)
            
            if discrete_data:
                for i, value in enumerate(discrete_data):
                    addr = start_addr + i
                    if value:
                        fault_codes.append(f"0x{addr:02X}")
        
        return fault_codes
    
    async def write_control(self, device_address: int, register: int, value: int) -> bool:
        """
        写入控制指令
        
        使用功能码 0x06 写单个寄存器
        
        Args:
            device_address: Modbus 从站地址
            register: 寄存器地址
            value: 写入值
            
        Returns:
            bool: 是否成功
        """
        if not self.connected:
            await self.connect()
        
        return await self._write_single_register(device_address, register, value)
    
    async def _read_registers(self, addr: int, start: int, count: int) -> Optional[List[int]]:
        """读输入寄存器（内部方法）"""
        logger.debug("读寄存器: 设备%d, 起始%d, 数量%d", addr, start, count)
        return [0] * count  # 模拟返回
    
    async def _read_discrete(self, addr: int, start: int, count: int) -> Optional[List[bool]]:
        """读离散量输入（内部方法）"""
        logger.debug("读离散量: 设备%d, 起始%d, 数量%d", addr, start, count)
        return [False] * count  # 模拟返回
    
    async def _write_single_register(self, addr: int, register: int, value: int) -> bool:
        """写单个寄存器（内部方法）"""
        logger.debug("写寄存器: 设备%d, 寄存器%d, 值%d", addr, register, value)
        return True
    
    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """解析故障码"""
        return None
    
    # 数据解析方法（保留向后兼容）
    def _parse_voltage(self, value: int) -> float:
        """解析电压（原始值×0.1V）"""
        return value * 0.1
    
    def _parse_current(self, value: int) -> float:
        """解析电流（原始值×0.01A）"""
        return value * 0.01
    
    def _parse_power(self, value: int) -> float:
        """解析功率（原始值×0.1kW）"""
        return value * 0.1
    
    def _parse_frequency(self, value: int) -> float:
        """解析频率（原始值×0.01Hz）"""
        return value * 0.01