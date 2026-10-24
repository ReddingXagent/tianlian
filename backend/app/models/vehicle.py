"""
车辆管理模型（车队管理）

包含：
- Vehicle: 车辆信息（车牌号/VIN码/司机绑定）
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, Enum as SQLEnum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class VehicleStatus(str, enum.Enum):
    ACTIVE = "active"          # 使用中
    IDLE = "idle"              # 闲置
    MAINTENANCE = "maintenance"  # 维修中
    RETIRED = "retired"        # 已报废


class Vehicle(Base):
    """车辆表"""
    __tablename__ = "vehicles"

    id = Column(BigInteger, primary_key=True, index=True)
    plate_number = Column(String(20), unique=True, nullable=False, index=True, comment="车牌号")
    vin = Column(String(50), unique=True, nullable=False, comment="VIN码")
    brand = Column(String(50), comment="品牌")
    model = Column(String(100), comment="车型")
    color = Column(String(20), comment="颜色")
    year = Column(Integer, comment="出厂年份")
    energy_type = Column(String(20), default="electric", comment="能源类型: electric/gasoline/diesel/hybrid")
    battery_capacity = Column(Float, comment="电池容量(kWh)")
    mileage = Column(Float, default=0.0, comment="累计里程(km)")

    # 司机绑定
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="绑定的司机用户ID")
    driver_name = Column(String(100), comment="司机姓名")
    driver_phone = Column(String(20), comment="司机电话")

    # 所属企业/租户
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True, comment="所属企业租户ID")

    # 状态
    status = Column(SQLEnum(VehicleStatus), default=VehicleStatus.IDLE, comment="车辆状态")

    # 时间
    purchase_date = Column(DateTime(timezone=True), comment="购入日期")
    insurance_expire = Column(DateTime(timezone=True), comment="保险到期")
    last_maintenance_date = Column(DateTime(timezone=True), comment="上次保养日期")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    driver = relationship("User", foreign_keys=[driver_id])
