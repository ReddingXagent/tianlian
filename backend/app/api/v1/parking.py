"""
停车折扣方案管理 API - Phase46 停车管理

商户站点停车折扣方案的 CRUD：
- GET    /api/v1/parking/discounts        列表（分页+筛选）
- GET    /api/v1/parking/discounts/{id}   详情
- POST   /api/v1/parking/discounts        创建
- PUT    /api/v1/parking/discounts/{id}   更新
- DELETE /api/v1/parking/discounts/{id}   删除
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Literal, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from decimal import Decimal

from app.api.deps import assert_station_team_access, is_platform_admin
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.parking import ParkingDiscount
from app.models.station import Station
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("operate:manage"))])


class ParkingDiscountCreate(BaseModel):
    station_id: int = Field(..., description="商户站点ID")
    merchant_name: Optional[str] = Field(None, max_length=100, description="商户名称")
    discount_type: str = Field("free_minutes", description="折扣类型: free_minutes/percentage/fixed")
    free_minutes: Optional[int] = Field(0, ge=0, description="免费时长(分钟)")
    discount_percent: Optional[float] = Field(0, ge=0, le=100, description="折扣比例(%)")
    fixed_amount: Optional[float] = Field(0, ge=0, description="固定减免(元)")
    max_discount: Optional[float] = Field(None, ge=0, description="单次最大减免(元)")
    valid_start: Optional[str] = Field(None, description="每日有效开始 HH:MM")
    valid_end: Optional[str] = Field(None, description="每日有效结束 HH:MM")
    is_active: bool = Field(True, description="是否启用")
    remark: Optional[str] = Field(None, max_length=500, description="备注")


class ParkingDiscountUpdate(BaseModel):
    station_id: Optional[int] = None
    merchant_name: Optional[str] = None
    discount_type: Optional[str] = None
    free_minutes: Optional[int] = Field(None, ge=0)
    discount_percent: Optional[float] = Field(None, ge=0, le=100)
    fixed_amount: Optional[float] = Field(None, ge=0)
    max_discount: Optional[float] = Field(None, ge=0)
    valid_start: Optional[str] = None
    valid_end: Optional[str] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None


_VALID_TYPES = {"free_minutes", "percentage", "fixed"}


def _discount_to_dict(d: ParkingDiscount) -> dict:
    return {
        "id": d.id,
        "station_id": d.station_id,
        "merchant_name": d.merchant_name,
        "discount_type": d.discount_type,
        "free_minutes": d.free_minutes,
        "discount_percent": float(d.discount_percent) if d.discount_percent is not None else 0.0,
        "fixed_amount": float(d.fixed_amount) if d.fixed_amount is not None else 0.0,
        "max_discount": float(d.max_discount) if d.max_discount is not None else None,
        "valid_start": d.valid_start,
        "valid_end": d.valid_end,
        "is_active": d.is_active,
        "remark": d.remark,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


@router.get("/parking/discounts")
def list_parking_discounts(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    station_id: Optional[int] = Query(None, description="站点ID筛选"),
    is_active: Optional[bool] = Query(None, description="启用状态筛选"),
    keyword: Optional[str] = Query(None, description="商户名称关键词"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """停车折扣方案列表"""
    try:
        q = db.query(ParkingDiscount)
        # team scoping（任务卡 1c19b59a）：非 admin 仅本 team 站点折扣。
        if not is_platform_admin(user):
            q = q.join(Station, Station.id == ParkingDiscount.station_id, isouter=True)\
                 .filter(Station.team_id == user.team_id)
        if station_id is not None:
            q = q.filter(ParkingDiscount.station_id == station_id)
        if is_active is not None:
            q = q.filter(ParkingDiscount.is_active == is_active)
        if keyword:
            q = q.filter(ParkingDiscount.merchant_name.ilike(f"%{keyword}%"))

        total = q.count()
        items = q.order_by(ParkingDiscount.created_at.desc())\
            .offset((page - 1) * page_size)\
            .limit(page_size)\
            .all()
        return paginated_response(
            items=[_discount_to_dict(d) for d in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("停车折扣列表查询失败")
        raise HTTPException(status_code=503, detail="服务暂时不可用")


@router.get("/parking/discounts/{discount_id}")
def get_parking_discount(discount_id: int, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """停车折扣方案详情"""
    try:
        d = db.query(ParkingDiscount).filter(ParkingDiscount.id == discount_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="停车折扣方案不存在")
        # team scoping（任务卡 1c19b59a）：经 station_id 校验站点归属，跨团队 → 404。
        assert_station_team_access(db, d.station_id, user)
        return success_response(_discount_to_dict(d))
    except HTTPException:
        raise
    except Exception:
        logger.exception("停车折扣详情查询失败 discount_id=%s", discount_id)
        raise HTTPException(status_code=503, detail="服务暂时不可用")


@router.post("/parking/discounts")
def create_parking_discount(body: ParkingDiscountCreate, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """创建停车折扣方案"""
    try:
        # team scoping（任务卡 1c19b59a）：站点归属校验前置，跨团队建折扣 → 404。
        assert_station_team_access(db, body.station_id, user)
        if body.discount_type not in _VALID_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"无效的折扣类型: {body.discount_type}，请使用 free_minutes/percentage/fixed",
            )
        d = ParkingDiscount(
            station_id=body.station_id,
            merchant_name=body.merchant_name,
            discount_type=body.discount_type,
            free_minutes=body.free_minutes or 0,
            discount_percent=Decimal(str(body.discount_percent or 0)),
            fixed_amount=Decimal(str(body.fixed_amount or 0)),
            max_discount=Decimal(str(body.max_discount)) if body.max_discount is not None else None,
            valid_start=body.valid_start,
            valid_end=body.valid_end,
            is_active=body.is_active,
            remark=body.remark,
        )
        db.add(d)
        db.commit()
        db.refresh(d)
        return success_response(_discount_to_dict(d), "停车折扣方案创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("停车折扣创建失败 station_id=%s", body.station_id)
        raise HTTPException(status_code=503, detail="服务暂时不可用")


@router.put("/parking/discounts/{discount_id}")
def update_parking_discount(discount_id: int, body: ParkingDiscountUpdate, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """更新停车折扣方案"""
    try:
        d = db.query(ParkingDiscount).filter(ParkingDiscount.id == discount_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="停车折扣方案不存在")
        # team scoping（任务卡 1c19b59a）：校验当前站点归属；若改 station_id 亦校验新归属。
        assert_station_team_access(db, d.station_id, user)
        update_data = body.model_dump(exclude_unset=True)
        if "station_id" in update_data and update_data["station_id"] is not None:
            assert_station_team_access(db, update_data["station_id"], user)
        if "discount_type" in update_data and update_data["discount_type"] not in _VALID_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"无效的折扣类型: {update_data['discount_type']}，请使用 free_minutes/percentage/fixed",
            )
        for key, value in update_data.items():
            if key in ("discount_percent", "fixed_amount", "max_discount") and value is not None:
                value = Decimal(str(value))
            setattr(d, key, value)

        db.commit()
        db.refresh(d)
        return success_response(_discount_to_dict(d), "停车折扣方案更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("停车折扣更新失败 discount_id=%s", discount_id)
        raise HTTPException(status_code=503, detail="服务暂时不可用")


@router.delete("/parking/discounts/{discount_id}")
def delete_parking_discount(discount_id: int, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """删除停车折扣方案"""
    try:
        d = db.query(ParkingDiscount).filter(ParkingDiscount.id == discount_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="停车折扣方案不存在")
        # team scoping（任务卡 1c19b59a）：经 station_id 校验站点归属，跨团队 → 404。
        assert_station_team_access(db, d.station_id, user)
        db.delete(d)
        db.commit()
        return success_response({"id": discount_id}, "停车折扣方案已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("停车折扣删除失败 discount_id=%s", discount_id)
        raise HTTPException(status_code=503, detail="服务暂时不可用")
