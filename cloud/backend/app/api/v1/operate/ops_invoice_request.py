"""运营手动开票 API (用户端云端契约 §5.4, 工作卡 a09f8a21; 红冲 卡 f42bdf5a)

挂 /ops 前缀 (与 ops_merchants / ops_platform_fee 同前缀, 契约 v1.1 运营后台统一前缀):
- GET  /ops/invoice-requests                 待开票/全部列表 (按 team 隔离)
- POST /ops/invoice-requests/{id}/upload     multipart 上传发票文件 → ISSUED + 通知
- POST /ops/invoice-requests/{id}/reject     拒绝开票 → REJECTED
- POST /ops/invoice-requests/{id}/void       红冲已开发票 (Phase2-B2, R1 方案b: 打 voided 标记)

权限门: require_permission("operate:manage") (与 operate/* 同模式)。
team scoping: invoice_request.team_id (创建时由订单 station→team 捕获);
admin 平台级豁免; 跨团队 → 404 (不泄露存在)。
响应: 运营侧统一 success_response (code=200)。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_team_access, team_scope
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.response import success_response
from app.middleware.permission import require_permission
from app.models.user import User
from app.services import invoice_request_service
from app.services.invoice_request_service import InvoiceError

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_permission("operate:manage"))])


# ========== Schemas ==========

class RejectRequest(BaseModel):
    reject_reason: str = Field(..., min_length=1, max_length=500, description="拒绝原因")


class VoidRequest(BaseModel):
    """红冲请求体 (Phase2-B2, 卡 f42bdf5a)。service 层另有 strip 非空校验。"""
    reason: str = Field(..., min_length=1, max_length=500, description="红冲原因")


# ========== 路由 ==========

@router.get("/invoice-requests", summary="开票申请列表 (team 隔离)")
@limiter.limit("60/minute")
def list_invoice_requests(
    request: Request,
    status: Optional[str] = Query(None, description="pending/issued/rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """运营开票申请列表。团队级仅本 team; admin 平台级全量。"""
    data = invoice_request_service.list_ops_requests(
        db, user, team_scope(user), status, page, page_size
    )
    return success_response(data)


@router.post("/invoice-requests/{invoice_id}/upload", summary="上传发票文件 → ISSUED")
@limiter.limit("10/minute")
def upload_invoice_file(
    request: Request,
    invoice_id: int,
    file: UploadFile = File(..., description="发票文件 PDF/OFD/jpg/png ≤10MB"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """multipart 上传发票文件: magic bytes 校验 + 落盘 → status=ISSUED + 触发通知。"""
    # 卡7502e6fb 缺陷3: chunked(无 content-length)绕过全局体积限制, read() 前早拒
    # (file.size 由 Starlette 按实际接收字节设置, 不受头部欺骗)
    if file.size is not None and file.size > invoice_request_service.MAX_INVOICE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")
    content = file.file.read()
    try:
        req = invoice_request_service.upload_invoice_file(
            db,
            user,
            invoice_id,
            file.filename or "invoice",
            content,
            file.content_type,
            assert_team_access,
        )
    except InvoiceError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    return success_response(invoice_request_service._ops_list_item(req), "发票已上传")


@router.post("/invoice-requests/{invoice_id}/reject", summary="拒绝开票 → REJECTED")
@limiter.limit("30/minute")
def reject_invoice(
    request: Request,
    invoice_id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """拒绝开票 (填理由); 用户可对同一订单重新申请新建 InvoiceRequest。"""
    try:
        req = invoice_request_service.reject_invoice_request(
            db, user, invoice_id, body.reject_reason, assert_team_access
        )
    except InvoiceError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    return success_response(invoice_request_service._ops_list_item(req), "已拒绝开票")


@router.post("/invoice-requests/{invoice_id}/void", summary="红冲已开发票 (打 voided 标记)")
@limiter.limit("30/minute")
def void_invoice(
    request: Request,
    invoice_id: int,
    body: VoidRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """红冲已开发票 (Phase2-B2, 卡 f42bdf5a; R1 方案b —— status 保持 issued,
    响应新增 voided/void_reason/voided_by/voided_at 可选字段, 契约只增不破)。

    守卫: 仅 ISSUED 可红冲; 已红冲重复红冲 → 400; 红冲不动金额/发票文件。
    """
    try:
        req = invoice_request_service.void_invoice_request(
            db, user, invoice_id, body.reason, assert_team_access
        )
    except InvoiceError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    return success_response(invoice_request_service._ops_list_item(req), "发票已红冲")
