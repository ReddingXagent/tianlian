"""
故障码知识库模型 - 基于光储充设备协议分析
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Float, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base

class FaultLevel(str, enum.Enum):
    """故障等级 - 基于充电桩MQTT协议"""
    EMERGENCY = "emergency"  # 紧急故障（0x01） - 立即停机
    SERIOUS = "serious"  # 一般故障（0x02） - 可延迟处理
    WARNING_SERIOUS = "warning_serious"  # 严重告警（0x03） - 需关注但不停机
    WARNING_GENERAL = "warning_general"  # 一般告警（0x04） - 提示信息

class FaultCategory(str, enum.Enum):
    """故障分类 - 基于协议分析"""
    GRID = "grid"  # 电网侧故障（地址0-47）
    INVERTER = "inverter"  # 逆变侧故障（地址48-111）
    BATTERY = "battery"  # 电池侧故障（地址112-143）
    BUS = "bus"  # 母线侧故障（地址144-159）
    TEMPERATURE = "temperature"  # 温度故障（地址160-162）
    RELAY = "relay"  # 继电器/接触器故障（地址163-171）
    OVERLOAD = "overload"  # 过载故障（地址172-195）
    OTHER = "other"  # 其他故障（地址196-223）
    BCU_BMS = "bcu_bms"  # BCU/BMS故障（地址512-671）
    
    # 充电桩故障分类
    POWER_CONTROL = "power_control"  # 功率控制单元（0x01XX）
    CHARGING_MODULE = "charging_module"  # 充电模块（0x02XX）
    CHARGING_CONTROLLER = "charging_controller"  # 充电控制器（0x03XX）
    AC_DISTRIBUTION = "ac_distribution"  # 交流配电（0x04XX）
    DC_DISTRIBUTION = "dc_distribution"  # 直流配电（0x05XX）
    BMS_RELATED = "bms_related"  # BMS相关（0x06XX）
    ENVIRONMENT = "environment"  # 环境安全（0x07XX）
    COMMUNICATION = "communication"  # 通信模块（0x08XX）

class FaultCode(Base):
    """故障码知识库"""
    __tablename__ = "fault_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 故障码基本信息
    fault_code = Column(String(20), unique=True, nullable=False, index=True)  # 故障编码（如0x01, 0x0101）
    fault_name = Column(String(100), nullable=False)  # 故障名称
    fault_description = Column(Text)  # 故障描述
    
    # 分类
    device_type = Column(String(50), index=True)  # 适用设备类型（inverter/charger/pcs）
    fault_category = Column(SQLEnum(FaultCategory), index=True)  # 故障分类
    fault_level = Column(SQLEnum(FaultLevel), default=FaultLevel.WARNING_GENERAL)
    
    # 协议地址（逆变器Modbus）
    modbus_address = Column(Integer)  # Modbus离散量输入地址（对应0x02功能码）
    mqtt_code = Column(String(20))  # MQTT故障编码
    
    # 诊断信息
    possible_causes = Column(JSON)  # 可能原因（列表）
    diagnosis_steps = Column(JSON)  # 诊断步骤（列表）
    repair_suggestions = Column(JSON)  # 修复建议（列表）
    
    # 响应要求
    response_time_minutes = Column(Integer)  # 响应时间（分钟）
    auto_stop = Column(Boolean, default=False)  # 是否自动停机
    remote_fixable = Column(Boolean, default=False)  # 是否可远程修复
    
    # 统计
    occurrence_count = Column(Integer, default=0)  # 发生次数
    avg_repair_time_minutes = Column(Integer)  # 平均修复时间
    
    # 状态
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    repair_guides = relationship("RepairGuide", back_populates="fault_code")

class DiagnosisRule(Base):
    """诊断规则表"""
    __tablename__ = "diagnosis_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # 适用范围
    device_type = Column(String(50))  # 设备类型
    fault_category = Column(String(50))  # 故障分类
    
    # 规则逻辑（JSON格式）
    conditions = Column(JSON)  # 触发条件（如：{ "voltage": "<180", "current": ">100" }）
    priority = Column(Integer, default=1)  # 规则优先级
    
    # 诊断结果
    diagnosis_result = Column(String(200))  # 诊断结论
    repair_actions = Column(JSON)  # 修复动作列表
    
    # 状态
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class RepairGuide(Base):
    """修复指南表"""
    __tablename__ = "repair_guides"
    
    id = Column(Integer, primary_key=True, index=True)
    
    title = Column(String(200), nullable=False)
    fault_code_id = Column(Integer, ForeignKey("fault_codes.id"), index=True)
    
    # 修复内容
    symptoms = Column(JSON)  # 故障现象
    diagnosis_process = Column(JSON)  # 诊断流程（步骤列表）
    repair_steps = Column(JSON)  # 修复步骤（详细步骤）
    required_tools = Column(JSON)  # 所需工具/备件
    safety_notes = Column(JSON)  # 安全注意事项
    
    # 时间估算
    estimated_time_minutes = Column(Integer)  # 估算修复时间
    difficulty_level = Column(Integer, default=1)  # 难度等级（1-5）
    
    # 统计
    success_rate = Column(Float)  # 成功率
    usage_count = Column(Integer, default=0)  # 使用次数
    
    # 状态
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    fault_code = relationship("FaultCode", back_populates="repair_guides")