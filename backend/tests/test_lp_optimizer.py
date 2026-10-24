"""
VPPLPOptimizer 单元测试
覆盖：4种模式目标函数、约束构建(SOC/功率/等式)、_filter_dispatchable 全分支、
_result_to_plan 方向与收益、_fallback_dispatch 4模式、_empty_plan、单例、
optimize_dispatch 正常/边界/异常/回退、_solve_lp 内部逻辑。

设计要点：
- base_optimizer 用 MagicMock 固定电价(0.9)与谷价(0.3)，消除 datetime 依赖
- scipy.linprog 用 patch 隔离，返回 SimpleNamespace 模拟求解结果
- 不触碰 DB；不修改源文件
"""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.vpp import lp_optimizer as lp_mod
from app.services.vpp.dispatch_optimizer import (
    DispatchMode,
    DispatchPlan,
    GridSignalType,
    ResourceType,
    ResourceCapability,
    StationStatus,
)
from app.services.vpp.lp_optimizer import (
    HAS_SCIPY,
    LPOptimizationResult,
    VPPLPOptimizer,
    get_vpp_lp_optimizer,
)

PRICE = 0.9
VALLEY = 0.3
SOC_MIN = 0.10
SOC_MAX = 0.95


def make_resource(rid, rtype, *, station_id="ST-001", rated=100.0, current=0.0,
                  available=100.0, soc=None, efficiency=0.95, ramp=100.0, priority=5,
                  _soc_default=True):
    # _soc_default=False allows passing soc=None explicitly for filter tests
    actual_soc = 0.5 if (_soc_default and soc is None) else soc
    return ResourceCapability(
        resource_id=rid, resource_type=rtype, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        soc=actual_soc, efficiency=efficiency,
        ramp_rate_kw_per_min=ramp, priority=priority,
    )


def make_station(sid="ST-001", online=True):
    return StationStatus(
        station_id=sid, station_name="station-" + sid, total_pv_kw=200,
        total_battery_kwh=500, total_ev_chargers=10, current_load_kw=100,
        current_pv_output_kw=120, current_battery_soc=0.7,
        available_dispatch_kw=200, online=online,
    )


def make_base_mock(price=PRICE, discharge_floor=0.20):
    # spec 同时暴露类常量(BATTERY_DISCHARGE_SOC_FLOOR)与 config 可覆盖 property
    # (_battery_discharge_soc_floor): 真实 VPPOptimizer 两者都有, 这样可在旧/新实现下
    # 分别读到不同值, 用以回归 "LP 过滤是否改用 property" 的 bug。
    m = MagicMock(spec=["get_current_price", "VALLEY_PRICE", "BATTERY_SOC_MIN",
                        "BATTERY_SOC_MAX", "BATTERY_DISCHARGE_SOC_FLOOR",
                        "_battery_discharge_soc_floor",
                        "optimize_economic_dispatch", "optimize_peak_shaving",
                        "handle_demand_response", "optimize_multi_station_coordination"])
    m.get_current_price.return_value = price
    m.VALLEY_PRICE = VALLEY
    m.BATTERY_SOC_MIN = SOC_MIN
    m.BATTERY_SOC_MAX = SOC_MAX
    m.BATTERY_DISCHARGE_SOC_FLOOR = 0.20  # 类常量(旧实现读这个), 与基座对齐
    m._battery_discharge_soc_floor = discharge_floor  # property(新实现读这个), 默认等于类常量
    m.optimize_economic_dispatch.return_value = DispatchPlan(
        plan_id="fb-eco", mode=DispatchMode.ECONOMIC, trigger="eco",
        stations_involved=[], commands=[], total_dispatch_kw=0,
        estimated_revenue=0, estimated_cost=0, net_profit=0)
    m.optimize_peak_shaving.return_value = DispatchPlan(
        plan_id="fb-ps", mode=DispatchMode.PEAK_SHAVING, trigger="ps",
        stations_involved=[], commands=[], total_dispatch_kw=0,
        estimated_revenue=0, estimated_cost=0, net_profit=0)
    m.handle_demand_response.return_value = DispatchPlan(
        plan_id="fb-dr", mode=DispatchMode.DEMAND_RESPONSE, trigger="dr",
        stations_involved=[], commands=[], total_dispatch_kw=0,
        estimated_revenue=0, estimated_cost=0, net_profit=0)
    m.optimize_multi_station_coordination.return_value = DispatchPlan(
        plan_id="fb-ms", mode=DispatchMode.GRID_SUPPORT, trigger="ms",
        stations_involved=[], commands=[], total_dispatch_kw=0,
        estimated_revenue=0, estimated_cost=0, net_profit=0)
    return m


