"""
碳排放管理模型 - 车队碳排放追踪与减排核算

包含:
- CarbonEmissionFactor: 碳排放因子表 (年份/区域/类型/因子值/来源)
- CarbonReductionRecord: 碳减排记录表 (车辆/日期/充电量/电网因子/减排量/等效节油量)
- CarbonReductionSummary: 碳减排月度汇总表 (企业/年/月/合计/审核状态)
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Date, Index, UniqueConstraint

from app.core.database import Base


class CarbonEmissionFactor(Base):
    """碳排放因子表 - 按年份/区域/类型记录电网排放因子和燃油基准"""
    __tablename__ = "carbon_emission_factors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False, comment="年份")
    region = Column(String(50), nullable=False, default="全国", comment="区域(如:全国/华东/华北)")
    factor_type = Column(String(50), nullable=False, comment="因子类型(grid-电网/fuel-燃油基准)")
    emission_factor = Column(Numeric(10, 6), nullable=False, comment="排放因子(kgCO2/kWh 或 kgCO2/L)")
    source = Column(String(200), nullable=True, comment="数据来源(如:生态环境部)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_cef_year_region_type", "year", "region", "factor_type", unique=True),
    )


class CarbonReductionRecord(Base):
    """碳减排记录表 - 每辆车每次充电的减排量"""
    __tablename__ = "carbon_reduction_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(Integer, nullable=False, comment="车辆ID(enterprise_vehicles.id)")
    enterprise_id = Column(Integer, nullable=False, comment="所属企业ID")
    record_date = Column(Date, nullable=False, comment="记录日期")
    charge_energy_kwh = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="充电量(kWh)")
    grid_factor = Column(Numeric(10, 6), nullable=False, default=Decimal("0.000000"), comment="电网排放因子(kgCO2/kWh)")
    fuel_factor = Column(Numeric(10, 6), nullable=False, default=Decimal("0.000000"), comment="燃油排放基准(kgCO2/kWh,已含能量转换)")
    carbon_reduction_kg = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="碳减排量(kgCO2)")
    equivalent_fuel_saved_liters = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="等效节油量(L)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        # 卡 7ea84b57: 幂等唯一约束, 防 celery 并发/acks_late 重投递插重复行
        # 导致下游 func.sum 碳减排量双倍 (同族: 卡 97c83af9 / 9863018d)
        UniqueConstraint("vehicle_id", "record_date", name="uq_crr_vehicle_date"),
        Index("idx_crr_vehicle_date", "vehicle_id", "record_date"),
        Index("idx_crr_enterprise_date", "enterprise_id", "record_date"),
    )


class CarbonReductionSummary(Base):
    """碳减排月度汇总表 - 按企业/年/月汇总减排数据"""
    __tablename__ = "carbon_reduction_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, nullable=False, comment="企业ID")
    report_year = Column(Integer, nullable=False, comment="报告年份")
    report_month = Column(Integer, nullable=False, comment="报告月份(1-12)")
    total_charge_kwh = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"), comment="总充电量(kWh)")
    total_reduction_kg = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"), comment="总减排量(kgCO2)")
    total_fuel_saved_liters = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"), comment="总节油量(L)")
    vehicle_count = Column(Integer, nullable=False, default=0, comment="参与车辆数")
    verified = Column(Boolean, nullable=False, default=False, comment="是否已审核")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_crs_enterprise_year_month", "enterprise_id", "report_year", "report_month", unique=True),
    )
