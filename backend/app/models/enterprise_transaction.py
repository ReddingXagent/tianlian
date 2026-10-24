"""
企业交易记录模型 - Phase41 账户流水

包含:
- EnterpriseTransaction: 企业账户交易流水
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class TransactionType(str, enum.Enum):
    RECHARGE = "recharge"
    CONSUME = "consume"
    REFUND = "refund"


class EnterpriseTransaction(Base):
    """企业交易记录表 - 账户充值/消费/退款流水"""
    __tablename__ = "enterprise_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True, comment="企业ID")
    vehicle_id = Column(Integer, ForeignKey("enterprise_vehicles.id"), nullable=True, index=True, comment="关联车辆ID(可为空)")
    type = Column(SAEnum(TransactionType), nullable=False, comment="交易类型: recharge/consume/refund")
    amount = Column(Numeric(12, 2), nullable=False, comment="交易金额(元)")
    balance_after = Column(Numeric(12, 2), nullable=False, comment="交易后余额(元)")
    order_id = Column(String(64), nullable=True, comment="关联订单号")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    enterprise = relationship("Enterprise", backref="transactions")
    vehicle = relationship("EnterpriseVehicle", backref="transactions")

    __table_args__ = (
        Index("idx_et_enterprise", "enterprise_id"),
        Index("idx_et_type", "type"),
        Index("idx_et_created", "created_at"),
        Index("idx_et_order", "order_id"),
        # 卡4d3ea0ed: (enterprise_id, type, order_id) 部分唯一约束, order_id 非空时
        # DB 层兜底幂等(网络重试/重复提交不再重复加余额); NULL 不受约束,
        # 语义对齐 charging_order.transaction_id
        Index(
            "uq_et_enterprise_type_order",
            "enterprise_id", "type", "order_id",
            unique=True,
            sqlite_where=order_id.isnot(None),
            postgresql_where=order_id.isnot(None),
        ),
    )