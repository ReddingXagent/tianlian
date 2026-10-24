"""
VPPOptimizer / MultiStationCoordinator 单元测试

被测文件: app/services/vpp/dispatch_optimizer.py

设计要点:
- 纯逻辑模块, 无 DB / 外部依赖, 不需要 MagicMock(db)
- 价格相关测试一律传显式 hour 参数, 保证确定性 (不依赖 datetime.now())
- 涉及 optimize_economic_dispatch / optimize_multi_station_coordination 内部
  使用 datetime.now() 取价的方法, 用 monkeypatch 固定 get_current_price 返回值
"""
from unittest.mock import MagicMock

import pytest

from app.services.vpp.dispatch_optimizer import (
    ResourceType,
    DispatchMode,
    GridSignalType,
    ResourceCapability,
    GridSignal,
    StationStatus,
    DispatchCommand,
    DispatchPlan,
    VPPOptimizer,
    MultiStationCoordinator,
    get_vpp_coordinator,
)
from datetime import datetime


# ─── 工厂函数 ───

def make_battery(rid="BAT-1", station_id="ST-1", *, rated=100, available=100,
                 soc=0.6, priority=2, current=0):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.BATTERY, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        soc=soc, priority=priority,
    )


def make_ev(rid="EV-1", station_id="ST-1", *, rated=120, current=60, available=30, priority=3):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.EV_CHARGER, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def make_load(rid="LOAD-1", station_id="ST-1", *, rated=50, available=20, priority=4, current=15):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.LOAD, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def make_pv(rid="PV-1", station_id="ST-1", *, rated=200, current=100, available=100, priority=5):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.PV, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def make_station(sid="ST-1", name="S1", *, pv=200, battery=500, ev=20, load=100,
                 pv_out=80, soc=0.6, available=200, online=True):
    return StationStatus(
        station_id=sid, station_name=name, total_pv_kw=pv, total_battery_kwh=battery,
        total_ev_chargers=ev, current_load_kw=load, current_pv_output_kw=pv_out,
        current_battery_soc=soc, available_dispatch_kw=available, online=online,
    )


# ═══════════════════════════════════════════════════════════
# VPPOptimizer — get_current_price 边界
# ═══════════════════════════════════════════════════════════

class TestGetCurrentPrice:
    def setup_method(self):
        self.opt = VPPOptimizer()

    def test_peak_window(self):
        # 10:00-12:00 尖峰
        assert self.opt.get_current_price(10.0) == pytest.approx(self.opt.PEAK_PRICE)
        assert self.opt.get_current_price(11.5) == pytest.approx(self.opt.PEAK_PRICE)

    def test_high_window_morning_and_evening(self):
        assert self.opt.get_current_price(8.0) == pytest.approx(self.opt.HIGH_PRICE)
        assert self.opt.get_current_price(9.99) == pytest.approx(self.opt.HIGH_PRICE)
        assert self.opt.get_current_price(18.0) == pytest.approx(self.opt.HIGH_PRICE)
        assert self.opt.get_current_price(20.99) == pytest.approx(self.opt.HIGH_PRICE)

    def test_valley_window_late_and_early(self):
        assert self.opt.get_current_price(23.0) == pytest.approx(self.opt.VALLEY_PRICE)
        assert self.opt.get_current_price(2.0) == pytest.approx(self.opt.VALLEY_PRICE)
        assert self.opt.get_current_price(5.99) == pytest.approx(self.opt.VALLEY_PRICE)

    def test_flat_window(self):
        # 6-8, 12-18, 21-23 平段
        assert self.opt.get_current_price(6.0) == pytest.approx(self.opt.FLAT_PRICE)
        assert self.opt.get_current_price(12.0) == pytest.approx(self.opt.FLAT_PRICE)
        assert self.opt.get_current_price(21.0) == pytest.approx(self.opt.FLAT_PRICE)

    def test_multiplier_scales_price(self):
        opt = VPPOptimizer(config={"price_multiplier": 2.0})
        assert opt.get_current_price(11.0) == pytest.approx(self.opt.PEAK_PRICE * 2.0)
        assert opt.get_current_price(3.0) == pytest.approx(self.opt.VALLEY_PRICE * 2.0)

    def test_config_overrides_reward_rates(self):
        opt = VPPOptimizer(config={"dr_reward_rate": 0.8, "frequency_reg_reward": 0.2})
        assert opt.dr_reward_rate == 0.8
        assert opt.frequency_reg_reward == 0.2
        # 未提供的项保留默认
        assert opt.price_multiplier == 1.0


