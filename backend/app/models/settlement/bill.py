"""
车队结算账单模型 - 对账结算

状态流转: pending → confirmed → paid
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Index, UniqueConstraint
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class BillStatus(str, enum.Enum):
    """账单状态: pending(待确认) → confirmed(已确认) → paid(已付款)"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAID = "paid"


class FleetSettlementBill(Base):
    """车队对账结算账单表 - 按账期聚合"""
    __tablename__ = "fleet_settlement_bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_no = Column(String(64), unique=True, nullable=False, index=True, comment="账单编号")
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, comment="企业ID")
    bill_period = Column(String(20), nullable=False, comment="账期 YYYY-MM")
    # 订单统计
    total_orders = Column(Integer, default=0, comment="订单数")
    # 金额汇总
    total_energy_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总电量(kWh)")
    total_charge_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总电费(元)")
    total_service_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总服务费(元)")
    total_parking_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总停车费(元)")
    total_discount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总优惠(元)")
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="应付总额(元)")
    paid_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="已付金额(元)")
    balance_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="待结余额(元)")
    # 状态
    status = Column(SAEnum(BillStatus), default=BillStatus.PENDING, comment="账单状态")
    confirmed_at = Column(DateTime, nullable=True, comment="确认时间")
    paid_at = Column(DateTime, nullable=True, comment="付款时间")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    enterprise = relationship("Enterprise", backref="settlement_bills")
    details = relationship("FleetSettlementDetail", back_populates="bill", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("enterprise_id", "bill_period", name="uq_bill_enterprise_period"),
        Index("idx_fsb_enterprise", "enterprise_id"),
        Index("idx_fsb_period", "bill_period"),
        Index("idx_fsb_status", "status"),
    )
