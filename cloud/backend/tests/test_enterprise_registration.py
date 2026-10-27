"""tests/test_enterprise_registration.py — 企业注册 + 审批 (卡 c8f7be6f)

覆盖:
- 注册校验: credit_code 格式 / 手机号格式 / 重复拒绝 / 未勾选协议拒绝
- 执照上传: magic bytes 防伪造 / size 上限 / content_type 白名单
- 审批权限: 非平台 admin 403 (approve/reject/list)
- 审批建 Team + 账户: Subject / ops_company Team / owner_subject_id 关联 / admin 账户
- apply_scope=both 同时建 maintenance_team (同主体)
- 审批幂等: 重复 approve 不重复创建
"""
import os

import bcrypt
import pytest

from app.api.v1 import enterprise_registration as er_mod
from app.models.registration import (
    ApplyScope,
    RegistrationApplication,
    RegistrationStatus,
)
from app.models.subject import Subject
from app.models.user import Team, TeamType, User, UserRole


REGISTER_URL = "/api/v1/auth/register/enterprise"
UPLOAD_URL = "/api/v1/auth/register/upload-license"
ADMIN_BASE = "/api/v1/admin/registrations"

_VALID_CREDIT_1 = "91350100M000100Y4A"  # 18 位合法(GB 32100-2015 字符集)
_VALID_CREDIT_2 = "91350100M000100Y4B"
_VALID_PHONE = "13800138000"
_PASSWORD = "Test1234!"


def _payload(**overrides):
    base = {
        "company_name": "测试充电运营公司",
        "credit_code": _VALID_CREDIT_1,
        "contact_name": "张三",
        "contact_phone": _VALID_PHONE,
        "contact_email": "zhangsan@example.com",
        "password": _PASSWORD,
        "apply_scope": "both",
        "agreed_to_terms": True,
    }
    base.update(overrides)
    return base


def _submit(client, **overrides):
    """提交一份注册申请, 返回 (response, RegistrationApplication)。"""
    r = client.post(REGISTER_URL, json=_payload(**overrides))
    return r


def _login_as(client, db_session, username, password, role):
    """建一个指定角色用户并登录, 返回其 token (供越权测试切换 header)。"""
    db_session.add(User(
        username=username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        role=role,
        status="active",
    ))
    db_session.commit()
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


# ─── 注册校验 ─────────────────────────────────────────────────────────────────
class TestRegisterValidation:
    def test_register_success(self, client, db_session):
        r = _submit(client)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] == "pending"
        assert data["agreement_version"] == "platform_terms_v1"
        # 落库
        app = db_session.query(RegistrationApplication).first()
        assert app is not None
        assert app.company_name == "测试充电运营公司"
        assert app.credit_code == _VALID_CREDIT_1
        assert app.agreed_to_terms is True
        assert app.status == RegistrationStatus.PENDING
        # 密码 bcrypt hash
        assert app.password_hash.startswith("$2")

    @pytest.mark.parametrize("bad_code", [
        "12345",                       # 长度不足
        "91350100M000100Y4",           # 17 位
        "91350100M000100Y4AB1",        # 19 位
        "91350100M000100Y4I",          # 含非法字符 I
        "91350100M000100Y4O",          # 含非法字符 O
    ])
    def test_register_reject_bad_credit_code(self, client, bad_code):
        r = _submit(client, credit_code=bad_code)
        assert r.status_code == 400, f"{bad_code} 应被拒"

    def test_register_reject_bad_phone(self, client):
        r = _submit(client, contact_phone="12345")
        assert r.status_code == 400
        r2 = _submit(client, contact_phone="10800138000", credit_code=_VALID_CREDIT_2)
        assert r2.status_code == 400

    def test_register_reject_duplicate_pending(self, client):
        assert _submit(client).status_code == 200
        # 同 credit_code 已有 pending → 409
        r2 = _submit(client)
        assert r2.status_code == 409

    def test_register_reject_duplicate_approved(self, client, db_session):
        assert _submit(client).status_code == 200
        app = db_session.query(RegistrationApplication).first()
        # 先 approve
        r = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r.status_code == 200
        # 同 credit_code 已 approved → 409
        r2 = _submit(client)
        assert r2.status_code == 409

    def test_register_rejected_credit_code_can_reapply(self, client, db_session):
        """rejected 状态的 credit_code 允许重新申请 (非 pending/approved)。"""
        assert _submit(client).status_code == 200
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/reject", json={"review_remark": "资质不符"})
        # 同 credit_code 重新申请 → 允许
        r2 = _submit(client)
        assert r2.status_code == 200

    def test_register_reject_no_agreement(self, client):
        r = _submit(client, agreed_to_terms=False)
        assert r.status_code == 400

    def test_register_reject_bad_email(self, client):
        # EmailStr 校验 → 422
        r = _submit(client, contact_email="not-an-email", credit_code=_VALID_CREDIT_2)
        assert r.status_code == 422


