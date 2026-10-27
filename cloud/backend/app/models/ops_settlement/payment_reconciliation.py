"""
支付对账模型 - SPEC §2.7

平台订单流水 vs 支付渠道(IM-B/支付宝/银联)对账。
状态: pending → reconciled
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum as SAEnum, Index, Date, UniqueConstraint
import enum

from app.core.database import Base


class ReconciliationStatus(str, enum.Enum):
    """对账状态: pending(待对账) → reconciled(已对账)"""
    PENDING = "pending"
    RECONCILED = "reconciled"


class PaymentReconciliation(Base):
    """支付对账记录表"""
    __tablename__ = "payment_reconciliation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_date = Column(Date, nullable=False, index=True, comment="对账日期")
    payment_channel = Column(String(50), nullable=False, comment="支付渠道(im_b/alipay/unionpay)")
    # 平台侧
    platform_orders_count = Column(Integer, default=0, comment="平台订单数")
    platform_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="平台流水金额(元)")
    # 渠道侧
    payment_orders_count = Column(Integer, default=0, comment="渠道订单数")
    payment_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="渠道流水金额(元)")
    # 差异
    difference_count = Column(Integer, default=0, comment="差异数量")
    difference_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="差异金额(元)")
    difference_detail = Column(String(1000), nullable=True, comment="差异说明")
    # 状态
    status = Column(SAEnum(ReconciliationStatus), default=ReconciliationStatus.PENDING, comment="对账状态")
    reconciled_at = Column(DateTime, nullable=True, comment="对账完成时间")
    reconciled_by = Column(String(100), nullable=True, comment="对账操作人")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        # 卡 97c83af9: 幂等键唯一约束, 两列均 NOT NULL, 无 PG NULL 语义坑
        UniqueConstraint("settlement_date", "payment_channel", name="uq_pr_date_channel"),
        Index("idx_pr_date_channel", "settlement_date", "payment_channel"),
        Index("idx_pr_status", "status"),
    )
