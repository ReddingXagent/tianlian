"""预约费定价 CRUD 端点（拆分自原 pricing_management.py）。"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_v2 import ReservationFeePrice, ReservationPolicy

from ._shared import (
    _ROUTER_DEPENDENCIES,
    _parse_date,
    _fmt_date,
    _fmt_dt,
    ReservationFeeCreate,
    ReservationFeeUpdate,
)


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


def _rf_to_dict(o: ReservationFeePrice) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "deposit_amount": float(o.deposit_amount) if o.deposit_amount else 0.0,
        "reservation_policy": o.reservation_policy.value if o.reservation_policy else None,
        "fee_amount": float(o.fee_amount) if o.fee_amount else 0.0,
        "no_show_penalty": float(o.no_show_penalty) if o.no_show_penalty else 0.0,
        "effective_date": _fmt_date(o.effective_date),
        "expire_date": _fmt_date(o.expire_date),
        "is_active": o.is_active,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


@router.get("/pricing/mgmt/reservation")
def list_reservation_fees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ReservationFeePrice)
    if station_id is not None:
        q = q.filter(ReservationFeePrice.station_id == station_id)
    if is_active is not None:
        q = q.filter(ReservationFeePrice.is_active == is_active)
    total = q.count()
    items = q.order_by(ReservationFeePrice.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_rf_to_dict(i) for i in items], total, page, page_size)


@router.get("/pricing/mgmt/reservation/{item_id}")
def get_reservation_fee(item_id: int, db: Session = Depends(get_db)):
    o = db.query(ReservationFeePrice).filter(ReservationFeePrice.id == item_id).first()
    if not o:
        raise HTTPException(404, "预约费定价不存在")
    return success_response(_rf_to_dict(o))


@router.post("/pricing/mgmt/reservation")
def create_reservation_fee(body: ReservationFeeCreate, db: Session = Depends(get_db)):
    try:
        rp = ReservationPolicy(body.reservation_policy)
    except ValueError:
        raise HTTPException(400, f"无效的预约策略: {body.reservation_policy}")
    o = ReservationFeePrice(
        station_id=body.station_id,
        deposit_amount=Decimal(str(body.deposit_amount)),
        reservation_policy=rp,
        fee_amount=Decimal(str(body.fee_amount)),
        no_show_penalty=Decimal(str(body.no_show_penalty)),
        effective_date=_parse_date(body.effective_date),
        expire_date=_parse_date(body.expire_date) if body.expire_date else None,
        is_active=body.is_active,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return success_response(_rf_to_dict(o), "预约费定价创建成功")


@router.put("/pricing/mgmt/reservation/{item_id}")
def update_reservation_fee(item_id: int, body: ReservationFeeUpdate, db: Session = Depends(get_db)):
    o = db.query(ReservationFeePrice).filter(ReservationFeePrice.id == item_id).first()
    if not o:
        raise HTTPException(404, "预约费定价不存在")
    if body.station_id is not None:
        o.station_id = body.station_id
    if body.deposit_amount is not None:
        o.deposit_amount = Decimal(str(body.deposit_amount))
    if body.reservation_policy is not None:
        try:
            o.reservation_policy = ReservationPolicy(body.reservation_policy)
        except ValueError:
            raise HTTPException(400, f"无效的预约策略: {body.reservation_policy}")
    if body.fee_amount is not None:
        o.fee_amount = Decimal(str(body.fee_amount))
    if body.no_show_penalty is not None:
        o.no_show_penalty = Decimal(str(body.no_show_penalty))
    if body.effective_date is not None:
        o.effective_date = _parse_date(body.effective_date)
    if body.expire_date is not None:
        o.expire_date = _parse_date(body.expire_date)
    if body.is_active is not None:
        o.is_active = body.is_active
    db.commit()
    db.refresh(o)
    return success_response(_rf_to_dict(o), "预约费定价更新成功")


@router.delete("/pricing/mgmt/reservation/{item_id}")
def delete_reservation_fee(item_id: int, db: Session = Depends(get_db)):
    o = db.query(ReservationFeePrice).filter(ReservationFeePrice.id == item_id).first()
    if not o:
        raise HTTPException(404, "预约费定价不存在")
    db.delete(o)
    db.commit()
    return success_response(None, "预约费定价已删除")
