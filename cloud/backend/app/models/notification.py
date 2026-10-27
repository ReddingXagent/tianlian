"""
站内消息模型 — admin-platform-spec §2.8 站内消息中心

收件箱 / 已读未读状态。隔离键用 team_id (Integer FK→teams)，与 Station.team_id、
operations_analytics._team_scope 同一服务端隔离契约：admin/super_admin 平台级全可见，
团队级用户只看本团队 (team_id == user.team_id) 及平台广播 (team_id IS NULL) 的消息。

注: User 模型的 tenant_id 已注释禁用，用户实际携带的归属作用域是 team_id，故此处
沿用 team_id 作为隔离键（而非字面 tenant_id），保证收件箱能按当前用户作用域正确过滤。
"""
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func

from app.core.database import Base


class Notification(Base):
    """站内消息表 — 每条消息 = 一个接收者(用户或角色)的一站内投递记录。"""

    __tablename__ = "notifications"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    # 隔离键: 所属团队。NULL = 平台级广播 (所有团队可见)。
    team_id = Column(
        Integer,
        ForeignKey("teams.id"),
        nullable=True,
        index=True,
        comment="所属团队(隔离键), NULL=平台广播",
    )

    # 消息体
    title = Column(String(200), nullable=False, comment="消息标题")
    content = Column(Text, nullable=True, comment="消息内容")
    type = Column(
        String(20),
        default="system",
        nullable=False,
        comment="消息类型: alarm/order/work_order/system",
    )
    sender = Column(String(100), default="system", nullable=False, comment="发送者, 系统消息=system")

    # 接收者: user=指定用户(recipient_id=user.id), role=角色广播(recipient_id=角色名)
    recipient_type = Column(
        String(20),
        default="user",
        nullable=False,
        comment="接收者类型: role/user",
    )
    recipient_id = Column(
        String(100),
        nullable=False,
        index=True,
        comment="接收者ID (用户ID字符串或角色名)",
    )

    # 投递
    channel = Column(
        String(20),
        default="app_push",
        nullable=False,
        comment="渠道, 站内默认 app_push",
    )
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        comment="发送状态: pending/sent/failed",
    )

    # 已读状态
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True, comment="已读时间")
    sent_at = Column(DateTime(timezone=True), nullable=True, comment="发送时间")

    # 时间戳
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # 收件箱主查询路径: (recipient_type, recipient_id) → 按时间倒序
        Index("ix_notifications_recipient", "recipient_type", "recipient_id"),
    )
