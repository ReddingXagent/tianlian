"""
Parsers 模块补充覆盖率测试 (Phase33-Task4)

补 app/parsers/ 缺口：
  - normalizer.py: _clean_data 各分支 + convert_units + _convert_temperature
  - modbus_schema.py: _load_schema_json + load_modbus_schema JSON 分支/兜底

目标：app/parsers/ 整体覆盖率 ≥ 80%。
"""
import json

import pytest

from app.parsers.normalizer import DataNormalizer
from app.parsers.base_schema import DeviceSchema, Unit
import app.parsers.modbus_schema as modbus_schema_module
from app.parsers.modbus_schema import (
    _load_schema_json,
    load_modbus_schema,
)


# ========== DataNormalizer._clean_data 分支 ==========

class TestCleanDataBranches:
    def test_clean_filters_negative_voltage(self):
        """负电压 (字段名以 _voltage 结尾) → 丢弃"""
        norm = DataNormalizer()  # schema=None
        from datetime import datetime
        result = norm.normalize({"test_voltage": -1, "timestamp": datetime.now()})
        assert "test_voltage" not in result

    def test_clean_filters_negative_power(self):
        """负功率 (非 total) → 丢弃"""
        norm = DataNormalizer()
        from datetime import datetime
        result = norm.normalize({"grid_power": -5, "timestamp": datetime.now()})
        assert "grid_power" not in result

    def test_clean_keeps_negative_total_power(self):
        """total_power 含 total，负值保留"""
        norm = DataNormalizer()
        from datetime import datetime
        result = norm.normalize({"total_power": -5, "timestamp": datetime.now()})
        assert result["total_power"] == -5

    def test_clean_filters_below_min(self):
        """低于 schema min → 丢弃"""
        schema = DeviceSchema("test", "modbus")
        schema.add_field({
            "name": "v", "data_type": "uint16", "unit": "V",
            "scale": 1.0, "offset": 0.0, "min": 100, "max": 300,
        })
        norm = DataNormalizer(schema)
        from datetime import datetime
        result = norm.normalize({"v": 50, "timestamp": datetime.now()})
        assert "v" not in result

    def test_clean_filters_above_max(self):
        """高于 schema max → 丢弃"""
        schema = DeviceSchema("test", "modbus")
        schema.add_field({
            "name": "v", "data_type": "uint16", "unit": "V",
            "scale": 1.0, "offset": 0.0, "min": 0, "max": 100,
        })
        norm = DataNormalizer(schema)
        from datetime import datetime
        result = norm.normalize({"v": 150, "timestamp": datetime.now()})
        assert "v" not in result

    def test_normalize_without_schema_passthrough(self):
        """无 schema 时字段原样保留"""
        norm = DataNormalizer()
        from datetime import datetime
        result = norm.normalize({"custom_field": 42, "timestamp": datetime.now()})
        assert result["custom_field"] == 42


# ========== DataNormalizer.convert_units ==========

class TestConvertUnits:
    def test_same_unit_no_conversion(self):
        norm = DataNormalizer()
        assert norm.convert_units(5, Unit.VOLTAGE, Unit.VOLTAGE) == 5

    def test_direct_factor(self):
        """kW → W 乘 1000 (直接查表命中)"""
        norm = DataNormalizer()
        assert norm.convert_units(2, "kW", "W") == 2000

    def test_unsupported_units_returns_original(self):
        """无转换因子 → 原值返回 (V→A 无意义)"""
        norm = DataNormalizer()
        assert norm.convert_units(10, Unit.VOLTAGE, Unit.CURRENT) == 10


# ========== DataNormalizer._convert_temperature (底层函数直接测试) ==========
# 注: convert_units 温度死代码已于卡 1b22c251 修复 (键成员判断替代 .get() is not None,
# 温度表补全 K↔°F), 公开入口 6 向测试见 test_parsers_convert_units.py;
# 此处保留对 _convert_temperature 底层函数的直接单测。

