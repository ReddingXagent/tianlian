"""
企业账户模型 - Phase41 运营管理

包含:
- Enterprise: 企业账户（车队/运营企业）
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum as SAEnum, Index, Text, JSON, ForeignKey, Table
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base

# 多对多关联表: 企业 ↔ 场站
enterprise_stations = Table(
    "enterprise_stations",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("enterprise_id", Integer, ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("station_id", Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", DateTime, default=lambda: datetime.now(timezone.utc)),
    Index("idx_enterprise_station_unique", "enterprise_id", "station_id", unique=True),
)


class EnterpriseStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Enterprise(Base):
    """企业账户表 - 车队和运营企业账户"""
    __tablename__ = "enterprises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="企业名称")
    code = Column(String(50), unique=True, nullable=False, comment="企业编码")
    contact = Column(String(100), nullable=True, comment="联系人")
    phone = Column(String(20), nullable=True, comment="联系电话")
    balance = Column(Numeric(12, 2), default=Decimal("0.00"), comment="账户余额(元)")
    credit_limit = Column(Numeric(12, 2), default=Decimal("0.00"), comment="信用额度(元)")
    default_vehicle_config = Column(JSON, nullable=True, comment="默认车辆配置(JSON)")

    # 经营团队归属
    owner_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, comment="经营团队ID")

    address = Column(String(500), nullable=True, comment="企业地址")
    description = Column(Text, nullable=True, comment="企业描述")
    status = Column(SAEnum(EnterpriseStatus), default=EnterpriseStatus.ACTIVE, comment="状态")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    owner_team = relationship("Team", foreign_keys=[owner_team_id])
    stations = relationship("Station", secondary=enterprise_stations, backref="enterprises")

    __table_args__ = (
        Index("idx_enterprise_code", "code"),
        Index("idx_enterprise_status", "status"),
        Index("idx_enterprise_owner_team", "owner_team_id"),
    )
