"""
天链 V3 - 网关 API 路由 - 数据库版
"""
import hashlib
import logging
import os
import re

from fastapi import APIRouter, HTTPException, Query, Depends, Form, UploadFile, File
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from typing import Literal, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, get_async_db
from app.models.gateway import Gateway, GatewaySN, Firmware, UpgradeTask
from app.models.station import Station
from app.models.user import User
from app.api.deps import is_platform_admin, require_platform_admin
from app.services.audit_service import audit_service
from app.services.code_generator import CodeGenerator
from app.core.response import success_response, paginated_response, action_response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("device:edit"))])


# USING get_db FROM app.core.database


# ==================== Pydantic Models ====================

class GatewayCreate(BaseModel):
    sn: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    station_id: Optional[int] = None
    status: Optional[Literal["online", "offline", "maintenance", "fault"]] = "offline"
    firmware_version: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class GatewayUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    station_id: Optional[int] = None
    status: Optional[Literal["online", "offline", "maintenance", "fault"]] = None
    firmware_version: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class SNGenerate(BaseModel):
    count: int = Field(10, ge=1, le=1000)
    model: str = "TL-GW-100"
    batch_no: Optional[str] = None
    region: str = Field("HN", description="区域码，如HN(河南)、GD(广东)等")


class SNUpdate(BaseModel):
    gateway_id: Optional[int] = None
    station_id: Optional[int] = None
    team_id: Optional[int] = None


class FirmwareCreate(BaseModel):
    version: str
    model: str = Field(..., max_length=50)
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    checksum: Optional[str] = None
    changelog: Optional[str] = None
    created_by: Optional[int] = None


class FirmwareUpdate(BaseModel):
    changelog: Optional[str] = None
    status: Optional[Literal["draft", "released", "deprecated"]] = None


class UpgradeTaskCreate(BaseModel):
    gateway_id: int
    firmware_id: int
    created_by: Optional[int] = None


# ==================== Helpers ====================

# ─── 团队归属校验（任务卡 ed509541）───
# gateway 经 station 间接归属 team（自身无 team_id 列）；GatewaySN 自身带 team_id。
# admin/super_admin 平台级豁免；跨团队一律 404（不泄露存在）。


def _gateway_team_id(db: Session, gateway_id: int):
    """gateway → station.team_id（经 join）；gateway/station 不存在或未挂站点 → None。"""
    row = (
        db.query(Station.team_id)
        .join(Gateway, Gateway.station_id == Station.id)
        .filter(Gateway.id == gateway_id)
        .first()
    )
    return row[0] if row else None


