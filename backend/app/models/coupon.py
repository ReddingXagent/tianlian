"""
优惠券模型 - P0 运营核心补齐

包含:
- Coupon: 优惠券（类型/面额/门槛/有效期/库存）
- CouponBatch: 优惠券发放批次
- CouponUsage: 优惠券使用记录
- CouponType: 优惠券类型枚举
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Enum as SAEnum, Text, Index
import enum

from app.core.database import Base


class CouponType(str, enum.Enum):
    FIXED = "fixed"            # 固定金额券
    PERCENTAGE = "percentage"  # 百分比折扣券
    FREE_CHARGE = "free_charge"  # 免单券
    SERVICE_FREE = "service_free"  # 免服务费券


class CouponStatus(str, enum.Enum):
    ACTIVE = "active"          # 可用
    USED = "used"              # 已使用
    EXPIRED = "expired"        # 已过期
    DISABLED = "disabled"      # 已停用


class Coupon(Base):
    """优惠券定义表"""
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="优惠券名称")
    coupon_type = Column(SAEnum(CouponType), nullable=False, default=CouponType.FIXED, comment="券类型")
    face_value = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="面额/折扣率")
    min_order_amount = Column(Numeric(10, 2), nullable=True, default=Decimal("0.00"), comment="最低使用门槛(元)")
    max_discount_amount = Column(Numeric(10, 2), nullable=True, comment="最大优惠金额上限(元)")
    applicable_user_types = Column(Text, nullable=True, comment="适用用户类型，逗号分隔")
    applicable_stations = Column(Text, nullable=True, comment="适用站点ID列表，逗号分隔")
    total_stock = Column(Integer, nullable=False, default=0, comment="总库存")
    remaining_stock = Column(Integer, nullable=False, default=0, comment="剩余库存")
    per_user_limit = Column(Integer, nullable=True, default=1, comment="每人限领数量")
    valid_days = Column(Integer, nullable=False, default=30, comment="领取后有效天数")
    start_time = Column(DateTime, nullable=False, comment="发放开始时间")
    end_time = Column(DateTime, nullable=False, comment="发放结束时间")
    is_active = Column(Boolean, default=True, comment="是否启用")
    description = Column(Text, nullable=True, comment="描述")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_coupon_type", "coupon_type"),
        Index("idx_coupon_active", "is_active"),
        Index("idx_coupon_time", "start_time", "end_time"),
    )


class CouponBatch(Base):
    """优惠券发放批次表"""
    __tablename__ = "coupon_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coupon_id = Column(Integer, nullable=False, index=True, comment="关联优惠券ID")
    batch_name = Column(String(100), nullable=False, comment="批次名称")
    quantity = Column(Integer, nullable=False, default=0, comment="发放数量")
    user_type = Column(String(50), nullable=True, comment="发放目标用户类型")
    user_ids = Column(Text, nullable=True, comment="具体用户ID列表，逗号分隔")
    distributed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="发放时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_cb_coupon_id", "coupon_id"),
    )


class CouponUsage(Base):
    """优惠券使用记录表"""
    __tablename__ = "coupon_usages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coupon_id = Column(Integer, nullable=False, index=True, comment="关联优惠券ID")
    batch_id = Column(Integer, nullable=True, index=True, comment="关联批次ID")
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    user_type = Column(String(50), nullable=True, comment="用户类型")
    coupon_code = Column(String(64), nullable=False, unique=True, index=True, comment="券码")
    order_id = Column(Integer, nullable=True, index=True, comment="关联订单ID")
    status = Column(SAEnum(CouponStatus), nullable=False, default=CouponStatus.ACTIVE, comment="状态")
    discount_amount = Column(Numeric(10, 2), nullable=True, default=Decimal("0.00"), comment="实际抵扣金额")
    used_at = Column(DateTime, nullable=True, comment="使用时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="领取时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_cu_user_id", "user_id"),
        Index("idx_cu_status", "status"),
        Index("idx_cu_expires", "expires_at"),
    )