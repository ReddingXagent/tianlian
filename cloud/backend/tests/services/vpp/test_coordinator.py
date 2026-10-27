"""
MultiStationCoordinator 单元测试 (services/vpp/test_coordinator.py)

被测文件: app/services/vpp/dispatch_optimizer/coordinator.py
聚焦 coordinator 层公开 API 的真实缺口 (现有 test_dispatch_optimizer.py 偏 optimizer 算法):
- 注册/注销 站点与资源 (含重复注册/不存在ID)
- update_*_status (不存在ID / 无效属性)
- get_aggregate_capacity (空 / 部分在线 / 全在线 + avg_soc 仅 battery)
- 四种 dispatch_* (正常落历史 + 异常降级 safe_plan)
- auto_dispatch 六条分支路由 (DR/EMERGENCY/peak/freq/multi/economic) + 异常降级
- _record_plan 计数器与 100 条上限
- get_dispatch_history limit 边界 (默认 / 0 / 负数 / 超大 / 顺序)
- simulate_station_data (计数封顶 / 资源配比)

设计要点:
- 纯内存模块, 无 DB / 外部依赖, 不依赖 tests/ 根的同名工厂
- 切片 bug 用例 (limit<=0) 先 RED 驱动 coordinator.py 修复
- auto_dispatch 分支用 sentinel plan + spy 替换 dispatch_* 方法, 解耦 optimizer 内部
"""
from __future__ import annotations

from datetime import datetime
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
)


# ─── 工厂 (自包含) ───

def _station(sid="ST-1", *, name=None, load=100.0, pv_out=80.0, available=200.0,
             total_pv=200.0, battery_kwh=500.0, ev=20, soc=0.6, online=True):
    return StationStatus(
        station_id=sid, station_name=name or f"N-{sid}",
        total_pv_kw=total_pv, total_battery_kwh=battery_kwh, total_ev_chargers=ev,
        current_load_kw=load, current_pv_output_kw=pv_out, current_battery_soc=soc,
        available_dispatch_kw=available, online=online,
    )


def _resource(rid="R-1", station_id="ST-1", *, rtype=ResourceType.BATTERY,
              rated=100.0, current=0.0, available=100.0, soc=None, priority=2):
    return ResourceCapability(
        resource_id=rid, resource_type=rtype, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        soc=soc, priority=priority,
    )


def _plan(pid="plan-1", mode=DispatchMode.ECONOMIC):
    """最小可用 DispatchPlan (供 _record_plan / history 测试)。"""
    return DispatchPlan(
        plan_id=pid, mode=mode, trigger="t", stations_involved=[],
        commands=[], total_dispatch_kw=1.0, estimated_revenue=2.0,
        estimated_cost=0.5, net_profit=1.5,
    )


def _sentinel(mode):
    """auto_dispatch 路由测试用的可识别空计划。"""
    return DispatchPlan(
        plan_id=f"sentinel_{mode.value}", mode=mode, trigger="spy",
        stations_involved=[], commands=[], total_dispatch_kw=0,
        estimated_revenue=0, estimated_cost=0, net_profit=0,
    )


def _signal(signal_type, **kw):
    base = {"timestamp": datetime.now()}
    base.update(kw)
    return GridSignal(signal_type=signal_type, **base)


# ═══════════════════════════════════════════════════════════
# 注册 / 注销 站点
# ═══════════════════════════════════════════════════════════

class TestRegisterStation:
    def test_register_adds_station(self):
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1"))
        assert "ST-1" in coord.stations
        assert coord.stations["ST-1"].station_name == "N-ST-1"

    def test_register_idempotent_overwrites(self):
        """重复注册同ID覆盖旧记录 (字典语义)。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1", name="old"))
        coord.register_station(_station("ST-1", name="new"))
        assert len(coord.stations) == 1
        assert coord.stations["ST-1"].station_name == "new"


class TestUnregisterStation:
    def test_unregister_removes_station(self):
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1"))
        coord.unregister_station("ST-1")
        assert "ST-1" not in coord.stations

    def test_unregister_nonexistent_id_silent(self):
        """注销不存在的ID不抛异常, 状态不变。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1"))
        coord.unregister_station("nope")  # 不抛
        assert "ST-1" in coord.stations
        assert coord.unregister_station("nope") is None

    def test_unregister_twice_silent(self):
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1"))
        coord.unregister_station("ST-1")
        coord.unregister_station("ST-1")  # 二次注销不抛
        assert coord.stations == {}


# ═══════════════════════════════════════════════════════════
# 注册 / 注销 资源
# ═══════════════════════════════════════════════════════════

class TestRegisterResource:
    def test_register_adds_resource(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1"))
        assert "R-1" in coord.resources

    def test_register_idempotent_overwrites(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1", rated=100))
        coord.register_resource(_resource("R-1", rated=200))
        assert len(coord.resources) == 1
        assert coord.resources["R-1"].rated_power_kw == 200


class TestUnregisterResource:
    def test_unregister_removes_resource(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1"))
        coord.unregister_resource("R-1")
        assert "R-1" not in coord.resources

    def test_unregister_nonexistent_id_silent(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1"))
        coord.unregister_resource("nope")
        assert "R-1" in coord.resources


# ═══════════════════════════════════════════════════════════
# update_*_status (不存在ID / 无效属性)
# ═══════════════════════════════════════════════════════════

class TestUpdateStationStatus:
    def test_update_valid_attribute(self):
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1", load=100, online=True))
        coord.update_station_status("ST-1", current_load_kw=250, online=False)
        assert coord.stations["ST-1"].current_load_kw == 250
        assert coord.stations["ST-1"].online is False

    def test_update_nonexistent_id_noop(self):
        """更新不存在的站点 → 无操作不抛。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1"))
        coord.update_station_status("nope", current_load_kw=999)
        assert coord.stations["ST-1"].current_load_kw == 100  # 未受影响

    def test_update_invalid_attribute_ignored(self):
        """无效属性 (hasattr=False) 静默忽略, 不创建新属性。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1"))
        coord.update_station_status("ST-1", bogus_field=42, current_load_kw=300)
        assert coord.stations["ST-1"].current_load_kw == 300
        assert not hasattr(coord.stations["ST-1"], "bogus_field")


class TestUpdateResourceStatus:
    def test_update_valid_attribute(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1", soc=0.6))
        coord.update_resource_status("R-1", soc=0.8, available_power_kw=50)
        assert coord.resources["R-1"].soc == 0.8
        assert coord.resources["R-1"].available_power_kw == 50

    def test_update_nonexistent_id_noop(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1", soc=0.6))
        coord.update_resource_status("nope", soc=0.1)
        assert coord.resources["R-1"].soc == 0.6

    def test_update_invalid_attribute_ignored(self):
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("R-1"))
        coord.update_resource_status("R-1", no_such_attr=1)
        assert not hasattr(coord.resources["R-1"], "no_such_attr")


# ═══════════════════════════════════════════════════════════
# get_aggregate_capacity (空 / 部分在线 / 全在线 + avg_soc)
# ═══════════════════════════════════════════════════════════

class TestGetAggregateCapacity:
    def test_empty_all_zero(self):
        coord = MultiStationCoordinator()
        agg = coord.get_aggregate_capacity()
        assert agg["online_stations"] == 0
        assert agg["total_stations"] == 0
        assert agg["total_pv_kw"] == 0
        assert agg["total_battery_kwh"] == 0
        assert agg["total_ev_chargers"] == 0
        assert agg["current_load_kw"] == 0
        assert agg["available_dispatch_kw"] == 0
        assert agg["avg_battery_soc"] == 0
        assert "timestamp" in agg

    def test_partial_online_excludes_offline(self):
        """离线站点的容量不计入聚合。"""
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1", load=100, pv_out=80, available=200,
                                        total_pv=200, battery_kwh=500, ev=20, online=True))
        coord.register_station(_station("ST-2", load=300, pv_out=150, available=400,
                                        total_pv=300, battery_kwh=600, ev=10, online=False))
        agg = coord.get_aggregate_capacity()
        assert agg["total_stations"] == 2
        assert agg["online_stations"] == 1
        # 仅在线 ST-1 计入
        assert agg["current_load_kw"] == 100
        assert agg["total_pv_kw"] == 200
        assert agg["total_battery_kwh"] == 500
        assert agg["total_ev_chargers"] == 20
        assert agg["available_dispatch_kw"] == 200

    def test_all_online_sums_correct(self):
        coord = MultiStationCoordinator()
        coord.register_station(_station("ST-1", load=100, pv_out=80, available=200, online=True))
        coord.register_station(_station("ST-2", load=150, pv_out=70, available=250, online=True))
        agg = coord.get_aggregate_capacity()
        assert agg["online_stations"] == 2
        assert agg["current_load_kw"] == 250
        assert agg["current_pv_output_kw"] == 150
        assert agg["available_dispatch_kw"] == 450

    def test_avg_battery_soc_only_battery_resources(self):
        """avg_battery_soc 仅统计 BATTERY 且 soc 非 None 的资源 (PV/EV/LOAD 排除)。"""
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("BAT-1", rtype=ResourceType.BATTERY, soc=0.6))
        coord.register_resource(_resource("BAT-2", rtype=ResourceType.BATTERY, soc=0.8))
        coord.register_resource(_resource("PV-1", rtype=ResourceType.PV, soc=0.99))      # 排除
        coord.register_resource(_resource("EV-1", rtype=ResourceType.EV_CHARGER, soc=0.5))  # 排除
        agg = coord.get_aggregate_capacity()
        assert agg["avg_battery_soc"] == pytest.approx(0.7, abs=1e-3)

    def test_avg_battery_soc_none_battery_zero(self):
        """battery 资源 soc 全 None → 不进分母, avg=0。"""
        coord = MultiStationCoordinator()
        coord.register_resource(_resource("BAT-1", rtype=ResourceType.BATTERY, soc=None))
        agg = coord.get_aggregate_capacity()
        assert agg["avg_battery_soc"] == 0


# ═══════════════════════════════════════════════════════════
# 四种 dispatch_* (正常落历史 + 异常降级)
# ═══════════════════════════════════════════════════════════

class TestDispatchNormalRecordsHistory:
    def setup_method(self):
        self.coord = MultiStationCoordinator()
        self.coord.register_station(_station("ST-1"))
        self.coord.register_resource(_resource("BAT-1", soc=0.7, available=80, rated=100))

    def test_dispatch_economic_records_plan(self):
        plan = self.coord.dispatch_economic()
        assert isinstance(plan, DispatchPlan)
        assert plan.mode == DispatchMode.ECONOMIC
        assert len(self.coord.dispatch_history) == 1
        assert self.coord._plan_counter == 1

    def test_dispatch_peak_shaving_records_plan(self):
        plan = self.coord.dispatch_peak_shaving()
        assert plan.mode == DispatchMode.PEAK_SHAVING
        assert len(self.coord.dispatch_history) == 1

    def test_dispatch_peak_shaving_updates_threshold(self):
        """传入 threshold_kw 时更新 peak_threshold_kw。"""
        assert self.coord.peak_threshold_kw == 500.0
        self.coord.dispatch_peak_shaving(threshold_kw=300.0)
        assert self.coord.peak_threshold_kw == 300.0

    def test_dispatch_demand_response_records_plan(self):
        sig = _signal(GridSignalType.DEMAND_RESPONSE, target_power_kw=50)
        plan = self.coord.dispatch_demand_response(sig)
        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        assert len(self.coord.dispatch_history) == 1

    def test_dispatch_multi_station_records_plan(self):
        plan = self.coord.dispatch_multi_station()
        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert len(self.coord.dispatch_history) == 1


class TestDispatchExceptionDegradesSafe:
    """optimizer 抛异常 → coordinator 层 _safe_plan, 不冒泡, 落历史。"""

    def setup_method(self):
        self.coord = MultiStationCoordinator()
        self.coord.register_station(_station("ST-1"))
        self.coord.optimizer = MagicMock()

    def _assert_safe(self, plan, mode):
        assert isinstance(plan, DispatchPlan)
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == mode
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_economic_exception_safe(self):
        self.coord.optimizer.optimize_economic_dispatch.side_effect = RuntimeError("boom")
        self._assert_safe(self.coord.dispatch_economic(), DispatchMode.ECONOMIC)
        assert len(self.coord.dispatch_history) == 0  # safe_plan 不落历史

    def test_peak_shaving_exception_safe(self):
        self.coord.optimizer.optimize_peak_shaving.side_effect = RuntimeError("boom")
        self._assert_safe(self.coord.dispatch_peak_shaving(), DispatchMode.PEAK_SHAVING)

    def test_demand_response_exception_safe(self):
        self.coord.optimizer.handle_demand_response.side_effect = RuntimeError("boom")
        sig = _signal(GridSignalType.DEMAND_RESPONSE, target_power_kw=50)
        self._assert_safe(self.coord.dispatch_demand_response(sig), DispatchMode.DEMAND_RESPONSE)

    def test_multi_station_exception_safe(self):
        self.coord.optimizer.optimize_multi_station_coordination.side_effect = RuntimeError("boom")
        self._assert_safe(self.coord.dispatch_multi_station(), DispatchMode.GRID_SUPPORT)


# ═══════════════════════════════════════════════════════════
# auto_dispatch 六条分支路由 + 异常降级
# ═══════════════════════════════════════════════════════════

class TestAutoDispatchRouting:
    """用 sentinel plan 替换 dispatch_* 方法, 断言分支路由命中正确方法。"""

    def _coord_with_spies(self):
        coord = MultiStationCoordinator()
        coord.dispatch_demand_response = MagicMock(return_value=_sentinel(DispatchMode.DEMAND_RESPONSE))
        coord.dispatch_peak_shaving = MagicMock(return_value=_sentinel(DispatchMode.PEAK_SHAVING))
        coord.dispatch_multi_station = MagicMock(return_value=_sentinel(DispatchMode.GRID_SUPPORT))
        coord.dispatch_economic = MagicMock(return_value=_sentinel(DispatchMode.ECONOMIC))
        return coord

    def test_demand_response_signal_routes_to_dr(self):
        coord = self._coord_with_spies()
        plan = coord.auto_dispatch(_signal(GridSignalType.DEMAND_RESPONSE, target_power_kw=50))
        coord.dispatch_demand_response.assert_called_once()
        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        coord.dispatch_peak_shaving.assert_not_called()

    def test_emergency_signal_routes_to_dr(self):
        coord = self._coord_with_spies()
        coord.auto_dispatch(_signal(GridSignalType.EMERGENCY, target_power_kw=50))
        coord.dispatch_demand_response.assert_called_once()

    def test_overload_routes_to_peak_shaving(self):
        """负荷超阈值 (无电网信号) → 削峰。"""
        coord = self._coord_with_spies()
        coord.register_station(_station("ST-1", load=600))  # > 500 阈值
        plan = coord.auto_dispatch(None)
        coord.dispatch_peak_shaving.assert_called_once()
        assert plan.mode == DispatchMode.PEAK_SHAVING

    def test_frequency_regulation_routes_to_multi_station(self):
        """调频信号 (负荷正常) → 多站点协同。"""
        coord = self._coord_with_spies()
        coord.register_station(_station("ST-1", load=100))  # < 阈值
        coord.auto_dispatch(_signal(GridSignalType.FREQUENCY_REGULATION))
        coord.dispatch_multi_station.assert_called_once()

    def test_multi_online_stations_routes_to_multi_station(self):
        """多站点 (>1) 且无信号无过载 → 多站点协同。"""
        coord = self._coord_with_spies()
        coord.register_station(_station("ST-1", load=100))
        coord.register_station(_station("ST-2", load=100))
        coord.auto_dispatch(None)
        coord.dispatch_multi_station.assert_called_once()

    def test_single_station_routes_to_economic(self):
        """单站点 + 无信号 + 无过载 → 经济调度 (兜底分支)。"""
        coord = self._coord_with_spies()
        coord.register_station(_station("ST-1", load=100))
        plan = coord.auto_dispatch(None)
        coord.dispatch_economic.assert_called_once()
        assert plan.mode == DispatchMode.ECONOMIC

    def test_auto_dispatch_exception_safe(self):
        """auto_dispatch 内部异常 (get_aggregate_capacity 抛) → _safe_plan(ECONOMIC)。"""
        coord = MultiStationCoordinator()
        coord.get_aggregate_capacity = MagicMock(side_effect=RuntimeError("boom"))
        plan = coord.auto_dispatch(None)
        assert plan.plan_id.startswith("safe_")
        assert plan.mode == DispatchMode.ECONOMIC


# ═══════════════════════════════════════════════════════════
# _record_plan 计数器与 100 条上限
# ═══════════════════════════════════════════════════════════

class TestRecordPlan:
    def test_counter_increments(self):
        coord = MultiStationCoordinator()
        assert coord._plan_counter == 0
        coord._record_plan(_plan("p1"))
        coord._record_plan(_plan("p2"))
        assert coord._plan_counter == 2
        assert len(coord.dispatch_history) == 2

    def test_history_capped_at_100_keeps_latest(self):
        """超过100条仅保留最近100条, counter 仍累加。"""
        coord = MultiStationCoordinator()
        for i in range(105):
            coord._record_plan(_plan(f"p{i:03d}"))
        assert coord._plan_counter == 105
        assert len(coord.dispatch_history) == 100
        # 保留 p005..p104 (最近100条)
        assert coord.dispatch_history[0].plan_id == "p005"
        assert coord.dispatch_history[-1].plan_id == "p104"

    def test_history_at_exactly_100_not_trimmed(self):
        """恰好100条不触发裁剪。"""
        coord = MultiStationCoordinator()
        for i in range(100):
            coord._record_plan(_plan(f"p{i:03d}"))
        assert len(coord.dispatch_history) == 100
        assert coord.dispatch_history[0].plan_id == "p000"


# ═══════════════════════════════════════════════════════════
# get_dispatch_history limit 边界 (默认 / 0 / 负数 / 超大 / 顺序)
# ═══════════════════════════════════════════════════════════

class TestGetDispatchHistoryLimit:
    def setup_method(self):
        self.coord = MultiStationCoordinator()
        # 直接灌入 5 条已知历史: p0(最旧) .. p4(最新)
        for i in range(5):
            self.coord.dispatch_history.append(_plan(f"p{i}"))

    def _ids(self, result):
        return [d["plan_id"] for d in result]

    def test_default_limit_returns_all_reversed(self):
        """默认 limit=20, 不足则全返回, 顺序最新在前。"""
        res = self.coord.get_dispatch_history()
        assert self._ids(res) == ["p4", "p3", "p2", "p1", "p0"]

    def test_limit_zero_returns_empty(self):
        """limit=0 → 空 (切片 bug: [-0:] 返回全部)。"""
        assert self.coord.get_dispatch_history(limit=0) == []

    def test_limit_negative_one_returns_empty(self):
        """limit=-1 → 空 (切片 bug: [-(-1):]=[1:] 错位返回4条)。"""
        assert self.coord.get_dispatch_history(limit=-1) == []

    def test_limit_negative_three_returns_empty(self):
        """limit=-3 → 空 (切片 bug: [-(-3):]=[3:] 错位返回2条)。"""
        assert self.coord.get_dispatch_history(limit=-3) == []

    def test_limit_within_range_returns_last_n_reversed(self):
        """limit=3 → 最近3条, 最新在前。"""
        res = self.coord.get_dispatch_history(limit=3)
        assert self._ids(res) == ["p4", "p3", "p2"]

    def test_limit_one_returns_latest(self):
        res = self.coord.get_dispatch_history(limit=1)
        assert self._ids(res) == ["p4"]

    def test_limit_larger_than_history_returns_all(self):
        """limit 超过历史总量 → 返回全部。"""
        res = self.coord.get_dispatch_history(limit=100)
        assert len(res) == 5

    def test_result_shape_and_rounding(self):
        """返回字典字段齐全, 数值 round 到2位。"""
        res = self.coord.get_dispatch_history(limit=1)
        d = res[0]
        assert set(d.keys()) == {
            "plan_id", "mode", "trigger", "stations_involved",
            "total_dispatch_kw", "estimated_revenue", "estimated_cost",
            "net_profit", "commands_count", "created_at", "executed",
        }
        assert d["total_dispatch_kw"] == 1.0
        assert d["commands_count"] == 0
        assert d["executed"] is False

    def test_empty_history_returns_empty(self):
        coord = MultiStationCoordinator()
        assert coord.get_dispatch_history() == []
        assert coord.get_dispatch_history(limit=5) == []


# ═══════════════════════════════════════════════════════════
# simulate_station_data
# ═══════════════════════════════════════════════════════════

class TestSimulateStationData:
    def test_default_count_creates_three_stations(self):
        coord = MultiStationCoordinator()
        coord.simulate_station_data()  # default count=3
        assert len(coord.stations) == 3
        assert {sid for sid in coord.stations} == {"ST-001", "ST-002", "ST-003"}

    def test_each_station_has_four_resources(self):
        """每站点注册 PV/BAT/EV/LOAD 共4类资源。"""
        coord = MultiStationCoordinator()
        coord.simulate_station_data(count=2)
        assert len(coord.resources) == 8  # 2 站 × 4 资源
        types_by_station = {}
        for r in coord.resources.values():
            types_by_station.setdefault(r.station_id, set()).add(r.resource_type)
        for sid, types in types_by_station.items():
            assert types == {ResourceType.PV, ResourceType.BATTERY,
                             ResourceType.EV_CHARGER, ResourceType.LOAD}

    def test_count_exceeds_configs_capped_at_five(self):
        """count > 配置数(5) → 封顶5站点。"""
        coord = MultiStationCoordinator()
        coord.simulate_station_data(count=99)
        assert len(coord.stations) == 5
        assert len(coord.resources) == 20

    def test_count_zero_creates_nothing(self):
        coord = MultiStationCoordinator()
        coord.simulate_station_data(count=0)
        assert coord.stations == {}
        assert coord.resources == {}

    def test_battery_resources_have_soc(self):
        """模拟的储能资源 soc 落在生成区间 [0.2, 0.9]。"""
        coord = MultiStationCoordinator()
        coord.simulate_station_data(count=1)
        bat = coord.resources["ST-001-BAT"]
        assert bat.resource_type == ResourceType.BATTERY
        assert 0.2 <= bat.soc <= 0.9
