"""
V2G 充放电调度 API

提供V2G双向充电桩的调度指令下发、历史查询和活跃调度监控。
所有端点继承 /devices 前缀，由 __init__.py 统一注册。
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timezone
import logging

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import is_platform_admin, assert_device_team_access
from app.models.device import Device
from app.models.station import Station
from app.models.user import User
from app.models.v2g_dispatch import V2GDispatchLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["V2G调度"], dependencies=[Depends(require_write_permission("device:edit"))])

# ── Pydantic 模型 ──────────────────────────────────────────────

class V2GDispatchRequest(BaseModel):
    """V2G调度请求"""
    dispatch_type: Literal["charge", "discharge", "standby"] = Field(
        ..., description="调度类型: charge=充电, discharge=放电, standby=待机"
    )
    target_power_kw: float = Field(..., gt=0, description="目标功率(kW)，必须大于0")


class V2GDispatchResponse(BaseModel):
    """V2G调度响应"""
    id: int
    device_id: int
    dispatch_type: str
    target_power_kw: float
    actual_power_kw: float
    status: str
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    created_at: str


# ── 鉴权（team scoping，任务卡 e1f0e6d5 已完成）──────────────────
# 所有端点已注入 user: User = Depends(get_current_user)，端点级鉴权：
# - dispatch / history：assert_device_team_access 做 device→station→team 隔离，越权/不存在 → 404
# - active：非 admin 通过 join 过滤本 team 设备；平台 admin 跨 team 可见


def _serialize_log(record: V2GDispatchLog) -> dict:
    """序列化一条调度日志"""
    return {
        "id": record.id,
        "device_id": record.device_id,
        "dispatch_type": record.dispatch_type,
        "target_power_kw": record.target_power_kw,
        "actual_power_kw": record.actual_power_kw,
        "status": record.status,
        "start_at": record.start_at.isoformat() if record.start_at else None,
        "end_at": record.end_at.isoformat() if record.end_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


# ── 端点 ──────────────────────────────────────────────────────

@router.post("/{device_id}/v2g/dispatch")
def dispatch_v2g(
    device_id: int,
    data: V2GDispatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下发V2G充放电调度指令

    向指定V2G充电桩下发 charge/discharge/standby 调度指令，
    写入 v2g_dispatch_logs 表并返回调度记录。
    """
    try:
        # team scoping（任务卡 e1f0e6d5）：非 admin 仅可调度本 team 设备；
        # 越权或不存在 → 404（不泄露存在）。
        assert_device_team_access(db, device_id, user)
        # 校验设备为 V2G 充电桩（存在性已由 assert 校验）
        device = db.query(Device).filter(Device.id == device_id).first()

        # 仅 V2G 充电桩支持调度
        from app.models.device import DeviceType
        if device.type != DeviceType.V2G_CHARGER:
            raise HTTPException(
                status_code=400,
                detail=f"设备类型 {device.type.value} 不支持V2G调度，仅支持 v2g_charger",
            )

        # 写入调度日志
        now = datetime.now(timezone.utc)
        dispatch_log = V2GDispatchLog(
            device_id=device_id,
            dispatch_type=data.dispatch_type,
            target_power_kw=data.target_power_kw,
            actual_power_kw=0.0,  # 初始无实际功率，由设备回传更新
            status="pending",
            start_at=now,
        )
        db.add(dispatch_log)
        db.commit()
        db.refresh(dispatch_log)

        logger.info(
            "V2G调度已下发 device_id=%s dispatch_type=%s target_power=%s kW log_id=%s",
            device_id, data.dispatch_type, data.target_power_kw, dispatch_log.id,
        )

        return success_response(
            _serialize_log(dispatch_log),
            f"V2G调度指令已下发: {data.dispatch_type} @ {data.target_power_kw} kW",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("dispatch_v2g 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/{device_id}/v2g/dispatch/history")
def get_v2g_dispatch_history(
    device_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询该设备V2G调度历史

    返回按时间倒序的调度记录列表，支持分页。
    """
    try:
        # team scoping（任务卡 e1f0e6d5）：非 admin 仅可查本 team 设备；越权/不存在 → 404。
        assert_device_team_access(db, device_id, user)

        query = db.query(V2GDispatchLog).filter(
            V2GDispatchLog.device_id == device_id
        )
        total = query.count()
        records = (
            query.order_by(desc(V2GDispatchLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = [_serialize_log(r) for r in records]
        return paginated_response(items, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_v2g_dispatch_history 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/v2g/dispatch/active")
def get_active_dispatches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前所有活跃的V2G调度

    返回 status=pending 或 executing 的调度记录列表。
    """
    try:
        query = db.query(V2GDispatchLog).filter(
            V2GDispatchLog.status.in_(["pending", "executing"])
        )
        # team scoping（任务卡 e1f0e6d5）：非 admin 仅本 team 设备的活跃调度（device→station→team）。
        if not is_platform_admin(user):
            query = (
                query.join(Device, V2GDispatchLog.device_id == Device.id)
                .join(Station, Device.station_id == Station.id)
                .filter(Station.team_id == user.team_id)
            )
        total = query.count()
        records = (
            query.order_by(desc(V2GDispatchLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = [_serialize_log(r) for r in records]
        return paginated_response(items, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_active_dispatches 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})