"""手动充电模式 — 用户直接指定功率,策略不做自动调整"""
from __future__ import annotations

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)


class ManualStrategy(ChargingStrategy):
    """手动模式: 优先级最高(1)

    - 若上下文指定 manual_power_kw, 按其充电(钳位到额定功率)
    - 否则回落到车辆充电需求 demand_power_kw
    """

    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.MANUAL

    @property
    def priority(self) -> int:
        return 1

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        if ctx.manual_power_kw is not None:
            target = self.clamp_power(ctx.manual_power_kw, ctx.rated_power_kw)
            source = "用户手动设定"
        else:
            target = self.clamp_power(ctx.demand_power_kw, ctx.rated_power_kw)
            source = "按需求(未设定手动功率)"

        decision = ChargingDecision(
            mode=ChargingMode.MANUAL,
            grid_power_kw=target,
            curtailed=False,
            reason=f"手动模式[{source}]: {target:.1f}kW",
        )
        decision.reconcile_source()
        return decision
