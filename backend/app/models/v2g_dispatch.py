"""
V2G调度日志模型
"""
from sqlalchemy import Column, BigInteger, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class V2GDispatchLog(Base):
    """V2G调度日志表"""
    __tablename__ = 'v2g_dispatch_logs'

    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)

    dispatch_type = Column(String(20), nullable=False, index=True, comment='调度类型: charge/discharge/standby')
    target_power_kw = Column(Float, nullable=False, comment='目标功率(kW)')
    actual_power_kw = Column(Float, nullable=False, comment='实际功率(kW)')
    actual_energy_kwh = Column(Float, nullable=True, comment='实际能量(kWh)')

    status = Column(String(20), nullable=False, default='pending', index=True, comment='状态: pending/executing/completed/failed')

    start_at = Column(DateTime(timezone=True), nullable=True, comment='开始时间')
    end_at = Column(DateTime(timezone=True), nullable=True, comment='结束时间')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment='创建时间')

    # 关系
    device = relationship("Device", back_populates="v2g_dispatch_logs")