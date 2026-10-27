"""
车队充值申请 API - 卡 4144ef1b

挂载前缀 /fleet/recharge (见 api/v1/__init__.py), 实际路径:
- POST   /api/v1/fleet/recharge            创建充值申请(上传凭证)
- GET    /api/v1/fleet/recharge            列表(fleet 用户只看自己企业; operator/admin 看全部)
- GET    /api/v1/fleet/recharge/{id}       详情
- POST   /api/v1/fleet/recharge/{id}/approve   审核通过(余额入账)
- POST   /api/v1/fleet/recharge/{id}/reject    驳回

权限口径:
- fleet 用户判定按 Team.type == "fleet" (UserRole 无 fleet 角色, 不能按 role 判)。
- 审核: platform admin (admin/super_admin) 豁免; 其余须为 operator 角色且
  其 team 绑定了该企业的场站 (enterprise.stations → station.team_id)。
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import is_platform_admin, resolve_team_type
from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.enterprise import Enterprise
from app.models.fleet_recharge import FleetRechargeRequest, RechargeStatus
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

UPLOAD_SUBDIR = "fleet_recharge"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".webp"}
_MAX_VOUCHER_BYTES = 10 * 1024 * 1024  # 10MB

# (magic bytes, 扩展名) —— 校验文件头防伪造扩展名 (对齐 enterprise_registration::_LICENSE_MAGIC, 卡 7007f36c)
_VOUCHER_MAGIC = [
    (b"\xff\xd8\xff", ".jpg"),   # JPEG
    (b"\x89PNG", ".png"),        # PNG (89504E47)
    (b"RIFF", ".webp"),          # WebP (RIFF....WEBP)
    (b"%PDF", ".pdf"),           # PDF
]


# ─── Schemas ───

class RejectRequest(BaseModel):
    remark: str = Field(..., min_length=1, max_length=500, description="驳回理由")


# ─── Helpers ───

def _is_fleet_user(db: Session, user: User) -> bool:
    """fleet 用户 = 所属 Team.type == "fleet" (角色体系里没有 fleet 角色)。"""
    return resolve_team_type(db, user) == "fleet"


def _save_upload(file: UploadFile) -> str:
    """保存上传的凭证文件，返回 URL 路径 (/uploads/fleet_recharge/...)。"""
    original_name = file.filename or "voucher"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"不支持的文件格式: {ext}，仅支持 jpg/png/pdf/webp")

    # 卡7502e6fb 缺陷3: chunked(无 content-length)绕过全局体积限制, read() 前按
    # Starlette 实际接收字节数早拒, 避免全量进内存后才 len() 检查
    if file.size is not None and file.size > _MAX_VOUCHER_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件为空")
    if len(content) > _MAX_VOUCHER_BYTES:
        raise HTTPException(status_code=422, detail="文件超过 10MB 上限")

    # 魔数硬校验(防伪造扩展名): 以文件头推断实际类型, 命中即用对应后缀落盘 (卡 7007f36c)
    detected_ext = None
    for magic, magic_ext in _VOUCHER_MAGIC:
        if content.startswith(magic):
            detected_ext = magic_ext
            break
    if detected_ext is None:
        raise HTTPException(status_code=422, detail="文件内容与声明类型不符，校验失败")
    ext = detected_ext

    upload_dir = os.path.join(settings.UPLOAD_DIR or "./uploads", UPLOAD_SUBDIR)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)
    try:
        os.makedirs(upload_dir, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.error("车队充值凭证落盘失败: %s", e)
        raise HTTPException(status_code=500, detail="文件保存失败，请稍后重试")
    return f"/uploads/{UPLOAD_SUBDIR}/{filename}"


def _to_dict(req: FleetRechargeRequest, db: Session, enterprise_map: Optional[dict] = None) -> dict:
    if enterprise_map is not None:
        enterprise_name = enterprise_map.get(req.enterprise_id)
    else:
        enterprise = db.query(Enterprise).filter(Enterprise.id == req.enterprise_id).first()
        enterprise_name = enterprise.name if enterprise else None
    return {
        "id": req.id,
        "enterprise_id": req.enterprise_id,
        "enterprise_name": enterprise_name,
        "amount": float(req.amount) if req.amount is not None else 0.0,
        "voucher_url": req.voucher_url,
        "status": req.status.value if req.status else "pending",
        "remark": req.remark,
        "reviewed_by": req.reviewed_by,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }


def _own_enterprise_ids(db: Session, user: User) -> set:
    """fleet 用户可访问的企业集合 (owner_team_id == user.team_id)。"""
    return {
        row[0] for row in db.query(Enterprise.id).filter(
            Enterprise.owner_team_id == user.team_id
        ).all()
    }


def _get_scoped_or_404(db: Session, req_id: int, user: User) -> FleetRechargeRequest:
    """详情/审核入口统一作用域: fleet 用户只能访问本企业申请(跨企业一律 404 不泄露存在性)。"""
    req = db.query(FleetRechargeRequest).filter(FleetRechargeRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="充值申请不存在")
    if _is_fleet_user(db, user) and req.enterprise_id not in _own_enterprise_ids(db, user):
        raise HTTPException(status_code=404, detail="充值申请不存在")
    return req


def _assert_reviewer(db: Session, req: FleetRechargeRequest, user: User) -> None:
    """审核权限: platform admin 豁免; operator 须绑定该企业的场站(station.team_id 匹配)。"""
    if is_platform_admin(user):
        return
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "operator":
        raise HTTPException(status_code=403, detail="无权审核充值申请")
    enterprise = db.query(Enterprise).filter(Enterprise.id == req.enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="关联企业不存在")
    bound_team_ids = {s.team_id for s in enterprise.stations if s.team_id is not None}
    if user.team_id not in bound_team_ids:
        raise HTTPException(status_code=403, detail="该运营商未绑定此企业的场站，无权审核")


# ─── Endpoints ───

@router.post("", summary="创建充值申请(上传凭证)")
def create_recharge(
    enterprise_id: int = Form(..., description="车队企业ID"),
    amount: float = Form(..., gt=0, description="充值金额(元)"),
    file: UploadFile = File(..., description="付款凭证(jpg/png/pdf/webp)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """车队用户发起充值申请，上传付款凭证"""
    enterprise = db.query(Enterprise).filter(Enterprise.id == enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="企业不存在")

    # fleet 用户只能为自己企业创建
    if _is_fleet_user(db, current_user) and enterprise.owner_team_id != current_user.team_id:
        raise HTTPException(status_code=403, detail="只能为自己企业创建充值申请")

    voucher_url = _save_upload(file)

    req = FleetRechargeRequest(
        enterprise_id=enterprise_id,
        amount=Decimal(str(amount)),
        voucher_url=voucher_url,
        status=RechargeStatus.PENDING,
    )
    try:
        db.add(req)
        db.commit()
        db.refresh(req)
    except Exception as e:
        db.rollback()
        logger.error("提交车队充值申请失败(enterprise_id=%s): %s", enterprise_id, e)
        raise HTTPException(status_code=500, detail="提交充值申请失败，请稍后重试")
    return success_response(_to_dict(req, db), message="充值申请已提交，等待审核")


@router.get("", summary="充值申请列表")
def list_recharges(
    status: Optional[str] = Query(None, description="状态筛选: pending/approved/rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    enterprise_id: Optional[int] = Query(None, description="企业筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """车队用户只看自己企业; operator/admin 看全部"""
    q = db.query(FleetRechargeRequest)

    if _is_fleet_user(db, current_user):
        own_ids = _own_enterprise_ids(db, current_user)
        # join+IN 过滤; owner_team 无企业时 own_ids 为空 → 恒空集(IN 条件需非空守卫)
        q = q.filter(FleetRechargeRequest.enterprise_id.in_(own_ids or [-1]))

    if status:
        try:
            status_enum = RechargeStatus(status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"无效状态: {status}")
        q = q.filter(FleetRechargeRequest.status == status_enum)

    if enterprise_id:
        q = q.filter(FleetRechargeRequest.enterprise_id == enterprise_id)

    total = q.count()
    items = (
        q.order_by(FleetRechargeRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # 批量预取企业名, 消除列表页 N+1 (卡 43625a78); enterprise_id 为 None 的不查, 名置 None
    enterprise_ids = {r.enterprise_id for r in items if r.enterprise_id is not None}
    if enterprise_ids:
        rows = db.query(Enterprise.id, Enterprise.name).filter(Enterprise.id.in_(enterprise_ids)).all()
        enterprise_map = {eid: name for eid, name in rows}
    else:
        enterprise_map = {}
    return paginated_response(
        [_to_dict(r, db, enterprise_map) for r in items], total, page, page_size
    )


@router.get("/{req_id}", summary="充值申请详情")
def get_recharge(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_scoped_or_404(db, req_id, current_user)
    return success_response(_to_dict(req, db))


@router.get("/{req_id}/voucher", summary="凭证文件下载(鉴权+团队作用域)")
def download_voucher(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """付款凭证文件下载 (卡 554bb70b): /uploads 裸挂已移除, 凭证改走本端点。

    作用域与详情一致 (_get_scoped_or_404): fleet 用户仅本企业, 跨企业 404。
    路径仅接受 voucher_url 中 /uploads/fleet_recharge/<filename> 的文件名段,
    realpath 收敛防目录穿越。"""
    req = _get_scoped_or_404(db, req_id, current_user)
    prefix = f"/uploads/{UPLOAD_SUBDIR}/"
    url = req.voucher_url or ""
    if not url.startswith(prefix):
        raise HTTPException(status_code=404, detail="凭证文件不存在")
    filename = os.path.basename(url[len(prefix):])
    upload_dir = os.path.realpath(os.path.join(settings.UPLOAD_DIR or "./uploads", UPLOAD_SUBDIR))
    filepath = os.path.realpath(os.path.join(upload_dir, filename))
    if not filepath.startswith(upload_dir + os.sep) or not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="凭证文件不存在")
    media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf",
        ".webp": "image/webp",
    }
    ext = os.path.splitext(filename)[1].lower()
    return FileResponse(filepath, media_type=media.get(ext, "application/octet-stream"), filename=filename)


@router.post("/{req_id}/approve", summary="审核通过(余额入账)")
def approve_recharge(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """运营商/管理员审核通过 → 企业余额增加"""
    req = _get_scoped_or_404(db, req_id, current_user)
    _assert_reviewer(db, req, current_user)
    if req.status != RechargeStatus.PENDING:
        raise HTTPException(status_code=409, detail="该申请已处理")

    enterprise = db.query(Enterprise).filter(Enterprise.id == req.enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="关联企业不存在")

    try:
        # SQLite Numeric 列返回类型随方言漂移(Decimal/float/str)，统一 Decimal(str(...)) 归一
        enterprise.balance = Decimal(str(enterprise.balance or 0)) + Decimal(str(req.amount))
        req.status = RechargeStatus.APPROVED
        req.reviewed_by = current_user.id
        req.reviewed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(req)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("车队充值审核通过失败(request_id=%s): %s", req_id, e)
        raise HTTPException(status_code=500, detail="审核操作失败，请稍后重试")
    return success_response(_to_dict(req, db), message="审核通过，余额已入账")


@router.post("/{req_id}/reject", summary="驳回")
def reject_recharge(
    req_id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """运营商/管理员驳回充值申请"""
    req = _get_scoped_or_404(db, req_id, current_user)
    _assert_reviewer(db, req, current_user)
    if req.status != RechargeStatus.PENDING:
        raise HTTPException(status_code=409, detail="该申请已处理")

    try:
        req.status = RechargeStatus.REJECTED
        req.remark = body.remark
        req.reviewed_by = current_user.id
        req.reviewed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(req)
    except Exception as e:
        db.rollback()
        logger.error("车队充值驳回失败(request_id=%s): %s", req_id, e)
        raise HTTPException(status_code=500, detail="审核操作失败，请稍后重试")
    return success_response(_to_dict(req, db), message="已驳回")
