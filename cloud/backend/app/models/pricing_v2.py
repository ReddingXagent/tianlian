"""
定价管理模型 V2 - Phase42 运营管理平台

包含 6 类定价模型:
1. TimeSlotDefinition - 时段定义(尖/峰/平/谷)
2. EnergyPrice - 充电费定价
3. ServiceFeePrice - 服务费定价
4. ParkingPrice - 停车费定价
5. OccupancyFeePrice - 占桩费定价
6. ReservationFeePrice - 预约费定价
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, Time, Boolean, Enum as SAEnum, Index, DateTime, Date, ForeignKey
import enum

from app.core.database import Base


class PeriodType(str, enum.Enum):
    """时段类型: 尖/峰/平/谷"""
    PEAK = "peak"
    SHOULDER = "shoulder"
    FLAT = "flat"
    VALLEY = "valley"
    DEEP_VALLEY = "deep_valley"
    SHARP = "sharp"


class UserType(str, enum.Enum):
    """用户类型"""
    APP = "app"
    CARD = "card"
    VIN = "vin"
    INTERCONNECT = "interconnect"
    ENTERPRISE = "enterprise"


class FeeType(str, enum.Enum):
    """费用类型"""
    FIXED = "fixed"
    PERCENT = "percent"


class ReservationPolicy(str, enum.Enum):
    """预约策略"""
    SLOT_BASED = "slot_based"
    FLAT = "flat"


class TimeSlotDefinition(Base):
    """时段定义表 - 尖/峰/平/谷时段模板"""
    __tablename__ = "time_slot_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="时段名称: 尖/峰/平/谷")
    period_type = Column(SAEnum(PeriodType), nullable=False, unique=True, comment="时段类型枚举")
    start_time = Column(Time, nullable=False, comment="开始时间")
    end_time = Column(Time, nullable=False, comment="结束时间")
    description = Column(String(200), nullable=True, comment="描述")
    is_active = Column(Boolean, default=True, comment="是否启用")
    sort_order = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_tsd_period", "period_type"),
        Index("idx_tsd_active", "is_active"),
    )


class EnergyPrice(Base):
    """充电费定价 - 基于站点和时段的电价"""
    __tablename__ = "energy_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="站点ID")
    slot_id = Column(Integer, ForeignKey("time_slot_definitions.id"), nullable=False, index=True, comment="时段ID")
    price_per_kwh = Column(Numeric(10, 4), nullable=False, default=Decimal("0.0000"), comment="电价(元/kWh)")
    effective_date = Column(Date, nullable=False, index=True, comment="生效日期")
    expire_date = Column(Date, nullable=True, index=True, comment="失效日期")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_ep_station_slot", "station_id", "slot_id"),
        Index("idx_ep_effective", "effective_date", "expire_date"),
        Index("idx_ep_active", "is_active"),
    )


class ServiceFeePrice(Base):
    """服务费定价 - 按站点、用户类型区分"""
    __tablename__ = "service_fee_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="站点ID")
    user_type = Column(SAEnum(UserType), nullable=False, index=True, comment="用户类型")
    fee_type = Column(SAEnum(FeeType), nullable=False, comment="费用类型: fixed/percent")
    fee_value = Column(Numeric(10, 4), nullable=False, default=Decimal("0.0000"), comment="费用值: 固定金额(元/次) 或 费率(元/kWh)")
    effective_date = Column(Date, nullable=False, index=True, comment="生效日期")
    expire_date = Column(Date, nullable=True, index=True, comment="失效日期")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_sfp_station_user", "station_id", "user_type"),
        Index("idx_sfp_effective", "effective_date", "expire_date"),
        Index("idx_sfp_active", "is_active"),
    )


class ParkingPrice(Base):
    """停车费定价 - 站内停车计时收费"""
    __tablename__ = "parking_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="站点ID")
    free_minutes = Column(Integer, default=0, comment="免费时长(分钟)")
    hourly_rate = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="小时费率(元/小时)")
    daily_cap = Column(Numeric(10, 2), nullable=True, comment="日封顶金额")
    enable_night_rate = Column(Boolean, default=False, comment="是否启用夜间费率")
    night_rate = Column(Numeric(10, 2), nullable=True, comment="夜间费率(元/小时)")
    night_start = Column(Time, nullable=True, comment="夜间开始时间")
    night_end = Column(Time, nullable=True, comment="夜间结束时间")
    effective_date = Column(Date, nullable=False, index=True, comment="生效日期")
    expire_date = Column(Date, nullable=True, index=True, comment="失效日期")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_pp_station", "station_id"),
        Index("idx_pp_effective", "effective_date", "expire_date"),
        Index("idx_pp_active", "is_active"),
    )


class OccupancyFeePrice(Base):
    """占桩费定价 - 充电完成后超时停放罚金"""
    __tablename__ = "occupancy_fee_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="站点ID")
    grace_minutes = Column(Integer, default=15, comment="免罚时长(分钟)")
    rate_per_minute = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="罚金费率(元/分钟)")
    max_fee = Column(Numeric(10, 2), nullable=True, comment="单次封顶金额")
    effective_date = Column(Date, nullable=False, index=True, comment="生效日期")
    expire_date = Column(Date, nullable=True, index=True, comment="失效日期")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_ofp_station", "station_id"),
        Index("idx_ofp_effective", "effective_date", "expire_date"),
        Index("idx_ofp_active", "is_active"),
    )


class ReservationFeePrice(Base):
    """预约费定价 - 预约充电占位费"""
    __tablename__ = "reservation_fee_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="站点ID")
    deposit_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="预约冻结金额")
    reservation_policy = Column(SAEnum(ReservationPolicy), nullable=False, comment="预约策略: slot_based/flat")
    fee_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="预约费金额")
    no_show_penalty = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="爽约罚款金额")
    effective_date = Column(Date, nullable=False, index=True, comment="生效日期")
    expire_date = Column(Date, nullable=True, index=True, comment="失效日期")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_rfp_station", "station_id"),
        Index("idx_rfp_effective", "effective_date", "expire_date"),
        Index("idx_rfp_active", "is_active"),
    )