def lp_ok(x, message="optimal"):
    return SimpleNamespace(success=True, x=np.array(x, dtype=float), message=message)


def lp_fail(message="infeasible"):
    return SimpleNamespace(success=False, x=np.array([], dtype=float), message=message)


def new_optimizer(price=PRICE):
    return VPPLPOptimizer(base_optimizer=make_base_mock(price))


# ─── _filter_dispatchable ───

DISCHARGE_CASES = [
    ("BAT-ok", ResourceType.BATTERY, dict(soc=0.8, available=100), True),
    ("BAT-low-soc", ResourceType.BATTERY, dict(soc=0.15, available=100), False),
    ("BAT-zero-power", ResourceType.BATTERY, dict(soc=0.8, available=0), False),
    ("BAT-none-soc", ResourceType.BATTERY, dict(soc=None, available=100, _soc_default=False), False),
    ("PV-ok", ResourceType.PV, dict(available=120), True),
    ("PV-zero", ResourceType.PV, dict(available=0), False),
    ("EV-ok", ResourceType.EV_CHARGER, dict(current=60), True),
    ("EV-zero", ResourceType.EV_CHARGER, dict(current=0), False),
]


@pytest.mark.parametrize("rid,rtype,kw,included", DISCHARGE_CASES,
                         ids=[c[0] for c in DISCHARGE_CASES])
def test_filter_dispatchable_discharge(rid, rtype, kw, included):
    opt = new_optimizer()
    r = make_resource(rid, rtype, **kw)
    out = opt._filter_dispatchable([r], discharge=True)
    assert (r in out) is included


CHARGE_CASES = [
    ("BAT-chargeable", ResourceType.BATTERY, dict(soc=0.5, rated=100), True),
    ("BAT-full", ResourceType.BATTERY, dict(soc=0.95, rated=100), False),  # 达 BATTERY_SOC_MAX(0.95) 不可充
    ("BAT-zero-rated", ResourceType.BATTERY, dict(soc=0.5, rated=0), False),
    ("PV-not-charge", ResourceType.PV, dict(available=100), False),
    ("EV-not-charge", ResourceType.EV_CHARGER, dict(current=60), False),
]


@pytest.mark.parametrize("rid,rtype,kw,included", CHARGE_CASES,
                         ids=[c[0] for c in CHARGE_CASES])
def test_filter_dispatchable_charge(rid, rtype, kw, included):
    opt = new_optimizer()
    r = make_resource(rid, rtype, **kw)
    out = opt._filter_dispatchable([r], discharge=False)
    assert (r in out) is included


def test_filter_dispatchable_mixed_keeps_order():
    opt = new_optimizer()
    r_ok = make_resource("BAT1", ResourceType.BATTERY, soc=0.8, available=100)
    r_no = make_resource("BAT2", ResourceType.BATTERY, soc=0.1, available=100)
    r_pv = make_resource("PV1", ResourceType.PV, available=50)
    out = opt._filter_dispatchable([r_ok, r_no, r_pv], discharge=True)
    assert out == [r_ok, r_pv]


def test_filter_dispatchable_discharge_floor_aligns_with_base_constant():
    """放电门槛引用 base_optimizer._battery_discharge_soc_floor(property, 默认0.20), 与基座策略一致。

    边界为严格大于: soc==floor 不可放电, soc>floor 可放电。
    """
    opt = new_optimizer()
    at_floor = make_resource("F", ResourceType.BATTERY, soc=0.20, available=100)
    above_floor = make_resource("A", ResourceType.BATTERY, soc=0.21, available=100)
    assert at_floor not in opt._filter_dispatchable([at_floor], discharge=True)
    assert above_floor in opt._filter_dispatchable([above_floor], discharge=True)


