"""
normalizer.py 补充测试 (卡 810f2bd8)

针对 DataNormalizer 现有测试未覆盖的分支/数据结构:
  - STANDARD_UNITS / UNIT_CONVERSION_FACTORS 表完整性契约
  - convert_units 多量纲正向链路 (现有只测 kW→W + 温度; 本文件补 V/mV/kV、
    A/mA/kA、kWh/Wh/MWh、s/min/h、Hz/kHz/MHz 全套正向因子)
  - convert_units 相同单位短路 + 反向因子 (除法)
  - normalize: 空 dict / 无 timestamp / device_address+timestamp 联动对齐

注: 温度 6 向、reverse monkeypatch、_clean_data 各分支、可疑点 characterization
已在 test_parsers_convert_units.py / test_parsers_coverage.py 覆盖, 此处不重复。
"""
import pytest
from datetime import datetime

from app.parsers.normalizer import DataNormalizer
from app.parsers.base_schema import DeviceSchema, DataType, Unit


# ========== 数据结构完整性契约 ==========

class TestStandardUnits:
    def test_standard_units_covers_all_unit_enums(self):
        """STANDARD_UNITS 应覆盖除 NONE 外的全部 Unit 维度"""
        norm = DataNormalizer()
        for u in Unit:
            if u is Unit.NONE:
                continue
            assert u in norm.STANDARD_UNITS, f"缺少 {u}"

    def test_standard_units_value_mapping(self):
        """STANDARD_UNITS 把每个 Unit 维度映射到其标准标签字符串"""
        norm = DataNormalizer()
        assert norm.STANDARD_UNITS[Unit.VOLTAGE] == "V"
        assert norm.STANDARD_UNITS[Unit.PERCENTAGE] == "%"
        assert norm.STANDARD_UNITS[Unit.TEMPERATURE] == "°C"
        assert norm.STANDARD_UNITS[Unit.TIME] == "s"


class TestConversionFactorsSelfConsistency:
    """UNIT_CONVERSION_FACTORS 双向因子自洽: (A,B)=f ⟹ (B,A)=1/f"""

    def test_factor_table_symmetric_reciprocal(self):
        """对所有非 None (温度) 因子对, 反向因子应为倒数"""
        norm = DataNormalizer()
        for (frm, to), factor in norm.UNIT_CONVERSION_FACTORS.items():
            if factor is None:
                continue  # 温度对走偏移转换, 不适用纯因子倒数
            reverse = norm.UNIT_CONVERSION_FACTORS.get((to, frm))
            assert reverse is not None, f"{frm}->{to} 有因子但反向缺失"
            assert reverse == pytest.approx(1.0 / factor)

    def test_temperature_pairs_marked_none(self):
        """温度转换对因子必须为 None (走 _convert_temperature 偏移路径)"""
        norm = DataNormalizer()
        temp_keys = [
            ("°F", "°C"), ("°C", "°F"), ("K", "°C"), ("°C", "K"),
            ("K", "°F"), ("°F", "K"),
        ]
        for k in temp_keys:
            assert norm.UNIT_CONVERSION_FACTORS[k] is None


# ========== convert_units 多量纲正向链路 ==========

class TestConvertUnitsPowerChain:
    def test_kW_to_W(self):
        assert DataNormalizer().convert_units(2.5, "kW", "W") == pytest.approx(2500)

    def test_W_to_kW(self):
        assert DataNormalizer().convert_units(500, "W", "kW") == pytest.approx(0.5)

    def test_MW_to_kW(self):
        assert DataNormalizer().convert_units(1, "MW", "kW") == pytest.approx(1000)

    def test_kW_to_MW(self):
        assert DataNormalizer().convert_units(500, "kW", "MW") == pytest.approx(0.5)

    def test_MW_to_W(self):
        assert DataNormalizer().convert_units(1, "MW", "W") == pytest.approx(1_000_000)

    def test_W_to_MW(self):
        assert DataNormalizer().convert_units(1_000_000, "W", "MW") == pytest.approx(1)


class TestConvertUnitsVoltageChain:
    def test_kV_to_V(self):
        assert DataNormalizer().convert_units(1, "kV", "V") == pytest.approx(1000)

    def test_V_to_kV(self):
        assert DataNormalizer().convert_units(1000, "V", "kV") == pytest.approx(1)

    def test_mV_to_V(self):
        assert DataNormalizer().convert_units(500, "mV", "V") == pytest.approx(0.5)

    def test_V_to_mV(self):
        assert DataNormalizer().convert_units(1, "V", "mV") == pytest.approx(1000)


class TestConvertUnitsCurrentChain:
    def test_kA_to_A(self):
        assert DataNormalizer().convert_units(1, "kA", "A") == pytest.approx(1000)

    def test_A_to_kA(self):
        assert DataNormalizer().convert_units(1000, "A", "kA") == pytest.approx(1)

    def test_mA_to_A(self):
        assert DataNormalizer().convert_units(500, "mA", "A") == pytest.approx(0.5)

    def test_A_to_mA(self):
        assert DataNormalizer().convert_units(1, "A", "mA") == pytest.approx(1000)


