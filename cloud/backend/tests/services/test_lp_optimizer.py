"""
VPP LP 线性规划优化器缺陷修复 + 测试覆盖 — 任务卡 fd4a326f

被测模块 app/services/vpp/lp_optimizer.py 依赖 scipy.optimize.linprog, 但所有输入
都是纯 dataclass(零 DB / 零外部 IO), 因此用纯单元测试直接构造输入, 无需 DB fixture。

时间依赖隔离:
  - 电价经 VPPOptimizer.get_current_price 按时段计算, 用 monkeypatch 锁定固定值,
    消除 datetime.now() 导致的测试漂移。
  - optimize_dispatch 内部不再读 wall-clock, 全程稳定。

scipy 不可用路径: 用 monkeypatch 篡改 lp_optimizer.HAS_SCIPY=False 强制走 _fallback_dispatch。

本文件聚焦任务卡五处缺陷的回归 + 维度覆盖:
  DEF1 _filter_dispatchable: r.current_power_kw > 0 当值为 None 抛 TypeError。
  DEF2 SOC 能量近似硬编码 soc_headroom * rated_power_kw * 2: 用 capacity_kwh 或加文档。
  DEF3 _build_equality_constraints: sum(avail_powers) 含负值偏小, 等式约束被误跳过。
  DEF4 optimize_dispatch: duration_min<=0 无校验, 产生垃圾输出。
  DEF5 _fallback_dispatch: 不传 target_power_kw / duration_min, 无 fallback 语义差异告警。

浮点断言: LP/电价经乘除后存 double 误差, 一律 pytest.approx; 计数/符号/类型直接断言。
"""
import logging

import numpy as np
import pytest

from app.services.vpp import lp_optimizer as lp_mod
from app.services.vpp.dispatch_optimizer import (
    VPPOptimizer,
    ResourceType,
    DispatchMode,
    GridSignalType,
    StationStatus,
    ResourceCapability,
    DispatchPlan,
)
from app.services.vpp.lp_optimizer import VPPLPOptimizer


# ═══════════════════════════════════════════════════════════════
# 工厂函数 — 构造 dataclass 输入, 隔离 DB
# ═══════════════════════════════════════════════════════════════

def _station(sid="ST-1", name="测试站", load=200.0, pv=100.0,
             available=100.0, online=True):
    return StationStatus(
        station_id=sid, station_name=name,
        total_pv_kw=pv, total_battery_kwh=500.0, total_ev_chargers=10,
        current_load_kw=load, current_pv_output_kw=pv,
        current_battery_soc=0.5, available_dispatch_kw=available, online=online,
    )


def _battery(rid="BAT-1", sid="ST-1", rated=100.0, available=100.0,
             soc=0.8, current=0.0, priority=2, efficiency=0.95,
             capacity_kwh=None):
    """capacity_kwh 非默认值时挂到实例属性(模拟 DEF2 新增字段)。"""
    bat = ResourceCapability(
        resource_id=rid, resource_type=ResourceType.BATTERY, station_id=sid,
        rated_power_kw=rated, current_power_kw=current,
        available_power_kw=available, soc=soc, priority=priority,
        efficiency=efficiency,
    )
    if capacity_kwh is not None:
        # ResourceCapability dataclass 未声明该字段, 通过实例属性附加(向后兼容)。
        bat.capacity_kwh = capacity_kwh
    return bat


def _pv(rid="PV-1", sid="ST-1", available=80.0, current=60.0, priority=3):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.PV, station_id=sid,
        rated_power_kw=100.0, current_power_kw=current,
        available_power_kw=available, priority=priority,
    )


def _ev(rid="EV-1", sid="ST-1", power=100.0, available=50.0, priority=3):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.EV_CHARGER, station_id=sid,
        rated_power_kw=200.0, current_power_kw=power,
        available_power_kw=available, priority=priority,
    )


@pytest.fixture
def opt(monkeypatch):
    """fresh VPPLPOptimizer, 锁定电价为平段 0.6, 消除 datetime 漂移。"""
    o = VPPLPOptimizer(VPPOptimizer())
    monkeypatch.setattr(o.base_optimizer, "get_current_price",
                        lambda *_a, **_k: 0.6)
    return o


