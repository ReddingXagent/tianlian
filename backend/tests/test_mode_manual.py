"""test_mode_manual.py — ManualStrategy 手动充电模式单元测试

被测对象: app/services/charging/mode_manual.py 的 ManualStrategy。

纯逻辑测试(无 DB / 外部依赖;ChargingContext 为 dataclass, 直接构造)。
手动模式契约(用户直接指定功率, 策略不做自动调整):
- manual_power_kw is not None → target = clamp(manual_power_kw, rated), 来源"用户手动设定"
- manual_power_kw is None      → target = clamp(demand_power_kw, rated), 来源"按需求"
- curtailed 恒为 False(手动模式永不标记降功率)
- manual_power_kw = 0 属合法手动设定(非 None), 充 0 功率

注意: `is not None` 判断下, 0 与负数均视为"已设定手动功率", 走手动分支。
"""
import pytest

from app.services.charging.mode_manual import ManualStrategy
from app.services.charging.strategy_base import ChargingMode, ChargingContext


@pytest.fixture
def s():
    return ManualStrategy()


def _ctx(**kw):
    defaults = dict(station_id="s1", charger_id="c1", rated_power_kw=120, demand_power_kw=60)
    defaults.update(kw)
    return ChargingContext(**defaults)


class TestManualMeta:
    def test_mode(self, s):
        assert s.mode == ChargingMode.MANUAL

    def test_priority(self, s):
        assert s.priority == 1  # 手动模式优先级最高

    def test_get_mode(self, s):
        assert s.get_mode() == ChargingMode.MANUAL


class TestManualPowerSet:
    def test_uses_manual_power(self, s):
        d = s.evaluate(_ctx(manual_power_kw=50, demand_power_kw=80))
        assert d.grid_power_kw == 50
        assert d.target_power_kw == 50
        assert not d.curtailed

    def test_manual_overrides_demand(self, s):
        """手动功率优先于车辆需求。"""
        d = s.evaluate(_ctx(manual_power_kw=30, demand_power_kw=200))
        assert d.grid_power_kw == 30

    def test_manual_zero_is_valid(self, s):
        """manual_power_kw=0 属合法设定(is not None), 充 0 功率。"""
        d = s.evaluate(_ctx(manual_power_kw=0, demand_power_kw=80))
        assert d.grid_power_kw == 0
        assert d.target_power_kw == 0
        assert d.source == "none"
        assert "用户手动设定" in d.reason

    def test_manual_clamps_to_rated(self, s):
        d = s.evaluate(_ctx(manual_power_kw=200, rated_power_kw=120))
        assert d.grid_power_kw == 120
        assert d.target_power_kw == 120

    def test_manual_negative_clamped_to_zero(self, s):
        d = s.evaluate(_ctx(manual_power_kw=-30))
        assert d.grid_power_kw == 0
        assert d.target_power_kw == 0


class TestManualFallbackToDemand:
    def test_fallback_uses_demand(self, s):
        d = s.evaluate(_ctx(manual_power_kw=None, demand_power_kw=60))
        assert d.grid_power_kw == 60
        assert "按需求" in d.reason

    def test_demand_clamps_to_rated(self, s):
        d = s.evaluate(_ctx(manual_power_kw=None, demand_power_kw=200, rated_power_kw=120))
        assert d.grid_power_kw == 120

    def test_demand_negative_clamped_to_zero(self, s):
        d = s.evaluate(_ctx(manual_power_kw=None, demand_power_kw=-30))
        assert d.grid_power_kw == 0


class TestManualNeverCurtailed:
    def test_not_curtailed_when_manual(self, s):
        d = s.evaluate(_ctx(manual_power_kw=50, demand_power_kw=200))
        assert not d.curtailed  # 即便手动功率低于需求也不标记降功率

    def test_not_curtailed_when_fallback(self, s):
        d = s.evaluate(_ctx(manual_power_kw=None, demand_power_kw=200, rated_power_kw=120))
        assert not d.curtailed  # 被额定钳位也不标记降功率


class TestManualReasonAndSource:
    def test_reason_manual_includes_power(self, s):
        d = s.evaluate(_ctx(manual_power_kw=50))
        assert "手动模式" in d.reason
        assert "用户手动设定" in d.reason
        assert "50.0kW" in d.reason

    def test_reason_fallback_text(self, s):
        d = s.evaluate(_ctx(manual_power_kw=None, demand_power_kw=60))
        assert "按需求" in d.reason
        assert "60.0kW" in d.reason

    def test_source_grid_when_positive(self, s):
        d = s.evaluate(_ctx(manual_power_kw=50))
        assert d.source == "grid"
