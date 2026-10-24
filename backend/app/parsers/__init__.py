"""
解析层包入口 - 提供统一的解析接口

包含：
    - DeviceSchema: 数据 Schema 定义
    - DataNormalizer: 数据标准化器
    - ParsePipeline: 解析流水线
"""
from .base_schema import DeviceSchema, DataType, Unit, FieldSchema
from .normalizer import DataNormalizer
from .pipeline import ParsePipeline, create_pipeline
from .modbus_schema import load_modbus_schema, INVERTER_EAHI_20K_REGISTERS
from .mqtt_schema import load_mqtt_schema, CHARGER_TELEMETRY_FIELDS


__all__ = [
    # Schema
    "DeviceSchema",
    "DataType",
    "Unit",
    "FieldSchema",
    
    # 解析器
    "DataNormalizer",
    "ParsePipeline",
    "create_pipeline",
    
    # Schema 加载
    "load_modbus_schema",
    "load_mqtt_schema",
    
    # 预定义 Schema
    "INVERTER_EAHI_20K_REGISTERS",
    "CHARGER_TELEMETRY_FIELDS",
]