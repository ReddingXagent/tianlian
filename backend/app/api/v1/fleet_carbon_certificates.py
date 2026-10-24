"""
碳减排核证/交易管理 API - fleet-platform-spec §4.3 规划表

挂载前缀 /fleet (见 api/v1/__init__.py), 实际路径:
- POST  /api/v1/fleet/carbon/certificates/apply      从月度汇总申请核证
- GET   /api/v1/fleet/carbon/certificates            核证记录列表(企业/状态筛选)
- PATCH /api/v1/fleet/carbon/certificates/{id}/verify 核证确认 (pending->verified)
- PATCH /api/v1/fleet/carbon/certificates/{id}/trade  交易登记 (verified->traded)
- PATCH /api/v1/fleet/carbon/certificates/{id}/cancel 撤销核证 (pending/verified->cancelled)

状态机: pending -> verified -> traded
        pending|verified -> cancelled (撤销后同汇总可重新申请)
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import assert_enterprise_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.carbon_emission import CarbonReductionSummary
from app.models.enterprise import Enterprise
from app.models.fleet_carbon_certificate import (
    FleetCarbonCertificate,
    CertificateStatus,
)
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])

logger = logging.getLogger(__name__)


# ─── Schemas ───

class CertificateApplyRequest(BaseModel):
    summary_id: int = Field(..., gt=0, description="碳减排月度汇总ID")


class CertificateTradeRequest(BaseModel):
    trade_volume: float = Field(..., gt=0, description="交易量(吨CO2)")
    trade_price: float = Field(..., gt=0, description="交易单价(元/吨)")


# ─── 常量 ───

# 有效(未撤销)状态集合, 用于重复申请校验
_ACTIVE_STATUSES = {
    CertificateStatus.PENDING,
    CertificateStatus.VERIFIED,
    CertificateStatus.TRADED,
}


# ─── Helpers ───

def _gen_certificate_no(summary: CarbonReductionSummary) -> str:
    """生成核证编号: CC-{年月}-{企业ID}-{时间戳}-{6位随机}。"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"CC-{summary.report_year}{summary.report_month:02d}-{summary.enterprise_id}-{stamp}-{suffix}"


