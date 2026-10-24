"""
停车折扣方案模型 - Phase46 停车管理

商户站点的停车折扣配置：免费时长 / 折扣比例 / 固定减免。
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Index

from app.core.database import Base


class ParkingDiscount(Base):
    """停车折扣方案表 - 商户站点"""
    __tablename__ = "parking_discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, nullable=False, index=True, comment="商户站点ID")
    merchant_name = Column(String(100), nullable=True, comment="商户名称")
    discount_type = Column(String(30), nullable=False, default="free_minutes",
                           comment="折扣类型: free_minutes/percentage/fixed")
    free_minutes = Column(Integer, nullable=True, default=0, comment="免费时长(分钟)")
    discount_percent = Column(Numeric(5, 2), nullable=True, default=0, comment="折扣比例(%)")
    fixed_amount = Column(Numeric(12, 2), nullable=True, default=0, comment="固定减免(元)")
    max_discount = Column(Numeric(12, 2), nullable=True, comment="单次最大减免(元)")
    valid_start = Column(String(5), nullable=True, comment="每日有效开始 HH:MM")
    valid_end = Column(String(5), nullable=True, comment="每日有效结束 HH:MM")
    is_active = Column(Boolean, default=True, comment="是否启用")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_pd_station", "station_id"),
        Index("idx_pd_active", "is_active"),
    )
