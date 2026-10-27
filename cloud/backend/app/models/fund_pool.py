"""
资金池管理模型（企业资金账户）

- FundPool: 企业资金账户（对齐前端 Fleet FundAccount 契约:
            id / enterprise_id / enterprise_name / account_name / account_type /
            balance / status / bank_name / bank_account / currency / description）
- FundPoolTransaction: 资金账户流水（充值 / 消费 / 退款）

枚举统一加 Fund 前缀，避免与 enterprise_transaction.TransactionType 同名冲突。
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


class FundAccountStatus(str, enum.Enum):
    """资金账户状态（对齐前端 mock: active / frozen / inactive）"""
    ACTIVE = "active"
    FROZEN = "frozen"
    INACTIVE = "inactive"


class FundAccountType(str, enum.Enum):
    """资金账户类型（对齐前端 FUND_TYPES；中文自由值，列存 String 不强约束）"""
    OPERATION = "运营账户"
    MAINTENANCE = "维修基金"
    RESERVE = "备用金"
    DEPOSIT = "保证金"
    SETTLEMENT = "结算账户"


class FundTransactionType(str, enum.Enum):
    """资金流水类型"""
    RECHARGE = "recharge"
    CONSUME = "consume"
    REFUND = "refund"


class FundTransactionStatus(str, enum.Enum):
    """资金流水状态"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class FundPool(Base):
    """企业资金账户表 - 对齐前端 Fleet FundAccount 契约"""
    __tablename__ = "fund_pools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"), nullable=True, index=True, comment="所属企业ID")
    enterprise_name = Column(String(200), nullable=True, comment="企业名称(冗余, 便于前端展示)")
    account_name = Column(String(100), nullable=False, comment="账户名称")
    account_type = Column(String(50), nullable=False, default="运营账户", comment="账户类型(运营账户/维修基金/备用金/保证金/结算账户)")
    balance = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="账户余额(元)")
    status = Column(SAEnum(FundAccountStatus), nullable=False, default=FundAccountStatus.ACTIVE, comment="账户状态")
    bank_name = Column(String(100), nullable=True, comment="开户银行")
    bank_account = Column(String(50), nullable=True, comment="银行账号")
    currency = Column(String(10), nullable=False, default="¥", comment="币种符号")
    description = Column(Text, nullable=True, comment="账户描述")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    transactions = relationship(
        "FundPoolTransaction", back_populates="fund_pool", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_fund_pool_enterprise", "enterprise_id"),
        Index("idx_fund_pool_status", "status"),
    )


class FundPoolTransaction(Base):
    """资金账户流水表 - 充值 / 消费 / 退款"""
    __tablename__ = "fund_pool_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_pool_id = Column(Integer, ForeignKey("fund_pools.id", ondelete="CASCADE"), nullable=False, index=True, comment="资金账户ID")
    transaction_type = Column(SAEnum(FundTransactionType), nullable=False, comment="流水类型")
    amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="发生金额(元)")
    balance_before = Column(Numeric(12, 2), nullable=True, comment="交易前余额")
    balance_after = Column(Numeric(12, 2), nullable=True, comment="交易后余额")
    status = Column(SAEnum(FundTransactionStatus), nullable=False, default=FundTransactionStatus.SUCCESS, comment="流水状态")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    fund_pool = relationship("FundPool", back_populates="transactions")

    __table_args__ = (
        Index("idx_fund_txn_pool", "fund_pool_id"),
        Index("idx_fund_txn_created", "created_at"),
    )
