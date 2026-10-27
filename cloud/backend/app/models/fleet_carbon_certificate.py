"""
碳减排核证/交易模型 - fleet-platform-spec §4.3 规划表

包含:
- FleetCarbonCertificate: 碳减排核证/交易记录
  (从月度汇总申请核证 -> 核证确认 -> 交易登记, 全程状态机约束)
"""
from datetime import datetime, timezone
from decimal import Decimal
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    Index,
    Enum as SAEnum,
)

from app.core.database import Base


class CertificateStatus(str, enum.Enum):
    """碳核证状态"""
    PENDING = "pending"      # 待核证(已申请, 等待核证确认)
    VERIFIED = "verified"    # 已核证(可进入交易)
    TRADED = "traded"        # 已交易(已登记交易量/价)
    CANCELLED = "cancelled"  # 已撤销(作废)


class FleetCarbonCertificate(Base):
    """碳减排核证/交易记录表"""
    __tablename__ = "fleet_carbon_certificates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True, comment="所属企业ID")
    summary_id = Column(Integer, ForeignKey("carbon_reduction_summary.id"), nullable=False, index=True, comment="关联碳减排月度汇总ID")
    certificate_no = Column(String(64), nullable=False, unique=True, index=True, comment="核证编号")
    verified_at = Column(DateTime, nullable=True, comment="核证时间")
    trade_volume = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"), comment="交易量(吨CO2)")
    trade_price = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="交易单价(元/吨)")
    status = Column(SAEnum(CertificateStatus), nullable=False, default=CertificateStatus.PENDING, index=True, comment="核证状态")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_fcc_enterprise_status", "enterprise_id", "status"),
        Index("idx_fcc_summary", "summary_id"),
    )
