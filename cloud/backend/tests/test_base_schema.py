"""
base_schema.py 补充测试 (卡 810f2bd8)

针对 DeviceSchema / DataType / Unit 现有测试 (test_parsers.py) 未覆盖的分支:
  - parse_value 字段不存在 → 原值返回 (base_schema.py:173-175)
  - get_field_schema 不存在 → None
  - load_from_dict 默认值兜底 (缺 type/scale/offset/min/max/description)
  - load_from_dict 非法 type → ValueError (DataType 校验)
  - load_from_dict 缺 registers / 空 registers
  - to_dict 字段值逐项断言 (现有仅断言 key 存在)
  - DataType / Unit 枚举契约 (值集合、Unit.NONE、Unit("") 兜底)

注: load_from_dict 的 normal/unit 默认走 DataType()/Unit() 构造, 空串 "" 必须映射到
Unit.NONE (value=''), 否则 load_from_dict 对无 unit 字段会抛 ValueError。
"""
import pytest

from app.parsers.base_schema import DeviceSchema, DataType, Unit, FieldSchema


# ========== DataType / Unit 枚举契约 ==========

class TestDataTypeEnum:
    def test_data_type_values(self):
        """DataType 每个成员的字符串值锁定"""
        assert DataType.UINT16.value == "uint16"
        assert DataType.UINT32.value == "uint32"
        assert DataType.INT16.value == "int16"
        assert DataType.INT32.value == "int32"
        assert DataType.FLOAT.value == "float"
        assert DataType.STRING.value == "string"
        assert DataType.BOOL.value == "bool"

    def test_data_type_from_string(self):
        """合法字符串 → DataType (load_from_dict 依赖此构造)"""
        assert DataType("uint16") is DataType.UINT16
        assert DataType("float") is DataType.FLOAT

    def test_data_type_invalid_raises(self):
        """非法 type 字符串 → ValueError"""
        with pytest.raises(ValueError):
            DataType("badtype")

    def test_data_type_is_str_enum(self):
        """DataType 继承 str, 可直接当字符串比较"""
        assert DataType.UINT16 == "uint16"


class TestUnitEnum:
    def test_unit_values(self):
        assert Unit.VOLTAGE.value == "V"
        assert Unit.CURRENT.value == "A"
        assert Unit.POWER.value == "kW"
        assert Unit.ENERGY.value == "kWh"
        assert Unit.FREQUENCY.value == "Hz"
        assert Unit.TEMPERATURE.value == "°C"
        assert Unit.PERCENTAGE.value == "%"
        assert Unit.TIME.value == "s"

    def test_unit_none_is_empty_string(self):
        """Unit.NONE 值为空串, 是 load_from_dict 缺 unit 时的默认"""
        assert Unit.NONE.value == ""
        assert Unit("") is Unit.NONE

    def test_unit_invalid_raises(self):
        with pytest.raises(ValueError):
            Unit("not_a_unit")

    def test_unit_is_str_enum(self):
        assert Unit.POWER == "kW"


# ========== DeviceSchema.parse_value: 字段不存在分支 ==========

class TestParseValueMissingField:
    def test_parse_value_missing_field_returns_raw(self):
        """字段不在 schema → 原值原样返回 (不缩放/不抛异常)"""
        schema = DeviceSchema("d", "modbus")
        # schema 为空, 任意字段都不存在
        assert schema.parse_value("anything", 999) == 999

    def test_parse_value_missing_field_ignores_scale(self):
        """字段不存在时不会应用任何缩放"""
        schema = DeviceSchema("d", "modbus")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 0.1, "offset": 0, "min": None, "max": None,
            "description": "",
        })
        # 查一个不存在的字段
        assert schema.parse_value("not_v", 1000) == 1000  # 未缩放


# ========== DeviceSchema.get_field_schema: 不存在分支 ==========

class TestGetFieldSchema:
    def test_get_existing_field(self):
        schema = DeviceSchema("d", "modbus")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 0.1, "offset": 0, "min": None, "max": None,
            "description": "x",
        })
        field = schema.get_field_schema("v")
        assert field is not None
        assert field["scale"] == 0.1

    def test_get_missing_field_returns_none(self):
        """字段不存在 → None (normalizer._clean_data 据此判断是否做范围检查)"""
        schema = DeviceSchema("d", "modbus")
        assert schema.get_field_schema("nope") is None


# ========== DeviceSchema.load_from_dict: 默认值兜底 / 异常 ==========

