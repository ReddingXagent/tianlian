"""C端用户车辆模型 (用户端契约§8 P2 §8.6, 卡 36396f29).

不复用运营侧 vehicles 表: 该表车牌/VIN 全局 unique 且绑 driver_id→users.id
(车队管理域)。C 端车辆是 end_user 私有资产, 不同用户同名车牌属正常场景,
故独立表 + (end_user_id, plate_number) 复合唯一。
"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.core.database import Base


class EndUserVehicle(Base):
    """C 端用户车辆, 仅本人可见."""

    __tablename__ = "end_user_vehicles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    end_user_id = Column(Integer, ForeignKey("end_users.id"), nullable=False, index=True)
    plate_number = Column(String(20), nullable=False)
    vin = Column(String(17), nullable=True)
    brand = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("end_user_id", "plate_number", name="uq_end_user_vehicle_plate"),
    )
