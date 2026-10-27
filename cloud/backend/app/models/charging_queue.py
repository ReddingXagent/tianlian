"""
充电排序队列模型 - Phase41 车队管理

核心表结构对应 spec §2.3 中的 charging_queue 字段定义
"""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Index, JSON

from app.core.database import Base


class ChargingQueueStatus(str, Enum):
    WAITING = "waiting"
    CHARGING = "charging"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ChargingQueue(Base):
    """充电排序队列 - 实时队列模型"""

    __tablename__ = "charging_queues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True, comment="电站ID")
    vehicle_id = Column(Integer, nullable=False, index=True, comment="车辆ID")
    enterprise_id = Column(Integer, nullable=True, default=0, index=True, comment="企业ID")
    rule_id = Column(Integer, nullable=True, index=True, comment="排序规则ID")
    priority = Column(Integer, nullable=False, default=100, comment="排序优先级 (数字越小越靠前)")
    arrival_time = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True, comment="入队时间")
    estimated_wait_minutes = Column(Integer, nullable=False, default=0, comment="预计等待分钟数")
    required_energy_kwh = Column(Float, nullable=False, default=0.0, comment="需求能量(kWh)")
    target_soc = Column(Float, nullable=False, default=0.8, comment="目标SOC (0.0-1.0)")
    current_soc = Column(Float, nullable=True, default=0.0, comment="当前SOC (0.0-1.0)")
    status = Column(String(20), nullable=False, default="waiting", index=True, comment="队列状态")
    assigned_device_id = Column(Integer, nullable=True, default=None, comment="分配的充电桩设备ID")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_cq_station", "station_id"),
        Index("idx_cq_vehicle", "vehicle_id"),
        Index("idx_cq_rule", "rule_id"),
        Index("idx_cq_priority", "priority"),
        Index("idx_cq_arrival", "arrival_time"),
        Index("idx_cq_status", "status"),
    )


class ChargingQueueRule(Base):
    """充电排序规则 - 支持 JSON 优先级标准"""

    __tablename__ = "charging_queue_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, nullable=False, default=0, index=True, comment="企业ID")
    station_id = Column(Integer, nullable=True, default=None, index=True, comment="电站ID (null=全局)")
    rule_name = Column(String(100), nullable=False, comment="规则名称")
    priority_criteria = Column(JSON, nullable=False, default=list, comment="权重计算标准 (JSON array of {field, weight, direction})")
    max_queue_length = Column(Integer, nullable=False, default=100, comment="最大队列长度")
    enable = Column(Boolean, nullable=False, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_cqr_enterprise", "enterprise_id"),
        Index("idx_cqr_name", "rule_name"),
    )