# ─── _build_objective ───

def test_build_objective_economic_discharge():
    opt = new_optimizer(price=0.9)
    res = [make_resource("BAT", ResourceType.BATTERY, efficiency=0.95),
           make_resource("PV", ResourceType.PV),
           make_resource("EV", ResourceType.EV_CHARGER, current=60)]
    c = opt._build_objective(res, [100.0, 100.0, 30.0], is_discharge=True,
                             mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    np.testing.assert_allclose(c, [-0.57, -0.81, -0.45])


def test_build_objective_economic_charge():
    opt = new_optimizer(price=0.9)
    res = [make_resource("BAT-hi", ResourceType.BATTERY, efficiency=0.95),
           make_resource("BAT-lo", ResourceType.BATTERY, efficiency=0.80)]
    c = opt._build_objective(res, [100.0, 100.0], is_discharge=False,
                             mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    np.testing.assert_allclose(c, [0.9 * 1.05, 0.9 * 1.20])


def test_build_objective_peak_shaving():
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, efficiency=0.95),
           make_resource("EV", ResourceType.EV_CHARGER, current=60),
           make_resource("PV", ResourceType.PV)]
    c = opt._build_objective(res, [100.0, 30.0, 100.0], is_discharge=True,
                             mode=DispatchMode.PEAK_SHAVING, dr_reward=0.5)
    np.testing.assert_allclose(c, [0.05, 0.3, 0.1])


def test_build_objective_demand_response():
    opt = new_optimizer()
    res = [make_resource("BAT-a", ResourceType.BATTERY, efficiency=0.95),
           make_resource("BAT-b", ResourceType.BATTERY, efficiency=0.80)]
    c = opt._build_objective(res, [100.0, 100.0], is_discharge=True,
                             mode=DispatchMode.DEMAND_RESPONSE, dr_reward=0.5)
    np.testing.assert_allclose(c, [-0.475, -0.40])


def test_build_objective_grid_support():
    opt = new_optimizer()
    res = [make_resource("F", ResourceType.BATTERY, ramp=100),
           make_resource("S", ResourceType.BATTERY, ramp=200)]
    c = opt._build_objective(res, [100.0, 100.0], is_discharge=True,
                             mode=DispatchMode.GRID_SUPPORT, dr_reward=0.5)
    np.testing.assert_allclose(c, [1 / 101, 1 / 201])
    assert c[0] > c[1]  # faster ramp → lower coefficient


def test_build_objective_default_mode_maximizes_power():
    opt = new_optimizer()
    res = [make_resource("A", ResourceType.BATTERY), make_resource("B", ResourceType.PV)]
    c = opt._build_objective(res, [100.0, 100.0], is_discharge=True,
                             mode=DispatchMode.EMERGENCY, dr_reward=0.5)
    np.testing.assert_allclose(c, [-1.0, -1.0])


def test_build_objective_returns_numpy_array_of_correct_length():
    opt = new_optimizer()
    res = [make_resource("R0", ResourceType.PV), make_resource("R1", ResourceType.PV),
           make_resource("R2", ResourceType.PV)]
    c = opt._build_objective(res, [10.0, 20.0, 30.0], is_discharge=True,
                             mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert isinstance(c, np.ndarray)
    assert c.shape == (3,)


# ─── _build_inequality_constraints ───

def test_build_inequality_discharge_with_battery_soc_rows():
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.8, rated=100, available=100),
           make_resource("PV", ResourceType.PV, available=50)]
    A_ub, b_ub = opt._build_inequality_constraints(
        res, [100.0, 50.0], required_power=200, duration_min=15, is_discharge=True)
    assert A_ub.shape == (2, 2)
    np.testing.assert_allclose(A_ub[0], [1, 1])
    np.testing.assert_allclose(b_ub[0], 200 * 1.1)
    np.testing.assert_allclose(A_ub[1], [1, 0])
    np.testing.assert_allclose(b_ub[1], 100.0)


