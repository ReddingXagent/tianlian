"""
VPPOptimizer / MultiStationCoordinator 补充单元测试 (services/vpp 目录)

被测文件: app/services/vpp/dispatch_optimizer.py

聚焦 (现有 tests/test_dispatch_optimizer.py 未覆盖的真实缺口):
- get_current_price 异常降级 (price_multiplier 坏值 → FLAT_PRICE)
- _optimize_single_resource 完整路由 (现有仅覆盖 BATTERY 分支, 补 EV/LOAD/PV)
- SOC 精确边界 0 与 1
- 任务 Edge Cases: 空输入 / 零功率 / 超大额定功率 / 零电价 / 爬坡速率=0
- 异常降级路径 (optimize_* 与 coordinator 层 try/except → 安全空计划)
- 空历史 / 空站点聚合容量
- get_vpp_coordinator 单例并发安全 (双重检查锁)

设计要点:
- 纯逻辑模块, 无 DB / 外部依赖
- 价格相关测试用 monkeypatch 固定 get_current_price, 消除 datetime 不确定性
"""
from __future__ import annotations

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from app.services.vpp.dispatch_optimizer import (
    DispatchMode,
    DispatchPlan,
    GridSignal,
    GridSignalType,
    MultiStationCoordinator,
    ResourceCapability,
    ResourceType,
    StationStatus,
    VPPOptimizer,
    get_vpp_coordinator,
)


# ─── 工厂函数 (自包含, 不依赖 tests/ 根的同名工厂) ───

def _battery(rid="BAT-1", station_id="ST-1", *, rated=100.0, current=0.0,
             available=100.0, soc=0.6, priority=2, efficiency=0.95, ramp=100.0):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.BATTERY, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        soc=soc, priority=priority, efficiency=efficiency, ramp_rate_kw_per_min=ramp,
    )


def _ev(rid="EV-1", station_id="ST-1", *, rated=120.0, current=60.0,
        available=30.0, priority=3):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.EV_CHARGER, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def _load(rid="LOAD-1", station_id="ST-1", *, rated=50.0, current=15.0,
          available=20.0, priority=4):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.LOAD, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def _pv(rid="PV-1", station_id="ST-1", *, rated=200.0, current=100.0,
        available=100.0, priority=5):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.PV, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def _station(sid="ST-1", *, load=100.0, pv_out=80.0, available=200.0, online=True):
    return StationStatus(
        station_id=sid, station_name="S-" + sid, total_pv_kw=200, total_battery_kwh=500,
        total_ev_chargers=20, current_load_kw=load, current_pv_output_kw=pv_out,
        current_battery_soc=0.6, available_dispatch_kw=available, online=online,
    )


# ═══════════════════════════════════════════════════════════
# get_current_price 异常降级
# ═══════════════════════════════════════════════════════════

class TestGetCurrentPriceDegradation:
    """get_current_price 的 except 降级路径 (line 191-193)。"""

    def test_bad_multiplier_falls_back_to_flat_price(self):
        """price_multiplier 非数值 → 乘法抛 TypeError → except 返回 FLAT_PRICE (不乘 multiplier)。"""
        opt = VPPOptimizer(config={"price_multiplier": "not-a-number"})
        # 无论传入哪个时段, 异常都会被 except 捕获降级为平段电价
        assert opt.get_current_price(11.0) == pytest.approx(opt.FLAT_PRICE)
        assert opt.get_current_price(3.0) == pytest.approx(opt.FLAT_PRICE)


# ═══════════════════════════════════════════════════════════
# _optimize_single_resource 完整路由
# ═══════════════════════════════════════════════════════════

class TestSingleResourceRouting:
    """_optimize_single_resource 按类型路由的完整分支 (现有仅覆盖 BATTERY)。"""

    def setup_method(self):
        self.opt = VPPOptimizer()

    def test_routes_ev_charger_to_ev_optimizer(self):
        """EV_CHARGER → _optimize_ev_charger, 高峰降功率 50%。"""
        cmd = self.opt._optimize_single_resource(_ev(current=60), self.opt.HIGH_PRICE, 19.0)
        assert cmd is not None
        assert cmd.resource_type == ResourceType.EV_CHARGER
        assert cmd.target_power_kw == pytest.approx(-30.0)

    def test_routes_load_to_load_optimizer(self):
        """LOAD → _optimize_load, 尖峰削减 30%。"""
        cmd = self.opt._optimize_single_resource(_load(available=20), self.opt.PEAK_PRICE, 11.0)
        assert cmd is not None
        assert cmd.resource_type == ResourceType.LOAD
        assert cmd.target_power_kw == pytest.approx(-6.0)

    def test_routes_pv_returns_none(self):
        """PV → 光伏不调度, 返回 None。"""
        assert self.opt._optimize_single_resource(_pv(), self.opt.PEAK_PRICE, 11.0) is None

    def test_battery_routing_produces_command(self):
        """BATTERY 路由 → _optimize_battery 产指令 (高峰放电)。"""
        cmd = self.opt._optimize_single_resource(_battery(soc=0.7), self.opt.HIGH_PRICE, 19.0)
        assert cmd is not None and cmd.resource_type == ResourceType.BATTERY
        assert cmd.target_power_kw > 0


