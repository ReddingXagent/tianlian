"""多策略仲裁层 — SPEC §4 (多策略并行 + 仲裁) + §4.3 (安全底线)

各储能策略并行运行, 各自独立产出「功率建议」(StrategyAdvice), 仲裁器合成
最终功率指令 (ArbitrationResult)。独立于现有 StrategyEngine (单策略互斥),
作为上层编排, **不破坏现有 StrategyEngine 契约** (预研 §6 风险1)。

功率方向约定 (与底层 storage_optimizer「正充负放」解耦, 用显式方向 + 绝对值):
- StrategyAdvice.direction ∈ {charge, discharge, idle}
- StrategyAdvice.power_kw ≥ 0 (绝对值, 不带符号)

仲裁规则 (SPEC §4):
- 反向冲突 (一策略充、另一放): 按策略优先级裁决胜出方向,
  默认 保供 > 安全 > 需量 > 增容 > 套利 > 消纳 (数字越小越高)。
- 同向叠加 (多策略同向): 默认取最大功率建议 (MAX, 不叠加); 可选 STACK 叠加
  (受 stack_cap_kw 上限) 或 WEIGHTED 权重加权。
- 硬约束 (SPEC §4.3, 不可被配置突破): SOC 底线 / SOC 上限 / BMS 功率 / 循环次数
  → 裁剪后下发, 每次产出决策日志 (哪个策略胜出、为什么)。

strategy_config JSON schema (来自 station_energy_strategy.strategy_config):
    {
      "arbitration_mode": "max" | "stack" | "weighted",   # 仲裁模式, 默认 "max"
      "stack_cap_kw": <float>,                             # stack 模式同向叠加上限 (kW)
      "priorities": {                                      # 优先级覆盖 (数字越小越高)
        "backup": 1, "safety": 2, "demand": 3,
        "boosting": 4, "arbitrage": 5, "solar_absorb": 6
      },
      "strategies": {                                      # 各策略开关/阈值 (策略自身消费, 仲裁器不解释)
        "arbitrage": {"enabled": true, "min_spread": 0.3},
        "boosting": {"enabled": true},
        "demand": {"enabled": false},
        "backup": {"enabled": true, "reserve_soc": 0.2},
        "solar_absorb": {"enabled": true}
      }
    }
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    """储能策略类型 (对齐 SPEC §4 优先级链: 保供 > 安全 > 需量 > 增容 > 套利 > 消纳)

    SAFETY 为电池安全/健康保护策略 (StorageOptimizer 已有的 SOC/温度保护是其运行时体现),
    优先级仅次于保供, 不可被业务策略配置突破。
    """
    BACKUP = "backup"            # 保供预留 (离网/弱网保供)
    SAFETY = "safety"            # 安全/电池健康保护
    DEMAND = "demand"            # 需量管理 (两部制, P2)
    BOOSTING = "boosting"        # 动态增容
    ARBITRAGE = "arbitrage"      # 峰谷套利
    SOLAR_ABSORB = "solar_absorb"  # 新能源消纳


# 默认优先级序 (数字越小越高): 保供 > 安全 > 需量 > 增容 > 套利 > 消纳
DEFAULT_PRIORITY: Dict[StrategyType, int] = {
    StrategyType.BACKUP: 1,
    StrategyType.SAFETY: 2,
    StrategyType.DEMAND: 3,
    StrategyType.BOOSTING: 4,
    StrategyType.ARBITRAGE: 5,
    StrategyType.SOLAR_ABSORB: 6,
}


class AdviceDirection(str, Enum):
    """功率建议方向"""
    CHARGE = "charge"        # 充电 (功率入储能)
    DISCHARGE = "discharge"  # 放电 (储能对外输出)
    IDLE = "idle"            # 保持/待机


class ArbitrationMode(str, Enum):
    """同向合成模式"""
    MAX = "max"          # 默认: 取最大功率建议 (不叠加)
    STACK = "stack"      # 同向叠加, 受 stack_cap_kw 限制
    WEIGHTED = "weighted"  # 按权重加权合成


@dataclass
class StrategyAdvice:
    """单个策略产出的功率建议

    power_kw 为绝对值 (≥0), 方向由 direction 表达, 避免带符号歧义。
    """
    strategy_type: StrategyType
    direction: AdviceDirection
    power_kw: float = 0.0
    weight: float = 1.0            # WEIGHTED 模式用
    reason: str = ""


@dataclass
class HardConstraints:
    """硬约束 (SPEC §4.3, 不可被配置突破) — 裁剪最终指令"""
    soc: float                            # 当前 SOC (0-1), 必填
    soc_floor: float = 0.10               # SOC 下限, 低于此禁止放电
    soc_ceiling: float = 0.90             # SOC 上限, 高于此禁止充电
    bms_max_charge_kw: Optional[float] = None      # BMS 最大充电功率
    bms_max_discharge_kw: Optional[float] = None   # BMS 最大放电功率
    cycles_today: int = 0                          # 当日已用循环次数
    max_daily_cycles: Optional[int] = None         # 日最大循环次数 (None=不限)


@dataclass
class ArbitrationResult:
    """仲裁产出: 最终功率指令 + 决策日志"""
    direction: AdviceDirection
    power_kw: float                                  # 裁剪后最终功率 (绝对值)
    winning_strategy: Optional[StrategyType] = None  # 胜出策略
    mode: ArbitrationMode = ArbitrationMode.MAX
    decision_log: List[dict] = field(default_factory=list)  # 每条建议的采纳记录
    reason: str = ""


class EnergyArbitrator:
    """多策略仲裁器 — 合成多个 StrategyAdvice 为最终功率指令"""

    def __init__(
        self,
        priority_override: Optional[Dict[StrategyType, int]] = None,
        default_mode: ArbitrationMode = ArbitrationMode.MAX,
        stack_cap_kw: Optional[float] = None,
    ) -> None:
        """
        Args:
            priority_override: 场站级优先级覆盖 (数字越小越高), 未覆盖者走 DEFAULT_PRIORITY。
            default_mode: 同向合成模式 (MAX/STACK/WEIGHTED)。
            stack_cap_kw: STACK 模式同向叠加上限 (kW), None=不限。
        """
        self._priority_override: Dict[StrategyType, int] = priority_override or {}
        self._default_mode = default_mode
        self._stack_cap_kw = stack_cap_kw

    # ─── 对外 ───

    def arbitrate(
        self,
        advices: List[StrategyAdvice],
        constraints: HardConstraints,
    ) -> ArbitrationResult:
        """仲裁入口: 输入各策略建议 + 硬约束 → 最终指令。
        
        异常时返回 IDLE 安全结果, 保证充电调度不因仲裁异常全面崩溃。
        """
        try:
            if not advices or constraints is None:
                return ArbitrationResult(
                    direction=AdviceDirection.IDLE,
                    power_kw=0.0,
                    reason="无策略建议或约束缺失, 保持待机",
                )
            
            # 决策日志: 只为非 None 建议建条目, 同步建 id→entry 映射。
            # 标记阶段按 id 查回 entry, 避免 enumerate(advices) 原始 idx 与「过滤后 log」索引错位
            # (advices 含 None 时 idx 会指错条目或越界, 见卡 f5017f52 缺陷2)。
            log: List[dict] = []
            log_by_id: Dict[int, dict] = {}
            for a in advices:
                if a is None:
                    continue
                entry = self._log_entry(a, accepted=False)
                log.append(entry)
                log_by_id[id(a)] = entry

            active = [
                a for a in advices
                if a is not None and a.direction != AdviceDirection.IDLE and a.power_kw > 1e-9
            ]
            if not active:
                return ArbitrationResult(
                    direction=AdviceDirection.IDLE,
                    power_kw=0.0,
                    winning_strategy=None,
                    mode=self._default_mode,
                    decision_log=log,
                    reason="无活跃策略建议, 保持待机",
                )

            chargers = [a for a in active if a.direction == AdviceDirection.CHARGE]
            dischargers = [a for a in active if a.direction == AdviceDirection.DISCHARGE]

            if chargers and dischargers:
                # 反向冲突: 按组内最高优先级裁决胜出方向
                best_charge = min(chargers, key=lambda a: self._priority(a.strategy_type))
                best_discharge = min(dischargers, key=lambda a: self._priority(a.strategy_type))
                if self._priority(best_discharge.strategy_type) < self._priority(best_charge.strategy_type):
                    winner_group, direction, conflict_reason = (
                        dischargers, AdviceDirection.DISCHARGE,
                        f"反向冲突: 放电组最高优先级策略 {best_discharge.strategy_type.value} "
                        f"(prio={self._priority(best_discharge.strategy_type)}) 胜出",
                    )
                else:
                    winner_group, direction, conflict_reason = (
                        chargers, AdviceDirection.CHARGE,
                        f"反向冲突: 充电组最高优先级策略 {best_charge.strategy_type.value} "
                        f"(prio={self._priority(best_charge.strategy_type)}) 胜出",
                    )
            elif dischargers:
                winner_group, direction, conflict_reason = dischargers, AdviceDirection.DISCHARGE, "同向放电"
            else:
                winner_group, direction, conflict_reason = chargers, AdviceDirection.CHARGE, "同向充电"

            raw_power, top_strategy = self._combine(winner_group)
            winner = top_strategy if top_strategy is not None else winner_group[0].strategy_type

            final_direction, final_power, clip_reason = self._apply_constraints(
                direction, raw_power, constraints
            )

            # 标记决策日志: 胜出方向内的建议标采纳 (用 id 做身份比较, 避免 dataclass 值相等误判)
            winner_ids = {id(a) for a in winner_group}
            for a in advices:
                if a is None:
                    continue
                entry = log_by_id.get(id(a))
                if entry is None:
                    continue
                entry["accepted"] = (
                    final_direction != AdviceDirection.IDLE
                    and id(a) in winner_ids
                    and a.direction == final_direction
                )

            parts = [conflict_reason, f"胜出策略 {winner.value}"]
            if clip_reason:
                parts.append(clip_reason)
            return ArbitrationResult(
                direction=final_direction,
                power_kw=round(final_power, 4),
                winning_strategy=winner if final_direction != AdviceDirection.IDLE else None,
                mode=self._default_mode,
                decision_log=log,
                reason="; ".join(parts),
            )
        except Exception as e:
            logger.warning("arbitrate 仲裁异常: %s, 返回 IDLE 安全结果", e)
            return ArbitrationResult(
                direction=AdviceDirection.IDLE,
                power_kw=0.0,
                reason=f"仲裁异常: {e}",
            )

    # ─── 内部 ───

    def _priority(self, stype: StrategyType) -> int:
        return self._priority_override.get(stype, DEFAULT_PRIORITY[stype])

    def _combine(self, group: List[StrategyAdvice]) -> tuple:
        """同向合成: 返回 (合成功率, 代表策略)。异常返回 (0, None)。"""
        try:
            if not group:
                return 0.0, None
            top = max(group, key=lambda a: a.power_kw)
            if self._default_mode == ArbitrationMode.STACK:
                total = sum(a.power_kw for a in group)
                if self._stack_cap_kw is not None:
                    total = min(total, self._stack_cap_kw)
                return total, top.strategy_type
            if self._default_mode == ArbitrationMode.WEIGHTED:
                weight_sum = sum(a.weight for a in group)
                if weight_sum <= 1e-9:
                    return top.power_kw, top.strategy_type
                blended = sum(a.power_kw * a.weight for a in group) / weight_sum
                return blended, top.strategy_type
            # MAX (默认)
            return top.power_kw, top.strategy_type
        except Exception as e:
            logger.warning("_combine 异常: %s, 返回 (0, None)", e)
            return 0.0, None

    @staticmethod
    def _apply_constraints(
        direction: AdviceDirection,
        power: float,
        c: HardConstraints,
    ) -> tuple:
        """硬约束裁剪 → (final_direction, final_power, reason)。异常返回 IDLE。"""
        try:
            # soc 必须有限值: NaN/inf 穿透 isinstance(int,float), 且令所有大小比较恒为 False,
            # 会导致 soc<=floor 与 soc>=ceiling 双双不触发 → 充放电硬约束均被放行 (严重安全隐患)。
            # 电池状态未知 → 禁止任何动作 (卡 f5017f52 缺陷1)。
            soc_raw = c.soc
            if not (isinstance(soc_raw, (int, float)) and math.isfinite(soc_raw)):
                return (
                    AdviceDirection.IDLE, 0.0,
                    f"SOC 非有限值 ({soc_raw!r}), 电池状态未知, 禁止充放",
                )
            soc = float(soc_raw)
            # soc_floor/soc_ceiling 非有限 → 回退默认 (仍可正常裁剪, 不必 IDLE)
            soc_floor = (
                c.soc_floor
                if isinstance(c.soc_floor, (int, float)) and math.isfinite(c.soc_floor)
                else 0.10
            )
            soc_ceiling = (
                c.soc_ceiling
                if isinstance(c.soc_ceiling, (int, float)) and math.isfinite(c.soc_ceiling)
                else 0.90
            )

            # 功率必须有限: inf 穿过 active 过滤 (power_kw>1e-9) 与 MAX 同向合成无截断,
            # 旧码会下发 inf (卡 f5017f52 缺陷3)。
            if not math.isfinite(power):
                return (
                    AdviceDirection.IDLE, 0.0,
                    f"功率非有限值 ({power!r}), 禁止下发",
                )

            # 循环寿命保护: 连充放都禁 (SPEC §4.3)
            if c.max_daily_cycles is not None and c.cycles_today >= c.max_daily_cycles:
                return (
                    AdviceDirection.IDLE, 0.0,
                    f"当日循环次数 {c.cycles_today} 已达上限 {c.max_daily_cycles}, 禁止充放",
                )

            if direction == AdviceDirection.DISCHARGE:
                if soc <= soc_floor:
                    return (
                        AdviceDirection.IDLE, 0.0,
                        f"SOC={soc:.0%} 低于底线 {soc_floor:.0%}, 禁止套利性放电",
                    )
                if c.bms_max_discharge_kw is not None:
                    power = min(power, c.bms_max_discharge_kw)
                return direction, power, ""

            if direction == AdviceDirection.CHARGE:
                if soc >= soc_ceiling:
                    return (
                        AdviceDirection.IDLE, 0.0,
                        f"SOC={soc:.0%} 高于上限 {soc_ceiling:.0%}, 禁止充电",
                    )
                if c.bms_max_charge_kw is not None:
                    power = min(power, c.bms_max_charge_kw)
                return direction, power, ""

            return direction, power, ""
        except Exception as e:
            logger.warning("_apply_constraints 异常: %s, 返回 IDLE", e)
            return AdviceDirection.IDLE, 0.0, f"硬约束裁剪异常: {e}"

    @staticmethod
    def _log_entry(advice: StrategyAdvice, accepted: bool = False) -> dict:
        return {
            "strategy_type": advice.strategy_type.value,
            "direction": advice.direction.value,
            "power_kw": round(advice.power_kw, 4),
            "weight": advice.weight,
            "reason": advice.reason,
            "accepted": accepted,
        }
