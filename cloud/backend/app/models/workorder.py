"""
工单模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, JSON, Float, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base

class WorkOrderType(str, enum.Enum):
    PREVENTIVE = "preventive"  # 预防性维护
    EMERGENCY = "emergency"    # 紧急故障
    PLAN = "plan"             # 计划性维护
    MAINTENANCE = "maintenance"  # 维修保养
    INSPECTION = "inspection"    # 巡检
    UPGRADE = "upgrade"          # 升级改造
    REPAIR = "repair"         # 报修

class WorkOrderLevel(str, enum.Enum):
    INFO = "info"         # 提示
    WARNING = "warning"   # 警告
    CRITICAL = "critical"
    P0 = "P0"
    P1 = "P1"
    P2 = "P2" # 严重

class WorkOrderStatus(str, enum.Enum):
    PENDING = "pending"        # 待处理
    ACCEPTED = "accepted"      # 已接单
    PROCESSING = "processing"  # 处理中
    PENDING_VERIFY = "pending_verify"  # 待验收
    COMPLETED = "completed"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"    # 已完成

class WorkOrder(Base):
    """工单表"""
    __tablename__ = "work_orders"
    
    id = Column(String(50), primary_key=True)  # 工单号 WO-20260403-001
    type = Column(SQLEnum(WorkOrderType, values_callable=lambda x: [m.value for m in x]), default=WorkOrderType.REPAIR)
    level = Column(SQLEnum(WorkOrderLevel, values_callable=lambda x: [m.value for m in x]), default=WorkOrderLevel.INFO)
    
    # 关联
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), index=True)
    assignee_id = Column(Integer, ForeignKey("users.id"), index=True)  # 指派工程师
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 创建人(系统自动创建时为 NULL, 卡片 1236b769)
    
    # 状态
    status = Column(SQLEnum(WorkOrderStatus, values_callable=lambda x: [m.value for m in x]), default=WorkOrderStatus.PENDING)

    # 派发与来源 (maint-platform-spec §4)
    dispatch_type = Column(String(20), default="assign", nullable=False)  # assign=指派 / grab=抢单
    source = Column(String(20), default="manual", nullable=False)  # manual/alarm/app/inspection

    # 内容
    fault_desc = Column(Text)  # 故障描述
    solution = Column(Text)  # 解决方案
    attachments = Column(JSON)  # 附件 (照片/视频)
    
    # 时间
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    accept_time = Column(DateTime(timezone=True))
    finish_time = Column(DateTime(timezone=True))
    verify_time = Column(DateTime(timezone=True))
    verifier_id = Column(Integer, ForeignKey("users.id"), index=True)  # 验收人(maint-spec §2.2 站长确认)
    
    # 关系
    device = relationship("Device", back_populates="workorders")
    station = relationship("Station", back_populates="workorders")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_workorders")
    creator = relationship("User", foreign_keys=[creator_id], back_populates="created_workorders")
    logs = relationship("WorkOrderLog", back_populates="workorder", cascade="all, delete-orphan")

class WorkOrderLog(Base):
    """工单日志表"""
    __tablename__ = "work_order_logs"
    
    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    order_id = Column(String(50), ForeignKey("work_orders.id"), nullable=False, index=True)
    action = Column(String(50))  # created/assigned/accepted/started/completed
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    description = Column(Text)
    attachments = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    workorder = relationship("WorkOrder", back_populates="logs")


class WorkOrderCheckin(Base):
    """工单签到表 — 到场签到（GPS + 照片）"""
    __tablename__ = "work_order_checkins"

    id = Column(BigInteger, primary_key=True, index=True)
    order_id = Column(String(50), ForeignKey("work_orders.id"), nullable=False, index=True)
    latitude = Column(Float)                       # 纬度
    longitude = Column(Float)                      # 经度
    address = Column(String(255))                  # 签到地址
    note = Column(Text)                            # 备注
    photo_url = Column(String(500))                # 签到照片URL
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class WorkOrderSupportRequest(Base):
    """工单支援请求表 — 申请远程协助 / 高级工程师协助"""
    __tablename__ = "work_order_support_requests"

    id = Column(BigInteger, primary_key=True, index=True)
    order_id = Column(String(50), ForeignKey("work_orders.id"), nullable=False, index=True)
    target_engineer_id = Column(Integer, ForeignKey("users.id"), index=True)  # 指定协助工程师（可空=任意）
    reason = Column(Text, nullable=False)          # 支援原因
    remote = Column(Boolean, default=False)        # 是否远程协助
    status = Column(String(20), default="pending") # pending/approved/resolved
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class WorkOrderSparePart(Base):
    """工单备件申请表 — 申请/记录备件"""
    __tablename__ = "work_order_spare_parts"

    id = Column(BigInteger, primary_key=True, index=True)
    order_id = Column(String(50), ForeignKey("work_orders.id"), nullable=False, index=True)
    part_name = Column(String(100), nullable=False)  # 备件名称
    part_model = Column(String(100))                  # 备件型号
    quantity = Column(Integer, nullable=False, default=1)  # 数量
    reason = Column(Text)                             # 申请说明
    status = Column(String(20), default="requested")  # requested/approved/used/cancelled
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class WorkOrderRating(Base):
    """工单评价表 — 三维星级评价（响应速度/维修质量/服务态度）"""
    __tablename__ = "work_order_ratings"

    id = Column(BigInteger, primary_key=True, index=True)
    order_id = Column(String(50), ForeignKey("work_orders.id"), nullable=False, index=True, unique=True)
    response_rating = Column(Integer, nullable=False)   # 响应速度 1-5
    quality_rating = Column(Integer, nullable=False)    # 维修质量 1-5
    attitude_rating = Column(Integer, nullable=False)   # 服务态度 1-5
    comment = Column(Text)                              # 评语
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # 评价人
    verifier_id = Column(Integer, ForeignKey("users.id"), index=True)  # 验收人(站长,与评价人可能不同)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