def test_build_inequality_charge_has_no_soc_rows():
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.5, rated=100)]
    A_ub, b_ub = opt._build_inequality_constraints(
        res, [100.0], required_power=80, duration_min=15, is_discharge=False)
    assert A_ub.shape == (1, 1)
    np.testing.assert_allclose(b_ub, [80 * 1.1])


def test_build_inequality_soc_limits_power_when_low_soc():
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.2, rated=100, available=100)]
    A_ub, b_ub = opt._build_inequality_constraints(
        res, [100.0], required_power=500, duration_min=15, is_discharge=True)
    np.testing.assert_allclose(b_ub[1], 80.0)


# ─── _build_equality_constraints ───

def test_build_equality_constraints_sufficient_capacity():
    opt = new_optimizer()
    A_eq, b_eq = opt._build_equality_constraints([100.0, 100.0], required_power=150)
    assert A_eq is not None and b_eq is not None
    np.testing.assert_allclose(A_eq, [[1, 1]])
    np.testing.assert_allclose(b_eq, [150])


def test_build_equality_constraints_caps_at_95_percent():
    opt = new_optimizer()
    # total_avail=200, required=210 → 200 >= 210*0.9=189 → cap at 200*0.95=190
    A_eq, b_eq = opt._build_equality_constraints([100.0, 100.0], required_power=210)
    np.testing.assert_allclose(b_eq, [190])


def test_build_equality_constraints_respects_90_percent_floor():
    """total_avail 略高于 90% 阈值时, b_eq 不应跌破需求 90% 下限。

    回归: 旧实现 b_eq=min(req, total_avail*0.95), 当 total_avail∈[0.9, 0.9474)*req 时
    b_eq 落到 90% 以下, 违反 "允许10%偏差" 的下限语义。
    例: avail=189, req=210 → 旧 b_eq=179.55(85.5%); 修复后 b_eq=189(90%)。
    """
    opt = new_optimizer()
    A_eq, b_eq = opt._build_equality_constraints([189.0], required_power=210)
    assert A_eq is not None and b_eq is not None
    assert b_eq[0] >= 210 * 0.9  # 不低于90%下限
    np.testing.assert_allclose(b_eq, [189.0])


def test_build_equality_constraints_insufficient_returns_none():
    opt = new_optimizer()
    A_eq, b_eq = opt._build_equality_constraints([10.0], required_power=100)
    assert A_eq is None and b_eq is None


# ─── _result_to_plan ───

def test_result_to_plan_discharge_directions_and_revenue():
    opt = new_optimizer(price=0.9)
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1", efficiency=0.95),
           make_resource("EV", ResourceType.EV_CHARGER, station_id="S2", current=100)]
    result = LPOptimizationResult(
        success=True, site_allocations=[("BAT", 100.0), ("EV", 100.0)],
        total_power_kw=200.0, solve_time_ms=1.0, solver_status="optimal", message="ok")
    plan = opt._result_to_plan(result, res, [make_station("S1"), make_station("S2")],
                               DispatchMode.ECONOMIC, duration_min=15, is_discharge=True)
    assert len(plan.commands) == 2
    by_id = dict((c.resource_id, c) for c in plan.commands)
    assert by_id["BAT"].target_power_kw == 100.0
    assert by_id["BAT"].estimated_revenue == pytest.approx(14.25)
    assert by_id["BAT"].estimated_cost == 0
    assert by_id["EV"].target_power_kw == -100.0
    assert by_id["EV"].estimated_revenue == 0
    assert by_id["EV"].estimated_cost == pytest.approx(22.5)
    assert plan.total_dispatch_kw == pytest.approx(200.0)
    assert plan.net_profit == pytest.approx(14.25 - 22.5)
    assert set(plan.stations_involved) == set(["S1", "S2"])


