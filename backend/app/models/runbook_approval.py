"""
Runbook审批流模型

当Runbook步骤的风险等级为MEDIUM/HIGH/CRITICAL时，
需要经过人工审批才能执行。审批流支持多级审批。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class RunbookApproval(Base):
    """Runbook审批记录"""
    __tablename__ = "runbook_approvals"

    id = Column(Integer, primary_key=True, index=True)
    runbook_id = Column(String(64), index=True, comment="关联Runbook执行ID")
    alarm_id = Column(Integer, index=True, comment="关联告警ID")
    
    # 审批内容
    step_index = Column(Integer, comment="等待审批的步骤索引(JSON中)")
    step_description = Column(String(500), comment="步骤描述")
    action_type = Column(String(50), comment="动作类型")
    command_preview = Column(Text, comment="将执行的命令预览")
    risk_level = Column(String(20), comment="风险等级: medium/high/critical")
    rollback_preview = Column(Text, nullable=True, comment="回滚命令预览")
    
    # 审批状态
    status = Column(String(20), default="pending", comment="审批状态: pending/approved/rejected/expired")
    required_level = Column(String(20), default="operator", comment="所需审批人级别: operator/manager/admin")
    
    # 审批人
    approver_id = Column(Integer, nullable=True, comment="审批人ID")
    approver_name = Column(String(100), nullable=True, comment="审批人姓名")
    approved_at = Column(DateTime, nullable=True, comment="审批时间")
    reject_reason = Column(Text, nullable=True, comment="拒绝原因")
    
    # 自动执行相关
    auto_execute_after_approval = Column(Boolean, default=True, comment="审批通过后是否自动执行")
    executed_after_approval = Column(Boolean, default=False, comment="审批后是否已执行")
    
    # 超时
    expires_at = Column(DateTime, nullable=True, comment="审批超时时间(默认30分钟)")
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RunbookApprovalLog(Base):
    """审批操作日志"""
    __tablename__ = "runbook_approval_logs"

    id = Column(Integer, primary_key=True, index=True)
    approval_id = Column(Integer, index=True, comment="关联审批ID")
    action = Column(String(20), comment="操作: approve/reject/expire/escalate")
    operator_id = Column(Integer, comment="操作人ID")
    operator_name = Column(String(100), comment="操作人姓名")
    comment = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime, server_default=func.now())
