"""
车队告警规则引擎模型 - SPEC §4.3 车队平台告警规划表

包含:
- FleetAlertRule: 告警规则配置(规则类型/阈值/通知渠道/启用开关)
- FleetAlertRecord: 告警触发记录(车辆维度的具体告警事件)
"""
from datetime import datetime, timezone

import enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    JSON,
    Enum as SAEnum,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class AlertRuleType(str, enum.Enum):
    """车队告警规则类型"""
    LOW_BATTERY = "low_battery"            # 低电量(SOC低于阈值)
    ABNORMAL_CHARGING = "abnormal_charging"  # 异常充电(功率突变)
    OVERTIME_PARKING = "overtime_parking"  # 超时未离桩


class AlertRecordStatus(str, enum.Enum):
    """告警记录状态"""
    ACTIVE = "active"            # 活跃(未处理)
    ACKNOWLEDGED = "acknowledged"  # 已确认
    RESOLVED = "resolved"        # 已解决


class FleetAlertRule(Base):
    """车队告警规则表"""
    __tablename__ = "fleet_alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True, comment="企业ID")
    rule_type = Column(SAEnum(AlertRuleType), nullable=False, index=True, comment="规则类型")
    threshold = Column(JSON, nullable=False, default=dict, comment="阈值配置(JSON), 如 {soc_below:20}")
    notify_channels = Column(JSON, nullable=False, default=list, comment="通知渠道(JSON), 如 [im, sms]")
    enable = Column(Boolean, nullable=False, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    enterprise = relationship("Enterprise", backref="fleet_alert_rules")
    records = relationship("FleetAlertRecord", backref="rule", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_far_enterprise_type", "enterprise_id", "rule_type"),
    )


class FleetAlertRecord(Base):
    """车队告警触发记录表"""
    __tablename__ = "fleet_alert_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("fleet_alert_rules.id"), nullable=False, index=True, comment="规则ID")
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True, comment="企业ID")
    vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=True, index=True, comment="车辆ID")
    plate_number = Column(String(20), nullable=True, comment="车牌号")
    triggered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True, comment="触发时间")
    alert_value = Column(String(100), nullable=True, comment="触发取值描述, 如 soc=15.0%")
    notified = Column(Boolean, default=False, comment="是否已通知")
    status = Column(SAEnum(AlertRecordStatus), default=AlertRecordStatus.ACTIVE, index=True, comment="处理状态")

    # 关系
    enterprise = relationship("Enterprise", backref="fleet_alert_records")
    vehicle = relationship("EnterpriseVehicle", backref="fleet_alert_records")

    __table_args__ = (
        Index("idx_farec_enterprise_status", "enterprise_id", "status"),
        Index("idx_farec_rule_vehicle_status", "rule_id", "vehicle_id", "status"),
        # partial unique: 同规则同车辆至多一条 ACTIVE (DB 级兜底 service 去重,
        # 卡 49aafa24)。WHERE 用枚举 name 大写 'ACTIVE' (SAEnum 存 name, 卡 d9bba836)
        Index(
            "uq_fleet_alert_active",
            "rule_id", "vehicle_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )
