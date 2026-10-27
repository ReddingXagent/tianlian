"""
充电订单模型 - Phase41 计费引擎

包含:
- ChargingOrder: 充电订单（含完整费用明细）
- OrderPaymentStatus: 支付状态枚举
- OrderStatus: 订单状态枚举
- PaymentMethod: 支付方式枚举
- UserType: 用户类型枚举
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Integer as SA_Integer, Enum as SAEnum, Index, text
import enum

from app.core.database import Base


class OrderPaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    REFUNDING = "refunding"
    REFUNDED = "refunded"
    PARTIAL = "partial"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CHARGING = "charging"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PaymentMethod(str, enum.Enum):
    WECHAT = "im_b"
    ALIPAY = "alipay"
    CARD = "card"
    ENTERPRISE = "enterprise"
    BALANCE = "balance"


class UserType(str, enum.Enum):
    APP = "app"
    CARD = "card"


class ChargingOrder(Base):
    """充电订单表 - 完整费用明细"""
    __tablename__ = "charging_orders"

    id = Column(SA_Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True, comment="订单编号")
    station_id = Column(SA_Integer, nullable=False, index=True, comment="电站ID")
    device_id = Column(SA_Integer, nullable=False, index=True, comment="充电设备ID")
    user_id = Column(SA_Integer, nullable=True, index=True, comment="用户ID")
    user_type = Column(SAEnum(UserType), nullable=True, comment="用户类型: app/card")
    vehicle_id = Column(SA_Integer, nullable=True, comment="车辆ID")
    plate_number = Column(String(20), nullable=True, comment="车牌号")
    start_time = Column(DateTime, nullable=True, comment="充电开始时间")
    end_time = Column(DateTime, nullable=True, comment="充电结束时间")
    duration_minutes = Column(SA_Integer, default=0, comment="充电时长(分钟)")
    start_soc = Column(Numeric(5, 1), nullable=True, comment="起始SOC%")
    end_soc = Column(Numeric(5, 1), nullable=True, comment="结束SOC%")
    start_meter = Column(Numeric(12, 2), nullable=True, comment="起始电表读数")
    end_meter = Column(Numeric(12, 2), nullable=True, comment="结束电表读数")
    stop_reason = Column(String(50), nullable=True, comment="停止原因: full/active/fault/balance_low")
    # 外部充电会话追溯 (OCPP ingestion, d018e3dc)
    transaction_id = Column(String(64), nullable=True, index=True, comment="外部交易号(OCPP transactionId), 用于幂等")
    connector_id = Column(Integer, nullable=True, comment="充电桩枪号(OCPP connectorId)")
    charged_kwh = Column(Numeric(10, 2), default=Decimal("0.00"), comment="充电电量(kWh)")
    electricity_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="电费(元)")
    service_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="服务费(元)")
    parking_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="停车费(元)")
    idle_penalty = Column(Numeric(12, 2), default=Decimal("0.00"), comment="超时占用费(元)")
    occupancy_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="占桩费(元)")
    reservation_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="预约费(元)")
    # 分时电量明细
    peak_energy = Column(Numeric(10, 2), default=Decimal("0.00"), comment="尖峰电量(kWh)")
    flat_energy = Column(Numeric(10, 2), default=Decimal("0.00"), comment="平段电量(kWh)")
    valley_energy = Column(Numeric(10, 2), default=Decimal("0.00"), comment="谷段电量(kWh)")
    trough_energy = Column(Numeric(10, 2), default=Decimal("0.00"), comment="深谷电量(kWh)")
    # 优惠明细
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总金额(元)")
    discount_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="折扣金额(元)")
    coupon_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="优惠券抵扣(元)")
    points_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="积分抵扣(元)")
    paid_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="实付金额(元)")
    payment_status = Column(SAEnum(OrderPaymentStatus), default=OrderPaymentStatus.UNPAID, comment="支付状态")
    order_status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING, comment="订单状态")
    payment_method = Column(SAEnum(PaymentMethod), nullable=True, comment="支付方式")
    remark = Column(String(500), nullable=True, comment="备注")
    # 异常订单处理闭环 (卡 f730f63c): failed/cancelled 订单的标记处理结果。
    # 全 nullable —— 历史订单无值; abnormal_handle_type 非空即视为"已处理"。
    abnormal_handle_type = Column(String(32), nullable=True, comment="异常处理类型: refunded/written_off/false_alarm")
    abnormal_handle_remark = Column(String(500), nullable=True, comment="异常处理备注")
    abnormal_handled_at = Column(DateTime, nullable=True, comment="异常处理时间(UTC)")
    abnormal_handled_by = Column(Integer, nullable=True, comment="异常处理人ID")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_co_order_no", "order_no", unique=True),
        Index("idx_co_station", "station_id"),
        Index("idx_co_device", "device_id"),
        Index("idx_co_user", "user_id"),
        Index("idx_co_status", "order_status"),
        Index("idx_co_created", "created_at"),
        # 卡 57e7b199: vehicle_id/plate_number 原零索引, 以下热点查询全表扫:
        # fleet 充电统计 (按 vehicle_id 聚合)、车辆详情订单历史 (vehicle_id)、
        # 占位费重叠单匹配 (_find_overlapping_order 按 plate_number)、
        # 车牌维度的订单查询/报表 (plate_number)。
        Index("idx_co_vehicle", "vehicle_id"),
        Index("idx_co_plate", "plate_number"),
        # ingestion 幂等: (transaction_id, device_id) 唯一; transaction_id 为 NULL 时不约束
        # (SQL 标准多 NULL 不冲突, 故手工建单多条共存)
        Index("idx_co_tx_device", "transaction_id", "device_id", unique=True),
        # 防止同一 connector 出现两个活跃订单 (并发竞态 DB 级兜底, 卡 d9bba836):
        # create_order 的 connector 可用性 SELECT 与 INSERT 非原子, READ COMMITTED 下
        # 两并发请求可同枪建两单。应用层二次检查在 SQLite 单 writer 下能兜, 生产 PG
        # 不行 → 此 partial unique index 作硬约束, 终态(completed/cancelled/failed)不参与。
        #
        # 注意 WHERE 用枚举 *name* (大写 PENDING/CHARGING) 而非 value: SAEnum 默认
        # values_callable=None, SQLite/PG 均存枚举 name; 用 value ('pending'/'charging')
        # 会导致 WHERE 永不命中, index 形同虚设 (实测验证, 卡 d9bba836)。
        Index(
            "uq_connector_active_order",
            "device_id", "connector_id",
            unique=True,
            postgresql_where=text("order_status IN ('PENDING', 'CHARGING')"),
            sqlite_where=text("order_status IN ('PENDING', 'CHARGING')"),
        ),
    )
