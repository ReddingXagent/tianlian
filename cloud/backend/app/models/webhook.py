# -*- coding: utf-8 -*-
"""
出站 Webhook 管理模型 — SPEC §2.6

- Webhook:            回调配置 (URL / 事件类型 / 密钥 / 重试 / 超时)
- WebhookDelivery:    投递日志 (每次发送记录: 状态 / 响应码 / 耗时)

事件类型:
  alert  — 告警事件
  ticket — 工单事件
  order  — 订单事件
  device — 设备状态变更
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


# 取值白名单
WEBHOOK_EVENT_TYPES = ("alert", "ticket", "order", "device")
DELIVERY_STATUS = ("success", "failed", "pending", "retrying")


class Webhook(Base):
    """出站 Webhook 配置"""
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="Webhook 名称")
    url = Column(String(500), nullable=False, comment="回调 URL")
    event_types = Column(Text, nullable=False, default="[]", comment="订阅事件类型 JSON: [\"alert\",\"ticket\"]")
    secret = Column(String(256), nullable=True, comment="HMAC-SHA256 签名密钥")
    retry_count = Column(Integer, default=3, comment="失败重试次数")
    retry_interval = Column(Integer, default=60, comment="重试间隔(秒)")
    timeout = Column(Integer, default=10, comment="请求超时(秒)")
    enabled = Column(Boolean, default=True, comment="是否启用")
    description = Column(String(500), nullable=True, comment="描述")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间",
    )

    # 关系
    deliveries = relationship("WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_webhook_enabled", "enabled"),
    )

    def __repr__(self):
        return f"<Webhook name={self.name} url={self.url}>"


class WebhookDelivery(Base):
    """Webhook 投递日志"""
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    webhook_id = Column(Integer, ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(30), nullable=True, comment="触发事件类型")
    payload = Column(Text, nullable=True, comment="请求体 JSON")
    status_code = Column(Integer, nullable=True, comment="HTTP 响应码")
    response_body = Column(Text, nullable=True, comment="响应内容(截取前2000字符)")
    status = Column(String(20), default="pending", comment="投递状态 success/failed/pending/retrying")
    duration_ms = Column(Integer, nullable=True, comment="耗时(毫秒)")
    attempt = Column(Integer, default=1, comment="第几次尝试")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    webhook = relationship("Webhook", back_populates="deliveries")

    __table_args__ = (
        Index("idx_delivery_status", "status"),
        Index("idx_delivery_webhook", "webhook_id"),
    )

    def __repr__(self):
        return f"<WebhookDelivery webhook={self.webhook_id} status={self.status}>"
