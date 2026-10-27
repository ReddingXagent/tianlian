"""
设备维护记录模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class MaintenanceType(str, enum.Enum):
    PREVENTIVE = "preventive"      # 预防性维护
    CORRECTIVE = "corrective"       # 纠正性维护
    CONDITION_BASED = "condition_based"  # 状态维护
    EMERGENCY = "emergency"         # 紧急维修


class MaintenanceStatus(str, enum.Enum):
    PLANNED = "planned"        # 计划中
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"      # 已完成
    CANCELLED = "cancelled"      # 已取消


class MaintenanceRecord(Base):
    """设备维护记录表"""
    __tablename__ = "maintenance_records"

    id = Column(BigInteger, primary_key=True, index=True)

    # 关联
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), index=True)
    engineer_id = Column(Integer, ForeignKey("users.id"), index=True)

    # 类型与状态
    type = Column(SQLEnum(MaintenanceType), default=MaintenanceType.PREVENTIVE, nullable=False)
    status = Column(SQLEnum(MaintenanceStatus), default=MaintenanceStatus.PLANNED, nullable=False)

    # 内容
    title = Column(String(200), nullable=False)
    description = Column(Text)
    solution = Column(Text)
    parts_replaced = Column(Text)   # 更换备件
    cost = Column(Integer, default=0)  # 维护费用（分）

    # 时间
    planned_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    device = relationship("Device", back_populates="maintenance_records")
    station = relationship("Station", back_populates="maintenance_records")
    engineer = relationship("User", foreign_keys=[engineer_id], back_populates="maintenance_records")
