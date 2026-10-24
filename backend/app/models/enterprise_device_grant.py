"""
车队三级授权模型 - 公司→场站→设备(桩级白名单) (卡 a1468299)

- EnterpriseDeviceGrant: 运营公司给其车队授权可充电的范围。
  · device_id IS NULL  → 整站授权(该站所有桩可充)
  · device_id IS NOT NULL → 桩级白名单(仅该桩可充)

设计选独立授权表(Option A)而非 FleetChargingPolicy 加 JSON 字段:
授权(grant, "能用什么")与策略(policy, "限额/时段")是两类关注点; 表式建模
带 FK 引用完整性, 且 device_id NULL/NOT NULL 天然表达两级。详见
docs/plans/fleet-device-grant-a1468299.md。
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, ForeignKey, Index,
)

from app.core.database import Base


class EnterpriseDeviceGrant(Base):
    """车队设备授权表 - 整站/桩级白名单"""
    __tablename__ = "enterprise_device_grants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(
        Integer, ForeignKey("enterprises.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="被授权的车队(企业)",
    )
    station_id = Column(
        Integer, ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="授权场站",
    )
    # device_id NULL=整站授权; 非空=桩级白名单。类型对齐 devices.id(BigInteger)。
    device_id = Column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="NULL=整站授权(该站所有桩); 非空=桩级白名单",
    )
    note = Column(String(200), nullable=True, comment="授权备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        # 同企业对同(站点+设备)唯一。注意: SQL 唯一索引对 NULL 不去重(NULL≠NULL),
        # 故"整站授权"(device_id NULL)的重复须由应用层(fleet_grants 路由)显式去重。
        Index("ix_edg_enterprise_station_device", "enterprise_id", "station_id", "device_id", unique=True),
        Index("ix_edg_enterprise", "enterprise_id"),
        Index("ix_edg_station", "station_id"),
    )
