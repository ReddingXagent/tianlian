"""
Modbus 寄存器映射表 - 定义各设备类型的寄存器地址和解析规则

从 data_collector.py 提取寄存器地址，支持设备类型动态扩展。
"""
from typing import Dict, Any, TypedDict
import logging
import json
import os

from .base_schema import DeviceSchema

logger = logging.getLogger(__name__)


class ModbusRegisterConfig(TypedDict):
    """
    Modbus 寄存器配置
    
    Attributes:
        address: 寄存器地址
        type: 数据类型
        scale: 缩放因子
        unit: 单位
        description: 字段描述
    """
    address: int
    type: str
    scale: float
    unit: str
    description: str


# ========== 逆变器遥测寄存器地址（EAHI5-20K-TH-G3 V1.5） ==========

INVERTER_EAHI_20K_REGISTERS: Dict[str, ModbusRegisterConfig] = {
    # 电网侧（地址0-47）
    "grid_voltage_a": {
        "address": 0,
        "type": "uint16",
        "scale": 0.1,
        "unit": "V",
        "description": "A相电压"
    },
    "grid_current_a": {
        "address": 1,
        "type": "uint16",
        "scale": 0.01,
        "unit": "A",
        "description": "A相电流"
    },
    "grid_power_a": {
        "address": 2,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "A相功率"
    },
    "grid_voltage_b": {
        "address": 3,
        "type": "uint16",
        "scale": 0.1,
        "unit": "V",
        "description": "B相电压"
    },
    "grid_current_b": {
        "address": 4,
        "type": "uint16",
        "scale": 0.01,
        "unit": "A",
        "description": "B相电流"
    },
    "grid_power_b": {
        "address": 5,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "B相功率"
    },
    "grid_voltage_c": {
        "address": 6,
        "type": "uint16",
        "scale": 0.1,
        "unit": "V",
        "description": "C相电压"
    },
    "grid_current_c": {
        "address": 7,
        "type": "uint16",
        "scale": 0.01,
        "unit": "A",
        "description": "C相电流"
    },
    "grid_power_c": {
        "address": 8,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "C相功率"
    },
    "grid_frequency": {
        "address": 9,
        "type": "uint16",
        "scale": 0.01,
        "unit": "Hz",
        "description": "频率"
    },
    "grid_power_total": {
        "address": 10,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "总功率"
    },
    
    # 电池侧（地址100-130）
    "battery_voltage": {
        "address": 100,
        "type": "uint16",
        "scale": 0.1,
        "unit": "V",
        "description": "电池电压"
    },
    "battery_current": {
        "address": 101,
        "type": "uint16",
        "scale": 0.01,
        "unit": "A",
        "description": "电池电流"
    },
    "battery_power": {
        "address": 102,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "电池功率"
    },
    "battery_soc": {
        "address": 103,
        "type": "uint16",
        "scale": 0.01,
        "unit": "%",
        "description": "电池SOC"
    },
    "battery_soh": {
        "address": 104,
        "type": "uint16",
        "scale": 0.01,
        "unit": "%",
        "description": "电池SOH"
    },
    
    # 光伏侧（地址200-230）
    "pv1_voltage": {
        "address": 200,
        "type": "uint16",
        "scale": 0.1,
        "unit": "V",
        "description": "PV1电压"
    },
    "pv1_current": {
        "address": 201,
        "type": "uint16",
        "scale": 0.01,
        "unit": "A",
        "description": "PV1电流"
    },
    "pv1_power": {
        "address": 202,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "PV1功率"
    },
    "pv2_voltage": {
        "address": 203,
        "type": "uint16",
        "scale": 0.1,
        "unit": "V",
        "description": "PV2电压"
    },
    "pv2_current": {
        "address": 204,
        "type": "uint16",
        "scale": 0.01,
        "unit": "A",
        "description": "PV2电流"
    },
    "pv2_power": {
        "address": 205,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kW",
        "description": "PV2功率"
    },
    
    # 温度（地址300-310）
    "internal_temperature": {
        "address": 300,
        "type": "uint16",
        "scale": 0.1,
        "unit": "°C",
        "description": "机内温度"
    },
    "ambient_temperature": {
        "address": 301,
        "type": "uint16",
        "scale": 0.1,
        "unit": "°C",
        "description": "环境温度"
    },
    
    # 电能（地址400-420）
    "daily_generation": {
        "address": 400,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kWh",
        "description": "日发电量"
    },
    "daily_charge": {
        "address": 401,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kWh",
        "description": "日充电量"
    },
    "daily_discharge": {
        "address": 402,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kWh",
        "description": "日放电量"
    },
    "total_generation": {
        "address": 403,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kWh",
        "description": "累计发电量"
    },
    "total_charge": {
        "address": 404,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kWh",
        "description": "累计充电量"
    },
    "total_discharge": {
        "address": 405,
        "type": "uint16",
        "scale": 0.1,
        "unit": "kWh",
        "description": "累计放电量"
    },
    
    # 运行状态（地址500-510）
    "run_time": {
        "address": 500,
        "type": "uint16",
        "scale": 1.0,
        "unit": "s",
        "description": "运行时间"
    },
    "run_mode": {
        "address": 501,
        "type": "uint16",
        "scale": 1.0,
        "unit": "",
        "description": "运行模式"
    },
    "system_status": {
        "address": 502,
        "type": "uint16",
        "scale": 1.0,
        "unit": "",
        "description": "系统状态"
    },
}


