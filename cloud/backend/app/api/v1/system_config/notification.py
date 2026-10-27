"""
系统配置 - 通知配置域
/notification/switches (+defaults),
/notification/templates (CRUD),
/notification/rules (CRUD),
+ 兼容旧接口 /notification-switches*（简化版，直接调用上述实现）
"""
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator, model_validator

# 卡 6259ac0d: 静默时间 HH:MM 严格格式 (与 notification_configs.py 同规则)
_QUIET_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_quiet_time_format(value: Optional[str]) -> Optional[str]:
    if value is not None and not _QUIET_TIME_RE.match(value):
        raise ValueError("时间格式须为 HH:MM (00:00-23:59)")
    return value

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.notification_config import NotificationConfig, NotificationTemplate
from app.core.response import success_response, paginated_response, action_response
from app.services.audit_service import audit_service
from app.middleware.permission import require_permission

from .common import _check_admin_or_permission
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["系统配置"])


# ── 通知配置 Schemas ──

class NotificationSwitches(BaseModel):
    sms_on: bool = Field(False, description="短信开关")
    email_on: bool = Field(False, description="邮件开关")
    app_push_on: bool = Field(False, description="APP推送开关")
    im_b_on: bool = Field(False, description="IM-B开关")
    im_on: bool = Field(False, description="IM开关")


class NotificationSwitchesUpdate(BaseModel):
    sms_on: Optional[bool] = None
    email_on: Optional[bool] = None
    app_push_on: Optional[bool] = None
    im_b_on: Optional[bool] = None
    im_on: Optional[bool] = None


class NotificationTemplateCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    channel: str = Field(..., pattern="^(sms|email|app|im_b|im)$")
    event_type: str = Field(..., min_length=2, max_length=50)
    subject: Optional[str] = None
    content: str
    variables: List[dict] = []
    is_system: bool = False


class NotificationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[List[dict]] = None
    enabled: Optional[bool] = None


class NotificationRuleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    scope_type: str = Field(..., pattern="^(tenant|station|user|device)$")
    scope_id: int
    channels: List[str] = Field(default_factory=list)  # sms, email, app, im_b, im
    receivers: List[str] = []
    receiver_roles: List[str] = []
    trigger_events: List[str] = []
    template_overrides: dict = {}
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None
    timezone: str = "Asia/Shanghai"
    rate_limit_per_hour: int = 10
    rate_limit_per_day: int = 50
    enabled: bool = True
    priority: int = 0

    _check_quiet_start = field_validator("quiet_start")(_validate_quiet_time_format)
    _check_quiet_end = field_validator("quiet_end")(_validate_quiet_time_format)

    @model_validator(mode="after")
    def _quiet_times_paired(self):
        # 卡 6259ac0d: 静默窗口须成对出现, 一个有一无 → 422
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("quiet_start 与 quiet_end 必须成对提供")
        return self


class NotificationRuleUpdate(BaseModel):
    name: Optional[str] = None
    channels: Optional[List[str]] = None
    receivers: Optional[List[str]] = None
    receiver_roles: Optional[List[str]] = None
    trigger_events: Optional[List[str]] = None
    template_overrides: Optional[dict] = None
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None
    timezone: Optional[str] = None
    rate_limit_per_hour: Optional[int] = None
    rate_limit_per_day: Optional[int] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None

    _check_quiet_start = field_validator("quiet_start")(_validate_quiet_time_format)
    _check_quiet_end = field_validator("quiet_end")(_validate_quiet_time_format)

    @model_validator(mode="after")
    def _quiet_times_paired(self):
        # 卡 6259ac0d: 按 payload 实际出现的字段判定成对 (model_fields_set), 未提供不算
        provided = {"quiet_start", "quiet_end"} & self.model_fields_set
        if len(provided) == 1:
            raise ValueError("quiet_start 与 quiet_end 必须成对提供")
        return self


# ── 通知渠道开关 ──

