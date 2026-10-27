"""
停车场减免留痕记录 - 任务卡 309b4132

外部停车场系统按充电状态对车主减免停车费后，回调留痕（对账凭证）。
order_no 幂等：同一停车场订单号仅留一条。
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Index, ForeignKey

from app.core.database import Base


class ParkingDiscountApplied(Base):
    """停车减免留痕表 - 减免已发生的事实记录"""
    __tablename__ = "parking_discount_applied"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True, comment="商户站点ID(取自对接凭证)")
    plate_number = Column(String(20), nullable=False, index=True, comment="车牌号")
    order_no = Column(String(100), nullable=False, unique=True, index=True, comment="停车场订单号(幂等键)")
    amount = Column(Numeric(12, 2), nullable=False, comment="减免金额(元)")
    applied_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="减免发生时间")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_pda_station", "station_id"),
        Index("idx_pda_plate", "plate_number"),
    )
