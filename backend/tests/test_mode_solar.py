"""test_mode_solar.py — SolarStrategy 光伏优先充电模式单元测试

被测对象: app/services/charging/mode_solar.py 的 SolarStrategy。

纯逻辑测试(无 DB / 外部依赖;ChargingContext 为 dataclass, 直接构造)。
光伏优先契约(仅用光伏, 不取电网):
- target = clamp(min(demand, pv), rated)         # 取需求与光伏的较小者, 再钳位额定
- curtailed = target < demand - 1e-9             # 实际充电低于需求即降功率
- 光伏 >= 需求 且未触额定 → 按需求充(curtailed=False, "(光伏充足)")
- 光伏 <  需求            → 降至光伏水平(curtailed=True, "(降功率)")
- 即便光伏充足, 若被额定钳位导致 target < demand, 仍标记 curtailed。
所有充电走 pv_power_kw; target=0 时 source="none"。
"""
import pytest

from app.services.charging.mode_solar import SolarStrategy
from app.services.charging.strategy_base import ChargingMode, ChargingContext


@pytest.fixture
def s():
    return SolarStrategy()


def _ctx(**kw):
    defaults = dict(station_id="s1", charger_id="c1", rated_power_kw=120, demand_power_kw=60)
    defaults.update(kw)
    return ChargingContext(**defaults)


class TestSolarMeta:
    def test_mode(self, s):
        assert s.mode == ChargingMode.SOLAR

    def test_priority(self, s):
        assert s.priority == 3

    def test_get_mode(self, s):
        assert s.get_mode() == ChargingMode.SOLAR


class TestSolarPvSufficient:
    def test_pv_covers_demand_charges_at_demand(self, s):
        d = s.evaluate(_ctx(demand_power_kw=40, pv_output_kw=60))
        assert d.pv_power_kw == 40
        assert d.target_power_kw == 40
        assert not d.curtailed
        assert d.source == "pv"

    def test_pv_equals_demand_not_curtailed(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, pv_output_kw=60))
        assert d.pv_power_kw == 60
        assert not d.curtailed

    def test_pv_surplus_not_beyond_demand(self, s):
        """光伏过剩时只按需求充, 不超过需求。"""
        d = s.evaluate(_ctx(demand_power_kw=30, pv_output_kw=100))
        assert d.pv_power_kw == 30
        assert not d.curtailed
        assert "光伏充足" in d.reason


class TestSolarPvInsufficient:
    def test_pv_less_than_demand_curtailed(self, s):
        d = s.evaluate(_ctx(demand_power_kw=80, pv_output_kw=40))
        assert d.pv_power_kw == 40
        assert d.target_power_kw == 40
        assert d.curtailed
        assert "降功率" in d.reason

    def test_zero_pv_zero_target_curtailed(self, s):
        d = s.evaluate(_ctx(demand_power_kw=50, pv_output_kw=0))
        assert d.pv_power_kw == 0
        assert d.target_power_kw == 0
        assert d.curtailed
        assert d.source == "none"

    def test_zero_demand_zero_target_not_curtailed(self, s):
        """需求为 0 时光伏再多也不充, 且不算降功率(target 不低于 demand)。"""
        d = s.evaluate(_ctx(demand_power_kw=0, pv_output_kw=50))
        assert d.pv_power_kw == 0
        assert d.target_power_kw == 0
        assert not d.curtailed
        assert d.source == "none"


class TestSolarClamping:
    def test_clamps_to_rated_when_pv_sufficient(self, s):
        """光伏充足但需求超过额定 → 钳位额定, 且因 target<demand 标记 curtailed。"""
        d = s.evaluate(_ctx(demand_power_kw=200, pv_output_kw=300, rated_power_kw=120))
        assert d.pv_power_kw == 120
        assert d.target_power_kw == 120
        assert d.curtailed

    def test_clamps_to_rated_when_pv_insufficient(self, s):
        d = s.evaluate(_ctx(demand_power_kw=200, pv_output_kw=150, rated_power_kw=120))
        assert d.pv_power_kw == 120
        assert d.curtailed

    def test_negative_demand_clamped_to_zero(self, s):
        d = s.evaluate(_ctx(demand_power_kw=-50, pv_output_kw=60))
        assert d.target_power_kw == 0
        assert not d.curtailed  # target(0) 不低于 demand(-50)


class TestSolarReasonAndSource:
    def test_reason_includes_pv_demand_target(self, s):
        d = s.evaluate(_ctx(demand_power_kw=40, pv_output_kw=60))
        assert "光伏优先" in d.reason
        assert "60.0kW" in d.reason  # pv
        assert "40.0kW" in d.reason  # demand & target

    def test_source_pv_when_charging(self, s):
        d = s.evaluate(_ctx(demand_power_kw=40, pv_output_kw=60))
        assert d.source == "pv"

    def test_source_none_when_zero(self, s):
        d = s.evaluate(_ctx(demand_power_kw=50, pv_output_kw=0))
        assert d.source == "none"
