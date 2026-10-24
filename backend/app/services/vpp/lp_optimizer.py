"""
VPP线性规划(LP)优化器
基于scipy.optimize.linprog求解最优功率分配
目标：最大化经济效益 / 最小化成本 / 最快响应
约束：SOC上下限、最大功率、爬坡速率、响应时间

集成自vpp-scheduling独立项目，适配天链V3架构
"""
from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import numpy as np

try:
    from scipy.optimize import linprog
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .dispatch_optimizer import (
    ResourceType, DispatchMode, VPPOptimizer,
    StationStatus, ResourceCapability, DispatchCommand, DispatchPlan,
)
from .dispatch_optimizer.optimizer import _make_plan_id

logger = logging.getLogger("vpp.lp_optimizer")


@dataclass
class LPOptimizationResult:
    """LP优化结果"""
    success: bool
    site_allocations: list[tuple[str, float]]  # (resource_id, power_kw)
    total_power_kw: float
    total_cost_cny: float = 0
    total_revenue_cny: float = 0
    solve_time_ms: float = 0
    solver_status: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "total_power_kw": round(self.total_power_kw, 2),
            "total_cost_cny": round(self.total_cost_cny, 2),
            "total_revenue_cny": round(self.total_revenue_cny, 2),
            "solve_time_ms": round(self.solve_time_ms, 2),
            "solver_status": self.solver_status,
            "allocations": len(self.site_allocations),
            "message": self.message,
        }