# ═══════════════════════════════════════════════════════════
# VPPOptimizer — 单资源优化 (确定性, 显式价格)
# ═══════════════════════════════════════════════════════════

class TestOptimizeSingleResource:
    def setup_method(self):
        self.opt = VPPOptimizer()

    def test_battery_charges_in_valley(self):
        # 谷电 + soc 未满 → 充电 (target_power 负)
        bat = make_battery(soc=0.3)
        cmd = self.opt._optimize_battery(bat, self.opt.VALLEY_PRICE, hour=2.0)
        assert cmd is not None
        assert cmd.target_power_kw < 0
        assert cmd.estimated_cost > 0
        assert cmd.estimated_revenue == 0
        assert cmd.resource_type == ResourceType.BATTERY

    def test_battery_discharges_at_high_price(self):
        # 高电价 + soc 充足 → 放电
        bat = make_battery(soc=0.6)
        cmd = self.opt._optimize_battery(bat, self.opt.HIGH_PRICE, hour=19.0)
        assert cmd is not None
        assert cmd.target_power_kw > 0
        assert cmd.estimated_revenue > 0

    def test_battery_skip_discharge_when_soc_too_low(self):
        # soc <= BATTERY_SOC_MIN+0.1=0.20, 高价也不放电; 且非谷电不充电 → None
        bat = make_battery(soc=0.15)
        cmd = self.opt._optimize_battery(bat, self.opt.HIGH_PRICE, hour=19.0)
        assert cmd is None

    def test_battery_no_action_at_flat_price(self):
        # 平段电价: 既不满足谷电充电, 也不满足高价放电 → None
        bat = make_battery(soc=0.5)
        cmd = self.opt._optimize_battery(bat, self.opt.FLAT_PRICE, hour=13.0)
        assert cmd is None

    def test_battery_soc_none_treated_as_half(self):
        # soc=None 时按 0.5 处理, 谷电可充电
        bat = make_battery(soc=None)
        bat.soc = None
        cmd = self.opt._optimize_battery(bat, self.opt.VALLEY_PRICE, hour=3.0)
        assert cmd is not None and cmd.target_power_kw < 0

    def test_ev_charger_curtail_at_high_price(self):
        ev = make_ev(current=60)
        cmd = self.opt._optimize_ev_charger(ev, self.opt.HIGH_PRICE, hour=19.0)
        assert cmd is not None
        # 降功率50% → 负方向 curtail
        assert cmd.target_power_kw == pytest.approx(-30.0)
        assert cmd.estimated_revenue > 0

    def test_ev_charger_no_curtail_at_low_price(self):
        ev = make_ev(current=60)
        cmd = self.opt._optimize_ev_charger(ev, self.opt.VALLEY_PRICE, hour=3.0)
        assert cmd is None

    def test_ev_charger_no_curtail_when_idle(self):
        # current_power_kw=0 时即使高价也不动作
        ev = make_ev(current=0)
        cmd = self.opt._optimize_ev_charger(ev, self.opt.HIGH_PRICE, hour=19.0)
        assert cmd is None

    def test_load_curtail_at_peak_price(self):
        load = make_load(available=20)
        cmd = self.opt._optimize_load(load, self.opt.PEAK_PRICE, hour=11.0)
        assert cmd is not None
        # 削减30% → 负方向
        assert cmd.target_power_kw == pytest.approx(-6.0)
        assert cmd.estimated_cost > 0

    def test_load_no_curtail_below_peak(self):
        load = make_load(available=20)
        # 高峰价(< 尖峰)不削减负荷
        cmd = self.opt._optimize_load(load, self.opt.HIGH_PRICE, hour=19.0)
        assert cmd is None

    def test_single_resource_dispatches_pv_returns_none(self):
        cmd = self.opt._optimize_single_resource(make_pv(), self.opt.PEAK_PRICE, 11.0)
        assert cmd is None

    def test_single_resource_routes_by_type(self):
        # 验证 _optimize_single_resource 按类型分发
        bat_cmd = self.opt._optimize_single_resource(
            make_battery(soc=0.6), self.opt.HIGH_PRICE, 19.0)
        assert bat_cmd is not None and bat_cmd.resource_type == ResourceType.BATTERY