def _check_gateway_team(db: Session, gateway_id: int, user: User, msg: str = "网关不存在") -> None:
    """非 admin 校验 gateway 经 station 归属本 team；不存在/跨团队/未挂站点 → 404。"""
    if is_platform_admin(user):
        return
    tid = _gateway_team_id(db, gateway_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _check_sn_team(db: Session, sn_id: int, user: User, msg: str = "SN码不存在") -> None:
    """非 admin 校验 GatewaySN 自身 team_id 归属本 team；不存在/跨团队 → 404。"""
    if is_platform_admin(user):
        return
    row = db.query(GatewaySN.team_id).filter(GatewaySN.id == sn_id).first()
    tid = row[0] if row else None
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _gateway_to_dict(g: Gateway) -> dict:
    return {
        "id": g.id,
        "sn": g.sn,
        "name": g.name,
        "model": g.model,
        "manufacturer": g.manufacturer,
        "station_id": g.station_id,
        "status": g.status,
        "firmware_version": g.firmware_version,
        "last_online": g.last_online.isoformat() if g.last_online else None,
        "ip_address": g.ip_address,
        "mac_address": g.mac_address,
        "location": g.location,
        "health_score": g.health_score,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
        "notes": g.notes,
    }


def _sn_to_dict(s: GatewaySN) -> dict:
    return {
        "id": s.id,
        "sn": s.sn,
        "model": s.model,
        "status": s.status,
        "batch_no": s.batch_no,
        "gateway_id": s.gateway_id,
        "station_id": s.station_id,
        "team_id": s.team_id,
        "generated_at": s.generated_at.isoformat() if s.generated_at else None,
        "written_at": s.written_at.isoformat() if s.written_at else None,
        "activated_at": s.activated_at.isoformat() if s.activated_at else None,
        "locked_at": s.locked_at.isoformat() if s.locked_at else None,
        "recalled_at": s.recalled_at.isoformat() if s.recalled_at else None,
        "generated_by": s.generated_by,
        "written_by": s.written_by,
        "activated_by": s.activated_by,
        "notes": s.notes,
    }


def _firmware_to_dict(f: Firmware) -> dict:
    return {
        "id": f.id,
        "version": f.version,
        "model": f.model,
        "file_path": f.file_path,
        "file_size": f.file_size,
        "checksum": f.checksum,
        "changelog": f.changelog,
        "release_date": f.release_date.isoformat() if f.release_date else None,
        "status": f.status,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        "created_by": f.created_by,
    }


def _upgrade_task_to_dict(t: UpgradeTask) -> dict:
    return {
        "id": t.id,
        "gateway_id": t.gateway_id,
        "firmware_id": t.firmware_id,
        "status": t.status,
        "progress": t.progress,
        "start_time": t.start_time.isoformat() if t.start_time else None,
        "end_time": t.end_time.isoformat() if t.end_time else None,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "created_by": t.created_by,
    }


# ==================== SN码管理 (固定路径 - 放在动态路径之前) ====================

@router.get("/sn")
def list_sn_codes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    batch_no: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取SN码列表（team scoping：非 admin 仅返回本 team SN）"""
    query = db.query(GatewaySN)
    if not is_platform_admin(user):
        query = query.filter(GatewaySN.team_id == user.team_id)
    if status:
        query = query.filter(GatewaySN.status == status)
    if batch_no:
        query = query.filter(GatewaySN.batch_no == batch_no)

    total = query.count()
    items = query.order_by(GatewaySN.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_sn_to_dict(s) for s in items],
        total, page, page_size
    )


@router.post("/sn/generate")
def generate_sn_codes(data: SNGenerate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """批量生成SN码 - 使用结构化编码。

    team scoping（任务卡 ed509541）：非 admin 生成的 SN 强制归属其本 team
    （GatewaySN.team_id = user.team_id），SN 无客户端传入的 team_id 字段可伪造。
    """
    import random
    batch_no = data.batch_no or f"BATCH-{random.randint(1000, 9999)}"
    now = datetime.now(timezone.utc)

    # 使用新的编码生成器
    try:
        sn_codes_list = CodeGenerator.batch_generate_gateway_sn(data.count, data.region, db)
    except ValueError as e:
        logger.exception("批量生成SN码失败 batch=%s count=%s", data.batch_no, data.count)
        raise HTTPException(status_code=400, detail="SN码生成失败, 请检查参数")

    # 非 admin 强制本团队；admin 不绑定（平台级生成）
    sn_team_id = None if is_platform_admin(user) else user.team_id

    # 保存到数据库
    sn_codes = []
    for sn_str in sn_codes_list:
        sn = GatewaySN(
            sn=sn_str,  # 使用结构化编码
            model=data.model,
            batch_no=batch_no,
            team_id=sn_team_id,
            status="generated",
            generated_at=now,
        )
        db.add(sn)
        sn_codes.append(sn)

    # 持久化 GatewaySN 行: batch_generate_gateway_sn 的内部 commit 只落序列自增,
    # 此处 add 的行必须显式 commit, 否则 get_db() 关闭 session 时隐式回滚 (卡 3681a8c6)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("SN码生成落库失败 batch=%s count=%s", batch_no, data.count)
        raise HTTPException(status_code=500, detail="服务器内部错误")
    for s in sn_codes:
        db.refresh(s)

    return success_response({
        "count": data.count,
        "batch_no": batch_no,
        "region": data.region,
        "items": [_sn_to_dict(s) for s in sn_codes],
    }, message=f"已生成 {data.count} 个结构化SN码 (区域: {data.region})")


@router.post("/sn/{sn_id}/write")
def write_sn_code(
    sn_id: int,
    data: SNUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """写入SN码到网关（team scoping：跨团队 SN → 404）"""
    sn = db.query(GatewaySN).filter(GatewaySN.id == sn_id).first()
    if not sn:
        raise HTTPException(status_code=404, detail="SN码不存在")
    _check_sn_team(db, sn_id, current_user)
    if sn.status != "generated":
        raise HTTPException(status_code=400, detail=f"SN码状态为 {sn.status}，无法写入")

    sn.status = "written"
    sn.gateway_id = data.gateway_id
    sn.written_at = datetime.now(timezone.utc)
    sn.written_by = current_user.id
    db.commit()
    db.refresh(sn)
    return success_response(_sn_to_dict(sn))


@router.post("/sn/{sn_id}/activate")
def activate_sn_code(
    sn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """激活SN码（team scoping：跨团队 SN → 404）"""
    sn = db.query(GatewaySN).filter(GatewaySN.id == sn_id).first()
    if not sn:
        raise HTTPException(status_code=404, detail="SN码不存在")
    _check_sn_team(db, sn_id, current_user)
    if sn.status not in ("generated", "written"):
        raise HTTPException(status_code=400, detail=f"SN码状态为 {sn.status}，无法激活")

    sn.status = "activated"
    sn.activated_at = datetime.now(timezone.utc)
    sn.activated_by = current_user.id
    db.commit()
    db.refresh(sn)
    return success_response(_sn_to_dict(sn))


@router.post("/sn/{sn_id}/lock")
def lock_sn_code(sn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """锁定SN码（team scoping：跨团队 SN → 404）"""
    sn = db.query(GatewaySN).filter(GatewaySN.id == sn_id).first()
    if not sn:
        raise HTTPException(status_code=404, detail="SN码不存在")
    _check_sn_team(db, sn_id, user)
    if sn.status == "locked":
        raise HTTPException(status_code=400, detail="SN码已锁定")

    sn.status = "locked"
    sn.locked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sn)
    return success_response(_sn_to_dict(sn))


@router.post("/sn/{sn_id}/recall")
def recall_sn_code(sn_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """召回SN码（team scoping：跨团队 SN → 404）"""
    sn = db.query(GatewaySN).filter(GatewaySN.id == sn_id).first()
    if not sn:
        raise HTTPException(status_code=404, detail="SN码不存在")
    _check_sn_team(db, sn_id, user)

    sn.status = "recalled"
    sn.recalled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sn)
    return success_response(_sn_to_dict(sn))


# ==================== 固件管理 ====================

@router.get("/firmware")
def list_firmware(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取固件列表"""
    query = db.query(Firmware)
    if model:
        query = query.filter(Firmware.model == model)
    if status:
        query = query.filter(Firmware.status == status)

    total = query.count()
    items = query.order_by(Firmware.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_firmware_to_dict(f) for f in items],
        total, page, page_size
    )


