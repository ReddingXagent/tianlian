"""平台服务费配置模型 (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §4 (平台服务费预留, 暂不启用)

设计:
- 本期仅落数据结构 + 管理端 CRUD, 不接真实IM-B分账 (profitsharing)。
- enabled 默认 false → 端侧与支付流程零感知, prepay 响应不体现抽佣。
- rate_bp 基点 (1bp = 0.01%), IM-B分账比例上限 30% → rate_bp ≤ 3000。
- scope: all (租户全员) / whitelist (仅 user_ids 白名单)。
- team_id 供 ops team scoping; tenant_id 标识归属租户 (平台级可为 null)。
- 真实分账: 支付成功回调后, 以天链服务商号为分账接收方发起 profitsharing。
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
    Enum as SAEnum,
    Index,
)

from app.core.database import Base


def _enum_values(ec):
    return [m.value for m in ec]


class FeeScope(str, enum.Enum):
    """计费范围"""

    ALL = "all"            # 租户全员
    WHITELIST = "whitelist"  # 仅白名单用户


class PlatformFeeConfig(Base):
    """平台服务费配置表 (分账预留)"""
    __tablename__ = "platform_fee_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True, comment="归属租户 (平台级可为 null)")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="运营归属团队 (ops team scoping)")

    enabled = Column(Boolean, nullable=False, default=False, comment="是否启用平台服务费 (本期固定 false)")
    rate_bp = Column(Integer, nullable=False, default=0, comment="费率 (基点, 上限 3000=30%)")
    scope = Column(
        SAEnum(FeeScope, values_callable=_enum_values),
        nullable=False,
        default=FeeScope.ALL,
        comment="计费范围: all/whitelist",
    )
    user_ids = Column(JSON, nullable=True, comment="白名单用户 id 列表 (scope=whitelist 时生效)")

    note = Column(String(200), nullable=True, comment="备注")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_fee_config_team", "team_id"),
        Index("idx_fee_config_tenant", "tenant_id"),
    )
