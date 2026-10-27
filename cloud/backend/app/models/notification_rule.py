"""
通知规则配置模型
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class NotificationRule(Base):
    """通知规则配置表"""
    __tablename__ = "notification_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 规则名称
    level = Column(String(20), index=True)  # 告警级别: critical/warning/info/daily
    channels = Column(JSON, default=list)  # 通知渠道: ["sms", "email", "im_b"]
    receivers = Column(JSON, default=list)  # 接收人列表
    enabled = Column(Boolean, default=True)  # 是否启用
    
    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'level': self.level,
            'channels': self.channels or [],
            'receivers': self.receivers or [],
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
