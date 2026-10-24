"""test_mode_balanced.py — BalancedStrategy 均衡充电模式单元测试

被测对象: app/services/charging/mode_balanced.py 的 BalancedStrategy。

纯逻辑测试。能量优先级契约: 光伏 → 储能放电 → 电网兜底。
- 光伏按 min(剩余需求, 光伏出力) 消纳。
- 储能放电受 SOC 保护: soc is None 或 soc <= 0.15 时不放电。
- 电网兜底受 grid_power_limit_kw 上限约束(为 None 时不限)。
- 三源总和超过额定功率时按比例缩放各源。
"""
import pytest

from app.services.charging.mode_balanced import BalancedStrategy
from app.services.charging.strategy_base import ChargingMode, ChargingContext


@pytest.fixture
def s():
    return BalancedStrategy()


def _ctx(**kw):
    defaults = dict(station_id="s1", charger_id="c1", rated_power_kw=120, demand_power_kw=60)
    defaults.update(kw)
    return ChargingContext(**defaults)


class TestBalancedMeta:
    def test_mode(self, s):
        assert s.mode == ChargingMode.BALANCED

    def test_priority(self, s):
        assert s.priority == 5

    def test_get_mode(self, s):
        assert s.get_mode() == ChargingMode.BALANCED

    def test_discharge_soc_min_constant(self, s):
        assert s.BATTERY_DISCHARGE_SOC_MIN == 0.15


class TestBalancedEnergyPriority:
    def test_pv_covers_all_demand(self, s):
        d = s.evaluate(_ctx(demand_power_kw=40, pv_output_kw=60))
        assert d.pv_power_kw == 40
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 0
        assert d.target_power_kw == 40
        assert d.source == "pv"
        assert not d.curtailed

    def test_pv_then_battery_then_grid(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=100, pv_output_kw=40,
            battery_soc=0.8, battery_available_kw=30,
            grid_power_limit_kw=100,
        ))
        assert d.pv_power_kw == 40
        assert d.battery_power_kw == 30
        assert d.grid_power_kw == 30
        assert d.target_power_kw == 100
        assert d.source == "mixed"
        assert not d.curtailed

    def test_pv_surplus_not_used_beyond_demand(self, s):
        d = s.evaluate(_ctx(demand_power_kw=30, pv_output_kw=30, battery_soc=0.8))
        assert d.pv_power_kw == 30
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 0


class TestBatterySocProtection:
    def test_battery_skipped_when_soc_below_min(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=50, pv_output_kw=0,
            battery_soc=0.1, battery_available_kw=100,
            grid_power_limit_kw=100,
        ))
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 50

    def test_battery_skipped_when_soc_none(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=50, pv_output_kw=0,
            battery_soc=None, battery_available_kw=100,
            grid_power_limit_kw=100,
        ))
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 50

    def test_battery_at_exact_threshold_not_discharging(self, s):
        """soc == 0.15 不满足严格 > 0.15 → 不放电。"""
        d = s.evaluate(_ctx(
            demand_power_kw=50, pv_output_kw=0,
            battery_soc=0.15, battery_available_kw=100,
            grid_power_limit_kw=100,
        ))
        assert d.battery_power_kw == 0

    def test_battery_just_above_threshold_discharges(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=50, pv_output_kw=0,
            battery_soc=0.16, battery_available_kw=50,
            grid_power_limit_kw=100,
        ))
        assert d.battery_power_kw == 50

    def test_battery_capped_by_available_kw(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=100, pv_output_kw=0,
            battery_soc=0.8, battery_available_kw=30,
            grid_power_limit_kw=100,
        ))
        assert d.battery_power_kw == 30
        assert d.grid_power_kw == 70


class TestGridBackstop:
    def test_grid_respects_power_limit(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=100, pv_output_kw=0,
            battery_soc=None, grid_power_limit_kw=30,
        ))
        assert d.grid_power_kw == 30
        assert d.curtailed  # 30 < 100

    def test_grid_no_limit_when_none(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=50, pv_output_kw=0,
            battery_soc=None, grid_power_limit_kw=None,
        ))
        assert d.grid_power_kw == 50
        assert not d.curtailed

    def test_grid_zero_limit_curtailed(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=50, pv_output_kw=0,
            battery_soc=0.1, grid_power_limit_kw=0,
        ))
        assert d.target_power_kw == 0
        assert d.curtailed