# ═══════════════════════════════════════════════════════════
# VPPOptimizer — 经济调度
# ═══════════════════════════════════════════════════════════

class TestEconomicDispatch:
    def test_plan_structure_and_priority_sort(self, monkeypatch):
        opt = VPPOptimizer()
        # 固定电价为高峰 → 储能放电
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        stations = [make_station()]
        resources = [
            make_battery(rid="B1", priority=3, soc=0.7),
            make_battery(rid="B2", priority=1, soc=0.7),
        ]
        plan = opt.optimize_economic_dispatch(stations, resources)
        assert isinstance(plan, DispatchPlan)
        assert plan.mode == DispatchMode.ECONOMIC
        assert plan.plan_id.startswith("eco_")
        assert len(plan.commands) == 2
        # 按优先级升序: B2(1) 在前
        assert plan.commands[0].resource_id == "B2"
        assert plan.net_profit == pytest.approx(plan.estimated_revenue - plan.estimated_cost)

    def test_valley_price_charges_batteries(self, monkeypatch):
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.VALLEY_PRICE)
        plan = opt.optimize_economic_dispatch([make_station()], [make_battery(soc=0.3)])
        assert len(plan.commands) == 1
        assert plan.commands[0].target_power_kw < 0  # 充电

    def test_flat_price_no_commands(self, monkeypatch):
        opt = VPPOptimizer()
        # 平段 + 高SOC → 既不充也不放
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.FLAT_PRICE)
        plan = opt.optimize_economic_dispatch([make_station()], [make_battery(soc=0.6)])
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_aggregates_by_station(self, monkeypatch):
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        stations = [make_station("ST-A"), make_station("ST-B")]
        resources = [
            make_battery(rid="A-BAT", station_id="ST-A", soc=0.7),
            make_battery(rid="B-BAT", station_id="ST-B", soc=0.7),
        ]
        plan = opt.optimize_economic_dispatch(stations, resources)
        assert set(plan.stations_involved) == {"ST-A", "ST-B"}


# ═══════════════════════════════════════════════════════════
# VPPOptimizer — 削峰填谷
# ═══════════════════════════════════════════════════════════

class TestPeakShaving:
    def test_no_overload_returns_empty_plan(self):
        opt = VPPOptimizer()
        # 负荷 < 阈值
        stations = [make_station(load=100)]
        plan = opt.optimize_peak_shaving(stations, [], peak_threshold_kw=500)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "负荷正常" in plan.trigger

    def test_overload_discharges_battery(self):
        opt = VPPOptimizer()
        stations = [make_station(load=600)]  # overload=100
        bat = make_battery(soc=0.6, available=80, rated=80)
        plan = opt.optimize_peak_shaving(stations, [bat], peak_threshold_kw=500)
        assert len(plan.commands) == 1
        assert plan.commands[0].target_power_kw > 0  # 放电为正
        assert plan.commands[0].resource_type == ResourceType.BATTERY

    def test_low_soc_battery_skipped(self):
        opt = VPPOptimizer()
        stations = [make_station(load=600)]
        # soc=0.15 < 0.20 → 跳过; 无其他资源 → 无命令
        bat = make_battery(soc=0.15, available=80, rated=80)
        plan = opt.optimize_peak_shaving(stations, [bat], peak_threshold_kw=500)
        assert plan.commands == []

    def test_load_curtail_when_battery_insufficient(self):
        opt = VPPOptimizer()
        stations = [make_station(load=700)]  # overload=200
        bat = make_battery(soc=0.6, available=50, rated=50)  # 储能不足
        load = make_load(available=100)
        plan = opt.optimize_peak_shaving(stations, [bat, load], peak_threshold_kw=500)
        # 至少有一条负荷削减 (负 target)
        curtails = [c for c in plan.commands if c.resource_type == ResourceType.LOAD]
        assert len(curtails) >= 1
        assert all(c.target_power_kw < 0 for c in curtails)

    def test_offline_station_excluded_from_load_sum(self):
        opt = VPPOptimizer()
        stations = [make_station(load=1000, online=False), make_station("ST-2", load=100)]
        plan = opt.optimize_peak_shaving(stations, [], peak_threshold_kw=500)
        # 离线站不计入 → 总负荷100 < 500 → 正常
        assert plan.commands == []


