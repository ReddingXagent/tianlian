"""
V2G车队调度模型 - Phase44 V2G车队调度后端

包含:
- FleetV2GPlan: V2G充放电计划表
- FleetV2GRevenue: V2G收益统计表
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, DateTime, Date, ForeignKey, Numeric, Enum as SAEnum, Index, Float
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class V2GPlanStatus(str, enum.Enum):
    """V2G计划状态"""
    SCHEDULED = "scheduled"        # 已排程
    CHARGING = "charging"          # 充电中
    DISCHARGING = "discharging"    # 放电中
    COMPLETED = "completed"        # 已完成
    CANCELLED = "cancelled"        # 已取消
    FAILED = "failed"              # 失败


class FleetV2GPlan(Base):
    """V2G车队充放电计划表"""
    __tablename__ = "fleet_v2g_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True, comment="企业ID")
    vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=False, index=True, comment="车辆ID")
    plan_date = Column(Date, nullable=False, index=True, comment="计划日期")
    
    # 充电时间窗
    planned_charge_start = Column(DateTime, nullable=True, comment="计划充电开始时间")
    planned_charge_end = Column(DateTime, nullable=True, comment="计划充电结束时间")
    
    # 放电时间窗
    planned_discharge_start = Column(DateTime, nullable=True, comment="计划放电开始时间")
    planned_discharge_end = Column(DateTime, nullable=True, comment="计划放电结束时间")
    
    # 目标SOC范围
    target_soc_min = Column(Float, nullable=False, default=20.0, comment="目标最小SOC(%)")
    target_soc_max = Column(Float, nullable=False, default=80.0, comment="目标最大SOC(%)")
    
    # 状态
    status = Column(SAEnum(V2GPlanStatus), default=V2GPlanStatus.SCHEDULED, index=True, comment="计划状态")
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    enterprise = relationship("Enterprise", backref="v2g_plans")
    vehicle = relationship("EnterpriseVehicle", backref="v2g_plans")

    __table_args__ = (
        Index("idx_fv2gp_enterprise_date", "enterprise_id", "plan_date"),
        Index("idx_fv2gp_vehicle_date", "vehicle_id", "plan_date"),
        Index("idx_fv2gp_status_date", "status", "plan_date"),
    )


class FleetV2GRevenue(Base):
    """V2G车队收益统计表"""
    __tablename__ = "fleet_v2g_revenue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True, comment="企业ID")
    vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=False, index=True, comment="车辆ID")
    record_date = Column(Date, nullable=False, index=True, comment="记录日期")
    
    # 放电能量和收益
    discharge_energy_kwh = Column(Numeric(10, 2), default=Decimal("0.00"), comment="放电电量(kWh)")
    discharge_revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="放电收益(元)")
    
    # 电网响应
    grid_response_count = Column(Integer, default=0, comment="电网响应次数")
    
    # 削峰填谷
    peak_shaving_kwh = Column(Numeric(10, 2), default=Decimal("0.00"), comment="削峰电量(kWh)")
    valley_filling_kwh = Column(Numeric(10, 2), default=Decimal("0.00"), comment="填谷电量(kWh)")
    
    # 总收益
    total_revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总收益(元)")
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    enterprise = relationship("Enterprise", backref="v2g_revenues")
    vehicle = relationship("EnterpriseVehicle", backref="v2g_revenues")

    __table_args__ = (
        Index("idx_fv2gr_enterprise_date", "enterprise_id", "record_date"),
        Index("idx_fv2gr_vehicle_date", "vehicle_id", "record_date"),
        Index("idx_fv2gr_enterprise_vehicle_date", "enterprise_id", "vehicle_id", "record_date", unique=True),
    )