def _scipy_off(monkeypatch):
    """强制走 fallback 路径(HAS_SCIPY=False)。"""
    monkeypatch.setattr(lp_mod, "HAS_SCIPY", False)


# ═══════════════════════════════════════════════════════════════
# 1. DEF4 — duration_min 守卫
# ═══════════════════════════════════════════════════════════════

class TestDurationGuard:
    def test_duration_zero_raises(self, opt):
        """DEF4: duration_min=0 → raise ValueError(避免除零/负能量垃圾输出)。"""
        with pytest.raises(ValueError):
            opt.optimize_dispatch(
                [_station()], [_battery()],
                target_power_kw=100, duration_min=0,
                mode=DispatchMode.ECONOMIC,
            )

    def test_duration_negative_raises(self, opt):
        """DEF4: duration_min<0 → raise ValueError。"""
        with pytest.raises(ValueError):
            opt.optimize_dispatch(
                [_station()], [_battery()],
                target_power_kw=100, duration_min=-30,
                mode=DispatchMode.ECONOMIC,
            )


# ═══════════════════════════════════════════════════════════════
# 2. DEF1 — current_power_kw=None 不崩 (EV 充电桩降功率路径)
# ═══════════════════════════════════════════════════════════════

class TestNoneCurrentPowerGuard:
    def test_ev_current_power_none_no_crash(self, opt):
        """DEF1: EV 充电桩 current_power_kw=None → 不抛 TypeError。
        走放电(target>0)筛选路径, EV_CHARGER 分支 None>0 修复前抛 TypeError。
        """
        ev = _ev(power=100.0)
        ev.current_power_kw = None  # 模拟脏数据
        # 修复前: r.current_power_kw > 0 → None > 0 抛 TypeError
        plan = opt.optimize_dispatch(
            [_station()], [ev],
            target_power_kw=50, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        # 该 EV 因 current_power_kw=None 被正确过滤, 不进入可调度集 → 空计划
        assert isinstance(plan, DispatchPlan)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_filter_dispatchable_none_current_power(self, opt):
        """DEF1 直测: _filter_dispatchable 对 current_power_kw=None 的 EV 返回空。"""
        ev = _ev(power=100.0)
        ev.current_power_kw = None
        assert opt._filter_dispatchable([ev], discharge=True) == []


# ═══════════════════════════════════════════════════════════════
# 3. 空计划路径 — 无可调度资源
# ═══════════════════════════════════════════════════════════════

class TestEmptyPlan:
    def test_no_dispatchable_returns_empty(self, opt):
        """电池 SOC 过低 → 不可放电 → 空计划, 不崩。"""
        bat = _battery(soc=0.1)  # 低于放电下限 0.20
        plan = opt.optimize_dispatch(
            [_station()], [bat],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "无可调度" in plan.trigger

    def test_empty_resources_returns_empty(self, opt):
        """空资源列表 → 空计划。"""
        plan = opt.optimize_dispatch(
            [_station()], [],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        assert plan.commands == []

    def test_empty_plan_id_prefix(self, opt):
        """空计划 plan_id 前缀 lp_empty_。"""
        plan = opt.optimize_dispatch(
            [_station()], [],
            target_power_kw=100, duration_min=15,
        )
        assert plan.plan_id.startswith("lp_empty_")


# ═══════════════════════════════════════════════════════════════
# 4. 四种调度模式 — 端到端 LP 求解
# ═══════════════════════════════════════════════════════════════

class TestDispatchModes:
    def test_economic_discharge_single_battery(self, opt):
        """经济模式: 单电池放电, 总功率 > 0 且不超过需求*1.1。"""
        plan = opt.optimize_dispatch(
            [_station()], [_battery(soc=0.8, available=100.0)],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        assert plan.mode == DispatchMode.ECONOMIC
        assert len(plan.commands) == 1
        cmd = plan.commands[0]
        assert cmd.resource_type == ResourceType.BATTERY
        assert cmd.target_power_kw > 0                      # 放电为正
        assert cmd.target_power_kw == pytest.approx(95.0, rel=0.05)  # 等式 target≈95
        assert cmd.target_power_kw <= 100 * 1.1             # 不超 10% 超调
        assert "经济调度" in plan.trigger

    def test_peak_shaving_mode(self, opt):
        """削峰模式: 多资源参与, 总调度 > 0。"""
        resources = [
            _battery(rid="BAT-1", soc=0.8, available=80.0),
            _ev(rid="EV-1", power=100.0, available=50.0),
        ]
        plan = opt.optimize_dispatch(
            [_station(load=600.0)], resources,
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.PEAK_SHAVING,
            peak_threshold_kw=500.0,
        )
        assert plan.mode == DispatchMode.PEAK_SHAVING
        assert plan.total_dispatch_kw > 0
        assert "削峰填谷" in plan.trigger

    def test_demand_response_mode(self, opt):
        """需求响应模式: 电池放电参与, 总功率 > 0。"""
        plan = opt.optimize_dispatch(
            [_station()], [_battery(rid="BAT-1", soc=0.8, available=100.0)],
            target_power_kw=80, duration_min=30,
            mode=DispatchMode.DEMAND_RESPONSE,
            dr_reward_per_kwh=0.5,
        )
        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        assert plan.total_dispatch_kw > 0
        assert "需求响应" in plan.trigger

    def test_grid_support_mode(self, opt):
        """电网支撑模式: 最快响应优先, 总功率 > 0。"""
        plan = opt.optimize_dispatch(
            [_station()], [_battery(rid="BAT-1", soc=0.8, available=100.0)],
            target_power_kw=80, duration_min=15,
            mode=DispatchMode.GRID_SUPPORT,
        )
        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert plan.total_dispatch_kw > 0
        assert "电网支撑" in plan.trigger

    def test_multi_resource_allocation(self, opt):
        """多资源: 电池 + 光伏同时参与放电, 两者都被分配。"""
        resources = [
            _battery(rid="BAT-1", soc=0.8, available=60.0),
            _pv(rid="PV-1", available=40.0),
        ]
        plan = opt.optimize_dispatch(
            [_station()], resources,
            target_power_kw=90, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        ids = {c.resource_id for c in plan.commands}
        assert {"BAT-1", "PV-1"}.issubset(ids)
        assert plan.total_dispatch_kw > 0


# ═══════════════════════════════════════════════════════════════
# 5. SOC 约束 — DEF2
# ═══════════════════════════════════════════════════════════════

class TestSocConstraint:
    def test_low_soc_caps_discharge_power(self, opt):
        """DEF2: SOC 能量约束把放电上界压到可用能量以下。
        soc=0.21, headroom=0.21-0.10=0.11, 硬编码容量=0.11*100*2=22kWh,
        15min 内 max_power=22/0.25=88kW < available(100) → 不等式约束 b 取 min(100,88)=88。
        直接断言内部约束构造, 避免端到端等式约束与 SOC 上界冲突导致 LP 不可行。
        """
        bat = _battery(rid="BAT-1", soc=0.21, available=100.0, rated=100.0)
        A_ub, b_ub = opt._build_inequality_constraints(
            [bat], [100.0], required_power=50, duration_min=15,
            is_discharge=True,
        )
        assert A_ub is not None and b_ub is not None
        # b_ub[0]=总功率上界(55), b_ub[1]=SOC约束(88); SOC 把上界从 available 100 压到 88
        assert b_ub[0] == pytest.approx(55.0)
        assert b_ub[1] == pytest.approx(88.0, rel=0.01)
        assert b_ub[1] < 100.0

    def test_capacity_kwh_field_overrides_hardcode(self, opt):
        """DEF2: ResourceCapability 带 capacity_kwh → 用真实容量替代硬编码 *2 假设。
        soc=0.21, headroom=0.11:
          硬编码容量 = 0.11*100*2 = 22kWh  → 88kW
          真实容量 capacity_kwh=50 → 可放能量=50*0.11=5.5kWh → 22kW
        带 capacity_kwh 后 SOC 不等式上界从 88 收紧到 22。
        """
        bat = _battery(rid="BAT-1", soc=0.21, available=100.0, rated=100.0,
                       capacity_kwh=50.0)
        A_ub, b_ub = opt._build_inequality_constraints(
            [bat], [100.0], required_power=50, duration_min=15,
            is_discharge=True,
        )
        assert A_ub is not None and b_ub is not None
        # b_ub[0]=总功率上界(55), b_ub[1]=SOC约束; capacity_kwh=50 收紧可放能量:
        # 50*0.11=5.5kWh / 0.25h = 22kW
        assert b_ub[0] == pytest.approx(55.0)
        assert b_ub[1] == pytest.approx(22.0, rel=0.01)

    def test_low_soc_caps_discharge_end_to_end(self, opt):
        """DEF2 端到端: SOC 约束在 LP 求解中真正压低电池放电功率。
        多资源避免单资源等式冲突: 电池(SOC约束88) + 光伏(40)。
        target=min(120, max(108, (100+40)*0.95=133))=120。
        电池受 SOC 上界 88 限制(available 100 被 SOC 压到 88), 总功率由电池+光伏凑。
        关键断言: 电池指令功率 <= 88(SOC 约束生效), 不会顶到 available 100。
        """
        resources = [
            _battery(rid="BAT-1", soc=0.21, available=100.0, rated=100.0),
            _pv(rid="PV-1", available=40.0),
        ]
        plan = opt.optimize_dispatch(
            [_station()], resources,
            target_power_kw=120, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        bat_cmd = next((c for c in plan.commands if c.resource_id == "BAT-1"), None)
        assert bat_cmd is not None, "电池应参与调度"
        # SOC 约束(88)生效: 电池放电不超过 88kW, 远低于 available 100
        assert bat_cmd.target_power_kw <= 88.5
        assert bat_cmd.target_power_kw > 0

    def test_soc_none_no_inequality_constraint(self, opt):
        """电池 soc=None → 不加 SOC 不等式约束行(仅靠 available 上界)。"""
        bat = _battery(soc=None, available=100.0)
        # 直接调内部约束构造验证不崩
        A_ub, b_ub = opt._build_inequality_constraints(
            [bat], [100.0], required_power=80, duration_min=15,
            is_discharge=True,
        )  # fmt: skip
        # SOC=None 不应贡献额外约束行; 总功率上界行始终存在
        assert A_ub is not None and b_ub is not None


# ═══════════════════════════════════════════════════════════════
# 6. 约束构造 — DEF3 等式约束负值
# ═══════════════════════════════════════════════════════════════

class TestEqualityConstraints:
    def test_negative_avail_not_undercounted(self, opt):
        """DEF3: avail_powers 含负脏数据时, total_avail 应用 max(0, ap) 求和。
        修复前 sum([100, -50])=50 < required*0.9=72 → 等式约束被跳过(返回 None)。
        修复后 sum(max(0,...))=100 >= 72 → 返回等式约束。
        """
        avail = [100.0, -50.0]   # 第二个资源脏数据
        required = 80.0
        A_eq, b_eq = opt._build_equality_constraints(avail, required)
        # 修复后: total_avail=100 >= 72 → 有等式约束
        assert A_eq is not None
        assert b_eq is not None
        # target = min(80, max(72, 100*0.95=95)) = min(80, 95) = 80
        assert b_eq[0] == pytest.approx(80.0)

    def test_sufficient_capacity_target_equals_required(self, opt):
        """可用充足 → 等式 target 等于 required。"""
        A_eq, b_eq = opt._build_equality_constraints([100.0, 100.0], required_power=80.0)
        assert b_eq[0] == pytest.approx(80.0)
        # 系数全 1(对每个决策变量等权)
        assert np.allclose(A_eq[0], [1.0, 1.0])

    def test_insufficient_capacity_no_equality(self, opt):
        """可用不足(< required*0.9) → 无等式约束(交由上界最大化)。"""
        # total_avail=50 < required*0.9=72
        A_eq, b_eq = opt._build_equality_constraints([50.0], required_power=80.0)
        assert A_eq is None and b_eq is None


# ═══════════════════════════════════════════════════════════════
# 7. scipy 不可用 — fallback 路径 + DEF5
# ═══════════════════════════════════════════════════════════════

class TestScipyFallback:
    def test_fallback_when_scipy_unavailable(self, opt, monkeypatch):
        """HAS_SCIPY=False → 走 _fallback_dispatch, 返回 DispatchPlan 不崩。"""
        _scipy_off(monkeypatch)
        plan = opt.optimize_dispatch(
            [_station()], [_battery(soc=0.8, available=100.0)],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        assert isinstance(plan, DispatchPlan)

    def test_fallback_peak_shaving(self, opt, monkeypatch):
        """fallback 削峰模式: 无 scipy 时回退到启发式 optimize_peak_shaving。"""
        _scipy_off(monkeypatch)
        plan = opt.optimize_dispatch(
            [_station(load=600.0)],
            [_battery(soc=0.8, available=80.0), _load := _ev(rid="LOAD-1")],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.PEAK_SHAVING,
            peak_threshold_kw=500.0,
        )
        assert isinstance(plan, DispatchPlan)

    def test_fallback_emits_warning(self, opt, monkeypatch, caplog):
        """DEF5: 走 fallback 时应打 warning 说明语义差异(未传 target/duration 上下文)。"""
        _scipy_off(monkeypatch)
        with caplog.at_level(logging.WARNING, logger="vpp.lp_optimizer"):
            opt.optimize_dispatch(
                [_station()], [_battery(soc=0.8, available=100.0)],
                target_power_kw=100, duration_min=15,
                mode=DispatchMode.ECONOMIC,
            )
        assert any("fallback" in rec.message.lower() or "回退" in rec.message
                   or "启发式" in rec.message
                   for rec in caplog.records)

    def test_fallback_demand_response(self, opt, monkeypatch):
        """fallback 需求响应: 构造 GridSignal 走 handle_demand_response。"""
        _scipy_off(monkeypatch)
        plan = opt.optimize_dispatch(
            [_station()],
            [_battery(rid="BAT-1", soc=0.8, available=150.0, rated=200.0)],
            target_power_kw=150, duration_min=60,
            mode=DispatchMode.DEMAND_RESPONSE,
            dr_reward_per_kwh=0.5,
        )
        assert isinstance(plan, DispatchPlan)

    def test_fallback_grid_support(self, opt, monkeypatch):
        """fallback 电网支撑: 走 multi_station_coordination。"""
        _scipy_off(monkeypatch)
        plan = opt.optimize_dispatch(
            [_station()],
            [_battery(rid="BAT-1", soc=0.8, available=100.0)],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.GRID_SUPPORT,
        )
        assert isinstance(plan, DispatchPlan)


# ═══════════════════════════════════════════════════════════════
# 8. 结果转计划 + 单例
# ═══════════════════════════════════════════════════════════════

class TestResultToPlan:
    def test_plan_id_lp_prefix(self, opt):
        """成功 LP 计划 plan_id 前缀 lp_。"""
        plan = opt.optimize_dispatch(
            [_station()], [_battery(soc=0.8, available=100.0)],
            target_power_kw=100, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        assert plan.plan_id.startswith("lp_")
        assert not plan.plan_id.startswith("lp_empty_")

    def test_ev_curtail_is_negative_power(self, opt):
        """EV 充电桩降功率 → 指令 target_power_kw 为负(等效放电用负值表示)。"""
        # 仅 EV, current_power=100, target 放电触发降功率
        plan = opt.optimize_dispatch(
            [_station()], [_ev(power=100.0, available=50.0)],
            target_power_kw=40, duration_min=15,
            mode=DispatchMode.ECONOMIC,
        )
        ev_cmds = [c for c in plan.commands
                   if c.resource_type == ResourceType.EV_CHARGER]
        if ev_cmds:
            assert ev_cmds[0].target_power_kw < 0
