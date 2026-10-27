"""
告警自愈规则模型

自愈规则定义：当告警满足特定条件时，自动触发关联的Runbook进行修复。
低风险操作可自动审批执行，高风险操作需人工确认。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class HealingRule(Base):
    """自愈规则表"""
    __tablename__ = "healing_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="规则名称")
    description = Column(Text, nullable=True, comment="规则描述")

    # 告警匹配条件 (JSON)
    # 示例: {"alarm_levels": ["critical", "warning"], "alarm_types": ["逆变器通讯中断"], "device_types": ["inverter"], "device_ids": [1,2,3], "station_ids": [1]}
    alarm_pattern = Column(JSON, nullable=False, comment="告警匹配条件")

    # 关联Runbook
    runbook_template = Column(String(200), nullable=True, comment="关联Runbook模板名称")
    # 如果不指定模板名称，则使用fault_type自动匹配

    # 执行策略
    auto_approve = Column(Boolean, default=False, comment="是否自动审批（仅对低风险步骤生效）")
    max_retries = Column(Integer, default=1, comment="最大重试次数")
    cooldown_minutes = Column(Integer, default=30, comment="冷却时间（分钟），防止同一规则频繁触发")

    # 优先级与状态
    priority = Column(Integer, default=0, comment="优先级，数值越大越优先")
    enabled = Column(Boolean, default=True, comment="是否启用")

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
