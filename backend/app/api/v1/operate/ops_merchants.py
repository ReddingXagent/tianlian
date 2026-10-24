"""运营平台 - 特约商户进件 API (工作卡 280c85ee — 云端配套④)

契约: backend/docs/contracts/user-client-contract.md §3 (特约商户进件 + 商户状态)
端点 (挂 /ops 前缀, 契约 v1.1 运营后台统一前缀):
- POST /ops/merchants/applyment                  进件提交 → 202 {business_code, applyment_state}
- GET  /ops/merchants/applyment/{business_code}  进件状态查询
- GET  /ops/merchants                            商户列表 (team scoping)

权限门: require_permission("operate:manage") (与 operate/* 同模式)。
team scoping: merchant.team_id = current_user.team_id; admin 平台级豁免; 跨团队 → 404。
响应: 用户端云端契约统一 code=0 (契约 §6)。
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.deps import team_scope, assert_team_access
from app.middleware.permission import require_permission
from app.models.user import User
from app.models.merchant import Merchant
from app.services.wx_pay import applyment as applyment_svc
from app.services.wx_pay import response as rsp

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])


# ========== Schemas ==========

class ContactInfo(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


class IdCardInfo(BaseModel):
    name: Optional[str] = None
    number: Optional[str] = None


class SettlementInfo(BaseModel):
    account_type: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None


class ApplymentPayload(BaseModel):
    merchant_type: Literal["micro_merchant", "individual_business", "enterprise"]
    merchant_name: str = Field(..., min_length=1, max_length=120)
    contact: Optional[ContactInfo] = None
    id_card: Optional[IdCardInfo] = None
    settlement: Optional[SettlementInfo] = None
    station_ids: Optional[list] = None


# 七态状态机合法 event (对齐 applyment4sub 迁移矩阵, 卡 d53a2f2f)
AdvanceEvent = Literal[
    "submit",        # APPLYMENT_EDITING → AUDITING
    "audit_pass",    # AUDITING → TO_BE_SIGNED
    "audit_reject",  # AUDITING → REJECTED
    "resubmit",      # REJECTED → AUDITING
    "validate",      # TO_BE_SIGNED → SIGNING
    "finish",        # SIGNING → FINISH (生成 sub_mchid + ACTIVE)
    "freeze",        # 任意非 FROZEN → FROZEN
    "unfreeze",      # FROZEN → AUDITING
]


class AdvancePayload(BaseModel):
    event: AdvanceEvent
    reject_reason: Optional[str] = None


# ========== Helpers ==========

def _detail_dict(m: Merchant) -> dict:
    """契约 §3.2 详情结构。"""
    return {
        "business_code": m.business_code,
        "merchant_type": m.merchant_type.value,
        "merchant_name": m.merchant_name,
        "applyment_state": m.applyment_state.value,
        "sub_mchid": m.sub_mchid,
        "reject_reason": m.reject_reason,
        "legal_validation_url": m.legal_validation_url,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _list_item_dict(m: Merchant) -> dict:
    """契约 §3.3 列表项结构。"""
    return {
        "business_code": m.business_code,
        "merchant_name": m.merchant_name,
        "merchant_type": m.merchant_type.value,
        "applyment_state": m.applyment_state.value,
        "sub_mchid": m.sub_mchid,
        "merchant_status": m.merchant_status.value,
        "settlement": {
            "account_type": m.settlement_account_type,
            "bank_name": m.settlement_bank_name,
            "account_last4": m.settlement_account_last4,
        },
        "profit_sharing_enabled": m.profit_sharing_enabled,
        "station_ids": m.station_ids or [],
    }


def _get_merchant_by_code(db: Session, business_code: str) -> Optional[Merchant]:
    return db.query(Merchant).filter(Merchant.business_code == business_code).first()


# ========== 端点 ==========

@router.post("/merchants/applyment", status_code=202, summary="特约商户进件提交")
def submit_applyment(
    body: ApplymentPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交进件 → applyment_state=AUDITING, merchant_status=PENDING (契约 §3.1)。

    team 归属: merchant.team_id = current_user.team_id (admin 创建为平台级 team_id=None)。
    """
    try:
        payload = body.model_dump()
        m = applyment_svc.submit_applyment(db, current_user.team_id, payload)
        return rsp.ok(
            {"business_code": m.business_code, "applyment_state": m.applyment_state.value}
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("submit_applyment 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.get("/merchants/applyment/{business_code}", summary="进件状态查询")
def get_applyment(
    business_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """进件状态 (契约 §3.2)。跨团队 → 404。"""
    try:
        m = _get_merchant_by_code(db, business_code)
        if m is None:
            raise HTTPException(status_code=404, detail="进件记录不存在")
        assert_team_access(current_user, m.team_id)
        return rsp.ok(_detail_dict(m))
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_applyment 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.get("/merchants", summary="商户列表 (team scoping)")
def list_merchants(
    applyment_state: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """商户列表 (契约 §3.3)。非 admin 仅返回本 team。"""
    try:
        q = db.query(Merchant)
        scope = team_scope(current_user)
        if scope is not None:
            q = q.filter(Merchant.team_id == scope)
        if applyment_state:
            q = q.filter(Merchant.applyment_state == applyment_state)
        items = q.order_by(Merchant.id.desc()).all()
        return rsp.ok(
            {"items": [_list_item_dict(m) for m in items], "total": len(items)}
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_merchants 异常")
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )


@router.post(
    "/merchants/applyment/{business_code}/advance",
    summary="[mock] 手动推进进件状态机",
)
def advance_applyment(
    business_code: str,
    body: AdvancePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """[mock 演示] 手动推进进件状态机 (契约 §3.2 七态, 卡 d53a2f2f)。

    真实接入由IM-B applyment4sub 异步通知驱动状态流转, 此端点仅供 mock 期间运维演示;
    服务商凭证到位后应禁用或限制为内部运维 (状态机本身在 service 层 applyment.advance)。

    - FINISH → 生成 sub_mchid (mock_ 前缀) + merchant_status=ACTIVE (可收款)
    - TO_BE_SIGNED → 生成法人验证链接; REJECTED → 记录驳回原因
    - 非法迁移 → 400; 跨团队/未知 business_code → 404
    响应在 §3.2 详情结构上附加 merchant_status (确认 FINISH 后运行态)。
    """
    try:
        m = _get_merchant_by_code(db, business_code)
        if m is None:
            raise HTTPException(status_code=404, detail="进件记录不存在")
        assert_team_access(current_user, m.team_id)
        m = applyment_svc.advance(db, m, body.event, reject_reason=body.reject_reason)
        data = _detail_dict(m)
        data["merchant_status"] = m.merchant_status.value
        return rsp.ok(data)
    except applyment_svc.WxPayError:
        # IM-B外部调用故障 (网络/超时) → 502 网关错误, 非裸 500 (卡 a201d398)
        raise HTTPException(status_code=502, detail="IM-B进件接口异常，请稍后重试")
    except applyment_svc.IllegalTransition:
        raise HTTPException(status_code=400, detail="非法状态迁移")
    except HTTPException:
        raise
    except Exception:
        logger.exception("advance_applyment 异常 business_code=%s", business_code)
        return JSONResponse(
            status_code=500, content={"detail": "服务器内部错误，请稍后重试"}
        )