def _cert_to_dict(c: FleetCarbonCertificate) -> dict:
    return {
        "id": c.id,
        "enterprise_id": c.enterprise_id,
        "summary_id": c.summary_id,
        "certificate_no": c.certificate_no,
        "verified_at": c.verified_at.isoformat() if c.verified_at else None,
        "trade_volume": float(c.trade_volume) if c.trade_volume is not None else 0.0,
        "trade_price": float(c.trade_price) if c.trade_price is not None else 0.0,
        "status": c.status.value if hasattr(c.status, "value") else str(c.status),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _get_or_404(db: Session, cert_id: int) -> FleetCarbonCertificate:
    cert = db.query(FleetCarbonCertificate).filter(FleetCarbonCertificate.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="核证记录不存在")
    return cert


# ─── Endpoints ───

@router.post("/carbon/certificates/apply", summary="从月度汇总申请碳减排核证")
def apply_certificate(
    body: CertificateApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    从已审核的月度碳减排汇总申请核证:
    - 汇总必须存在且已审核(verified=True)
    - 同一汇总不可重复申请有效证书(撤销后可重新申请)
    """
    summary = db.query(CarbonReductionSummary).filter(
        CarbonReductionSummary.id == body.summary_id
    ).first()
    if not summary:
        raise HTTPException(status_code=404, detail="月度汇总不存在")
    assert_enterprise_team_access(db, summary.enterprise_id, current_user)

    if not summary.verified:
        raise HTTPException(status_code=400, detail="月度汇总尚未审核，无法申请核证")

    existing = db.query(FleetCarbonCertificate).filter(
        FleetCarbonCertificate.summary_id == body.summary_id,
        FleetCarbonCertificate.status.in_(_ACTIVE_STATUSES),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该汇总已存在有效核证证书，不可重复申请")

    cert = FleetCarbonCertificate(
        enterprise_id=summary.enterprise_id,
        summary_id=summary.id,
        certificate_no=_gen_certificate_no(summary),
        status=CertificateStatus.PENDING,
    )
    db.add(cert)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("核证申请写入冲突 summary_id=%s", body.summary_id)
        raise HTTPException(status_code=409, detail="核证申请写入冲突")
    except Exception:
        db.rollback()
        logger.exception("核证申请失败 summary_id=%s", body.summary_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(cert)
    return success_response(_cert_to_dict(cert), "核证申请成功")


@router.get("/carbon/certificates", summary="核证记录列表")
def list_certificates(
    enterprise_id: Optional[int] = Query(None, gt=0, description="企业ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选: pending/verified/traded/cancelled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询碳核证记录列表, 支持按企业/状态筛选 (卡 45166947: 缺省时 team 兜底过滤)。"""
    if enterprise_id is not None:
        assert_enterprise_team_access(db, enterprise_id, current_user)
    query = db.query(FleetCarbonCertificate)
    scope = team_scope(current_user)
    if scope is not None:
        # 团队级用户缺省 enterprise_id 时按企业归属 team 兜底过滤, 杜绝全表裸查越权
        query = query.join(Enterprise, Enterprise.id == FleetCarbonCertificate.enterprise_id).filter(
            Enterprise.owner_team_id == scope
        )
    if enterprise_id:
        query = query.filter(FleetCarbonCertificate.enterprise_id == enterprise_id)
    if status:
        valid = {s.value for s in CertificateStatus}
        if status not in valid:
            raise HTTPException(status_code=400, detail=f"无效状态 '{status}', 可选: {', '.join(sorted(valid))}")
        query = query.filter(FleetCarbonCertificate.status == CertificateStatus(status))

    total = query.count()
    items = (
        query.order_by(desc(FleetCarbonCertificate.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response([_cert_to_dict(c) for c in items], total, page, page_size)


@router.patch("/carbon/certificates/{cert_id}/verify", summary="核证确认")
def verify_certificate(
    cert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """核证确认: pending -> verified, 记录核证时间。"""
    cert = _get_or_404(db, cert_id)
    assert_enterprise_team_access(db, cert.enterprise_id, current_user)
    if cert.status != CertificateStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 '{cert.status.value}' 不支持核证, 仅 pending 可核证",
        )

    cert.status = CertificateStatus.VERIFIED
    cert.verified_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("核证确认失败 cert_id=%s", cert_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(cert)
    return success_response(_cert_to_dict(cert), "核证确认成功")


@router.patch("/carbon/certificates/{cert_id}/trade", summary="交易登记")
def trade_certificate(
    cert_id: int,
    body: CertificateTradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """交易登记: verified -> traded, 记录交易量/单价。"""
    cert = _get_or_404(db, cert_id)
    assert_enterprise_team_access(db, cert.enterprise_id, current_user)
    if cert.status != CertificateStatus.VERIFIED:
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 '{cert.status.value}' 不支持交易, 仅 verified 可登记交易",
        )

    cert.status = CertificateStatus.TRADED
    try:
        cert.trade_volume = Decimal(str(body.trade_volume))
        cert.trade_price = Decimal(str(body.trade_price))
    except (ArithmeticError, ValueError, TypeError):
        logger.exception("交易金额换算失败 cert_id=%s", cert_id)
        raise HTTPException(status_code=400, detail="交易量或单价格式非法")
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("交易登记失败 cert_id=%s", cert_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(cert)
    return success_response(_cert_to_dict(cert), "交易登记成功")


@router.patch("/carbon/certificates/{cert_id}/cancel", summary="撤销核证")
def cancel_certificate(
    cert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销核证: pending|verified -> cancelled; 已交易不可撤销。撤销后同汇总可重新申请。"""
    cert = _get_or_404(db, cert_id)
    assert_enterprise_team_access(db, cert.enterprise_id, current_user)
    if cert.status not in (CertificateStatus.PENDING, CertificateStatus.VERIFIED):
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 '{cert.status.value}' 不可撤销",
        )

    cert.status = CertificateStatus.CANCELLED
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("核证撤销失败 cert_id=%s", cert_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(cert)
    return success_response(_cert_to_dict(cert), "核证已撤销")
