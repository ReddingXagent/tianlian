"""test_mode_price.py — PriceStrategy 电价优先充电模式单元测试

被测对象: app/services/charging/mode_price.py 的 PriceStrategy。

纯逻辑测试。电价决策契约:
- grid_price is None        → 无电价信息, 按需求充电(不阻塞), clamp 到额定。
- grid_price <= 0.50        → 低谷, 集中充电(按需求, clamp 到额定)。
- grid_price >  0.50        → 高电价, 暂停充电(target=0, curtailed)。
- 所有充电分支均走 clamp_power, 负值归零, 超额归额定。
"""
import pytest

from app.services.charging.mode_price import PriceStrategy
from app.services.charging.strategy_base import ChargingMode, ChargingContext


@pytest.fixture
def s():
    return PriceStrategy()


def _ctx(**kw):
    defaults = dict(station_id="s1", charger_id="c1", rated_power_kw=120, demand_power_kw=60)
    defaults.update(kw)
    return ChargingContext(**defaults)


class TestPriceMeta:
    def test_mode(self, s):
        assert s.mode == ChargingMode.PRICE

    def test_priority(self, s):
        assert s.priority == 4

    def test_get_mode(self, s):
        assert s.get_mode() == ChargingMode.PRICE

    def test_valley_threshold_constant(self, s):
        assert s.VALLEY_THRESHOLD == 0.50


class TestPriceDecision:
    def test_low_price_charges(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.3))
        assert d.target_power_kw == 60
        assert d.grid_power_kw == 60
        assert not d.curtailed
        assert d.source == "grid"

    def test_high_price_stops(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.8))
        assert d.target_power_kw == 0
        assert d.curtailed

    def test_no_price_allows_charging(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=None))
        assert d.target_power_kw == 60
        assert not d.curtailed
        assert "无电价" in d.reason

    def test_threshold_boundary_inclusive_low(self, s):
        """price == 0.50 满足 <= 阈值 → 视为低谷充电。"""
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.50))
        assert d.target_power_kw == 60
        assert not d.curtailed

    def test_just_above_threshold_stops(self, s):
        """price == 0.51 超过阈值 → 暂停充电。"""
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.51))
        assert d.target_power_kw == 0
        assert d.curtailed

    def test_zero_price_charges(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.0))
        assert d.target_power_kw == 60
        assert not d.curtailed


class TestPriceClamping:
    def test_clamps_to_rated_when_low_price(self, s):
        d = s.evaluate(_ctx(demand_power_kw=200, rated_power_kw=120, grid_price=0.3))
        assert d.target_power_kw == 120

    def test_clamps_to_rated_when_no_price(self, s):
        d = s.evaluate(_ctx(demand_power_kw=200, rated_power_kw=120, grid_price=None))
        assert d.target_power_kw == 120

    def test_negative_demand_clamped_to_zero(self, s):
        d = s.evaluate(_ctx(demand_power_kw=-50, grid_price=0.3))
        assert d.target_power_kw == 0


class TestPriceReasonAndSource:
    def test_reason_low_price_includes_value(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.3))
        assert "低谷电价" in d.reason
        assert "0.30" in d.reason

    def test_reason_high_price_includes_value(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, grid_price=0.8))
        assert "高电价" in d.reason
        assert "0.80" in d.reason
        assert "暂停" in d.reason

    def test_source_none_when_stopped(self, s):
        d = s.evaluate(_ctx(grid_price=0.8))
        assert d.source == "none"

    def test_source_grid_when_charging(self, s):
        d = s.evaluate(_ctx(grid_price=0.3))
        assert d.source == "grid"
