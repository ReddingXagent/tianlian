"""
企业车辆模型 - Phase41 车队管理

包含:
- EnterpriseVehicle: 企业所属车辆（含确认状态）
- StationVinWhitelist: 场站 VIN 充电授权白名单
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class EnterpriseVehicleStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EnterpriseVehicle(Base):
    """企业车辆表 - 企业车队管理的自有车辆"""
    __tablename__ = "enterprise_vehicles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="所属企业ID")
    plate_number = Column(String(20), nullable=False, comment="车牌号")
    vin = Column(String(50), unique=True, nullable=False, comment="VIN码")
    driver_name = Column(String(100), nullable=True, comment="司机姓名")
    driver_phone = Column(String(20), nullable=True, comment="司机电话")
    status = Column(SAEnum(EnterpriseVehicleStatus), default=EnterpriseVehicleStatus.ACTIVE, comment="状态")
    # 确认流字段
    approval_status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False, comment="确认状态")
    confirmed_at = Column(DateTime, nullable=True, comment="确认时间")
    confirmed_by = Column(String(100), nullable=True, comment="确认人")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    enterprise = relationship("Enterprise", backref="vehicles")

    __table_args__ = (
        Index("idx_ev_enterprise", "enterprise_id"),
        Index("idx_ev_plate", "plate_number"),
        Index("idx_ev_vin", "vin", unique=True),
        Index("idx_ev_approval", "enterprise_id", "approval_status"),
    )


class StationVinWhitelist(Base):
    """场站 VIN 充电授权白名单

    车辆 confirmed 后，VIN 自动进入所绑定场站的白名单。
    解绑/拒绝时自动移除。
    """
    __tablename__ = "station_vin_whitelist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, comment="场站ID")
    vin = Column(String(50), nullable=False, comment="VIN码")
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="所属企业ID")
    source = Column(String(50), nullable=False, default="vehicle_confirm", comment="来源: vehicle_confirm/manual/auto")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_svw_station_vin", "station_id", "vin", unique=True),
        Index("idx_svw_enterprise", "enterprise_id"),
        Index("idx_svw_vin", "vin"),
    )