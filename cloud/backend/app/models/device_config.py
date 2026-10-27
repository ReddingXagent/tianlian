"""
设备配置模型 - 充电桩参数配置
"""
from sqlalchemy import Column, BigInteger, Boolean, DateTime, Float, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class ChargeMode(str, enum.Enum):
    """充电模式"""
    FAST = "fast"        # 快充
    SMART = "smart"      # 智能
    ECO = "eco"          # 经济/环保


class DeviceConfig(Base):
    """设备配置表 - 充电桩参数配置"""
    __tablename__ = "device_configs"
    
    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, unique=True, index=True)
    
    # 充电参数
    voltage_limit = Column(Float, default=420.0)  # 电压上限 V
    current_limit = Column(Float, default=60.0)   # 电流上限 A
    max_power = Column(Float, default=60.0)       # 最大功率 kW
    charge_mode = Column(SQLEnum(ChargeMode), default=ChargeMode.SMART)  # 充电模式
    overload_protection = Column(Boolean, default=True)  # 过载保护
    
    # 时段配置 (JSON) - 每个元素: {start_time, end_time, power_limit, price_per_kwh}
    time_periods = Column(JSON, default=[])
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    device = relationship("Device", backref="config")