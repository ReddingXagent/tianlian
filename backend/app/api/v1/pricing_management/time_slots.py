"""时段定义 CRUD 端点（拆分自原 pricing_management.py）。"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_v2 import TimeSlotDefinition, PeriodType

from ._shared import (
    _ROUTER_DEPENDENCIES,
    _parse_time,
    _fmt_time,
    _fmt_dt,
    TimeSlotCreate,
    TimeSlotUpdate,
)


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


def _ts_to_dict(o: TimeSlotDefinition) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "period_type": o.period_type.value if o.period_type else None,
        "start_time": _fmt_time(o.start_time),
        "end_time": _fmt_time(o.end_time),
        "description": o.description,
        "is_active": o.is_active,
        "sort_order": o.sort_order,
        "created_at": _fmt_dt(o.created_at),
        "updated_at": _fmt_dt(o.updated_at),
    }


@router.get("/pricing/mgmt/time-slots")
def list_time_slots(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(TimeSlotDefinition)
    if is_active is not None:
        q = q.filter(TimeSlotDefinition.is_active == is_active)
    total = q.count()
    items = q.order_by(TimeSlotDefinition.sort_order.asc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_ts_to_dict(i) for i in items], total, page, page_size)


@router.get("/pricing/mgmt/time-slots/{item_id}")
def get_time_slot(item_id: int, db: Session = Depends(get_db)):
    o = db.query(TimeSlotDefinition).filter(TimeSlotDefinition.id == item_id).first()
    if not o:
        raise HTTPException(404, "时段定义不存在")
    return success_response(_ts_to_dict(o))


@router.post("/pricing/mgmt/time-slots")
def create_time_slot(body: TimeSlotCreate, db: Session = Depends(get_db)):
    try:
        pt = PeriodType(body.period_type)
    except ValueError:
        raise HTTPException(400, f"无效的时段类型: {body.period_type}")
    o = TimeSlotDefinition(
        name=body.name,
        period_type=pt,
        start_time=_parse_time(body.start_time),
        end_time=_parse_time(body.end_time),
        description=body.description,
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return success_response(_ts_to_dict(o), "时段定义创建成功")


@router.put("/pricing/mgmt/time-slots/{item_id}")
def update_time_slot(item_id: int, body: TimeSlotUpdate, db: Session = Depends(get_db)):
    o = db.query(TimeSlotDefinition).filter(TimeSlotDefinition.id == item_id).first()
    if not o:
        raise HTTPException(404, "时段定义不存在")
    if body.name is not None:
        o.name = body.name
    if body.period_type is not None:
        try:
            o.period_type = PeriodType(body.period_type)
        except ValueError:
            raise HTTPException(400, f"无效的时段类型: {body.period_type}")
    if body.start_time is not None:
        o.start_time = _parse_time(body.start_time)
    if body.end_time is not None:
        o.end_time = _parse_time(body.end_time)
    if body.description is not None:
        o.description = body.description
    if body.is_active is not None:
        o.is_active = body.is_active
    if body.sort_order is not None:
        o.sort_order = body.sort_order
    db.commit()
    db.refresh(o)
    return success_response(_ts_to_dict(o), "时段定义更新成功")


@router.delete("/pricing/mgmt/time-slots/{item_id}")
def delete_time_slot(item_id: int, db: Session = Depends(get_db)):
    o = db.query(TimeSlotDefinition).filter(TimeSlotDefinition.id == item_id).first()
    if not o:
        raise HTTPException(404, "时段定义不存在")
    db.delete(o)
    db.commit()
    return success_response(None, "时段定义已删除")
