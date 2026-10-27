"""企业注册 + 审批 API (卡 c8f7be6f)

公开端点(挂 /auth):
- POST /register/upload-license : 执照上传(magic bytes 防伪造扩展名, ≤10MB)
- POST /register/enterprise     : 企业注册申请(credit_code/手机号/协议校验, 不登录)

审批端点(挂 /admin/registrations, 平台 admin):
- GET ""                   : 申请列表(分页, 含 license file_path)
- POST /{id}/approve       : 建 Subject + ops_company Team + admin User; both 再建
                              maintenance_team; 幂等
- POST /{id}/reject        : 填 review_remark

设计要点:
- /auth/register 已被现有用户注册占用(7 处测试依赖), 企业注册用 /register/enterprise
  子路径, 不破坏既有契约。
- approve 复用申请时密码 hash 作为初始账户密码(不明文回传), 用户用注册时密码登录。
- owner_subject_id 是无 FK 逻辑键(卡 cf614348), approve 建 Subject 后 ops_company/
  maintenance_team 共享同一 subject.id, 实现「同主体多角色」。
"""
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.api.v1.auth import get_password_hash, check_password_byte_length
from app.core.database import get_db
from app.core.rate_limit import limiter, rate_limits
from app.core.response import action_response, paginated_response, success_response
from app.models.registration import (
    ApplyScope,
    RegistrationApplication,
    RegistrationStatus,
)
from app.models.subject import Subject
from app.models.user import Team, TeamType, User, UserRole

logger = logging.getLogger(__name__)


# ─── 常量 ─────────────────────────────────────────────────────────────────────
# 公开注册端点(注册前置, 匿名可访问) → 须加入 auth._PUBLIC_PATH_EXACT 白名单
_MAX_LICENSE_BYTES = 10 * 1024 * 1024  # 10MB
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

# (magic bytes, 推断 mime, 扩展名) —— 校验文件头防伪造扩展名
_LICENSE_MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),      # JPEG
    (b"\x89PNG", "image/png", "png"),            # PNG (89504E47)
    (b"RIFF", "image/webp", "webp"),             # WebP (52494646, RIFF....WEBP)
    (b"%PDF", "application/pdf", "pdf"),         # PDF (25504446)
]

# 执照存放目录(相对 cwd); 测试可 monkeypatch 本模块 _LICENSE_DIR 到 tmp_path
_LICENSE_DIR = os.path.join("uploads", "licenses")

# 统一社会信用代码: 18 位, GB 32100-2015 字符集(不含 I/O/S/V/Z)
_CREDIT_CODE_RE = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{18}$")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_CURRENT_AGREEMENT_VERSION = "platform_terms_v1"


# ─── Pydantic ─────────────────────────────────────────────────────────────────
class EnterpriseRegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    credit_code: str  # 18位格式由业务正则统一校验(长度+字符集), 错误返回 400 而非 422
    license_file_path: Optional[str] = None
    legal_person: Optional[str] = None
    contact_name: str = Field(..., min_length=1, max_length=100)
    contact_phone: str
    contact_email: Optional[EmailStr] = None
    password: str = Field(..., min_length=6)
    apply_scope: ApplyScope = ApplyScope.BOTH
    agreed_to_terms: bool = False

    @field_validator("password")
    @classmethod
    def _check_password_bytes(cls, v: str) -> str:
        # bcrypt 5.0 >72 字节抛 ValueError → 500, 入口统一 400 (卡 d827fd9a)
        return check_password_byte_length(v)


class RejectRequest(BaseModel):
    review_remark: str = Field(..., min_length=1)


# ─── 序列化 ───────────────────────────────────────────────────────────────────
def _app_to_dict(app: RegistrationApplication) -> dict:
    return {
        "id": app.id,
        "company_name": app.company_name,
        "credit_code": app.credit_code,
        "license_file_path": app.license_file_path,
        "legal_person": app.legal_person,
        "contact_name": app.contact_name,
        "contact_phone": app.contact_phone,
        "contact_email": app.contact_email,
        "apply_scope": app.apply_scope.value if hasattr(app.apply_scope, "value") else app.apply_scope,
        "status": app.status.value if hasattr(app.status, "value") else app.status,
        "agreement_version": app.agreement_version,
        "reviewer_id": app.reviewer_id,
        "review_remark": app.review_remark,
        "subject_id": app.subject_id,
        "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
    }