class TestConvertUnitsEnergyChain:
    def test_MWh_to_kWh(self):
        assert DataNormalizer().convert_units(1, "MWh", "kWh") == pytest.approx(1000)

    def test_kWh_to_MWh(self):
        assert DataNormalizer().convert_units(1000, "kWh", "MWh") == pytest.approx(1)

    def test_Wh_to_kWh(self):
        assert DataNormalizer().convert_units(500, "Wh", "kWh") == pytest.approx(0.5)

    def test_kWh_to_Wh(self):
        assert DataNormalizer().convert_units(1, "kWh", "Wh") == pytest.approx(1000)


class TestConvertUnitsTimeChain:
    def test_h_to_s(self):
        assert DataNormalizer().convert_units(1, "h", "s") == pytest.approx(3600)

    def test_s_to_h(self):
        assert DataNormalizer().convert_units(3600, "s", "h") == pytest.approx(1)

    def test_min_to_s(self):
        assert DataNormalizer().convert_units(2, "min", "s") == pytest.approx(120)

    def test_s_to_min(self):
        assert DataNormalizer().convert_units(120, "s", "min") == pytest.approx(2)


class TestConvertUnitsFrequencyChain:
    def test_kHz_to_Hz(self):
        assert DataNormalizer().convert_units(1, "kHz", "Hz") == pytest.approx(1000)

    def test_Hz_to_kHz(self):
        assert DataNormalizer().convert_units(1000, "Hz", "kHz") == pytest.approx(1)

    def test_MHz_to_Hz(self):
        assert DataNormalizer().convert_units(1, "MHz", "Hz") == pytest.approx(1_000_000)

    def test_Hz_to_MHz(self):
        assert DataNormalizer().convert_units(1_000_000, "Hz", "MHz") == pytest.approx(1)


class TestConvertUnitsEdgeCases:
    def test_same_unit_short_circuit(self):
        """from==to → 直接返回, 不查表"""
        norm = DataNormalizer()
        assert norm.convert_units(42, "kW", "kW") == 42
        assert norm.convert_units(7, Unit.VOLTAGE, Unit.VOLTAGE) == 7

    def test_unit_enum_label_resolution(self):
        """Unit 枚举作入参 → 取 .value 后查表"""
        norm = DataNormalizer()
        # Unit.POWER.value == "kW", Unit.VOLTAGE.value == "V" → 无因子, 返回原值
        assert norm.convert_units(10, Unit.POWER, Unit.VOLTAGE) == 10

    def test_zero_value(self):
        """0 值转换仍为 0"""
        assert DataNormalizer().convert_units(0, "kW", "W") == 0

    def test_negative_value(self):
        """负值转换保留符号"""
        assert DataNormalizer().convert_units(-2, "kW", "W") == pytest.approx(-2000)

    def test_float_input(self):
        assert DataNormalizer().convert_units(1.5, "kW", "W") == pytest.approx(1500)


# ========== normalize: 空 / 无 timestamp / 联动 ==========

class TestNormalizeEdgeCases:
    def test_normalize_empty_dict(self):
        """空 dict → 空 dict (无 schema 无字段)"""
        assert DataNormalizer().normalize({}) == {}

    def test_normalize_no_timestamp(self):
        """无 timestamp → 不做对齐, 字段原样保留"""
        norm = DataNormalizer()
        result = norm.normalize({"custom": 42})
        assert result == {"custom": 42}

    def test_normalize_no_schema_passthrough(self):
        """无 schema → 所有非特殊字段原样保留"""
        norm = DataNormalizer()
        result = norm.normalize({"a": 1, "b": "x", "timestamp": datetime(2026, 1, 1, 0, 0, 0, 999)})
        assert result["a"] == 1
        assert result["b"] == "x"
        assert result["timestamp"].microsecond == 0

    def test_normalize_device_address_passthrough(self):
        """device_address 不参与解析/清洗, 原样直通"""
        norm = DataNormalizer()
        result = norm.normalize({"device_address": 7, "custom": 9})
        assert result["device_address"] == 7
        assert result["custom"] == 9

    def test_normalize_with_schema_applies_scale(self):
        """有 schema → 字段经 parse_value 缩放"""
        schema = DeviceSchema("d", "modbus")
        schema.add_field({
            "name": "v", "data_type": DataType.UINT16, "unit": Unit.VOLTAGE,
            "scale": 0.1, "offset": 0, "min": None, "max": None,
            "description": "",
        })
        norm = DataNormalizer(schema)
        result = norm.normalize({"v": 2205})
        assert result["v"] == pytest.approx(220.5)
