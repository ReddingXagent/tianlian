"""
设备通信协议 + 协议解析规则 ORM 模型 (admin-platform-spec §2.4)

- DeviceProtocol: OCPP/Modbus/MQTT/HTTP/自定义 协议定义 + 数据点映射
- ProtocolRule:   上行(parse_rule) / 下行(encode_rule) 解析编码规则

删协议时, ORM 级联删除其下规则(cascade=all, delete-orphan)。
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceProtocol(Base):
    """通信协议"""
    __tablename__ = "device_protocols"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)                # 协议名称
    code = Column(String(50), unique=True, index=True)        # 协议编码(唯一)
    type = Column(String(20), nullable=False, index=True)
    # 协议类型: ocpp / modbus / mqtt / http / custom

    version = Column(String(50))              # 协议版本(如 1.6, 2.0.1)
    protocol_definition = Column(JSON)        # 协议参数定义
    data_point_mappings = Column(JSON)        # 数据点映射

    status = Column(String(20), default="active", index=True)  # active / inactive

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联: 删除协议时级联删除其解析规则
    rules = relationship(
        "ProtocolRule",
        back_populates="protocol",
        cascade="all, delete-orphan",
    )


class ProtocolRule(Base):
    """协议解析规则"""
    __tablename__ = "protocol_rules"

    id = Column(Integer, primary_key=True, index=True)

    protocol_id = Column(
        Integer, ForeignKey("device_protocols.id"), nullable=False, index=True
    )
    direction = Column(String(20), nullable=False)   # uplink / downlink
    message_type = Column(String(100))               # 消息类型(如 MeterValues)

    parse_rule = Column(JSON)     # 上行数据解析规则
    encode_rule = Column(JSON)    # 下行指令编码规则

    status = Column(String(20), default="active")    # active / inactive

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    protocol = relationship("DeviceProtocol", back_populates="rules")
