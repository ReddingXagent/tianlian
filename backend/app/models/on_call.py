# -*- coding: utf-8 -*-
"""
值班排班 & On-Call 轮换模型 — Phase9

功能:
- On-Call 排班表 (按周/月自动轮换)
- 值班规则 (班次类型、人员顺序、通知方式)
- 值班日志 & 交接记录
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class OnCallRule(Base):
    """值班规则表 — 定义如何轮换"""
    __tablename__ = "on_call_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="规则名称 (如: 一线工程师轮值)")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True, comment="所属团队")
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=True, index=True, comment="适用站点 (NULL=全局)")
    schedule_type = Column(
        String(32), default="weekly", comment="轮换类型: daily|weekly|monthly|custom"
    )
    rotation_order = Column(JSON, nullable=False, comment="轮换顺序 (用户ID列表)")
    shift_duration_hours = Column(Integer, default=168, comment="每班时长(小时), 默认168=1周")
    overlap_minutes = Column(Integer, default=30, comment="交接班重叠分钟数")
    escalation_level = Column(Integer, default=2, comment="升级级别数")
    escalation_timeout_minutes = Column(Integer, default=30, comment="升级超时(分钟)")
    notify_methods = Column(JSON, default=lambda: ["app", "sms"], comment="通知方式列表")
    auto_assign_workorders = Column(Boolean, default=True, comment="自动将告警工单分配给当班人")
    enabled = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关系
    shifts = relationship("OnCallShift", back_populates="rule", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<OnCallRule name={self.name} type={self.schedule_type}>"


class OnCallShift(Base):
    """值班班次表 — 具体谁什么时候值班"""
    __tablename__ = "on_call_shifts"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("on_call_rules.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="值班人员")
    backup_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="备份/二级值班人")
    start_time = Column(DateTime, nullable=False, index=True, comment="班次开始时间")
    end_time = Column(DateTime, nullable=False, comment="班次结束时间")
    status = Column(
        String(32), default="scheduled",
        comment="状态: scheduled|active|completed|cancelled|missed"
    )
    handover_notes = Column(Text, nullable=True, comment="交接班备注")
    handover_completed = Column(Boolean, default=False, comment="交接是否完成")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关系
    rule = relationship("OnCallRule", back_populates="shifts")

    def __repr__(self):
        return f"<OnCallShift user={self.user_id} {self.start_time}→{self.end_time}>"


class OnCallLog(Base):
    """值班日志表"""
    __tablename__ = "on_call_logs"

    id = Column(Integer, primary_key=True, index=True)
    shift_id = Column(Integer, ForeignKey("on_call_shifts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="记录人")
    event_type = Column(
        String(32), default="note",
        comment="事件类型: note|alarm|workorder|handover|escalation|incident"
    )
    content = Column(Text, nullable=False, comment="日志内容")
    alarm_id = Column(Integer, ForeignKey("alarms.id"), nullable=True, index=True, comment="关联告警")
    workorder_id = Column(String(50), nullable=True, comment="关联工单号")
    severity = Column(String(32), default="info", comment="严重级别: info|warning|critical")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<OnCallLog shift={self.shift_id} type={self.event_type}>"