def test_result_to_plan_charge_direction_negative_power():
    opt = new_optimizer(price=0.9)
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1", efficiency=0.95)]
    result = LPOptimizationResult(
        success=True, site_allocations=[("BAT", 80.0)], total_power_kw=80.0,
        solve_time_ms=1.0, solver_status="optimal", message="ok")
    plan = opt._result_to_plan(result, res, [make_station("S1")],
                               DispatchMode.ECONOMIC, duration_min=15, is_discharge=False)
    assert plan.commands[0].target_power_kw == -80.0
    assert plan.commands[0].estimated_cost == pytest.approx(80 * 0.25 * 0.9)
    assert plan.commands[0].estimated_revenue == 0


def test_result_to_plan_skips_unknown_resource_id():
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1")]
    result = LPOptimizationResult(
        success=True, site_allocations=[("GHOST", 100.0), ("BAT", 50.0)],
        total_power_kw=150.0, solve_time_ms=1.0, solver_status="optimal", message="ok")
    plan = opt._result_to_plan(result, res, [make_station("S1")],
                               DispatchMode.ECONOMIC, duration_min=15, is_discharge=True)
    assert len(plan.commands) == 1
    assert plan.commands[0].resource_id == "BAT"


def test_result_to_plan_empty_allocations_yields_empty_plan():
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1")]
    result = LPOptimizationResult(
        success=True, site_allocations=[], total_power_kw=0.0,
        solve_time_ms=1.0, solver_status="optimal", message="ok")
    plan = opt._result_to_plan(result, res, [make_station("S1")],
                               DispatchMode.ECONOMIC, duration_min=15, is_discharge=True)
    assert plan.commands == []
    assert plan.total_dispatch_kw == 0
    assert plan.net_profit == 0


# ─── _fallback_dispatch ───

def test_fallback_dispatch_economic():
    opt = new_optimizer()
    stations = [make_station("S1")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1")]
    plan = opt._fallback_dispatch(stations, res, DispatchMode.ECONOMIC, None, 0.5)
    opt.base_optimizer.optimize_economic_dispatch.assert_called_once_with(stations, res)
    assert plan.plan_id == "fb-eco"


def test_fallback_dispatch_peak_shaving_default_threshold():
    opt = new_optimizer()
    stations = [make_station("S1")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1")]
    opt._fallback_dispatch(stations, res, DispatchMode.PEAK_SHAVING, None, 0.5)
    opt.base_optimizer.optimize_peak_shaving.assert_called_once_with(stations, res, 500)


def test_fallback_dispatch_peak_shaving_uses_given_threshold():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY)]
    opt._fallback_dispatch(stations, res, DispatchMode.PEAK_SHAVING, 300, 0.5)
    opt.base_optimizer.optimize_peak_shaving.assert_called_once_with(stations, res, 300)


def test_fallback_dispatch_demand_response_builds_signal():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY)]
    opt._fallback_dispatch(stations, res, DispatchMode.DEMAND_RESPONSE, None, 0.75)
    call = opt.base_optimizer.handle_demand_response.call_args
    assert call.args[0] == stations
    assert call.args[1] == res
    signal = call.args[2]
    assert signal.signal_type == GridSignalType.DEMAND_RESPONSE
    assert signal.reward_per_kwh == 0.75


def test_fallback_dispatch_grid_support_else_branch():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY)]
    plan = opt._fallback_dispatch(stations, res, DispatchMode.GRID_SUPPORT, None, 0.5)
    opt.base_optimizer.optimize_multi_station_coordination.assert_called_once_with(stations, res)
    assert plan.plan_id == "fb-ms"


def test_fallback_dispatch_emergency_falls_to_else():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY)]
    opt._fallback_dispatch(stations, res, DispatchMode.EMERGENCY, None, 0.5)
    opt.base_optimizer.optimize_multi_station_coordination.assert_called_once_with(stations, res)


# ─── _empty_plan ───

def test_empty_plan_fields_and_online_stations_only():
    opt = new_optimizer()
    stations = [make_station("S1", online=True), make_station("S2", online=False)]
    plan = opt._empty_plan(stations, DispatchMode.ECONOMIC, "no-dispatchable")
    assert plan.commands == []
    assert plan.total_dispatch_kw == 0
    assert plan.estimated_revenue == 0
    assert plan.estimated_cost == 0
    assert plan.net_profit == 0
    assert plan.mode == DispatchMode.ECONOMIC
    assert plan.trigger == "no-dispatchable"
    assert plan.stations_involved == ["S1"]
    assert plan.plan_id.startswith("lp_empty_")


