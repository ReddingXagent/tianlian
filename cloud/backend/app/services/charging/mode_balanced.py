"""均衡充电模式 — 光伏+储能+电网三源协同:优先光伏,其次储能,电网兜底"""
from __future__ import annotations

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)


class BalancedStrategy(ChargingStrategy):
    """均衡模式: 优先级 5

    能量优先级: 光伏 → 储能放电 → 电网
    - 光伏按 min(剩余需求, 光伏出力) 消纳
    - 储能放电受 SOC 保护(低于 BATTERY_DISCHARGE_SOC_MIN 不放电)
    - 电网兜底, 受 grid_power_limit_kw 上限约束
    - 总功率钳位到充电桩额定功率
    """

    BATTERY_DISCHARGE_SOC_MIN = 0.15  # 储能放电 SOC 下限(电池健康保护)

    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.BALANCED

    @property
    def priority(self) -> int:
        return 5

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        remaining = ctx.demand_power_kw

        # 1. 光伏优先消纳
        pv_use = max(0.0, min(remaining, ctx.pv_output_kw))
        remaining -= pv_use

        # 2. 储能放电(SOC 保护)
        battery_use = 0.0
        soc = ctx.battery_soc
        if remaining > 1e-9 and soc is not None and soc > self.BATTERY_DISCHARGE_SOC_MIN:
            battery_use = max(0.0, min(remaining, ctx.battery_available_kw))
            remaining -= battery_use

        # 3. 电网兜底(受上限约束)
        grid_use = 0.0
        if remaining > 1e-9:
            grid_use = remaining
            if ctx.grid_power_limit_kw is not None:
                grid_use = min(grid_use, ctx.grid_power_limit_kw)
            grid_use = max(0.0, grid_use)
            remaining -= grid_use

        # 4. 总功率钳位到额定功率 (rated_power_kw 为 None 或 <=0 时视为无限制,
        #    避免链式比较 total > None 抛 TypeError)
        total = pv_use + battery_use + grid_use
        rated = ctx.rated_power_kw
        if rated is not None and rated > 0 and total > rated:
            scale = rated / total
            pv_use *= scale
            battery_use *= scale
            grid_use *= scale
            total = rated

        curtailed = total < ctx.demand_power_kw - 1e-9
        reason = (
            f"均衡调度: 光伏{pv_use:.1f} + 储能{battery_use:.1f} + 电网{grid_use:.1f}kW"
        )

        decision = ChargingDecision(
            mode=ChargingMode.BALANCED,
            pv_power_kw=round(pv_use, 4),
            battery_power_kw=round(battery_use, 4),
            grid_power_kw=round(grid_use, 4),
            curtailed=curtailed,
            reason=reason,
        )
        decision.reconcile_source()
        return decision
