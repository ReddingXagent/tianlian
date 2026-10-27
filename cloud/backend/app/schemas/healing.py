"""
告警自愈引擎 API 请求模型

任务卡 7011daeb：将 healing.py 路由的 `data: dict` 替换为 Pydantic BaseModel，
提供类型校验与 OpenAPI 字段文档。

设计要点：
- 字段全部 Optional（默认 None）以精确复刻原 dict 语义。路由层调用
  model_dump(exclude_unset=True)，未传字段不出现在结果 dict 中，由
  healing_engine 内部 .get(key, default) 回填默认值，与改造前行为完全一致。
- 业务必填约束（name / alarm_pattern）保留在路由层手动校验，返回业务级
  error_response(code=400) 而非 Pydantic 422，与既有测试契约一致
  (test_create_healing_rule_missing_name 期望 code==400)。
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class HealingRuleCreateRequest(BaseModel):
    """创建自愈规则请求"""
    name: Optional[str] = Field(None, description="规则名称（业务必填，缺失返回 400）")
    description: Optional[str] = Field(None, description="规则描述")
    alarm_pattern: Optional[Dict[str, Any]] = Field(None, description="告警匹配条件（业务必填，缺失返回 400）")
    runbook_template: Optional[str] = Field(None, description="关联的 Runbook 模板名称")
    auto_approve: Optional[bool] = Field(None, description="是否自动审批")
    max_retries: Optional[int] = Field(None, ge=0, description="最大重试次数")
    cooldown_minutes: Optional[int] = Field(None, ge=0, description="冷却时间（分钟）")
    priority: Optional[int] = Field(None, description="优先级（数值越小越高）")
    enabled: Optional[bool] = Field(None, description="是否启用")


class HealingRuleUpdateRequest(BaseModel):
    """更新自愈规则请求（所有字段可选，仅更新传入字段）"""
    name: Optional[str] = Field(None, description="规则名称")
    description: Optional[str] = Field(None, description="规则描述")
    alarm_pattern: Optional[Dict[str, Any]] = Field(None, description="告警匹配条件")
    runbook_template: Optional[str] = Field(None, description="关联的 Runbook 模板名称")
    auto_approve: Optional[bool] = Field(None, description="是否自动审批")
    max_retries: Optional[int] = Field(None, ge=0, description="最大重试次数")
    cooldown_minutes: Optional[int] = Field(None, ge=0, description="冷却时间（分钟）")
    priority: Optional[int] = Field(None, description="优先级（数值越小越高）")
    enabled: Optional[bool] = Field(None, description="是否启用")


class HealingExecutionRejectRequest(BaseModel):
    """拒绝自愈执行请求"""
    reason: str = Field("", description="拒绝原因")
