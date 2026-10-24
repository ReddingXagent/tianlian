"""
设备维护记录管理 API
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.maintenance_record import MaintenanceRecord, MaintenanceType, MaintenanceStatus
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import is_platform_admin, assert_device_team_access, assert_station_team_access
from app.models.user import User
from app.models.device import Device
from app.models.station import Station

router = APIRouter(dependencies=[Depends(require_write_permission("workorder:edit"))])


# ========== Pydantic Schemas ==========

class MaintenanceRecordCreate(BaseModel):
    device_id: int = Field(..., description="设备ID")
    station_id: Optional[int] = Field(None, description="站点ID")
    engineer_id: Optional[int] = Field(None, description="工程师ID")
    type: Literal["preventive", "corrective", "condition_based", "emergency"] = Field("preventive", description="维护类型: preventive/corrective/condition_based/emergency")
    title: str = Field(..., description="维护标题")
    description: Optional[str] = Field(None, description="维护描述")
    solution: Optional[str] = Field(None, description="解决方案")
    parts_replaced: Optional[str] = Field(None, description="更换备件")
    cost: Optional[int] = Field(0, ge=0, description="维护费用（分）")
    planned_at: Optional[datetime] = Field(None, description="计划维护时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


class MaintenanceRecordUpdate(BaseModel):
    engineer_id: Optional[int] = Field(None, description="工程师ID")
    type: Optional[Literal["preventive", "corrective", "condition_based", "emergency"]] = Field(None, description="维护类型")
    status: Optional[Literal["planned", "in_progress", "completed", "cancelled"]] = Field(None, description="维护状态: planned/in_progress/completed/cancelled")
    title: Optional[str] = Field(None, description="维护标题")
    description: Optional[str] = Field(None, description="维护描述")
    solution: Optional[str] = Field(None, description="解决方案")
    parts_replaced: Optional[str] = Field(None, description="更换备件")
    cost: Optional[int] = Field(None, ge=0, description="维护费用（分）")
    planned_at: Optional[datetime] = Field(None, description="计划维护时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


def _serialize_record(r: MaintenanceRecord) -> dict:
    """序列化维护记录为字典"""
    return {
        "id": r.id,
        "device_id": r.device_id,
        "station_id": r.station_id,
        "engineer_id": r.engineer_id,
        "type": r.type.value if r.type else None,
        "status": r.status.value if r.status else None,
        "title": r.title,
        "description": r.description,
        "solution": r.solution,
        "parts_replaced": r.parts_replaced,
        "cost": r.cost,
        "planned_at": r.planned_at.isoformat() if r.planned_at else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ========== API Endpoints ==========

@router.get("")
def list_maintenance_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    station_id: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取维护记录列表"""
    query = db.query(MaintenanceRecord)

    if device_id:
        query = query.filter(MaintenanceRecord.device_id == device_id)
    if station_id:
        query = query.filter(MaintenanceRecord.station_id == int(station_id))
    if type:
        try:
            query = query.filter(MaintenanceRecord.type == MaintenanceType(type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维护类型: {type}")
    if status:
        try:
            query = query.filter(MaintenanceRecord.status == MaintenanceStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维护状态: {status}")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅本 team 设备的维护记录（device→station→team）。
    if not is_platform_admin(user):
        query = (
            query.join(Device, MaintenanceRecord.device_id == Device.id, isouter=True)
            .join(Station, Device.station_id == Station.id, isouter=True)
            .filter(Station.team_id == user.team_id)
        )

    total = query.count()
    records = query.order_by(MaintenanceRecord.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return paginated_response(
        [_serialize_record(r) for r in records], total, page, page_size
    )


@router.get("/{record_id}")
def get_maintenance_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取维护记录详情"""
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="维护记录不存在")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可查本 team 设备的维护记录；越权 → 404。
    assert_device_team_access(db, record.device_id, user)
    return success_response(_serialize_record(record))


@router.post("")
def create_maintenance_record(
    data: MaintenanceRecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建维护记录"""
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可为本 team 设备建维护记录；越权/不存在 → 404。
    assert_device_team_access(db, data.device_id, user)
    if data.station_id is not None:
        assert_station_team_access(db, data.station_id, user)
    try:
        mt = MaintenanceType(data.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的维护类型: {data.type}")

    record = MaintenanceRecord(
        device_id=data.device_id,
        station_id=data.station_id,
        engineer_id=data.engineer_id,
        type=mt,
        status=MaintenanceStatus.PLANNED,
        title=data.title,
        description=data.description,
        solution=data.solution,
        parts_replaced=data.parts_replaced,
        cost=data.cost or 0,
        planned_at=data.planned_at,
        started_at=data.started_at,
        completed_at=data.completed_at,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return success_response(_serialize_record(record), "维护记录创建成功")


@router.put("/{record_id}")
def update_maintenance_record(
    record_id: int,
    data: MaintenanceRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新维护记录"""
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="维护记录不存在")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可改本 team 设备的维护记录；越权 → 404。
    assert_device_team_access(db, record.device_id, user)

    update_data = data.dict(exclude_unset=True)

    # 枚举字段需要特殊处理
    if "type" in update_data:
        try:
            update_data["type"] = MaintenanceType(update_data["type"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维护类型: {update_data['type']}")
    if "status" in update_data:
        try:
            update_data["status"] = MaintenanceStatus(update_data["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的维护状态: {update_data['status']}")

    for key, value in update_data.items():
        setattr(record, key, value)

    db.commit()
    db.refresh(record)

    return success_response(_serialize_record(record), "维护记录更新成功")


@router.delete("/{record_id}")
def delete_maintenance_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除维护记录"""
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="维护记录不存在")
    # team scoping（任务卡 ab5c5f17）：非 admin 仅可删本 team 设备的维护记录；越权 → 404。
    assert_device_team_access(db, record.device_id, user)

    db.delete(record)
    db.commit()

    return action_response(success=True, message="维护记录已删除")
