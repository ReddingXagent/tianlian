"""
互联互通结算模型 - SPEC §2.7

与第三方互联互通平台的导流订单分成结算。
状态: pending → settled
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum as SAEnum, Index, Date
import enum

from app.core.database import Base


class InterconnectSettlementStatus(str, enum.Enum):
    """互联互通结算状态: pending(待结算) → settled(已结算)"""
    PENDING = "pending"
    SETTLED = "settled"


class InterconnectSettlement(Base):
    """互联互通结算表"""
    __tablename__ = "interconnect_settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(String(100), nullable=False, comment="第三方平台标识")
    platform_name = Column(String(200), nullable=True, comment="平台名称")
    start_date = Column(Date, nullable=False, comment="结算周期开始")
    end_date = Column(Date, nullable=False, comment="结算周期结束")
    # 订单统计
    total_orders = Column(Integer, default=0, comment="导流订单数")
    total_energy_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总充电量(kWh)")
    # 金额
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="订单总金额(元)")
    revenue_share_ratio = Column(Numeric(5, 4), default=Decimal("0.0000"), comment="分成比例(如0.7000=70%)")
    our_revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="我方收入(元)")
    partner_revenue = Column(Numeric(12, 2), default=Decimal("0.00"), comment="合作方收入(元)")
    settlement_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="实际结算金额(元)")
    # 发票
    invoice_id = Column(Integer, nullable=True, comment="关联发票ID")
    # 状态
    status = Column(SAEnum(InterconnectSettlementStatus), default=InterconnectSettlementStatus.PENDING, comment="结算状态")
    settled_at = Column(DateTime, nullable=True, comment="结算时间")
    settled_by = Column(String(100), nullable=True, comment="结算操作人")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_is_platform", "platform_id"),
        Index("idx_is_period", "start_date", "end_date"),
        Index("idx_is_status", "status"),
    )
