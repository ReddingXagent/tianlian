"""
车队充值申请模型

- FleetRechargeRequest: 车队充值申请（凭证上传 → 运营商审核 → 余额入账）
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Text,
    ForeignKey, Enum as SAEnum, Index,
)
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class RechargeStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FleetRechargeRequest(Base):
    """车队充值申请表"""
    __tablename__ = "fleet_recharge_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False, index=True, comment="车队企业ID")
    amount = Column(Numeric(12, 2), nullable=False, comment="充值金额(元)")
    voucher_url = Column(String(500), nullable=False, comment="凭证文件路径")
    status = Column(SAEnum(RechargeStatus), default=RechargeStatus.PENDING, nullable=False, index=True, comment="状态")
    remark = Column(Text, nullable=True, comment="审核备注(驳回理由)")
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="审核人ID")
    reviewed_at = Column(DateTime, nullable=True, comment="审核时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    enterprise = relationship("Enterprise", foreign_keys=[enterprise_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    __table_args__ = (
        Index("idx_fleet_recharge_status", "status"),
        Index("idx_fleet_recharge_enterprise", "enterprise_id"),
    )