class TestRatedClamping:
    def test_total_clamped_to_rated(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=200, pv_output_kw=100,
            battery_soc=0.8, battery_available_kw=100,
            rated_power_kw=120, grid_power_limit_kw=200,
        ))
        assert abs(d.target_power_kw - 120) < 1e-3

    def test_clamping_scales_each_source_proportionally(self, s):
        # 钳位前: pv=100, battery=50, grid=50(限200不限), total=200, scale=120/200=0.6
        d = s.evaluate(_ctx(
            demand_power_kw=200, pv_output_kw=100,
            battery_soc=0.8, battery_available_kw=50,
            rated_power_kw=120, grid_power_limit_kw=200,
        ))
        assert abs(d.pv_power_kw - 60) < 1e-3      # 100*0.6
        assert abs(d.battery_power_kw - 30) < 1e-3  # 50*0.6
        assert abs(d.grid_power_kw - 30) < 1e-3     # 50*0.6
        assert abs((d.pv_power_kw + d.battery_power_kw + d.grid_power_kw) - 120) < 1e-3


class TestCurtailedAndReason:
    def test_not_curtailed_when_demand_met(self, s):
        d = s.evaluate(_ctx(demand_power_kw=60, pv_output_kw=60))
        assert not d.curtailed

    def test_curtailed_when_grid_limit_cuts_demand(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=100, pv_output_kw=0,
            battery_soc=None, grid_power_limit_kw=30,
        ))
        assert d.curtailed

    def test_zero_demand_all_zero_not_curtailed(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=0, pv_output_kw=50,
            battery_soc=0.8, battery_available_kw=50,
        ))
        assert d.pv_power_kw == 0
        assert d.target_power_kw == 0
        assert d.source == "none"
        assert not d.curtailed

    def test_reason_contains_all_three_sources(self, s):
        d = s.evaluate(_ctx(
            demand_power_kw=100, pv_output_kw=40,
            battery_soc=0.8, battery_available_kw=30,
            grid_power_limit_kw=100,
        ))
        assert "均衡调度" in d.reason
        assert "光伏" in d.reason
        assert "储能" in d.reason
        assert "电网" in d.reason


class TestRatedPowerNone:
    def test_rated_power_none_does_not_raise(self, s):
        """rated_power_kw=None 时不抛 TypeError, 视为无钳位限制。

        链式比较 `total > ctx.rated_power_kw > 0` 在 Py3 对 None 求值抛
        TypeError: '>' not supported between 'float' and 'NoneType'。
        ChargingContext.rated_power_kw 类型注解虽为 float(非 Optional),
        但 dataclass 不做运行时类型校验, 调用方可能传 None。
        """
        d = s.evaluate(_ctx(
            demand_power_kw=60, pv_output_kw=60,
            rated_power_kw=None,
        ))
        # None → 不钳位, 光伏满供 60, 无降功率
        assert d.pv_power_kw == 60
        assert d.target_power_kw == 60
        assert not d.curtailed

    def test_rated_power_none_with_grid_backstop(self, s):
        """rated_power_kw=None + 电网兜底场景同样不抛, 不钳位。"""
        d = s.evaluate(_ctx(
            demand_power_kw=100, pv_output_kw=40,
            battery_soc=0.8, battery_available_kw=30,
            grid_power_limit_kw=100,
            rated_power_kw=None,
        ))
        # 三源 40+30+30=100, 无额定限制不缩放
        assert d.pv_power_kw == 40
        assert d.battery_power_kw == 30
        assert d.grid_power_kw == 30
        assert d.target_power_kw == 100

    def test_rated_power_zero_not_clamped(self, s):
        """rated_power_kw=0 (<=0) 也不应触发钳位除零/异常, 视为无限制。"""
        d = s.evaluate(_ctx(
            demand_power_kw=60, pv_output_kw=60,
            rated_power_kw=0,
        ))
        assert d.pv_power_kw == 60
        assert d.target_power_kw == 60
