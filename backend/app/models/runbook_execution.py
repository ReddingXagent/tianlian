"""
Runbook执行记录模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class RunbookExecutionRecord(Base):
    __tablename__ = "runbook_executions"

    id = Column(Integer, primary_key=True, index=True)
    runbook_id = Column(String(64), unique=True, index=True, comment="Runbook执行ID")
    alarm_id = Column(Integer, index=True, comment="关联告警ID")
    diagnosis_record_id = Column(Integer, nullable=True, comment="关联AI诊断记录ID")
    device_id = Column(Integer, index=True, comment="关联设备ID")
    station_id = Column(Integer, index=True, comment="关联站点ID")
    fault_type = Column(String(200), comment="故障类型")
    
    status = Column(String(20), default="pending", comment="执行状态")
    steps_json = Column(JSON, comment="执行步骤详情(JSON)")
    
    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    total_duration_ms = Column(Integer, default=0, comment="总耗时(ms)")
    
    success_steps = Column(Integer, default=0)
    failed_steps = Column(Integer, default=0)
    skipped_steps = Column(Integer, default=0)
    auto_executed = Column(Integer, default=0, comment="自动执行步骤数")
    manual_required = Column(Integer, default=0, comment="需人工步骤数")
    
    workorder_id = Column(Integer, nullable=True, comment="自动创建的工单ID")
    error_message = Column(Text, comment="错误信息")
    
    created_at = Column(DateTime, server_default=func.now())
