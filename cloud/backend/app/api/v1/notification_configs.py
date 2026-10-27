"""
通知配置 API - 管理 SMS/邮件/APP 通知渠道开关
支持租户级、站点级、用户级配置
"""
from fastapi import APIRouter, HTTPException, Depends, Query
import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# 卡 6259ac0d: 静默时间 HH:MM 严格格式, 坏值在入口 422 拒绝
_QUIET_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_quiet_time_format(value: Optional[str]) -> Optional[str]:
    if value is not None and not _QUIET_TIME_RE.match(value):
        raise ValueError("时间格式须为 HH:MM (00:00-23:59)")
    return value
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.notification_config import NotificationConfig, NotificationTemplate, NotificationLog
from app.models.station import Station
from app.models.device import Device
from app.api.deps import (
    is_platform_admin, assert_station_team_access, assert_device_team_access,
)
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response
from sqlalchemy import or_, and_
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("notification:manage"))])


def _team_station_ids(db: Session, user):
    """本 team 站点 id 列表；admin/super_admin 返回 None（不过滤）；无站点团队返回 [0] 占位。
    任务卡 1c19b59a team scoping。"""
    if is_platform_admin(user):
        return None
    rows = db.query(Station.id).filter(Station.team_id == user.team_id).all()
    return [r[0] for r in rows] or [0]


def _team_device_ids(db: Session, user):
    """本 team 设备 id 列表；admin/super_admin 返回 None（不过滤）；无设备返回 [0] 占位。

    Device 无 team_id 列，归属经 device.station_id→station.team_id 间接判定（同
    assert_device_team_access）。任务卡 5b22d9f7 —— 修 list_configs 对 device scope
    漏过滤：旧实现仅过滤 station scope，device scope 全放行致跨 team device config 可见。
    """
    if is_platform_admin(user):
        return None
    rows = (
        db.query(Device.id)
        .join(Station, Device.station_id == Station.id)
        .filter(Station.team_id == user.team_id)
        .all()
    )
    return [r[0] for r in rows] or [0]


def _assert_config_scope_access(db, config, user):
    """NotificationConfig 按 scope_type 校验 team 归属：station/device 经对应链路 →
    跨团队 404；tenant/user/None 平台级或弱归属，不强制 404（依赖 RBAC 收紧，NOTE）。
    任务卡 1c19b59a。

    team_id 显式隔离 (卡 cf614348): team_id 非空时硬归属他 team → 404; NULL 走原逻辑。
    """
    if is_platform_admin(user):
        return
    if config.team_id is not None and user.team_id != config.team_id:
        raise HTTPException(404, "配置不存在")
    st = config.scope_type
    sid = config.scope_id
    if st == "station" and sid is not None:
        assert_station_team_access(db, sid, user)
    elif st == "device" and sid is not None:
        assert_device_team_access(db, sid, user)


def _assert_create_scope_access(db, scope_type, scope_id, user):
    """创建前的 scope 归属校验（与 _assert_config_scope_access 同语义）。"""
    if is_platform_admin(user):
        return
    if scope_type == "station" and scope_id is not None:
        assert_station_team_access(db, scope_id, user)
    elif scope_type == "device" and scope_id is not None:
        assert_device_team_access(db, scope_id, user)


# ─── Pydantic Schemas ───

class NotificationConfigCreate(BaseModel):
    name: str = Field(..., description="配置名称")
    scope_type: str = Field("tenant", pattern="^(tenant|station|user|device)$", description="作用域类型: tenant/station/user/device")
    scope_id: Optional[int] = Field(None, description="作用域ID")
    sms_enabled: bool = Field(False, description="短信启用")
    email_enabled: bool = Field(False, description="邮件启用")
    app_push_enabled: bool = Field(False, description="APP推送启用")
    im_b_enabled: bool = Field(False, description="IM-B启用")
    im_enabled: bool = Field(False, description="IM启用")
    receivers: List[str] = Field(default_factory=list, description="固定接收人列表")
    receiver_roles: List[str] = Field(default_factory=list, description="接收角色")
    trigger_events: List[str] = Field(default_factory=list, description="触发事件")
    quiet_start: Optional[str] = Field(None, description="静默开始时间 HH:MM")
    quiet_end: Optional[str] = Field(None, description="静默结束时间 HH:MM")
    timezone: str = Field("Asia/Shanghai", max_length=50, description="时区")
    rate_limit_per_hour: int = Field(10, description="每小时限制")
    rate_limit_per_day: int = Field(50, description="每天限制")
    enabled: bool = Field(True, description="是否启用")
    priority: int = Field(0, description="优先级")

    _check_quiet_start = field_validator("quiet_start")(_validate_quiet_time_format)
    _check_quiet_end = field_validator("quiet_end")(_validate_quiet_time_format)

    @model_validator(mode="after")
    def _quiet_times_paired(self):
        # 卡 6259ac0d: 静默窗口须成对出现, 一个有一无 → 422
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("quiet_start 与 quiet_end 必须成对提供")
        return self