# ========== 故障状态离散量输入地址（地址0-223） ==========

INVERTER_FAULT_DISCRETE_ADDR: Dict[int, str] = {
    # 电网侧故障（0-47）
    0: "grid_over_voltage_a",   # A相一段过压
    3: "grid_under_voltage_a",  # A相一段欠压
    39: "island_fault",         # 孤岛故障
    
    # 逆变侧故障（48-111）
    60: "bus_short",            # 母线短路
    80: "inverter_over_current_a", # A相快速过流
    
    # 电池侧故障（112-143）
    126: "bms_comm_fault",      # BMS通信异常
    130: "battery_over_current", # 电池过流
    
    # 温度故障（160-162）
    160: "internal_over_temp",  # 机内过温
    161: "pv_over_temp",        # PV过温
    162: "inverter_over_temp",  # 逆变过温
    
    # 其他故障（196-223）
    212: "meter_comm_fault",    # 电表通信故障
}


# ========== Schema 配置文件目录 ==========

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")


def _load_schema_json(device_type: str) -> Dict[str, Any]:
    """
    从 JSON 配置文件加载设备 Schema
    
    支持的扩展方式：
    1. 在 schemas/ 目录下放置 {device_type}.modbus.json 文件
    2. 文件格式与 DeviceSchema.load_from_dict() 兼容
    """
    # 确保 schemas 目录存在
    if not os.path.isdir(SCHEMA_DIR):
        return None

    # 尝试匹配 JSON 文件: {device_type}.modbus.json 或 {device_type}.json
    for ext in [f"{device_type}.modbus.json", f"{device_type}.json"]:
        path = os.path.join(SCHEMA_DIR, ext)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    schema_dict = json.load(f)
                logger.info("从 JSON 配置文件加载 Schema: %s (%s)", device_type, path)
                return schema_dict
            except (json.JSONDecodeError, IOError) as e:
                logger.error("加载 Schema JSON 失败: %s - %s", path, e)
                return None

    return None


def load_inverter_schema() -> DeviceSchema:
    """
    加载逆变器 Schema（EAHI5-20K）
    
    Returns:
        DeviceSchema: 逆变器数据 Schema
    """
    schema = DeviceSchema("inverter_eahi_20k", "modbus")
    
    # 加载寄存器配置
    schema_dict = {
        "device_type": "inverter_eahi_20k",
        "protocol": "modbus",
        "registers": INVERTER_EAHI_20K_REGISTERS,
    }
    
    schema.load_from_dict(schema_dict)
    
    logger.info("加载逆变器 Schema: %d 个字段", len(schema.fields))
    return schema


def load_modbus_schema(device_type: str) -> DeviceSchema:
    """
    加载指定设备类型的 Modbus Schema
    
    Args:
        device_type: 设备类型标识
        
    Returns:
        DeviceSchema: 设备数据 Schema
        
    Note:
        支持扩展：可通过 JSON 配置文件加载新设备类型
    """
    # 内置设备类型
    if device_type == "inverter_eahi_20k":
        return load_inverter_schema()
    
    # 从 JSON 配置文件加载
    schema_dict = _load_schema_json(device_type)
    if schema_dict is not None:
        schema = DeviceSchema(device_type, protocol=schema_dict.get("protocol", "modbus"))
        schema.load_from_dict(schema_dict)
        logger.info("从 JSON 配置加载设备 Schema: %s", device_type)
        return schema
    
    # 未找到——返回一个空的 DeviceSchema（不报错），确保调用方仍能获得有效对象
    logger.warning("未找到设备类型 %s 的 Modbus Schema，返回空 Schema", device_type)
    return DeviceSchema(device_type, "modbus")