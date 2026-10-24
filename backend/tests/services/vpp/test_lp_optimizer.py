"""
VPPLPOptimizer 补充单元测试 (services/vpp 目录)

被测文件: app/services/vpp/lp_optimizer.py

聚焦 (现有 tests/test_lp_optimizer.py 未覆盖的真实缺口):
- scipy 降级: HAS_SCIPY=False (patch) + 模块级 import except 分支 (子进程模拟无 scipy)
- _build_objective 边界: LOAD 放电 else 分支 / 零电价 / 零爬坡速率
- _build_inequality_constraints 边界: duration_min=0 / BATTERY soc=None
- optimize_dispatch 边界: 空资源 / 空站点 / 超大额定功率 / 负功率充电
- get_vpp_lp_optimizer 单例并发安全 (双重检查锁验收, 配合本次并发 bug 修复)

设计要点:
- base_optimizer 用 MagicMock 固定电价/谷价, 消除 datetime 依赖
- scipy.linprog 用 patch 隔离
- 不触碰 DB
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
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
from app.services.vpp.lp_optimizer import VPPLPOptimizer, get_vpp_lp_optimizer


# ─── 工厂函数 ───

def _resource(rid, rtype, *, station_id="ST-001", rated=100.0, current=0.0,
              available=100.0, soc=0.5, efficiency=0.95, ramp=100.0, priority=5):
    return ResourceCapability(
        resource_id=rid, resource_type=rtype, station_id=station_id,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        soc=soc, efficiency=efficiency, ramp_rate_kw_per_min=ramp, priority=priority,
    )


def _station(sid="ST-001", online=True):
    return StationStatus(
        station_id=sid, station_name="S-" + sid, total_pv_kw=200, total_battery_kwh=500,
        total_ev_chargers=10, current_load_kw=100, current_pv_output_kw=120,
        current_battery_soc=0.7, available_dispatch_kw=200, online=online,
    )


def _base_mock(price=0.9, valley=0.3):
    """固定电价/谷价的 base_optimizer 替身, 4 个 fallback 方法预置空计划。"""
    m = MagicMock()
    m.get_current_price.return_value = price
    m.VALLEY_PRICE = valley
    m.BATTERY_SOC_MIN = 0.10
    m.BATTERY_DISCHARGE_SOC_FLOOR = 0.20  # 与 dispatch_optimizer.VPPOptimizer 对齐
    # ⚠️ 生产代码 _filter_dispatchable 实际读的是这两个:
    #   - _battery_discharge_soc_floor (property, 放电分支 line141; 默认 == 类常量 0.20)
    #   - BATTERY_SOC_MAX              (类常量,   充电分支 line153)
    # 裸 MagicMock 未设属性返回 MagicMock, 与 float 比较抛 TypeError → 4 测试预存失败。
    # 与 tests/test_lp_optimizer.py::make_base_mock 的 spec 列表保持一致。
    m.BATTERY_SOC_MAX = 0.95
    m._battery_discharge_soc_floor = 0.20
    for meth, pid, mode in [
        ("optimize_economic_dispatch", "fb-eco", DispatchMode.ECONOMIC),
        ("optimize_peak_shaving", "fb-ps", DispatchMode.PEAK_SHAVING),
        ("handle_demand_response", "fb-dr", DispatchMode.DEMAND_RESPONSE),
        ("optimize_multi_station_coordination", "fb-ms", DispatchMode.GRID_SUPPORT),
    ]:
        getattr(m, meth).return_value = DispatchPlan(
            plan_id=pid, mode=mode, trigger="t", stations_involved=[], commands=[],
            total_dispatch_kw=0, estimated_revenue=0, estimated_cost=0, net_profit=0,
        )
    return m


def _new_opt(price=0.9):
    return VPPLPOptimizer(base_optimizer=_base_mock(price))


def _lp_ok(x, message="optimal"):
    return SimpleNamespace(success=True, x=np.array(x, dtype=float), message=message)


# ═══════════════════════════════════════════════════════════
# scipy 不可用降级路径
# ═══════════════════════════════════════════════════════════

class TestScipyDegradation:
    """scipy 不可用时的降级路径 (任务明确要求 mock HAS_SCIPY=False)。"""

    def test_optimize_dispatch_scipy_false_falls_back(self):
        """HAS_SCIPY 被 patch 为 False → optimize_dispatch 直接走 _fallback_dispatch(ECONOMIC)。"""
        opt = _new_opt()
        stations = [_station()]
        res = [_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.8, available=100)]
        with patch.object(lp_mod, "HAS_SCIPY", False):
            plan = opt.optimize_dispatch(stations, res, target_power_kw=50,
                                         mode=DispatchMode.ECONOMIC)
        opt.base_optimizer.optimize_economic_dispatch.assert_called_once_with(stations, res)
        assert plan.plan_id == "fb-eco"

    def test_filter_dispatchable_independent_of_scipy(self):
        """_filter_dispatchable 不依赖 scipy, HAS_SCIPY=False 时仍正常过滤。"""
        opt = _new_opt()
        bat = _resource("BAT", ResourceType.BATTERY, soc=0.8, available=100)
        with patch.object(lp_mod, "HAS_SCIPY", False):
            out = opt._filter_dispatchable([bat], discharge=True)
        assert bat in out

    def test_module_imports_without_scipy_sets_flag_false(self):
        """scipy 缺失环境模块仍可导入, HAS_SCIPY=False 且降级调度不崩溃 (覆盖 import except 分支)。

        用独立子进程 + sys.modules['scipy']=None 模拟 scipy 不可用, 避免污染主进程。
        """
        code = textwrap.dedent("""
            import sys
            # 让 from scipy.optimize import linprog 抛 ImportError
            sys.modules['scipy'] = None
            sys.modules['scipy.optimize'] = None
            from app.services.vpp import lp_optimizer
            assert lp_optimizer.HAS_SCIPY is False
            # 降级调度走启发式, 不崩溃
            plan = lp_optimizer.VPPLPOptimizer().optimize_dispatch([], [])
            assert plan is not None
        """)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            cwd="/Users/xxx/.openclaw/workspace/projects/tianlian-cloud/backend",
        )
        assert result.returncode == 0, f"子进程失败 stderr={result.stderr}\nstdout={result.stdout}"


# ═══════════════════════════════════════════════════════════
# _build_objective 边界
# ═══════════════════════════════════════════════════════════

class TestObjectiveEdgeCases:
    """目标函数 edge cases: LOAD 放电 / 零电价 / 零爬坡速率。"""

    def test_economic_discharge_load_type_default_coefficient(self):
        """economic 放电 + LOAD 类型 → else 分支 c = -(price * 0.3) (覆盖 line 259)。"""
        opt = _new_opt(price=0.9)
        load = _resource("LOAD", ResourceType.LOAD)
        c = opt._build_objective([load], [100.0], is_discharge=True,
                                 mode=DispatchMode.ECONOMIC, dr_reward=0.5)
        np.testing.assert_allclose(c, [-(0.9 * 0.3)])

    def test_zero_price_charge_yields_zero_coefficient(self):
        """电价=0 + economic 充电 → 充电成本系数 c = price * (2 - eff) = 0。"""
        opt = _new_opt(price=0.0)
        res = [_resource("BAT", ResourceType.BATTERY, efficiency=0.95)]
        c = opt._build_objective(res, [100.0], is_discharge=False,
                                 mode=DispatchMode.ECONOMIC, dr_reward=0.5)
        np.testing.assert_allclose(c, [0.0])

    def test_zero_ramp_rate_grid_support_no_division_error(self):
        """爬坡速率=0 + grid_support → 1 / (0 + 1) = 1.0, 不除零。"""
        opt = _new_opt()
        res = [_resource("F", ResourceType.BATTERY, ramp=0.0)]
        c = opt._build_objective(res, [100.0], is_discharge=True,
                                 mode=DispatchMode.GRID_SUPPORT, dr_reward=0.5)
        np.testing.assert_allclose(c, [1.0])


# ═══════════════════════════════════════════════════════════
# 约束构建边界
# ═══════════════════════════════════════════════════════════

class TestConstraintBoundaries:
    """_build_inequality_constraints 边界: duration=0 / BATTERY soc=None。"""

    def test_inequality_duration_zero_uses_available_power(self):
        """duration_min=0 + 放电 + BATTERY → SOC 行走三元 else 分支, 用 avail_powers[i]。"""
        opt = _new_opt()
        res = [_resource("BAT", ResourceType.BATTERY, soc=0.8, rated=100, available=100)]
        _, b_ub = opt._build_inequality_constraints(
            res, [100.0], required_power=80, duration_min=0, is_discharge=True)
        # b_ub[0] = 总功率上限 = 80 * 1.1; b_ub[1] = SOC 约束, duration=0 → avail=100
        assert b_ub[0] == pytest.approx(80 * 1.1)
        assert b_ub[1] == pytest.approx(100.0)

    def test_inequality_battery_soc_none_skips_soc_row(self):
        """BATTERY soc=None → 不生成 SOC 行 (仅有总功率行)。"""
        opt = _new_opt()
        bat = _resource("BAT", ResourceType.BATTERY, soc=None)
        A_ub, _ = opt._build_inequality_constraints(
            [bat], [100.0], required_power=80, duration_min=15, is_discharge=True)
        assert A_ub.shape == (1, 1)


# ═══════════════════════════════════════════════════════════
# optimize_dispatch 边界
# ═══════════════════════════════════════════════════════════

class TestOptimizeDispatchEdgeCases:
    """optimize_dispatch 边界: 空资源 / 空站点 / 超大功率 / 负功率。"""

    def test_empty_resources_returns_empty_plan(self):
        """空资源列表 → 无可调度资源 → _empty_plan。"""
        opt = _new_opt()
        plan = opt.optimize_dispatch([_station()], [], target_power_kw=50,
                                     mode=DispatchMode.ECONOMIC)
        assert plan.plan_id.startswith("lp_empty_")
        assert plan.commands == []

    def test_empty_stations_no_crash(self):
        """空站点列表 + 有资源 → 不崩溃, 正常产出 LP 计划。"""
        opt = _new_opt(price=0.9)
        res = [_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.8, available=100, rated=100)]
        with patch("app.services.vpp.lp_optimizer.linprog", return_value=_lp_ok([80.0])):
            plan = opt.optimize_dispatch([], res, target_power_kw=80,
                                         duration_min=15, mode=DispatchMode.ECONOMIC)
        assert plan.plan_id.startswith("lp_")
        assert len(plan.commands) == 1

    def test_huge_rated_power_lp_solve(self):
        """超大额定功率 (1e9 kW) LP 求解不溢出。"""
        opt = _new_opt(price=0.9)
        res = [_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.8, rated=1e9, available=1e9)]
        with patch("app.services.vpp.lp_optimizer.linprog", return_value=_lp_ok([1e9])):
            plan = opt.optimize_dispatch([], res, target_power_kw=1e9,
                                         duration_min=15, mode=DispatchMode.ECONOMIC)
        assert plan.commands[0].target_power_kw == pytest.approx(1e9)

    def test_negative_target_charges_battery(self):
        """target_power_kw<0 → 充电模式, 指令功率为负。"""
        opt = _new_opt(price=0.9)
        res = [_resource("BAT", ResourceType.BATTERY, station_id="ST-001",
                         soc=0.5, rated=100, available=100)]
        with patch("app.services.vpp.lp_optimizer.linprog", return_value=_lp_ok([60.0])):
            plan = opt.optimize_dispatch([], res, target_power_kw=-60,
                                         duration_min=15, mode=DispatchMode.ECONOMIC)
        assert plan.commands[0].target_power_kw == pytest.approx(-60.0)


# ═══════════════════════════════════════════════════════════
# get_vpp_lp_optimizer 单例并发安全 (本次并发 bug 修复验收)
# ═══════════════════════════════════════════════════════════

class TestSingletonConcurrency:
    """get_vpp_lp_optimizer 单例 + 双重检查锁并发验收。"""

    def test_module_lock_exists(self):
        """模块级 _lock 存在且为锁对象 (并发 bug 修复的必要构件)。"""
        assert hasattr(lp_mod, "_lock")
        assert hasattr(lp_mod._lock, "acquire")
        assert hasattr(lp_mod._lock, "release")

    def test_singleton_returns_same_instance(self, monkeypatch):
        """两次调用返回同一 VPPLPOptimizer 实例。"""
        monkeypatch.setattr(lp_mod, "_lp_optimizer", None)
        o1 = get_vpp_lp_optimizer()
        o2 = get_vpp_lp_optimizer()
        assert o1 is o2
        assert isinstance(o1, VPPLPOptimizer)

    def test_concurrent_get_returns_single_instance(self, monkeypatch):
        """多线程并发首次调用 → 双重检查锁 → 全部拿到同一实例 (无锁则可能创建多个)。"""
        monkeypatch.setattr(lp_mod, "_lp_optimizer", None)
        instances = []
        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = [ex.submit(get_vpp_lp_optimizer) for _ in range(50)]
            for f in futures:
                instances.append(f.result())
        assert len(set(id(i) for i in instances)) == 1
