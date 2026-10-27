"""
审计日志模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
import enum
from app.core.database import Base


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    DISPATCH = "dispatch"
    CONFIG = "config"
    OTHER = "other"


class AuditModule(str, enum.Enum):
    AUTH = "auth"
    USERS = "users"
    STATIONS = "stations"
    DEVICES = "devices"
    ALARMS = "alarms"
    WORKORDERS = "workorders"
    KNOWLEDGE = "knowledge"
    REPORTS = "reports"
    CONFIG = "config"
    GATEWAYS = "gateways"
    RBAC = "rbac"


class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # 操作者
    user_id = Column(Integer, index=True, nullable=True)
    username = Column(String(50), index=True)
    user_role = Column(String(20), nullable=True)
    
    # 操作内容
    action = Column(String(20), index=True)  # login/create/update/delete/export
    module = Column(String(30), index=True)  # auth/devices/alarms/workorders
    target_id = Column(String(50), nullable=True)  # 操作目标ID
    target_desc = Column(String(200), nullable=True)  # 操作目标描述
    
    # 详情
    detail = Column(Text, nullable=True)  # 详细描述
    old_value = Column(Text, nullable=True)  # 变更前（可选）
    new_value = Column(Text, nullable=True)  # 变更后（可选）
    
    # 请求信息
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(200), nullable=True)
    result = Column(String(10), default="success")  # success/failure
    error_msg = Column(Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'user_id': self.user_id,
            'username': self.username,
            'user_role': self.user_role,
            'action': self.action,
            'module': self.module,
            'target_id': self.target_id,
            'target_desc': self.target_desc,
            'detail': self.detail,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'result': self.result,
            'error_msg': self.error_msg,
        }
