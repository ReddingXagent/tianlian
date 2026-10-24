"""
车辆维保/保险档案管理 API - fleet-platform-spec §4.3 规划表

挂载前缀 /fleet (见 api/v1/__init__.py), 实际路径:
- GET    /api/v1/fleet/vehicles/{vid}/maintenance            维保列表(类型+状态筛选)
- POST   /api/v1/fleet/vehicles/{vid}/maintenance            创建维保
- GET    /api/v1/fleet/vehicles/{vid}/maintenance/{mid}      维保详情
- PUT    /api/v1/fleet/vehicles/{vid}/maintenance/{mid}      更新维保
- DELETE /api/v1/fleet/vehicles/{vid}/maintenance/{mid}      删除维保
- GET    /api/v1/fleet/vehicles/{vid}/insurance              保险列表(类型筛选)
- POST   /api/v1/fleet/vehicles/{vid}/insurance              创建保险
- GET    /api/v1/fleet/vehicles/{vid}/insurance/{iid}        保险详情
- PUT    /api/v1/fleet/vehicles/{vid}/insurance/{iid}        更新保险
- DELETE /api/v1/fleet/vehicles/{vid}/insurance/{iid}        删除保险
- GET    /api/v1/fleet/vehicles/{vid}/profile                聚合档案(维保统计+保险+到期提醒)
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.iso_utils import parse_iso8601
from app.api.v1.auth import require_role, get_current_user
from app.api.deps import assert_vehicle_team_access
from app.models.user import User
from app.core.response import success_response, paginated_response, action_response
from app.models.fleet_vehicle_profile import (
    FleetVehicleMaintenance, FleetVehicleInsurance,
    VehicleMaintenanceType, VehicleMaintenanceStatus, VehicleInsuranceType,
)

router = APIRouter(dependencies=[Depends(require_role("admin", "operator"))])


# ─── Schemas ───

class MaintenanceCreateRequest(BaseModel):
    type: Literal["maintenance", "repair", "inspection"]  # maintenance/repair/inspection
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    cost: float = Field(0.0, ge=0.0)
    mileage: float = Field(0.0, ge=0.0)
    description: Optional[str] = None
    status: Optional[Literal["pending", "in_progress", "completed", "cancelled"]] = None  # 缺省 pending


class MaintenanceUpdateRequest(BaseModel):
    type: Optional[Literal["maintenance", "repair", "inspection"]] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    cost: Optional[float] = Field(None, ge=0.0)
    mileage: Optional[float] = Field(None, ge=0.0)
    description: Optional[str] = None
    status: Optional[Literal["pending", "in_progress", "completed", "cancelled"]] = None


class InsuranceCreateRequest(BaseModel):
    insurance_type: Literal["compulsory", "commercial", "third_party"]  # compulsory/commercial/third_party
    company: str = Field(..., max_length=100)
    policy_no: str = Field(..., max_length=100)
    start_date: str
    end_date: str
    premium: float = Field(0.0, ge=0.0)
    attachment_url: Optional[str] = None


class InsuranceUpdateRequest(BaseModel):
    insurance_type: Optional[Literal["compulsory", "commercial", "third_party"]] = None
    company: Optional[str] = None
    policy_no: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    premium: Optional[float] = Field(None, ge=0.0)
    attachment_url: Optional[str] = None


# ─── Helpers ───

def _parse_dt(value: Optional[str], field: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        dt = parse_iso8601(value)  # py3.9 兼容 'Z' 后缀 (卡 c4cbcbf1)
        # 统一 naive: DB(SQLite) 存 naive, 避免 aware/naive 混用比较 TypeError
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} 格式无效，需 ISO 8601")


def _maintenance_to_dict(m: FleetVehicleMaintenance) -> dict:
    return {
        "id": m.id,
        "vehicle_id": m.vehicle_id,
        "type": m.type.value if m.type else None,
        "start_at": m.start_at.isoformat() if m.start_at else None,
        "end_at": m.end_at.isoformat() if m.end_at else None,
        "cost": float(m.cost) if m.cost is not None else 0.0,
        "mileage": float(m.mileage) if m.mileage is not None else 0.0,
        "description": m.description,
        "status": m.status.value if m.status else "pending",
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _insurance_to_dict(i: FleetVehicleInsurance) -> dict:
    return {
        "id": i.id,
        "vehicle_id": i.vehicle_id,
        "insurance_type": i.insurance_type.value if i.insurance_type else None,
        "company": i.company,
        "policy_no": i.policy_no,
        "start_date": i.start_date.isoformat() if i.start_date else None,
        "end_date": i.end_date.isoformat() if i.end_date else None,
        "premium": float(i.premium) if i.premium is not None else 0.0,
        "attachment_url": i.attachment_url,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


def _get_maintenance_or_404(db: Session, vehicle_id: int, mid: int) -> FleetVehicleMaintenance:
    m = db.query(FleetVehicleMaintenance).filter(
        FleetVehicleMaintenance.id == mid,
        FleetVehicleMaintenance.vehicle_id == vehicle_id,
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="维保记录不存在")
    return m


def _get_insurance_or_404(db: Session, vehicle_id: int, iid: int) -> FleetVehicleInsurance:
    i = db.query(FleetVehicleInsurance).filter(
        FleetVehicleInsurance.id == iid,
        FleetVehicleInsurance.vehicle_id == vehicle_id,
    ).first()
    if not i:
        raise HTTPException(status_code=404, detail="保险记录不存在")
    return i


# ─── 维保 CRUD ───

@router.get("/vehicles/{vehicle_id}/maintenance", summary="车辆维保列表")
def list_maintenance(
    vehicle_id: int,
    type: Optional[str] = Query(None, description="维保类型筛选: maintenance/repair/inspection"),
    status: Optional[str] = Query(None, description="状态筛选: pending/in_progress/completed/cancelled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取车辆维保记录列表, 支持按类型与状态筛选。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    query = db.query(FleetVehicleMaintenance).filter(
        FleetVehicleMaintenance.vehicle_id == vehicle_id
    )
    if type:
        try:
            query = query.filter(FleetVehicleMaintenance.type == VehicleMaintenanceType(type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维保类型: {type}")
    if status:
        try:
            query = query.filter(FleetVehicleMaintenance.status == VehicleMaintenanceStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维保状态: {status}")
    total = query.count()
    items = query.order_by(FleetVehicleMaintenance.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return paginated_response(
        [_maintenance_to_dict(m) for m in items], total, page, page_size
    )


@router.post("/vehicles/{vehicle_id}/maintenance", summary="创建维保记录")
def create_maintenance(
    vehicle_id: int,
    data: MaintenanceCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """为车辆创建维保记录(保养/维修/年检), 缺省状态 pending。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    try:
        mtype = VehicleMaintenanceType(data.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的维保类型: {data.type}")
    status = VehicleMaintenanceStatus.PENDING
    if data.status:
        try:
            status = VehicleMaintenanceStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维保状态: {data.status}")
    m = FleetVehicleMaintenance(
        vehicle_id=vehicle_id,
        type=mtype,
        start_at=_parse_dt(data.start_at, "start_at"),
        end_at=_parse_dt(data.end_at, "end_at"),
        cost=Decimal(str(data.cost)),
        mileage=Decimal(str(data.mileage)),
        description=data.description,
        status=status,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return success_response(_maintenance_to_dict(m), message="维保记录创建成功")


@router.get("/vehicles/{vehicle_id}/maintenance/{maintenance_id}", summary="维保详情")
def get_maintenance(
    vehicle_id: int,
    maintenance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单条维保记录(校验归属车辆)。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    m = _get_maintenance_or_404(db, vehicle_id, maintenance_id)
    return success_response(_maintenance_to_dict(m))


@router.put("/vehicles/{vehicle_id}/maintenance/{maintenance_id}", summary="更新维保记录")
def update_maintenance(
    vehicle_id: int,
    maintenance_id: int,
    data: MaintenanceUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新维保记录, 仅覆盖传入字段。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    m = _get_maintenance_or_404(db, vehicle_id, maintenance_id)
    if data.type is not None:
        try:
            m.type = VehicleMaintenanceType(data.type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维保类型: {data.type}")
    if data.start_at is not None:
        m.start_at = _parse_dt(data.start_at, "start_at")
    if data.end_at is not None:
        m.end_at = _parse_dt(data.end_at, "end_at")
    if data.cost is not None:
        m.cost = Decimal(str(data.cost))
    if data.mileage is not None:
        m.mileage = Decimal(str(data.mileage))
    if data.description is not None:
        m.description = data.description
    if data.status is not None:
        try:
            m.status = VehicleMaintenanceStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维保状态: {data.status}")
    db.commit()
    db.refresh(m)
    return success_response(_maintenance_to_dict(m), message="维保记录更新成功")


@router.delete("/vehicles/{vehicle_id}/maintenance/{maintenance_id}", summary="删除维保记录")
def delete_maintenance(
    vehicle_id: int,
    maintenance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除单条维保记录。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    m = _get_maintenance_or_404(db, vehicle_id, maintenance_id)
    db.delete(m)
    db.commit()
    return action_response(message="维保记录删除成功")


# ─── 保险 CRUD ───

@router.get("/vehicles/{vehicle_id}/insurance", summary="车辆保险列表")
def list_insurance(
    vehicle_id: int,
    insurance_type: Optional[str] = Query(None, description="保险类型筛选: compulsory/commercial/third_party"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取车辆保险档案列表, 支持按类型筛选。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    query = db.query(FleetVehicleInsurance).filter(
        FleetVehicleInsurance.vehicle_id == vehicle_id
    )
    if insurance_type:
        try:
            query = query.filter(FleetVehicleInsurance.insurance_type == VehicleInsuranceType(insurance_type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的保险类型: {insurance_type}")
    total = query.count()
    items = query.order_by(FleetVehicleInsurance.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return paginated_response(
        [_insurance_to_dict(i) for i in items], total, page, page_size
    )


@router.post("/vehicles/{vehicle_id}/insurance", summary="创建保险记录")
def create_insurance(
    vehicle_id: int,
    data: InsuranceCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """为车辆创建保险档案, 校验起止日期。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    try:
        itype = VehicleInsuranceType(data.insurance_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的保险类型: {data.insurance_type}")
    start = _parse_dt(data.start_date, "start_date")
    end = _parse_dt(data.end_date, "end_date")
    if start is None or end is None:
        raise HTTPException(status_code=400, detail="起保日期和到期日期必填")
    if end < start:
        raise HTTPException(status_code=400, detail="到期日期不能早于起保日期")
    i = FleetVehicleInsurance(
        vehicle_id=vehicle_id,
        insurance_type=itype,
        company=data.company,
        policy_no=data.policy_no,
        start_date=start,
        end_date=end,
        premium=Decimal(str(data.premium)),
        attachment_url=data.attachment_url,
    )
    db.add(i)
    db.commit()
    db.refresh(i)
    return success_response(_insurance_to_dict(i), message="保险记录创建成功")


@router.get("/vehicles/{vehicle_id}/insurance/{insurance_id}", summary="保险详情")
def get_insurance(
    vehicle_id: int,
    insurance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单条保险档案(校验归属车辆)。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    i = _get_insurance_or_404(db, vehicle_id, insurance_id)
    return success_response(_insurance_to_dict(i))


@router.put("/vehicles/{vehicle_id}/insurance/{insurance_id}", summary="更新保险记录")
def update_insurance(
    vehicle_id: int,
    insurance_id: int,
    data: InsuranceUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新保险档案, 仅覆盖传入字段, 校验起止日期。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    i = _get_insurance_or_404(db, vehicle_id, insurance_id)
    if data.insurance_type is not None:
        try:
            i.insurance_type = VehicleInsuranceType(data.insurance_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的保险类型: {data.insurance_type}")
    if data.company is not None:
        i.company = data.company
    if data.policy_no is not None:
        i.policy_no = data.policy_no
    if data.start_date is not None:
        i.start_date = _parse_dt(data.start_date, "start_date")
    if data.end_date is not None:
        i.end_date = _parse_dt(data.end_date, "end_date")
    if i.start_date and i.end_date and i.end_date < i.start_date:
        raise HTTPException(status_code=400, detail="到期日期不能早于起保日期")
    if data.premium is not None:
        i.premium = Decimal(str(data.premium))
    if data.attachment_url is not None:
        i.attachment_url = data.attachment_url
    db.commit()
    db.refresh(i)
    return success_response(_insurance_to_dict(i), message="保险记录更新成功")


@router.delete("/vehicles/{vehicle_id}/insurance/{insurance_id}", summary="删除保险记录")
def delete_insurance(
    vehicle_id: int,
    insurance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除单条保险档案。"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    i = _get_insurance_or_404(db, vehicle_id, insurance_id)
    db.delete(i)
    db.commit()
    return action_response(message="保险记录删除成功")


# ─── 聚合档案 ───

@router.get("/vehicles/{vehicle_id}/profile", summary="车辆聚合档案(维保+保险+到期提醒)")
def get_vehicle_profile(
    vehicle_id: int,
    reminder_days: int = Query(30, ge=0, le=365, description="到期提醒窗口(天)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    聚合车辆档案:
    - 维保统计(总数/总费用/按状态分布/最近5条)
    - 保险统计(总数/生效数/总保费/当前生效列表)
    - 到期提醒(end_date 已过期或在 reminder_days 窗口内)
    """
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可操作本 team 车辆；越权/不存在 → 404。
    assert_vehicle_team_access(db, vehicle_id, user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # DB end_date 为 naive, 统一 naive 比较

    maintenances = db.query(FleetVehicleMaintenance).filter(
        FleetVehicleMaintenance.vehicle_id == vehicle_id
    ).order_by(FleetVehicleMaintenance.id.desc()).all()
    insurances = db.query(FleetVehicleInsurance).filter(
        FleetVehicleInsurance.vehicle_id == vehicle_id
    ).order_by(FleetVehicleInsurance.id.desc()).all()

    # 维保统计
    by_status: dict = {}
    total_cost = Decimal("0.00")
    for m in maintenances:
        key = m.status.value if m.status else "pending"
        by_status[key] = by_status.get(key, 0) + 1
        if m.cost:
            total_cost += m.cost

    # 保险统计
    active_policies = [i for i in insurances if i.end_date and i.end_date >= now]
    total_premium = Decimal("0.00")
    for i in insurances:
        if i.premium:
            total_premium += i.premium

    # 到期提醒
    reminders = []
    for i in insurances:
        if not i.end_date:
            continue
        days_remaining = (i.end_date - now).days
        if days_remaining < 0:
            reminder_status = "expired"
        elif days_remaining <= reminder_days:
            reminder_status = "expiring_soon"
        else:
            continue
        reminders.append({
            "id": i.id,
            "insurance_type": i.insurance_type.value if i.insurance_type else None,
            "company": i.company,
            "policy_no": i.policy_no,
            "end_date": i.end_date.isoformat(),
            "days_remaining": days_remaining,
            "status": reminder_status,
        })
    reminders.sort(key=lambda r: r["days_remaining"])

    return success_response({
        "vehicle_id": vehicle_id,
        "maintenance": {
            "total_count": len(maintenances),
            "total_cost": float(total_cost),
            "by_status": by_status,
            "recent": [_maintenance_to_dict(m) for m in maintenances[:5]],
        },
        "insurance": {
            "total_count": len(insurances),
            "active_count": len(active_policies),
            "total_premium": float(total_premium),
            "current": [_insurance_to_dict(i) for i in active_policies[:5]],
        },
        "expiry_reminders": reminders,
    })
