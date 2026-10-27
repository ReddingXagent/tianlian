"""通知渠道配置模型 (卡 8d98ebe3)

按 team_id 隔离的真实发送渠道凭证表。与 NotificationConfig (渠道开关 + 接收人 +
模板路由) 正交: ChannelConfig 只管「这个团队的某渠道拿什么凭证去真实发送」。

config JSON 按渠道存不同键:
  - im:  webhook_url, secret(HMAC-SHA256 签名校验)
  - wecom:   webhook_url, secret(企微机器人签名, 预留)
  - webhook: webhook_url, secret(自定义校验头, 预留)
  - email:   smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from
  - sms:     sms_access_key, sms_secret, sign_name, template_code
  - voice:   voice_access_key, voice_secret, voice_caller, voice_template_code

凭证未报备的渠道 (sms/voice) 实际发送走 mock log, 仅预留配置位 (见 channel_providers)。
"""
import enum

from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func

from app.core.database import Base


class ChannelType(str, enum.Enum):
    """通知渠道枚举 — 与 _dispatch_channel 渠道名同源。"""
    IM = "im"
    WECOM = "wecom"
    WEBHOOK = "webhook"
    SMS = "sms"
    VOICE = "voice"
    EMAIL = "email"


class ChannelConfig(Base):
    """团队级通知渠道凭证配置。

    (team_id, channel) 唯一: 一个团队同一渠道只保留一份凭证。team_id NULL = 平台级
    默认凭证 (团队未单独配置时回退使用)。SQLite 对 NULL 不去重, 故平台级每渠道
    允许多行 —— 调用方查询时按 enabled + 最新优先即可, 不依赖约束。
    """
    __tablename__ = "channel_configs"

    id = Column(Integer, primary_key=True, index=True)
    # 隔离键: NULL = 平台级默认凭证, 供团队未配置时回退。
    team_id = Column(
        Integer,
        ForeignKey("teams.id"),
        nullable=True,
        index=True,
        comment="归属团队 (NULL=平台默认凭证)",
    )
    channel = Column(
        SQLEnum(ChannelType, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        comment="渠道: im/wecom/webhook/sms/voice/email",
    )
    # 各渠道凭证 JSON (见模块 docstring 键约定)
    config = Column(JSON, default=dict, nullable=False, comment="渠道凭证 JSON")
    enabled = Column(Boolean, default=True, nullable=False, comment="是否启用")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("team_id", "channel", name="uq_channel_config_team_channel"),
        Index("ix_channel_config_team_channel", "team_id", "channel"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "team_id": self.team_id,
            "channel": self.channel.value if hasattr(self.channel, "value") else self.channel,
            "config": self.config or {},
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
