"""
设备型号库管理 API (admin-platform-spec §2.4)

功能:
- 设备型号库 CRUD(光储充设备模板: 品牌/型号/类型/额定功率/参数模板/支持协议/规格书)
- 搜索、分页、详情
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, Literal
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.device_library import DeviceLibrary
from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response, action_response
from app.api.deps import get_current_user, require_platform_admin
from app.middleware.permission import require_write_permission

router = APIRouter(tags=["设备库管理"], dependencies=[Depends(require_write_permission("device:edit"))])


# ========== Schemas ==========

class DeviceLibraryCreate(BaseModel):
    brand: str = Field(..., max_length=100)
    model: str = Field(..., max_length=100)
    device_type: str = Field(..., max_length=50)
    rated_power_kw: Optional[float] = None
    params_template: Optional[dict] = None
    supported_protocols: Optional[list] = None
    spec_url: Optional[str] = None

class DeviceLibraryUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    device_type: Optional[str] = None
    rated_power_kw: Optional[float] = None
    params_template: Optional[dict] = None
    supported_protocols: Optional[list] = None
    spec_url: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


def _to_dict(item: DeviceLibrary) -> dict:
    return {
        "id": item.id,
        "brand": item.brand,
        "model": item.model,
        "device_type": item.device_type,
        "rated_power_kw": item.rated_power_kw,
        "params_template": item.params_template,
        "supported_protocols": item.supported_protocols,
        "spec_url": item.spec_url,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


# ========== API Endpoints ==========

@router.get("", summary="获取设备型号库列表")
def list_device_library(
    device_type: Optional[str] = None,
    keyword: Optional[str] = Query(None),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """获取设备型号库列表，支持按类型过滤和分页搜索"""
    q = db.query(DeviceLibrary)
    if device_type:
        q = q.filter(DeviceLibrary.device_type == device_type)

    search_term = keyword or search
    if search_term:
        like = f"%{search_term}%"
        q = q.filter(
            DeviceLibrary.brand.ilike(like) | DeviceLibrary.model.ilike(like)
        )

    total = q.count()
    items = (
        q.order_by(DeviceLibrary.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response(
        items=[_to_dict(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", summary="创建设备型号", dependencies=[Depends(require_platform_admin)])
def create_device_library(
    data: DeviceLibraryCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """创建新的设备型号条目"""
    item = DeviceLibrary(
        brand=data.brand,
        model=data.model,
        device_type=data.device_type,
        rated_power_kw=data.rated_power_kw,
        params_template=data.params_template,
        supported_protocols=data.supported_protocols,
        spec_url=data.spec_url,
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="create", module="device_library",
            target_id=str(item.id),
            target_desc=f"创建设备型号:{item.brand} {item.model}",
        )
    except Exception:
        pass
    return success_response(_to_dict(item), message="设备型号创建成功")


@router.get("/{item_id}", summary="获取设备型号详情")
def get_device_library(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """获取设备型号详情"""
    item = db.query(DeviceLibrary).filter(DeviceLibrary.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="设备型号不存在")
    return success_response(_to_dict(item))


@router.put("/{item_id}", summary="更新设备型号", dependencies=[Depends(require_platform_admin)])
def update_device_library(
    item_id: int,
    data: DeviceLibraryUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """更新设备型号条目"""
    item = db.query(DeviceLibrary).filter(DeviceLibrary.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="设备型号不存在")

    changed = False
    for field in [
        "brand", "model", "device_type", "rated_power_kw",
        "params_template", "supported_protocols", "spec_url", "status",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(item, field, val)
            changed = True

    if not changed:
        return action_response(message="无需更新")

    db.commit()
    db.refresh(item)

    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="update", module="device_library",
            target_id=str(item_id), target_desc=f"更新设备型号:{item_id}",
        )
    except Exception:
        pass
    return action_response(message="设备型号更新成功")


@router.delete("/{item_id}", summary="删除设备型号", dependencies=[Depends(require_platform_admin)])
def delete_device_library(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """删除设备型号条目"""
    item = db.query(DeviceLibrary).filter(DeviceLibrary.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="设备型号不存在")

    db.delete(item)
    db.commit()

    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="delete", module="device_library",
            target_id=str(item_id), target_desc=f"删除设备型号:{item_id}",
        )
    except Exception:
        pass
    return action_response(message="设备型号删除成功")
