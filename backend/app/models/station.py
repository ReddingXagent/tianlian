"""
站点模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, Float, Numeric, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base

class StationStatus(str, enum.Enum):
    NORMAL = "normal"          # 正常
    MAINTENANCE = "maintenance"  # 维护中
    CLOSED = "closed"          # 关闭
    ACTIVE = "active"           # 活跃（兼容旧数据）

class ApprovalStatus(str, enum.Enum):
    """站点审核状态（任务卡 1256e7fa）。

    自建自营站点默认 approved（直通）；监管/第三方站点后续可切审核流
    （pending → approved/rejected），本期仅留字段 + 接口。
    """
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"

class Station(Base):
    """站点表"""
    __tablename__ = "stations"
    
    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    name = Column(String(100), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    
    # 地址
    province = Column(String(50))
    city = Column(String(50))
    district = Column(String(50))
    address = Column(String(200))
    lat = Column(Float)  # 纬度
    lon = Column(Float)  # 经度
    
    # 运营商
    operator_id = Column(Integer, ForeignKey("users.id"), index=True)
    operator_name = Column(String(100))
    
    # 运维团队
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    
    # 多租户支持
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True, comment="所属租户")
    
    # 配置
    total_power = Column(Float)  # 总功率 kW
    total_devices = Column(Integer, default=0)  # 设备数量
    gun_count = Column(Integer, default=0)  # 充电枪数量
    
    # 场所与成本信息
    venue_type = Column(String(50), nullable=True, comment="建设场所: highway_station/transport_hub/mall/community/industrial_park")
    total_cost = Column(Numeric(12, 2), nullable=True, comment="站点总成本(元)")
    parking_spots = Column(Integer, nullable=True, comment="车位数")
    station_type = Column(String(50), nullable=True, comment="站点类型: public/private/residential")
    contact_person = Column(String(50), nullable=True, comment="联系人")
    contact_phone = Column(String(30), nullable=True, comment="联系电话")
    description = Column(Text, nullable=True, comment="描述")
    pv_capacity = Column(Float, nullable=True, comment="光伏装机量(kWp)")
    ess_capacity = Column(Float, nullable=True, comment="储能装机量(kWh)")
    
    # 状态
    status = Column(SQLEnum(StationStatus), default=StationStatus.NORMAL)
    health_score = Column(Float, default=100.0)  # 健康度 (0-100)

    # 审核状态（任务卡 1256e7fa）：自建自营直通 approved，监管站点可切审核流
    approval_status = Column(
        SQLEnum(ApprovalStatus),
        default=ApprovalStatus.APPROVED,
        nullable=False,
        index=True,
        comment="审核状态: approved/pending/rejected",
    )
    
    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    operator = relationship("User", foreign_keys=[operator_id], back_populates="operated_stations")
    team = relationship("Team", foreign_keys=[team_id], back_populates="stations")
    tenant = relationship("Tenant", back_populates="stations")
    devices = relationship("Device", back_populates="station", cascade="all, delete-orphan")
    workorders = relationship("WorkOrder", back_populates="station")
    alarms = relationship("Alarm", back_populates="station")
    # Phase1: 新增遥测专表关系
    telemetry_pv_records = relationship("TelemetryPV", back_populates="station")
    telemetry_battery_records = relationship("TelemetryBattery", back_populates="station")
    telemetry_charger_records = relationship("TelemetryCharger", back_populates="station")
    maintenance_records = relationship("MaintenanceRecord", back_populates="station")
