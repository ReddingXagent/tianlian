"""设备固件升级 (OTA) 端点 (卡 43b26421)

补齐前端 deviceAPI.firmware 三端点 (原零实现, UI 点击「固件」即 404):
- GET  /{device_id}/firmware          当前版本 + released 可升级列表
- POST /{device_id}/firmware/upgrade  下发设备级升级任务 (DeviceUpgradeTask)
- GET  /{device_id}/firmware/status   最近一条升级任务状态

与网关级 /gateways/firmware* (gateways.py, UpgradeTask gateway_id 维度) 正交,
不动其模型与端点。team scoping 与 crud.py 同范式: 跨团队 404 (不泄露存在),
admin 平台级豁免。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db, get_async_db
from app.core.response import success_response
from app.models.device import Device
from app.models.device_upgrade_task import DeviceUpgradeTask
from app.models.gateway import Firmware
from app.models.user import User
from app.services.audit_service import audit_service

from ._shared import _check_device_team, _check_device_team_async, _ROUTER_DEPENDENCIES


router = APIRouter(dependencies=_ROUTER_DEPENDENCIES)


class FirmwareUpgradeRequest(BaseModel):
    target_version: str = Field(..., min_length=1, max_length=50)
    url: str = Field(None, max_length=500)
    force: bool = False


def _task_to_dict(t: DeviceUpgradeTask) -> dict:
    return {
        "id": t.id,
        "device_id": t.device_id,
        "target_version": t.target_version,
        "url": t.url,
        "force": bool(t.force),
        "status": t.status,
        "progress": t.progress,
        "error_message": t.error_message,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _get_scoped_device(db: Session, device_id: int, user: User) -> Device:
    """取设备 + team scoping (跨团队 404, admin 豁免), 与 crud.py get_device 同范式。"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    _check_device_team(db, device_id, user)
    return device


async def _get_scoped_device_async(db: AsyncSession, device_id: int, user: User) -> Device:
    """async 版 _get_scoped_device (卡 3f5b3d6b)。"""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    await _check_device_team_async(db, device_id, user)
    return device


@router.get("/{device_id}/firmware")
def check_firmware(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """固件检查: 设备当前版本 + released 且 model 匹配的可升级版本列表。"""
    device = _get_scoped_device(db, device_id, user)
    upgrades = (
        db.query(Firmware)
        .filter(
            Firmware.status == "released",
            Firmware.model == (device.model or ""),
        )
        .order_by(Firmware.version.desc())
        .all()
    )
    return success_response({
        "device_id": device.id,
        "model": device.model,
        "current_version": device.firmware_version,
        "upgrades": [{
            "version": f.version,
            "file_path": f.file_path,
            "file_size": f.file_size,
            "checksum": f.checksum,
            "changelog": f.changelog,
            "release_date": f.release_date.isoformat() if f.release_date else None,
        } for f in upgrades],
    })


@router.post("/{device_id}/firmware/upgrade")
async def upgrade_firmware(
    device_id: int,
    data: FirmwareUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    user: User = Depends(get_current_user),
):
    """下发设备固件升级任务。

    target_version 须有对应 released 且 model 匹配的 Firmware 记录;
    force=true 跳过该校验 (任务仍落库)。
    """
    device = await _get_scoped_device_async(db, device_id, user)

    if not data.force:
        result = await db.execute(
            select(Firmware).where(
                Firmware.version == data.target_version,
                Firmware.status == "released",
                Firmware.model == (device.model or ""),
            )
        )
        released = result.scalar_one_or_none()
        if not released:
            raise HTTPException(
                status_code=400,
                detail=f"固件版本 {data.target_version} 不存在或未发布",
            )

    task = DeviceUpgradeTask(
        device_id=device_id,
        target_version=data.target_version,
        url=data.url,
        force=1 if data.force else 0,
        status="pending",
        progress=0,
        created_by=user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # SZBUS 桩在线 → 直接下发 0x51 远程升级 (2026-10-10 固件体系闭环, 协议6.1)
    dispatch_note = ""
    try:
        from app.gateway.szbus import _gateway
        if _gateway is not None and getattr(device, "sn", None):
            session = _gateway._sessions.get(device.sn)
            if session and session.get("checked_in"):
                dl_url = data.url
                if not dl_url:
                    fw_result = await db.execute(
                        select(Firmware).where(Firmware.version == data.target_version)
                    )
                    fw = fw_result.scalar_one_or_none()
                    if fw:
                        dl_url = f"http://demo.example.com:8080/api/v1/gateways/firmware/{fw.id}/download"
                if dl_url:
                    sent = await _gateway.remote_upgrade(device.sn, data.target_version, dl_url)
                    task.status = "dispatched" if sent else "pending"
                    dispatch_note = "已下发0x51, 待桩响应" if sent else "桩离线, 任务保留"
                    await db.commit()
                else:
                    dispatch_note = "无下载地址(手填URL或固件库)"
            else:
                dispatch_note = "桩不在线, 任务保留待下发"
    except Exception as e:
        dispatch_note = f"下发异常: {e}"

    # 审计日志 (best-effort, 参照 gateways.py 范式)
    try:
        audit_service.log_crud(
            user_id=user.id,
            username=user.username,
            action="upgrade", module="devices",
            target_id=str(device_id),
            target_desc=f"固件升级任务下发: v{data.target_version} [{dispatch_note or '未尝试SZBUS下发'}]",
        )
    except Exception:
        pass

    return success_response(_task_to_dict(task), f"固件升级任务已下发{(' — ' + dispatch_note) if dispatch_note else ''}")


@router.get("/{device_id}/firmware/status")
def firmware_status(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """该设备最近一条升级任务状态。"""
    _get_scoped_device(db, device_id, user)
    task = (
        db.query(DeviceUpgradeTask)
        .filter(DeviceUpgradeTask.device_id == device_id)
        .order_by(DeviceUpgradeTask.id.desc())
        .first()
    )
    return success_response({
        "device_id": device_id,
        "task": _task_to_dict(task) if task else None,
    })
