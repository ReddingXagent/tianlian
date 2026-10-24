"""
租户品牌模型 - 多租户动态品牌 (工作卡 28546b66)

契约: backend/docs/contracts/user-client-contract.md §1 (场站响应 + branding)

设计:
- 每租户一条品牌 (tenant_id 唯一)；场站经 station.tenant_id 解析品牌。
- team_id 为运营归属，供 ops CRUD team scoping (与 Station/SupervisionConfig 同模式)；
  admin/平台级豁免 team 过滤。
- 未配置品牌的租户 → 端侧拿到「天链默认品牌」(source=default)，见
  app/services/tenant_brand_service.py，所有字段非 null，端侧无需判空。
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from datetime import datetime, timezone

from app.core.database import Base


class TenantBrand(Base):
    """租户品牌表 - 每租户一条动态品牌配置"""
    __tablename__ = "tenant_brands"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True,
        comment="所属租户 (唯一，一租户一品牌)",
    )
    team_id = Column(
        Integer, ForeignKey("teams.id"), nullable=True, index=True,
        comment="运营归属团队，用于 ops CRUD team scoping",
    )

    # 品牌展示字段 (契约 §1.1 branding)
    operator_name = Column(String(100), nullable=False, comment="运营商展示名称")
    logo_url = Column(String(500), nullable=False, default="", comment="logo 绝对 URL")
    service_phone = Column(String(50), nullable=False, default="", comment="客服电话")
    theme_color = Column(String(20), nullable=False, default="#00A86B", comment="主题色 hex")

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_tenant_brand_team", "team_id"),
    )
