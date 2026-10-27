"""
多租户模型 - 支持 SaaS 模式部署

设计原则:
- 共享数据库，隔离数据 (tenant_id 字段)
- 超级管理员可管理所有租户
- 租户管理员只能访问本租户数据
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base


class Tenant(Base):
    """租户表 - 每个客户一个租户"""
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="租户名称")
    code = Column(String(50), unique=True, nullable=False, comment="租户编码")
    description = Column(Text, nullable=True, comment="描述")
    
    # 联系信息
    contact_name = Column(String(50), nullable=True, comment="联系人")
    contact_phone = Column(String(20), nullable=True, comment="联系电话")
    contact_email = Column(String(100), nullable=True, comment="联系邮箱")
    
    # 状态
    status = Column(String(20), default="active", comment="状态: active/inactive/suspended")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 配额限制
    max_stations = Column(Integer, default=10, comment="最大站点数")
    max_devices = Column(Integer, default=100, comment="最大设备数")
    max_users = Column(Integer, default=20, comment="最大用户数")
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expired_at = Column(DateTime, nullable=True, comment="过期时间")
    
    # 关系
    # users = relationship("User", back_populates="tenant")
    stations = relationship("Station", back_populates="tenant")
    
    __table_args__ = (
        Index('idx_tenant_code', 'code'),
        Index('idx_tenant_status', 'status'),
    )


class TenantConfig(Base):
    """租户配置表 - 每个租户的个性化配置"""
    __tablename__ = "tenant_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    
    # 配置项
    config_key = Column(String(100), nullable=False, comment="配置键")
    config_value = Column(Text, nullable=True, comment="配置值(JSON)")
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('idx_tenant_config', 'tenant_id', 'config_key', unique=True),
    )


class TenantAuditLog(Base):
    """租户操作审计日志"""
    __tablename__ = "tenant_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 操作信息
    action = Column(String(50), nullable=False, comment="操作类型")
    resource_type = Column(String(50), nullable=False, comment="资源类型")
    resource_id = Column(Integer, nullable=True, comment="资源ID")
    
    # 详情
    old_value = Column(Text, nullable=True, comment="旧值(JSON)")
    new_value = Column(Text, nullable=True, comment="新值(JSON)")
    ip_address = Column(String(50), nullable=True, comment="IP地址")
    user_agent = Column(Text, nullable=True, comment="User-Agent")
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('idx_tenant_audit_tenant', 'tenant_id'),
        Index('idx_tenant_audit_user', 'user_id'),
        Index('idx_tenant_audit_action', 'action'),
        Index('idx_tenant_audit_created', 'created_at'),
    )
