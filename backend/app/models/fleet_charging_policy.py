"""
企业充电策略模型 - fleet-platform-spec §4.3 规划表

包含:
- FleetChargingPolicy: 企业充电策略(日限额 / 时段白名单 / 站点白名单)
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, DateTime, Boolean, JSON, ForeignKey, Index

from app.core.database import Base


class FleetChargingPolicy(Base):
    """企业充电策略表 - 限额/时段/站点白名单"""
    __tablename__ = "fleet_charging_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="所属企业ID")
    daily_kwh_limit = Column(Float, nullable=False, default=0.0, comment="企业日充电限额(kWh), 0表示不限")
    allowed_time_slots = Column(JSON, nullable=True, comment="允许时段列表, 如 [\"谷\",\"平\"]; 空表示不限")
    allowed_station_ids = Column(JSON, nullable=True, comment="允许站点ID列表; 空表示不限")
    enable = Column(Boolean, nullable=False, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_fcp_enterprise", "enterprise_id"),
        Index("idx_fcp_enable", "enable"),
    )
