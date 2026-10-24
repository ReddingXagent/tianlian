"""光伏优先充电模式 — 光伏出力大于需求则按需求充,否则降功率至光伏水平"""
from __future__ import annotations

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)


class SolarStrategy(ChargingStrategy):
    """光伏优先模式: 优先级 3

    仅使用光伏能量, 不从电网取电:
    - 光伏 >= 需求 → 按需求充(target = demand)
    - 光伏 <  需求 → 降功率至光伏水平(target = pv), 标记 curtailed
    """

    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.SOLAR

    @property
    def priority(self) -> int:
        return 3

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        demand = ctx.demand_power_kw
        pv = ctx.pv_output_kw

        target = self.clamp_power(min(demand, pv), ctx.rated_power_kw)
        curtailed = target < demand - 1e-9

        reason = (
            f"光伏优先: 光伏{pv:.1f}kW, 需求{demand:.1f}kW → 充电{target:.1f}kW"
            + ("(降功率)" if curtailed else "(光伏充足)")
        )

        decision = ChargingDecision(
            mode=ChargingMode.SOLAR,
            pv_power_kw=target,
            curtailed=curtailed,
            reason=reason,
        )
        decision.reconcile_source()
        return decision
