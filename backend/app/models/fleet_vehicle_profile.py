"""
车辆维保/保险档案模型 - fleet-platform-spec §4.3 规划表

包含:
- FleetVehicleMaintenance: 车辆维保记录(保养/维修/年检)
- FleetVehicleInsurance: 车辆保险档案

注意: 枚举加 Vehicle 前缀, 避免与 maintenance_record.MaintenanceType/MaintenanceStatus 重名覆盖。
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Index
import enum

from app.core.database import Base


class VehicleMaintenanceType(str, enum.Enum):
    MAINTENANCE = "maintenance"  # 保养
    REPAIR = "repair"            # 维修
    INSPECTION = "inspection"    # 年检


class VehicleMaintenanceStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VehicleInsuranceType(str, enum.Enum):
    COMPULSORY = "compulsory"    # 交强险
    COMMERCIAL = "commercial"    # 商业险
    THIRD_PARTY = "third_party"  # 三者险


class FleetVehicleMaintenance(Base):
    """车辆维保记录表 - 保养/维修/年检"""
    __tablename__ = "fleet_vehicle_maintenances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=False, comment="车辆ID")
    type = Column(SAEnum(VehicleMaintenanceType), nullable=False, comment="类型: maintenance/repair/inspection")
    start_at = Column(DateTime, nullable=True, comment="开始时间")
    end_at = Column(DateTime, nullable=True, comment="结束时间")
    cost = Column(Numeric(12, 2), default=Decimal("0.00"), comment="费用(元)")
    mileage = Column(Numeric(12, 2), default=Decimal("0.00"), comment="里程(km)")
    description = Column(String(500), nullable=True, comment="描述")
    status = Column(SAEnum(VehicleMaintenanceStatus), default=VehicleMaintenanceStatus.PENDING, comment="状态")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_fvm_vehicle", "vehicle_id"),
        Index("idx_fvm_type", "type"),
        Index("idx_fvm_status", "status"),
    )


class FleetVehicleInsurance(Base):
    """车辆保险档案表"""
    __tablename__ = "fleet_vehicle_insurances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=False, comment="车辆ID")
    insurance_type = Column(SAEnum(VehicleInsuranceType), nullable=False, comment="保险类型: compulsory/commercial/third_party")
    company = Column(String(100), nullable=False, comment="保险公司")
    policy_no = Column(String(100), nullable=False, comment="保单号")
    start_date = Column(DateTime, nullable=False, comment="起保日期")
    end_date = Column(DateTime, nullable=False, comment="到期日期")
    premium = Column(Numeric(12, 2), default=Decimal("0.00"), comment="保费(元)")
    attachment_url = Column(String(500), nullable=True, comment="保单附件URL")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_fvi_vehicle", "vehicle_id"),
        Index("idx_fvi_type", "insurance_type"),
        Index("idx_fvi_end", "end_date"),
    )
