# -*- coding: utf-8 -*-
"""SSL证书 & 域名管理模型 — Phase9"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.core.database import Base


class SSLCertificate(Base):
    """SSL 证书跟踪表"""
    __tablename__ = "ssl_certificates"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), unique=True, nullable=False, index=True, comment="域名/IP")
    email = Column(String(255), nullable=False, default="admin@tianlian.com", comment="Let's Encrypt 通知邮箱")
    cert_path = Column(String(512), nullable=True, comment="证书完整路径")
    key_path = Column(String(512), nullable=True, comment="私钥路径")
    issuer = Column(String(255), nullable=True, comment="签发机构")
    serial_number = Column(String(128), nullable=True, comment="证书序列号")
    not_before = Column(DateTime, nullable=True, comment="生效时间")
    not_after = Column(DateTime, nullable=True, comment="过期时间")
    subject_alt_names = Column(Text, nullable=True, comment="SAN 列表 (JSON数组)")
    auto_renew = Column(Boolean, default=True, comment="是否自动续期")
    renew_days_before = Column(Integer, default=30, comment="提前多少天续期")
    status = Column(
        String(32), default="pending", comment="状态: pending|active|expiring_soon|expired|error"
    )
    last_renew_at = Column(DateTime, nullable=True, comment="上次续期时间")
    last_renew_success = Column(Boolean, nullable=True, comment="上次续期是否成功")
    last_renew_error = Column(Text, nullable=True, comment="上次续期错误信息")
    last_check_at = Column(DateTime, nullable=True, comment="上次状态检查时间")
    nginx_conf_path = Column(String(512), nullable=True, comment="Nginx 配置文件路径")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间",
    )

    def __repr__(self):
        return f"<SSLCertificate domain={self.domain} status={self.status}>"

    @property
    def days_remaining(self) -> 'int | None':
        """剩余天数"""
        if self.not_after:
            naive = self.not_after.replace(tzinfo=None) if self.not_after.tzinfo else self.not_after
            return (naive - datetime.now(timezone.utc).replace(tzinfo=None)).days
        return None

    @property
    def needs_renewal(self) -> bool:
        """是否需要续期"""
        if not self.auto_renew:
            return False
        remaining = self.days_remaining
        if remaining is None:
            return True  # 没有过期时间，认为需要续期
        return remaining <= self.renew_days_before
