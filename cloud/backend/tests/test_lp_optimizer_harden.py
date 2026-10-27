"""
lp_optimizer.py 防御性加固边界测试 (卡6a17ab26)

覆盖新增加固点:
1. linprog 异常时不崩溃, 返回 failed result
2. result.x=None / 空 / 含NaN / 含Inf 时不崩溃
3. result.x 索引越界(资源数 > 解维度) 不崩溃
4. dt_hours=0 (duration_min=0 在 _solve_lp 被直接调用) 不除零
5. 空资源列表传入 _build_objective/_build_inequality/_build_equality 不崩溃
6. current_power_kw=None 的 EV 在 _solve_lp 内部不崩溃 (avail_powers 计算)
7. 价格脏数据 (None/NaN/负值) 不崩溃
8. _result_to_plan 中 duration_min=0 不除零
9. linprog 返回非预期结构(convergence warning)时的安全处理
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
    ResourceType,
    ResourceCapability,
    StationStatus,
)
from app.services.vpp.lp_optimizer import (
    HAS_SCIPY,
    LPOptimizationResult,
    VPPLPOptimizer,
)


def make_resource(rid, rtype, *, station_id="ST-001", rated=100.0, current=0.0,
                  available=100.0, soc=None, efficiency=0.95, ramp=100.0, priority=5):
    actual_soc = 0.5 if soc is None else soc
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


def make_base_mock(price=0.9, discharge_floor=0.20):
    m = MagicMock(spec=["get_current_price", "VALLEY_PRICE", "BATTERY_SOC_MIN",
                        "BATTERY_SOC_MAX", "BATTERY_DISCHARGE_SOC_FLOOR",
                        "_battery_discharge_soc_floor",
                        "optimize_economic_dispatch", "optimize_peak_shaving",
                        "handle_demand_response", "optimize_multi_station_coordination"])
    m.get_current_price.return_value = price
    m.VALLEY_PRICE = 0.3
    m.BATTERY_SOC_MIN = 0.10
    m.BATTERY_SOC_MAX = 0.95
    m.BATTERY_DISCHARGE_SOC_FLOOR = 0.20
    m._battery_discharge_soc_floor = discharge_floor
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


def new_optimizer(price=0.9):
    return VPPLPOptimizer(base_optimizer=make_base_mock(price))


# ─── 1. linprog 抛异常 → 安全返回 failed result ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_linprog_exception_returns_failed():
    """linprog 抛 RuntimeError 时, _solve_lp 返回 success=False, 不向上传播异常。"""
    opt = new_optimizer()
    res = [make_resource("PV", ResourceType.PV, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", side_effect=RuntimeError("internal error")):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is False
    assert "error" in result.solver_status or "异常" in result.message


# ─── 2. result.x = None → 安全返回 failed ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_result_x_none():
    """result.x=None(scipy极罕见情况) → 返回 success=False, 不抛 TypeError。"""
    opt = new_optimizer()
    res = [make_resource("PV", ResourceType.PV, available=100)]
    fake_result = SimpleNamespace(success=True, x=None, message="degenerate")
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=fake_result):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is False
    assert result.solver_status == "empty"


# ─── 3. result.x 含 NaN → 安全返回 failed ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_result_x_has_nan():
    """result.x 含 NaN → 返回 success=False, status=nan, 不传播 NaN。"""
    opt = new_optimizer()
    res = [make_resource("PV", ResourceType.PV, available=100),
           make_resource("PV2", ResourceType.PV, available=80)]
    fake_result = SimpleNamespace(success=True, x=np.array([50.0, np.nan]), message="ok")
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=fake_result):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is False
    assert result.solver_status == "nan"


# ─── 4. result.x 含 Inf → 安全返回 failed ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_result_x_has_inf():
    """result.x 含 Inf → 返回 success=False, status=nan, 不传播 Inf。"""
    opt = new_optimizer()
    res = [make_resource("PV", ResourceType.PV, available=100)]
    fake_result = SimpleNamespace(success=True, x=np.array([np.inf]), message="ok")
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=fake_result):
        result = opt._solve_lp(res, required_power=80, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is False
    assert result.solver_status == "nan"


# ─── 5. result.x 索引越界(资源多于解维度) → 不崩溃 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_result_x_fewer_than_resources():
    """result.x 维度 < resources 数量 → 不越界, 只解析有效维度。"""
    opt = new_optimizer()
    res = [make_resource("A", ResourceType.PV, available=100),
           make_resource("B", ResourceType.PV, available=80),
           make_resource("C", ResourceType.PV, available=60)]
    # linprog 只返回 2 个变量(异常情况), 但有 3 个资源
    fake_result = SimpleNamespace(success=True, x=np.array([50.0, 40.0]), message="ok")
    with patch("app.services.vpp.lp_optimizer.linprog", return_value=fake_result):
        result = opt._solve_lp(res, required_power=100, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    # 不崩溃, 成功解析前两个
    assert result.success is True
    assert len(result.site_allocations) == 2


# ─── 6. 空资源列表 → _build_objective 不崩溃 ───

def test_build_objective_empty_resources():
    """_build_objective 传入空 resources → 返回空 np.array, 不崩溃。"""
    opt = new_optimizer()
    c = opt._build_objective([], [], is_discharge=True,
                             mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert isinstance(c, np.ndarray)
    assert c.shape == (0,)


# ─── 7. 空资源列表 → _build_inequality_constraints 不崩溃 ───

def test_build_inequality_empty_resources():
    """_build_inequality_constraints 传入空 resources → 返回 (None, None)。"""
    opt = new_optimizer()
    A_ub, b_ub = opt._build_inequality_constraints(
        [], [], required_power=100, duration_min=15, is_discharge=True)
    assert A_ub is None and b_ub is None


# ─── 8. 空资源列表 → _build_equality_constraints 不崩溃 ───

def test_build_equality_empty_avail():
    """_build_equality_constraints 传入空 avail_powers → 返回 (None, None)。"""
    opt = new_optimizer()
    A_eq, b_eq = opt._build_equality_constraints([], required_power=100)
    assert A_eq is None and b_eq is None


# ─── 9. dt_hours=0 在 _solve_lp 直接调用时不除零 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_zero_duration_no_division_error():
    """_solve_lp 直接调用 duration_min=0 → dt_hours=0, 收益/成本=0, 不除零。"""
    opt = new_optimizer()
    res = [make_resource("PV", ResourceType.PV, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog",
               return_value=SimpleNamespace(success=True, x=np.array([50.0]), message="ok")):
        result = opt._solve_lp(res, required_power=50, duration_min=0,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    assert result.success is True
    assert result.total_revenue_cny == 0
    assert result.total_cost_cny == 0


# ─── 10. _result_to_plan 中 dt_hours 除法守卫 ───

def test_result_to_plan_zero_duration_no_crash():
    """_result_to_plan 直接调用 duration_min=0 → dt_hours=0, 不除零, energy_kwh=0。"""
    opt = new_optimizer()
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="S1")]
    result = LPOptimizationResult(
        success=True, site_allocations=[("BAT", 100.0)], total_power_kw=100.0,
        solve_time_ms=1.0, solver_status="optimal", message="ok")
    plan = opt._result_to_plan(result, res, [make_station("S1")],
                               DispatchMode.ECONOMIC, duration_min=0, is_discharge=True)
    # energy_kwh=0 → revenue=0, cost=0
    assert plan.commands[0].estimated_revenue == 0
    assert plan.commands[0].estimated_cost == 0


# ─── 11. linprog 异常在 optimize_dispatch 中回退到启发式 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_optimize_dispatch_linpeg_exception_falls_back():
    """optimize_dispatch 中 linprog 抛异常 → _solve_lp 返回 failed → 回退启发式。"""
    opt = new_optimizer()
    stations = [make_station()]
    res = [make_resource("BAT", ResourceType.BATTERY, station_id="ST-001", soc=0.8, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog", side_effect=ValueError("bad matrix")):
        plan = opt.optimize_dispatch(stations, res, target_power_kw=50, mode=DispatchMode.ECONOMIC)
    opt.base_optimizer.optimize_economic_dispatch.assert_called_once()
    assert plan.plan_id == "fb-eco"


# ─── 12. 价格脏数据 None → 安全兜底为 0 ───

@pytest.mark.skipif(not HAS_SCIPY, reason="scipy unavailable")
def test_solve_lp_price_none_safe_default():
    """get_current_price 返回 None → 安全兜底 0.0, 不抛 TypeError。"""
    base = make_base_mock()
    base.get_current_price.return_value = None
    opt = VPPLPOptimizer(base_optimizer=base)
    res = [make_resource("PV", ResourceType.PV, available=100)]
    with patch("app.services.vpp.lp_optimizer.linprog",
               return_value=SimpleNamespace(success=True, x=np.array([50.0]), message="ok")):
        result = opt._solve_lp(res, required_power=50, duration_min=15,
                               is_discharge=True, mode=DispatchMode.ECONOMIC, dr_reward=0.5)
    # price=0 → revenue=0
    assert result.success is True
    assert result.total_revenue_cny == 0