# ═══════════════════════════════════════════════════════════
# VPPOptimizer — 需求响应
# ═══════════════════════════════════════════════════════════

class TestDemandResponse:
    def _signal(self, target=200, duration=30, reward=None):
        return GridSignal(
            signal_type=GridSignalType.DEMAND_RESPONSE,
            timestamp=datetime.now(), target_power_kw=target,
            duration_min=duration, reward_per_kwh=reward,
        )

    def test_target_zero_no_commands(self):
        opt = VPPOptimizer()
        sig = self._signal(target=0)
        plan = opt.handle_demand_response([make_station()], [], sig)
        assert plan.commands == []
        assert "0.0%" in plan.trigger  # response_rate 0

    def test_battery_priority_before_ev_and_load(self):
        opt = VPPOptimizer()
        sig = self._signal(target=200)
        resources = [
            make_battery(rid="BAT", available=200, rated=200, soc=0.7),
            make_ev(rid="EV", current=60),
            make_load(rid="LOAD", available=50),
        ]
        plan = opt.handle_demand_response([make_station()], resources, sig)
        # 储能单独满足目标 → 仅1条命令
        assert len(plan.commands) == 1
        assert plan.commands[0].resource_id == "BAT"

    def test_partial_response_when_capacity_insufficient(self):
        opt = VPPOptimizer()
        sig = self._signal(target=1000)
        resources = [make_battery(available=100, rated=100, soc=0.7)]
        plan = opt.handle_demand_response([make_station()], resources, sig)
        assert len(plan.commands) == 1
        # response_rate < 100%
        assert "100.0%" not in plan.trigger

    def test_low_soc_battery_skipped_falls_to_ev(self):
        opt = VPPOptimizer()
        sig = self._signal(target=60)
        # 储能 soc 太低(< 0.25) → 跳过, 由充电桩 curtail
        resources = [
            make_battery(available=100, soc=0.2),
            make_ev(rid="EV", current=60),
        ]
        plan = opt.handle_demand_response([make_station()], resources, sig)
        ids = [c.resource_id for c in plan.commands]
        assert "BAT" not in ids
        assert "EV" in ids

    def test_uses_signal_reward_when_provided(self):
        opt = VPPOptimizer()
        sig = self._signal(target=100, reward=0.9)
        resources = [make_battery(available=100, rated=100, soc=0.7)]
        plan = opt.handle_demand_response([make_station()], resources, sig)
        # revenue = 100 * 0.9 * 30/60 = 45
        assert plan.commands[0].estimated_revenue == pytest.approx(45.0)


# ═══════════════════════════════════════════════════════════
# VPPOptimizer — 多站点协同
# ═══════════════════════════════════════════════════════════

