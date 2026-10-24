"""
日结汇总模型 - SPEC §2.7

按日期聚合充电订单的五项费用汇总。
状态: pending → confirmed
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum as SAEnum, Index, Date, UniqueConstraint, event
import enum

from app.core.database import Base


class SettlementStatus(str, enum.Enum):
    """日结状态: pending(待确认) → confirmed(已确认)"""
    PENDING = "pending"
    CONFIRMED = "confirmed"


class DailySettlement(Base):
    """日结汇总表 - 按日期+站点维度聚合"""
    __tablename__ = "daily_settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_date = Column(Date, nullable=False, index=True, comment="结算日期")
    station_id = Column(Integer, nullable=True, index=True, comment="站点ID (NULL=全平台)")
    # 卡 97c83af9: 唯一约束哨兵键。PG 默认 unique 视多个 NULL 为不同值, 全平台
    # 汇总行(station_id=NULL)会重复插入, 故落库前由 before_insert 事件把
    # station_id 映射为 station_key=COALESCE(station_id, 0), 约束建在非 NULL 列上。
    station_key = Column(Integer, nullable=False, default=0, server_default="0",
                         comment="站点哨兵键 (station_id, NULL=0, 唯一约束载体)")
    # 订单统计
    total_orders = Column(Integer, default=0, comment="总订单数")
    total_energy_kwh = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总充电量(kWh)")
    # 五项费用汇总
    total_charge_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总电费(元)")
    total_service_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总服务费(元)")
    total_parking_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总停车费(元)")
    total_occupancy_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总占桩费(元)")
    total_reservation_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="总预约费(元)")
    # 金额汇总
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="应收总额(元)")
    total_paid = Column(Numeric(12, 2), default=Decimal("0.00"), comment="实收总额(元)")
    total_discount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="优惠金额(元)")
    total_coupon = Column(Numeric(12, 2), default=Decimal("0.00"), comment="优惠券抵扣(元)")
    total_points = Column(Numeric(12, 2), default=Decimal("0.00"), comment="积分抵扣(元)")
    total_refund = Column(Numeric(12, 2), default=Decimal("0.00"), comment="退款金额(元)")
    # 状态
    status = Column(SAEnum(SettlementStatus), default=SettlementStatus.PENDING, comment="结算状态")
    confirmed_at = Column(DateTime, nullable=True, comment="确认时间")
    confirmed_by = Column(String(100), nullable=True, comment="确认人")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        # 卡 97c83af9: 幂等键唯一约束 (settlement_date, station_key)。用非 NULL
        # 哨兵列 station_key 而非 station_id, 规避 PG unique 多 NULL 不去重。
        UniqueConstraint("settlement_date", "station_key", name="uq_ds_date_station"),
        Index("idx_ds_date_station", "settlement_date", "station_id"),
        Index("idx_ds_status", "status"),
    )


@event.listens_for(DailySettlement, "before_insert")
def _ds_sync_station_key(mapper, connection, target):
    """station_id → station_key 哨兵同步 (NULL=0), 保持唯一约束载体非 NULL。"""
    target.station_key = target.station_id if target.station_id is not None else 0
