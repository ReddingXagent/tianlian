"""
车队发票申请模型 - 对账结算
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class InvoiceStatus(str, enum.Enum):
    PENDING = "pending"
    ISSUED = "issued"
    REJECTED = "rejected"


class InvoiceType(str, enum.Enum):
    GENERAL = "general"
    SPECIAL = "special"


class FleetInvoiceRequest(Base):
    """车队发票申请表"""
    __tablename__ = "fleet_invoice_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="企业ID")
    bill_id = Column(Integer, ForeignKey("fleet_settlement_bills.id"), nullable=True, comment="关联账单ID")
    amount = Column(Numeric(12, 2), nullable=False, comment="开票金额(元)")
    invoice_type = Column(SAEnum(InvoiceType), default=InvoiceType.GENERAL, comment="发票类型")
    title = Column(String(200), nullable=False, comment="发票抬头")
    tax_no = Column(String(50), nullable=True, comment="税号")
    email = Column(String(100), nullable=True, comment="接收邮箱")
    status = Column(SAEnum(InvoiceStatus), default=InvoiceStatus.PENDING, comment="状态")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    enterprise = relationship("Enterprise", backref="invoice_requests")
    bill = relationship("FleetSettlementBill", backref="invoice_requests")

    __table_args__ = (
        Index("idx_fir_enterprise", "enterprise_id"),
        Index("idx_fir_bill", "bill_id"),
        Index("idx_fir_status", "status"),
    )
