"""
parsers 层 convert_units 死代码修复 + 边界 characterization 测试 (卡 1b22c251)

本文件覆盖 test_parsers_coverage.py 未触达的两块:
  1. 通过 convert_units *公开入口* 验证温度转换 6 向 —— 修复前全部 RED。
     死代码根因: UNIT_CONVERSION_FACTORS 温度对 value=None, convert_units 用
     `.get((from,to))` 后 `if factor is not None:` 判空, None 直接跳过整个分支,
     内层 `if factor is None: return self._convert_temperature(...)` 永不可达。
  2. convert_units 反向因子 / 反向温度分支 (monkeypatch 单向表锁死)。
  3. 4 个可疑点 characterization (锁定当前行为, 非本次修复范围):
     - _align_time 对 str/epoch 非 datetime 无类型守卫 → AttributeError
     - _clean_data 对 str 型值做数值比较 → TypeError (特定条件下)
     - 负功率过滤 (除 total) 的语义限制: V2G 放电/逆变器出力负功率会被误丢
     - batch_normalize 列表推导无单条隔离, 一条坏数据炸整批
"""
import pytest
from datetime import datetime

from app.parsers.normalizer import DataNormalizer
from app.parsers.base_schema import DeviceSchema, Unit


# ========== convert_units 温度转换 (公开入口) ==========

class TestConvertUnitsTemperature:
    """通过 convert_units 公开入口验证温度转换 6 向。

    修复前: 温度对 value=None 致 convert_units 静默返回原值, 全部 RED。
    """

    def test_fahrenheit_to_celsius(self):
        norm = DataNormalizer()
        assert norm.convert_units(212, "°F", "°C") == pytest.approx(100)

    def test_celsius_to_fahrenheit(self):
        norm = DataNormalizer()
        assert norm.convert_units(100, "°C", "°F") == pytest.approx(212)

    def test_kelvin_to_celsius(self):
        norm = DataNormalizer()
        assert norm.convert_units(273.15, "K", "°C") == pytest.approx(0, abs=1e-6)

    def test_celsius_to_kelvin(self):
        norm = DataNormalizer()
        assert norm.convert_units(0, "°C", "K") == pytest.approx(273.15)

    def test_kelvin_to_fahrenheit(self):
        """K → °C → °F (UNIT_CONVERSION_FACTORS 须注册 (K,°F) 键才能触发)"""
        norm = DataNormalizer()
        assert norm.convert_units(273.15, "K", "°F") == pytest.approx(32)

    def test_fahrenheit_to_kelvin(self):
        """°F → °C → K (UNIT_CONVERSION_FACTORS 须注册 (°F,K) 键才能触发)"""
        norm = DataNormalizer()
        assert norm.convert_units(32, "°F", "K") == pytest.approx(273.15)

    def test_celsius_to_fahrenheit_via_unit_enum(self):
        """Unit.TEMPERATURE (='°C') 作 from_unit 同样命中温度分支"""
        norm = DataNormalizer()
        assert norm.convert_units(100, Unit.TEMPERATURE, "°F") == pytest.approx(212)


# ========== convert_units 反向分支 (monkeypatch 单向表) ==========

class TestConvertUnitsReverseBranch:
    """锁死 convert_units 反向查找分支 (查 (from,to) 未命中时回退查 (to,from))。

    真实表双向齐全, 反向分支日常不触发; 用 monkeypatch 注入单向表强制走反向,
    防未来重构改坏。温度表修复后反向温度分支也应正确路由到 _convert_temperature。
    """

    def test_reverse_factor_branch(self, monkeypatch):
        """表里只有 (to,from) 单向因子时 → value / factor"""
        norm = DataNormalizer()
        monkeypatch.setattr(norm, "UNIT_CONVERSION_FACTORS", {("W", "kW"): 0.001})
        # 查 ("kW","W") 正向未命中, 反向 ("W","kW")=0.001 → 2 / 0.001 = 2000
        assert norm.convert_units(2, "kW", "W") == pytest.approx(2000)

    def test_reverse_temperature_branch(self, monkeypatch):
        """反向键是温度对 (value=None) 时 → _convert_temperature"""
        norm = DataNormalizer()
        monkeypatch.setattr(norm, "UNIT_CONVERSION_FACTORS", {("°C", "°F"): None})
        # 查 ("°F","°C") 正向未命中, 反向 ("°C","°F")=None → 温度转换
        assert norm.convert_units(212, "°F", "°C") == pytest.approx(100)

    def test_unknown_units_returns_original(self):
        """正反向都查无 → warning + 原值返回, 不抛异常"""
        norm = DataNormalizer()
        assert norm.convert_units(10, "foo", "bar") == 10


