"""
财务管理 API - 充电费/停车费/占桩费/预约费/退款管理
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.station import Station
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_station_team_access

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/financial/charges", summary="充电费记录")
def list_charges(
    station_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """电费明细列表"""
    q = db.query(ChargingOrder).filter(ChargingOrder.payment_status == OrderPaymentStatus.PAID)
    # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
    if not is_platform_admin(user):
        q = q.join(Station, ChargingOrder.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if station_id:
        # 非 admin 校验 station 归属本 team，越权站点 → 404（不泄露存在）。
        if not is_platform_admin(user):
            assert_station_team_access(db, station_id, user)
        q = q.filter(ChargingOrder.station_id == station_id)
    if start_date:
        q = q.filter(ChargingOrder.created_at >= start_date)
    if end_date:
        q = q.filter(ChargingOrder.created_at < end_date)

    try:
        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        stations = {s.id: s.name for s in db.query(Station).all()}
    except Exception:
        logger.exception("充电费记录查询失败 user=%s", user.id)
        raise HTTPException(status_code=500, detail="查询失败")

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "order_no": r.order_no,
            "station_name": stations.get(r.station_id, f"站点#{r.station_id}"),
            "plate_number": r.plate_number,
            "charged_kwh": float(r.charged_kwh) if r.charged_kwh else 0,
            "electricity_fee": float(r.electricity_fee) if r.electricity_fee else 0,
            "total_amount": float(r.total_amount) if r.total_amount else 0,
            "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
            "payment_method": r.payment_method.value if r.payment_method else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return success_response({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/financial/parking", summary="停车费记录")
def list_parking_fees(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """停车费记录（从充电订单中提取停车费）"""
    q = db.query(ChargingOrder).filter(ChargingOrder.parking_fee > 0)
    # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
    if not is_platform_admin(user):
        q = q.join(Station, ChargingOrder.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if start_date:
        q = q.filter(ChargingOrder.created_at >= start_date)
    if end_date:
        q = q.filter(ChargingOrder.created_at < end_date)

    try:
        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        stations = {s.id: s.name for s in db.query(Station).all()}
    except Exception:
        logger.exception("停车费记录查询失败 user=%s", user.id)
        raise HTTPException(status_code=500, detail="查询失败")

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "order_no": r.order_no,
            "station_name": stations.get(r.station_id, f"站点#{r.station_id}"),
            "plate_number": r.plate_number,
            "parking_fee": float(r.parking_fee) if r.parking_fee else 0,
            "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return success_response({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/financial/occupancy", summary="占桩费记录")
def list_occupancy_fees(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """超时占用费记录"""
    q = db.query(ChargingOrder).filter(ChargingOrder.idle_penalty > 0)
    # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
    if not is_platform_admin(user):
        q = q.join(Station, ChargingOrder.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if start_date:
        q = q.filter(ChargingOrder.created_at >= start_date)
    if end_date:
        q = q.filter(ChargingOrder.created_at < end_date)

    try:
        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        stations = {s.id: s.name for s in db.query(Station).all()}
    except Exception:
        logger.exception("占桩费记录查询失败 user=%s", user.id)
        raise HTTPException(status_code=500, detail="查询失败")

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "order_no": r.order_no,
            "station_name": stations.get(r.station_id, f"站点#{r.station_id}"),
            "plate_number": r.plate_number,
            "idle_penalty": float(r.idle_penalty) if r.idle_penalty else 0,
            "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return success_response({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/financial/reservations", summary="预约费记录")
def list_reservation_fees(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """预约费记录"""
    q = db.query(ChargingOrder).filter(ChargingOrder.reservation_fee > 0)
    # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
    if not is_platform_admin(user):
        q = q.join(Station, ChargingOrder.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if start_date:
        q = q.filter(ChargingOrder.created_at >= start_date)
    if end_date:
        q = q.filter(ChargingOrder.created_at < end_date)

    try:
        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    except Exception:
        logger.exception("预约费记录查询失败 user=%s", user.id)
        raise HTTPException(status_code=500, detail="查询失败")

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "order_no": r.order_no,
            "reservation_fee": float(r.reservation_fee) if r.reservation_fee else 0,
            "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return success_response({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/financial/refunds", summary="退款管理")
def list_refunds(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """退款记录（退款中的订单）"""
    q = db.query(ChargingOrder).filter(
        ChargingOrder.payment_status.in_([OrderPaymentStatus.REFUNDING, OrderPaymentStatus.REFUNDED, OrderPaymentStatus.PARTIAL])
    )
    # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 站点的订单（经 station→team）。
    if not is_platform_admin(user):
        q = q.join(Station, ChargingOrder.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    if start_date:
        q = q.filter(ChargingOrder.created_at >= start_date)
    if end_date:
        q = q.filter(ChargingOrder.created_at < end_date)

    try:
        total = q.count()
        rows = q.order_by(ChargingOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        stations = {s.id: s.name for s in db.query(Station).all()}
    except Exception:
        logger.exception("退款记录查询失败 user=%s", user.id)
        raise HTTPException(status_code=500, detail="查询失败")

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "order_no": r.order_no,
            "station_name": stations.get(r.station_id, f"站点#{r.station_id}"),
            "paid_amount": float(r.paid_amount) if r.paid_amount else 0,
            "payment_status": r.payment_status.value if r.payment_status else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return success_response({"items": items, "total": total, "page": page, "page_size": page_size})