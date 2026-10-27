"""停车费定价 CRUD 端点（拆分自原 pricing_management.py）。"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_v2 import ParkingPrice

from ._shared import (
    _ROUTER_DEPENDENCIES,
    _parse_time,
    _parse_date,
    _fmt_time,
    _fmt_date,
    _fmt_dt,
    assert_no_effective_overlap,
    ParkingPriceCreate,
    ParkingPriceUpdate,
    logger,
)


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


def _pp_to_dict(o: ParkingPrice) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "free_minutes": o.free_minutes,
        "hourly_rate": float(o.hourly_rate) if o.hourly_rate else 0.0,
        "daily_cap": float(o.daily_cap) if o.daily_cap else None,
        "enable_night_rate": o.enable_night_rate,
        "night_rate": float(o.night_rate) if o.night_rate else None,
        "night_start": _fmt_time(o.night_start),
        "night_end": _fmt_time(o.night_end),
        "effective_date": _fmt_date(o.effective_date),
        "expire_date": _fmt_date(o.expire_date),
        "is_active": o.is_active,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


@router.get("/pricing/mgmt/parking")
def list_parking_prices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(ParkingPrice)
        if station_id is not None:
            q = q.filter(ParkingPrice.station_id == station_id)
        if is_active is not None:
            q = q.filter(ParkingPrice.is_active == is_active)
        total = q.count()
        items = q.order_by(ParkingPrice.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        return paginated_response([_pp_to_dict(i) for i in items], total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_parking_prices 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/pricing/mgmt/parking/{item_id}")
def get_parking_price(item_id: int, db: Session = Depends(get_db)):
    try:
        o = db.query(ParkingPrice).filter(ParkingPrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "停车费定价不存在")
        return success_response(_pp_to_dict(o))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_parking_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/pricing/mgmt/parking")
def create_parking_price(body: ParkingPriceCreate, db: Session = Depends(get_db)):
    try:
        effective = _parse_date(body.effective_date)
        expire = _parse_date(body.expire_date) if body.expire_date else None
        if body.is_active:
            # 缺陷1: 同 station 重叠生效期会让下游 .first() 选取不确定 → 拒绝(409)
            assert_no_effective_overlap(
                db, ParkingPrice,
                dims={ParkingPrice.station_id: body.station_id},
                effective=effective, expire=expire, label="停车费定价",
            )
        o = ParkingPrice(
            station_id=body.station_id,
            free_minutes=body.free_minutes,
            hourly_rate=Decimal(str(body.hourly_rate)),
            daily_cap=Decimal(str(body.daily_cap)) if body.daily_cap is not None else None,
            enable_night_rate=body.enable_night_rate,
            night_rate=Decimal(str(body.night_rate)) if body.night_rate is not None else None,
            night_start=_parse_time(body.night_start),
            night_end=_parse_time(body.night_end),
            effective_date=effective,
            expire_date=expire,
            is_active=body.is_active,
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return success_response(_pp_to_dict(o), "停车费定价创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_parking_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/pricing/mgmt/parking/{item_id}")
def update_parking_price(item_id: int, body: ParkingPriceUpdate, db: Session = Depends(get_db)):
    try:
        o = db.query(ParkingPrice).filter(ParkingPrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "停车费定价不存在")
        if body.station_id is not None:
            o.station_id = body.station_id
        if body.free_minutes is not None:
            o.free_minutes = body.free_minutes
        if body.hourly_rate is not None:
            o.hourly_rate = Decimal(str(body.hourly_rate))
        if body.daily_cap is not None:
            o.daily_cap = Decimal(str(body.daily_cap))
        if body.enable_night_rate is not None:
            o.enable_night_rate = body.enable_night_rate
        if body.night_rate is not None:
            o.night_rate = Decimal(str(body.night_rate))
        if body.night_start is not None:
            o.night_start = _parse_time(body.night_start)
        if body.night_end is not None:
            o.night_end = _parse_time(body.night_end)
        if body.effective_date is not None:
            o.effective_date = _parse_date(body.effective_date)
        if body.expire_date is not None:
            o.expire_date = _parse_date(body.expire_date)
        if body.is_active is not None:
            o.is_active = body.is_active
        # 缺陷1: 按更新后的值做重叠校验(同 station), 排除自身
        if o.is_active:
            assert_no_effective_overlap(
                db, ParkingPrice,
                dims={ParkingPrice.station_id: o.station_id},
                effective=o.effective_date, expire=o.expire_date,
                item_id=item_id, label="停车费定价",
            )
        db.commit()
        db.refresh(o)
        return success_response(_pp_to_dict(o), "停车费定价更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_parking_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.delete("/pricing/mgmt/parking/{item_id}")
def delete_parking_price(item_id: int, db: Session = Depends(get_db)):
    try:
        o = db.query(ParkingPrice).filter(ParkingPrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "停车费定价不存在")
        db.delete(o)
        db.commit()
        return success_response(None, "停车费定价已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_parking_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