@router.post("/firmware", dependencies=[Depends(require_platform_admin)])
def create_firmware(data: FirmwareCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """上传固件"""
    existing = db.query(Firmware).filter(Firmware.version == data.version).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"固件版本 {data.version} 已存在")

    firmware = Firmware(**data.model_dump(), status="draft")
    db.add(firmware)
    db.commit()
    db.refresh(firmware)
    # 审计日志(2026-10-10 修复: 原写在return后永不执行)
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="gateways",
            target_id=str(firmware.id), target_desc=f"上传固件:v{firmware.version}",
        )
    except Exception:
        pass
    return success_response(_firmware_to_dict(firmware))


FIRMWARE_DIR = "/opt/tianlian-cloud/backend/firmware"
# 固件包硬上限 (网关/PCS .bin 常见 20MB+, 全局 10MB 中间件对该路径豁免, 端点内自设此上限)
FIRMWARE_MAX_BYTES = 200 * 1024 * 1024
# 卡7502e6fb 缺陷1: version 拼进落盘文件名, 白名单防路径穿越 (../ 或绝对路径可逃逸 FIRMWARE_DIR)
_FIRMWARE_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@router.post("/firmware/upload", dependencies=[Depends(require_platform_admin)])
async def upload_firmware(
    file: UploadFile = File(...),
    version: str = Form(None),
    model: str = Form(None),
    changelog: str = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    """上传固件包(.bin) — 存服务器固件目录, 自动算MD5/大小, 落库draft (2026-10-10 丁哥固件体系)"""
    if not version or not model:
        raise HTTPException(status_code=400, detail="version 与 model 必填")
    if not _FIRMWARE_VERSION_RE.fullmatch(version):
        raise HTTPException(status_code=400, detail="version 含非法字符, 仅允许字母/数字/./_/-")
    existing_result = await db.execute(select(Firmware).where(Firmware.version == version))
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"固件版本 {version} 已存在")

    os.makedirs(FIRMWARE_DIR, exist_ok=True)
    safe_name = os.path.basename(file.filename or f"fw-{version}.bin")
    dest = os.path.join(FIRMWARE_DIR, f"{version}_{safe_name}")
    md5 = hashlib.md5()
    size = 0
    oversize = False
    with open(dest, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            # 卡7502e6fb 缺陷2: 中间件豁免后端点内分块计数硬上限, 防滥用
            if size > FIRMWARE_MAX_BYTES:
                oversize = True
                break
            out.write(chunk)
            md5.update(chunk)
    if oversize:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise HTTPException(
            status_code=413,
            detail=f"固件包超过 {FIRMWARE_MAX_BYTES // (1024 * 1024)}MB 上限",
        )

    firmware = Firmware(
        version=version, model=model,
        file_path=dest, file_size=size, checksum=md5.hexdigest(),
        changelog=changelog or "", status="draft",
    )
    db.add(firmware)
    await db.commit()
    await db.refresh(firmware)
    return success_response(_firmware_to_dict(firmware))


@router.get("/firmware/{firmware_id}/download")
def download_firmware(firmware_id: int, db: Session = Depends(get_db)):
    """固件包下载(桩端升级取包/运维存档)"""
    from fastapi.responses import FileResponse
    firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()
    if not firmware or not firmware.file_path or not os.path.exists(firmware.file_path):
        raise HTTPException(status_code=404, detail="固件文件不存在")
    return FileResponse(firmware.file_path, filename=os.path.basename(firmware.file_path))


@router.post("/firmware/{firmware_id}/release", dependencies=[Depends(require_platform_admin)])
def release_firmware(firmware_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """发布固件"""
    firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()
    if not firmware:
        raise HTTPException(status_code=404, detail="固件不存在")

    firmware.status = "released"
    firmware.release_date = datetime.now(timezone.utc)
    db.commit()
    db.refresh(firmware)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="gateways",
            target_id=str(firmware_id), target_desc=f"发布固件:v{firmware.version}",
        )
    except Exception:
        pass
    return success_response(_firmware_to_dict(firmware))


@router.put("/firmware/{firmware_id}", dependencies=[Depends(require_platform_admin)])
def update_firmware(firmware_id: int, data: FirmwareUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新固件"""
    firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()
    if not firmware:
        raise HTTPException(status_code=404, detail="固件不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(firmware, key, value)

    db.commit()
    db.refresh(firmware)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="gateways",
            target_id=str(firmware_id), target_desc=f"更新固件:{firmware_id}",
        )
    except Exception:
        pass
    return success_response(_firmware_to_dict(firmware))


@router.delete("/firmware/{firmware_id}", dependencies=[Depends(require_platform_admin)])
def delete_firmware(firmware_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除固件"""
    firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()
    if not firmware:
        raise HTTPException(status_code=404, detail="固件不存在")
    db.delete(firmware)
    db.commit()
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="delete", module="gateways",
            target_id=str(firmware_id), target_desc=f"删除固件:{firmware_id}",
        )
    except Exception:
        pass
    return action_response(success=True, message=f"固件 {firmware_id} 已删除")


# ==================== 升级任务 ====================

@router.get("/upgrade-tasks")
def list_upgrade_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    gateway_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取升级任务列表（team scoping：非 admin 仅本 team 网关的任务）"""
    query = db.query(UpgradeTask)
    if not is_platform_admin(user):
        query = query.join(Gateway, UpgradeTask.gateway_id == Gateway.id) \
                     .join(Station, Gateway.station_id == Station.id) \
                     .filter(Station.team_id == user.team_id)
    if gateway_id:
        query = query.filter(UpgradeTask.gateway_id == gateway_id)
    if status:
        query = query.filter(UpgradeTask.status == status)

    total = query.count()
    items = query.order_by(UpgradeTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_upgrade_task_to_dict(t) for t in items],
        total, page, page_size
    )


@router.get("/upgrade-tasks/{task_id}")
def get_upgrade_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取升级任务详情（team scoping：跨团队 → 404）"""
    task = db.query(UpgradeTask).filter(UpgradeTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="升级任务不存在")
    _check_gateway_team(db, task.gateway_id, user, "升级任务不存在")
    return success_response(_upgrade_task_to_dict(task))


@router.post("/upgrade-tasks")
def create_upgrade_task(data: UpgradeTaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建升级任务（team scoping：非 admin 仅可为本 team 网关建任务）"""
    _check_gateway_team(db, data.gateway_id, user)
    task = UpgradeTask(
        gateway_id=data.gateway_id,
        firmware_id=data.firmware_id,
        status="pending",
        progress=0,
        created_by=data.created_by or 1,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="gateways",
            target_id=str(task.id), target_desc=f"创建升级任务:网关{task.gateway_id}固件{task.firmware_id}",
        )
    except Exception:
        pass
    return success_response(_upgrade_task_to_dict(task))


@router.post("/upgrade-tasks/{task_id}/start")
def start_upgrade_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """启动升级任务（team scoping：跨团队 → 404）"""
    task = db.query(UpgradeTask).filter(UpgradeTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="升级任务不存在")
    _check_gateway_team(db, task.gateway_id, user, "升级任务不存在")
    if task.status != "pending":
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无法启动")

    task.status = "running"
    task.progress = 0
    task.start_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="gateways",
            target_id=str(task_id), target_desc=f"启动升级任务:{task_id}",
        )
    except Exception:
        pass
    return success_response(_upgrade_task_to_dict(task))


@router.post("/upgrade-tasks/{task_id}/cancel")
def cancel_upgrade_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """取消升级任务（team scoping：跨团队 → 404）"""
    task = db.query(UpgradeTask).filter(UpgradeTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="升级任务不存在")
    _check_gateway_team(db, task.gateway_id, user, "升级任务不存在")

    task.status = "cancelled"
    task.end_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="gateways",
            target_id=str(task_id), target_desc=f"取消升级任务:{task_id}",
        )
    except Exception:
        pass
    return success_response(_upgrade_task_to_dict(task))


@router.put("/upgrade-tasks/{task_id}")
def update_upgrade_task(task_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新升级任务进度（team scoping：跨团队 → 404）"""
    task = db.query(UpgradeTask).filter(UpgradeTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="升级任务不存在")
    _check_gateway_team(db, task.gateway_id, user, "升级任务不存在")

    if "progress" in data:
        task.progress = data["progress"]
    if "status" in data:
        task.status = data["status"]
    if "error_message" in data:
        task.error_message = data["error_message"]
    if data.get("status") in ("success", "failed"):
        task.end_time = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)
    return success_response(_upgrade_task_to_dict(task))


# ==================== 网关综合状态 ====================

@router.get("/status")
def get_gateway_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取所有网关的综合状态汇总（team scoping：非 admin 仅统计本 team 网关）"""
    q = db.query(Gateway)
    if not is_platform_admin(user):
        q = q.join(Station, Gateway.station_id == Station.id) \
             .filter(Station.team_id == user.team_id)
    gateways = q.all()
    total = len(gateways)
    online_count = sum(1 for g in gateways if g.status == "online")
    offline_count = sum(1 for g in gateways if g.status == "offline")
    maintenance_count = sum(1 for g in gateways if g.status == "maintenance")
    fault_count = sum(1 for g in gateways if g.status == "fault")

    return success_response({
        "online_count": online_count,
        "offline_count": offline_count,
        "maintenance_count": maintenance_count,
        "fault_count": fault_count,
        "total": total,
    })


# ==================== 网关管理 (动态路径 - 放在固定路径之后) ====================

@router.get("")
def list_gateways(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取网关列表（team scoping：非 admin 仅返回本 team 网关，经 station→team）"""
    query = db.query(Gateway)
    if not is_platform_admin(user):
        query = query.join(Station, Gateway.station_id == Station.id) \
                     .filter(Station.team_id == user.team_id)
    if station_id:
        query = query.filter(Gateway.station_id == station_id)
    if status:
        query = query.filter(Gateway.status == status)

    total = query.count()
    items = query.order_by(Gateway.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_gateway_to_dict(g) for g in items],
        total, page, page_size
    )


