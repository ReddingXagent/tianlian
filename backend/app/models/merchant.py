"""特约商户进件模型 - IM-B服务商模式 (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §3 (特约商户进件 + 商户状态)

设计:
- Merchant 一条记录对应一次进件申请 (business_code 唯一)，承载进件状态机
  (applyment_state 七态, 对齐IM-B applyment4sub) 与运行态 (merchant_status)。
- team_id 为运营归属，供 ops 进件端点 team scoping (与 TenantBrand/Station 同模式)；
  admin/平台级豁免 team 过滤。
- sub_mchid (特约商户号) 仅在 applyment_state=FINISH 后生效，prepay 下单用。
- merchant_status 独立于进件状态: FINISH 后可被运营冻结 (FROZEN) 禁收。
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Boolean,
    Enum as SAEnum,
)

from app.core.database import Base


def _enum_values(ec):
    """SAEnum 存 enum.value (与 User/UserRole 同模式)。"""
    return [m.value for m in ec]


class MerchantType(str, enum.Enum):
    """商户类型 (契约 §3.1 merchant_type, 裁剪材料要求)"""

    MICRO_MERCHANT = "micro_merchant"            # 小微: 仅身份证 + 个人银行卡
    INDIVIDUAL_BUSINESS = "individual_business"  # 个体工商户: 执照 + 法人身份证
    ENTERPRISE = "enterprise"                    # 企业: 执照 + 对公账户


class ApplymentState(str, enum.Enum):
    """进件状态机七态 (契约 §3.2, 对齐IM-B applyment4sub 原值)"""

    APPLYMENT_EDITING = "APPLYMENT_EDITING"  # 资料编辑中 (被驳回后可重新提交)
    AUDITING = "AUDITING"                    # 审核中
    TO_BE_SIGNED = "TO_BE_SIGNED"            # 待账户验证/法人验证
    SIGNING = "SIGNING"                      # 开通权限中
    FINISH = "FINISH"                        # 完成 → sub_mchid 生效, 可收款
    REJECTED = "REJECTED"                    # 已驳回 → 见 reject_reason
    FROZEN = "FROZEN"                        # 已冻结


class MerchantStatus(str, enum.Enum):
    """商户运行态 (契约 §3.3, 独立于进件状态)"""

    ACTIVE = "ACTIVE"    # 可收款
    FROZEN = "FROZEN"    # 禁收 (prepay 返回 SUB_MCH_FROZEN)
    PENDING = "PENDING"  # 进件未完成


class Merchant(Base):
    """特约商户进件表 - 承载进件状态机 + 运行态"""
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    business_code = Column(String(64), unique=True, nullable=False, index=True, comment="进件申请号 APL_yyyymmdd_xxxx")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True, comment="运营归属团队 (ops team scoping)")
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True, comment="所属租户")

    # 商户基本信息
    merchant_type = Column(
        SAEnum(MerchantType, values_callable=_enum_values), nullable=False, comment="商户类型"
    )
    merchant_name = Column(String(120), nullable=False, comment="商户名称")

    # 联系人 (契约 §3.1 contact 对象拆字段)
    contact_name = Column(String(60), nullable=True, comment="联系人姓名")
    contact_phone = Column(String(30), nullable=True, comment="联系人电话")

    # 身份证 (契约 §3.1 id_card 对象拆字段)
    id_card_name = Column(String(60), nullable=True, comment="身份证姓名")
    id_card_number = Column(String(40), nullable=True, comment="身份证号")

    # 结算账户 (契约 §3.1 settlement 对象拆字段)
    settlement_account_type = Column(String(20), nullable=True, comment="结算账户类型: personal/corporate")
    settlement_bank_name = Column(String(100), nullable=True, comment="开户银行")
    settlement_account_number = Column(String(60), nullable=True, comment="结算账号")
    settlement_account_last4 = Column(String(4), nullable=True, comment="结算账号末四位 (列表展示)")

    # 进件状态机
    applyment_state = Column(
        SAEnum(ApplymentState, values_callable=_enum_values),
        nullable=False,
        default=ApplymentState.AUDITING,
        comment="进件状态 (七态)",
    )
    sub_mchid = Column(String(32), nullable=True, comment="特约商户号 (FINISH 后生效)")
    reject_reason = Column(String(500), nullable=True, comment="驳回原因 (REJECTED 时填)")
    legal_validation_url = Column(String(500), nullable=True, comment="法人验证链接 (TO_BE_SIGNED 时填)")

    # 运行态 (独立于进件状态)
    merchant_status = Column(
        SAEnum(MerchantStatus, values_callable=_enum_values),
        nullable=False,
        default=MerchantStatus.PENDING,
        comment="商户运行态: ACTIVE/FROZEN/PENDING",
    )
    profit_sharing_enabled = Column(Boolean, nullable=False, default=False, comment="是否已签分账协议 (平台服务费)")

    # 关联站点 (契约 §3.1 station_ids 数组; JSON 存, 兼容真实 int id 与 mock 字符串)
    station_ids = Column(JSON, nullable=True, comment="关联场站 id 列表")

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_merchant_team", "team_id"),
        Index("idx_merchant_state", "applyment_state"),
    )
