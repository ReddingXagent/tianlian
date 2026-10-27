"""
消息通知中心 API

端点分组：
- POST /send                         发送通知（原有，骨架实现）
- GET/POST/PUT/DELETE /templates     消息模板 CRUD
- GET /messages + DELETE /messages/{id}   消息记录查询/删除
- GET /stats                         发送统计聚合

设计说明（方案A：复用现有模型 + 字段适配层）：
前端 MessageCenter(index.tsx) 消费的契约字段（template_type/title/channels 等）
与现有 `NotificationTemplate`/`NotificationLog`（为告警通知配置设计，字段为
event_type/subject/channel 单值等）语义不同。本模块通过 adapter 函数做字段映射，
既满足前端契约，又不改动既有 `/notification-configs` 端点、不新增数据表（零 schema 变更）。
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin
from app.core.database import get_db
from app.core.response import success_response, paginated_response, error_response
from app.models.notification import Notification
from app.models.notification_config import NotificationTemplate, NotificationLog
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.notification_service import send_notification
from app.tasks.tz_utils import today_in_biz_tz
from app.middleware.permission import require_write_permission
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("notification:manage"))])

# 站内消息中心收件箱 — 用户自服务 (读自己消息/标记已读), 仅认证不要求 notification:manage,
# 故独立成 router, 不继承上面的路由级写权限守卫。全局 enforce_auth 已强制认证。
inbox_router = APIRouter()


# ════════════════════════════════════════════════════════
#  既有：发送通知
# ════════════════════════════════════════════════════════

class NotificationSendRequest(BaseModel):
    user_id: str = Field(..., description="接收用户ID")
    title: str = Field(..., description="通知标题")
    content: str = Field(..., description="通知内容")
    channel: str = Field("app", max_length=20, description="发送渠道: sms/email/app")


class NotificationSendResponse(BaseModel):
    status: str
    channel: str
    user_id: str
    title: str
    sent_at: str


@router.post("/send")
def send_notification_endpoint(
    req: NotificationSendRequest,
    db: Session = Depends(get_db),
):
    """发送通知"""
    try:
        if req.channel not in ("sms", "email", "app", "app_push"):
            return error_response(400, f"不支持的渠道: {req.channel}")

        result = send_notification(
            user_id=req.user_id,
            title=req.title,
            content=req.content,
            channel=req.channel,
            db=db,
        )

        if result["status"] != "ok":
            err_detail = result.get("error", "通知发送失败")
            return error_response(500, f"通知发送失败: {err_detail}")

        # 站内渠道 (app / app_push): 在通知日志之外, 同时落一条 Notification 收件箱记录。
        # 日志归日志 (notification_logs), 消息归消息 (notifications), 两者并存。
        if req.channel in ("app", "app_push"):
            recipient_team_id = None
            if req.user_id.isdigit():
                recipient = db.query(User).filter(User.id == int(req.user_id)).first()
                if recipient is not None:
                    recipient_team_id = recipient.team_id
            inbox_msg = Notification(
                title=req.title,
                content=req.content,
                type="system",
                sender="system",
                recipient_type="user",
                recipient_id=req.user_id,
                channel="app_push",
                status="sent",
                sent_at=datetime.now(timezone.utc),
                team_id=recipient_team_id,
            )
            db.add(inbox_msg)
            db.commit()

        return success_response(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("send_notification_endpoint 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ════════════════════════════════════════════════════════
#  字段适配层：模型 <-> 前端契约
# ════════════════════════════════════════════════════════

def _gen_template_code(name: str) -> str:
    """前端不发 code，后端自动生成唯一模板代码（NotificationTemplate.code 必填且唯一）"""
    slug = "".join(c.lower() if c.isalnum() else "_" for c in (name or ""))[:24].strip("_") or "tpl"
    return f"mc_{slug}_{uuid.uuid4().hex[:8]}"


def _template_to_dict(t: NotificationTemplate) -> dict:
    """NotificationTemplate -> 前端 NotificationTemplate 契约字段

    映射: template_type<-event_type, title<-subject, channels<-[channel]
    """
    return {
        "id": t.id,
        "name": t.name,
        "template_type": t.event_type,
        "title": t.subject or t.name,
        "content": t.content,
        "channels": [t.channel] if t.channel else [],
        "variables": t.variables or [],
        "enabled": bool(t.enabled),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _log_to_dict(log: NotificationLog, template_name: Optional[str] = None) -> dict:
    """NotificationLog -> 前端 NotificationMessage 契约字段

    映射: title<-subject, receivers<-[receiver_id], result_message<-error_message,
          sender 固定 'system'（NotificationLog 无发送人字段，复用模型下的已知限制）
    """
    return {
        "id": log.id,
        "template_id": log.template_id,
        "template_name": template_name,
        "title": log.subject or "",
        "content": log.content,
        "channel": log.channel,
        "receivers": [log.receiver_id] if log.receiver_id else [],
        "sender": "system",
        "status": log.status,
        "result_message": log.error_message,
        "sent_at": log.sent_at.isoformat() if log.sent_at else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ════════════════════════════════════════════════════════
#  模板 CRUD
# ════════════════════════════════════════════════════════

class TemplateCreateRequest(BaseModel):
    name: str = Field(..., description="模板名称")
    template_type: str = Field("system", description="模板类型: system/charging/maintenance/marketing/custom")
    title: Optional[str] = Field(None, description="标题模板")
    content: str = Field(..., description="内容模板，支持 {variable} 占位符")
    channels: List[str] = Field(default_factory=list, description="默认渠道")
    variables: Optional[list] = Field(default_factory=list, description="变量定义列表")
    enabled: bool = Field(True, description="是否启用")


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    template_type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    channels: Optional[List[str]] = None
    variables: Optional[list] = None
    enabled: Optional[bool] = None


@router.get("/templates")
def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取消息模板列表（分页）"""
    try:
        query = db.query(NotificationTemplate)
        total = query.count()
        templates = (
            query.order_by(NotificationTemplate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return paginated_response(
            [_template_to_dict(t) for t in templates], total, page, page_size
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_templates 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.post("/templates")
def create_template(data: TemplateCreateRequest, db: Session = Depends(get_db),
    user: User = Depends(get_current_user)):
    """创建消息模板"""
    try:
        template = NotificationTemplate(
            name=data.name,
            code=_gen_template_code(data.name),
            channel=data.channels[0] if data.channels else "app_push",
            event_type=data.template_type,
            subject=data.title,
            content=data.content,
            variables=data.variables or [],
            is_system=False,
            enabled=data.enabled,
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        audit_service.log_crud(user.id, user.username, "create", "message_templates", str(template.id))
        return success_response(_template_to_dict(template), message="模板创建成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/templates/{template_id}")
def update_template(
    template_id: int,
    data: TemplateUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新消息模板"""
    try:
        template = (
            db.query(NotificationTemplate)
            .filter(NotificationTemplate.id == template_id)
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        payload = data.dict(exclude_unset=True)
        if "name" in payload:
            template.name = payload["name"]
        if "template_type" in payload:
            template.event_type = payload["template_type"]
        if "title" in payload:
            template.subject = payload["title"]
        if "content" in payload:
            template.content = payload["content"]
        if "channels" in payload:
            template.channel = payload["channels"][0] if payload["channels"] else template.channel
        if "variables" in payload:
            template.variables = payload["variables"]
        if "enabled" in payload:
            template.enabled = payload["enabled"]

        db.commit()
        db.refresh(template)
        audit_service.log_crud(user.id, user.username, "update", "message_templates", str(template_id))
        return success_response(_template_to_dict(template), message="模板更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除消息模板"""
    try:
        template = (
            db.query(NotificationTemplate)
            .filter(NotificationTemplate.id == template_id)
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        db.delete(template)
        db.commit()
        audit_service.log_crud(user.id, user.username, "delete", "message_templates", str(template_id))
        return success_response(None, message="模板已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_template 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ════════════════════════════════════════════════════════
#  消息记录
# ════════════════════════════════════════════════════════

@router.get("/messages")
def list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    channel: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取消息记录列表（分页 + status/channel 筛选）"""
    try:
        query = db.query(NotificationLog)
        if status:
            query = query.filter(NotificationLog.status == status)
        if channel:
            query = query.filter(NotificationLog.channel == channel)

        total = query.count()
        logs = (
            query.order_by(NotificationLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # 批量关联模板名，避免 N+1
        template_ids = {log.template_id for log in logs if log.template_id}
        name_map: dict = {}
        if template_ids:
            tpls = (
                db.query(NotificationTemplate)
                .filter(NotificationTemplate.id.in_(template_ids))
                .all()
            )
            name_map = {t.id: t.name for t in tpls}

        items = [_log_to_dict(log, name_map.get(log.template_id)) for log in logs]
        return paginated_response(items, total, page, page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_messages 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.delete("/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除单条消息记录"""
    try:
        log = (
            db.query(NotificationLog)
            .filter(NotificationLog.id == message_id)
            .first()
        )
        if not log:
            raise HTTPException(status_code=404, detail="消息记录不存在")
        db.delete(log)
        db.commit()
        audit_service.log_crud(user.id, user.username, "delete", "message_records", str(message_id))
        return success_response(None, message="消息记录已删除")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_message 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ════════════════════════════════════════════════════════
#  发送统计
# ════════════════════════════════════════════════════════

@router.get("/stats")
def notification_stats(db: Session = Depends(get_db)):
    """消息中心发送统计聚合

    对齐前端 MessageStats 展示字段：
    total_templates / total_messages / sent_today / failed_count / channel_distribution
    """
    try:
        total_templates = db.query(NotificationTemplate).count()
        log_q = db.query(NotificationLog)
        total_messages = log_q.count()
        failed_count = log_q.filter(NotificationLog.status == "failed").count()

        # created_at 由 server_default=func.now() 写入（SQLite CURRENT_TIMESTAMP 为 UTC）。
        # “今日”基准改业务时区自然日 (卡 ba16a9ff, 同 alarms.py:483 模式):
        # func.date(UTC时间戳)=UTC日 与业务今天比较, 已知局限: 上海 00:00-08:00
        # 创建的记录 func.date=业务昨天, 该窗口漏计; 彻底修复需 DB 层时区转换 (范围外)。
        today = today_in_biz_tz().isoformat()
        sent_today = log_q.filter(func.date(NotificationLog.created_at) == today).count()

        # 渠道分布（按 channel 分组计数）
        channel_rows = (
            db.query(NotificationLog.channel, func.count(NotificationLog.id))
            .group_by(NotificationLog.channel)
            .all()
        )
        channel_distribution = {ch: cnt for ch, cnt in channel_rows if ch}

        return success_response({
            "total_templates": total_templates,
            "total_messages": total_messages,
            "sent_today": sent_today,
            "failed_count": failed_count,
            "channel_distribution": channel_distribution,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("notification_stats 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ════════════════════════════════════════════════════════
#  站内消息中心 — 收件箱 (admin-platform-spec §2.8)
#  用户自服务: 读自己收件箱 / 未读数 / 标记已读。仅认证, 不要求 notification:manage。
# ════════════════════════════════════════════════════════

def _role_value(user: User) -> str:
    """统一取用户角色字符串 (UserRole 枚举或裸字符串)。"""
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _inbox_query(db: Session, user: User):
    """当前用户收件箱基础查询: 命中个人 + 角色广播, 再叠 team_id 隔离。

    隔离契约对齐 app/api/deps.py (team-isolation-contract):
    - admin/super_admin (is_platform_admin) 平台级全可见, 不加 team 过滤;
    - 团队级用户只看本团队消息; 无团队用户只看 team_id IS NULL 的消息。
      严格「双方 team_id 必须相等」(NULL 仅匹配 NULL), 不做 NULL 平台广播放行,
      与 deps._team_denied 同源, 避免越权模糊地带。
    """
    uid = str(user.id)
    role = _role_value(user)
    q = db.query(Notification).filter(
        or_(
            and_(
                Notification.recipient_type == "user",
                Notification.recipient_id == uid,
            ),
            and_(
                Notification.recipient_type == "role",
                Notification.recipient_id == role,
            ),
        )
    )
    if not is_platform_admin(user):
        if user.team_id is None:
            q = q.filter(Notification.team_id.is_(None))
        else:
            q = q.filter(Notification.team_id == user.team_id)
    return q


def _notification_to_dict(n: Notification) -> dict:
    """Notification -> 收件箱条目契约字段。"""
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "type": n.type,
        "sender": n.sender,
        "recipient_type": n.recipient_type,
        "recipient_id": n.recipient_id,
        "channel": n.channel,
        "status": n.status,
        "is_read": bool(n.is_read),
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@inbox_router.get("/inbox")
def list_inbox(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户的站内消息列表 (按 created_at DESC, 支持 unread_only 过滤)。"""
    try:
        q = _inbox_query(db, user)
        if unread_only:
            q = q.filter(Notification.is_read.is_(False))
        total = q.count()
        items = (
            q.order_by(Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return success_response({
            "items": [_notification_to_dict(n) for n in items],
            "total": total,
            "skip": skip,
            "limit": limit,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_inbox 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@inbox_router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户未读消息数。"""
    try:
        count = (
            _inbox_query(db, user)
            .filter(Notification.is_read.is_(False))
            .count()
        )
        return success_response({"unread_count": count})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("unread_count 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@inbox_router.post("/{notification_id}/read")
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记单条站内消息已读 (仅限当前用户收件箱内的消息, is_read=True, read_at=now)。"""
    try:
        n = (
            _inbox_query(db, user)
            .filter(Notification.id == notification_id)
            .first()
        )
        if n is None:
            raise HTTPException(status_code=404, detail="消息不存在")
        if not n.is_read:
            n.is_read = True
            n.read_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(n)
        return success_response(_notification_to_dict(n), message="已标记为已读")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("mark_read 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@inbox_router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户收件箱全部标记已读 (单条 bulk UPDATE, scope 条件完整下推防越权)。"""
    try:
        now = datetime.now(timezone.utc)
        marked = (
            _inbox_query(db, user)
            .filter(Notification.is_read.is_(False))
            .update(
                {"is_read": True, "read_at": now},
                synchronize_session=False,
            )
        )
        db.commit()
        return success_response({"marked_count": marked}, message="全部已标记为已读")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("mark_all_read 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