@router.get("/{gateway_id}")
def get_gateway(gateway_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取网关详情（team scoping：跨团队 → 404）"""
    gateway = db.query(Gateway).filter(Gateway.id == gateway_id).first()
    if not gateway:
        raise HTTPException(status_code=404, detail="网关不存在")
    _check_gateway_team(db, gateway_id, user)
    return success_response(_gateway_to_dict(gateway))


@router.post("")
def create_gateway(data: GatewayCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建网关。

    team scoping（任务卡 ed509541）：非 admin 必须指定本 team 站点（station_id），
    网关归属经 station 间接判定；指定他团站点 → 404（不泄露存在）。
    admin 可不指定站点（平台级未部署网关）。
    """
    existing = db.query(Gateway).filter(Gateway.sn == data.sn).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"网关SN {data.sn} 已存在")

    if not is_platform_admin(user):
        if data.station_id is None:
            raise HTTPException(status_code=400, detail="需指定本团队站点 station_id")
        st = db.query(Station).filter(Station.id == data.station_id).first()
        if st is None or st.team_id is None or st.team_id != user.team_id:
            raise HTTPException(status_code=404, detail="站点不存在")

    gateway = Gateway(**data.model_dump())
    db.add(gateway)
    db.commit()
    db.refresh(gateway)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="gateways",
            target_id=str(gateway.id), target_desc=f"创建网关:{data.sn}",
        )
    except Exception:
        pass
    return success_response(_gateway_to_dict(gateway))


