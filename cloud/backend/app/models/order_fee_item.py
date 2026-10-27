"""
订单费用明细模型 - 运营五项费用扩展

包含:
- OrderFeeItem: 订单费用明细行（充电费/服务费/停车费/占桩费/预约费等）
- RefundRecord: 退款记录（pending → approved → refunded / rejected）
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Index
from sqlalchemy import Enum as SAEnum
import enum

from app.core.database import Base


class FeeType(str, enum.Enum):
    """费用类型枚举"""
    ELECTRICITY = "electricity"      # 电费
    SERVICE = "service"              # 服务费
    PARKING = "parking"              # 停车费
    OCCUPANCY = "occupancy"          # 占桩费
    RESERVATION = "reservation"      # 预约费
    DISCOUNT = "discount"            # 折扣
    COUPON = "coupon"                # 优惠券
    POINTS = "points"                # 积分抵扣


class RefundStatus(str, enum.Enum):
    """退款状态枚举"""
    PENDING = "pending"      # 待审核
    APPROVED = "approved"    # 已批准，待退款
    REFUNDED = "refunded"    # 已退款
    REJECTED = "rejected"    # 已拒绝


class OrderFeeItem(Base):
    """订单费用明细表 - 每笔订单结算时生成多条明细"""
    __tablename__ = "order_fee_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True, comment="充电订单ID")
    fee_type = Column(
        SAEnum(FeeType, name="order_fee_type"),
        nullable=False, comment="费用类型",
    )
    fee_name = Column(String(64), nullable=False, comment="费用项名称")
    quantity = Column(Numeric(12, 4), default=Decimal("0.0000"), comment="数量")
    unit_price = Column(Numeric(12, 6), default=Decimal("0.000000"), comment="单价")
    amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="金额(元)")
    unit = Column(String(20), nullable=True, comment="单位: kWh/小时/分钟/元/次")
    remark = Column(String(255), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_ofi_order", "order_id"),
        Index("idx_ofi_type", "fee_type"),
    )


class RefundRecord(Base):
    """退款记录表 - 退款申请→审批→到账全流程"""
    __tablename__ = "refund_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True, comment="充电订单ID")
    user_id = Column(Integer, nullable=True, index=True, comment="用户ID")
    refund_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="退款金额(元)")
    reason = Column(String(500), nullable=False, comment="退款原因")
    status = Column(SAEnum(RefundStatus), nullable=False, default=RefundStatus.PENDING, comment="退款状态")
    reviewer_id = Column(Integer, nullable=True, comment="审核人ID")
    reviewed_at = Column(DateTime, nullable=True, comment="审核时间")
    refunded_at = Column(DateTime, nullable=True, comment="退款到账时间")
    reject_reason = Column(String(500), nullable=True, comment="拒绝原因")
    # 卡 aa88371f: 退款发起前订单支付状态快照, reject 时恢复 (避免硬编码 REFUNDING→PAID)
    prev_payment_status = Column(String(32), nullable=True, comment="退款发起前订单支付状态快照(reject时恢复)")
    # 卡 aa88371f: 渠道(IM-B)退款单号, complete 调 wx_pay 退款后填
    channel_refund_no = Column(String(64), nullable=True, comment="渠道退款单号(IM-B退款成功后填)")
    # 卡 69fe6381: 平台退款幂等单号 — 渠道失败重试必须复用同号, 否则重复打款
    out_refund_no = Column(String(64), nullable=True, unique=True, comment="平台退款幂等单号(重试复用)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_rr_order", "order_id"),
        Index("idx_rr_user", "user_id"),
        Index("idx_rr_status", "status"),
    )
