"""
MQTT 主题映射 - 定义 MQTT 消息的字段映射和解析规则

适用于直流充电桩的 MQTT 协议解析。
"""
from typing import Dict, TypedDict
import logging

from .base_schema import DeviceSchema

logger = logging.getLogger(__name__)


class MQTTFieldConfig(TypedDict):
    """
    MQTT 字段配置
    
    Attributes:
        field: 字段名称
        type: 数据类型
        unit: 单位
        description: 字段描述
    """
    field: str
    type: str
    unit: str
    description: str


# ========== 充电桩遥测字段映射（MQTT 消息类型 0x122001） ==========

CHARGER_TELEMETRY_FIELDS: Dict[str, MQTTFieldConfig] = {
    "charger_voltage": {
        "field": "charger_voltage",
        "type": "float",
        "unit": "V",
        "description": "充电电压"
    },
    "charger_current": {
        "field": "charger_current",
        "type": "float",
        "unit": "A",
        "description": "充电电流"
    },
    "charger_power": {
        "field": "charger_power",
        "type": "float",
        "unit": "kW",
        "description": "充电功率"
    },
    "charger_soc": {
        "field": "charger_soc",
        "type": "float",
        "unit": "%",
        "description": "电池SOC"
    },
    "gun_status": {
        "field": "gun_status",
        "type": "uint16",
        "unit": "",
        "description": "枪头状态（1=充电中）"
    },
    "gun_temperature": {
        "field": "gun_temperature",
        "type": "float",
        "unit": "°C",
        "description": "枪头温度"
    },
    "internal_temperature": {
        "field": "internal_temperature",
        "type": "float",
        "unit": "°C",
        "description": "机内温度"
    },
}


# ========== MQTT 消息类型映射 ==========

MQTT_MESSAGE_TYPES: Dict[int, str] = {
    0x122001: "telemetry",     # 遥测数据上报
    0x122006: "fault_report",  # 故障上报
    0x122002: "charge_status", # 充电状态
    0x4000: "control_set",     # 参数设置
    0x4001: "control_reset",   # 复位控制
    0x4002: "control_reboot",  # 重启控制
}


# ========== MQTT 主题结构 ==========

MQTT_TOPIC_STRUCTURE: Dict[str, str] = {
    "telemetry_up": "tcu/{tcu_address}/report",  # 上行（遥测/告警上报）
    "control_down": "tcu/{tcu_address}/control", # 下行（控制指令）
}


def load_charger_schema() -> DeviceSchema:
    """
    加载充电桩 Schema
    
    Returns:
        DeviceSchema: 充电桩数据 Schema
    """
    schema = DeviceSchema("charger_dc_60kw", "mqtt")
    
    # 加载字段配置
    schema_dict = {
        "device_type": "charger_dc_60kw",
        "protocol": "mqtt",
        "registers": {
            field_name: {
                "type": field_config["type"],
                "unit": field_config["unit"],
                "scale": 1.0,  # MQTT 数据通常无需缩放
                "offset": 0.0,
                "description": field_config["description"],
            }
            for field_name, field_config in CHARGER_TELEMETRY_FIELDS.items()
        },
    }
    
    schema.load_from_dict(schema_dict)
    
    logger.info("加载充电桩 Schema: %d 个字段", len(schema.fields))
    return schema


def get_topic(device_address: str, direction: str = "up") -> str:
    """
    生成 MQTT 主题
    
    Args:
        device_address: TCU 地址
        direction: 方向（up=上行, down=下行）
        
    Returns:
        str: MQTT 主题
        
    Example:
        >>> topic = get_topic("TCU001", "up")
        >>> print(topic)  # "tcu/TCU001/report"
    """
    template_key = f"telemetry_up" if direction == "up" else "control_down"
    template = MQTT_TOPIC_STRUCTURE[template_key]
    
    return template.format(tcu_address=device_address)


def parse_message_type(message_type: int) -> str:
    """
    解析 MQTT 消息类型
    
    Args:
        message_type: 消息类型代码
        
    Returns:
        str: 消息类型名称
        
    Example:
        >>> type_name = parse_message_type(0x122001)
        >>> print(type_name)  # "telemetry"
    """
    return MQTT_MESSAGE_TYPES.get(message_type, "unknown")


def load_mqtt_schema(device_type: str) -> DeviceSchema:
    """
    加载指定设备类型的 MQTT Schema
    
    Args:
        device_type: 设备类型标识
        
    Returns:
        DeviceSchema: 设备数据 Schema
    """
    # 内置设备类型
    if device_type == "charger_dc_60kw":
        return load_charger_schema()
    
    # 其他设备类型（从配置文件加载）
    logger.warning("未找到设备类型 %s 的 MQTT Schema", device_type)
    return DeviceSchema(device_type, "mqtt")