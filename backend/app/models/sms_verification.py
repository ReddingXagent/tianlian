"""
短信验证码模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class SmsVerificationCode(Base):
    """短信验证码记录表"""
    __tablename__ = "sms_verification_codes"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phone = Column(String(20), nullable=False, index=True, comment="手机号")
    code = Column(String(6), nullable=False, comment="验证码")
    purpose = Column(String(20), nullable=False, default="login", comment="用途: login/register/reset")
    used = Column(Integer, default=0, comment="是否已使用: 0=未使用, 1=已使用")
    attempts = Column(Integer, default=0, nullable=False, server_default="0", comment="验证码错误尝试次数 (≥5 则失效)")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    expires_at = Column(DateTime(timezone=True), nullable=False, comment="过期时间")
    
    # 复合索引
    __table_args__ = (
        Index('ix_sms_phone_purpose_used', 'phone', 'purpose', 'used'),
        Index('ix_sms_expires_at', 'expires_at'),
    )