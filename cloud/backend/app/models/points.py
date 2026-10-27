"""
积分模型 - P0 运营核心补齐

包含:
- PointsRule: 积分规则
- PointsRecord: 积分流水记录
- PointsRuleType: 积分规则类型枚举
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Enum as SAEnum, Text, Index
import enum

from app.core.database import Base


class PointsRuleType(str, enum.Enum):
    CHARGE = "charge"               # 充电积分
    RECHARGE = "recharge"           # 充值积分
    SIGN_IN = "sign_in"             # 签到积分
    INVITE = "invite"               # 邀请积分
    BIRTHDAY = "birthday"           # 生日积分
    ACTIVITY = "activity"           # 活动积分
    SYSTEM = "system"               # 系统发放


class PointsRecordType(str, enum.Enum):
    EARN = "earn"                   # 获取
    REDEEM = "redeem"               # 兑换/消费
    EXPIRE = "expire"               # 过期
    ADJUST = "adjust"               # 调整


class PointsRule(Base):
    """积分规则表"""
    __tablename__ = "points_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="规则名称")
    rule_type = Column(SAEnum(PointsRuleType), nullable=False, comment="规则类型")
    points = Column(Integer, nullable=False, default=0, comment="积分值")
    unit = Column(String(50), nullable=True, comment="积分单位描述（如 '每消费1元'）")
    daily_limit = Column(Integer, nullable=True, comment="每日上限")
    weekly_limit = Column(Integer, nullable=True, comment="每周上限")
    total_limit = Column(Integer, nullable=True, comment="总上限")
    applicable_user_types = Column(Text, nullable=True, comment="适用用户类型，逗号分隔")
    min_amount = Column(Numeric(10, 2), nullable=True, comment="最低触发金额(元)")
    points_expire_days = Column(Integer, nullable=True, comment="积分过期天数")
    is_active = Column(Boolean, default=True, comment="是否启用")
    start_time = Column(DateTime, nullable=True, comment="规则生效开始时间")
    end_time = Column(DateTime, nullable=True, comment="规则生效结束时间")
    description = Column(Text, nullable=True, comment="规则描述")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_points_rule_type", "rule_type"),
        Index("idx_points_rule_active", "is_active"),
    )


class PointsRecord(Base):
    """积分流水记录表"""
    __tablename__ = "points_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    user_type = Column(String(50), nullable=True, comment="用户类型")
    rule_id = Column(Integer, nullable=True, index=True, comment="关联规则ID")
    record_type = Column(SAEnum(PointsRecordType), nullable=False, comment="流水类型")
    points = Column(Integer, nullable=False, default=0, comment="积分变动值(正数为获取)")
    balance_before = Column(Integer, nullable=False, default=0, comment="变动前余额")
    balance_after = Column(Integer, nullable=False, default=0, comment="变动后余额")
    description = Column(Text, nullable=True, comment="备注")
    order_id = Column(Integer, nullable=True, index=True, comment="关联订单ID")
    expires_at = Column(DateTime, nullable=True, comment="积分过期时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    __table_args__ = (
        Index("idx_prec_user_id", "user_id"),
        Index("idx_prec_type", "record_type"),
        Index("idx_prec_created", "created_at"),
    )