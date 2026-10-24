"""
运营概览 API - 运营Dashboard指标
GET /api/v1/operate/overview — 运营概览（充电点/桩数/使用率/累计营收/充电量/时长/次数）
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.response import success_response
from app.models.station import Station
from app.models.device import Device
from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin

router = APIRouter(dependencies=[Depends(get_current_user)])

logger = logging.getLogger(__name__)


@router.get("/overview", summary="运营概览")
def operate_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取运营概览卡片数据"""
    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        # team scoping（任务卡 ab5c5f17）：非 admin 仅统计本 team 站点/设备/订单（经 station→team）。
        scoped = not is_platform_admin(user)
        tid = user.team_id

        def _station_filter(q):
            return q.filter(Station.team_id == tid) if scoped else q

        def _device_filter(q):
            # Device 经 station→team 归属；admin 不过滤。
            return q.join(Station, Device.station_id == Station.id).filter(Station.team_id == tid) if scoped else q

        def _order_filter(q):
            # ChargingOrder 经 station→team 归属；admin 不过滤。
            return q.join(Station, ChargingOrder.station_id == Station.id).filter(Station.team_id == tid) if scoped else q

        # 站/桩统计
        station_count = _station_filter(db.query(func.count(Station.id))).scalar() or 0
        device_count = _device_filter(db.query(func.count(Device.id))).scalar() or 0
        active_devices = _device_filter(
            db.query(func.count(Device.id)).filter(Device.status == "online")
        ).scalar() or 0
        usage_rate = round((active_devices / device_count * 100) if device_count > 0 else 0, 1)

        # 累计统计
        total_revenue = _order_filter(
            db.query(func.coalesce(func.sum(ChargingOrder.paid_amount), 0)).filter(
                ChargingOrder.payment_status == OrderPaymentStatus.PAID
            )
        ).scalar() or Decimal("0.00")

        total_kwh = _order_filter(
            db.query(func.coalesce(func.sum(ChargingOrder.charged_kwh), 0)).filter(
                ChargingOrder.order_status == OrderStatus.COMPLETED
            )
        ).scalar() or Decimal("0.00")

        total_minutes = _order_filter(
            db.query(func.coalesce(func.sum(ChargingOrder.duration_minutes), 0)).filter(
                ChargingOrder.order_status == OrderStatus.COMPLETED
            )
        ).scalar() or 0

        total_orders = _order_filter(
            db.query(func.count(ChargingOrder.id)).filter(
                ChargingOrder.order_status == OrderStatus.COMPLETED
            )
        ).scalar() or 0

        # 今日营收
        today_revenue = _order_filter(
            db.query(func.coalesce(func.sum(ChargingOrder.paid_amount), 0)).filter(
                ChargingOrder.payment_status == OrderPaymentStatus.PAID,
                ChargingOrder.created_at >= today_start
            )
        ).scalar() or Decimal("0.00")

        # 昨日营收（环比用）
        yesterday_revenue = _order_filter(
            db.query(func.coalesce(func.sum(ChargingOrder.paid_amount), 0)).filter(
                ChargingOrder.payment_status == OrderPaymentStatus.PAID,
                ChargingOrder.created_at >= yesterday_start,
                ChargingOrder.created_at < today_start
            )
        ).scalar() or Decimal("0.00")

        # 环比
        yesterday_float = float(yesterday_revenue)
        today_float = float(today_revenue)
        mom_change = round(((today_float - yesterday_float) / yesterday_float * 100) if yesterday_float > 0 else 0, 2)

        return success_response({
            "station_count": station_count,
            "device_count": device_count,
            "usage_rate": usage_rate,
            "total_revenue": float(total_revenue),
            "total_kwh": float(total_kwh),
            "total_hours": round(total_minutes / 60, 1),
            "total_orders": total_orders,
            "today_revenue": today_float,
            "yesterday_revenue": yesterday_float,
            "revenue_mom_change": mom_change,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("operate_overview 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")