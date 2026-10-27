"""
运维数据分析与预测模块 - 数据模型
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import JSON

from app.core.database import Base


class AnalyticsResult(Base):
    """分析结果表"""
    __tablename__ = "analytics_results"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    analysis_type = Column(String(50), index=True)  # 'health_score', 'fault_prediction', 'efficiency', 'anomaly'
    result_json = Column(JSON)  # 分析结果JSON
    confidence = Column(Float)  # 置信度 (0-1)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    valid_until = Column(DateTime(timezone=True))  # 结果有效期

    __table_args__ = (
        # 卡 77184280: 幂等键唯一约束。health_score/efficiency 任务此前每次
        # 运行裸 INSERT 新行, 重试/重投递即表膨胀; 读侧只按 generated_at 取
        # latest, 单行覆盖 upsert 不破坏语义。两写入方恒写非 NULL
        # analysis_type, 无 PG unique 多 NULL 不去重坑。
        UniqueConstraint("device_id", "analysis_type", name="uq_ar_device_type"),
    )

    # 关系
    device = relationship("Device", back_populates="analytics_results")


class MLModel(Base):
    """机器学习模型记录表"""
    __tablename__ = "ml_models"
    
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False, index=True)  # 模型名称
    model_type = Column(String(50), nullable=False, index=True)  # 'classification', 'regression', 'clustering'
    version = Column(String(20), nullable=False)  # 版本号
    performance_metrics = Column(JSON)  # 性能指标
    trained_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, server_default="true", index=True)  # 是否激活
    
    def __repr__(self):
        return f"<MLModel {self.model_name} v{self.version}>"


class PredictionAlert(Base):
    """预测告警表"""
    __tablename__ = "prediction_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)  # 'fault_prediction', 'anomaly', 'maintenance'
    severity = Column(String(20), nullable=False, index=True)  # 'info', 'warning', 'critical'
    predicted_time = Column(DateTime(timezone=True))  # 预测发生时间
    confidence = Column(Float)  # 置信度 (0-1)
    description = Column(Text)  # 告警描述
    suggested_action = Column(Text)  # 建议操作
    acknowledged = Column(Boolean, server_default="false", index=True)  # 是否已确认
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # 关系
    device = relationship("Device", back_populates="prediction_alerts")


class DeviceHealthHistory(Base):
    """设备健康度历史记录"""
    __tablename__ = "device_health_history"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    health_score = Column(Float, nullable=False)  # 健康度评分 (0-100)
    risk_level = Column(String(20), nullable=False)  # 'low', 'medium', 'high', 'critical'
    component_scores = Column(JSON)  # 各组件评分
    maintenance_recommendations = Column(JSON)  # 维护建议
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # 关系
    device = relationship("Device", back_populates="health_history")


# 在Device模型中添加关系 (需要更新现有的Device模型)
"""
# 在app/models/device.py的Device类中添加:
analytics_results = relationship("AnalyticsResult", back_populates="device", cascade="all, delete-orphan")
prediction_alerts = relationship("PredictionAlert", back_populates="device", cascade="all, delete-orphan")
health_history = relationship("DeviceHealthHistory", back_populates="device", cascade="all, delete-orphan")
"""