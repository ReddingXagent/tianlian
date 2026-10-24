"""test_strategy_base.py — 充电策略基类单元测试

覆盖: ChargingMode 枚举, ChargingContext 字段, ChargingDecision.reconcile_source,
ChargingStrategy.clamp_power, 具体策略 evaluate/get_mode/priority/name/description。
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.services.charging.strategy_base import (
    ChargingMode,
    ChargingContext,
    ChargingDecision,
    ChargingStrategy,
    _MODE_NAMES,
    _MODE_DESCRIPTIONS,
)


# ─── ChargingMode 枚举 ───

class TestChargingMode:
    def test_mode_values(self):
        assert ChargingMode.MANUAL.value == "manual"
        assert ChargingMode.TIMED.value == "timed"
        assert ChargingMode.SOLAR.value == "solar"
        assert ChargingMode.PRICE.value == "price"
        assert ChargingMode.BALANCED.value == "balanced"

    def test_mode_is_str_enum(self):
        assert isinstance(ChargingMode.MANUAL, str)
        assert ChargingMode.MANUAL == "manual"

    def test_mode_count(self):
        assert len(ChargingMode) == 5


# ─── ChargingContext ───

class TestChargingContext:
    def test_minimal_context(self):
        ctx = ChargingContext(station_id="s1", charger_id="c1", rated_power_kw=120)
        assert ctx.station_id == "s1"
        assert ctx.demand_power_kw == 0.0
        assert ctx.timestamp is not None

    def test_full_context(self):
        ctx = ChargingContext(
            station_id="s1", charger_id="c1", rated_power_kw=120,
            demand_power_kw=60, current_soc=0.3, target_soc=0.8,
            pv_output_kw=30, battery_soc=0.7, grid_price=0.5,
        )
        assert ctx.demand_power_kw == 60
        assert ctx.battery_soc == 0.7

    def test_timestamp_auto_generated(self):
        ctx1 = ChargingContext(station_id="s", charger_id="c", rated_power_kw=1)
        assert isinstance(ctx1.timestamp, datetime)

    def test_optional_fields_default_none(self):
        ctx = ChargingContext(station_id="s", charger_id="c", rated_power_kw=1)
        assert ctx.current_soc is None
        assert ctx.target_soc is None
        assert ctx.grid_price is None
        assert ctx.in_valley_period is None
        assert ctx.manual_power_kw is None


# ─── ChargingDecision.reconcile_source ───

class TestReconcileSource:
    def test_all_zero_source_none(self):
        d = ChargingDecision(mode=ChargingMode.MANUAL)
        d.reconcile_source()
        assert d.source == "none"
        assert d.target_power_kw == 0.0

    def test_only_pv(self):
        d = ChargingDecision(mode=ChargingMode.SOLAR, pv_power_kw=10)
        d.reconcile_source()
        assert d.source == "pv"
        assert d.target_power_kw == 10.0

    def test_only_battery(self):
        d = ChargingDecision(mode=ChargingMode.BALANCED, battery_power_kw=20)
        d.reconcile_source()
        assert d.source == "battery"
        assert d.target_power_kw == 20.0

    def test_only_grid(self):
        d = ChargingDecision(mode=ChargingMode.MANUAL, grid_power_kw=30)
        d.reconcile_source()
        assert d.source == "grid"
        assert d.target_power_kw == 30.0

    def test_pv_and_grid_mixed(self):
        d = ChargingDecision(mode=ChargingMode.BALANCED, pv_power_kw=10, grid_power_kw=20)
        d.reconcile_source()
        assert d.source == "mixed"
        assert d.target_power_kw == 30.0

    def test_all_three_sources_mixed(self):
        d = ChargingDecision(
            mode=ChargingMode.BALANCED,
            pv_power_kw=10, battery_power_kw=15, grid_power_kw=5,
        )
        d.reconcile_source()
        assert d.source == "mixed"
        assert d.target_power_kw == 30.0

    def test_threshold_below_1e9_is_zero(self):
        """功率 < 1e-9 视为零"""
        d = ChargingDecision(mode=ChargingMode.SOLAR, pv_power_kw=1e-10)
        d.reconcile_source()
        assert d.source == "none"

    def test_threshold_exactly_1e9(self):
        """功率 == 1e-9 视为零（不大于阈值）"""
        d = ChargingDecision(mode=ChargingMode.SOLAR, pv_power_kw=1e-9)
        d.reconcile_source()
        assert d.source == "none"

    def test_round_to_4_decimals(self):
        d = ChargingDecision(
            mode=ChargingMode.BALANCED,
            pv_power_kw=10.123456, grid_power_kw=20.654321,
        )
        d.reconcile_source()
        assert d.target_power_kw == round(30.777777, 4)


# ─── ChargingStrategy.clamp_power ───

class TestClampPower:
    def test_clamp_negative_to_zero(self):
        assert ChargingStrategy.clamp_power(-5, 120) == 0.0

    def test_clamp_within_range(self):
        assert ChargingStrategy.clamp_power(50, 120) == 50

    def test_clamp_above_rated(self):
        assert ChargingStrategy.clamp_power(200, 120) == 120

    def test_clamp_negative_rated_to_zero(self):
        assert ChargingStrategy.clamp_power(50, -10) == 0.0

    def test_clamp_zero(self):
        assert ChargingStrategy.clamp_power(0, 120) == 0.0

    def test_clamp_exact_rated(self):
        assert ChargingStrategy.clamp_power(120, 120) == 120


# ─── 具体策略 (用于测试抽象基类) ───

class _DummyStrategy(ChargingStrategy):
    """手动模式策略 — 直接返回 manual_power_kw"""
    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.MANUAL

    @property
    def priority(self) -> int:
        return 1

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        power = self.clamp_power(ctx.manual_power_kw or 0, ctx.rated_power_kw)
        d = ChargingDecision(
            mode=ChargingMode.MANUAL,
            grid_power_kw=power,
            reason=f"手动功率 {power}kW",
        )
        d.reconcile_source()
        return d


class _SolarStrategy(ChargingStrategy):
    """光伏策略简化版"""
    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.SOLAR

    @property
    def priority(self) -> int:
        return 2

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        pv = min(ctx.pv_output_kw, ctx.demand_power_kw or ctx.rated_power_kw)
        pv = self.clamp_power(pv, ctx.rated_power_kw)
        d = ChargingDecision(
            mode=ChargingMode.SOLAR,
            pv_power_kw=pv,
            reason=f"光伏供电 {pv}kW",
        )
        d.reconcile_source()
        return d


class TestConcreteStrategies:
    def test_manual_strategy_returns_grid(self):
        s = _DummyStrategy()
        ctx = ChargingContext(station_id="s", charger_id="c", rated_power_kw=120, manual_power_kw=60)
        d = s.evaluate(ctx)
        assert d.mode == ChargingMode.MANUAL
        assert d.source == "grid"
        assert d.target_power_kw == 60

    def test_manual_strategy_clamps_to_rated(self):
        s = _DummyStrategy()
        ctx = ChargingContext(station_id="s", charger_id="c", rated_power_kw=60, manual_power_kw=200)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 60

    def test_solar_strategy(self):
        s = _SolarStrategy()
        ctx = ChargingContext(station_id="s", charger_id="c", rated_power_kw=120,
                              demand_power_kw=30, pv_output_kw=50)
        d = s.evaluate(ctx)
        assert d.source == "pv"
        assert d.target_power_kw == 30

    def test_get_mode(self):
        s = _DummyStrategy()
        assert s.get_mode() == ChargingMode.MANUAL

    def test_name_property(self):
        s = _DummyStrategy()
        assert s.name == "手动模式"

    def test_description_property(self):
        s = _SolarStrategy()
        assert "光伏" in s.description

    def test_solar_description_not_empty(self):
        s = _SolarStrategy()
        assert len(s.description) > 0

    def test_priority_ordering(self):
        manual = _DummyStrategy()
        solar = _SolarStrategy()
        assert manual.priority < solar.priority


# ─── 模式名/描述查找表 ───

class TestModeLookups:
    def test_all_modes_have_names(self):
        for mode in ChargingMode:
            assert mode in _MODE_NAMES
            assert len(_MODE_NAMES[mode]) > 0

    def test_all_modes_have_descriptions(self):
        for mode in ChargingMode:
            assert mode in _MODE_DESCRIPTIONS
            assert len(_MODE_DESCRIPTIONS[mode]) > 0

    def test_unknown_mode_fallback(self):
        """基类 name/description 对未知模式有 fallback"""
        class _UnknownStrategy(ChargingStrategy):
            @property
            def mode(self):
                return ChargingMode.BALANCED
            @property
            def priority(self):
                return 5
            def evaluate(self, ctx):
                return ChargingDecision(mode=ChargingMode.BALANCED)

        s = _UnknownStrategy()
        assert s.name == "均衡模式"
        assert len(s.description) > 0