def _build_provisioning(app: RegistrationApplication, db: Session) -> dict:
    """组装审批开通结果(含已建的 Subject/Team/账户信息)。幂等 approve 复用本函数。"""
    result = {
        "application_id": app.id,
        "status": app.status.value if hasattr(app.status, "value") else app.status,
        "subject_id": app.subject_id,
    }
    if app.subject_id:
        ops_team = (
            db.query(Team)
            .filter(Team.owner_subject_id == app.subject_id, Team.type == TeamType.OPS_COMPANY)
            .first()
        )
        maint_team = (
            db.query(Team)
            .filter(
                Team.owner_subject_id == app.subject_id,
                Team.type == TeamType.MAINTENANCE_TEAM,
            )
            .first()
        )
        admin_user = None
        if ops_team:
            result["ops_team_id"] = ops_team.id
            admin_user = (
                db.query(User)
                .filter(User.team_id == ops_team.id, User.role == UserRole.ADMIN)
                .first()
            )
        if maint_team:
            result["maintenance_team_id"] = maint_team.id
        if admin_user:
            result["username"] = admin_user.username
            # 不明文回传密码: 复用申请时密码 hash, 用户用注册时设置的密码登录
            result["password_hint"] = "请使用注册时设置的密码登录"
    return result


# ─── 公开端点(挂 /auth) ───────────────────────────────────────────────────────
router = APIRouter()


