"""
Runbook 模板持久化模型 (spec maint-platform §2.6)

将原硬编码在 app.services.runbook_engine.RunbookTemplate.TEMPLATES 的模板
迁移为 DB CRUD, 支持运维人员通过 UI 创建/编辑/删除。
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, JSON, Text
from sqlalchemy.sql import func

from app.core.database import Base


# 状态取值用 String 存储 (避免 SQLEnum name/value 存储坑), 业务层校验
TEMPLATE_STATUS_VALUES = ("active", "inactive")


class RunbookTemplateModel(Base):
    """Runbook 模板表

    name:       模板显示名 (唯一)
    category:   设备类别 (inverter/charger/pcs/bms/ems/ess/general)
    alarm_type: 告警匹配键, 执行引擎据此匹配诊断 fault_type; 默认=name
    steps:      执行步骤列表 JSON [{step_id, action_type, description, command,
                params, risk_level, timeout_sec, rollback_command, pre_check,
                post_check, auto_execute}]
    status:     active/inactive (inactive 不参与执行匹配)
    version:    版本号, 每次更新 +1
    """
    __tablename__ = "runbooks"

    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, comment="模板名称")
    category = Column(String(50), nullable=False, default="general", comment="设备类别")
    alarm_type = Column(String(200), nullable=False, comment="告警匹配键")
    description = Column(Text, nullable=True, comment="模板描述")
    steps = Column(JSON, nullable=True, comment="执行步骤列表(JSON)")
    status = Column(String(20), nullable=False, default="active", comment="状态 active/inactive")
    version = Column(Integer, nullable=False, default=1, comment="版本号")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


def seed_builtin_runbook_templates(session) -> int:
    """将内置 RunbookTemplate.TEMPLATES 种子化到 DB。

    幂等: 按 name 去重, 已存在的跳过。返回新插入条数。
    """
    from dataclasses import asdict
    from app.services.runbook_engine import RunbookTemplate

    existing = {r.name for r in session.query(RunbookTemplateModel).all()}
    new_rows = []
    for name, tmpl in RunbookTemplate.TEMPLATES.items():
        if name in existing:
            continue
        steps_json = [asdict(s) for s in tmpl.get("steps", [])]
        new_rows.append(RunbookTemplateModel(
            name=name,
            category=tmpl.get("category", "general"),
            alarm_type=name,
            description=tmpl.get("description"),
            steps=steps_json,
            status="active",
            version=1,
        ))
    if new_rows:
        session.add_all(new_rows)
        session.commit()
    return len(new_rows)
