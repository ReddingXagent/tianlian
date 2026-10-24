"""
数据 Schema 定义 - JSON Schema + 标准化接口

定义数据字段的类型、单位、范围、映射规则等元信息。
支持设备类型动态扩展，通过 JSON 配置定义数据 Schema。
"""
from typing import Dict, Any, List, Optional, TypedDict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """数据类型枚举"""
    UINT16 = "uint16"
    UINT32 = "uint32"
    INT16 = "int16"
    INT32 = "int32"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"


class Unit(str, Enum):
    """单位枚举"""
    VOLTAGE = "V"  # 电压
    CURRENT = "A"  # 电流
    POWER = "kW"  # 功率
    ENERGY = "kWh"  # 电能
    FREQUENCY = "Hz"  # 频率
    TEMPERATURE = "°C"  # 温度
    PERCENTAGE = "%"  # 百分比
    TIME = "s"  # 时间
    NONE = ""  # 无单位


class FieldSchema(TypedDict):
    """
    字段 Schema 定义
    
    Attributes:
        name: 字段名称
        data_type: 数据类型
        unit: 单位
        scale: 缩放因子（原始值 × scale = 实际值）
        offset: 偏移量（原始值 × scale + offset = 实际值）
        min: 最小值（可选）
        max: 最大值（可选）
        description: 字段描述
    """
    name: str
    data_type: DataType
    unit: Unit
    scale: float
    offset: float
    min: Optional[float]
    max: Optional[float]
    description: str


class DeviceSchema:
    """
    设备数据 Schema
    
    定义设备类型的所有数据字段及其解析规则。
    
    Example:
        >>> schema = DeviceSchema("inverter_eahi_20k")
        >>> schema.add_field({
        ...     "name": "grid_voltage_a",
        ...     "data_type": DataType.UINT16,
        ...     "unit": Unit.VOLTAGEAGE,
        ...     "scale": 0.1,
        ...     "offset": 0,
        ...     "description": "A相电压"
        ... })
        >>> value = schema.parse_value("grid_voltage_a", 2205)  # 220.5V
    """
    
    def __init__(self, device_type: str, protocol: str = "unknown"):
        """
        初始化设备 Schema
        
        Args:
            device_type: 设备类型标识
            protocol: 协议类型（modbus/mqtt/rest）
        """
        self.device_type = device_type
        self.protocol = protocol
        self.fields: Dict[str, FieldSchema] = {}
        
    def add_field(self, field_schema: FieldSchema) -> None:
        """
        添加字段 Schema
        
        Args:
            field_schema: 字段 Schema 定义
            
        Example:
            >>> schema.add_field({
            ...     "name": "battery_soc",
            ...     "data_type": DataType.UINT16,
            ...     "unit": Unit.PERCENTAGE,
            ...     "scale": 0.01,
            ...     "offset": 0,
            ...     "min": 0,
            ...     "max": 100,
            ...     "description": "电池SOC"
            ... })
        """
        field_name = field_schema["name"]
        self.fields[field_name] = field_schema
        logger.debug("添加字段: %s to %s", field_name, self.device_type)
    
    def load_from_dict(self, schema_dict: Dict[str, Any]) -> None:
        """
        从字典加载 Schema
        
        Args:
            schema_dict: Schema 字典（通常从 JSON 文件加载）
            
        Example JSON:
            {
                "device_type": "inverter_eahi_20k",
                "protocol": "modbus",
                "registers": {
                    "grid_voltage_a": {
                        "address": 0,
                        "type": "uint16",
                        "scale": 0.1,
                        "unit": "V"
                    }
                }
            }
        """
        self.device_type = schema_dict.get("device_type", self.device_type)
        self.protocol = schema_dict.get("protocol", self.protocol)
        
        # 加载字段
        registers = schema_dict.get("registers", {})
        for field_name, field_config in registers.items():
            field_schema = FieldSchema(
                name=field_name,
                data_type=DataType(field_config.get("type", "uint16")),
                unit=Unit(field_config.get("unit", "")),
                scale=field_config.get("scale", 1.0),
                offset=field_config.get("offset", 0.0),
                min=field_config.get("min"),
                max=field_config.get("max"),
                description=field_config.get("description", ""),
            )
            self.add_field(field_schema)
        
        logger.info("加载 Schema: %s, %d 个字段", self.device_type, len(self.fields))
    
    def parse_value(self, field_name: str, raw_value: int) -> float:
        """
        解析原始值为实际值
        
        Args:
            field_name: 字段名称
            raw_value: 原始值（从设备读取）
            
        Returns:
            float: 实际值
            
        Example:
            >>> value = schema.parse_value("grid_voltage_a", 2205)  # 220.5
        """
        field = self.fields.get(field_name)
        
        if not field:
            logger.warning("未找到字段: %s", field_name)
            return raw_value
        
        # 应用缩放和偏移
        actual_value = raw_value * field["scale"] + field["offset"]
        
        # 检查范围（可选）
        if field["min"] is not None and actual_value < field["min"]:
            logger.warning("字段 %s 值 %s 小于最小值 %s", field_name, actual_value, field['min'])
        
        if field["max"] is not None and actual_value > field["max"]:
            logger.warning("字段 %s 值 %s 大于最大值 %s", field_name, actual_value, field['max'])
        
        return actual_value
    
    def get_field_schema(self, field_name: str) -> Optional[FieldSchema]:
        """
        获取字段 Schema
        
        Args:
            field_name: 字段名称
            
        Returns:
            Optional[FieldSchema]: 字段 Schema
        """
        return self.fields.get(field_name)
    
    def list_fields(self) -> List[str]:
        """
        列出所有字段名称
        
        Returns:
            List[str]: 字段名称列表
        """
        return list(self.fields.keys())
    
    def to_dict(self) -> Dict[str, Any]:
        """
        导出为字典
        
        Returns:
            Dict[str, Any]: Schema 字典
        """
        return {
            "device_type": self.device_type,
            "protocol": self.protocol,
            "registers": {
                field_name: {
                    "type": field["data_type"].value,
                    "unit": field["unit"].value,
                    "scale": field["scale"],
                    "offset": field["offset"],
                    "min": field["min"],
                    "max": field["max"],
                    "description": field["description"],
                }
                for field_name, field in self.fields.items()
            }
        }