# ─── 执照上传 ─────────────────────────────────────────────────────────────────
class TestUploadLicense:
    def test_upload_jpeg_success(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"\xff\xd8\xff\xe0" + b"\x00jpegbody" * 10
        r = client.post(UPLOAD_URL, files={"file": ("license.jpg", content, "image/jpeg")})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["content_type"] == "image/jpeg"
        assert os.path.exists(data["file_path"])

    def test_upload_png_success(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"\x89PNG\r\n\x1a\n" + b"\x00pngbody" * 10
        r = client.post(UPLOAD_URL, files={"file": ("license.png", content, "image/png")})
        assert r.status_code == 200
        assert r.json()["data"]["content_type"] == "image/png"

    def test_upload_pdf_success(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"%PDF-1.4\n" + b"\x00pdfbody" * 10
        r = client.post(UPLOAD_URL, files={"file": ("license.pdf", content, "application/pdf")})
        assert r.status_code == 200
        assert r.json()["data"]["content_type"] == "application/pdf"

    def test_upload_reject_forged_extension(self, client, tmp_path, monkeypatch):
        """txt 内容声明 jpeg → magic bytes 不符 → 400 (防伪造扩展名)"""
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"this is plain text, not an image" * 5
        r = client.post(UPLOAD_URL, files={"file": ("fake.jpg", content, "image/jpeg")})
        assert r.status_code == 400

    def test_upload_reject_oversize(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"\xff\xd8\xff\xe0" + b"\x00" * (10 * 1024 * 1024 + 1)
        r = client.post(UPLOAD_URL, files={"file": ("big.jpg", content, "image/jpeg")})
        # 卡7502e6fb: read() 前 file.size 早拒, 400 → 413
        assert r.status_code == 413

    def test_upload_reject_bad_content_type(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        r = client.post(UPLOAD_URL, files={"file": ("a.zip", b"PK\x03\x04", "application/zip")})
        assert r.status_code == 400


# ─── 审批权限 / 越权 ──────────────────────────────────────────────────────────
class TestApprovalAuthorization:
    def test_approve_requires_platform_admin(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        token = _login_as(client, db_session, "viewer_a", "v123456", UserRole.VIEWER)
        client.headers["Authorization"] = f"Bearer {token}"
        r = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r.status_code == 403
        # 状态未变
        db_session.expire_all()
        assert db_session.query(RegistrationApplication).first().status == RegistrationStatus.PENDING

    def test_reject_requires_platform_admin(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        token = _login_as(client, db_session, "viewer_b", "v123456", UserRole.VIEWER)
        client.headers["Authorization"] = f"Bearer {token}"
        r = client.post(f"{ADMIN_BASE}/{app.id}/reject", json={"review_remark": "x"})
        assert r.status_code == 403

    def test_list_requires_platform_admin(self, client, db_session):
        token = _login_as(client, db_session, "viewer_c", "v123456", UserRole.VIEWER)
        client.headers["Authorization"] = f"Bearer {token}"
        r = client.get(ADMIN_BASE)
        assert r.status_code == 403

    def test_engineer_not_platform_admin(self, client, db_session):
        """工程师同样不可审批 (仅 platform admin)。"""
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        token = _login_as(client, db_session, "eng_a", "e123456", UserRole.ENGINEER)
        client.headers["Authorization"] = f"Bearer {token}"
        r = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r.status_code == 403


# ─── 审批建 Team + 账户 ──────────────────────────────────────────────────────
class TestApproveProvisioning:
    def test_approve_creates_subject_team_account(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()

        r = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r.status_code == 200, r.text
        data = r.json()["data"]

        # Subject 建
        subject = db_session.query(Subject).first()
        assert subject is not None
        assert subject.company_name == "测试充电运营公司"
        assert subject.credit_code == _VALID_CREDIT_1

        # ops_company Team, type 正确, owner_subject_id 关联主体
        ops_team = (
            db_session.query(Team)
            .filter(Team.type == TeamType.OPS_COMPANY)
            .first()
        )
        assert ops_team is not None
        assert ops_team.owner_subject_id == subject.id
        assert data["ops_team_id"] == ops_team.id
        assert data["subject_id"] == subject.id

        # 企业 admin 账户 (区别于 seed 的 platform admin)
        admin_user = (
            db_session.query(User)
            .filter(User.username == data["username"])
            .first()
        )
        assert admin_user is not None
        assert admin_user.role == UserRole.ADMIN
        assert admin_user.team_id == ops_team.id

        # 申请单回写
        db_session.expire_all()
        app2 = db_session.query(RegistrationApplication).first()
        assert app2.status == RegistrationStatus.APPROVED
        assert app2.subject_id == subject.id
        assert app2.reviewer_id is not None

    def test_approve_login_with_applied_password(self, client, db_session):
        """approve 复用申请密码 hash, 用户用注册时密码可登录。"""
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        r = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        username = r.json()["data"]["username"]
        r_login = client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": _PASSWORD},
        )
        assert r_login.status_code == 200
        assert r_login.json()["data"]["user"]["username"] == username

    def test_approve_both_creates_maintenance_team(self, client, db_session):
        _submit(client, apply_scope="both")
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/approve")

        ops_team = db_session.query(Team).filter(Team.type == TeamType.OPS_COMPANY).first()
        maint = db_session.query(Team).filter(Team.type == TeamType.MAINTENANCE_TEAM).first()
        assert maint is not None
        # 同主体关联
        assert maint.owner_subject_id == ops_team.owner_subject_id
        assert maint.owner_subject_id is not None
        # 挂在 ops_company 下
        assert maint.parent_team_id == ops_team.id

    def test_approve_ops_only_no_maintenance(self, client, db_session):
        _submit(client, apply_scope="ops")
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/approve")
        ops_team = db_session.query(Team).filter(Team.type == TeamType.OPS_COMPANY).first()
        assert ops_team is not None
        assert db_session.query(Team).filter(Team.type == TeamType.MAINTENANCE_TEAM).first() is None

    def test_approve_maintenance_scope(self, client, db_session):
        """apply_scope=maintenance: 建 ops_company + maintenance_team (主体仍需 ops 作挂载根)。"""
        _submit(client, apply_scope="maintenance")
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/approve")
        ops_team = db_session.query(Team).filter(Team.type == TeamType.OPS_COMPANY).first()
        maint = db_session.query(Team).filter(Team.type == TeamType.MAINTENANCE_TEAM).first()
        assert ops_team is not None
        assert maint is not None

    def test_approve_idempotent(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        r1 = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r1.status_code == 200
        username1 = r1.json()["data"]["username"]

        subject_count = db_session.query(Subject).count()
        ops_count = db_session.query(Team).filter(Team.type == TeamType.OPS_COMPANY).count()
        new_admin_count = db_session.query(User).filter(User.username.like("admin_%")).count()

        # 重复 approve → 幂等, 不重复创建
        r2 = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r2.status_code == 200
        assert r2.json()["data"]["username"] == username1

        assert db_session.query(Subject).count() == subject_count
        assert db_session.query(Team).filter(Team.type == TeamType.OPS_COMPANY).count() == ops_count
        assert (
            db_session.query(User).filter(User.username.like("admin_%")).count()
            == new_admin_count
        )

    def test_approve_not_found(self, client):
        r = client.post(f"{ADMIN_BASE}/99999/approve")
        assert r.status_code == 404

    def test_approve_rejected_application_fails(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/reject", json={"review_remark": "不行"})
        r = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r.status_code == 400


# ─── 拒绝 + 列表 ────────────────────────────────────────────────────────────
class TestRejectAndList:
    def test_reject(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        r = client.post(f"{ADMIN_BASE}/{app.id}/reject", json={"review_remark": "资质不符"})
        assert r.status_code == 200, r.text
        db_session.expire_all()
        app2 = db_session.query(RegistrationApplication).first()
        assert app2.status == RegistrationStatus.REJECTED
        assert app2.review_remark == "资质不符"
        assert app2.reviewer_id is not None
        assert app2.reviewed_at is not None

    def test_reject_approved_fails(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/approve")
        r = client.post(f"{ADMIN_BASE}/{app.id}/reject", json={"review_remark": "x"})
        assert r.status_code == 400

    def test_list_pending_default(self, client, db_session):
        _submit(client, credit_code=_VALID_CREDIT_1, contact_phone="13800138001")
        _submit(client, credit_code=_VALID_CREDIT_2, contact_phone="13800138002")
        r = client.get(ADMIN_BASE)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 2
        assert len(data["items"]) >= 2
        assert all(it["status"] == "pending" for it in data["items"])
        # 含 license file_path 字段(可预览)
        assert "license_file_path" in data["items"][0]
        assert "credit_code" in data["items"][0]

    def test_list_pagination(self, client, db_session):
        codes = [
            "91350100M000100Y4A", "91350100M000100Y4B",
            "91350100M000100Y4C", "91350100M000100Y4D",
            "91350100M000100Y4E",
        ]
        phones = ["13800138001", "13800138002", "13800138003", "13800138004", "13800138005"]
        for code, phone in zip(codes, phones):
            _submit(client, credit_code=code, contact_phone=phone)
        r = client.get(f"{ADMIN_BASE}?page=1&page_size=2")
        data = r.json()["data"]
        assert data["total"] >= 5
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        # 第二页
        r2 = client.get(f"{ADMIN_BASE}?page=2&page_size=2")
        assert len(r2.json()["data"]["items"]) == 2

    def test_list_filter_by_status(self, client, db_session):
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        client.post(f"{ADMIN_BASE}/{app.id}/approve")
        # approved 过滤
        r = client.get(f"{ADMIN_BASE}?status=approved")
        data = r.json()["data"]
        assert data["total"] >= 1
        assert all(it["status"] == "approved" for it in data["items"])
        # pending 过滤为空
        r2 = client.get(f"{ADMIN_BASE}?status=pending")
        assert r2.json()["data"]["total"] == 0
