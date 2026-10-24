#!/Users/xxx/.openclaw/workspace/projects/tianlian-v3/backend/venv/bin/python3
"""
AI 诊断记录模型 - 存储AI智能诊断结果
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class DiagnosisStatus(str, enum.Enum):
    PENDING = "pending"       # 等待诊断
    RUNNING = "running"       # 诊断中
    COMPLETED = "completed"    # 诊断完成
    FAILED = "failed"         # 诊断失败


class AIDiagnosisRecord(Base):
    """AI诊断记录表"""
    __tablename__ = "ai_diagnosis_records"

    id = Column(Integer, primary_key=True, index=True)
    alarm_id = Column(Integer, ForeignKey("alarms.id"), index=True, nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), index=True)

    status = Column(SQLEnum(DiagnosisStatus), default=DiagnosisStatus.PENDING)

    # 触发方式
    trigger_type = Column(String(20), default="manual")  # auto/manual

    # 原始日志内容
    log_source = Column(String(50), default="remote")  # remote/manual_paste
    raw_log = Column(Text, nullable=True)

    # 诊断结果（结构化）
    fault_type = Column(String(100), nullable=True)  # 故障类型
    fault_location = Column(String(200), nullable=True)  # 故障定位
    root_cause = Column(Text, nullable=True)  # 根因分析
    severity = Column(String(20), nullable=True)  # low/medium/high/critical
    confidence = Column(Float, nullable=True)  # 置信度 0-1

    # 匹配的知识库故障码
    matched_fault_code = Column(String(20), nullable=True)
    matched_fault_name = Column(String(100), nullable=True)

    # 处理建议
    immediate_actions = Column(JSON, nullable=True)  # 立即处理步骤列表
    repair_suggestions = Column(JSON, nullable=True)  # 维修建议列表
    preventive_measures = Column(JSON, nullable=True)  # 预防措施列表
    remote_fixable = Column(Boolean, default=False)  # 是否可远程修复

    # 原始AI响应
    raw_ai_response = Column(Text, nullable=True)

    # 错误信息
    error_message = Column(Text, nullable=True)

    # 诊断耗时(秒)
    duration_ms = Column(Integer, nullable=True)

    # 用户反馈
    user_feedback = Column(String(20), nullable=True)  # helpful/useless/wrong
    user_comment = Column(Text, nullable=True)

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "alarm_id": self.alarm_id,
            "device_id": self.device_id,
            "station_id": self.station_id,
            "status": self.status.value if self.status else None,
            "trigger_type": self.trigger_type,
            "log_source": self.log_source,
            "fault_type": self.fault_type,
            "fault_location": self.fault_location,
            "root_cause": self.root_cause,
            "severity": self.severity,
            "confidence": self.confidence,
            "matched_fault_code": self.matched_fault_code,
            "matched_fault_name": self.matched_fault_name,
            "immediate_actions": self.immediate_actions,
            "repair_suggestions": self.repair_suggestions,
            "preventive_measures": self.preventive_measures,
            "remote_fixable": self.remote_fixable,
            "user_feedback": self.user_feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