class TestMultiStationCoordination:
    def test_export_station_supplies_import_station(self, monkeypatch):
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        # ST-A 余量 (pv_out - load + available > 0), ST-B 缺电
        export = make_station("ST-A", load=50, pv_out=200, available=100)   # surplus=250
        importer = make_station("ST-B", load=300, pv_out=50, available=0)   # surplus=-200
        bat = make_battery(rid="A-BAT", station_id="ST-A", available=100, soc=0.7)
        plan = opt.optimize_multi_station_coordination([export, importer], [bat])
        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert plan.plan_id.startswith("coord_")
        # 应有从 ST-A 储能放电的指令
        assert any(c.station_id == "ST-A" and c.target_power_kw > 0 for c in plan.commands)

    def test_grid_signal_extends_commands(self, monkeypatch):
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        sig = GridSignal(signal_type=GridSignalType.DEMAND_RESPONSE,
                         timestamp=datetime.now(), target_power_kw=100, duration_min=30)
        stations = [make_station("ST-A"), make_station("ST-B")]
        resources = [make_battery(rid="BAT", station_id="ST-A", available=100, soc=0.7)]
        plan = opt.optimize_multi_station_coordination(stations, resources, sig)
        # 包含需求响应产生的指令
        assert len(plan.commands) >= 1

    def test_low_price_charges_remaining_batteries(self, monkeypatch):
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.VALLEY_PRICE)
        stations = [make_station("ST-A", load=10, pv_out=10, available=0)]  # 平衡, 无互济
        bat = make_battery(rid="BAT", station_id="ST-A", available=50, soc=0.3)
        plan = opt.optimize_multi_station_coordination(stations, [bat])
        # 低电价 → 储能充电 (负 target)
        charge = [c for c in plan.commands if c.target_power_kw < 0]
        assert len(charge) >= 1


# ═══════════════════════════════════════════════════════════
# MultiStationCoordinator
# ═══════════════════════════════════════════════════════════

class TestMultiStationCoordinator:
    def test_register_unregister_station(self):
        coord = MultiStationCoordinator()
        s = make_station("ST-X")
        coord.register_station(s)
        assert "ST-X" in coord.stations
        coord.unregister_station("ST-X")
        assert "ST-X" not in coord.stations
        # 注销不存在的站点不报错
        coord.unregister_station("nope")

    def test_register_unregister_resource(self):
        coord = MultiStationCoordinator()
        r = make_battery(rid="R1")
        coord.register_resource(r)
        assert "R1" in coord.resources
        coord.unregister_resource("R1")
        assert "R1" not in coord.resources
        coord.unregister_resource("nope")  # 不报错

    def test_update_station_status_only_known_attrs(self):
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1", load=100))
        coord.update_station_status("ST-1", current_load_kw=300, bogus_field=999)
        assert coord.stations["ST-1"].current_load_kw == 300
        # 不存在的站点 → 静默忽略
        coord.update_station_status("nope", current_load_kw=1)

    def test_update_resource_status(self):
        coord = MultiStationCoordinator()
        coord.register_resource(make_battery(rid="R1", soc=0.5))
        coord.update_resource_status("R1", soc=0.9)
        assert coord.resources["R1"].soc == 0.9

    def test_aggregate_capacity_math(self):
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1", pv=100, battery=200, ev=4, load=50,
                                            pv_out=70, available=80))
        coord.register_station(make_station("ST-2", pv=200, battery=400, ev=6, load=80,
                                            pv_out=140, available=160))
        coord.register_resource(make_battery(rid="B1", station_id="ST-1", soc=0.6))
        coord.register_resource(make_battery(rid="B2", station_id="ST-2", soc=0.8))
        agg = coord.get_aggregate_capacity()
        assert agg["online_stations"] == 2
        assert agg["total_stations"] == 2
        assert agg["total_pv_kw"] == 300
        assert agg["total_battery_kwh"] == 600
        assert agg["total_ev_chargers"] == 10
        assert agg["current_load_kw"] == 130
        assert agg["available_dispatch_kw"] == 240
        assert agg["avg_battery_soc"] == pytest.approx(0.7, abs=0.001)

    def test_aggregate_excludes_offline_and_no_battery_soc(self):
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1", online=False, pv=100, battery=200, load=10))
        coord.register_station(make_station("ST-2", pv=50, battery=100, load=20))
        # 无 BATTERY 资源 → avg_soc=0
        agg = coord.get_aggregate_capacity()
        assert agg["online_stations"] == 1
        assert agg["total_pv_kw"] == 50  # 离线不计
        assert agg["avg_battery_soc"] == 0