class TestLoadFromDictDefaults:
    def test_load_from_dict_empty_field_config(self):
        """空 field_config → 全部走默认: type=uint16, unit='', scale=1.0, offset=0.0,
        min/max=None, description=''"""
        schema = DeviceSchema("d")
        schema.load_from_dict({"registers": {"x": {}}})

        field = schema.get_field_schema("x")
        assert field["data_type"] is DataType.UINT16
        assert field["unit"] is Unit.NONE
        assert field["scale"] == 1.0
        assert field["offset"] == 0.0
        assert field["min"] is None
        assert field["max"] is None
        assert field["description"] == ""

    def test_load_from_dict_invalid_type_raises(self):
        """非法 type → DataType() 抛 ValueError, 阻止加载脏配置"""
        schema = DeviceSchema("d")
        with pytest.raises(ValueError):
            schema.load_from_dict({"registers": {"x": {"type": "badtype"}}})

    def test_load_from_dict_invalid_unit_raises(self):
        """非法 unit 字符串 → Unit() 抛 ValueError"""
        schema = DeviceSchema("d")
        with pytest.raises(ValueError):
            schema.load_from_dict({"registers": {"x": {"unit": "xyz"}}})

    def test_load_from_dict_missing_registers_key(self):
        """缺 registers 键 → 不报错, fields 为空"""
        schema = DeviceSchema("d", "mqtt")
        schema.load_from_dict({"device_type": "new"})
        assert schema.device_type == "new"
        assert len(schema.fields) == 0

    def test_load_from_dict_empty_registers(self):
        """registers 为空 dict → fields 为空"""
        schema = DeviceSchema("d")
        schema.load_from_dict({"registers": {}})
        assert len(schema.fields) == 0

    def test_load_from_dict_preserves_device_type_when_absent(self):
        """schema_dict 缺 device_type → 保留构造时的原 device_type"""
        schema = DeviceSchema("orig", "modbus")
        schema.load_from_dict({"registers": {}})
        assert schema.device_type == "orig"

    def test_load_from_dict_partial_field_config(self):
        """部分配置 → 其余走默认"""
        schema = DeviceSchema("d")
        schema.load_from_dict({
            "registers": {
                "v": {"type": "int16", "scale": 2.0, "unit": "V"},
            }
        })
        field = schema.get_field_schema("v")
        assert field["data_type"] is DataType.INT16
        assert field["unit"] is Unit.VOLTAGE
        assert field["scale"] == 2.0
        assert field["offset"] == 0.0  # 默认
        assert field["description"] == ""  # 默认


# ========== DeviceSchema.to_dict: 字段值逐项断言 ==========

class TestToDictFields:
    def test_to_dict_round_trip_field_values(self):
        """to_dict 应完整保留 type/unit/scale/offset/min/max/description"""
        schema = DeviceSchema("dev", "modbus")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 0.1, "offset": -5, "min": 0, "max": 500,
            "description": "A相电压",
        })
        out = schema.to_dict()

        assert out["device_type"] == "dev"
        assert out["protocol"] == "modbus"
        reg = out["registers"]["v"]
        assert reg["type"] == "uint16"
        assert reg["unit"] == "V"
        assert reg["scale"] == 0.1
        assert reg["offset"] == -5
        assert reg["min"] == 0
        assert reg["max"] == 500
        assert reg["description"] == "A相电压"

    def test_to_dict_none_min_max_preserved(self):
        """min/max=None 应原样导出为 None"""
        schema = DeviceSchema("d")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 1.0, "offset": 0, "min": None, "max": None,
            "description": "",
        })
        reg = schema.to_dict()["registers"]["v"]
        assert reg["min"] is None
        assert reg["max"] is None

    def test_to_dict_empty_schema(self):
        """空 schema → registers 为空 dict"""
        out = DeviceSchema("d", "mqtt").to_dict()
        assert out == {"device_type": "d", "protocol": "mqtt", "registers": {}}


# ========== DeviceSchema 初始化默认 protocol ==========

class TestDeviceSchemaInit:
    def test_default_protocol_is_unknown(self):
        """不传 protocol → 默认 'unknown'"""
        schema = DeviceSchema("d")
        assert schema.protocol == "unknown"

    def test_fields_starts_empty(self):
        schema = DeviceSchema("d", "modbus")
        assert schema.fields == {}


# ========== parse_value 范围越界只 warn 不拦截 ==========

class TestParseValueRangeWarning:
    def test_parse_value_below_min_still_returns(self):
        """值 < min 只记 warning, 仍返回计算值 (非拦截, 与 normalizer 清洗分工)"""
        schema = DeviceSchema("d")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 1.0, "offset": 0, "min": 100, "max": None,
            "description": "",
        })
        # raw=50, scale=1 → 50 < min=100, 但 parse_value 仍返回 50
        assert schema.parse_value("v", 50) == 50

    def test_parse_value_above_max_still_returns(self):
        schema = DeviceSchema("d")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 1.0, "offset": 0, "min": None, "max": 100,
            "description": "",
        })
        assert schema.parse_value("v", 150) == 150