class TestConvertTemperature:
    def test_fahrenheit_to_celsius(self):
        norm = DataNormalizer()
        assert norm._convert_temperature(212, "°F", "°C") == pytest.approx(100)

    def test_celsius_to_fahrenheit(self):
        norm = DataNormalizer()
        assert norm._convert_temperature(100, "°C", "°F") == pytest.approx(212)

    def test_kelvin_to_celsius(self):
        norm = DataNormalizer()
        assert norm._convert_temperature(273.15, "K", "°C") == pytest.approx(0, abs=1e-6)

    def test_celsius_to_kelvin(self):
        norm = DataNormalizer()
        assert norm._convert_temperature(0, "°C", "K") == pytest.approx(273.15)

    def test_kelvin_to_fahrenheit(self):
        """K → °C → °F"""
        norm = DataNormalizer()
        assert norm._convert_temperature(273.15, "K", "°F") == pytest.approx(32)

    def test_fahrenheit_to_kelvin(self):
        """°F → °C → K"""
        norm = DataNormalizer()
        assert norm._convert_temperature(32, "°F", "K") == pytest.approx(273.15)

    def test_unsupported_temperature_returns_original(self):
        norm = DataNormalizer()
        assert norm._convert_temperature(5, "X", "Y") == 5


# ========== modbus_schema._load_schema_json / load_modbus_schema ==========

class TestLoadSchemaJson:
    def test_load_schema_json_no_dir(self, monkeypatch, tmp_path):
        """SCHEMA_DIR 不存在 → None"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path / "nonexistent"))
        assert _load_schema_json("any_device") is None

    def test_load_schema_json_from_file(self, monkeypatch, tmp_path):
        """目录存在 + JSON 文件 → 返回 dict"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path))
        schema_dict = {"device_type": "dev", "protocol": "modbus", "registers": {}}
        (tmp_path / "dev.modbus.json").write_text(json.dumps(schema_dict), encoding="utf-8")
        assert _load_schema_json("dev") == schema_dict

    def test_load_schema_json_fallback_ext(self, monkeypatch, tmp_path):
        """无 .modbus.json 时回退 {device_type}.json"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path))
        schema_dict = {"device_type": "dev2", "protocol": "modbus"}
        (tmp_path / "dev2.json").write_text(json.dumps(schema_dict), encoding="utf-8")
        assert _load_schema_json("dev2") == schema_dict

    def test_load_schema_json_bad_json(self, monkeypatch, tmp_path):
        """损坏 JSON → None"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path))
        (tmp_path / "bad.modbus.json").write_text("{not valid json", encoding="utf-8")
        assert _load_schema_json("bad") is None

    def test_load_schema_json_no_matching_file(self, monkeypatch, tmp_path):
        """目录存在但无匹配文件 → None"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path))
        assert _load_schema_json("missing") is None


class TestLoadModbusSchemaFallback:
    def test_load_unknown_device_returns_empty_schema(self, monkeypatch, tmp_path):
        """未知 device_type + 无 JSON → 返回空 DeviceSchema (不抛异常)"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path / "none"))
        schema = load_modbus_schema("unknown_device")
        assert schema is not None
        assert schema.device_type == "unknown_device"

    def test_load_from_json_file(self, monkeypatch, tmp_path):
        """JSON 文件存在 → 加载为带字段的 DeviceSchema"""
        monkeypatch.setattr(modbus_schema_module, "SCHEMA_DIR", str(tmp_path))
        schema_dict = {
            "device_type": "custom_dev",
            "protocol": "modbus",
            "registers": {
                "voltage": {"address": 0, "type": "uint16", "scale": 0.1, "unit": "V"},
            },
        }
        (tmp_path / "custom_dev.modbus.json").write_text(json.dumps(schema_dict), encoding="utf-8")
        schema = load_modbus_schema("custom_dev")
        assert "voltage" in schema.fields
