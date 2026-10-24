"""
管理后台 - 云服务配置 API (SPEC §2.4)

公有云/私有云的对接配置(存储桶 + 同步策略) CRUD + 连通性测试(模拟)。
- /admin/cloud-configs   CRUD + 按提供商/策略/状态筛选 + 连通性测试
"""
import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import require_role
from app.core.response import success_response, paginated_response
from app.models.admin_terminals import (
    CloudConfig, CLOUD_PROVIDERS, SYNC_STRATEGIES, CLOUD_CONFIG_STATUS,
)

router = APIRouter(dependencies=[Depends(require_role("admin"))])


# ========== Schemas ==========

class CloudConfigCreate(BaseModel):
    config_name: str = Field(..., max_length=100, description="配置名称")
    provider: Literal["cloud-a", "cloud-b", "aws", "private"] = Field(..., description="云提供商 cloud_provider/vendor_b/aws/private")
    config_json: Optional[dict] = Field(None, description="配置JSON: region/endpoint/access配置")
    bucket: Optional[str] = Field(None, description="存储桶")
    sync_strategy: Literal["realtime", "hourly", "daily"] = Field("hourly", description="数据同步策略 realtime/hourly/daily")
    status: Literal["active", "inactive"] = Field("active", description="状态 active/inactive")
    remark: Optional[str] = None


class CloudConfigUpdate(BaseModel):
    config_name: Optional[str] = None
    provider: Optional[Literal["cloud-a", "cloud-b", "aws", "private"]] = None
    config_json: Optional[dict] = None
    bucket: Optional[str] = None
    sync_strategy: Optional[Literal["realtime", "hourly", "daily"]] = None
    status: Optional[Literal["active", "inactive"]] = None
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


def _to_dict(c: CloudConfig) -> dict:
    return {
        "id": c.id,
        "config_name": c.config_name,
        "provider": c.provider,
        "config_json": _load(c.config_json),
        "bucket": c.bucket,
        "sync_strategy": c.sync_strategy,
        "status": c.status,
        "remark": c.remark,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ========== CRUD ==========

@router.get("", summary="云服务配置列表")
def list_cloud_configs(
    provider: Optional[str] = Query(None, description="提供商 cloud_provider/vendor_b/aws/private"),
    sync_strategy: Optional[str] = Query(None, description="同步策略 realtime/hourly/daily"),
    status: Optional[str] = Query(None, description="状态 active/inactive"),
    keyword: Optional[str] = Query(None, description="按配置名称模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(CloudConfig)
    if provider:
        q = q.filter(CloudConfig.provider == provider)
    if sync_strategy:
        q = q.filter(CloudConfig.sync_strategy == sync_strategy)
    if status:
        q = q.filter(CloudConfig.status == status)
    if keyword:
        q = q.filter(CloudConfig.config_name.like(f"%{keyword}%"))

    total = q.count()
    items = q.order_by(CloudConfig.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[_to_dict(c) for c in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", summary="新增云服务配置")
def create_cloud_config(data: CloudConfigCreate, db: Session = Depends(get_db)):
    if data.provider not in CLOUD_PROVIDERS:
        raise HTTPException(400, f"provider 取值: {CLOUD_PROVIDERS}")
    if data.sync_strategy not in SYNC_STRATEGIES:
        raise HTTPException(400, f"sync_strategy 取值: {SYNC_STRATEGIES}")
    if data.status not in CLOUD_CONFIG_STATUS:
        raise HTTPException(400, f"status 取值: {CLOUD_CONFIG_STATUS}")

    c = CloudConfig(
        config_name=data.config_name,
        provider=data.provider,
        config_json=_dump(data.config_json),
        bucket=data.bucket,
        sync_strategy=data.sync_strategy,
        status=data.status,
        remark=data.remark,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return success_response(_to_dict(c), message="云服务配置已创建")


@router.get("/{config_id}", summary="云服务配置详情")
def get_cloud_config(config_id: int, db: Session = Depends(get_db)):
    c = db.query(CloudConfig).filter(CloudConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "云服务配置不存在")
    return success_response(_to_dict(c))


@router.put("/{config_id}", summary="更新云服务配置")
def update_cloud_config(config_id: int, data: CloudConfigUpdate, db: Session = Depends(get_db)):
    c = db.query(CloudConfig).filter(CloudConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "云服务配置不存在")

    payload = data.model_dump(exclude_unset=True)
    if "provider" in payload and payload["provider"] not in CLOUD_PROVIDERS:
        raise HTTPException(400, f"provider 取值: {CLOUD_PROVIDERS}")
    if "sync_strategy" in payload and payload["sync_strategy"] not in SYNC_STRATEGIES:
        raise HTTPException(400, f"sync_strategy 取值: {SYNC_STRATEGIES}")
    if "status" in payload and payload["status"] not in CLOUD_CONFIG_STATUS:
        raise HTTPException(400, f"status 取值: {CLOUD_CONFIG_STATUS}")

    for k, v in payload.items():
        if k == "config_json":
            c.config_json = _dump(v)
        else:
            setattr(c, k, v)

    db.commit()
    db.refresh(c)
    return success_response(_to_dict(c), message="云服务配置已更新")


@router.delete("/{config_id}", summary="删除云服务配置")
def delete_cloud_config(config_id: int, db: Session = Depends(get_db)):
    c = db.query(CloudConfig).filter(CloudConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "云服务配置不存在")
    db.delete(c)
    db.commit()
    return success_response({"id": config_id}, message="云服务配置已删除")


@router.post("/{config_id}/test", summary="连通性测试(模拟)")
def test_cloud_config(config_id: int, db: Session = Depends(get_db)):
    c = db.query(CloudConfig).filter(CloudConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "云服务配置不存在")
    # mock 连通性: 后端不真实发起请求, 统一返回成功
    # (真实云连通性测试需带凭证发请求, 此处仅校验配置存在)
    return success_response({
        "config_id": c.id,
        "config_name": c.config_name,
        "provider": c.provider,
        "reachable": True,
        "storage_ok": True,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }, message="连通性测试通过")
