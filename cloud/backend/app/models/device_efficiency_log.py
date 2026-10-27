"""
设备效率日志模型

存储设备效率计算的历史记录，用于趋势分析。
字段设计对应效率报表所需的三类指标:
- 利用率 (utilization)
- 充电效率 (charge_efficiency)
- 发电效率 (generation_efficiency / pv_pr)
"""
from sqlalchemy import Column, BigInteger, String, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceEfficiencyLog(Base):
    """设备效率日志表"""
    __tablename__ = "device_efficiency_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), nullable=True, index=True)

    # === 利用率 ===
    utilization = Column(Float, nullable=True, comment="设备利用率(%)")

    # === 充电效率 ===
    charge_efficiency = Column(Float, nullable=True, comment="充电效率(%)")

    # === 发电效率 ===
    generation_efficiency = Column(Float, nullable=True, comment="发电效率(%)")
    pv_pr = Column(Float, nullable=True, comment="光伏PR性能比")

    # === 原始数据快照 (JSON, 用于调试) ===
    raw_data = Column(JSON, nullable=True, comment="原始遥测数据快照")

    # === V3扩展: 通用效率指标 ===
    metric_type = Column(String(50), nullable=True, index=True, comment='指标类型: utilization/charge/generation')
    metric_name = Column(String(100), nullable=True, comment='指标名称')
    metric_value = Column(Float, nullable=True, comment='指标值')
    unit = Column(String(20), nullable=True, comment='单位')
    threshold_warn = Column(Float, nullable=True, comment='告警阈值')
    threshold_critical = Column(Float, nullable=True, comment='严重阈值')
    recorded_at = Column(DateTime(timezone=True), nullable=True, index=True, comment='记录时间')

    # === 时间 ===
    log_date = Column(String(10), nullable=False, index=True, comment="日志日期 YYYY-MM-DD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    device = relationship("Device", back_populates="efficiency_logs")