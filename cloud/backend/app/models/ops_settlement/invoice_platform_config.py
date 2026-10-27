"""
第三方开票平台配置模型 - SPEC §2.5

团队级配置: 每个运营团队管自己的开票平台（百旺/航信/诺诺）
开票时选平台或走团队默认。
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum, Index, Text
import enum

from app.core.database import Base


class PlatformType(str, enum.Enum):
    """开票平台类型"""
    BAIWANG = "baiwang"       # 百旺
    HANGXIN = "hangxin"       # 航信
    NUONUO = "nuonuo"         # 诺诺
    OTHER = "other"           # 其他


class InvoicePlatformConfig(Base):
    """第三方开票平台配置表（团队级隔离）"""
    __tablename__ = "invoice_platform_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 团队隔离
    team_id = Column(Integer, nullable=False, index=True, comment="所属团队ID")
    # 平台信息
    platform_type = Column(SAEnum(PlatformType), nullable=False, comment="平台类型(百旺/航信/诺诺)")
    platform_name = Column(String(100), nullable=False, comment="平台显示名称")
    # API 接入配置
    api_url = Column(String(500), nullable=True, comment="平台API地址")
    app_key = Column(String(200), nullable=True, comment="应用Key")
    app_secret = Column(String(500), nullable=True, comment="应用密钥")
    # OAuth / 签名配置 (电子发票自动开票)
    access_token_url = Column(String(500), nullable=True, comment="换取access_token的URL")
    private_key_enc = Column(Text, nullable=True, comment="RSA私钥(Fernet加密存储, 读取时解密)")
    device_no = Column(String(100), nullable=True, comment="设备/终端编号")
    callback_url = Column(String(500), nullable=True, comment="开票结果回调地址")
    ext_config_json = Column(Text, nullable=True, comment="平台特有扩展字段(JSON)")
    # 运行时缓存: access_token + 过期时间 (由适配器读写, 不回显明文)
    token_cache_json = Column(Text, nullable=True, comment="运行时缓存access_token+过期时间(JSON)")
    # 开票主体信息
    taxpayer_id = Column(String(50), nullable=True, comment="纳税人识别号")
    tax_classification_code = Column(String(50), nullable=True, comment="税收分类编码")
    # 状态
    is_default = Column(Boolean, default=False, comment="是否团队默认平台")
    enabled = Column(Boolean, default=True, comment="是否启用")
    remark = Column(Text, nullable=True, comment="备注")
    # 时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    __table_args__ = (
        Index("idx_ipc_team", "team_id"),
        Index("idx_ipc_team_default", "team_id", "is_default"),
        Index("idx_ipc_team_enabled", "team_id", "enabled"),
    )
