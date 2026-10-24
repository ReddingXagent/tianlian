"""
充电调度模型 - 智能充电调度引擎

包含:
- ChargingSchedulePlan: 调度计划
- ChargingScheduleEntry: 调度条目
- ChargingScheduleRule: 调度规则
"""
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, DateTime, Float, ForeignKey, Index, Enum as SAEnum, Boolean, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class ChargingSchedulePlanStatus(PyEnum):
    """调度计划状态"""
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ChargingScheduleRuleType(PyEnum):
    """调度规则类型"""
    PRIORITY_BASED = "priority_based"
    LOAD_BALANCED = "load_balanced"
    VALLEY_FILLING = "valley_filling"
    V2G_OPTIMIZED = "v2g_optimized"


class ChargingEntryMode(PyEnum):
    """调度条目充放电模式"""
    CHARGE = "charge"          # 有序充电
    DISCHARGE = "discharge"    # V2G 反向放电
    IDLE = "idle"              # 待机(无分配)


class ChargingPeriodType(PyEnum):
    """电价时段类型(峰/平/谷)"""
    PEAK = "peak"              # 尖/峰时段(利于V2G放电)
    FLAT = "flat"              # 平时段
    VALLEY = "valley"          # 谷时段(利于充电)


class ChargingSchedulePlan(Base):
    """充电调度计划 - 主计划表"""
    __tablename__ = "charging_schedule_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, nullable=False, index=True, comment="所属企业ID")
    plan_date = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), comment="计划生成日期")
    time_window_start = Column(DateTime, nullable=False, comment="调度时段开始时间")
    time_window_end = Column(DateTime, nullable=False, comment="调度时段结束时间")
    total_available_power_kw = Column(Float, nullable=False, comment="可用总功率(kW)")
    status = Column(SAEnum(ChargingSchedulePlanStatus), nullable=False, default=ChargingSchedulePlanStatus.PLANNED, comment="计划状态")
    rule_json = Column(JSON, nullable=True, comment="关联的规则参数(JSON)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    entries = relationship("ChargingScheduleEntry", back_populates="plan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_csp_enterprise", "enterprise_id"),
        Index("idx_csp_plan_date", "plan_date"),
        Index("idx_csp_status", "status"),
    )


class ChargingScheduleEntry(Base):
    """充电调度条目 - 具体车辆的调度分配"""
    __tablename__ = "charging_schedule_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("charging_schedule_plans.id"), nullable=False, index=True, comment="所属计划ID")
    vehicle_id = Column(Integer, nullable=False, index=True, comment="车辆ID")
    assigned_power_kw = Column(Float, nullable=False, default=0.0, comment="分配功率(kW)")
    start_time = Column(DateTime, nullable=False, comment="开始充电时间")
    end_time = Column(DateTime, nullable=True, comment="结束充电时间")
    priority = Column(Integer, nullable=False, default=100, comment="调度优先级 (数字越小越优先)")
    soc_start = Column(Float, nullable=False, comment="开始SOC (0.0-1.0)")
    soc_target = Column(Float, nullable=False, comment="目标SOC (0.0-1.0)")
    charge_mode = Column(SAEnum(ChargingEntryMode), nullable=False, default=ChargingEntryMode.CHARGE, comment="充放电模式(charge/discharge/idle)")
    period_type = Column(SAEnum(ChargingPeriodType), nullable=True, comment="时段类型(peak/flat/valley)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    plan = relationship("ChargingSchedulePlan", back_populates="entries")

    __table_args__ = (
        Index("idx_cse_plan", "plan_id"),
        Index("idx_cse_vehicle", "vehicle_id"),
        Index("idx_cse_priority", "priority"),
    )


class ChargingScheduleRule(Base):
    """充电调度规则 - 调度策略配置"""
    __tablename__ = "charging_schedule_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, nullable=False, index=True, comment="所属企业ID")
    rule_type = Column(SAEnum(ChargingScheduleRuleType), nullable=False, comment="规则类型")
    priority_weight = Column(Float, nullable=False, default=1.0, comment="优先级权重")
    max_power_per_vehicle = Column(Float, nullable=True, comment="单车最大功率限制(kW)")
    prefer_valley_period = Column(Boolean, nullable=False, default=False, comment="是否偏好谷时充电")
    v2g_enabled = Column(Boolean, nullable=False, default=False, comment="是否启用V2G")
    parameter = Column(JSON, nullable=True, comment="规则扩展参数(JSON)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_csr_enterprise", "enterprise_id"),
        Index("idx_csr_type", "rule_type"),
    )