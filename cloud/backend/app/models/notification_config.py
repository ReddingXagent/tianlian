"""
通知配置模型
支持 SMS/邮件/APP 开关管理、模板配置、发送日志记录
"""
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, JSON, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class NotificationConfig(Base):
    """通知配置表 - 租户/站点级通知渠道开关"""
    __tablename__ = "notification_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="配置名称")

    # 作用域：tenant/station/user/device
    scope_type = Column(String(20), nullable=False, default="tenant", comment="作用域类型")
    scope_id = Column(Integer, nullable=True, index=True, comment="作用域ID (租户ID/站点ID/用户ID/设备ID)")

    # 多租户显式隔离 (卡 cf614348): 供快速 team 维度过滤; NULL = 走原 scope_type 兼容逻辑。
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="归属运营团队 (NULL=平台/弱归属)")
    
    # 通知渠道开关
    sms_enabled = Column(Boolean, default=False, comment="短信启用")
    email_enabled = Column(Boolean, default=False, comment="邮件启用")
    app_push_enabled = Column(Boolean, default=False, comment="APP推送启用")
    im_b_enabled = Column(Boolean, default=False, comment="IM-B启用")
    im_enabled = Column(Boolean, default=False, comment="IM启用")
    
    # 接收人配置
    receivers = Column(JSON, default=list, comment="固定接收人列表")
    receiver_roles = Column(JSON, default=list, comment="接收角色: ['admin', 'engineer', 'station_manager']")
    
    # 触发场景
    trigger_events = Column(JSON, default=list, comment="触发事件: ['workorder_dispatch', 'workorder_urge', 'alarm_trigger', 'alarm_escalate', 'workorder_complete']")
    
    # 模板配置（可覆盖全局模板）
    template_overrides = Column(JSON, default=dict, comment="模板覆盖: {'sms': 'custom template', 'email': 'custom template'}")
    
    # 静默时间
    quiet_start = Column(String(5), nullable=True, comment="静默开始时间 HH:MM")
    quiet_end = Column(String(5), nullable=True, comment="静默结束时间 HH:MM")
    timezone = Column(String(50), default="Asia/Shanghai", comment="时区")
    
    # 频率限制
    rate_limit_per_hour = Column(Integer, default=10, comment="每小时限制发送数")
    rate_limit_per_day = Column(Integer, default=50, comment="每天限制发送数")
    
    enabled = Column(Boolean, default=True, comment="是否启用")
    priority = Column(Integer, default=0, comment="优先级，数值越大越优先")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    logs = relationship("NotificationLog", back_populates="config", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_notification_configs_scope', 'scope_type', 'scope_id'),
        Index('ix_notification_configs_enabled', 'enabled'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'scope_type': self.scope_type,
            'scope_id': self.scope_id,
            'team_id': self.team_id,
            'sms_enabled': self.sms_enabled,
            'email_enabled': self.email_enabled,
            'app_push_enabled': self.app_push_enabled,
            'im_b_enabled': self.im_b_enabled,
            'im_enabled': self.im_enabled,
            'receivers': self.receivers or [],
            'receiver_roles': self.receiver_roles or [],
            'trigger_events': self.trigger_events or [],
            'template_overrides': self.template_overrides or {},
            'quiet_start': self.quiet_start,
            'quiet_end': self.quiet_end,
            'timezone': self.timezone,
            'rate_limit_per_hour': self.rate_limit_per_hour,
            'rate_limit_per_day': self.rate_limit_per_day,
            'enabled': self.enabled,
            'priority': self.priority,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationTemplate(Base):
    """通知模板表"""
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="模板名称")
    code = Column(String(50), unique=True, nullable=False, index=True, comment="模板代码，如 workorder_dispatch_sms")
    
    channel = Column(String(20), nullable=False, index=True, comment="渠道: sms/email/app/im_b/im")
    event_type = Column(String(50), nullable=False, index=True, comment="事件类型: workorder_dispatch/workorder_urge/alarm_trigger/...")
    
    # 模板内容
    subject = Column(String(200), nullable=True, comment="主题（邮件用）")
    content = Column(Text, nullable=False, comment="模板内容，支持 {variable} 占位符")
    
    # 变量说明
    variables = Column(JSON, default=list, comment="变量列表: [{'name': 'order_id', 'desc': '工单号', 'example': 'WO-20260101-001'}]")
    
    is_system = Column(Boolean, default=False, comment="是否系统内置模板")
    enabled = Column(Boolean, default=True, comment="是否启用")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'channel': self.channel,
            'event_type': self.event_type,
            'subject': self.subject,
            'content': self.content,
            'variables': self.variables or [],
            'is_system': self.is_system,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationLog(Base):
    """通知发送日志表"""
    __tablename__ = "notification_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("notification_configs.id"), nullable=True, index=True, comment="关联配置ID")
    
    # 事件信息
    event_type = Column(String(50), nullable=False, index=True, comment="事件类型")
    event_id = Column(String(100), nullable=True, index=True, comment="事件ID (工单号/告警ID)")
    event_data = Column(JSON, default=dict, comment="事件数据快照，用于模板渲染")
    
    # 发送信息
    channel = Column(String(20), nullable=False, index=True, comment="发送渠道")
    template_id = Column(Integer, ForeignKey("notification_templates.id"), nullable=True, index=True, comment="使用的模板ID")
    template_code = Column(String(50), nullable=True, comment="模板代码（冗余）")
    
    # 接收信息
    receiver_type = Column(String(20), nullable=False, comment="接收者类型: user/phone/email/webhook")
    receiver_id = Column(String(100), nullable=False, index=True, comment="接收者标识")
    receiver_name = Column(String(100), nullable=True, comment="接收者姓名")
    
    # 内容
    subject = Column(String(200), nullable=True, comment="主题")
    content = Column(Text, nullable=False, comment="实际发送内容")
    
    # 状态
    status = Column(String(20), default="pending", index=True, comment="状态: pending/sent/failed/blocked")
    error_message = Column(Text, nullable=True, comment="错误信息")
    provider_response = Column(JSON, default=dict, comment="服务商响应")
    
    # 时间
    sent_at = Column(DateTime(timezone=True), nullable=True, comment="发送时间")
    delivered_at = Column(DateTime(timezone=True), nullable=True, comment="送达时间")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    config = relationship("NotificationConfig", back_populates="logs")
    
    __table_args__ = (
        Index('ix_notification_logs_event', 'event_type', 'event_id'),
        Index('ix_notification_logs_status_time', 'status', 'created_at'),
        Index('ix_notification_logs_receiver', 'receiver_type', 'receiver_id'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'config_id': self.config_id,
            'event_type': self.event_type,
            'event_id': self.event_id,
            'event_data': self.event_data or {},
            'channel': self.channel,
            'template_id': self.template_id,
            'template_code': self.template_code,
            'receiver_type': self.receiver_type,
            'receiver_id': self.receiver_id,
            'receiver_name': self.receiver_name,
            'subject': self.subject,
            'content': self.content,
            'status': self.status,
            'error_message': self.error_message,
            'provider_response': self.provider_response or {},
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }