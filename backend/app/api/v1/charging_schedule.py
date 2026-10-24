"""
智能充电调度 API - Phase45

挂载前缀 /fleet (见 api/v1/__init__.py), 实际路径:
- POST  /api/v1/fleet/charging/schedule/generate        生成调度计划
- GET   /api/v1/fleet/charging/schedule/current         当前调度方案
- GET   /api/v1/fleet/charging/schedule/{plan_id}       调度详情
- PATCH /api/v1/fleet/charging/schedule/{plan_id}/adjust 动态调整
- GET   /api/v1/fleet/charging/schedule                 调度计划列表
"""
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.api.v1.auth import get_current_user
from app.api.deps import assert_enterprise_team_access
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.models.charging_schedule import (
    ChargingSchedulePlan,
    ChargingScheduleEntry,
    ChargingSchedulePlanStatus,
)
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.services.charging_schedule_service import generate_schedule, adjust_schedule

router = APIRouter(prefix="/charging/schedule", tags=["智能充电调度"], dependencies=[Depends(require_write_permission("charging:manage"))])


# ─── Helpers ───

def _plan_to_dict(p: ChargingSchedulePlan) -> dict:
    return {
        "id": p.id,
        "enterprise_id": p.enterprise_id,
        "plan_date": p.plan_date.isoformat() if p.plan_date else None,
        "time_window_start": p.time_window_start.isoformat() if p.time_window_start else None,
        "time_window_end": p.time_window_end.isoformat() if p.time_window_end else None,
        "total_available_power_kw": p.total_available_power_kw,
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
        "rule_json": p.rule_json,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _entry_to_dict(e: ChargingScheduleEntry) -> dict:
    return {
        "id": e.id,
        "plan_id": e.plan_id,
        "vehicle_id": e.vehicle_id,
        "assigned_power_kw": e.assigned_power_kw,
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "priority": e.priority,
        "soc_start": e.soc_start,
        "soc_target": e.soc_target,
        "charge_mode": e.charge_mode.value if hasattr(e.charge_mode, "value") else str(e.charge_mode),
        "period_type": e.period_type.value if e.period_type else None,
    }


# ─── Schemas ───

class VehicleState(BaseModel):
    """车辆实时状态(调度输入)"""
    vehicle_id: int
    current_soc: float = Field(0.0, ge=0.0, le=1.0, description="当前SOC (0.0-1.0)")
    target_soc: float = Field(0.9, ge=0.0, le=1.0, description="目标SOC (0.0-1.0)")
    max_power_kw: float = Field(7.0, gt=0.0, description="车辆最大接受功率(kW)")


class ScheduleGenerateRequest(BaseModel):
    enterprise_id: int
    vehicle_states: List[VehicleState] = Field(..., description="参与调度的车辆实时状态")
    available_power_kw: float = Field(..., ge=0.0, description="变压器当前可用总功率(kW)")
    time_window_start: datetime
    time_window_end: datetime
    rule_spec: Optional[dict] = Field(None, description="规则参数: max_power_per_vehicle/v2g_enabled/...")

    @field_validator("vehicle_states")
    @classmethod
    def validate_vehicle_states(cls, v):
        if not v:
            raise ValueError("vehicle_states 不能为空")
        return v

    @field_validator("time_window_end")
    @classmethod
    def validate_window(cls, v, info):
        start = info.data.get("time_window_start")
        if start and v <= start:
            raise ValueError("time_window_end 必须晚于 time_window_start")
        return v


class ScheduleAdjustRequest(BaseModel):
    new_distribution: List[dict]  # [{"entry_id": 1, "new_power_kw": 5.0}, ...]


# ─── Endpoints ───

@router.post("/generate", summary="生成智能充电调度计划")
def create_schedule(
    data: ScheduleGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    生成充电调度计划:
    - 按SOC从低到高优先分配功率
    - 变压器容量约束下贪心分配
    - 峰谷时段偏好(谷时充电优先, 峰时V2G放电)
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可为本 team 企业生成调度；越权/不存在 → 404。
    assert_enterprise_team_access(db, data.enterprise_id, user)

    # 校验车辆存在且属于该企业
    vehicle_ids = [vs.vehicle_id for vs in data.vehicle_states]
    vehicles = db.query(EnterpriseVehicle).filter(
        EnterpriseVehicle.id.in_(vehicle_ids),
        EnterpriseVehicle.enterprise_id == data.enterprise_id,
    ).all()
    found_ids = {v.id for v in vehicles}
    missing = [vid for vid in vehicle_ids if vid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"车辆不存在或不属于该企业: {missing}",
        )

    result = generate_schedule(
        db=db,
        enterprise_id=data.enterprise_id,
        vehicle_states=[vs.model_dump() for vs in data.vehicle_states],
        available_power_kw=data.available_power_kw,
        time_window_start=data.time_window_start,
        time_window_end=data.time_window_end,
        rule_spec=data.rule_spec,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return success_response(result, message="调度计划生成成功")


@router.get("/current", summary="获取当前有效调度方案")
def get_current_schedule(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前最新的 planned/active 状态调度方案。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)
    plan = (
        db.query(ChargingSchedulePlan)
        .filter(
            ChargingSchedulePlan.enterprise_id == enterprise_id,
            ChargingSchedulePlan.status.in_([
                ChargingSchedulePlanStatus.PLANNED,
                ChargingSchedulePlanStatus.ACTIVE,
            ]),
        )
        .order_by(desc(ChargingSchedulePlan.plan_date))
        .first()
    )

    if not plan:
        return success_response(None, message="暂无有效调度方案")

    entries = db.query(ChargingScheduleEntry).filter(
        ChargingScheduleEntry.plan_id == plan.id
    ).order_by(ChargingScheduleEntry.priority).all()

    return success_response({
        "plan": _plan_to_dict(plan),
        "entries": [_entry_to_dict(e) for e in entries],
    })


@router.get("/{plan_id}", summary="查询调度计划详情")
def get_schedule_detail(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取指定调度计划的详细条目。"""
    plan = db.get(ChargingSchedulePlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业的计划；越权 → 404。
    assert_enterprise_team_access(db, plan.enterprise_id, user)

    entries = (
        db.query(ChargingScheduleEntry)
        .filter(ChargingScheduleEntry.plan_id == plan_id)
        .order_by(ChargingScheduleEntry.priority)
        .all()
    )

    return success_response({
        "plan": _plan_to_dict(plan),
        "entries": [_entry_to_dict(e) for e in entries],
    })


@router.patch("/{plan_id}/adjust", summary="动态调整调度功率分配")
def adjust_schedule_plan(
    plan_id: int,
    data: ScheduleAdjustRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    动态调整充电调度:
    - new_distribution: [{"entry_id": 1, "new_power_kw": 5.0}, ...]
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可改本 team 企业的计划；越权/不存在 → 404。
    # 置于 service 调用前，越权先于业务校验，不泄露存在。
    plan = db.get(ChargingSchedulePlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
    assert_enterprise_team_access(db, plan.enterprise_id, user)

    result = adjust_schedule(db, plan_id, data.new_distribution)

    if "error" in result:
        # 计划不存在 -> 404, 其余 -> 400
        status = 404 if "不存在" in result["error"] else 400
        raise HTTPException(status_code=status, detail=result["error"])

    return success_response(result, message="调度调整成功")


@router.get("", summary="查询调度计划列表")
def list_schedules(
    enterprise_id: int = Query(..., gt=0, description="企业ID"),
    status: Optional[str] = Query(None, description="状态过滤: planned/active/completed/cancelled"),
    plan_date: Optional[date] = Query(None, description="计划日期"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """分页查询调度计划。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 企业的计划；越权/不存在 → 404。
    assert_enterprise_team_access(db, enterprise_id, user)
    query = db.query(ChargingSchedulePlan).filter(
        ChargingSchedulePlan.enterprise_id == enterprise_id
    )

    if status:
        try:
            status_enum = ChargingSchedulePlanStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效状态: {status}")
        query = query.filter(ChargingSchedulePlan.status == status_enum)
    if plan_date:
        query = query.filter(func.date(ChargingSchedulePlan.plan_date) == plan_date)

    total = query.count()
    plans = (
        query.order_by(desc(ChargingSchedulePlan.plan_date))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return paginated_response(
        [_plan_to_dict(p) for p in plans], total, page, page_size
    )