# ═══════════════════════════════════════════════════════════
# MultiStationCoordinator — auto_dispatch 决策树
# ═══════════════════════════════════════════════════════════

class TestAutoDispatch:
    def _coord_with_stations(self, n=2, load=100):
        coord = MultiStationCoordinator()
        for i in range(n):
            coord.register_station(make_station(f"ST-{i}", load=load))
        return coord

    def test_demand_response_signal_triggers_dr(self):
        coord = self._coord_with_stations()
        sig = GridSignal(signal_type=GridSignalType.DEMAND_RESPONSE,
                         timestamp=datetime.now(), target_power_kw=100)
        coord.dispatch_demand_response = MagicMock(return_value="DR")
        assert coord.auto_dispatch(sig) == "DR"
        coord.dispatch_demand_response.assert_called_once_with(sig)

    def test_emergency_signal_triggers_dr(self):
        coord = self._coord_with_stations()
        sig = GridSignal(signal_type=GridSignalType.EMERGENCY,
                         timestamp=datetime.now(), target_power_kw=100)
        coord.dispatch_demand_response = MagicMock(return_value="DR")
        assert coord.auto_dispatch(sig) == "DR"

    def test_overload_triggers_peak_shaving(self):
        coord = self._coord_with_stations(n=1, load=600)
        coord.peak_threshold_kw = 500
        coord.dispatch_peak_shaving = MagicMock(return_value="PS")
        assert coord.auto_dispatch(None) == "PS"

    def test_frequency_regulation_triggers_multi_station(self):
        coord = self._coord_with_stations()
        sig = GridSignal(signal_type=GridSignalType.FREQUENCY_REGULATION, timestamp=datetime.now())
        coord.dispatch_multi_station = MagicMock(return_value="MS")
        assert coord.auto_dispatch(sig) == "MS"
        coord.dispatch_multi_station.assert_called_once_with(sig)

    def test_multi_station_when_more_than_one_online(self):
        coord = self._coord_with_stations(n=2, load=10)  # 无过载
        coord.dispatch_multi_station = MagicMock(return_value="MS")
        assert coord.auto_dispatch(None) == "MS"

    def test_single_station_falls_back_to_economic(self):
        coord = self._coord_with_stations(n=1, load=10)
        coord.dispatch_economic = MagicMock(return_value="ECO")
        assert coord.auto_dispatch(None) == "ECO"


# ═══════════════════════════════════════════════════════════
# MultiStationCoordinator — 历史与模拟
# ═══════════════════════════════════════════════════════════

class TestHistoryAndSimulate:
    def test_dispatch_records_history(self, monkeypatch):
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1"))
        coord.register_resource(make_battery(rid="B1", station_id="ST-1", soc=0.7))
        monkeypatch.setattr(coord.optimizer, "get_current_price", lambda hour=None: 0.9)
        plan = coord.dispatch_economic()
        assert coord._plan_counter == 1
        assert len(coord.dispatch_history) == 1
        hist = coord.get_dispatch_history()
        assert len(hist) == 1
        assert hist[0]["plan_id"] == plan.plan_id
        assert hist[0]["mode"] == plan.mode.value

    def test_dispatch_peak_shaving_updates_threshold(self):
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1", load=100))
        coord.dispatch_peak_shaving(threshold_kw=800)
        assert coord.peak_threshold_kw == 800

    def test_history_capped_at_100(self, monkeypatch):
        coord = MultiStationCoordinator()
        plan = DispatchPlan(plan_id="x", mode=DispatchMode.ECONOMIC, trigger="t",
                            stations_involved=[], commands=[], total_dispatch_kw=0,
                            estimated_revenue=0, estimated_cost=0, net_profit=0)
        for i in range(120):
            coord._record_plan(plan)
        assert len(coord.dispatch_history) == 100

    def test_get_dispatch_history_limit_and_order(self):
        coord = MultiStationCoordinator()
        for i in range(5):
            coord._record_plan(DispatchPlan(
                plan_id=f"p{i}", mode=DispatchMode.ECONOMIC, trigger="t",
                stations_involved=[], commands=[], total_dispatch_kw=0,
                estimated_revenue=0, estimated_cost=0, net_profit=0))
        # 默认 limit=20, 反序 (最新在前)
        hist = coord.get_dispatch_history(limit=3)
        assert len(hist) == 3
        assert hist[0]["plan_id"] == "p4"

    def test_simulate_station_data_populates(self):
        coord = MultiStationCoordinator()
        coord.simulate_station_data(count=3)
        assert len(coord.stations) == 3
        # 每站注册 4 类资源 (PV/BAT/EV/LOAD)
        assert len(coord.resources) == 12
        agg = coord.get_aggregate_capacity()
        assert agg["online_stations"] == 3


# ═══════════════════════════════════════════════════════════
# 单例
# ═══════════════════════════════════════════════════════════

class TestSingleton:
    def test_get_vpp_coordinator_returns_same_instance(self, monkeypatch):
        import app.services.vpp.dispatch_optimizer as mod
        monkeypatch.setattr(mod, "_coordinator", None)
        # 避免随机模拟数据影响: 直接验证两次调用同对象
        c1 = get_vpp_coordinator()
        c2 = get_vpp_coordinator()
        assert c1 is c2
        assert isinstance(c1, MultiStationCoordinator)


# ═══════════════════════════════════════════════════════════
# 健壮性 / 异常处理 / 并发安全 (缺陷修复验收)
# ═══════════════════════════════════════════════════════════

class TestEdgeCasesAndResilience:
    def test_empty_resources_dispatch(self):
        """空资源列表调度不崩溃, 各模式均返回安全空计划"""
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1"))
        # 不注册任何资源
        plan = coord.dispatch_economic()
        assert isinstance(plan, DispatchPlan)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        # 其他调度模式同样不崩溃
        assert isinstance(coord.dispatch_peak_shaving(), DispatchPlan)
        sig = GridSignal(signal_type=GridSignalType.DEMAND_RESPONSE,
                         timestamp=datetime.now(), target_power_kw=100)
        assert isinstance(coord.dispatch_demand_response(sig), DispatchPlan)
        assert isinstance(coord.dispatch_multi_station(), DispatchPlan)
        assert isinstance(coord.auto_dispatch(), DispatchPlan)

    def test_none_value_handling(self, monkeypatch):
        """None/坏数据字段传入不崩溃, 降级返回安全空计划"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        # available_power_kw=None 会让 min(None, x) 抛 TypeError
        bad_bat = make_battery(rid="B1", soc=0.7)
        bad_bat.available_power_kw = None
        plan = opt.optimize_economic_dispatch([make_station()], [bad_bat])
        assert isinstance(plan, DispatchPlan)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

        # coordinator 层同样降级 (异常不冒泡到调用方)
        coord = MultiStationCoordinator(optimizer=opt)
        coord.register_station(make_station("ST-1"))
        bad_bat2 = make_battery(rid="B2", station_id="ST-1", soc=0.7)
        bad_bat2.available_power_kw = None
        coord.register_resource(bad_bat2)
        plan2 = coord.dispatch_economic()
        assert isinstance(plan2, DispatchPlan)
        assert plan2.commands == []

    def test_concurrent_dispatch(self):
        """并发调度线程安全: 多线程 register/dispatch 不崩溃且计数一致"""
        from concurrent.futures import ThreadPoolExecutor
        coord = MultiStationCoordinator()
        coord.register_station(make_station("ST-1", load=10))
        coord.register_resource(make_battery(rid="B1", station_id="ST-1", soc=0.7))

        errors = []
        N = 50
        expected_plans = 4 * N  # 4 个 dispatch worker, 各 N 次

        def dispatch_worker():
            try:
                for _ in range(N):
                    plan = coord.dispatch_economic()
                    assert isinstance(plan, DispatchPlan), "dispatch 必须返回 DispatchPlan"
            except Exception as e:
                errors.append(("dispatch", repr(e)))

        def mutate_worker():
            try:
                for i in range(N):
                    sid = f"ST-T{i % 5}"
                    coord.register_station(make_station(sid, load=float(i)))
                    coord.register_resource(
                        make_battery(rid=f"B{i % 5}", station_id=sid, soc=0.7))
                    coord.update_station_status(sid, current_load_kw=float(i))
                    coord.update_resource_status(f"B{i % 5}", soc=0.6)
                    coord.get_aggregate_capacity()
                    coord.unregister_resource(f"B{i % 5}")
                    coord.unregister_station(sid)
            except Exception as e:
                errors.append(("mutate", repr(e)))

        # 缩短 GIL 切换间隔放大竞态: 无锁时 _record_plan 的 += 必丢更新,
        # 且 list(dict.values()) 在并发增删时必抛 RuntimeError
        import sys
        orig_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = [ex.submit(dispatch_worker) for _ in range(4)]
                futures += [ex.submit(mutate_worker) for _ in range(4)]
                for f in futures:
                    f.result()
        finally:
            sys.setswitchinterval(orig_interval)

        assert errors == [], f"并发调度出现异常: {errors}"
        assert coord._plan_counter == expected_plans, (
            f"_record_plan 计数不一致(期望 {expected_plans}, "
            f"实际 {coord._plan_counter}), 缺少锁保护导致丢失更新"
        )


# ─── 放电 SOC 下限动态校验 + EV 削减比例可配 (任务4) ───

class TestBatteryDischargeFloor:
    def test_default_floor_blocks_low_soc_discharge(self):
        """默认放电下限 0.20: soc=0.18 + 峰价 → None(回归保护)"""
        opt = VPPOptimizer()
        bat = make_battery(soc=0.18)
        assert opt._optimize_battery(bat, opt.HIGH_PRICE, hour=19.0) is None

    def test_config_higher_floor_blocks_discharge(self):
        """config 放电下限 0.40: soc=0.35(>默认0.20) + 峰价 → None"""
        opt = VPPOptimizer(config={'battery_discharge_soc_floor': 0.40})
        bat = make_battery(soc=0.35)
        assert opt._optimize_battery(bat, opt.HIGH_PRICE, hour=19.0) is None

    def test_config_higher_floor_allows_above(self):
        """config 放电下限 0.40: soc=0.55 → 仍允许放电"""
        opt = VPPOptimizer(config={'battery_discharge_soc_floor': 0.40})
        bat = make_battery(soc=0.55)
        cmd = opt._optimize_battery(bat, opt.HIGH_PRICE, hour=19.0)
        assert cmd is not None and cmd.target_power_kw > 0

    def test_floor_clamped_to_soc_min(self):
        """config 设 0.05 → 实际 clamp 到 BATTERY_SOC_MIN(0.10), 不低于绝对地板"""
        opt = VPPOptimizer(config={'battery_discharge_soc_floor': 0.05})
        assert opt._battery_discharge_soc_floor == 0.10


class TestEvCurtailConfig:
    def test_default_ratio_half(self):
        """默认 EV_CURTAILMENT_RATIO=0.5(回归保护)"""
        opt = VPPOptimizer()
        ev = make_ev(current=60)
        cmd = opt._optimize_ev_charger(ev, opt.HIGH_PRICE, hour=19.0)
        assert cmd.target_power_kw == pytest.approx(-30.0)

    def test_config_override_ratio(self):
        """config ev_curtailment_ratio=0.3 → curtail 60*0.3=18"""
        opt = VPPOptimizer(config={'ev_curtailment_ratio': 0.3})
        ev = make_ev(current=60)
        cmd = opt._optimize_ev_charger(ev, opt.HIGH_PRICE, hour=19.0)
        assert cmd.target_power_kw == pytest.approx(-18.0)
