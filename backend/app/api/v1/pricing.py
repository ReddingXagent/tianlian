"""
定价管理 API - Phase42 运营管理

提供时段电价的 CRUD 操作:
- GET    /api/v1/pricing        列表
- POST   /api/v1/pricing        创建
- PUT    /api/v1/pricing/{id}   更新
- DELETE /api/v1/pricing/{id}   删除
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.pricing_rule import PricingRule, PeriodType
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


# ─── Pydantic 模型 ───

class PricingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="规则名称")
    period_type: str = Field(..., description="时段类型: peak/shoulder/valley/flat")
    start_time: str = Field(..., description="时段开始时间 (HH:MM)")
    end_time: str = Field(..., description="时段结束时间 (HH:MM)")
    electricity_price: float = Field(0.0, ge=0, description="电价(元/kWh)")
    service_fee_rate: float = Field(0.0, ge=0, description="服务费率(元/kWh)")
    parking_fee_per_hour: float = Field(0.0, ge=0, description="停车费(元/小时)")
    idle_penalty_per_min: float = Field(0.0, ge=0, description="超时占用费(元/分钟)")
    is_active: bool = Field(True, description="是否启用")


class PricingUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="规则名称")
    period_type: Optional[str] = Field(None, description="时段类型: peak/shoulder/valley/flat")
    start_time: Optional[str] = Field(None, description="时段开始时间 (HH:MM)")
    end_time: Optional[str] = Field(None, description="时段结束时间 (HH:MM)")
    electricity_price: Optional[float] = Field(None, ge=0, description="电价(元/kWh)")
    service_fee_rate: Optional[float] = Field(None, ge=0, description="服务费率(元/kWh)")
    parking_fee_per_hour: Optional[float] = Field(None, ge=0, description="停车费(元/小时)")
    idle_penalty_per_min: Optional[float] = Field(None, ge=0, description="超时占用费(元/分钟)")
    is_active: Optional[bool] = Field(None, description="是否启用")


# ─── Helper ───

def _pricing_to_dict(pr: PricingRule) -> dict:
    return {
        "id": pr.id,
        "name": pr.name,
        "period_type": pr.period_type.value if pr.period_type else None,
        "start_time": str(pr.start_time) if pr.start_time else None,
        "end_time": str(pr.end_time) if pr.end_time else None,
        "electricity_price": float(pr.electricity_price) if pr.electricity_price else 0.0,
        "service_fee_rate": float(pr.service_fee_rate) if pr.service_fee_rate else 0.0,
        "parking_fee_per_hour": float(pr.parking_fee_per_hour) if pr.parking_fee_per_hour else 0.0,
        "idle_penalty_per_min": float(pr.idle_penalty_per_min) if pr.idle_penalty_per_min else 0.0,
        "is_active": pr.is_active if pr.is_active is not None else True,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
    }


# ─── API 端点 ───

@router.get("/pricing")
def list_pricing(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    period_type: Optional[str] = Query(None, description="时段类型筛选"),
    is_active: Optional[bool] = Query(None, description="是否启用筛选"),
    db: Session = Depends(get_db),
):
    """定价规则列表"""
    q = db.query(PricingRule)

    if period_type:
        try:
            pt = PeriodType(period_type)
            q = q.filter(PricingRule.period_type == pt)
        except ValueError:
            pass

    if is_active is not None:
        q = q.filter(PricingRule.is_active == is_active)

    total = q.count()
    items = q.order_by(PricingRule.start_time.asc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()

    return paginated_response(
        items=[_pricing_to_dict(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/pricing/{pricing_id}")
def get_pricing(pricing_id: int, db: Session = Depends(get_db)):
    """定价规则详情"""
    pr = db.query(PricingRule).filter(PricingRule.id == pricing_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="定价规则不存在")
    return success_response(_pricing_to_dict(pr))


@router.post("/pricing")
def create_pricing(
    body: PricingCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("system:config")),
):
    """创建定价规则"""
    try:
        pt = PeriodType(body.period_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的时段类型: {body.period_type}，请使用 peak/shoulder/valley/flat/deep_valley/sharp")

    from datetime import time as dt_time
    try:
        h_start, m_start = body.start_time.split(":")
        h_end, m_end = body.end_time.split(":")
        start_t = dt_time(int(h_start), int(m_start))
        end_t = dt_time(int(h_end), int(m_end))
    except Exception:
        raise HTTPException(status_code=400, detail="时间格式无效，请使用 HH:MM 格式")

    pr = PricingRule(
        name=body.name,
        period_type=pt,
        start_time=start_t,
        end_time=end_t,
        electricity_price=body.electricity_price,
        service_fee_rate=body.service_fee_rate,
        parking_fee_per_hour=body.parking_fee_per_hour,
        idle_penalty_per_min=body.idle_penalty_per_min,
        is_active=body.is_active,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return success_response(_pricing_to_dict(pr), "定价规则创建成功")


@router.put("/pricing/{pricing_id}")
def update_pricing(
    pricing_id: int,
    body: PricingUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("system:config")),
):
    """更新定价规则"""
    pr = db.query(PricingRule).filter(PricingRule.id == pricing_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="定价规则不存在")

    if body.name is not None:
        pr.name = body.name
    if body.period_type is not None:
        try:
            pr.period_type = PeriodType(body.period_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的时段类型: {body.period_type}")
    if body.start_time is not None:
        from datetime import time as dt_time
        try:
            h, m = body.start_time.split(":")
            pr.start_time = dt_time(int(h), int(m))
        except Exception:
            raise HTTPException(status_code=400, detail="时间格式无效，请使用 HH:MM 格式")
    if body.end_time is not None:
        from datetime import time as dt_time
        try:
            h, m = body.end_time.split(":")
            pr.end_time = dt_time(int(h), int(m))
        except Exception:
            raise HTTPException(status_code=400, detail="时间格式无效，请使用 HH:MM 格式")
    if body.electricity_price is not None:
        pr.electricity_price = body.electricity_price
    if body.service_fee_rate is not None:
        pr.service_fee_rate = body.service_fee_rate
    if body.parking_fee_per_hour is not None:
        pr.parking_fee_per_hour = body.parking_fee_per_hour
    if body.idle_penalty_per_min is not None:
        pr.idle_penalty_per_min = body.idle_penalty_per_min
    if body.is_active is not None:
        pr.is_active = body.is_active

    db.commit()
    db.refresh(pr)
    return success_response(_pricing_to_dict(pr), "定价规则更新成功")


@router.delete("/pricing/{pricing_id}")
def delete_pricing(
    pricing_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("system:config")),
):
    """删除定价规则"""
    pr = db.query(PricingRule).filter(PricingRule.id == pricing_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="定价规则不存在")

    db.delete(pr)
    db.commit()
    return success_response(None, "定价规则已删除")