# ========== 4 个可疑点 characterization ==========

class TestNormalizerEdgeCases:
    """锁定当前边界行为 (非本次修复范围, 供未来决策参考)。"""

    def test_align_time_non_datetime_raises(self):
        """[可疑点1] _align_time 对 str/epoch 无类型守卫, 直接 .replace 即崩。

        两种不同失败模式 (刻画当前行为):
          - str: 恰有 .replace 但签名不兼容 (不接受关键字参数) → TypeError
          - int: 无 .replace 属性 → AttributeError
        正常链路 timestamp 总是 datetime (pipeline add_metadata_step 兜底注入)。
        """
        norm = DataNormalizer()
        with pytest.raises(TypeError):
            norm._align_time("2026-01-01T00:00:00.123")
        with pytest.raises(AttributeError):
            norm._align_time(1700000000)

    def test_clean_data_str_value_with_min_raises(self):
        """[可疑点2] schema 有 min 且 value 是 str → 'str' < int 抛 TypeError"""
        schema = DeviceSchema("t", "modbus")
        schema.add_field({
            "name": "v", "data_type": "uint16", "unit": "V",
            "scale": 1.0, "offset": 0.0, "min": 0, "max": 100,
        })
        norm = DataNormalizer(schema)
        with pytest.raises(TypeError):
            norm._clean_data({"v": "abc"})

    def test_clean_data_str_voltage_field_raises_without_schema(self):
        """[可疑点2] 无 schema + 字段名以 _voltage 结尾 + str 值 → 负值检查 'str'<0 抛 TypeError"""
        norm = DataNormalizer()
        with pytest.raises(TypeError):
            norm._clean_data({"grid_voltage": "abc"})

    def test_clean_data_str_plain_field_passthrough(self):
        """[可疑点2] 无 schema + 普通字段名 + str 值 → 不触发任何数值比较, 原样保留"""
        norm = DataNormalizer()
        result = norm._clean_data({"custom_field": "abc"})
        assert result["custom_field"] == "abc"

    def test_negative_power_filtered_except_total(self):
        """[可疑点3] 负功率被静默过滤 (仅含 'total' 字段名例外)。

        已知语义限制: 逆变器出力/V2G 放电场景负功率是合法语义, 当前会被误丢。
        修复需产品决策 (哪些 _power 字段允许负值), 不在本次 convert_units 修复范围。
        """
        norm = DataNormalizer()
        result = norm.normalize({
            "grid_power": -5,
            "battery_power": -3,   # V2G 放电会被误丢
            "total_power": -10,    # 含 'total' 例外保留
            "timestamp": datetime(2026, 1, 1),
        })
        assert "grid_power" not in result
        assert "battery_power" not in result
        assert result["total_power"] == -10

    def test_batch_normalize_no_isolation(self):
        """[可疑点4] batch_normalize 列表推导无单条隔离, 一条坏数据炸整批。

        一条 normalize 抛异常 → 整批无结果返回。健壮化需加 try/except 单条隔离。
        """
        schema = DeviceSchema("t", "modbus")
        schema.add_field({
            "name": "v", "data_type": "uint16", "unit": "V",
            "scale": 1.0, "offset": 0.0, "min": 0, "max": 100,
        })
        norm = DataNormalizer(schema)
        records = [
            {"v": 50, "timestamp": datetime(2026, 1, 1)},
            {"v": 50, "timestamp": "not-a-datetime"},  # 坏数据 → _align_time 崩
            {"v": 60, "timestamp": datetime(2026, 1, 2)},
        ]
        with pytest.raises(TypeError):
            norm.batch_normalize(records)
