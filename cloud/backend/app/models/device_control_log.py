from typing import Dict, Any

from sqlalchemy import Column, BigInteger, String, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceControlLog(Base):
    __tablename__ = "device_control_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    device_id = Column(BigInteger, ForeignKey("devices.id"), nullable=False, index=True)

    # 关系
    device = relationship("Device", back_populates="control_logs")
    device_name = Column(String(200))
    action = Column(String(50), nullable=False, index=True)  # start, stop, restart, set_param, emergency_stop
    parameter = Column(String(200), nullable=True)  # 参数名（set_param 时用）
    value = Column(Text, nullable=True)  # 参数值
    params = Column(JSON, nullable=True)  # 完整参数设置 JSON
    result = Column(String(50), default="pending", nullable=False)  # pending, success, failed
    message = Column(Text, nullable=True)  # 结果消息/错误信息
    operator = Column(String(100), nullable=True)  # 操作人
    operator_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "action": self.action,
            "parameter": self.parameter,
            "value": self.value,
            "params": self.params,
            "result": self.result,
            "message": self.message,
            "operator": self.operator,
            "operator_id": self.operator_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
