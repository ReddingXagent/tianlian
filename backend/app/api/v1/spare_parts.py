"""
备件库存管理 API - maint-platform-spec §2.2

work_order_spare_parts 仅记录工单领用明细，本表为独立库存台账：
- total_quantity:     累计入库量（只增，随入库增加）
- available_quantity: 当前可用量（入库增、出库/工单领用减）

端点:
- CRUD:   GET/POST "" , GET/PUT/DELETE "/{part_id}"
- 入库:   POST /{part_id}/inbound   (available + total 同增)
- 出库:   POST /{part_id}/outbound  (仅减 available, 不足 409)

工单申请备件时由 workorders.spare_parts_workorder 按 (part_name, part_model)
匹配本表扣减 available_quantity，与本台账联动。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, action_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.spare_part import SparePartInventory

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("workorder:edit"))])


# ========== Schemas ==========

class SparePartCreate(BaseModel):
    part_name: str = Field(..., max_length=100)
    part_model: Optional[str] = None
    total_quantity: int = Field(0, ge=0)   # 初始入库量，同时作为初始可用量
    warehouse: Optional[str] = None


class SparePartUpdate(BaseModel):
    """仅更新基本信息，不得直接改动库存量（库存经入库/出库端点变动）。"""
    part_name: Optional[str] = None
    part_model: Optional[str] = None
    warehouse: Optional[str] = None


class StockMove(BaseModel):
    quantity: int = Field(..., ge=1)
    note: Optional[str] = None


# ========== Helpers ==========

def _serialize(p: SparePartInventory) -> dict:
    return {
        "id": p.id,
        "part_name": p.part_name,
        "part_model": p.part_model,
        "total_quantity": p.total_quantity,
        "available_quantity": p.available_quantity,
        "warehouse": p.warehouse,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _lock_part_or_404(db: Session, part_id: int) -> SparePartInventory:
    """行锁获取库存行并刷新快照 (卡 78bffa57 库存读改写竞态加固)。

    余量校验与扣减/累加原为 check-then-act 裸读改写, 并发出库可超扣至负数、
    并发入库丢更新。全临界区持 SparePartInventory 行 with_for_update() 行锁
    (对照 enterprises.py / business_end_user_coupons._lock_coupon),
    populate_existing 强制重发 SELECT 刷新 identity-map 陈旧快照。
    SQLite 下 with_for_update 为 no-op, 由持锁后基于最新快照复查兜底
    (双 session 交错测试见 test_spare_parts_inventory.py 并发组)。
    """
    rec = (
        db.query(SparePartInventory)
        .filter(SparePartInventory.id == part_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="备件不存在")
    return rec


def _get_or_404(db: Session, part_id: int) -> SparePartInventory:
    rec = db.query(SparePartInventory).filter(SparePartInventory.id == part_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="备件不存在")
    return rec


# ========== CRUD ==========

@router.get("")
def list_parts(
    keyword: Optional[str] = Query(None, description="按名称/型号模糊搜索"),
    warehouse: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """备件库存列表（分页 + 名称/型号模糊搜索）"""
    try:
        q = db.query(SparePartInventory)
        if keyword:
            like = f"%{keyword}%"
            q = q.filter(
                (SparePartInventory.part_name.like(like))
                | (SparePartInventory.part_model.like(like))
            )
        if warehouse:
            q = q.filter(SparePartInventory.warehouse == warehouse)

        total = q.count()
        items = (
            q.order_by(SparePartInventory.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return success_response({
            "items": [_serialize(p) for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_parts 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("")
def create_part(data: SparePartCreate, db: Session = Depends(get_db)):
    """登记备件并设定初始库存（初始可用量 = 初始入库量）"""
    try:
        rec = SparePartInventory(
            part_name=data.part_name,
            part_model=data.part_model,
            total_quantity=data.total_quantity,
            available_quantity=data.total_quantity,
            warehouse=data.warehouse,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return success_response(_serialize(rec), message="备件已登记入库")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_part 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/{part_id}")
def get_part(part_id: int, db: Session = Depends(get_db)):
    try:
        return success_response(_serialize(_get_or_404(db, part_id)))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_part 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{part_id}")
def update_part(part_id: int, data: SparePartUpdate, db: Session = Depends(get_db)):
    """更新备件基本信息（不改库存量）"""
    try:
        rec = _get_or_404(db, part_id)
        if data.part_name is not None:
            rec.part_name = data.part_name
        if data.part_model is not None:
            rec.part_model = data.part_model
        if data.warehouse is not None:
            rec.warehouse = data.warehouse
        db.commit()
        db.refresh(rec)
        return success_response(_serialize(rec), message="备件信息已更新")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_part 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/{part_id}")
def delete_part(part_id: int, db: Session = Depends(get_db)):
    try:
        rec = _get_or_404(db, part_id)
        db.delete(rec)
        db.commit()
        return action_response(success=True, message="备件已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_part 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ========== 入库 / 出库 ==========

@router.post("/{part_id}/inbound")
def inbound(part_id: int, data: StockMove, db: Session = Depends(get_db)):
    """入库 — available_quantity 与 total_quantity 同增"""
    try:
        rec = _lock_part_or_404(db, part_id)
        rec.available_quantity = (rec.available_quantity or 0) + data.quantity
        rec.total_quantity = (rec.total_quantity or 0) + data.quantity
        db.commit()
        db.refresh(rec)
        return success_response(_serialize(rec), message=f"入库 {data.quantity} 件")
    except HTTPException:
        raise
    except Exception:
        logger.exception("inbound 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/{part_id}/outbound")
def outbound(part_id: int, data: StockMove, db: Session = Depends(get_db)):
    """出库 — 仅扣减 available_quantity；可用量不足返回 409"""
    try:
        rec = _lock_part_or_404(db, part_id)
        if (rec.available_quantity or 0) < data.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"库存不足: 当前可用 {rec.available_quantity}, 需 {data.quantity}",
            )
        rec.available_quantity = rec.available_quantity - data.quantity
        db.commit()
        db.refresh(rec)
        return success_response(_serialize(rec), message=f"出库 {data.quantity} 件")
    except HTTPException:
        raise
    except Exception:
        logger.exception("outbound 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
