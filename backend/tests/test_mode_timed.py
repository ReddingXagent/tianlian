"""test_mode_timed.py — TimedStrategy 定时充电模式单元测试

被测对象: app/services/charging/mode_timed.py 的 TimedStrategy。

纯逻辑测试(无 DB / 外部依赖;ChargingContext 为 dataclass, 直接构造)。
峰谷调度契约:
- in_valley_period is True  → 低谷时段, 按需求满功率充电(clamp 到额定), curtailed=False
- in_valley_period is False → 高峰时段, 停充(target=0, curtailed=True)
- in_valley_period is None  → 无时段信息, 保守停充(target=0, curtailed=True)

边界: 分支用 `is True` / `is False` 严格判断, 任何非 bool 的 truthy/falsy 值
(如 1 / 0) 一律落入 else → 保守停充。
"""
import pytest

from app.services.charging.mode_timed import TimedStrategy
from app.services.charging.strategy_base import ChargingMode, ChargingContext


@pytest.fixture
def s():
    return TimedStrategy()


def _ctx(**kw):
    defaults = dict(station_id="s1", charger_id="c1", rated_power_kw=120, demand_power_kw=60)
    defaults.update(kw)
    return ChargingContext(**defaults)


class TestTimedMeta:
    def test_mode(self, s):
        assert s.mode == ChargingMode.TIMED

    def test_priority(self, s):
        assert s.priority == 2

    def test_get_mode(self, s):
        assert s.get_mode() == ChargingMode.TIMED


class TestTimedValleyCharges:
    def test_valley_charges_at_demand(self, s):
        d = s.evaluate(_ctx(in_valley_period=True, demand_power_kw=60))
        assert d.grid_power_kw == 60
        assert d.target_power_kw == 60
        assert not d.curtailed
        assert d.source == "grid"

    def test_valley_clamps_to_rated(self, s):
        d = s.evaluate(_ctx(in_valley_period=True, demand_power_kw=200, rated_power_kw=120))
        assert d.target_power_kw == 120
        assert not d.curtailed

    def test_valley_zero_demand_zero_target(self, s):
        d = s.evaluate(_ctx(in_valley_period=True, demand_power_kw=0))
        assert d.target_power_kw == 0
        assert not d.curtailed  # 低谷分支硬编码 False, 即便 0 功率也不算降功率
        assert d.source == "none"

    def test_valley_negative_demand_clamped_to_zero(self, s):
        d = s.evaluate(_ctx(in_valley_period=True, demand_power_kw=-50))
        assert d.target_power_kw == 0


class TestTimedPeakStops:
    def test_peak_stops_charging(self, s):
        d = s.evaluate(_ctx(in_valley_period=False, demand_power_kw=60))
        assert d.target_power_kw == 0
        assert d.grid_power_kw == 0
        assert d.curtailed
        assert d.source == "none"

    def test_peak_ignores_high_demand(self, s):
        """高峰时段即便需求很高也强制停充。"""
        d = s.evaluate(_ctx(in_valley_period=False, demand_power_kw=500))
        assert d.target_power_kw == 0
        assert d.curtailed


class TestTimedNoPeriodInfo:
    def test_none_period_stops_conservatively(self, s):
        d = s.evaluate(_ctx(in_valley_period=None, demand_power_kw=60))
        assert d.target_power_kw == 0
        assert d.curtailed
        assert "无时段信息" in d.reason

    def test_default_period_is_none_stops(self, s):
        """不传 in_valley_period 时默认 None → 保守停充。"""
        d = s.evaluate(_ctx(demand_power_kw=60))
        assert d.target_power_kw == 0
        assert d.curtailed


class TestTimedStrictBool:
    """分支用 `is True`/`is False` 严格判断, 非 bool 值一律落 else。"""

    def test_truthy_non_bool_falls_to_conservative(self, s):
        d = s.evaluate(_ctx(in_valley_period=1, demand_power_kw=60))
        assert d.target_power_kw == 0
        assert d.curtailed
        assert "无时段信息" in d.reason

    def test_falsy_non_bool_falls_to_conservative(self, s):
        d = s.evaluate(_ctx(in_valley_period=0, demand_power_kw=60))
        assert d.target_power_kw == 0
        assert d.curtailed


class TestTimedReasonAndSource:
    def test_reason_valley_includes_power(self, s):
        d = s.evaluate(_ctx(in_valley_period=True, demand_power_kw=60))
        assert "低谷时段满功率充电" in d.reason
        assert "60.0kW" in d.reason

    def test_reason_peak_text(self, s):
        d = s.evaluate(_ctx(in_valley_period=False))
        assert "高峰时段停充" in d.reason
        assert "定时模式" in d.reason

    def test_source_grid_when_valley_charging(self, s):
        d = s.evaluate(_ctx(in_valley_period=True, demand_power_kw=60))
        assert d.source == "grid"

    def test_source_none_when_stopped(self, s):
        d = s.evaluate(_ctx(in_valley_period=False, demand_power_kw=60))
        assert d.source == "none"