# ─── 单例 get_vpp_lp_optimizer ───

def test_get_vpp_lp_optimizer_returns_singleton():
    saved = lp_mod._lp_optimizer
    try:
        lp_mod._lp_optimizer = None
        o1 = get_vpp_lp_optimizer()
        o2 = get_vpp_lp_optimizer()
        assert o1 is o2
        assert isinstance(o1, VPPLPOptimizer)
    finally:
        lp_mod._lp_optimizer = saved


def test_get_vpp_lp_optimizer_recreates_after_reset():
    saved = lp_mod._lp_optimizer
    try:
        lp_mod._lp_optimizer = None
        o1 = get_vpp_lp_optimizer()
        lp_mod._lp_optimizer = None
        o2 = get_vpp_lp_optimizer()
        assert o1 is not o2
    finally:
        lp_mod._lp_optimizer = saved


# ─── optimize_dispatch 集成 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_no_scipy_falls_back():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.8, available=100)]
    with patch.object(lp_mod, "HAS_SCIPY", False):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=50, mode=DispatchMode.ECONOMIC)
    opt.base_optimizer.optimize_economic_dispatch.assert_called_once()
    assert plan.plan_id == "fb-eco"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_no_dispatchable_returns_empty_plan():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.10, available=100)]
    plan = opt.optimize_dispatch(stations, res, target_power_kw=50, mode=DispatchMode.ECONOMIC)
    assert plan.plan_id.startswith("lp_empty_")
    assert plan.commands == []
    assert plan.trigger == "无可调度资源"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_lp_exception_falls_back():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.8, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", side_effect=RuntimeError("boom")):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=50, mode=DispatchMode.ECONOMIC)
    opt.base_optimizer.optimize_economic_dispatch.assert_called_once()
    assert plan.plan_id == "fb-eco"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_lp_not_success_falls_back():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.8, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_fail()):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=50, mode=DispatchMode.ECONOMIC)
    opt.base_optimizer.optimize_economic_dispatch.assert_called_once()
    assert plan.plan_id == "fb-eco"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_success_returns_plan_from_lp():
    opt = new_optimizer(price=0.9)
    stations = [make_station("ST-001")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.8, rated=100, available=100, efficiency=0.95)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([80.0])):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=80,
                                     duration_min=15, mode=DispatchMode.ECONOMIC)
    opt.base_optimizer.optimize_economic_dispatch.assert_not_called()
    assert plan.plan_id.startswith("lp_")
    assert len(plan.commands) == 1
    cmd = plan.commands[0]
    assert cmd.resource_id == "BAT"
    assert cmd.target_power_kw == 80.0
    assert cmd.estimated_revenue == pytest.approx(11.4)
    assert "求解时间" in plan.trigger and "经济调度(LP优化)" in plan.trigger


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_charge_mode_negative_target():
    opt = new_optimizer(price=0.9)
    stations = [make_station("ST-001")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.5, rated=100, available=100, efficiency=0.95)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([60.0])):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=-60,
                                     duration_min=15, mode=DispatchMode.ECONOMIC)
    assert plan.commands[0].target_power_kw == -60.0
    assert plan.commands[0].estimated_cost == pytest.approx(60 * 0.25 * 0.9)


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_auto_mode_uses_80_percent():
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.8, available=100),
           make_resource("PV", ResourceType.PV, station_id="ST-001", available=100)]
    captured = dict()

    def fake_linprog(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, **kw):
        captured["b_ub"] = b_ub
        captured["bounds"] = bounds
        return lp_ok([100.0, 60.0])

    with patch("app.services.vpp.lp_optimizer.linprog", side_effect=fake_linprog):
        opt.optimize_dispatch(stations, res, target_power_kw=0, mode=DispatchMode.ECONOMIC)
    assert captured["b_ub"][0] == pytest.approx(160 * 1.1)


