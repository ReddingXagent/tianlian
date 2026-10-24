"""
折扣管理 API - P0 运营核心补齐
POST   /api/v1/operate/discount          — 创建折扣
GET    /api/v1/operate/discount          — 折扣列表
GET    /api/v1/operate/discount/{id}     — 折扣详情
PUT    /api/v1/operate/discount/{id}     — 更新折扣
DELETE /api/v1/operate/discount/{id}     — 删除折扣
POST   /api/v1/operate/discount/group    — 创建折扣组
GET    /api/v1/operate/discount/groups   — 折扣组列表
PUT    /api/v1/operate/discount/group/{id} — 更新折扣组
DELETE /api/v1/operate/discount/group/{id} — 删除折扣组
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.price_discount import PriceDiscount, DiscountGroup, DiscountType
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import require_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# ── Pydantic Schemas ──

class DiscountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    discount_type: DiscountType = DiscountType.PERCENTAGE
    discount_rate: float = Field(..., ge=0)
    applicable_user_types: Optional[str] = None
    min_consumption: Optional[float] = 0.0
    max_discount_amount: Optional[float] = Field(None, ge=0)
    start_time: datetime
    end_time: datetime
    priority: int = 0
    is_active: bool = True
    description: Optional[str] = None

class DiscountUpdate(BaseModel):
    name: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_rate: Optional[float] = Field(None, ge=0)
    applicable_user_types: Optional[str] = None
    min_consumption: Optional[float] = None
    max_discount_amount: Optional[float] = Field(None, ge=0)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None

class DiscountGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    discount_id: int
    user_type: str = Field(..., min_length=1, max_length=50)
    user_ids: Optional[str] = None
    station_ids: Optional[str] = None
    priority: int = 0
    is_active: bool = True

class DiscountGroupUpdate(BaseModel):
    name: Optional[str] = None
    discount_id: Optional[int] = None
    user_type: Optional[str] = None
    user_ids: Optional[str] = None
    station_ids: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None

# ── 固定路径路由（必须在 /discount/{discount_id} 参数化路由之前）──

@router.post("/discount/group", summary="创建折扣组")
def create_discount_group(body: DiscountGroupCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = DiscountGroup(**body.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "折扣组创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_discount_group 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/discount/groups", summary="折扣组列表")
def list_discount_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(DiscountGroup)
        if user_type:
            q = q.filter(DiscountGroup.user_type == user_type)
        if is_active is not None:
            q = q.filter(DiscountGroup.is_active == is_active)
        total = q.count()
        items = q.order_by(DiscountGroup.priority.desc(), DiscountGroup.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        data = [{c.name: getattr(i, c.name) for c in i.__table__.columns} for i in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_discount_groups 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/discount/group/{group_id}", summary="更新折扣组")
def update_discount_group(group_id: int, body: DiscountGroupUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(DiscountGroup).filter(DiscountGroup.id == group_id).first()
        if not obj:
            raise HTTPException(404, "折扣组不存在")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_discount_group 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/discount/group/{group_id}", summary="删除折扣组")
def delete_discount_group(group_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(DiscountGroup).filter(DiscountGroup.id == group_id).first()
        if not obj:
            raise HTTPException(404, "折扣组不存在")
        db.delete(obj)
        db.commit()
        return success_response(None, "已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_discount_group 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── Discount CRUD ──

@router.post("/discount", summary="创建折扣方案")
def create_discount(body: DiscountCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = PriceDiscount(**body.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "折扣方案创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_discount 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/discount", summary="折扣方案列表")
def list_discounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    discount_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(PriceDiscount)
        if is_active is not None:
            q = q.filter(PriceDiscount.is_active == is_active)
        if discount_type:
            q = q.filter(PriceDiscount.discount_type == discount_type)
        total = q.count()
        items = q.order_by(PriceDiscount.priority.desc(), PriceDiscount.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        data = [{c.name: getattr(i, c.name) for c in i.__table__.columns} for i in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_discounts 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 参数化路由（必须在固定路径之后）──

@router.get("/discount/{discount_id}", summary="折扣方案详情")
def get_discount(discount_id: int, db: Session = Depends(get_db)):
    try:
        obj = db.query(PriceDiscount).filter(PriceDiscount.id == discount_id).first()
        if not obj:
            raise HTTPException(404, "折扣方案不存在")
        return success_response({c.name: str(getattr(obj, c.name)) if isinstance(getattr(obj, c.name), datetime) else getattr(obj, c.name) for c in obj.__table__.columns})
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_discount 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/discount/{discount_id}", summary="更新折扣方案")
def update_discount(discount_id: int, body: DiscountUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(PriceDiscount).filter(PriceDiscount.id == discount_id).first()
        if not obj:
            raise HTTPException(404, "折扣方案不存在")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        return success_response({"id": obj.id, "name": obj.name}, "更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_discount 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/discount/{discount_id}", summary="删除折扣方案")
def delete_discount(discount_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        obj = db.query(PriceDiscount).filter(PriceDiscount.id == discount_id).first()
        if not obj:
            raise HTTPException(404, "折扣方案不存在")
        db.delete(obj)
        db.commit()
        return success_response(None, "已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_discount 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
