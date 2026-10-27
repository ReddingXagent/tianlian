"""
通知规则配置 API
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import Literal, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.notification_rule import NotificationRule
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.response import success_response, action_response

router = APIRouter(dependencies=[Depends(require_write_permission("notification:manage"))])

logger = logging.getLogger(__name__)


class RuleCreate(BaseModel):
    name: str
    level: Literal["critical", "warning", "info", "daily"]
    channels: List[str] = []
    receivers: List[str] = []
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[Literal["critical", "warning", "info", "daily"]] = None
    channels: Optional[List[str]] = None
    receivers: Optional[List[str]] = None
    enabled: Optional[bool] = None


@router.get("")
def list_rules(db: Session = Depends(get_db)):
    """获取所有通知规则"""
    try:
        rules = db.query(NotificationRule).all()
        return success_response([r.to_dict() for r in rules])
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_rules 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    """获取单条通知规则"""
    try:
        rule = db.query(NotificationRule).filter(NotificationRule.id == rule_id).first()
        if not rule:
            raise HTTPException(404, "规则不存在")
        return success_response(rule.to_dict())
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_rule 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.post("")
def create_rule(data: RuleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建通知规则"""
    try:
        rule = NotificationRule(
            name=data.name,
            level=data.level,
            channels=data.channels,
            receivers=data.receivers,
            enabled=data.enabled,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        audit_service.log_crud(user.id, user.username, "create", "notification_rules", str(rule.id), f"rule:{rule.name}")
        return success_response(rule.to_dict())
    except HTTPException:
        raise
    except Exception:
        logger.exception("create_rule 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: RuleUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新通知规则"""
    try:
        rule = db.query(NotificationRule).filter(NotificationRule.id == rule_id).first()
        if not rule:
            raise HTTPException(404, "规则不存在")

        if data.name is not None: rule.name = data.name
        if data.level is not None: rule.level = data.level
        if data.channels is not None: rule.channels = data.channels
        if data.receivers is not None: rule.receivers = data.receivers
        if data.enabled is not None: rule.enabled = data.enabled

        db.commit()
        db.refresh(rule)
        audit_service.log_crud(user.id, user.username, "update", "notification_rules", str(rule_id), f"rule:{rule.name}")
        return success_response(rule.to_dict())
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_rule 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除通知规则"""
    try:
        rule = db.query(NotificationRule).filter(NotificationRule.id == rule_id).first()
        if not rule:
            raise HTTPException(404, "规则不存在")
        db.delete(rule)
        db.commit()
        audit_service.log_crud(user.id, user.username, "delete", "notification_rules", str(rule_id))
        return action_response(success=True, message=f"规则 {rule_id} 已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_rule 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.put("/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    """切换规则启用状态"""
    try:
        rule = db.query(NotificationRule).filter(NotificationRule.id == rule_id).first()
        if not rule:
            raise HTTPException(404, "规则不存在")
        rule.enabled = not rule.enabled
        db.commit()
        return success_response({'enabled': rule.enabled}, message="状态已切换")
    except HTTPException:
        raise
    except Exception:
        logger.exception("toggle_rule 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