# ═══════════════════════════════════════════════════════════
# SOC 精确边界 (0, 1)
# ═══════════════════════════════════════════════════════════

class TestBatterySocBoundaries:
    """储能 SOC 精确边界值 0 与 1 的调度决策。"""

    def setup_method(self):
        self.opt = VPPOptimizer()

    def test_soc_zero_charges_in_valley(self):
        """soc=0 (< SOC_MAX=0.95) 谷电可充电。"""
        cmd = self.opt._optimize_battery(_battery(soc=0.0), self.opt.VALLEY_PRICE, 3.0)
        assert cmd is not None
        assert cmd.target_power_kw < 0

    def test_soc_zero_no_discharge_at_high_price(self):
        """soc=0 (<= SOC_MIN+0.1=0.20) 高价也不放电, 且非谷电不充电 → None。"""
        cmd = self.opt._optimize_battery(_battery(soc=0.0), self.opt.HIGH_PRICE, 19.0)
        assert cmd is None

    def test_soc_full_discharges_at_high_price(self):
        """soc=1.0 (> SOC_MIN+0.1) 高价可放电。"""
        cmd = self.opt._optimize_battery(_battery(soc=1.0), self.opt.HIGH_PRICE, 19.0)
        assert cmd is not None
        assert cmd.target_power_kw > 0

    def test_soc_full_no_charge_in_valley(self):
        """soc=1.0 (>= SOC_MAX=0.95) 谷电也不再充电。"""
        cmd = self.opt._optimize_battery(_battery(soc=1.0), self.opt.VALLEY_PRICE, 3.0)
        assert cmd is None