@router.post("/register/upload-license")
@limiter.limit(rate_limits["register"])
def upload_license(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """执照上传: content_type + size + magic bytes 三重校验, 存 uploads/licenses/。"""
    # 1. content_type 软校验(声明类型须在白名单内)
    if file.content_type and file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}")

    # 卡7502e6fb 缺陷3: chunked(无 content-length)绕过全局体积限制, read() 前早拒
    if file.size is not None and file.size > _MAX_LICENSE_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 上限")

    content = file.file.read()
    # 2. size 上限
    if len(content) > _MAX_LICENSE_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 10MB 上限")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    # 3. magic bytes 硬校验(防伪造扩展名: 头部字节须命中已知类型)
    detected = None
    for magic, mime, ext in _LICENSE_MAGIC:
        if content.startswith(magic):
            detected = (mime, ext)
            break
    if detected is None:
        raise HTTPException(status_code=400, detail="文件内容与声明类型不符，校验失败")

    detected_mime, ext = detected
    # 4. 落盘 (磁盘故障/权限不足 → 受控 500, 不裸冒泡成通用错误)
    try:
        os.makedirs(_LICENSE_DIR, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.{ext}"
        fpath = os.path.join(_LICENSE_DIR, fname)
        with open(fpath, "wb") as fp:
            fp.write(content)
    except OSError as e:
        logger.error("执照上传落盘失败 mime=%s size=%d: %s", detected_mime, len(content), e)
        raise HTTPException(status_code=500, detail="文件保存失败，请稍后重试")
    return success_response({
        "file_path": fpath,
        "file_name": fname,
        "content_type": detected_mime,
        "size": len(content),
    })


@router.post("/register/enterprise")
@limiter.limit(rate_limits["register"])
def enterprise_register(
    request: Request,
    body: EnterpriseRegisterRequest,
    db: Session = Depends(get_db),
):
    """企业注册申请: 不做登录(登录属另一张卡), 仅落 pending 申请单。"""
    # credit_code 18 位格式
    if not _CREDIT_CODE_RE.match(body.credit_code):
        raise HTTPException(status_code=400, detail="统一社会信用代码格式错误(需18位合法字符)")
    # 手机号格式
    if not _PHONE_RE.match(body.contact_phone):
        raise HTTPException(status_code=400, detail="手机号格式错误")
    # 必须勾选同意协议
    if not body.agreed_to_terms:
        raise HTTPException(status_code=400, detail="必须同意平台协议后方可注册")
    # 唯一: 同 credit_code 已有 pending/approved → 拒绝(rejected 允许重新申请)
    exists = (
        db.query(RegistrationApplication)
        .filter(
            RegistrationApplication.credit_code == body.credit_code,
            RegistrationApplication.status.in_(
                [RegistrationStatus.PENDING, RegistrationStatus.APPROVED]
            ),
        )
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=409,
            detail="该企业已提交申请或已开通，请勿重复注册",
        )

    application = RegistrationApplication(
        company_name=body.company_name,
        credit_code=body.credit_code,
        license_file_path=body.license_file_path,
        legal_person=body.legal_person,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        contact_email=body.contact_email,
        password_hash=get_password_hash(body.password),
        apply_scope=body.apply_scope,
        status=RegistrationStatus.PENDING,
        agreed_to_terms=True,
        agreement_version=_CURRENT_AGREEMENT_VERSION,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return success_response({
        "id": application.id,
        "company_name": application.company_name,
        "status": application.status.value if hasattr(application.status, "value") else application.status,
        "agreement_version": application.agreement_version,
    })


# ─── 审批端点(挂 /admin/registrations, 平台 admin) ──────────────────────────
admin_router = APIRouter()


@admin_router.get("")
def list_registrations(
    status: Optional[str] = Query("pending"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """申请列表(默认 pending), 含 license file_path 供预览, 支持分页。"""
    query = db.query(RegistrationApplication)
    if status:
        query = query.filter(RegistrationApplication.status == status)
    total = query.count()
    items = (
        query.order_by(RegistrationApplication.applied_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated_response([_app_to_dict(a) for a in items], total, page, page_size)


@admin_router.post("/{app_id}/approve")
def approve_registration(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """审批通过: 建 Subject + ops_company Team + admin User; apply_scope 含 maintenance
    时同主体再建 maintenance_team; 幂等(重复 approve 返回已有结果)。"""
    application = (
        db.query(RegistrationApplication)
        .filter(RegistrationApplication.id == app_id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="申请不存在")

    # 幂等: 已通过 → 返回已创建结果(不重复建)
    if application.status == RegistrationStatus.APPROVED:
        return success_response(
            _build_provisioning(application, db),
            message="申请已通过审批(幂等返回)",
        )
    if application.status == RegistrationStatus.REJECTED:
        raise HTTPException(status_code=400, detail="申请已被拒绝，无法通过审批")

    # provisioning 主体: Subject → ops_company Team → (运维 Team) → admin User → 回写申请。
    # 多步 flush 串联无中间 commit, 任一步失败必须整体 rollback —— 否则 identity_map 残留
    # 半成品主体/团队/账户, 且 application 被脏改 APPROVED, 污染后续请求 (幂等误判/假成功)。
    try:
        # 1. 建主体 Subject
        subject = Subject(company_name=application.company_name, credit_code=application.credit_code)
        db.add(subject)
        db.flush()  # 拿 subject.id

        # 2. 建 ops_company Team(owner_subject_id 关联主体)
        ops_team = Team(
            name=f"{application.company_name}-运营公司-{subject.id}",
            type=TeamType.OPS_COMPANY,
            owner_subject_id=subject.id,
        )
        db.add(ops_team)
        db.flush()

        # 3. apply_scope 含 maintenance → 同主体再建 maintenance_team(挂 ops_company 下)
        if application.apply_scope in (ApplyScope.MAINTENANCE, ApplyScope.BOTH):
            maint_team = Team(
                name=f"{application.company_name}-运维团队-{subject.id}",
                type=TeamType.MAINTENANCE_TEAM,
                parent_team_id=ops_team.id,
                owner_subject_id=subject.id,
            )
            db.add(maint_team)
            db.flush()

        # 4. 建企业 admin User(用户名 admin_{subject.id} 保证唯一, 密码复用申请 hash)
        admin_user = User(
            username=f"admin_{subject.id}",
            password_hash=application.password_hash,
            real_name=application.contact_name,
            phone=application.contact_phone,
            email=application.contact_email,
            role=UserRole.ADMIN,
            team_id=ops_team.id,
            status="active",
        )
        db.add(admin_user)
        db.flush()

        # 5. 回写申请
        application.status = RegistrationStatus.APPROVED
        application.reviewer_id = user.id
        application.subject_id = subject.id
        application.reviewed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.error("审批开通失败 app_id=%s", app_id, exc_info=True)
        raise HTTPException(status_code=500, detail="审批开通失败，请稍后重试")
    db.refresh(application)

    return success_response(
        _build_provisioning(application, db),
        message="审批通过，企业账户已开通",
    )


@admin_router.post("/{app_id}/reject")
def reject_registration(
    app_id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_platform_admin),
):
    """拒绝申请: 填 review_remark 理由。"""
    application = (
        db.query(RegistrationApplication)
        .filter(RegistrationApplication.id == app_id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="申请不存在")
    if application.status == RegistrationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="申请已通过审批，无法拒绝")
    if application.status == RegistrationStatus.REJECTED:
        raise HTTPException(status_code=400, detail="申请已被拒绝，无法重复拒绝")

    application.status = RegistrationStatus.REJECTED
    application.reviewer_id = user.id
    application.review_remark = body.review_remark
    application.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return action_response(success=True, message="申请已拒绝")
