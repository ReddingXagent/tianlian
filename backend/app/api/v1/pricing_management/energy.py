"""充电费定价 CRUD 端点（拆分自原 pricing_management.py）。"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_v2 import EnergyPrice

from ._shared import (
    _ROUTER_DEPENDENCIES,
    _parse_date,
    _fmt_date,
    _fmt_dt,
    assert_no_effective_overlap,
    EnergyPriceCreate,
    EnergyPriceUpdate,
    logger,
)


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


def _ep_to_dict(o: EnergyPrice) -> dict:
    return {
        "id": o.id,
        "station_id": o.station_id,
        "slot_id": o.slot_id,
        "price_per_kwh": float(o.price_per_kwh) if o.price_per_kwh else 0.0,
        "effective_date": _fmt_date(o.effective_date),
        "expire_date": _fmt_date(o.expire_date),
        "is_active": o.is_active,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


@router.get("/pricing/mgmt/energy")
def list_energy_prices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(EnergyPrice)
        if station_id is not None:
            q = q.filter(EnergyPrice.station_id == station_id)
        if is_active is not None:
            q = q.filter(EnergyPrice.is_active == is_active)
        total = q.count()
        items = q.order_by(EnergyPrice.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        return paginated_response([_ep_to_dict(i) for i in items], total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_energy_prices 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/pricing/mgmt/energy/{item_id}")
def get_energy_price(item_id: int, db: Session = Depends(get_db)):
    try:
        o = db.query(EnergyPrice).filter(EnergyPrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "充电费定价不存在")
        return success_response(_ep_to_dict(o))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_energy_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("/pricing/mgmt/energy")
def create_energy_price(body: EnergyPriceCreate, db: Session = Depends(get_db)):
    try:
        effective = _parse_date(body.effective_date)
        expire = _parse_date(body.expire_date) if body.expire_date else None
        if body.is_active:
            # 缺陷1: 同 (station, slot) 重叠生效期会让下游 .first() 选取不确定 → 拒绝(409)
            assert_no_effective_overlap(
                db, EnergyPrice,
                dims={EnergyPrice.station_id: body.station_id, EnergyPrice.slot_id: body.slot_id},
                effective=effective, expire=expire, label="充电费定价",
            )
        o = EnergyPrice(
            station_id=body.station_id,
            slot_id=body.slot_id,
            price_per_kwh=Decimal(str(body.price_per_kwh)),
            effective_date=effective,
            expire_date=expire,
            is_active=body.is_active,
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return success_response(_ep_to_dict(o), "充电费定价创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_energy_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/pricing/mgmt/energy/{item_id}")
def update_energy_price(item_id: int, body: EnergyPriceUpdate, db: Session = Depends(get_db)):
    try:
        o = db.query(EnergyPrice).filter(EnergyPrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "充电费定价不存在")
        if body.station_id is not None:
            o.station_id = body.station_id
        if body.slot_id is not None:
            o.slot_id = body.slot_id
        if body.price_per_kwh is not None:
            o.price_per_kwh = Decimal(str(body.price_per_kwh))
        if body.effective_date is not None:
            o.effective_date = _parse_date(body.effective_date)
        if body.expire_date is not None:
            o.expire_date = _parse_date(body.expire_date)
        if body.is_active is not None:
            o.is_active = body.is_active
        # 缺陷1: 按更新后的值做重叠校验(同 station+slot), 排除自身
        if o.is_active:
            assert_no_effective_overlap(
                db, EnergyPrice,
                dims={EnergyPrice.station_id: o.station_id, EnergyPrice.slot_id: o.slot_id},
                effective=o.effective_date, expire=o.expire_date,
                item_id=item_id, label="充电费定价",
            )
        db.commit()
        db.refresh(o)
        return success_response(_ep_to_dict(o), "充电费定价更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_energy_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.delete("/pricing/mgmt/energy/{item_id}")
def delete_energy_price(item_id: int, db: Session = Depends(get_db)):
    try:
        o = db.query(EnergyPrice).filter(EnergyPrice.id == item_id).first()
        if not o:
            raise HTTPException(404, "充电费定价不存在")
        db.delete(o)
        db.commit()
        return success_response(None, "充电费定价已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_energy_price 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