class VPPLPOptimizer:
    """
    VPP线性规划优化器

    决策变量: x_i = 资源i的功率分配 (kW, 正=放电, 负=充电)

    目标函数(取决于模式):
    - economic: 最大化净收益 = sum(x_i * price_diff_i)
    - peak_shaving: 最小化总调度成本
    - demand_response: 最大化响应容量 * 奖励率
    - fastest_response: 最小化加权响应时间

    约束:
    - 每个资源功率 <= 最大可调度功率
    - SOC约束: 放电不超过可用SOC量
    - 总功率满足需求(允许10%偏差)
    - 爬坡速率约束
    """

    def __init__(self, base_optimizer: Optional[VPPOptimizer] = None):
        self.base_optimizer = base_optimizer or VPPOptimizer()

    def optimize_dispatch(
        self,
        stations: List[StationStatus],
        resources: List[ResourceCapability],
        target_power_kw: float = 0,  # 正=放电, 负=充电, 0=自动
        duration_min: int = 15,
        mode: DispatchMode = DispatchMode.ECONOMIC,
        peak_threshold_kw: Optional[float] = None,
        dr_reward_per_kwh: float = 0.5,
    ) -> DispatchPlan:
        """
        使用LP优化创建调度计划

        如果scipy不可用或LP求解失败，自动回退到启发式调度

        ⚠️ DEF4: duration_min<=0 是非法输入(除零/负能量垃圾输出), 直接拒绝。
        """
        # DEF4: duration_min<=0 守卫, 避免除零与负能量垃圾输出
        if duration_min <= 0:
            raise ValueError(
                f"duration_min 必须为正数, 实际收到 {duration_min}"
            )

        if not HAS_SCIPY:
            logger.warning("scipy不可用，回退到启发式调度")
            return self._fallback_dispatch(
                stations, resources, mode, peak_threshold_kw, dr_reward_per_kwh
            )

        # 筛选可调度资源
        is_discharge = target_power_kw >= 0
        dispatchable = self._filter_dispatchable(resources, is_discharge)

        if not dispatchable:
            logger.info("无可调度资源，返回空计划")
            return self._empty_plan(stations, mode, "无可调度资源")

        required_power = abs(target_power_kw) if target_power_kw != 0 else sum(
            r.available_power_kw for r in dispatchable
        ) * 0.8  # 自动模式：用80%可用容量

        try:
            result = self._solve_lp(dispatchable, required_power, duration_min, is_discharge, mode, dr_reward_per_kwh)
        except Exception as e:
            logger.error("LP求解异常: %s，回退到启发式", e)
            return self._fallback_dispatch(
                stations, resources, mode, peak_threshold_kw, dr_reward_per_kwh
            )

        if not result or not result.success:
            logger.warning("LP求解失败，回退到启发式调度")
            return self._fallback_dispatch(
                stations, resources, mode, peak_threshold_kw, dr_reward_per_kwh
            )

        # 转换为DispatchPlan
        return self._result_to_plan(
            result, dispatchable, stations, mode, duration_min, is_discharge
        )

    def _filter_dispatchable(
        self, resources: List[ResourceCapability], discharge: bool
    ) -> List[ResourceCapability]:
        """筛选可调度资源"""
        dispatchable = []
        for r in resources:
            if discharge:
                # 放电：储能可放电，光伏可满发
                if r.resource_type == ResourceType.BATTERY:
                    if r.soc is not None and r.soc > self.base_optimizer._battery_discharge_soc_floor and r.available_power_kw > 0:
                        dispatchable.append(r)
                elif r.resource_type == ResourceType.PV:
                    if r.available_power_kw > 0:
                        dispatchable.append(r)
                # 充电桩可降功率（等效放电）
                elif r.resource_type == ResourceType.EV_CHARGER:
                    # DEF1: current_power_kw 可能为 None(脏数据), 直接 > 0 会抛 TypeError
                    if (r.current_power_kw or 0) > 0:
                        dispatchable.append(r)
            else:
                # 充电：储能可充电
                if r.resource_type == ResourceType.BATTERY:
                    if r.soc is not None and r.soc < self.base_optimizer.BATTERY_SOC_MAX and r.rated_power_kw > 0:
                        dispatchable.append(r)
        return dispatchable

    def _solve_lp(
        self,
        resources: List[ResourceCapability],
        required_power: float,
        duration_min: int,
        is_discharge: bool,
        mode: DispatchMode,
        dr_reward: float,
    ) -> Optional[LPOptimizationResult]:
        """求解LP"""
        avail_powers = [
            r.available_power_kw if r.resource_type != ResourceType.EV_CHARGER
            else (r.current_power_kw or 0) * 0.5  # 充电桩最多降50%, None守卫
            for r in resources
        ]

        # 1. 目标函数
        c = self._build_objective(resources, avail_powers, is_discharge, mode, dr_reward)

        # 2. 不等式约束 A_ub * x <= b_ub
        A_ub, b_ub = self._build_inequality_constraints(
            resources, avail_powers, required_power, duration_min, is_discharge
        )

        # 3. 等式约束
        A_eq, b_eq = self._build_equality_constraints(avail_powers, required_power)

        # 4. 变量边界 (max(0, ap) 防御负的 available_power_kw 脏数据: lb>ub 会使 linprog 拒绝)
        bounds = [(0, max(0.0, ap)) for ap in avail_powers]

        # 求解
        start = time.time()
        try:
            result = linprog(
                c,
                A_ub=A_ub, b_ub=b_ub,
                A_eq=A_eq, b_eq=b_eq,
                bounds=bounds,
                method='highs',
                options={'maxiter': 1000, 'disp': False},
            )
        except Exception as e:
            logger.error("linprog求解异常: %s", e)
            return LPOptimizationResult(
                success=False, site_allocations=[], total_power_kw=0,
                solver_status="error",
                message=f"linprog异常: {e}",
            )
        solve_time = (time.time() - start) * 1000

        if not result.success:
            return LPOptimizationResult(
                success=False, site_allocations=[], total_power_kw=0,
                solve_time_ms=solve_time, solver_status="failed",
                message=result.message,
            )

        # result.x 安全检查: None / 空 / NaN / Inf
        if result.x is None or len(result.x) == 0:
            return LPOptimizationResult(
                success=False, site_allocations=[], total_power_kw=0,
                solve_time_ms=solve_time, solver_status="empty",
                message="LP返回空解",
            )
        x_arr = np.asarray(result.x, dtype=float)
        if np.any(np.isnan(x_arr)) or np.any(np.isinf(x_arr)):
            logger.warning("LP解含NaN/Inf, 舍弃: %s", x_arr)
            return LPOptimizationResult(
                success=False, site_allocations=[], total_power_kw=0,
                solve_time_ms=solve_time, solver_status="nan",
                message="LP解含NaN或Inf",
            )

        # 解析结果
        allocations = []
        total_power = 0.0
        for i, r in enumerate(resources):
            if i >= len(x_arr):
                break
            power = float(x_arr[i])
            if not np.isfinite(power):
                continue
            if power > 1:  # 忽略极小值
                allocations.append((r.resource_id, round(power, 2)))
                total_power += power

        # 计算经济效益
        current_price = self.base_optimizer.get_current_price()
        valley_price = self.base_optimizer.VALLEY_PRICE
        # dt_hours 除法守卫: duration_min 已在 optimize_dispatch 层校验 >0,
        # 此处防御性兜底 _solve_lp 被直接调用时的除零风险
        dt_hours = duration_min / 60 if duration_min > 0 else 0.0

        # 价格安全检查: 防御 None/NaN/负值脏数据
        try:
            current_price = float(current_price)
        except (TypeError, ValueError):
            current_price = 0.0
        if not np.isfinite(current_price) or current_price < 0:
            current_price = 0.0
        try:
            valley_price = float(valley_price)
        except (TypeError, ValueError):
            valley_price = 0.0
        if not np.isfinite(valley_price) or valley_price < 0:
            valley_price = 0.0

        if is_discharge:
            total_revenue = total_power * dt_hours * current_price
            total_cost = total_power * dt_hours * valley_price * 0.05  # 损耗成本
        else:
            total_revenue = 0
            total_cost = total_power * dt_hours * current_price

        return LPOptimizationResult(
            success=True,
            site_allocations=allocations,
            total_power_kw=round(total_power, 2),
            total_cost_cny=round(total_cost, 2),
            total_revenue_cny=round(total_revenue, 2),
            solve_time_ms=round(solve_time, 2),
            solver_status="optimal",
            message=f"LP求解成功, {len(allocations)}个资源, 总功率={total_power:.1f}kW",
        )

    def _build_objective(
        self, resources, avail_powers, is_discharge, mode, dr_reward
    ) -> np.ndarray:
        """构建目标函数系数 (linprog求最小值)"""
        n = len(resources)
        if n == 0:
            return np.zeros(0)
        c = np.zeros(n)
        # 价格安全检查: 防御 None/NaN/负值脏数据
        try:
            current_price = float(self.base_optimizer.get_current_price())
        except (TypeError, ValueError):
            current_price = 0.0
        if not np.isfinite(current_price) or current_price < 0:
            current_price = 0.0
        try:
            valley_price = float(self.base_optimizer.VALLEY_PRICE)
        except (TypeError, ValueError):
            valley_price = 0.0
        if not np.isfinite(valley_price) or valley_price < 0:
            valley_price = 0.0

        if mode == DispatchMode.ECONOMIC:
            # 最大化净收益 = (售价 - 成本) * 功率
            # 等价最小化: -(售价 - 成本) * 功率
            for i, r in enumerate(resources):
                if is_discharge:
                    if r.resource_type == ResourceType.BATTERY:
                        profit_per_kw = (current_price - valley_price) * r.efficiency
                    elif r.resource_type == ResourceType.PV:
                        profit_per_kw = current_price * 0.9  # 光伏无成本
                    elif r.resource_type == ResourceType.EV_CHARGER:
                        profit_per_kw = current_price * 0.5  # 降功率收益
                    else:
                        profit_per_kw = current_price * 0.3
                    c[i] = -profit_per_kw
                else:
                    # 充电：最小化充电成本
                    c[i] = current_price * (2 - r.efficiency)  # 效率低的成本高

        elif mode == DispatchMode.PEAK_SHAVING:
            # 最小化总调度成本(优先用便宜的)
            for i, r in enumerate(resources):
                if r.resource_type == ResourceType.BATTERY:
                    c[i] = 1 - r.efficiency  # 效率损失
                elif r.resource_type == ResourceType.EV_CHARGER:
                    c[i] = 0.3  # 降功率有补偿成本
                else:
                    c[i] = 0.1

        elif mode == DispatchMode.DEMAND_RESPONSE:
            # 最大化响应容量 * 奖励率
            for i, r in enumerate(resources):
                c[i] = -(dr_reward * r.efficiency)  # 效率高的优先

        elif mode == DispatchMode.GRID_SUPPORT:
            # 最快响应优先：最小化加权响应时间
            for i, r in enumerate(resources):
                # 爬坡速率越快，权重越低
                ramp = getattr(r, 'ramp_rate_kw_per_min', 100)
                c[i] = 1.0 / (ramp + 1)  # 爬坡快的优先

        else:
            # 默认：最大化总功率
            c = np.ones(n) * (-1)

        return c

    def _build_inequality_constraints(
        self, resources, avail_powers, required_power, duration_min, is_discharge
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """构建不等式约束"""
        n = len(resources)
        if n == 0:
            return None, None
        rows_A = []
        rows_b = []

        # 约束1: 每个资源功率 <= 可用功率 (已在bounds中)

        # 约束2: 总功率 <= 需求 * 1.1 (允许10%超调)
        row = np.ones(n)
        rows_A.append(row)
        rows_b.append(required_power * 1.1)

        # 约束3: 储能SOC约束
        if is_discharge:
            for i, r in enumerate(resources):
                if r.resource_type == ResourceType.BATTERY and r.soc is not None:
                    # 放电不能超过可用SOC量
                    soc_headroom = r.soc - self.base_optimizer.BATTERY_SOC_MIN
                    # DEF2: SOC能量近似。
                    # 若资源带 capacity_kwh 字段(真实总容量), 用其乘以可放比例得到可用能量;
                    # 否则保留原硬编码假设 "2小时@额定功率=总容量" 作为保守近似,
                    # 即 max_energy_kwh = soc_headroom * rated_power_kw * 2。
                    capacity_kwh = getattr(r, 'capacity_kwh', None)
                    if capacity_kwh is not None:
                        max_energy_kwh = capacity_kwh * soc_headroom
                    else:
                        # 硬编码假设: 容量 ≈ 额定功率 * 2h。无真实容量数据时的保守近似。
                        max_energy_kwh = soc_headroom * r.rated_power_kw * 2
                    max_power_15min = max_energy_kwh / (duration_min / 60) if duration_min > 0 else avail_powers[i]
                    row = np.zeros(n)
                    row[i] = 1
                    rows_A.append(row)
                    rows_b.append(min(avail_powers[i], max_power_15min))

        if rows_A:
            return np.array(rows_A), np.array(rows_b)
        return None, None

    def _build_equality_constraints(
        self, avail_powers, required_power
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """构建等式约束 - 尽量满足功率需求"""
        n = len(avail_powers)
        if n == 0:
            return None, None
        # DEF3: avail_powers 可能含负脏数据(available_power_kw<0), 用 max(0, ap) 求和
        # 避免 total_avail 被负值压小, 误判容量不足而跳过等式约束。
        total_avail = sum(max(0, ap) for ap in avail_powers)

        # 只在可用容量充裕时要求精确匹配
        if total_avail >= required_power * 0.9:
            # 目标功率: 不超过需求, 且不低于需求90%(10%偏差下限);
            # total_avail*0.95 保留5%安全裕度, 避免求解器顶到总容量上界。
            # 注: 单独用 total_avail*0.95 会在 total_avail∈[0.9,0.9474)*req 时
            # 让 b_eq 跌破90%下限, 故用 max(...) 兜底下限。
            target = min(required_power, max(required_power * 0.9, total_avail * 0.95))
            A_eq = np.array([np.ones(n)])
            b_eq = np.array([target])
            return A_eq, b_eq
        return None, None

    def _result_to_plan(
        self,
        result: LPOptimizationResult,
        resources: List[ResourceCapability],
        stations: List[StationStatus],
        mode: DispatchMode,
        duration_min: int,
        is_discharge: bool,
    ) -> DispatchPlan:
        """将LP结果转换为DispatchPlan"""
        resource_map = {r.resource_id: r for r in resources}

        commands = []
        for resource_id, power_kw in result.site_allocations:
            r = resource_map.get(resource_id)
            if not r:
                continue

            # 确定功率方向
            if is_discharge:
                actual_power = power_kw
                # 充电桩降功率是负值
                if r.resource_type == ResourceType.EV_CHARGER:
                    actual_power = -power_kw  # 降功率=负
            else:
                actual_power = -power_kw  # 充电=负

            dt_hours = duration_min / 60 if duration_min > 0 else 0.0
            energy_kwh = power_kw * dt_hours

            # 计算收益
            current_price = self.base_optimizer.get_current_price()
            if actual_power > 0:
                revenue = energy_kwh * (current_price - self.base_optimizer.VALLEY_PRICE) * r.efficiency
                cost = 0
            else:
                revenue = 0
                cost = abs(energy_kwh) * current_price

            commands.append(DispatchCommand(
                resource_id=resource_id,
                station_id=r.station_id,
                resource_type=r.resource_type,
                target_power_kw=round(actual_power, 2),
                duration_min=duration_min,
                priority=r.priority,
                estimated_revenue=round(revenue, 2),
                estimated_cost=round(cost, 2),
                dispatch_mode=mode,
            ))

        total_dispatch = sum(abs(c.target_power_kw) for c in commands)
        total_revenue = sum(c.estimated_revenue for c in commands)
        total_cost = sum(c.estimated_cost for c in commands)

        mode_label = {
            DispatchMode.ECONOMIC: "经济调度(LP优化)",
            DispatchMode.PEAK_SHAVING: "削峰填谷(LP优化)",
            DispatchMode.DEMAND_RESPONSE: "需求响应(LP优化)",
            DispatchMode.GRID_SUPPORT: "电网支撑(LP优化)",
        }.get(mode, "LP优化调度")

        trigger = (
            f"{mode_label}, 目标功率{abs(total_dispatch):.0f}kW, "
            f"求解时间{result.solve_time_ms:.1f}ms, 状态={result.solver_status}"
        )

        return DispatchPlan(
            plan_id=_make_plan_id("lp_"),
            mode=mode,
            trigger=trigger,
            stations_involved=list({c.station_id for c in commands}),
            commands=commands,
            total_dispatch_kw=round(total_dispatch, 2),
            estimated_revenue=round(total_revenue, 2),
            estimated_cost=round(total_cost, 2),
            net_profit=round(total_revenue - total_cost, 2),
        )

    def _fallback_dispatch(
        self, stations, resources, mode, peak_threshold_kw, dr_reward
    ) -> DispatchPlan:
        """回退到启发式调度

        ⚠️ DEF5: 启发式调度与 LP 优化语义不同 —— 启发式方法不接收 target_power_kw
        和 duration_min 上下文(各自内部用固定 15min 窗口和自有阈值逻辑), 因此 fallback
        出来的计划可能在目标功率匹配度和时长上与 LP 路径不一致。调用方应据此判读结果。
        """
        logger.warning(
            "LP回退到启发式调度(mode=%s): 启发式不接收 target_power_kw/duration_min 上下文, "
            "调度结果在功率匹配与时长上可能与 LP 路径存在差异",
            mode.value if hasattr(mode, 'value') else mode,
        )
        if mode == DispatchMode.ECONOMIC:
            return self.base_optimizer.optimize_economic_dispatch(stations, resources)
        elif mode == DispatchMode.PEAK_SHAVING:
            return self.base_optimizer.optimize_peak_shaving(
                stations, resources, peak_threshold_kw or 500
            )
        elif mode == DispatchMode.DEMAND_RESPONSE:
            from .dispatch_optimizer import GridSignal, GridSignalType
            signal = GridSignal(
                signal_type=GridSignalType.DEMAND_RESPONSE,
                timestamp=datetime.now(timezone.utc),
                reward_per_kwh=dr_reward,
            )
            return self.base_optimizer.handle_demand_response(stations, resources, signal)
        else:
            return self.base_optimizer.optimize_multi_station_coordination(stations, resources)

    def _empty_plan(self, stations, mode, reason) -> DispatchPlan:
        """生成空计划"""
        return DispatchPlan(
            plan_id=_make_plan_id("lp_empty_"),
            mode=mode,
            trigger=reason,
            stations_involved=[s.station_id for s in stations if s.online],
            commands=[],
            total_dispatch_kw=0,
            estimated_revenue=0,
            estimated_cost=0,
            net_profit=0,
        )


# ─── 单例 ───

_lp_optimizer: Optional[VPPLPOptimizer] = None
_lock = threading.Lock()


def get_vpp_lp_optimizer() -> VPPLPOptimizer:
    """获取LP优化器单例(线程安全, 双重检查锁)"""
    global _lp_optimizer
    if _lp_optimizer is None:
        with _lock:
            if _lp_optimizer is None:
                _lp_optimizer = VPPLPOptimizer()
                logger.info("VPP LP优化器初始化完成" + (" (scipy可用)" if HAS_SCIPY else " (scipy不可用，将回退到启发式)"))
    return _lp_optimizer
