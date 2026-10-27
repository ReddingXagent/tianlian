"""设备维护计划 + 维护记录端点（拆分自原 devices.py）。"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from pydantic import BaseModel
from datetime import date
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.device import Device
from app.models.maintenance_record import MaintenanceRecord
from app.models.user import User
from app.core.response import success_response, paginated_response

from ._shared import logger, _check_device_team, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class MaintenancePlanUpdate(BaseModel):
    """设备维护计划更新"""
    maintenance_interval_days: Optional[int] = None
    next_maintenance: Optional[date] = None
    last_maintenance: Optional[date] = None


@router.get("/{device_id}/maintenance-plan")
def get_maintenance_plan(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取设备维护计划（维护周期、下次维护日期、上次维护日期）

    数据结构与 PUT 写入返回完全对齐；未设置维护计划时日期字段为 null，
    仍返回 200，便于前端编辑表单回填。team scoping：跨团队 → 404。
    """
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        _check_device_team(db, device_id, user)

        return success_response({
            'device_id': device.id,
            'maintenance_interval_days': device.maintenance_interval_days,
            'last_maintenance': device.last_maintenance.isoformat() if device.last_maintenance else None,
            'next_maintenance': device.next_maintenance.isoformat() if device.next_maintenance else None,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_maintenance_plan 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/{device_id}/maintenance-plan")
def update_maintenance_plan(
    device_id: int,
    data: MaintenancePlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """设置设备维护计划（维护周期、下次维护日期、上次维护日期；team scoping：跨团队 → 404）"""
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        _check_device_team(db, device_id, user)

        if data.maintenance_interval_days is not None:
            if data.maintenance_interval_days < 1:
                raise HTTPException(status_code=400, detail="维护周期必须大于0")
            device.maintenance_interval_days = data.maintenance_interval_days
        if data.next_maintenance is not None:
            device.next_maintenance = data.next_maintenance
        if data.last_maintenance is not None:
            device.last_maintenance = data.last_maintenance

        db.commit()
        db.refresh(device)

        return success_response({
            'device_id': device.id,
            'maintenance_interval_days': device.maintenance_interval_days,
            'last_maintenance': device.last_maintenance.isoformat() if device.last_maintenance else None,
            'next_maintenance': device.next_maintenance.isoformat() if device.next_maintenance else None,
        }, "维护计划已更新")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_maintenance_plan 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/{device_id}/maintenance-records")
def get_device_maintenance_records(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取指定设备的维护记录列表（team scoping：跨团队 → 404）"""
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        _check_device_team(db, device_id, user)

        query = db.query(MaintenanceRecord).filter(
            MaintenanceRecord.device_id == device_id
        )
        total = query.count()
        records = query.order_by(MaintenanceRecord.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        items = [{
            'id': r.id,
            'device_id': r.device_id,
            'station_id': r.station_id,
            'engineer_id': r.engineer_id,
            'type': r.type.value if r.type else None,
            'status': r.status.value if r.status else None,
            'title': r.title,
            'description': r.description,
            'solution': r.solution,
            'parts_replaced': r.parts_replaced,
            'cost': r.cost,
            'planned_at': r.planned_at.isoformat() if r.planned_at else None,
            'started_at': r.started_at.isoformat() if r.started_at else None,
            'completed_at': r.completed_at.isoformat() if r.completed_at else None,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in records]

        return paginated_response(items, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_device_maintenance_records 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
