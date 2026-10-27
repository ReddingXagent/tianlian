"""
巡检运维数据模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, JSON, ForeignKey, Enum as SQLEnum, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class TaskStatus(str, enum.Enum):
    SCHEDULED = "scheduled"       # 已安排
    IN_PROGRESS = "in_progress"   # 进行中
    COMPLETED = "completed"       # 已完成
    CANCELLED = "cancelled"       # 已取消


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"     # 激活
    PAUSED = "paused"     # 暂停


class PlanCycle(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class PlanTarget(str, enum.Enum):
    ALL = "all"
    INVERTER = "inverter"
    BATTERY = "battery"
    CHARGER = "charger"
    GATEWAY = "gateway"


class InspectionTask(Base):
    """巡检任务表"""
    __tablename__ = "inspection_tasks"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    name = Column(String(200), nullable=False, comment="任务名称")
    plan_id = Column(Integer, ForeignKey("inspection_plans.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联计划ID")
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联站点ID")
    station_name = Column(String(200), nullable=True, comment="站点名称")
    assignee = Column(String(100), nullable=True, comment="负责人")
    assignee_id = Column(Integer, nullable=True, comment="负责人用户ID")
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.SCHEDULED, comment="任务状态")
    total_items = Column(Integer, default=0, comment="检查项总数")
    completed_items = Column(Integer, default=0, comment="已完成项数")
    scheduled_date = Column(Date, nullable=True, comment="计划执行日期")
    actual_date = Column(Date, nullable=True, comment="实际执行日期")
    description = Column(Text, nullable=True, comment="任务描述")
    result = Column(JSON, nullable=True, comment="检查结果（JSON）")
    remark = Column(String(500), nullable=True, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class InspectionPlan(Base):
    """巡检计划表"""
    __tablename__ = "inspection_plans"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    name = Column(String(200), nullable=False, comment="计划名称")
    cycle = Column(SQLEnum(PlanCycle), nullable=False, comment="执行周期")
    target = Column(SQLEnum(PlanTarget), default=PlanTarget.ALL, comment="巡检对象")
    assignee = Column(String(100), nullable=True, comment="负责人")
    assignee_id = Column(Integer, nullable=True, comment="负责人用户ID")
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True, comment="所属团队")
    status = Column(SQLEnum(PlanStatus), default=PlanStatus.ACTIVE, comment="计划状态")
    next_execute = Column(Date, nullable=True, comment="下次执行日期")
    last_execute = Column(Date, nullable=True, comment="上次执行日期")
    description = Column(Text, nullable=True, comment="计划描述")
    config = Column(JSON, nullable=True, comment="检查项配置（JSON）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关联
    tasks = relationship("InspectionTask", backref="plan", lazy="select")


# 巡检模板状态与结果状态用 String 存储（避免 SQLEnum name/value 存储坑），
# 业务层在 {active,inactive} / {normal,abnormal} 范围内校验。
TEMPLATE_STATUS_VALUES = ("active", "inactive")
RESULT_STATUS_VALUES = ("normal", "abnormal")


class InspectionTemplate(Base):
    """巡检模板表（spec 2.5）

    items: 巡检项列表 [{name, type, standard_value, unit}]（前端只填 name/unit/standard_value，
           透传存储，缺字段不影响）
    device_types: 适用设备类型列表（spec 字段）；前端用单选 target，API 层桥接 target↔device_types
    status: active/inactive
    """
    __tablename__ = "inspection_templates"

    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="模板名称")
    description = Column(Text, nullable=True, comment="模板描述")
    items = Column(JSON, nullable=True, comment="巡检项列表（JSON）")
    device_types = Column(JSON, nullable=True, comment="适用设备类型列表（JSON）")
    status = Column(String(20), default="active", nullable=False, comment="状态 active/inactive")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class InspectionResult(Base):
    """巡检结果表（spec 2.5，按任务录入）

    item_value: 实测值（前端字段名为 value，API 层桥接 value↔item_value）
    result: normal/abnormal
    """
    __tablename__ = "inspection_results"

    id = Column(BigInteger, primary_key=True, index=True)
    task_id = Column(BigInteger, ForeignKey("inspection_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="关联任务ID")
    item_name = Column(String(200), nullable=False, comment="检查项名称")
    item_value = Column(String(500), nullable=True, comment="实测值")
    result = Column(String(20), default="normal", nullable=False, comment="结果 normal/abnormal")
    abnormal_desc = Column(Text, nullable=True, comment="异常描述")
    photo_url = Column(String(500), nullable=True, comment="照片URL")
    recorded_at = Column(DateTime, nullable=True, comment="记录时间")