# ═══════════════════════════════════════════════════════════
# 任务 Edge Cases
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    """任务要求的 Edge Cases: 空输入 / 零功率 / 超大功率 / 零电价 / 爬坡=0。"""

    def test_empty_stations_and_resources_all_modes_safe(self, monkeypatch):
        """空站点 + 空资源, 四种调度模式均返回安全 DispatchPlan 不崩溃。"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        assert isinstance(opt.optimize_economic_dispatch([], []), DispatchPlan)
        assert isinstance(opt.optimize_peak_shaving([], [], 500), DispatchPlan)
        sig = GridSignal(signal_type=GridSignalType.DEMAND_RESPONSE,
                         timestamp=datetime.now(), target_power_kw=100)
        assert isinstance(opt.handle_demand_response([], [], sig), DispatchPlan)
        assert isinstance(opt.optimize_multi_station_coordination([], []), DispatchPlan)

    def test_zero_available_power_battery(self):
        """available_power_kw=0 的电池谷电充电得 0 功率指令 (不崩溃, min(rated,0)=0)。"""
        opt = VPPOptimizer()
        cmd = opt._optimize_battery(_battery(available=0.0, rated=100.0),
                                    opt.VALLEY_PRICE, 3.0)
        assert cmd is not None
        assert cmd.target_power_kw == 0

    def test_huge_rated_power_no_overflow(self, monkeypatch):
        """超大额定功率 (1e9 kW) 经济调度不溢出, 产出满功率放电指令。"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)
        bat = _battery(rated=1e9, available=1e9, soc=0.8)
        plan = opt.optimize_economic_dispatch([_station()], [bat])
        assert len(plan.commands) == 1
        assert plan.commands[0].target_power_kw == pytest.approx(1e9)

    def test_zero_price_economic_dispatch_zero_cost(self, monkeypatch):
        """电价=0 经济调度不崩溃, 谷电充电成本 = charge * 0 = 0。"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: 0.0)
        plan = opt.optimize_economic_dispatch([_station()], [_battery(soc=0.3)])
        assert len(plan.commands) == 1
        assert plan.commands[0].target_power_kw < 0  # 充电
        assert plan.commands[0].estimated_cost == 0

    def test_zero_ramp_rate_resource_dispatches(self):
        """爬坡速率=0 的资源可正常创建并参与削峰调度 (不参与算术约束)。"""
        bat = _battery(ramp=0.0, soc=0.6)
        assert bat.ramp_rate_kw_per_min == 0.0
        opt = VPPOptimizer()
        plan = opt.optimize_peak_shaving([_station(load=600)], [bat], 500)
        assert isinstance(plan, DispatchPlan)
        assert any(c.resource_type == ResourceType.BATTERY for c in plan.commands)


# ═══════════════════════════════════════════════════════════
# 异常降级路径 (现有未覆盖的 except 分支)
# ═══════════════════════════════════════════════════════════

class TestExceptionDegradation:
    """optimize_* 与 coordinator 层的 try/except → 安全空计划路径。"""

    def test_economic_impl_exception_returns_safe_plan(self, monkeypatch):
        """_optimize_single_resource 抛异常 → 外层 try 捕获 → _safe_default_plan。"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "get_current_price", lambda hour=None: opt.HIGH_PRICE)

        def boom(*a, **kw):
            raise RuntimeError("injected")

        monkeypatch.setattr(opt, "_optimize_single_resource", boom)
        plan = opt.optimize_economic_dispatch([_station()], [_battery()])
        assert isinstance(plan, DispatchPlan)
        assert plan.plan_id.startswith("safe_")
        assert plan.commands == []
        assert "异常降级" in plan.trigger

    def test_peak_shaving_impl_exception_returns_safe_plan(self, monkeypatch):
        """_optimize_peak_shaving_impl 抛异常 → _safe_default_plan(PEAK_SHAVING)。"""
        opt = VPPOptimizer()

        def boom(*a, **kw):
            raise RuntimeError("injected")

        monkeypatch.setattr(opt, "_optimize_peak_shaving_impl", boom)
        plan = opt.optimize_peak_shaving([_station()], [], 500)
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.PEAK_SHAVING

    def test_demand_response_impl_exception_returns_safe_plan(self, monkeypatch):
        """_handle_demand_response_impl 抛异常 → _safe_default_plan(DEMAND_RESPONSE)。"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "_handle_demand_response_impl",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x")))
        sig = GridSignal(signal_type=GridSignalType.DEMAND_RESPONSE,
                         timestamp=datetime.now(), target_power_kw=100)
        plan = opt.handle_demand_response([_station()], [], sig)
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.DEMAND_RESPONSE

    def test_multi_station_impl_exception_returns_safe_plan(self, monkeypatch):
        """_optimize_multi_station_coordination_impl 抛异常 → _safe_default_plan(GRID_SUPPORT)。"""
        opt = VPPOptimizer()
        monkeypatch.setattr(opt, "_optimize_multi_station_coordination_impl",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x")))
        plan = opt.optimize_multi_station_coordination([_station()], [])
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.GRID_SUPPORT

    def test_coordinator_dispatch_exception_returns_safe_plan(self):
        """coordinator 层 optimizer 抛异常 → _safe_plan, 异常不冒泡到调用方。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station())
        coord.optimizer = MagicMock()
        coord.optimizer.optimize_economic_dispatch.side_effect = RuntimeError("boom")
        plan = coord.dispatch_economic()
        assert plan.plan_id.startswith("safe_")
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_coordinator_auto_dispatch_exception_returns_safe_plan(self):
        """auto_dispatch 内部抛异常 → _safe_plan(ECONOMIC)。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station())
        coord.get_aggregate_capacity = MagicMock(side_effect=RuntimeError("boom"))
        plan = coord.auto_dispatch(None)
        assert plan.plan_id.startswith("safe_")


# ═══════════════════════════════════════════════════════════
# 空历史 / 空站点聚合
# ═══════════════════════════════════════════════════════════

class TestEmptyHistoryAndAggregate:
    """dispatch_history 为空 / 无站点时的聚合容量与历史查询。"""

    def test_empty_dispatch_history_returns_empty_list(self):
        """新 coordinator 无调度历史 → get_dispatch_history 返回 []。"""
        coord = MultiStationCoordinator()
        assert coord.get_dispatch_history() == []
        assert coord.get_dispatch_history(limit=5) == []

    def test_aggregate_capacity_no_stations_all_zero(self):
        """无站点 → 全 0 容量, avg_battery_soc=0。"""
        coord = MultiStationCoordinator()
        agg = coord.get_aggregate_capacity()
        assert agg["online_stations"] == 0
        assert agg["total_stations"] == 0
        assert agg["total_pv_kw"] == 0
        assert agg["available_dispatch_kw"] == 0
        assert agg["avg_battery_soc"] == 0

    def test_get_dispatch_history_exception_returns_empty(self):
        """get_dispatch_history 异常 (dispatch_history 切片抛) → 降级返回空列表。"""
        coord = MultiStationCoordinator()
        coord.dispatch_history = MagicMock()
        coord.dispatch_history.__getitem__.side_effect = RuntimeError("boom")
        assert coord.get_dispatch_history() == []


# ═══════════════════════════════════════════════════════════
# 单例并发安全
# ═══════════════════════════════════════════════════════════

class TestCoordinatorSingleton:
    """get_vpp_coordinator 单例 + 双重检查锁并发验收。"""

    def test_singleton_returns_same_instance(self, monkeypatch):
        """两次调用返回同一实例。"""
        import app.services.vpp.dispatch_optimizer as mod
        monkeypatch.setattr(mod, "_coordinator", None)
        c1 = get_vpp_coordinator()
        c2 = get_vpp_coordinator()
        assert c1 is c2

    def test_concurrent_get_returns_single_instance(self, monkeypatch):
        """多线程并发首次调用 → 双重检查锁 → 全部拿到同一实例。"""
        import app.services.vpp.dispatch_optimizer as mod
        monkeypatch.setattr(mod, "_coordinator", None)
        results = []
        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = [ex.submit(get_vpp_coordinator) for _ in range(50)]
            for f in futures:
                results.append(f.result())
        assert len(set(id(r) for r in results)) == 1
