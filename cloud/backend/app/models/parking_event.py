"""
占位费事件模型 — 无人值守占位费自动化 (工作卡 f0db2036)

⚠️ 命名一致性说明(丁哥定调):
    平台不取代道闸系统、不收取停车费(停车费归停车场/道闸系统)。
    平台收的是「占位费」: 占用充电车位的费用(尤其充满电后未挪车)。
    现有 billing_engine.compute_parking_fee_full 与 ParkingPrice(parking pricing)
    语义实为占位费引擎/占位费率, 本模块沿用 parking 命名以避免破坏面, 复用其计费逻辑;
    后续 rename 建议: parking_fee → occupancy_parking_fee, ParkingPrice → OccupancyPrice
    (注意: billing_engine.compute_occupancy_fee_full 是「占桩费」, 与本「占位费」是两个概念,
     rename 须先理顺两者边界, 见任务报告)。

OccupancyEvent 记录一笔车位占用:
- 来源: 车牌识别系统(alpr, 外部最终数据: 车牌+起止时间) / 充电订单推算(charging_estimate)
- 计费状态机: PENDING → (BILLED | MERGED | EXEMPT)
    PENDING  未计费(进场未离场 / 站点未配占位费率)
    BILLED   纯占位独立账单(无充电订单, 费用落在 fee_amount)
    MERGED   占位费并入充电订单账单(有匹配订单, 写 order.parking_fee + total + 明细)
    EXEMPT   免费时长内/充电期间全覆盖, fee=0
- 幂等: 同站同车牌未离场(exit_at IS NULL)的事件, 新进场记录更新既有行而非新建。
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Index, ForeignKey,
)
from sqlalchemy import Enum as SAEnum
import enum

from app.core.database import Base


class OccupancyEventSource(str, enum.Enum):
    """占位事件来源"""
    ALPR = "alpr"                            # 车牌识别系统(外部最终数据)
    CHARGING_ESTIMATE = "charging_estimate"  # 充电订单推算(无识别记录时回退)


class OccupancyFeeStatus(str, enum.Enum):
    """占位费计费状态"""
    PENDING = "pending"    # 未计费
    BILLED = "billed"      # 纯占位独立账单
    MERGED = "merged"      # 已并入充电订单账单
    EXEMPT = "exempt"      # 免费时长内, fee=0


class OccupancyEvent(Base):
    """车位占用事件表 — 一笔车牌在一次站点的占位记录(可能匹配到充电订单)"""
    __tablename__ = "occupancy_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plate_number = Column(String(20), nullable=False, index=True, comment="车牌号")
    station_id = Column(
        Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="站点ID")
    enter_at = Column(DateTime, nullable=False, comment="进场时间(UTC)")
    exit_at = Column(DateTime, nullable=True, comment="离场时间(UTC), NULL=未离场")
    source = Column(
        SAEnum(OccupancyEventSource, name="occupancyeventsource"),
        nullable=False, default=OccupancyEventSource.ALPR,
        comment="来源: alpr(识别系统) / charging_estimate(充电订单推算)",
    )
    # 匹配到的充电订单(同站同车牌 + 时间窗重叠); 纯占位时为 NULL
    match_order_id = Column(
        Integer, ForeignKey("charging_orders.id"), nullable=True,
        comment="匹配的充电订单ID(并入账单时填)")
    occupancy_minutes = Column(Integer, default=0, comment="占位时长(分钟)")
    fee_status = Column(
        SAEnum(OccupancyFeeStatus, name="occupancyfeestatus"),
        nullable=False, default=OccupancyFeeStatus.PENDING,
        comment="占位费状态: pending/billed/merged/exempt",
    )
    fee_amount = Column(
        Numeric(12, 2), default=Decimal("0.00"), comment="占位费(元)")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间(UTC)")
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), comment="更新时间(UTC)")

    __table_args__ = (
        # 同站同车牌未离场幂等查询: (plate_number, station_id, exit_at)
        # 索引名用 occevt 前缀, 避免与 spec_tables.idx_occ_order 等同名
        # (SQLite 索引名库级全局唯一)
        Index("idx_occevt_plate_station_exit", "plate_number", "station_id", "exit_at"),
        Index("idx_occevt_station", "station_id"),
        Index("idx_occevt_status", "fee_status"),
        Index("idx_occevt_order", "match_order_id"),
    )
