"""C端设备 push token 模型 (用户端契约§8.4, 卡 d95dafd3)."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class EndUserDeviceToken(Base):
    """同一 C 端用户每个平台仅保留一个生效设备 token."""

    __tablename__ = "end_user_device_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    end_user_id = Column(Integer, ForeignKey("end_users.id"), nullable=False, index=True)
    platform = Column(String(16), nullable=False)
    device_token = Column(String(512), nullable=False)
    app_version = Column(String(50), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (UniqueConstraint("end_user_id", "platform", name="uq_end_user_device_platform"),)
