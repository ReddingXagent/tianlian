"""
API Key management API
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.models.api_key import ApiKey, ApiKeyUsageLog, generate_api_key, hash_api_key
from app.models.user import User
from app.api.deps import get_current_user
from app.middleware.permission import require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["API Key"])


class ApiKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    ip_whitelist: Optional[List[str]] = None
    rate_limit: int = Field(default=1000, ge=1, le=10000)
    expires_days: Optional[int] = Field(default=None, ge=1, le=365)


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    ip_whitelist: Optional[List[str]] = None
    rate_limit: Optional[int] = Field(default=None, ge=1, le=10000)
    is_active: Optional[bool] = None


@router.get("", summary="List API Keys")
def list_api_keys(
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    query = db.query(ApiKey).filter(ApiKey.user_id == current_user.id)
    if is_active is not None:
        query = query.filter(ApiKey.is_active == is_active)
    total = query.count()
    items = query.order_by(ApiKey.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response(
        items=[{
            "id": k.id, "name": k.name, "key_prefix": k.key_prefix,
            "description": k.description, "scopes": k.scopes,
            "rate_limit": k.rate_limit, "is_active": k.is_active,
            "is_revoked": k.is_revoked,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        } for k in items],
        total=total, page=page, page_size=page_size
    )


@router.post("", summary="Create API Key")
def create_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:10]
    expires_at = None
    if data.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)
    api_key = ApiKey(
        key_hash=key_hash, key_prefix=key_prefix,
        user_id=current_user.id, name=data.name,
        description=data.description, scopes=data.scopes,
        ip_whitelist=data.ip_whitelist, rate_limit=data.rate_limit,
        expires_at=expires_at,
    )
    db.add(api_key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("API Key 写入冲突 name=%s", data.name)
        raise HTTPException(status_code=409, detail="API Key 已存在")
    except Exception:
        db.rollback()
        logger.exception("API Key 创建失败 name=%s", data.name)
        raise HTTPException(status_code=500, detail="API Key 创建失败")
    db.refresh(api_key)
    return success_response({
        "id": api_key.id, "name": api_key.name,
        "api_key": raw_key, "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
    }, message="API Key created")


@router.get("/usage-stats", summary="Usage Stats")
def get_global_usage_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    from sqlalchemy import func
    user_keys = db.query(ApiKey.id).filter(ApiKey.user_id == current_user.id).subquery()
    total = db.query(func.count(ApiKeyUsageLog.id)).filter(
        ApiKeyUsageLog.api_key_id.in_(db.query(user_keys.c.id))
    ).scalar() or 0
    active_keys = db.query(func.count(ApiKey.id)).filter(
        ApiKey.user_id == current_user.id, ApiKey.is_active == True, ApiKey.is_revoked == False
    ).scalar() or 0
    return success_response({"total_usage": total, "active_keys": active_keys})

@router.delete("/{key_id}", summary="Revoke API Key")
def revoke_api_key(
    key_id: int, reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    api_key.is_revoked = True
    api_key.revoked_reason = reason
    api_key.revoked_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("API Key 撤销失败 key_id=%s", key_id)
        raise HTTPException(status_code=500, detail="API Key 撤销失败")
    return action_response(message="API Key revoked")



@router.get("/{key_id}", summary="Get API Key Detail")
def get_api_key_detail(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    return success_response({
        "id": api_key.id, "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "description": api_key.description,
        "scopes": api_key.scopes,
    })


@router.put("/{key_id}", summary="Update API Key")
def update_api_key(
    key_id: int, data: ApiKeyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(api_key, field, value)
    api_key.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("API Key 更新失败 key_id=%s", key_id)
        raise HTTPException(status_code=500, detail="API Key 更新失败")
    return action_response(message="API Key updated")


@router.get("/{key_id}/usage", summary="Get API Key Usage")
def get_api_key_usage(
    key_id: int, days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    from sqlalchemy import func
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stats = db.query(
        func.count(ApiKeyUsageLog.id).label("total"),
        func.avg(ApiKeyUsageLog.duration_ms).label("avg_duration"),
    ).filter(
        ApiKeyUsageLog.api_key_id == key_id,
        ApiKeyUsageLog.created_at >= since
    ).first()
    return success_response({
        "key_id": key_id, "period_days": days,
        "total_requests": stats.total or 0,
        "avg_duration_ms": round(stats.avg_duration or 0, 2),
    })


@router.post("/{key_id}/rotate", summary="Rotate API Key")
def rotate_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("api_key:manage")),
):
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    raw_key = generate_api_key()
    api_key.key_hash = hash_api_key(raw_key)
    api_key.key_prefix = raw_key[:10]
    api_key.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("API Key 轮换失败 key_id=%s", key_id)
        raise HTTPException(status_code=500, detail="API Key 轮换失败")
    return success_response({
        "id": api_key.id, "api_key": raw_key,
        "key_prefix": api_key.key_prefix,
    }, message="API Key rotated")
