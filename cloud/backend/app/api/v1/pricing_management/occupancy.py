"""占桩费定价 CRUD 端点（拆分自原 pricing_management.py）。"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_v2 import OccupancyFeePrice

from ._shared import (
    _ROUTER_DEPENDENCIES,
    _parse_date,
    _fmt_date,
    _fmt_dt,
    assert_no_effective_overlap,
    OccupancyFeeCreate,
    OccupancyFeeUpdate,
    logger,
)


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


def _of_to_dict(o: OccupancyFeePrice) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "grace_minutes": o.grace_minutes,
        "rate_per_minute": float(o.rate_per_minute) if o.rate_per_minute else 0.0,
        "max_fee": float(o.max_fee) if o.max_fee else None,
        "effective_date": _fmt_date(o.effective_date),
        "expire_date": _fmt_date(o.expire_date),
        "is_active": o.is_active,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


@router.get("/pricing/mgmt/occupancy")
def list_occupancy_fees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(OccupancyFeePrice)
        if station_id is not None:
            q = q.filter(OccupancyFeePrice.station_id == station_id)
        if is_active is not None:
            q = q.filter(OccupancyFeePrice.is_active == is_active)
        total = q.count()
        items = q.order_by(OccupancyFeePrice.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        return paginated_response([_of_to_dict(i) for i in items], total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_occupancy_fees 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/pricing/mgmt/occupancy/{item_id}")
def get_occupancy_fee(item_id: int, db: Session = Depends(get_db)):
    try:
        o = db.query(OccupancyFeePrice).filter(OccupancyFeePrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "占桩费定价不存在")
        return success_response(_of_to_dict(o))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_occupancy_fee 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/pricing/mgmt/occupancy")
def create_occupancy_fee(body: OccupancyFeeCreate, db: Session = Depends(get_db)):
    try:
        effective = _parse_date(body.effective_date)
        expire = _parse_date(body.expire_date) if body.expire_date else None
        if body.is_active:
            # 缺陷1: 同 station 重叠生效期会让下游 .first() 选取不确定 → 拒绝(409)
            assert_no_effective_overlap(
                db, OccupancyFeePrice,
                dims={OccupancyFeePrice.station_id: body.station_id},
                effective=effective, expire=expire, label="占桩费定价",
            )
        o = OccupancyFeePrice(
            station_id=body.station_id,
            grace_minutes=body.grace_minutes,
            rate_per_minute=Decimal(str(body.rate_per_minute)),
            max_fee=Decimal(str(body.max_fee)) if body.max_fee is not None else None,
            effective_date=effective,
            expire_date=expire,
            is_active=body.is_active,
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return success_response(_of_to_dict(o), "占桩费定价创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_occupancy_fee 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/pricing/mgmt/occupancy/{item_id}")
def update_occupancy_fee(item_id: int, body: OccupancyFeeUpdate, db: Session = Depends(get_db)):
    try:
        o = db.query(OccupancyFeePrice).filter(OccupancyFeePrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "占桩费定价不存在")
        if body.station_id is not None:
            o.station_id = body.station_id
        if body.grace_minutes is not None:
            o.grace_minutes = body.grace_minutes
        if body.rate_per_minute is not None:
            o.rate_per_minute = Decimal(str(body.rate_per_minute))
        if body.max_fee is not None:
            o.max_fee = Decimal(str(body.max_fee))
        if body.effective_date is not None:
            o.effective_date = _parse_date(body.effective_date)
        if body.expire_date is not None:
            o.expire_date = _parse_date(body.expire_date)
        if body.is_active is not None:
            o.is_active = body.is_active
        # 缺陷1: 按更新后的值做重叠校验(同 station), 排除自身
        if o.is_active:
            assert_no_effective_overlap(
                db, OccupancyFeePrice,
                dims={OccupancyFeePrice.station_id: o.station_id},
                effective=o.effective_date, expire=o.expire_date,
                item_id=item_id, label="占桩费定价",
            )
        db.commit()
        db.refresh(o)
        return success_response(_of_to_dict(o), "占桩费定价更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_occupancy_fee 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.delete("/pricing/mgmt/occupancy/{item_id}")
def delete_occupancy_fee(item_id: int, db: Session = Depends(get_db)):
    try:
        o = db.query(OccupancyFeePrice).filter(OccupancyFeePrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "占桩费定价不存在")
        db.delete(o)
        db.commit()
        return success_response(None, "占桩费定价已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_occupancy_fee 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
