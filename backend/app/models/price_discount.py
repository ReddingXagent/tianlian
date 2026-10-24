"""
折扣模型 - P0 运营核心补齐

包含:
- PriceDiscount: 折扣方案（折扣名称/类型/折扣率/适用用户类型/生效时间）
- DiscountGroup: 折扣电价组（用户分组折扣）
- DiscountType: 折扣类型枚举
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Enum as SAEnum, Text, Index
import enum

from app.core.database import Base


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"    # 百分比折扣（如 9折）
    FIXED = "fixed"              # 固定金额折扣
    TIERED = "tiered"            # 阶梯折扣


class PriceDiscount(Base):
    """折扣方案表"""
    __tablename__ = "price_discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="折扣名称")
    discount_type = Column(SAEnum(DiscountType), nullable=False, default=DiscountType.PERCENTAGE, comment="折扣类型")
    discount_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("1.00"), comment="折扣率(0.00~1.00) 或固定金额")
    applicable_user_types = Column(Text, nullable=True, comment="适用用户类型，逗号分隔: app,card,vin,interconnect,enterprise")
    min_consumption = Column(Numeric(10, 2), nullable=True, default=Decimal("0.00"), comment="最低消费门槛(元)")
    max_discount_amount = Column(Numeric(10, 2), nullable=True, comment="最大折扣金额上限(元)")
    start_time = Column(DateTime, nullable=False, comment="生效开始时间")
    end_time = Column(DateTime, nullable=False, comment="生效结束时间")
    priority = Column(Integer, default=0, comment="优先级，数字越大越优先")
    is_active = Column(Boolean, default=True, comment="是否启用")
    description = Column(Text, nullable=True, comment="描述")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_price_disc_type", "discount_type"),
        Index("idx_price_disc_active", "is_active"),
        Index("idx_price_disc_priority", "priority"),
    )


class DiscountGroup(Base):
    """折扣电价组表 - 用户分组关联折扣方案"""
    __tablename__ = "discount_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="分组名称")
    discount_id = Column(Integer, nullable=False, index=True, comment="关联折扣方案ID")
    user_type = Column(String(50), nullable=False, index=True, comment="用户类型: app/card/vin/interconnect/enterprise")
    user_ids = Column(Text, nullable=True, comment="关联用户ID列表，逗号分隔; 为空表示该类型所有用户")
    station_ids = Column(Text, nullable=True, comment="适用站点ID列表，逗号分隔; 为空表示所有站点")
    priority = Column(Integer, default=0, comment="优先级")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_dg_user_type", "user_type"),
        Index("idx_dg_active", "is_active"),
        Index("idx_dg_discount_id", "discount_id"),
    )