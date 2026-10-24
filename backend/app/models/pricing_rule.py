"""
定价规则模型 - Phase41 计费引擎

包含:
- PricingRule: 电价/服务费/停车费/占用费定价规则
- PeriodType: 时段类型枚举
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, Time, Boolean, Enum as SAEnum, Index, DateTime
import enum

from app.core.database import Base


class PeriodType(str, enum.Enum):
    PEAK = "peak"
    SHOULDER = "shoulder"
    VALLEY = "valley"
    FLAT = "flat"
    DEEP_VALLEY = "deep_valley"
    SHARP = "sharp"


class PricingRule(Base):
    """定价规则表 - 分时电价和费率配置"""
    __tablename__ = "pricing_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="规则名称")
    period_type = Column(SAEnum(PeriodType), nullable=False, comment="时段类型: peak/shoulder/valley/flat")
    start_time = Column(Time, nullable=False, comment="时段开始时间")
    end_time = Column(Time, nullable=False, comment="时段结束时间")
    electricity_price = Column(Numeric(10, 4), nullable=False, default=Decimal("0.0000"), comment="电价(元/kWh)")
    service_fee_rate = Column(Numeric(10, 4), nullable=False, default=Decimal("0.0000"), comment="服务费率(元/kWh)")
    parking_fee_per_hour = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="停车费(元/小时)")
    idle_penalty_per_min = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="超时占用费(元/分钟)")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_pr_period", "period_type"),
        Index("idx_pr_active", "is_active"),
    )