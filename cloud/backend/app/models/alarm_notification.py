"""
告警通知发送记录模型 (maint-platform-spec §2.1)

记录每次告警通知的发送结果，用于审计与查询。
spec 字段: id, alarm_id, channel(sms/app/email), recipient, sent_at, status, result
"""
from sqlalchemy import Column, BigInteger, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class AlarmNotification(Base):
    """告警通知发送记录表

    每次向某接收人某渠道发送告警通知（含成功/失败/静默跳过）写一条记录。
    """
    __tablename__ = "alarm_notifications"

    id = Column(BigInteger, primary_key=True, index=True)
    alarm_id = Column(BigInteger, ForeignKey("alarms.id"), nullable=False, index=True, comment="关联告警ID")
    channel = Column(String(20), nullable=False, comment="发送渠道: sms/email/app_push/im/im_b")
    recipient = Column(String(200), nullable=True, comment="接收人标识(手机号/邮箱/用户ID)")
    sent_at = Column(DateTime(timezone=True), nullable=True, comment="发送时间")
    status = Column(String(20), nullable=False, index=True, comment="状态: sent/failed/quiet")
    result = Column(Text, nullable=True, comment="发送结果/错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="记录创建时间")
