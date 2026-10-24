"""特约商户进件服务 (工作卡 280c85ee — 云端配套④)

契约 §3 (特约商户进件 + 商户状态):
- submit_applyment → 建 Merchant, applyment_state=AUDITING, merchant_status=PENDING
- advance(event) → 按 applyment4sub 七态状态机推进;
  FINISH 时生成 sub_mchid + merchant_status=ACTIVE (可收款)

迁移矩阵对齐IM-B applyment4sub 状态 (契约 §3.2 七态)。
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.merchant import (
    Merchant,
    ApplymentState,
    MerchantStatus,
    MerchantType,
)
from app.services.wx_pay import get_wxpay_client
from app.services.wx_pay.client import WxPayError

logger = logging.getLogger(__name__)


class IllegalTransition(Exception):
    """非法状态迁移 (调用方映射为 400)"""


# 七态迁移矩阵 (对齐IM-B applyment4sub)
# event: submit / audit_pass / audit_reject / resubmit / validate / finish / freeze / unfreeze
_TRANSITIONS = {
    (ApplymentState.APPLYMENT_EDITING, "submit"): ApplymentState.AUDITING,
    (ApplymentState.AUDITING, "audit_pass"): ApplymentState.TO_BE_SIGNED,
    (ApplymentState.AUDITING, "audit_reject"): ApplymentState.REJECTED,
    (ApplymentState.REJECTED, "resubmit"): ApplymentState.AUDITING,
    (ApplymentState.TO_BE_SIGNED, "validate"): ApplymentState.SIGNING,
    (ApplymentState.SIGNING, "finish"): ApplymentState.FINISH,
    # 任意非 FROZEN 态 → FROZEN (进件冻结)
    (ApplymentState.APPLYMENT_EDITING, "freeze"): ApplymentState.FROZEN,
    (ApplymentState.AUDITING, "freeze"): ApplymentState.FROZEN,
    (ApplymentState.TO_BE_SIGNED, "freeze"): ApplymentState.FROZEN,
    (ApplymentState.SIGNING, "freeze"): ApplymentState.FROZEN,
    (ApplymentState.REJECTED, "freeze"): ApplymentState.FROZEN,
    (ApplymentState.FINISH, "freeze"): ApplymentState.FROZEN,
    (ApplymentState.FROZEN, "unfreeze"): ApplymentState.AUDITING,
}


def transition(current: ApplymentState, event: str) -> Optional[ApplymentState]:
    """纯函数: 返回迁移后的状态, 非法迁移返回 None。

    供状态机矩阵测试直接断言, 与 DB 无关。
    """
    return _TRANSITIONS.get((current, event))


def generate_business_code() -> str:
    """APL_yyyymmdd_xxxx (xxxx 随机, 唯一性由 DB unique 约束兜底)。"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"APL_{today}_{secrets.token_hex(4).upper()}"


def _last4(num: Optional[str]) -> Optional[str]:
    if not num:
        return None
    s = str(num)
    return s[-4:] if len(s) >= 4 else s


def submit_applyment(db: Session, team_id: Optional[int], payload: dict) -> Merchant:
    """提交进件 → 建 Merchant, applyment_state=AUDITING, merchant_status=PENDING。

    payload 结构对齐契约 §3.1 请求 (contact/id_card/settlement 为嵌套对象)。
    """
    business_code = generate_business_code()
    # 极小概率冲突, 唯一性兜底重试
    while db.query(Merchant).filter(Merchant.business_code == business_code).first():
        business_code = generate_business_code()

    contact = payload.get("contact") or {}
    id_card = payload.get("id_card") or {}
    settlement = payload.get("settlement") or {}

    m = Merchant(
        business_code=business_code,
        team_id=team_id,
        merchant_type=MerchantType(payload["merchant_type"]),
        merchant_name=payload["merchant_name"],
        contact_name=contact.get("name"),
        contact_phone=contact.get("phone"),
        id_card_name=id_card.get("name"),
        id_card_number=id_card.get("number"),
        settlement_account_type=settlement.get("account_type"),
        settlement_bank_name=settlement.get("bank_name"),
        settlement_account_number=settlement.get("account_number"),
        settlement_account_last4=_last4(settlement.get("account_number")),
        applyment_state=ApplymentState.AUDITING,
        merchant_status=MerchantStatus.PENDING,
        profit_sharing_enabled=False,
        station_ids=payload.get("station_ids"),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def advance(
    db: Session,
    merchant: Merchant,
    event: str,
    *,
    reject_reason: Optional[str] = None,
) -> Merchant:
    """按 event 推进状态机 (mock 模拟IM-B异步通知)。非法 → IllegalTransition。

    FINISH: 生成 sub_mchid (IM-B返回) + merchant_status=ACTIVE (可收款)。
    TO_BE_SIGNED: 生成法人验证链接。
    REJECTED: 记录驳回原因。
    """
    new_state = transition(merchant.applyment_state, event)
    if new_state is None:
        raise IllegalTransition(
            f"非法迁移: {merchant.applyment_state.value} + {event}"
        )
    merchant.applyment_state = new_state
    if new_state == ApplymentState.TO_BE_SIGNED:
        merchant.legal_validation_url = (
            f"https://pay.tianlian.example/validate/{merchant.business_code}"
        )
    elif new_state == ApplymentState.REJECTED:
        merchant.reject_reason = reject_reason or "审核未通过"
    elif new_state == ApplymentState.FINISH:
        # 生成 sub_mchid 真实接入为IM-B applyment4sub 外部 HTTP 调用, 网络故障/超时
        # 不得冒泡裸 500: 捕获底层异常转 WxPayError, 由 router 映射 502 (卡 a201d398)。
        # 失败时下方 db.commit() 不执行, merchant 状态保持 SIGNING (事务未提交, 不半成品)。
        client = get_wxpay_client()
        try:
            sub_mchid = client.generate_sub_mchid()
        except Exception as exc:
            logger.error(
                "IM-B生成特约商户号失败 business_code=%s",
                merchant.business_code,
                exc_info=True,
            )
            raise WxPayError("IM-B进件接口异常，生成特约商户号失败") from exc
        merchant.sub_mchid = sub_mchid
        merchant.merchant_status = MerchantStatus.ACTIVE
    db.commit()
    db.refresh(merchant)
    return merchant
