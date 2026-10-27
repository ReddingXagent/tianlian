"""
车队账单明细模型 - 对账结算

每条明细对应一个充电订单的费用拆解。
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class FleetSettlementDetail(Base):
    """车队账单明细表 - 按订单粒度"""
    __tablename__ = "fleet_settlement_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("fleet_settlement_bills.id", ondelete="CASCADE"), nullable=False, comment="所属账单ID")
    order_id = Column(Integer, nullable=False, comment="充电订单ID")
    order_no = Column(String(64), nullable=True, comment="订单编号")
    vehicle_id = Column(Integer, nullable=True, comment="车辆ID")
    plate_number = Column(String(20), nullable=True, comment="车牌号")
    driver_id = Column(Integer, nullable=True, comment="司机ID")
    charging_time = Column(DateTime, nullable=True, comment="充电时间")
    energy_kwh = Column(Numeric(10, 2), default=Decimal("0.00"), comment="充电量(kWh)")
    charge_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="电费(元)")
    service_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="服务费(元)")
    parking_fee = Column(Numeric(12, 2), default=Decimal("0.00"), comment="停车费(元)")
    discount_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="优惠金额(元)")
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), comment="订单总额(元)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    bill = relationship("FleetSettlementBill", back_populates="details")

    __table_args__ = (
        Index("idx_fsd_bill", "bill_id"),
        Index("idx_fsd_order", "order_id"),
        Index("idx_fsd_vehicle", "vehicle_id"),
    )
