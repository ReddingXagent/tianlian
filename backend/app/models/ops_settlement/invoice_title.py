"""
发票抬头模型 - SPEC §2.5 + §4

个人/企业发票抬头管理。
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SAEnum, Index
import enum

from app.core.database import Base


class TitleType(str, enum.Enum):
    """抬头类型: personal(个人) / enterprise(企业)"""
    PERSONAL = "personal"
    ENTERPRISE = "enterprise"


class InvoiceTitle(Base):
    """发票抬头表"""
    __tablename__ = "invoice_titles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True, comment="关联用户ID (NULL=运营公用)")
    title_type = Column(SAEnum(TitleType), default=TitleType.PERSONAL, comment="抬头类型")
    title_name = Column(String(200), nullable=False, comment="抬头名称")
    tax_id = Column(String(50), nullable=True, comment="纳税人识别号")
    register_address = Column(String(500), nullable=True, comment="注册地址")
    register_phone = Column(String(20), nullable=True, comment="注册电话")
    bank_name = Column(String(200), nullable=True, comment="开户银行")
    bank_account = Column(String(50), nullable=True, comment="银行账号")
    email = Column(String(100), nullable=True, comment="接收邮箱")
    is_default = Column(Boolean, default=False, comment="是否默认抬头")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_it_user", "user_id"),
        Index("idx_it_type", "title_type"),
    )