@router.put("/{gateway_id}")
def update_gateway(gateway_id: int, data: GatewayUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新网关（team scoping：跨团队 → 404）"""
    gateway = db.query(Gateway).filter(Gateway.id == gateway_id).first()
    if not gateway:
        raise HTTPException(status_code=404, detail="网关不存在")
    _check_gateway_team(db, gateway_id, user)

    update_data = data.model_dump(exclude_unset=True)
    # 非 admin 不得把网关转移到他团站点（station_id 变更需校验新站点归属）
    if not is_platform_admin(user) and "station_id" in update_data and update_data["station_id"] is not None:
        st = db.query(Station).filter(Station.id == update_data["station_id"]).first()
        if st is None or st.team_id is None or st.team_id != user.team_id:
            raise HTTPException(status_code=404, detail="站点不存在")
    for key, value in update_data.items():
        setattr(gateway, key, value)

    db.commit()
    db.refresh(gateway)
    return success_response(_gateway_to_dict(gateway))


@router.delete("/{gateway_id}")
def delete_gateway(gateway_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除网关（team scoping：跨团队 → 404）"""
    gateway = db.query(Gateway).filter(Gateway.id == gateway_id).first()
    if not gateway:
        raise HTTPException(status_code=404, detail="网关不存在")
    _check_gateway_team(db, gateway_id, user)
    db.delete(gateway)
    db.commit()
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="delete", module="gateways",
            target_id=str(gateway_id), target_desc=f"删除网关:{gateway.sn if gateway.sn else gateway_id}",
        )
    except Exception:
        pass
    return action_response(success=True, message=f"网关 {gateway_id} 已删除")
