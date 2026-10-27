"""电价优先充电模式 — 低谷电价时段集中充电,高电价时段暂停"""
from __future__ import annotations

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)


class PriceStrategy(ChargingStrategy):
    """电价优先模式: 优先级 4

    - grid_price <= VALLEY_THRESHOLD → 低谷, 集中充电(按需求)
    - grid_price >  VALLEY_THRESHOLD → 高电价, 暂停充电
    - grid_price is None             → 无电价信息, 默认允许充电(不阻塞用户)
    """

    VALLEY_THRESHOLD = 0.50  # 元/kWh, 低谷充电阈值

    @property
    def mode(self) -> ChargingMode:
        return ChargingMode.PRICE

    @property
    def priority(self) -> int:
        return 4

    def evaluate(self, ctx: ChargingContext) -> ChargingDecision:
        price = ctx.grid_price

        if price is None:
            target = self.clamp_power(ctx.demand_power_kw, ctx.rated_power_kw)
            reason = "无电价信息,按需求充电(电价优先)"
            curtailed = False
        elif price <= self.VALLEY_THRESHOLD:
            target = self.clamp_power(ctx.demand_power_kw, ctx.rated_power_kw)
            reason = f"低谷电价{price:.2f}元/kWh,集中充电: {target:.1f}kW"
            curtailed = False
        else:
            target = 0.0
            reason = f"高电价{price:.2f}元/kWh,暂停充电(电价优先)"
            curtailed = True

        decision = ChargingDecision(
            mode=ChargingMode.PRICE,
            grid_power_kw=target,
            curtailed=curtailed,
            reason=reason,
        )
        decision.reconcile_source()
        return decision
