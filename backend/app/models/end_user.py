"""C端用户模型 (用户端契约§8, 卡 d95dafd3)."""

import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class EndUserType(str, enum.Enum):
    APP = "app"
    CARD = "card"
    VIN = "vin"
    INTERCONNECT = "interconnect"
    ENTERPRISE = "enterprise"


class EndUserStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class EndUser(Base):
    """IM-B C 端用户, 与运营侧 User/RBAC 完全隔离."""

    __tablename__ = "end_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wx_openid = Column(String(128), nullable=False, unique=True, index=True)
    wx_unionid = Column(String(128), nullable=True, index=True)
    nickname = Column(String(100), nullable=False, default="", server_default="")
    avatar_url = Column(String(500), nullable=False, default="", server_default="")
    phone = Column(String(20), nullable=True, index=True)
    user_type = Column(
        SAEnum(EndUserType, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        default=EndUserType.APP,
        server_default="app",
    )
    status = Column(
        SAEnum(EndUserStatus, values_callable=lambda x: [m.value for m in x]),
        nullable=False,
        default=EndUserStatus.ACTIVE,
        server_default="active",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
