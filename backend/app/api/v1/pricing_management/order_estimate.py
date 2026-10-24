"""订单费用估算联动端点（拆分自原 pricing_management.py）。

计费口径单一事实来源 (卡 b6c8faf3): 停车费/占桩费/服务费直接复用
billing_engine 纯函数, 消除双处各写一份规则导致的漂移; 金额全程 Decimal,
仅出口经 _to_amount 转 float, 舍入规则与 billing_engine (quantize TWO_PLACES,
ROUND_HALF_EVEN) 完全一致。
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.tasks.tz_utils import naive_utc_to_biz_wall, today_in_biz_tz
from app.models.pricing_v2 import EnergyPrice, ServiceFeePrice, ParkingPrice, OccupancyFeePrice
from app.services.billing_engine import (
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    _q,
    _to_amount,
)

from ._shared import _ROUTER_DEPENDENCIES, OrderEstimateRequest


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


@router.post("/pricing/mgmt/order-estimate")
def estimate_order_cost(body: OrderEstimateRequest, db: Session = Depends(get_db)):
    """根据当前生效的定价规则估算订单费用

    输入: 站点ID, 用户类型, 充电量(kWh), 充电时长(分), 停车时长(分), 占桩时长(分)
    输出: 充电费 + 服务费 + 停车费 + 占桩费 = 总费用

    电费为预估值(多时段均价 × 电量, Decimal 化): 估价时无实际充电起止时间,
    无法走 TOU 拆分, 保留均价口径但舍入规则与引擎对齐。
    """
    today = today_in_biz_tz()
    energy_cost = Decimal("0.00")
    service_fee = Decimal("0.00")
    parking_fee = Decimal("0.00")
    occupancy_fee = Decimal("0.00")

    # 1. 充电费: 取站点下所有生效时段电价的加权平均
    energy_prices = db.query(EnergyPrice).filter(
        EnergyPrice.station_id == body.station_id,
        EnergyPrice.is_active == True,
        EnergyPrice.effective_date <= today,
    ).all()
    active_energy = [
        ep for ep in energy_prices
        if ep.expire_date is None or ep.expire_date >= today
    ]
    if active_energy:
        avg_price = sum(_q(ep.price_per_kwh) for ep in active_energy) / len(active_energy)
        energy_cost = (avg_price * Decimal(str(body.energy_kwh))).quantize(Decimal("0.01"))

    # 2. 服务费: 按用户类型获取 (计算复用 billing_engine.compute_service_fee_multi)
    service_fees = db.query(ServiceFeePrice).filter(
        ServiceFeePrice.station_id == body.station_id,
        ServiceFeePrice.is_active == True,
        ServiceFeePrice.effective_date <= today,
    ).all()
    active_sf = [
        sf for sf in service_fees
        if sf.expire_date is None or sf.expire_date >= today
    ]
    # 匹配用户类型, fallback to app
    matched_sf = None
    for sf in active_sf:
        if sf.user_type and sf.user_type.value == body.user_type:
            matched_sf = sf
            break
    if not matched_sf and active_sf:
        matched_sf = active_sf[0]
    if matched_sf:
        service_fee = compute_service_fee_multi(
            Decimal(str(body.energy_kwh)),
            matched_sf.fee_type.value if matched_sf.fee_type else "percent",
            matched_sf.fee_value,
        )

    # 3. 停车费 (规则计算复用 billing_engine.compute_parking_fee_full:
    #    免费/夜间/每24h封顶语义与实收一致)
    parking = db.query(ParkingPrice).filter(
        ParkingPrice.station_id == body.station_id,
        ParkingPrice.is_active == True,
        ParkingPrice.effective_date <= today,
    ).first()
    active_parking = parking if parking and (parking.expire_date is None or parking.expire_date >= today) else None
    if active_parking and body.parking_minutes > 0:
        # 夜间费率分摊需要 start_time (卡 c13ac16b): 归一为业务时区墙钟,
        # 与实收路径 occupancy_fee_service 的 _wall 口径一致; 缺省取当前时刻。
        parking_start_raw = body.parking_start or datetime.now(timezone.utc)
        parking_start_wall = naive_utc_to_biz_wall(parking_start_raw)
        parking_fee = compute_parking_fee_full(
            body.parking_minutes,
            {
                "free_minutes": active_parking.free_minutes,
                "hourly_rate": active_parking.hourly_rate,
                "daily_cap": active_parking.daily_cap,
                "enable_night_rate": active_parking.enable_night_rate,
                "night_rate": active_parking.night_rate,
                "night_start": active_parking.night_start,
                "night_end": active_parking.night_end,
            },
            start_time=parking_start_wall,
        )["total"]

    # 4. 占桩费 (规则计算复用 billing_engine.compute_occupancy_fee_full:
    #    宽限/费率/单次封顶语义与实收一致)
    occupancy = db.query(OccupancyFeePrice).filter(
        OccupancyFeePrice.station_id == body.station_id,
        OccupancyFeePrice.is_active == True,
        OccupancyFeePrice.effective_date <= today,
    ).first()
    active_occ = occupancy if occupancy and (occupancy.expire_date is None or occupancy.expire_date >= today) else None
    if active_occ and body.occupancy_minutes > 0:
        occupancy_fee = compute_occupancy_fee_full(
            body.occupancy_minutes,
            {
                "grace_minutes": active_occ.grace_minutes,
                "rate_per_minute": active_occ.rate_per_minute,
                "max_fee": active_occ.max_fee,
            },
        )

    fee_breakdown = {
        "energy_cost": _to_amount(energy_cost),
        "service_fee": _to_amount(service_fee),
        "parking_fee": _to_amount(parking_fee),
        "occupancy_fee": _to_amount(occupancy_fee),
    }
    fee_breakdown["total"] = _to_amount(
        (energy_cost + service_fee + parking_fee + occupancy_fee).quantize(Decimal("0.01"))
    )
    return success_response(fee_breakdown, "费用估算完成")
