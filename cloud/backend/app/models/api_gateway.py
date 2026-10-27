"""
API网关数据模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Float, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.core.database import Base

class ApiClient(Base):
    """API客户端模型"""
    __tablename__ = "api_clients"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String(64), unique=True, index=True, nullable=False)
    client_secret_hash = Column(String(128), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    callback_url = Column(String(500))
    scopes = Column(String(500), default="read")  # 逗号分隔的权限范围
    status = Column(String(20), default="active")  # active, suspended, revoked
    rate_limit = Column(Integer, default=1000)  # 每分钟请求限制
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), index=True)
    
    # 关系
    creator = relationship("User", foreign_keys=[created_by])
    api_keys = relationship("GatewayApiKey", back_populates="client", cascade="all, delete-orphan")

class GatewayApiKey(Base):
    """API密钥模型 (网关专用，独立于 app.models.api_key)"""
    __tablename__ = "gateway_api_keys"
    
    id = Column(Integer, primary_key=True)
    key_id = Column(String(32), unique=True, index=True, nullable=False)
    client_id = Column(Integer, ForeignKey("api_clients.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    api_key = Column(String(128), unique=True, nullable=False)
    expires_at = Column(DateTime)
    status = Column(String(20), default="active")  # active, expired, revoked
    last_used_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), index=True)
    
    # 关系
    client = relationship("ApiClient", back_populates="api_keys")
    creator = relationship("User", foreign_keys=[created_by])

class ApiEndpoint(Base):
    """API端点注册模型"""
    __tablename__ = "api_endpoints"
    
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String(500), nullable=False)
    method = Column(String(10), nullable=False)  # GET, POST, PUT, DELETE
    description = Column(Text)
    rate_limit = Column(Integer, default=1000)
    require_auth = Column(Boolean, default=True)
    status = Column(String(20), default="active")  # active, deprecated, removed
    registered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deprecated_at = Column(DateTime)
    registered_by = Column(Integer, ForeignKey("users.id"), index=True)
    
    # 索引
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class ApiRequestLog(Base):
    """API请求日志模型"""
    __tablename__ = "api_request_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(64), unique=True, index=True)
    client_id = Column(Integer, ForeignKey("api_clients.id"), index=True)
    api_key_id = Column(Integer, ForeignKey("gateway_api_keys.id"), index=True)
    endpoint = Column(String(500), nullable=False)
    method = Column(String(10), nullable=False)
    request_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    response_time = Column(Float)  # 响应时间（毫秒）
    response_status = Column(Integer)
    user_agent = Column(String(500))
    client_ip = Column(String(45))
    query_params = Column(Text)
    request_body = Column(Text)  # 注意：敏感信息需要脱敏
    response_body = Column(Text)  # 注意：敏感信息需要脱敏
    error_message = Column(Text)
    
    # 关系
    client = relationship("ApiClient")
    api_key = relationship("GatewayApiKey")

class OAuthAuthorizationCode(Base):
    """OAuth授权码模型"""
    __tablename__ = "oauth_authorization_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(128), unique=True, nullable=False)
    client_id = Column(Integer, ForeignKey("api_clients.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    redirect_uri = Column(String(500))
    scopes = Column(String(500))
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # 关系
    client = relationship("ApiClient")
    user = relationship("User")

class RateLimitRule(Base):
    """限流规则模型"""
    __tablename__ = "rate_limit_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("api_clients.id"), index=True)
    endpoint_pattern = Column(String(500))  # 端点模式匹配，如 "/api/v1/*"
    method = Column(String(10))  # GET, POST, *（所有方法）
    limit_per_minute = Column(Integer, default=1000)
    limit_per_hour = Column(Integer)
    limit_per_day = Column(Integer)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), index=True)
    
    # 关系
    client = relationship("ApiClient")
    creator = relationship("User", foreign_keys=[created_by])

class ApiUsageQuota(Base):
    """API使用配额模型"""
    __tablename__ = "api_usage_quotas"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("api_clients.id"), unique=True)
    quota_type = Column(String(50), default="standard")  # standard, premium, enterprise
    monthly_limit = Column(BigInteger, default=100000)  # 每月请求限制
    current_month_usage = Column(BigInteger, default=0)
    daily_limit = Column(Integer, default=10000)
    current_day_usage = Column(Integer, default=0)
    reset_day = Column(Integer, default=1)  # 每月重置日（1-28）
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    client = relationship("ApiClient")

class ThirdPartyIntegration(Base):
    """第三方集成配置模型"""
    __tablename__ = "third_party_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)  # im_b, alipay, dingtalk, etc.
    config_type = Column(String(50), default="oauth")  # oauth, api_key, webhook
    config_data = Column(Text)  # JSON格式的配置
    status = Column(String(20), default="active")  # active, testing, disabled
    webhook_url = Column(String(500))
    webhook_secret = Column(String(128))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), index=True)
    
    # 关系
    creator = relationship("User", foreign_keys=[created_by])