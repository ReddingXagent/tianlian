"""设备详情读取 + 更新端点（拆分自原 devices.py）。

注：create_device（POST ""）因集合根空 path 限制，已内联至包 ``__init__``。
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Literal, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.device import Device, DeviceStatus
from app.models.maintenance_record import MaintenanceRecord
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.response import success_response

from ._shared import logger, _check_device_team, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[Literal["online", "offline", "charging", "fault", "maintenance"]] = None
    rated_power: Optional[float] = None


@router.get("/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取设备详情（含维护计划与最近维护记录）

    team scoping：跨团队 → 404（不泄露存在）。
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    # 获取最近5条维护记录
    recent_records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.device_id == device_id
    ).order_by(MaintenanceRecord.created_at.desc()).limit(5).all()

    maintenance_records_data = [{
        'id': r.id,
        'type': r.type.value if r.type else None,
        'status': r.status.value if r.status else None,
        'title': r.title,
        'description': r.description,
        'cost': r.cost,
        'planned_at': r.planned_at.isoformat() if r.planned_at else None,
        'completed_at': r.completed_at.isoformat() if r.completed_at else None,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    } for r in recent_records]

    return success_response({
        'id': device.id,
        'sn': device.sn,
        'code': device.code,
        'name': device.name,
        'type': device.type.value if device.type else 'charger_dc',
        'station_id': device.station_id,
        'status': device.status.value if device.status else 'offline',
        'health_score': device.health_score,
        'rated_power': device.rated_power,
        'gun_count': device.gun_count,
        # 入网状态 + 接入标识（任务卡 b26e8e60 §3）：仅暴露非敏感信息。
        # charge_box_id 是 OCPP 接入标识（运维需知桩用何 ID 注册）；
        # mqtt_username 为接入账号名；但 mqtt_password/auth_token 凭证明文
        # 仅创建时一次性返回，详情/列表一律不回显。
        'provision_status': device.provision_status.value if device.provision_status else 'unprovisioned',
        'charge_box_id': device.charge_box_id,
        'mqtt_username': device.mqtt_username,
        'created_at': device.created_at.isoformat() if device.created_at else None,
        'updated_at': device.updated_at.isoformat() if device.updated_at else None,
        # 维护计划
        'maintenance_interval_days': device.maintenance_interval_days,
        'last_maintenance': device.last_maintenance.isoformat() if device.last_maintenance else None,
        'next_maintenance': device.next_maintenance.isoformat() if device.next_maintenance else None,
        # 最近维护记录
        'maintenance_records': maintenance_records_data,
        'maintenance_record_count': db.query(MaintenanceRecord).filter(
            MaintenanceRecord.device_id == device_id
        ).count(),
    })


@router.put("/{device_id}")
def update_device(device_id: int, data: DeviceUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新设备（team scoping：跨团队 → 404）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)

    if data.name:
        device.name = data.name
    if data.status:
        device.status = DeviceStatus(data.status)
    if data.rated_power is not None:
        device.rated_power = data.rated_power

    db.commit()
    db.refresh(device)
    audit_service.log_crud(user.id, user.username, "update", "devices", str(device_id))
    return success_response({
        'id': device.id,
        'sn': device.sn,
        'code': device.code,
        'name': device.name,
        'type': device.type.value if device.type else 'charger_dc',
        'station_id': device.station_id,
        'status': device.status.value if device.status else 'offline',
        'health_score': device.health_score,
        'rated_power': device.rated_power,
        'gun_count': device.gun_count,
    })
