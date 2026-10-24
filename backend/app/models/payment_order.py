"""IM-B服务商支付订单模型 (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §2 (支付)

设计:
- PaymentOrder 是IM-B服务商支付订单的真相源 (独立于 ChargingOrder, 后者的
  transaction_id 已被 OCPP ingestion 占用, 故不复用)。
- business_order_no = 契约 order_id (ChargingOrder.order_no), 作 prepay/查询的关联键。
- payment_status 大写五态逐字对齐契约 §2.3 (UNPAID/PAID/REFUNDING/REFUNDED/CLOSED)。
- wx_transaction_id 为IM-B支付交易号 (4200...), 支付成功回调后填; 与 ChargingOrder 的
  OCPP transaction_id 互不干扰。
- notify_processed 作回调幂等标志 (重复回调不重复落 PAID)。
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Enum as SAEnum,
    Index,
)

from app.core.database import Base


def _enum_values(ec):
    return [m.value for m in ec]


class PaymentStatus(str, enum.Enum):
    """支付状态 (契约 §2.3 大写五态)"""

    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"
    CLOSED = "CLOSED"


class PayScene(str, enum.Enum):
    """下单场景 (契约 §2.1 scene, 决定下单 appid)"""

    MINIPROGRAM = "miniprogram"  # 小程序 appid
    APP = "app"                  # IM-B开放平台移动应用 appid


class PaymentOrder(Base):
    """IM-B服务商支付订单表"""
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True)
    out_trade_no = Column(String(64), unique=True, nullable=False, index=True, comment="平台统一下单单号 TL_yyyymmdd_xxxx")
    business_order_no = Column(String(64), nullable=False, index=True, comment="业务订单号 (= 契约 order_id, ChargingOrder.order_no)")

    # 下单参数
    openid = Column(String(64), nullable=False, comment="用户 openid")
    scene = Column(SAEnum(PayScene, values_callable=_enum_values), nullable=False, comment="下单场景")
    sub_mchid = Column(String(32), nullable=False, comment="特约商户号 (下单用)")
    appid = Column(String(32), nullable=True, comment="下单 appid (回调比对基准; 存量行为 NULL 兼容)")
    amount_fen = Column(Integer, nullable=False, default=0, comment="金额 (分)")
    description = Column(String(200), nullable=True, comment="商品描述")

    # IM-B返回
    prepay_id = Column(String(64), nullable=True, comment="预支付ID (下单返回)")
    wx_transaction_id = Column(String(64), nullable=True, comment="IM-B支付交易号 (支付成功后填)")

    # 状态
    payment_status = Column(
        SAEnum(PaymentStatus, values_callable=_enum_values),
        nullable=False,
        default=PaymentStatus.UNPAID,
        comment="支付状态",
    )
    paid_at = Column(DateTime, nullable=True, comment="支付完成时间")

    # 回调幂等
    notify_count = Column(Integer, nullable=False, default=0, comment="回调累计次数")
    notify_processed = Column(Boolean, nullable=False, default=False, comment="回调是否已处理 (幂等标志)")

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_payorder_biz", "business_order_no"),
        Index("idx_payorder_status", "payment_status"),
    )