# ─── _solve_lp 内部逻辑 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_ev_charger_available_power_halved():
    opt = new_optimizer()
    res = [make_resource("EV", ResourceType.EV_CHARGER, current=100, available=100)]
    captured = dict()

    def fake_linprog(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, **kw):
        captured["bounds"] = bounds
        return lp_ok([50.0])

    with patch("app.services.vpp.lp_optimizer.linprog", side_effect=fake_linprog):
        opt._solve_lp(res, required_power=40, duration_min=15,
                      is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert captured["bounds"] == [(0, 50.0)]


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_negative_available_power_does_not_break_bounds():
    """available_power_kw 为负(脏数据)时, bounds 不应出现 lb>ub 导致 linprog 崩溃。

    充电路径 _filter_dispatchable 仅校验 rated>0, 不校验 available 符号;
    负值会使 bounds=(0, 负) 非法 (lb>ub)。修复: 对 avail 做下限钳位 max(0, ap)。
    """
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.5, rated=100, available=-5)]
    captured = dict()

    def fake_linprog(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, **kw):
        captured["bounds"] = bounds
        return lp_ok([0.0])

    with patch("app.services.vpp.lp_optimizer.linprog", side_effect=fake_linprog):
        opt._solve_lp(res, required_power=40, duration_min=15,
                      is_discharge=False, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    for lb, ub in captured["bounds"]:
        assert lb <= ub, f"非法 bounds: lb={lb} > ub={ub}"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_ignores_tiny_power_below_threshold():
    opt = new_optimizer()
    res = [make_resource("SMALL", ResourceType.PV, available=10),
           make_resource("BIG", ResourceType.PV, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([0.5, 80.0])):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is True
    assert result.site_allocations == [("BIG", 80.0)]
    assert result.total_power_kw == 80.0


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_failed_returns_failed_result():
    opt = new_optimizer()
    res = [make_resource("PV", ResourceType.PV, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_fail("no solution")):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is False
    assert result.solver_status == "failed"
    assert result.site_allocations == []
    assert result.message == "no solution"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_discharge_revenue_and_cost():
    opt = new_optimizer(price=0.9)
    res = [make_resource("PV", ResourceType.PV, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([100.0])):
        result = opt._solve_lp(res, required_power=100, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.total_revenue_cny == pytest.approx(22.5)
    assert result.total_cost_cny == pytest.approx(0.38, abs=0.01)  # round(0.375, 2)=0.38


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_charge_cost_no_revenue():
    opt = new_optimizer(price=0.9)
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.5, rated=100, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([80.0])):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=False, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.total_revenue_cny == 0
    assert result.total_cost_cny == pytest.approx(80 * 0.25 * 0.9)


# ─── LPOptimizationResult.to_dict ───

def test_optimization_result_to_dict_rounds_and_counts():
    r = LPOptimizationResult(
        success=True, site_allocations=[("A", 1.0), ("B", 2.0)],
        total_power_kw=123.456, total_cost_cny=12.345, total_revenue_cny=7.771,
        solve_time_ms=3.1299, solver_status="optimal", message="ok")
    d = r.to_dict()
    assert d["success"] is True
    assert d["allocations"] == 2
    assert d["total_power_kw"] == 123.46
    assert d["total_cost_cny"] == 12.35
    assert d["total_revenue_cny"] == 7.77
    assert d["solve_time_ms"] == 3.13
    assert d["solver_status"] == "optimal"
    assert d["message"] == "ok"


# ─── SOC 过滤回归 (Bug1/Bug2) ───

def test_filter_discharge_respects_config_soc_floor():
    """Bug1回归: 放电门槛须读 config 可覆盖的 _battery_discharge_soc_floor, 而非类常量。

    config 设 battery_discharge_soc_floor=0.3 → SOC=0.25 的电池应被过滤放电。
    旧实现读类常量 BATTERY_DISCHARGE_SOC_FLOOR(0.20), 0.25>0.20 会错误保留。
    """
    opt = VPPLPOptimizer(base_optimizer=make_base_mock(discharge_floor=0.30))
    low = make_resource("LOW", ResourceType.BATTERY, soc=0.25, available=100)
    assert low not in opt._filter_dispatchable([low], discharge=True)
    # 0.35 > 0.30 仍可放电, 确认是按 0.30 而非 0.20 判定
    ok = make_resource("OK", ResourceType.BATTERY, soc=0.35, available=100)
    assert ok in opt._filter_dispatchable([ok], discharge=True)


def test_filter_charge_uses_battery_soc_max():
    """Bug2回归: 充电门槛须读 BATTERY_SOC_MAX(0.95), 而非硬编码 0.90。

    SOC=0.92 处于 (0.90, 0.95): 旧硬编码 0.90 误判为满不可充; 修复后 0.92<0.95 可充电。
    """
    opt = new_optimizer()  # BATTERY_SOC_MAX=0.95
    chargeable = make_resource("C", ResourceType.BATTERY, soc=0.92, rated=100)
    assert chargeable in opt._filter_dispatchable([chargeable], discharge=False)
    full = make_resource("F", ResourceType.BATTERY, soc=0.95, rated=100)
    assert full not in opt._filter_dispatchable([full], discharge=False)


# ─── _solve_lp 边界 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_lp_solve_duration_zero():
    """duration_min=0 不崩溃: SOC 约束走 avail 兜底分支, 收益/成本按 0 时长计算。"""
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, soc=0.8, rated=100, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([50.0])):
        result = opt._solve_lp(res, required_power=50, duration_min=0,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is True
    assert result.total_revenue_cny == 0  # dt_hours=0


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_lp_solve_all_zero_avail_powers():
    """所有资源 available_power_kw=0: bounds 全 (0,0), 解全 0, 不产生分配。"""
    opt = new_optimizer()
    res = [make_resource("PV1", ResourceType.PV, available=0),
           make_resource("PV2", ResourceType.PV, available=0)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([0.0, 0.0])):
        result = opt._solve_lp(res, required_power=50, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is True
    assert result.site_allocations == []
    assert result.total_power_kw == 0


# ─── optimize_dispatch 集成 (edge cases) ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_lp_solve_negative_target_power():
    """target_power_kw 为负(充电模式): 不崩溃, 命令功率方向为负(充电)。"""
    opt = new_optimizer(price=0.9)
    stations = [make_station("ST-001")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.5, rated=100, available=100, efficiency=0.95)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([50.0])):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=-50,
                                     duration_min=15, mode=DispatchMode.ECONOMIC)
    assert len(plan.commands) == 1
    assert plan.commands[0].target_power_kw == -50.0


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_lp_fallback_when_scipy_unavailable():
    """HAS_SCIPY=False 时任意模式回退到启发式调度, 不抛异常。"""
    opt = new_optimizer()
    stations = [make_station("ST-001")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.8, available=100)]
    with patch.object(lp_mod, "HAS_SCIPY", False):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=50,
                                     mode=DispatchMode.PEAK_SHAVING)
    opt.base_optimizer.optimize_peak_shaving.assert_called_once()
    assert plan.plan_id == "fb-ps"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_lp_empty_plan_when_no_dispatchable():
    """无可调度资源(电池 SOC 过低 + PV 零功率)时返回空计划。"""
    opt = new_optimizer()
    stations = [make_station("ST-001")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.05, available=100),
           make_resource("PV", ResourceType.PV, station_id="ST-001", available=0)]
    plan = opt.optimize_dispatch(stations, res, target_power_kw=50, mode=DispatchMode.ECONOMIC)
    assert plan.plan_id.startswith("lp_empty_")
    assert plan.commands == []
    assert plan.trigger == "无可调度资源"


@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_lp_solve_required_power_zero_auto_mode():
    """target_power_kw=0 自动模式: required_power 由可用容量 80% 推导, 产出有效计划。"""
    opt = new_optimizer(price=0.9)
    stations = [make_station("ST-001")]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.8, rated=100, available=100, efficiency=0.95)]
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=lp_ok([80.0])):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=0,
                                     duration_min=15, mode=DispatchMode.ECONOMIC)
    assert plan.plan_id.startswith("lp_")
    assert len(plan.commands) == 1
    assert plan.commands[0].target_power_kw == 80.0