@router.get("/notification/switches")
def get_notification_switches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取通知渠道开关配置"""
    try:
        tenant_id = getattr(current_user, 'tenant_id', None) or 1

        config = db.query(NotificationConfig).filter(
            NotificationConfig.scope_type == "tenant",
            NotificationConfig.scope_id == tenant_id
        ).first()

        if not config:
            return success_response(NotificationSwitches().dict())

        switches = NotificationSwitches(
            sms_on=config.sms_enabled,
            email_on=config.email_enabled,
            app_push_on=config.app_push_enabled,
            im_b_on=config.im_b_enabled,
            im_on=config.im_enabled,
        )
        return success_response(switches.dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_notification_switches 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/notification/switches")
def update_notification_switches(
    data: NotificationSwitchesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("notification:manage")),
):
    """更新通知渠道开关配置"""
    try:
        _check_admin_or_permission(current_user, "system:config")
        tenant_id = getattr(current_user, 'tenant_id', None) or 1

        config = db.query(NotificationConfig).filter(
            NotificationConfig.scope_type == "tenant",
            NotificationConfig.scope_id == tenant_id
        ).first()

        if not config:
            config = NotificationConfig(
                name="租户通知配置",
                scope_type="tenant",
                scope_id=tenant_id,
                sms_enabled=False,
                email_enabled=False,
                app_push_enabled=False,
                im_b_enabled=False,
                im_enabled=False,
                enabled=True,
                priority=0,
            )
            db.add(config)

        old_values = {
            "sms_enabled": config.sms_enabled,
            "email_enabled": config.email_enabled,
            "app_push_enabled": config.app_push_enabled,
            "im_b_enabled": config.im_b_enabled,
            "im_enabled": config.im_enabled,
        }

        if data.sms_on is not None:
            config.sms_enabled = data.sms_on
        if data.email_on is not None:
            config.email_enabled = data.email_on
        if data.app_push_on is not None:
            config.app_push_enabled = data.app_push_on
        if data.im_b_on is not None:
            config.im_b_enabled = data.im_b_on
        if data.im_on is not None:
            config.im_enabled = data.im_on

        db.commit()
        db.refresh(config)

        new_values = {
            "sms_enabled": config.sms_enabled,
            "email_enabled": config.email_enabled,
            "app_push_enabled": config.app_push_enabled,
            "im_b_enabled": config.im_b_enabled,
            "im_enabled": config.im_enabled,
        }

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="update",
            module="system_config",
            target_id=str(config.id),
            target_desc="更新通知渠道开关",
            old_value=str(old_values),
            new_value=str(new_values),
        )

        switches = NotificationSwitches(
            sms_on=config.sms_enabled,
            email_on=config.email_enabled,
            app_push_on=config.app_push_enabled,
            im_b_on=config.im_b_enabled,
            im_on=config.im_enabled,
        )
        return success_response(switches.dict(), message="通知开关已更新")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_notification_switches 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/notification/switches/defaults")
async def get_default_notification_switches():
    """获取默认通知开关配置（无需认证）"""
    try:
        defaults = NotificationSwitches(
            sms_on=False,
            email_on=False,
            app_push_on=False,
            im_b_on=False,
            im_on=False,
        )
        return success_response(defaults.dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_default_notification_switches 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 通知模板 ──

@router.get("/notification/templates")
def list_notification_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel: Optional[str] = None,
    event_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取通知模板列表"""
    try:
        _check_admin_or_permission(current_user, "system:config")

        query = db.query(NotificationTemplate)
        if channel:
            query = query.filter(NotificationTemplate.channel == channel)
        if event_type:
            query = query.filter(NotificationTemplate.event_type == event_type)
        if enabled is not None:
            query = query.filter(NotificationTemplate.enabled == enabled)

        total = query.count()
        items = query.order_by(NotificationTemplate.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return paginated_response(
            items=[{
                "id": t.id,
                "name": t.name,
                "code": t.code,
                "channel": t.channel,
                "event_type": t.event_type,
                "subject": t.subject,
                "content": t.content,
                "variables": t.variables or [],
                "is_system": t.is_system,
                "enabled": t.enabled,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            } for t in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_notification_templates 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/notification/templates/{template_id}")
def get_notification_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取通知模板详情"""
    try:
        _check_admin_or_permission(current_user, "system:config")
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        return success_response({
            "id": template.id,
            "name": template.name,
            "code": template.code,
            "channel": template.channel,
            "event_type": template.event_type,
            "subject": template.subject,
            "content": template.content,
            "variables": template.variables or [],
            "is_system": template.is_system,
            "enabled": template.enabled,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_notification_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/notification/templates", status_code=201)
def create_notification_template(
    data: NotificationTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("notification:manage")),
):
    """创建通知模板"""
    try:
        _check_admin_or_permission(current_user, "system:config")

        existing = db.query(NotificationTemplate).filter(NotificationTemplate.code == data.code).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"模板代码 {data.code} 已存在")

        template = NotificationTemplate(
            name=data.name,
            code=data.code,
            channel=data.channel,
            event_type=data.event_type,
            subject=data.subject,
            content=data.content,
            variables=data.variables,
            is_system=data.is_system,
            enabled=True,
        )
        db.add(template)
        db.commit()
        db.refresh(template)

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="create",
            module="system_config",
            target_id=str(template.id),
            target_desc=f"创建通知模板 {template.name}",
        )

        return success_response({
            "id": template.id,
            "name": template.name,
            "code": template.code,
        }, message=f"模板 {template.name} 创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_notification_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/notification/templates/{template_id}")
def update_notification_template(
    template_id: int,
    data: NotificationTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("notification:manage")),
):
    """更新通知模板"""
    try:
        _check_admin_or_permission(current_user, "system:config")
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        if template.is_system:
            raise HTTPException(status_code=400, detail="系统内置模板不可修改")

        old_content = template.content

        if data.name is not None:
            template.name = data.name
        if data.subject is not None:
            template.subject = data.subject
        if data.content is not None:
            template.content = data.content
        if data.variables is not None:
            template.variables = data.variables
        if data.enabled is not None:
            template.enabled = data.enabled

        db.commit()
        db.refresh(template)

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="update",
            module="system_config",
            target_id=str(template_id),
            target_desc=f"更新通知模板 {template.name}",
            old_value=old_content,
            new_value=template.content,
        )

        return success_response({
            "id": template.id,
            "name": template.name,
        }, message=f"模板 {template.name} 更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_notification_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/notification/templates/{template_id}")
def delete_notification_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("notification:manage")),
):
    """删除通知模板"""
    try:
        _check_admin_or_permission(current_user, "system:config")
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        if template.is_system:
            raise HTTPException(status_code=400, detail="系统内置模板不可删除")

        name = template.name
        db.delete(template)
        db.commit()

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="delete",
            module="system_config",
            target_id=str(template_id),
            target_desc=f"删除通知模板 {name}",
        )

        return action_response(success=True, message=f"模板 {name} 已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_notification_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 通知规则 ──

@router.get("/notification/rules")
def list_notification_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    scope_type: Optional[str] = None,
    scope_id: Optional[int] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取通知规则列表"""
    try:
        _check_admin_or_permission(current_user, "system:config")

        query = db.query(NotificationConfig)
        if scope_type:
            query = query.filter(NotificationConfig.scope_type == scope_type)
        if scope_id:
            query = query.filter(NotificationConfig.scope_id == scope_id)
        if enabled is not None:
            query = query.filter(NotificationConfig.enabled == enabled)

        total = query.count()
        items = query.order_by(NotificationConfig.priority.desc(), NotificationConfig.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return paginated_response(
            items=[{
                "id": c.id,
                "name": c.name,
                "scope_type": c.scope_type,
                "scope_id": c.scope_id,
                "sms_enabled": c.sms_enabled,
                "email_enabled": c.email_enabled,
                "app_push_enabled": c.app_push_enabled,
                "im_b_enabled": c.im_b_enabled,
                "im_enabled": c.im_enabled,
                "receivers": c.receivers or [],
                "receiver_roles": c.receiver_roles or [],
                "trigger_events": c.trigger_events or [],
                "template_overrides": c.template_overrides or {},
                "quiet_start": c.quiet_start,
                "quiet_end": c.quiet_end,
                "timezone": c.timezone,
                "rate_limit_per_hour": c.rate_limit_per_hour,
                "rate_limit_per_day": c.rate_limit_per_day,
                "enabled": c.enabled,
                "priority": c.priority,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            } for c in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_notification_rules 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/notification/rules", status_code=201)
def create_notification_rule(
    data: NotificationRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建通知规则"""
    try:
        _check_admin_or_permission(current_user, "system:config")

        config = NotificationConfig(
            name=data.name,
            scope_type=data.scope_type,
            scope_id=data.scope_id,
            sms_enabled="sms" in data.channels,
            email_enabled="email" in data.channels,
            app_push_enabled="app" in data.channels,
            im_b_enabled="im_b" in data.channels,
            im_enabled="im" in data.channels,
            receivers=data.receivers,
            receiver_roles=data.receiver_roles,
            trigger_events=data.trigger_events,
            template_overrides=data.template_overrides,
            quiet_start=data.quiet_start,
            quiet_end=data.quiet_end,
            timezone=data.timezone,
            rate_limit_per_hour=data.rate_limit_per_hour,
            rate_limit_per_day=data.rate_limit_per_day,
            enabled=data.enabled,
            priority=data.priority,
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="create",
            module="system_config",
            target_id=str(config.id),
            target_desc=f"创建通知规则 {config.name}",
        )

        return success_response({"id": config.id, "name": config.name}, message=f"通知规则 {config.name} 创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_notification_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/notification/rules/{rule_id}")
def update_notification_rule(
    rule_id: int,
    data: NotificationRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新通知规则"""
    try:
        _check_admin_or_permission(current_user, "system:config")
        config = db.query(NotificationConfig).filter(NotificationConfig.id == rule_id).first()
        if not config:
            raise HTTPException(status_code=404, detail="规则不存在")

        if data.name is not None:
            config.name = data.name
        if data.channels is not None:
            config.sms_enabled = "sms" in data.channels
            config.email_enabled = "email" in data.channels
            config.app_push_enabled = "app" in data.channels
            config.im_b_enabled = "im_b" in data.channels
            config.im_enabled = "im" in data.channels
        if data.receivers is not None:
            config.receivers = data.receivers
        if data.receiver_roles is not None:
            config.receiver_roles = data.receiver_roles
        if data.trigger_events is not None:
            config.trigger_events = data.trigger_events
        if data.template_overrides is not None:
            config.template_overrides = data.template_overrides
        if data.quiet_start is not None:
            config.quiet_start = data.quiet_start
        if data.quiet_end is not None:
            config.quiet_end = data.quiet_end
        if data.timezone is not None:
            config.timezone = data.timezone
        if data.rate_limit_per_hour is not None:
            config.rate_limit_per_hour = data.rate_limit_per_hour
        if data.rate_limit_per_day is not None:
            config.rate_limit_per_day = data.rate_limit_per_day
        if data.enabled is not None:
            config.enabled = data.enabled
        if data.priority is not None:
            config.priority = data.priority

        db.commit()
        db.refresh(config)

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="update",
            module="system_config",
            target_id=str(rule_id),
            target_desc=f"更新通知规则 {config.name}",
        )

        return success_response({"id": config.id, "name": config.name}, message=f"通知规则 {config.name} 更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_notification_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/notification/rules/{rule_id}")
def delete_notification_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除通知规则"""
    try:
        _check_admin_or_permission(current_user, "system:config")
        config = db.query(NotificationConfig).filter(NotificationConfig.id == rule_id).first()
        if not config:
            raise HTTPException(status_code=404, detail="规则不存在")

        name = config.name
        db.delete(config)
        db.commit()

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="delete",
            module="system_config",
            target_id=str(rule_id),
            target_desc=f"删除通知规则 {name}",
        )

        return action_response(success=True, message=f"通知规则 {name} 已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_notification_rule 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ── 兼容旧接口（简化版通知开关）──

@router.get("/notification-switches")
def get_notification_switches_simple(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """简化版：获取通知开关（兼容旧接口）"""
    try:
        return get_notification_switches(db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_notification_switches_simple 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/notification-switches")
def update_notification_switches_simple(
    data: NotificationSwitchesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """简化版：更新通知开关（兼容旧接口）"""
    try:
        return update_notification_switches(data, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_notification_switches_simple 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/notification-switches/defaults")
async def get_default_notification_switches_simple():
    """简化版：获取默认通知开关（兼容旧接口）"""
    try:
        return await get_default_notification_switches()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_default_notification_switches_simple 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
