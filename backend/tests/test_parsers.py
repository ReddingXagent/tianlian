"""
解析层测试 - 测试 parsers 层核心功能

测试内容：
    - DeviceSchema 数据 Schema
    - DataNormalizer 数据标准化
    - ParsePipeline 解析流水线
    - Modbus/MQTT Schema 加载
"""
import pytest
from datetime import datetime

from app.parsers import (
    DeviceSchema,
    DataType,
    Unit,
    DataNormalizer,
    ParsePipeline,
    create_pipeline,
    load_modbus_schema,
    load_mqtt_schema,
    INVERTER_EAHI_20K_REGISTERS,
    CHARGER_TELEMETRY_FIELDS,
)


# ========== DeviceSchema 测试 ==========

def test_schema_init():
    """测试 Schema 初始化"""
    schema = DeviceSchema("test_device", "modbus")
    
    assert schema.device_type == "test_device"
    assert schema.protocol == "modbus"
    assert len(schema.fields) == 0


def test_schema_add_field():
    """测试添加字段"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "grid_voltage",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 0.1,
        "offset": 0,
        "min": 0,
        "max": 500,
        "description": "电网电压",
    })
    
    assert len(schema.fields) == 1
    assert "grid_voltage" in schema.fields
    
    field = schema.get_field_schema("grid_voltage")
    assert field["data_type"] == DataType.UINT16
    assert field["unit"] == Unit.VOLTAGE
    assert field["scale"] == 0.1


def test_schema_load_from_dict():
    """测试从字典加载 Schema"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema_dict = {
        "device_type": "custom_device",
        "protocol": "mqtt",
        "registers": {
            "test_voltage": {
                "type": "uint16",
                "unit": "V",
                "scale": 0.1,
                "offset": 0,
                "description": "测试电压",
            },
            "test_current": {
                "type": "uint16",
                "unit": "A",
                "scale": 0.01,
                "offset": 0,
                "description": "测试电流",
            },
        },
    }
    
    schema.load_from_dict(schema_dict)
    
    assert schema.device_type == "custom_device"
    assert schema.protocol == "mqtt"
    assert len(schema.fields) == 2
    assert "test_voltage" in schema.fields
    assert "test_current" in schema.fields


def test_schema_parse_value():
    """测试字段值解析"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "voltage",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 0.1,
        "offset": 0,
        "min": 0,
        "max": 500,
        "description": "电压",
    })
    
    # 原始值 2205 → 220.5V
    parsed_value = schema.parse_value("voltage", 2205)
    assert parsed_value == 220.5


def test_schema_parse_value_with_offset():
    """测试带偏移的字段值解析"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "temperature",
        "data_type": DataType.UINT16,
        "unit": Unit.TEMPERATURE,
        "scale": 0.1,
        "offset": -40,  # 偏移 -40°C
        "min": -40,
        "max": 100,
        "description": "温度",
    })
    
    # 原始值 250 → 25.0 - 40 = -15°C
    parsed_value = schema.parse_value("temperature", 250)
    assert parsed_value == -15.0


def test_schema_list_fields():
    """测试列出字段"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "field1",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 1.0,
        "offset": 0,
        "min": None,
        "max": None,
        "description": "字段1",
    })
    
    schema.add_field({
        "name": "field2",
        "data_type": DataType.UINT16,
        "unit": Unit.CURRENT,
        "scale": 1.0,
        "offset": 0,
        "min": None,
        "max": None,
        "description": "字段2",
    })
    
    fields = schema.list_fields()
    
    assert len(fields) == 2
    assert "field1" in fields
    assert "field2" in fields


def test_schema_to_dict():
    """测试导出为字典"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "voltage",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 0.1,
        "offset": 0,
        "min": 0,
        "max": 500,
        "description": "电压",
    })
    
    schema_dict = schema.to_dict()
    
    assert schema_dict["device_type"] == "test_device"
    assert schema_dict["protocol"] == "modbus"
    assert "registers" in schema_dict
    assert "voltage" in schema_dict["registers"]


# ========== DataNormalizer 测试 ==========

def test_normalizer_init():
    """测试标准化器初始化"""
    normalizer = DataNormalizer()
    
    assert normalizer.schema is None


def test_normalizer_init_with_schema():
    """测试带 Schema 的标准化器初始化"""
    schema = DeviceSchema("test_device", "modbus")
    normalizer = DataNormalizer(schema)
    
    assert normalizer.schema is not None


def test_normalizer_normalize():
    """测试数据标准化"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "voltage",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 0.1,
        "offset": 0,
        "min": 0,
        "max": 500,
        "description": "电压",
    })
    
    normalizer = DataNormalizer(schema)
    
    raw_data = {
        "voltage": 2205,
        "timestamp": datetime.now(),
        "device_address": 1,
    }
    
    normalized = normalizer.normalize(raw_data)
    
    assert normalized["voltage"] == 220.5
    assert "timestamp" in normalized
    assert normalized["device_address"] == 1


def test_normalizer_align_time():
    """测试时间对齐"""
    normalizer = DataNormalizer()
    
    # 原始时间（带微秒）
    timestamp = datetime(2026, 6, 2, 12, 30, 45, 123456)
    
    # 对齐到整秒
    aligned = normalizer._align_time(timestamp)
    
    assert aligned.microsecond == 0
    assert aligned.second == 45


def test_normalizer_clean_data():
    """测试数据清洗"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "voltage",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 1.0,
        "offset": 0,
        "min": 0,
        "max": 500,
        "description": "电压",
    })
    
    normalizer = DataNormalizer(schema)
    
    # 包含异常值的数据
    raw_data = {
        "grid_voltage": -100,  # 异常负值（符合电压负值检查规则）
        "current": None,  # None 值
        "grid_power_total": -50,  # 功率负值（不在检查范围内，因为包含 'total'）
        "timestamp": datetime.now(),
    }
    
    cleaned = normalizer._clean_data(raw_data)
    
    # 异常值应被过滤
    assert "grid_voltage" not in cleaned  # 电压负值被过滤
    assert "current" not in cleaned  # None 值被过滤
    # grid_power_total 包含 'total' 不被过滤，或者改为测试 grid_power
    assert "timestamp" in cleaned


