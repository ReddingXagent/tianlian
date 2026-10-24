"""
API 密钥管理模型

功能:
- 客户端 API 密钥生成与管理
- 密钥权限控制 (scope-based)
- 密钥使用统计与限流
- 密钥轮换与过期
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import secrets
import hashlib

from app.core.database import Base


def generate_api_key():
    """生成安全的 API Key"""
    return "tl_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """哈希 API Key (存储用)"""
    return hashlib.sha256(key.encode()).hexdigest()


class ApiKey(Base):
    """API 密钥表"""
    __tablename__ = "api_keys"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 密钥信息
    key_hash = Column(String(64), unique=True, index=True, nullable=False, comment="密钥哈希")
    key_prefix = Column(String(10), nullable=False, comment="密钥前缀(用于识别)")
    
    # 归属
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # 名称和描述
    name = Column(String(100), nullable=False, comment="密钥名称")
    description = Column(Text, nullable=True, comment="描述")
    
    # 权限范围 (JSON: ["read:devices", "write:alarms", "admin:stations"])
    scopes = Column(JSON, default=list, comment="权限范围")
    
    # IP 白名单 (JSON: ["192.168.1.0/24", "10.0.0.0/8"])
    ip_whitelist = Column(JSON, nullable=True, comment="IP白名单")
    
    # 限流配置
    rate_limit = Column(Integer, default=1000, comment="每分钟请求限制")
    
    # 状态
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_revoked = Column(Boolean, default=False, comment="是否已撤销")
    revoked_reason = Column(Text, nullable=True, comment="撤销原因")
    revoked_at = Column(DateTime, nullable=True, comment="撤销时间")
    
    # 时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    last_used_at = Column(DateTime, nullable=True, comment="最后使用时间")
    
    # 关系
    tenant = relationship("Tenant")
    user = relationship("User")
    usage_logs = relationship("ApiKeyUsageLog", back_populates="api_key", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_api_key_tenant', 'tenant_id'),
        Index('idx_api_key_user', 'user_id'),
        Index('idx_api_key_active', 'is_active', 'is_revoked'),
    )
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        # DB(DateTime 无 tz) 读出的 expires_at 为 naive，按系统约定(UTC)补 tz 后再与 aware now 比较，
        # 否则 offset-naive vs offset-aware 比较 → TypeError（utcnow→now(timezone.utc) 重构残留）。
        expires_at = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at
    
    def is_valid(self) -> bool:
        """检查密钥是否有效"""
        return self.is_active and not self.is_revoked and not self.is_expired()
    
    def check_scope(self, required_scope: str) -> bool:
        """检查是否有指定权限"""
        if not self.scopes:
            return False
        # 支持通配符: "admin:*" 匹配 "admin:devices"
        for scope in self.scopes:
            if scope == required_scope:
                return True
            if scope.endswith("*") and required_scope.startswith(scope[:-1]):
                return True
            # admin 拥有所有权限
            if scope == "admin":
                return True
        return False


class ApiKeyUsageLog(Base):
    """API 密钥使用日志"""
    __tablename__ = "api_key_usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=False, index=True)
    
    # 请求信息
    method = Column(String(10), nullable=False, comment="HTTP方法")
    path = Column(String(500), nullable=False, comment="请求路径")
    status_code = Column(Integer, nullable=True, comment="状态码")
    
    # 客户端信息
    ip_address = Column(String(50), nullable=True, comment="IP地址")
    user_agent = Column(Text, nullable=True, comment="User-Agent")
    
    # 性能
    duration_ms = Column(Integer, nullable=True, comment="响应时间ms")
    
    # 时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # 关系
    api_key = relationship("ApiKey", back_populates="usage_logs")
    
    __table_args__ = (
        Index('idx_api_usage_key', 'api_key_id'),
        Index('idx_api_usage_created', 'created_at'),
        Index('idx_api_usage_path', 'path'),
    )


class ClientCertificate(Base):
    """客户端证书表 (mTLS)"""
    __tablename__ = "client_certificates"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 证书信息
    cert_serial = Column(String(64), unique=True, index=True, nullable=False, comment="证书序列号")
    cert_fingerprint = Column(String(64), unique=True, nullable=False, comment="证书指纹")
    cert_subject = Column(Text, nullable=False, comment="证书主题")
    cert_issuer = Column(Text, nullable=False, comment="证书颁发者")
    cert_pem = Column(Text, nullable=False, comment="证书PEM")
    
    # 归属
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    
    # 名称
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # 状态
    is_active = Column(Boolean, default=True)
    is_revoked = Column(Boolean, default=False)
    revoked_reason = Column(Text, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    
    # 有效期
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    
    # 时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_client_cert_tenant', 'tenant_id'),
        Index('idx_client_cert_device', 'device_id'),
        Index('idx_client_cert_active', 'is_active', 'is_revoked'),
        Index('idx_client_cert_valid', 'valid_until'),
    )
    
    def is_expired(self) -> bool:
        """检查证书是否过期"""
        # 同 ApiKey.is_expired: DB 读出的 valid_until 为 naive，补 UTC tz 后再比较，
        # 否则 offset-naive vs offset-aware 比较 → TypeError。
        valid_until = self.valid_until if self.valid_until.tzinfo else self.valid_until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > valid_until
    
    def is_valid(self) -> bool:
        """检查证书是否有效"""
        return self.is_active and not self.is_revoked and not self.is_expired()