class NotificationConfigUpdate(BaseModel):
    name: Optional[str] = None
    sms_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    app_push_enabled: Optional[bool] = None
    im_b_enabled: Optional[bool] = None
    im_enabled: Optional[bool] = None
    receivers: Optional[List[str]] = None
    receiver_roles: Optional[List[str]] = None
    trigger_events: Optional[List[str]] = None
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


class TemplateCreate(BaseModel):
    name: str = Field(..., description="模板名称")
    code: str = Field(..., description="模板代码")
    channel: str = Field(..., pattern="^(sms|email|app|im_b|im)$", description="渠道: sms/email/app/im_b/im")
    event_type: str = Field(..., max_length=50, description="事件类型")
    subject: Optional[str] = Field(None, description="主题")
    content: str = Field(..., description="模板内容，支持 {variable} 占位符")
    variables: List[dict] = Field(default_factory=list, description="变量列表")
    is_system: bool = Field(False, description="是否系统内置")
    enabled: bool = Field(True, description="是否启用")


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    event_type: Optional[str] = None
    subject: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[List[dict]] = None
    enabled: Optional[bool] = None


# ─── Config CRUD ───

@router.get("")
def list_configs(
    scope_type: Optional[str] = None,
    scope_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取通知配置列表，支持按作用域筛选"""
    try:
        query = db.query(NotificationConfig)
        # team scoping（任务卡 1c19b59a / 5b22d9f7）：非 admin 仅本 team 的 station/device
        # 配置可见；tenant/user 等平台级或弱归属 scope 保留。语义与 _assert_config_scope_access
        # 单资源一致：仅 station/device 且 scope_id 非空才校验 team，scope_id 为空的弱归属放行。
        sids = _team_station_ids(db, current_user)
        dids = _team_device_ids(db, current_user)
        if sids is not None:  # 非 admin（sids/dids 同时非 None）
            query = query.filter(
                or_(
                    and_(
                        NotificationConfig.scope_type == "station",
                        or_(NotificationConfig.scope_id.is_(None), NotificationConfig.scope_id.in_(sids)),
                    ),
                    and_(
                        NotificationConfig.scope_type == "device",
                        or_(NotificationConfig.scope_id.is_(None), NotificationConfig.scope_id.in_(dids)),
                    ),
                    NotificationConfig.scope_type.notin_(["station", "device"]),
                )
            )
            # team_id 显式隔离 (卡 cf614348): 归属他 team 的配置 (team_id 非空) 不可见;
            # team_id 为 NULL 的平台共享/弱归属配置沿用原 scope 过滤。
            query = query.filter(
                or_(
                    NotificationConfig.team_id.is_(None),
                    NotificationConfig.team_id == current_user.team_id,
                )
            )
        if scope_type:
            query = query.filter(NotificationConfig.scope_type == scope_type)
        if scope_id is not None:
            query = query.filter(NotificationConfig.scope_id == scope_id)
        configs = query.order_by(NotificationConfig.priority.desc()).all()
        return success_response([c.to_dict() for c in configs])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_configs 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("")
def create_config(data: NotificationConfigCreate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """创建通知配置"""
    # team scoping（任务卡 1c19b59a）：scope 归属校验前置，跨团队建 station/device 配置 → 404。
    try:
        _assert_create_scope_access(db, data.scope_type, data.scope_id, current_user)
        config = NotificationConfig(
            name=data.name,
            scope_type=data.scope_type,
            scope_id=data.scope_id,
            sms_enabled=data.sms_enabled,
            email_enabled=data.email_enabled,
            app_push_enabled=data.app_push_enabled,
            im_b_enabled=data.im_b_enabled,
            im_enabled=data.im_enabled,
            receivers=data.receivers,
            receiver_roles=data.receiver_roles,
            trigger_events=data.trigger_events,
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
        audit_service.log_crud(current_user.id, current_user.username, "create", "notification_configs", str(config.id))
        return success_response(config.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{config_id}")
def update_config(config_id: int, data: NotificationConfigUpdate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """更新通知配置"""
    try:
        config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            raise HTTPException(404, "配置不存在")
        # team scoping（任务卡 1c19b59a）：按 scope_type 校验当前归属，跨团队 → 404。
        _assert_config_scope_access(db, config, current_user)

        for field, value in data.dict(exclude_unset=True).items():
            setattr(config, field, value)

        db.commit()
        db.refresh(config)
        audit_service.log_crud(current_user.id, current_user.username, "update", "notification_configs", str(config_id))
        return success_response(config.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/{config_id}")
def delete_config(config_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """删除通知配置"""
    try:
        config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            raise HTTPException(404, "配置不存在")
        # team scoping（任务卡 1c19b59a）：按 scope_type 校验归属，跨团队 → 404。
        _assert_config_scope_access(db, config, current_user)
        db.delete(config)
        db.commit()
        audit_service.log_crud(current_user.id, current_user.username, "delete", "notification_configs", str(config_id))
        return success_response(None, message="配置已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/{config_id}/toggle")
def toggle_config(config_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """切换配置启用状态"""
    try:
        config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            raise HTTPException(404, "配置不存在")
        # team scoping（任务卡 1c19b59a）：按 scope_type 校验归属，跨团队 → 404。
        _assert_config_scope_access(db, config, current_user)
        config.enabled = not config.enabled
        db.commit()
        return success_response({"enabled": config.enabled}, message="状态已切换")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("toggle_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── Template CRUD ───

@router.get("/templates")
def list_templates(
    channel: Optional[str] = None,
    event_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取通知模板列表"""
    try:
        query = db.query(NotificationTemplate)
        if channel:
            query = query.filter(NotificationTemplate.channel == channel)
        if event_type:
            query = query.filter(NotificationTemplate.event_type == event_type)
        templates = query.all()
        return success_response([t.to_dict() for t in templates])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_templates 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/templates/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db)):
    """获取单个模板"""
    try:
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        if not template:
            raise HTTPException(404, "模板不存在")
        return success_response(template.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/templates")
def create_template(data: TemplateCreate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """创建通知模板"""
    try:
        existing = db.query(NotificationTemplate).filter(NotificationTemplate.code == data.code).first()
        if existing:
            raise HTTPException(400, f"模板代码 {data.code} 已存在")

        template = NotificationTemplate(
            name=data.name,
            code=data.code,
            channel=data.channel,
            event_type=data.event_type,
            subject=data.subject,
            content=data.content,
            variables=data.variables,
            is_system=data.is_system,
            enabled=data.enabled,
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        audit_service.log_crud(current_user.id, current_user.username, "create", "notification_templates", str(template.id))
        return success_response(template.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/templates/{template_id}")
def update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """更新通知模板"""
    try:
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        if not template:
            raise HTTPException(404, "模板不存在")

        for field, value in data.dict(exclude_unset=True).items():
            setattr(template, field, value)

        db.commit()
        db.refresh(template)
        audit_service.log_crud(current_user.id, current_user.username, "update", "notification_templates", str(template.id))
        return success_response(template.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """删除通知模板"""
    try:
        template = db.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
        if not template:
            raise HTTPException(404, "模板不存在")
        db.delete(template)
        db.commit()
        audit_service.log_crud(current_user.id, current_user.username, "delete", "notification_templates", str(template_id))
        return success_response(None, message="模板已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── Log Query ───

@router.get("/logs")
def list_logs(
    event_type: Optional[str] = None,
    channel: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取通知发送日志"""
    try:
        query = db.query(NotificationLog)
        if event_type:
            query = query.filter(NotificationLog.event_type == event_type)
        if channel:
            query = query.filter(NotificationLog.channel == channel)
        if status:
            query = query.filter(NotificationLog.status == status)

        total = query.count()
        logs = query.order_by(NotificationLog.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        return paginated_response(
            items=[log.to_dict() for log in logs],
            total=total,
            page=page,
            page_size=page_size
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_logs 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 单条配置查询 ───
# 路由顺序注意 [5627c6cb]：GET /{config_id} 是单段动态路由，必须注册在所有单段静态
# 路由（GET /templates、GET /logs）之后。FastAPI 按注册顺序匹配，若置于此二者之前，
# /templates、/logs 会被当成 config_id 走 int 解析 → 422，端点不可达。故挪到文件末尾。
# （PUT/DELETE /{config_id} method 不同、/{config_id}/toggle 与 /templates/{id} 为两段
# 路径，均不与单段静态冲突，无需移动。）
@router.get("/{config_id}")
def get_config(config_id: int, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """获取单个通知配置"""
    try:
        config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            raise HTTPException(404, "配置不存在")
        # team scoping（任务卡 1c19b59a）：按 scope_type 校验归属，跨团队 → 404。
        _assert_config_scope_access(db, config, current_user)
        return success_response(config.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_config 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
