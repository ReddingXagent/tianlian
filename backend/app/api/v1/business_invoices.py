"""用户端开票申请 API (用户端云端契约 §5, 工作卡 a09f8a21)

挂 /business 前缀 (与 business.router 同前缀):
- POST /business/invoices                  用户提交开票申请 (校验 PAID+未开票, 金额汇总)
- GET  /business/invoices                  用户申请列表 (轻量, 无 invoice_file)
- GET  /business/invoices/{invoice_id}     申请详情 (ISSUED 返回签名 file_url 2h)
- POST /business/invoices/{invoice_id}/send-email  补发/改发邮箱
- GET  /business/invoice-file?token=...    发票文件下载 (签名令牌自证, 白名单免登录)

认证: 前四个走 C 端用户 token (get_current_user); invoice-file 靠签名令牌,
经 is_public_path 白名单豁免 enforce_auth (契约 §5.5 分享/转发场景无 Bearer)。
响应: 用户端云端契约统一 code=0 (契约 §6)。
"""
import logging
import os
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.invoice_request import InvoiceFileType, InvoiceTitleType
from app.models.user import User
from app.services import invoice_notification, invoice_request_service
from app.services.invoice_request_service import InvoiceError
from app.services.wx_pay import response as rsp


def _invoice_error_response(e: InvoiceError):
    """InvoiceError → C 端响应 (卡 418a675a 契约 §6 统一)。

    业务状态类 (e.reason 有值: 订单不存在/未支付/重复申请/申请不存在/未开具/
    跨团队/场站缺失) → biz_error (HTTP 200 + code!=0 + message=原因码);
    输入校验类 (抬头空/税号缺失/邮箱空, 无 reason) → 保留 HTTPException,
    与全平台 422 语义一致。
    """
    if e.reason:
        return rsp.biz_error(message=e.reason)
    raise HTTPException(status_code=e.status, detail=e.message)

logger = logging.getLogger(__name__)
router = APIRouter()


def _send_email_limit_key(request: Request) -> str:
    """send-email 按用户维度限流 key (卡 71062d84)。

    slowapi 的 key_func 在端点函数体执行前调用, 此时依赖注入的 user
    尚不可得 → 直接解 Authorization token 取 sub(get_current_user 同源),
    不查库 (限流 key 只需稳定标识, 身份真伪由鉴权层把关); 解析失败
    回退 real IP。
    """
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from app.core.jwt_utils import decode_token
            sub = decode_token(auth[7:]).get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    from app.core.rate_limit import get_real_ip
    return get_real_ip(request)


# ========== Schemas ==========

class InvoiceApplyRequest(BaseModel):
    order_ids: List[str] = Field(..., min_length=1, max_length=50, description="订单号列表 (ChargingOrder.order_no)")
    title_type: Literal["personal", "company"] = "personal"
    title_name: str = Field(..., min_length=1, max_length=200, description="发票抬头")
    tax_number: Optional[str] = Field(None, max_length=50, description="税号 (company 必填)")
    receive_email: Optional[EmailStr] = Field(None, description="收票邮箱 (选填)")
    remark: Optional[str] = Field(None, max_length=500)


class SendEmailRequest(BaseModel):
    email: EmailStr


# ========== 路由 ==========

@router.post("/invoices", summary="用户提交开票申请")
@limiter.limit("30/minute")
def apply_invoice(
    request: Request,
    body: InvoiceApplyRequest,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """契约 §5.1: 仅 payment_status=PAID 且未开票的订单; 金额自动汇总(分)。"""
    try:
        title_type = InvoiceTitleType(body.title_type)
    except ValueError:
        raise HTTPException(status_code=422, detail="抬头类型非法")
    try:
        req = invoice_request_service.apply_invoice(
            db,
            user,
            order_ids=body.order_ids,
            title_type=title_type,
            title_name=body.title_name,
            tax_number=body.tax_number,
            email=str(body.receive_email) if body.receive_email else None,
            remark=body.remark,
        )
    except InvoiceError as e:
        return _invoice_error_response(e)
    # 契约 §5.1: 响应 202 Accepted (申请已受理, 待运营开票); body 仍 code=0
    return JSONResponse(
        status_code=202,
        content=rsp.ok({
            "invoice_id": req.id,
            "status": req.status.value,
            "amount": req.amount,
        }),
    )


@router.get("/invoices", summary="用户开票申请列表 (轻量)")
@limiter.limit("60/minute")
def list_invoices(
    request: Request,
    status: Optional[str] = Query(None, description="pending/issued/rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = invoice_request_service.list_user_invoices(db, user, status, page, page_size)
    return rsp.ok(data)


@router.get("/invoices/{invoice_id}", summary="开票申请详情")
@limiter.limit("60/minute")
def get_invoice(
    request: Request,
    invoice_id: int,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    base_url = str(request.base_url)
    try:
        data = invoice_request_service.get_user_invoice(db, user, invoice_id, base_url)
    except InvoiceError as e:
        return _invoice_error_response(e)
    return rsp.ok(data)


@router.post("/invoices/{invoice_id}/send-email", summary="补发/改发邮箱")
@limiter.limit("9/hour", key_func=_send_email_limit_key)
def send_email(
    request: Request,
    invoice_id: int,
    body: SendEmailRequest,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """契约 §5.3: 仅 ISSUED 可发; 响应 {sent: true}。

    限流 (卡 71062d84): 9次/小时 按用户维度 —— 带发票附件的邮件是真实
    SMTP 出口资源, 原 30/min = 1800封/小时/用户 可被刷爆; 个位数/小时
    足够正常改发场景 (填错邮箱重发)。
    """
    try:
        sent = invoice_request_service.resend_invoice_email(
            db, user, invoice_id, str(body.email)
        )
    except InvoiceError as e:
        return _invoice_error_response(e)
    return rsp.ok({"sent": bool(sent)})


@router.get("/invoice-file", summary="发票文件下载 (签名令牌, 无需登录)")
def download_invoice_file(
    token: str = Query(..., description="签名下载令牌"),
    db=Depends(get_db),
):
    """契约 §5.5: 签名 URL 2h 过期, 端侧/邮箱可直接打开 (无需 Bearer)。
    白名单 (/business/invoice-file) 豁免 enforce_auth, 靠令牌自证。"""
    invoice_id = invoice_notification.verify_file_token(token)
    if invoice_id is None:
        raise HTTPException(status_code=403, detail="下载链接无效或已过期")
    req = invoice_request_service.get_invoice_for_download(db, invoice_id)
    if req is None or not req.invoice_file_path or not os.path.exists(req.invoice_file_path):
        raise HTTPException(status_code=404, detail="发票文件不存在")
    media = {
        InvoiceFileType.PDF: "application/pdf",
        InvoiceFileType.OFD: "application/ofd",
        InvoiceFileType.IMAGE: "image/jpeg",
    }
    mimetype = media.get(req.invoice_file_type, "application/octet-stream")
    return FileResponse(
        req.invoice_file_path,
        media_type=mimetype,
        filename=req.invoice_file_name or os.path.basename(req.invoice_file_path),
    )
