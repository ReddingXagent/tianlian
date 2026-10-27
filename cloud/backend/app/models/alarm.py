"""
告警模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, JSON, ForeignKey, Text, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class AlarmLevel(str, enum.Enum):
    INFO = "info"         # 提示
    WARNING = "warning"   # 警告
    CRITICAL = "critical" # 严重
    FATAL = "fatal"       # 致命


class AlarmStatus(str, enum.Enum):
    ACTIVE = "active"           # 活跃（未处理）
    ACKNOWLEDGED = "acknowledged"  # 已确认
    PROCESSING = "processing"  # 处理中
    RESOLVED = "resolved"      # 已解决
    PROCESSED = "processed"    # 已处理
    IGNORED = "ignored"        # 已忽略


class Alarm(Base):
    """告警表 - 扩展故障码体系"""
    __tablename__ = "alarms"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)
    station_id = Column(BigInteger, ForeignKey("stations.id"), index=True)
    rule_id = Column(Integer, ForeignKey("alarm_rules.id"), index=True)  # 触发规则的ID

    # 告警信息
    alarm_type = Column(String(50), index=True)  # 告警类型
    level = Column(SQLEnum(AlarmLevel, values_callable=lambda x: [m.value for m in x]), default=AlarmLevel.INFO)
    content = Column(Text)  # 告警内容

    # ========== 故障码体系（基于协议分析）==========
    fault_code = Column(String(20), index=True)  # 故障编码（如0x01, 0x0101）
    fault_source = Column(String(50))  # 故障源（grid/inverter/battery/charger等）
    sequence_no = Column(Integer)  # 故障流水号（MQTT协议）

    # 协议相关
    modbus_address = Column(Integer)  # Modbus离散量地址（逆变器）
    mqtt_message_type = Column(Integer)  # MQTT消息类型（如0x122006）

    # 诊断信息
    diagnosis_result = Column(Text)  # 自动诊断结果
    repair_suggestion = Column(Text)  # 修复建议
    remote_fixable = Column(Boolean, default=False)  # 是否可远程修复

    # ========== 触发时的遥测快照 ==========
    trigger_metric = Column(String(50))  # 触发指标名
    trigger_value = Column(Float)  # 触发时的值
    trigger_threshold = Column(Float)  # 触发阈值
    trigger_operator = Column(String(10))  # 触发操作符

    # ========== 告警升级（迁移新增）==========
    escalated_from = Column(String(20), nullable=True, comment='从哪个级别升级而来')  # warn→error, error→critical
    escalated_at = Column(DateTime(timezone=True), nullable=True, comment='升级时间')
    original_level = Column(String(20), nullable=True, comment='原始告警级别')

    # ========== 告警聚合（迁移新增）==========
    aggregation_count = Column(Integer, default=1, comment='聚合告警计数')
    aggregation_first_at = Column(DateTime(timezone=True), nullable=True, comment='聚合首条告警时间')
    aggregation_last_at = Column(DateTime(timezone=True), nullable=True, comment='聚合末条告警时间')

    # ========== 状态 ==========
    status = Column(SQLEnum(AlarmStatus, values_callable=lambda x: [m.value for m in x]), default=AlarmStatus.ACTIVE)
    handler_id = Column(Integer, ForeignKey("users.id"), index=True)  # 处理人
    handle_desc = Column(Text)  # 处理描述
    
    # 工单关联
    workorder_id = Column(String(50), ForeignKey("work_orders.id"), nullable=True, index=True)  # 关联工单ID

    # 远程修复尝试
    remote_fix_attempted = Column(Boolean, default=False)  # 是否尝试过远程修复
    remote_fix_result = Column(Text)  # 远程修复结果

    # ========== 时间 ==========
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())  # 更新时间
    handled_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))  # 解决时间（闭环验证通过）
    cleared_at = Column(DateTime(timezone=True))  # 故障清除时间

    # 关系
    device = relationship("Device", back_populates="alarms")
    station = relationship("Station", back_populates="alarms")
    rule = relationship("AlarmRule", back_populates="alarms")


class AlarmRule(Base):
    """告警规则表"""
    __tablename__ = "alarm_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)  # 规则描述
    device_type = Column(String(50), index=True)  # 适用设备类型（空=全部）
    device_ids = Column(JSON)  # 指定设备ID列表（空=全部）
    station_ids = Column(JSON)  # 指定站点ID列表（空=全部）

    # 规则条件
    metric = Column(String(50))  # 指标名（如 battery_temperature, grid_voltage_a）
    operator = Column(String(10))  # >/</=/>=/<=/!=/
    threshold = Column(Float)  # 阈值
    duration = Column(Integer, default=0)  # 持续秒数（0=立即触发）
    level = Column(SQLEnum(AlarmLevel, values_callable=lambda x: [m.value for m in x]), default=AlarmLevel.WARNING)

    # 告警内容模板
    alarm_template = Column(String(200))  # 如 "${metric} = ${value}, 超过阈值 ${threshold}"

    # 通知
    notify_users = Column(JSON)  # 通知用户列表
    auto_create_workorder = Column(Boolean, default=False)  # 自动创建工单
    workorder_priority = Column(String(20), default="medium")  # 工单优先级

    # 告警升级配置
    escalation_timeout_minutes = Column(Integer, default=30, comment='超时未处理自动升级的分钟数')  # 迁移新增

    # 状态
    enabled = Column(Boolean, default=True)
    silence_minutes = Column(Integer, default=0)  # 沉默时间（同一设备重复告警间隔）

    # 时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    alarms = relationship("Alarm", back_populates="rule")


class AlarmRuleLog(Base):
    """告警规则触发日志"""
    __tablename__ = "alarm_rule_logs"

    id = Column(BigInteger, primary_key=True, index=True)  # Phase1: BigInt防止溢出
    rule_id = Column(BigInteger, ForeignKey("alarm_rules.id"), nullable=False, index=True)
    rule_name = Column(String(100))  # 快照：规则名称
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    device_name = Column(String(100))  # 快照：设备名称
    station_id = Column(Integer, ForeignKey("stations.id"), index=True)

    # 触发条件
    metric = Column(String(50))
    current_value = Column(Float)
    threshold = Column(Float)
    operator = Column(String(10))

    # 结果
    triggered = Column(Boolean, default=False)  # 是否触发
    alarm_id = Column(Integer, ForeignKey("alarms.id"), index=True)  # 触发的告警ID
    reason = Column(String(200))  # 未触发原因

    # 时间
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    rule = relationship("AlarmRule")
    device = relationship("Device")
    station = relationship("Station")
    alarm = relationship("Alarm")
