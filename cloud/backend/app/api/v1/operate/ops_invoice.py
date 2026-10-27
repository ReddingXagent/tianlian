"""
运营发票管理 API - SPEC §2.5

发票抬头 CRUD + 发票申请/审核/开具/红冲
统一挂载在 /api/v1/operate/invoices 前缀下

⚠️ Deprecated (卡 6d06831d, B1 决策): 旧 OpsInvoice 发票本体体系 (申请/审核/
开具/红冲) 已废弃, 由 InvoiceRequest 体系取代 (契约 v1.3 §5):
- 列表/待审核 → GET /ops/invoice-requests?status=
- 审核拒绝   → POST /ops/invoice-requests/{id}/reject
- 开具       → POST /ops/invoice-requests/{id}/upload (传文件)
- 红冲       → 待 R1 拍板后另卡补 void 端点

下方「发票管理」族端点标 deprecated 保留一个版本周期, 下版本物理移除;
「发票抬头管理」族 (titles) 独立保留, 不在本卡范围。
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response
from app.models.ops_settlement import (
    InvoiceTitle, TitleType,
    OpsInvoice, OpsInvoiceStatus, OpsInvoiceType,
)
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, require_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ========== Schemas ==========


class InvoiceTitleCreate(BaseModel):
    user_id: Optional[int] = None
    title_type: TitleType = TitleType.PERSONAL
    title_name: str
    tax_id: Optional[str] = None
    register_address: Optional[str] = None
    register_phone: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    email: Optional[str] = None
    is_default: bool = False


class InvoiceTitleUpdate(BaseModel):
    title_type: Optional[TitleType] = None
    title_name: Optional[str] = None
    tax_id: Optional[str] = None
    register_address: Optional[str] = None
    register_phone: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    email: Optional[str] = None
    is_default: Optional[bool] = None


class InvoiceCreate(BaseModel):
    applicant_name: Optional[str] = None
    applicant_phone: Optional[str] = None
    apply_source: str = Field("admin", max_length=20)
    order_ids: Optional[Any] = None
    invoice_title_id: Optional[int] = None
    title_name: str
    tax_id: Optional[str] = None
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="开票金额(元)：必须为正，整数部分≤10位，精确到分(2位小数)，与 Numeric(12,2) 列语义对齐",
    )
    invoice_type: OpsInvoiceType = OpsInvoiceType.ELECTRONIC


class InvoiceReview(BaseModel):
    approved: bool = True
    remark: Optional[str] = None
    reviewer_id: Optional[int] = None


class InvoiceIssue(BaseModel):
    invoice_no: Optional[str] = None
    invoice_code: Optional[str] = None
    pdf_url: Optional[str] = None
    issued_by: str = "admin"


class InvoiceVoid(BaseModel):
    reason: str = "红冲作废"


# ==================== 发票抬头管理 ====================

@router.get("/invoices/titles", summary="发票抬头列表")
def list_invoice_titles(
    title_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        q = db.query(InvoiceTitle)
        # team scoping（任务卡 ab5c5f17）：发票抬头按归属用户过滤，非 admin 仅返回本 team 用户的抬头（经 user→team）。
        if not is_platform_admin(user):
            q = q.join(User, InvoiceTitle.user_id == User.id).filter(User.team_id == user.team_id)
        if title_type:
            q = q.filter(InvoiceTitle.title_type == title_type)
        total = q.count()
        items = q.order_by(InvoiceTitle.created_at.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        return success_response({
            "items": [_title_to_dict(t) for t in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询发票抬头列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post("/invoices/titles", summary="创建发票抬头")
def create_invoice_title(body: InvoiceTitleCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        title = InvoiceTitle(
            user_id=body.user_id,
            title_type=body.title_type,
            title_name=body.title_name,
            tax_id=body.tax_id,
            register_address=body.register_address,
            register_phone=body.register_phone,
            bank_name=body.bank_name,
            bank_account=body.bank_account,
            email=body.email,
            is_default=body.is_default,
        )
        db.add(title)
        db.commit()
        db.refresh(title)
        return success_response(_title_to_dict(title), "抬头已创建")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建发票抬头失败 title_name=%s", body.title_name)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put("/invoices/titles/{title_id}", summary="更新发票抬头")
def update_invoice_title(title_id: int, body: InvoiceTitleUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        t = db.query(InvoiceTitle).filter(InvoiceTitle.id == title_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="抬头不存在")
        updates = body.model_dump(exclude_unset=True)
        for field in ["title_name", "tax_id", "register_address", "register_phone",
                       "bank_name", "bank_account", "email", "is_default"]:
            if field in updates:
                setattr(t, field, updates[field])
        if "title_type" in updates:
            t.title_type = updates["title_type"]
        db.commit()
        db.refresh(t)
        return success_response(_title_to_dict(t), "抬头已更新")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新发票抬头失败 title_id=%s", title_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.delete("/invoices/titles/{title_id}", summary="删除发票抬头")
def delete_invoice_title(title_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        t = db.query(InvoiceTitle).filter(InvoiceTitle.id == title_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="抬头不存在")
        db.delete(t)
        db.commit()
        return success_response({"id": title_id}, "抬头已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("删除发票抬头失败 title_id=%s", title_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ==================== 发票管理 ====================

@router.get(
    "/invoices",
    summary="[Deprecated] 发票列表(已开+全部)",
    description="已废弃 (卡 6d06831d): 改用 GET /ops/invoice-requests?status=",
    deprecated=True,
)
def list_invoices(
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    try:
        q = db.query(OpsInvoice)
        if status:
            q = q.filter(OpsInvoice.status == status)
        total = q.count()
        items = q.order_by(OpsInvoice.created_at.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        return success_response({
            "items": [_inv_to_dict(i) for i in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询发票列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get(
    "/invoices/pending",
    summary="[Deprecated] 待审核发票列表",
    description="已废弃 (卡 6d06831d): 改用 GET /ops/invoice-requests?status=pending",
    deprecated=True,
)
def list_pending_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    try:
        q = db.query(OpsInvoice).filter(OpsInvoice.status == OpsInvoiceStatus.PENDING)
        total = q.count()
        items = q.order_by(OpsInvoice.apply_time.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        return success_response({
            "items": [_inv_to_dict(i) for i in items],
            "total": total, "page": page, "page_size": page_size,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询待审核发票列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post(
    "/invoices",
    summary="[Deprecated] 提交发票申请",
    description="已废弃 (卡 6d06831d): C端入口为 POST /business/invoices; 运营不再手工代提",
    deprecated=True,
)
def create_invoice(body: InvoiceCreate, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    """用户提交开票申请"""
    try:
        inv = OpsInvoice(
            applicant_name=body.applicant_name,
            applicant_phone=body.applicant_phone,
            apply_source=body.apply_source,
            order_ids=body.order_ids,
            invoice_title_id=body.invoice_title_id,
            title_name=body.title_name,
            tax_id=body.tax_id,
            amount=body.amount,
            invoice_type=body.invoice_type,
            status=OpsInvoiceStatus.PENDING,
            apply_time=datetime.now(timezone.utc),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return success_response(_inv_to_dict(inv), "发票申请已提交")
    except HTTPException:
        raise
    except Exception:
        logger.exception("提交发票申请失败 title_name=%s", body.title_name)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put(
    "/invoices/{invoice_id}/review",
    summary="[Deprecated] 审核发票",
    description="已废弃 (卡 6d06831d): 驳回改用 POST /ops/invoice-requests/{id}/reject;"
                " 审核通过与新体系 upload 合并为一步",
    deprecated=True,
)
def review_invoice(invoice_id: int, body: InvoiceReview, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    """审核通过/驳回"""
    try:
        inv = db.query(OpsInvoice).filter(OpsInvoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="发票不存在")
        if inv.status != OpsInvoiceStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"只有待审核状态可操作, 当前: {inv.status.value}")

        approved = body.approved
        if approved:
            inv.status = OpsInvoiceStatus.REVIEWED
            inv.review_remark = body.remark or "审核通过"
        else:
            inv.status = OpsInvoiceStatus.REJECTED
            inv.review_remark = body.remark or "审核驳回"
        inv.review_time = datetime.now(timezone.utc)
        inv.reviewer_id = body.reviewer_id

        db.commit()
        db.refresh(inv)
        return success_response(_inv_to_dict(inv), "审核已通过" if approved else "已驳回")
    except HTTPException:
        raise
    except Exception:
        logger.exception("审核发票失败 invoice_id=%s", invoice_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put(
    "/invoices/{invoice_id}/issue",
    summary="[Deprecated] 开具发票",
    description="已废弃 (卡 6d06831d): 改用 POST /ops/invoice-requests/{id}/upload (上传发票文件)",
    deprecated=True,
)
def issue_invoice(invoice_id: int, body: InvoiceIssue, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    """调用开票服务后更新状态"""
    try:
        inv = db.query(OpsInvoice).filter(OpsInvoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="发票不存在")
        if inv.status != OpsInvoiceStatus.REVIEWED:
            raise HTTPException(status_code=400, detail=f"只有审核通过状态可开票, 当前: {inv.status.value}")

        inv.status = OpsInvoiceStatus.ISSUED
        inv.invoice_no = body.invoice_no
        inv.invoice_code = body.invoice_code
        inv.pdf_url = body.pdf_url
        inv.issue_time = datetime.now(timezone.utc)
        inv.issued_by = body.issued_by

        db.commit()
        db.refresh(inv)
        return success_response(_inv_to_dict(inv), "发票已开具")
    except HTTPException:
        raise
    except Exception:
        logger.exception("开具发票失败 invoice_id=%s", invoice_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put(
    "/invoices/{invoice_id}/void",
    summary="[Deprecated] 红冲发票",
    description="已废弃 (卡 6d06831d): 红冲迁入新体系待 R1 拍板 (另卡补 /ops/invoice-requests/{id}/void)",
    deprecated=True,
)
def void_invoice(invoice_id: int, body: InvoiceVoid, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    """红冲作废"""
    try:
        inv = db.query(OpsInvoice).filter(OpsInvoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="发票不存在")
        if inv.status != OpsInvoiceStatus.ISSUED:
            raise HTTPException(status_code=400, detail=f"只有已开具状态可红冲, 当前: {inv.status.value}")

        inv.status = OpsInvoiceStatus.VOIDED
        inv.void_reason = body.reason
        inv.void_time = datetime.now(timezone.utc)

        db.commit()
        db.refresh(inv)
        return success_response(_inv_to_dict(inv), "发票已红冲")
    except HTTPException:
        raise
    except Exception:
        logger.exception("红冲发票失败 invoice_id=%s", invoice_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get(
    "/invoices/{invoice_id}",
    summary="[Deprecated] 发票详情",
    description="已废弃 (卡 6d06831d): 改用 GET /ops/invoice-requests 列表",
    deprecated=True,
)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        inv = db.query(OpsInvoice).filter(OpsInvoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail="发票不存在")
        return success_response(_inv_to_dict(inv))
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询发票详情失败 invoice_id=%s", invoice_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


# ==================== 辅助函数 ====================

def _title_to_dict(t: InvoiceTitle) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "title_type": t.title_type.value if hasattr(t.title_type, 'value') else str(t.title_type),
        "title_name": t.title_name,
        "tax_id": t.tax_id,
        "register_address": t.register_address,
        "register_phone": t.register_phone,
        "bank_name": t.bank_name,
        "bank_account": t.bank_account,
        "email": t.email,
        "is_default": t.is_default,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _inv_to_dict(i: OpsInvoice) -> dict:
    return {
        "id": i.id,
        "applicant_name": i.applicant_name,
        "applicant_phone": i.applicant_phone,
        "apply_source": i.apply_source,
        "order_ids": i.order_ids,
        "invoice_title_id": i.invoice_title_id,
        "title_name": i.title_name,
        "tax_id": i.tax_id,
        "amount": float(i.amount) if i.amount else 0,
        "invoice_type": i.invoice_type.value if hasattr(i.invoice_type, 'value') else str(i.invoice_type),
        "invoice_no": i.invoice_no,
        "invoice_code": i.invoice_code,
        "pdf_url": i.pdf_url,
        "status": i.status.value if hasattr(i.status, 'value') else str(i.status),
        "reviewer_id": i.reviewer_id,
        "review_time": i.review_time.isoformat() if i.review_time else None,
        "review_remark": i.review_remark,
        "issue_time": i.issue_time.isoformat() if i.issue_time else None,
        "issued_by": i.issued_by,
        "void_reason": i.void_reason,
        "void_time": i.void_time.isoformat() if i.void_time else None,
        "apply_time": i.apply_time.isoformat() if i.apply_time else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }
