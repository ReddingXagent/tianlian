"""服务费定价 CRUD 端点（拆分自原 pricing_management.py）。"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_v2 import ServiceFeePrice, UserType, FeeType

from ._shared import (
    _ROUTER_DEPENDENCIES,
    _parse_date,
    _fmt_date,
    _fmt_dt,
    assert_no_effective_overlap,
    ServiceFeeCreate,
    ServiceFeeUpdate,
)


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


def _sf_to_dict(o: ServiceFeePrice) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "user_type": o.user_type.value if o.user_type else None,
        "fee_type": o.fee_type.value if o.fee_type else None,
        "fee_value": float(o.fee_value) if o.fee_value else 0.0,
        "effective_date": _fmt_date(o.effective_date),
        "expire_date": _fmt_date(o.expire_date),
        "is_active": o.is_active,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


@router.get("/pricing/mgmt/service-fee")
def list_service_fees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ServiceFeePrice)
    if station_id is not None:
        q = q.filter(ServiceFeePrice.station_id == station_id)
    if is_active is not None:
        q = q.filter(ServiceFeePrice.is_active == is_active)
    total = q.count()
    items = q.order_by(ServiceFeePrice.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_sf_to_dict(i) for i in items], total, page, page_size)


@router.get("/pricing/mgmt/service-fee/{item_id}")
def get_service_fee(item_id: int, db: Session = Depends(get_db)):
    o = db.query(ServiceFeePrice).filter(ServiceFeePrice.id == item_id).first()
    if not o:
        raise HTTPException(404, "服务费定价不存在")
    return success_response(_sf_to_dict(o))


@router.post("/pricing/mgmt/service-fee")
def create_service_fee(body: ServiceFeeCreate, db: Session = Depends(get_db)):
    try:
        ut = UserType(body.user_type)
    except ValueError:
        raise HTTPException(400, f"无效的用户类型: {body.user_type}")
    try:
        ft = FeeType(body.fee_type)
    except ValueError:
        raise HTTPException(400, f"无效的费用类型: {body.fee_type}")
    effective = _parse_date(body.effective_date)
    expire = _parse_date(body.expire_date) if body.expire_date else None
    if body.is_active:
        # 缺陷1: 同 (station, user_type) 重叠生效期会让下游 .first() 选取不确定 → 拒绝(409)
        assert_no_effective_overlap(
            db, ServiceFeePrice,
            dims={ServiceFeePrice.station_id: body.station_id, ServiceFeePrice.user_type: ut},
            effective=effective, expire=expire, label="服务费定价",
        )
    o = ServiceFeePrice(
        station_id=body.station_id,
        user_type=ut,
        fee_type=ft,
        fee_value=Decimal(str(body.fee_value)),
        effective_date=effective,
        expire_date=expire,
        is_active=body.is_active,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return success_response(_sf_to_dict(o), "服务费定价创建成功")


@router.put("/pricing/mgmt/service-fee/{item_id}")
def update_service_fee(item_id: int, body: ServiceFeeUpdate, db: Session = Depends(get_db)):
    o = db.query(ServiceFeePrice).filter(ServiceFeePrice.id == item_id).first()
    if not o:
        raise HTTPException(404, "服务费定价不存在")
    if body.station_id is not None:
        o.station_id = body.station_id
    if body.user_type is not None:
        try:
            o.user_type = UserType(body.user_type)
        except ValueError:
            raise HTTPException(400, f"无效的用户类型: {body.user_type}")
    if body.fee_type is not None:
        try:
            o.fee_type = FeeType(body.fee_type)
        except ValueError:
            raise HTTPException(400, f"无效的费用类型: {body.fee_type}")
    if body.fee_value is not None:
        o.fee_value = Decimal(str(body.fee_value))
    if body.effective_date is not None:
        o.effective_date = _parse_date(body.effective_date)
    if body.expire_date is not None:
        o.expire_date = _parse_date(body.expire_date)
    if body.is_active is not None:
        o.is_active = body.is_active
    # 缺陷1: 按更新后的值做重叠校验(同 station+user_type), 排除自身
    if o.is_active:
        assert_no_effective_overlap(
            db, ServiceFeePrice,
            dims={ServiceFeePrice.station_id: o.station_id, ServiceFeePrice.user_type: o.user_type},
            effective=o.effective_date, expire=o.expire_date,
            item_id=item_id, label="服务费定价",
        )
    db.commit()
    db.refresh(o)
    return success_response(_sf_to_dict(o), "服务费定价更新成功")


@router.delete("/pricing/mgmt/service-fee/{item_id}")
def delete_service_fee(item_id: int, db: Session = Depends(get_db)):
    o = db.query(ServiceFeePrice).filter(ServiceFeePrice.id == item_id).first()
    if not o:
        raise HTTPException(404, "服务费定价不存在")
    db.delete(o)
    db.commit()
    return success_response(None, "服务费定价已删除")
