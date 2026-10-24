"""定时充电模式 — 依据峰谷时段调度:低谷满充、高峰停充"""
from __future__ import annotations

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)


class TimedStrategy(ChargingStrategy):
    """定时模式: 优先级 2

    - in_valley_period=True  → 低谷时段, 满功率充电(按需求, 钳位额定)
    - in_valley_period=False → 高峰时段, 停充(降为 0)
    - in_valley_period=None  → 无时段信息, 保守停充
    """

    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.TIMED

    @property
    def priority(self) -> int:
        return 2

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        if ctx.in_valley_period is True:
            target = self.clamp_power(ctx.demand_power_kw, ctx.rated_power_kw)
            reason = f"低谷时段满功率充电: {target:.1f}kW"
            curtailed = False
        elif ctx.in_valley_period is False:
            target = 0.0
            reason = "高峰时段停充(定时模式)"
            curtailed = True
        else:
            target = 0.0
            reason = "无时段信息,保守停充(定时模式)"
            curtailed = True

        decision = ChargingDecision(
            mode=ChargingMode.TIMED,
            grid_power_kw=target,
            curtailed=curtailed,
            reason=reason,
        )
        decision.reconcile_source()
        return decision
