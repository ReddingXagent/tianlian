"""
自愈执行记录模型

记录每次自愈规则触发的完整过程：
触发条件 → 匹配规则 → Runbook执行 → 步骤结果 → 最终状态
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class HealingExecution(Base):
    """自愈执行记录表"""
    __tablename__ = "healing_executions"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, index=True, comment="关联自愈规则ID")
    rule_name = Column(String(100), comment="快照：规则名称")
    alarm_id = Column(Integer, index=True, comment="触发告警ID")
    device_id = Column(Integer, index=True, comment="设备ID")
    station_id = Column(Integer, index=True, comment="站点ID")

    # Runbook信息
    runbook_id = Column(String(64), nullable=True, comment="Runbook执行ID")
    runbook_template = Column(String(200), nullable=True, comment="使用的Runbook模板")
    fault_type = Column(String(200), comment="故障类型")

    # 状态
    # pending_approval: 等待人工审批
    # approved: 已审批，准备执行
    # running: 执行中
    # success: 全部成功
    # partial_success: 部分成功
    # failed: 执行失败
    # rejected: 审批被拒绝
    # timeout: 执行超时
    # cooldown: 冷却中（未触发）
    status = Column(String(20), default="pending_approval", index=True, comment="执行状态")

    # 执行步骤及结果 (JSON)
    steps = Column(JSON, comment="执行步骤详情")

    # 审批信息
    approved_by = Column(String(100), nullable=True, comment="审批人")
    approved_at = Column(DateTime, nullable=True, comment="审批时间")
    reject_reason = Column(Text, nullable=True, comment="拒绝原因")

    # 执行统计
    total_duration_ms = Column(Integer, default=0, comment="总耗时(ms)")
    success_steps = Column(Integer, default=0, comment="成功步骤数")
    failed_steps = Column(Integer, default=0, comment="失败步骤数")
    retry_count = Column(Integer, default=0, comment="已重试次数")

    result = Column(Text, nullable=True, comment="执行结果摘要")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 效果验证
    verified = Column(Boolean, default=False, comment="是否已验证效果")
    verified_at = Column(DateTime, nullable=True, comment="验证时间")
    verification_result = Column(String(20), nullable=True, comment="验证结果: healed/unhealed/partial")
    alarm_cleared = Column(Boolean, default=False, comment="告警是否已清除")

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime, nullable=True, comment="开始执行时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
