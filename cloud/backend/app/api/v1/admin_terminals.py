"""
管理后台 - 终端管理 API (SPEC §2.4)

终端设备(摄像头/传感器/门禁)的接入登记与状态管理。
- /admin/terminals   CRUD + 按站点/类型/状态筛选 + 关键字搜索
"""
import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import require_role
from app.core.response import success_response, paginated_response
from app.models.admin_terminals import (
    Terminal, TERMINAL_TYPES, TERMINAL_STATUS,
)

router = APIRouter(dependencies=[Depends(require_role("admin"))])


# ========== Schemas ==========

class TerminalCreate(BaseModel):
    terminal_code: str = Field(..., max_length=100, description="终端编号(唯一)")
    terminal_type: Literal["camera", "sensor", "access_control"] = Field(..., description="类型 camera/sensor/access_control")
    station_name: Optional[str] = Field(None, description="安装站点")
    ip_address: Optional[str] = Field(None, description="IP地址")
    rtsp_url: Optional[str] = Field(None, description="流地址 RTSP/RTMP")
    recording_config: Optional[dict] = Field(None, description="录制配置(JSON)")
    status: Literal["online", "offline", "maintenance"] = Field("offline", description="状态 online/offline/maintenance")
    remark: Optional[str] = None


class TerminalUpdate(BaseModel):
    terminal_code: Optional[str] = None
    terminal_type: Optional[Literal["camera", "sensor", "access_control"]] = None
    station_name: Optional[str] = None
    ip_address: Optional[str] = None
    rtsp_url: Optional[str] = None
    recording_config: Optional[dict] = None
    status: Optional[Literal["online", "offline", "maintenance"]] = None
    remark: Optional[str] = None


# ========== Helpers ==========

def _dump(v: Any) -> Optional[str]:
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def _load(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _to_dict(t: Terminal) -> dict:
    return {
        "id": t.id,
        "terminal_code": t.terminal_code,
        "terminal_type": t.terminal_type,
        "station_name": t.station_name,
        "ip_address": t.ip_address,
        "rtsp_url": t.rtsp_url,
        "recording_config": _load(t.recording_config),
        "status": t.status,
        "remark": t.remark,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ========== CRUD ==========

@router.get("", summary="终端设备列表")
def list_terminals(
    terminal_type: Optional[str] = Query(None, description="类型 camera/sensor/access_control"),
    station_name: Optional[str] = Query(None, description="站点精确匹配"),
    status: Optional[str] = Query(None, description="状态 online/offline/maintenance"),
    keyword: Optional[str] = Query(None, description="按终端编号模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Terminal)
    if terminal_type:
        q = q.filter(Terminal.terminal_type == terminal_type)
    if station_name:
        q = q.filter(Terminal.station_name == station_name)
    if status:
        q = q.filter(Terminal.status == status)
    if keyword:
        q = q.filter(Terminal.terminal_code.like(f"%{keyword}%"))

    total = q.count()
    items = q.order_by(Terminal.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[_to_dict(t) for t in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", summary="新增终端设备")
def create_terminal(data: TerminalCreate, db: Session = Depends(get_db)):
    if data.terminal_type not in TERMINAL_TYPES:
        raise HTTPException(400, f"terminal_type 取值: {TERMINAL_TYPES}")
    if data.status not in TERMINAL_STATUS:
        raise HTTPException(400, f"status 取值: {TERMINAL_STATUS}")
    if db.query(Terminal).filter(Terminal.terminal_code == data.terminal_code).first():
        raise HTTPException(400, "终端编号已存在")

    t = Terminal(
        terminal_code=data.terminal_code,
        terminal_type=data.terminal_type,
        station_name=data.station_name,
        ip_address=data.ip_address,
        rtsp_url=data.rtsp_url,
        recording_config=_dump(data.recording_config),
        status=data.status,
        remark=data.remark,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return success_response(_to_dict(t), message="终端设备已创建")


@router.get("/{terminal_id}", summary="终端设备详情")
def get_terminal(terminal_id: int, db: Session = Depends(get_db)):
    t = db.query(Terminal).filter(Terminal.id == terminal_id).first()
    if not t:
        raise HTTPException(404, "终端设备不存在")
    return success_response(_to_dict(t))


@router.put("/{terminal_id}", summary="更新终端设备")
def update_terminal(terminal_id: int, data: TerminalUpdate, db: Session = Depends(get_db)):
    t = db.query(Terminal).filter(Terminal.id == terminal_id).first()
    if not t:
        raise HTTPException(404, "终端设备不存在")

    payload = data.model_dump(exclude_unset=True)
    if "terminal_type" in payload and payload["terminal_type"] not in TERMINAL_TYPES:
        raise HTTPException(400, f"terminal_type 取值: {TERMINAL_TYPES}")
    if "status" in payload and payload["status"] not in TERMINAL_STATUS:
        raise HTTPException(400, f"status 取值: {TERMINAL_STATUS}")
    if "terminal_code" in payload and payload["terminal_code"] != t.terminal_code:
        if db.query(Terminal).filter(Terminal.terminal_code == payload["terminal_code"]).first():
            raise HTTPException(400, "终端编号已存在")

    for k, v in payload.items():
        if k == "recording_config":
            t.recording_config = _dump(v)
        else:
            setattr(t, k, v)

    db.commit()
    db.refresh(t)
    return success_response(_to_dict(t), message="终端设备已更新")


@router.delete("/{terminal_id}", summary="删除终端设备")
def delete_terminal(terminal_id: int, db: Session = Depends(get_db)):
    t = db.query(Terminal).filter(Terminal.id == terminal_id).first()
    if not t:
        raise HTTPException(404, "终端设备不存在")
    db.delete(t)
    db.commit()
    return success_response({"id": terminal_id}, message="终端设备已删除")
