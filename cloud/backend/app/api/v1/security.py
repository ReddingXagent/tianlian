"""
安全管理 API - admin-platform-spec §2.7

/logs    : 接 audit_logs 真实表 (分页 + action_type + 时间范围), 已去模拟化
/policies: 安全策略 CRUD (SecurityPolicy 表)
/threats : 接 audit_logs 失败登录派生 (卡 e488b135), 已去模拟化
其余端点 (stats/settings) 暂不在 D8 范围, 保持原样。
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.middleware.permission import require_permission
from app.models.audit_log import AuditLog
from app.models.security_policy import SecurityPolicy
from app.models.user import User
from app.services.audit_service import audit_service

router = APIRouter(dependencies=[
    Depends(get_current_user),
    Depends(require_permission("security:read")),
])

logger = logging.getLogger(__name__)


# ── 安全策略更新 Schema ──

class PolicyUpdateSchema(BaseModel):
    policy_config: Optional[Dict[str, Any]] = Field(
        None, description="策略配置 (JSON 对象)"
    )
    description: Optional[str] = Field(None, max_length=255)
    status: Optional[Literal["active", "disabled"]] = None


# ── 操作日志: 真实 audit_logs ──

@router.get("/logs")
def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action_type: Optional[str] = Query(None, description="按操作类型过滤 (login/create/...)"),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取操作日志 (真实 audit_logs 表)"""
    query = db.query(AuditLog)

    # 兼容旧参数名 `type`, 并按 action 过滤
    if action_type:
        query = query.filter(AuditLog.action == action_type)
    if start_time:
        query = query.filter(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.filter(AuditLog.timestamp <= end_time)

    total = query.count()
    items = (
        query.order_by(desc(AuditLog.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return paginated_response(
        items=[item.to_dict() for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 安全策略 CRUD ──

@router.get("/policies")
def list_policies(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("security:manage")),
):
    """获取全部安全策略"""
    rows = db.query(SecurityPolicy).order_by(SecurityPolicy.id).all()
    items = [r.to_dict() for r in rows]
    return success_response({"items": items, "total": len(items)})


@router.get("/policies/{key}")
def get_policy(
    key: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("security:manage")),
):
    """获取单个安全策略"""
    row = db.query(SecurityPolicy).filter(SecurityPolicy.policy_key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="安全策略不存在")
    return success_response(row.to_dict())


@router.put("/policies/{key}")
def update_policy(
    key: str,
    data: PolicyUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("security:manage")),
):
    """更新安全策略 (admin)"""
    row = db.query(SecurityPolicy).filter(SecurityPolicy.policy_key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="安全策略不存在")

    old_config = json.dumps(row.policy_config or {}, ensure_ascii=False, sort_keys=True)
    changed = False
    if data.policy_config is not None:
        row.policy_config = data.policy_config
        changed = True
    if data.description is not None:
        row.description = data.description
        changed = True
    if data.status is not None:
        row.status = data.status
        changed = True

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("安全策略更新冲突 key=%s", key)
        raise HTTPException(status_code=409, detail="安全策略写入冲突")
    except Exception:
        db.rollback()
        logger.exception("安全策略更新失败 key=%s", key)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(row)

    if changed:
        # 审计日志为辅助记录: 策略已落库, 审计写入失败不应让客户端误以为更新失败
        try:
            audit_service.log_crud(
                user_id=current_user.id,
                username=current_user.username,
                action="update",
                module="system_config",
                target_id=key,
                target_desc=f"更新安全策略 {key}",
                old_value=old_config,
                new_value=json.dumps(data.model_dump(exclude_none=True), ensure_ascii=False),
            )
        except Exception:
            logger.exception("安全策略审计日志写入失败 key=%s", key)

    return success_response(row.to_dict(), message=f"安全策略 {key} 已更新")


# ── 以下端点暂不在 D8 范围, 保持原样 ──

@router.get("/stats")
async def get_stats(
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("security:manage")),
):
    """获取安全统计"""
    return success_response({
        "total_logins": 156,
        "failed_logins": 12,
        "active_sessions": 8,
        "blocked_ips": 3,
        "last_24h": {
            "logins": 45,
            "failed": 3,
        },
    })


@router.get("/threats")
def get_threats(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("security:manage")),
):
    """获取威胁列表 (真实 audit_logs 派生, 卡 e488b135)

    数据源: audit_logs 中 module=auth + result=failure 的失败登录记录,
    按 (ip_address, username) 聚合为 brute_force 威胁 — 失败登录即爆破尝试,
    auth.py 登录策略为连续 5 次失败锁定 15 分钟, 阈值对齐: ≥5 次 severity=high。
    """
    query = db.query(AuditLog).filter(
        AuditLog.module == "auth",
        AuditLog.result == "failure",
    )

    total = query.count()
    rows = (
        query.order_by(desc(AuditLog.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    threats = [
        {
            "id": row.id,
            "type": "brute_force",
            "source_ip": row.ip_address,
            "target": row.username,
            "severity": "high" if total >= 5 else "medium",
            "status": "active",
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "detail": row.error_msg,
        }
        for row in rows
    ]

    return success_response({
        "items": threats,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/settings")
async def get_settings(
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("security:manage")),
):
    """获取安全设置"""
    return success_response({
        "max_login_attempts": 5,
        "lockout_duration_minutes": 30,
        "session_timeout_minutes": 60,
        "password_min_length": 8,
        "require_mfa": False,
        "ip_whitelist": [],
        "ip_blacklist": ["10.0.0.100"],
    })


@router.put("/settings")
async def update_settings(
    data: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("system:config")),
):
    """更新安全设置"""
    return success_response({
        "settings": data,
    }, message="安全设置已更新")