def test_normalizer_batch_normalize():
    """测试批量标准化"""
    schema = DeviceSchema("test_device", "modbus")
    
    schema.add_field({
        "name": "voltage",
        "data_type": DataType.UINT16,
        "unit": Unit.VOLTAGE,
        "scale": 0.1,
        "offset": 0,
        "min": 0,
        "max": 500,
        "description": "电压",
    })
    
    normalizer = DataNormalizer(schema)
    
    raw_data_list = [
        {"voltage": 2205, "timestamp": datetime.now()},
        {"voltage": 3805, "timestamp": datetime.now()},
    ]
    
    normalized_list = normalizer.batch_normalize(raw_data_list)
    
    assert len(normalized_list) == 2
    assert normalized_list[0]["voltage"] == 220.5
    assert normalized_list[1]["voltage"] == 380.5


# ========== ParsePipeline 测试 ==========

def test_pipeline_init():
    """测试流水线初始化"""
    pipeline = ParsePipeline("test_device", "modbus")
    
    assert pipeline.device_type == "test_device"
    assert pipeline.protocol == "modbus"
    assert len(pipeline.steps) == 0


def test_pipeline_add_step():
    """测试添加步骤"""
    pipeline = ParsePipeline("test_device", "modbus")
    
    def custom_step(data):
        data["custom"] = "test"
        return data
    
    pipeline.add_step("custom", custom_step)
    
    assert len(pipeline.steps) == 1


@pytest.mark.asyncio
async def test_pipeline_execute():
    """测试执行流水线"""
    pipeline = ParsePipeline("test_device", "modbus")
    
    def step1(data):
        data["step1"] = "done"
        return data
    
    def step2(data):
        data["step2"] = "done"
        return data
    
    pipeline.add_step("step1", step1)
    pipeline.add_step("step2", step2)
    
    raw_data = {"input": "test"}
    result = await pipeline.execute(raw_data)
    
    assert result["input"] == "test"
    assert result["step1"] == "done"
    assert result["step2"] == "done"


@pytest.mark.asyncio
async def test_pipeline_build_default():
    """测试构建默认流水线"""
    pipeline = create_pipeline("inverter_eahi_20k", "modbus")
    
    raw_data = {
        "grid_voltage_a": 2205,
        "device_address": 1,
        "timestamp": datetime.now(),
    }
    
    result = await pipeline.execute(raw_data)
    
    # 应包含元信息
    assert "device_type" in result
    assert "protocol" in result
    assert result["device_type"] == "inverter_eahi_20k"


# ========== Modbus Schema 测试 ==========

def test_load_modbus_schema():
    """测试加载 Modbus Schema"""
    schema = load_modbus_schema("inverter_eahi_20k")
    
    assert schema.device_type == "inverter_eahi_20k"
    assert schema.protocol == "modbus"
    
    # 应包含预定义寄存器
    assert "grid_voltage_a" in schema.fields
    assert "battery_soc" in schema.fields


def test_inverter_registers():
    """测试逆变器寄存器定义"""
    # 验证预定义寄存器存在
    assert "grid_voltage_a" in INVERTER_EAHI_20K_REGISTERS
    assert "grid_current_a" in INVERTER_EAHI_20K_REGISTERS
    assert "battery_soc" in INVERTER_EAHI_20K_REGISTERS
    
    # 验证寄存器配置
    voltage_config = INVERTER_EAHI_20K_REGISTERS["grid_voltage_a"]
    assert voltage_config["address"] == 0
    assert voltage_config["scale"] == 0.1
    assert voltage_config["unit"] == "V"


# ========== MQTT Schema 测试 ==========

def test_load_mqtt_schema():
    """测试加载 MQTT Schema"""
    schema = load_mqtt_schema("charger_dc_60kw")
    
    assert schema.device_type == "charger_dc_60kw"
    assert schema.protocol == "mqtt"
    
    # 应包含预定义字段
    assert "charger_voltage" in schema.fields
    assert "charger_soc" in schema.fields


def test_charger_telemetry_fields():
    """测试充电桩遥测字段"""
    assert "charger_voltage" in CHARGER_TELEMETRY_FIELDS
    assert "charger_current" in CHARGER_TELEMETRY_FIELDS
    assert "gun_status" in CHARGER_TELEMETRY_FIELDS
    
    # 验证字段配置
    voltage_config = CHARGER_TELEMETRY_FIELDS["charger_voltage"]
    assert voltage_config["unit"] == "V"


def test_mqtt_topic_generation():
    """测试 MQTT 主题生成"""
    from app.parsers.mqtt_schema import get_topic
    
    topic = get_topic("TCU001", "up")
    assert topic == "tcu/TCU001/report"
    
    topic = get_topic("TCU001", "down")
    assert topic == "tcu/TCU001/control"


def test_mqtt_message_type_parsing():
    """测试 MQTT 消息类型解析"""
    from app.parsers.mqtt_schema import parse_message_type
    
    type_name = parse_message_type(0x122001)
    assert type_name == "telemetry"
    
    type_name = parse_message_type(0x122006)
    assert type_name == "fault_report"