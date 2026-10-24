"""企业注册 + 审批: 异常保护 + 匿名访问门 + 边界 (任务卡 8ebfb681)

与 tests/test_enterprise_registration.py (卡 c8f7be6f, 35 例) 互补 —— 后者已充分覆盖
正向契约 (注册校验 / upload magic / 审批建 Team+账户 / 幂等 / 列表分页 / viewer 越权 403)。
本文件聚焦三块**真实缺口**:

1. **异常保护 (任务卡 B 核心)** —— enterprise_registration.py 原零 try/except:
   - upload_license 落盘 IO 故障 (OSError) 不得裸冒泡成通用 500, 须受控明确消息。
   - approve_registration provisioning 多步 flush + commit 串联, 末尾持久化失败必须
     db.rollback() —— 否则 session.identity_map 残留半成品 Subject/Team/User 且
     application 被脏改 APPROVED, 污染后续请求 (幂等误判/假成功)。
2. **匿名访问门** —— 公开端点 (upload/register) 匿名可访问; 审批端点匿名 → 401
   (现有只测 viewer→403, 未覆盖无 token→401)。
3. **边界** —— 空文件 / WebP / magic 决定扩展名 (与声明 content_type 无关) /
   最小 body / reject 缺 remark / reject 不存在申请。
"""
import os

import pytest

from app.api.v1 import enterprise_registration as er_mod
from app.models.registration import RegistrationApplication, RegistrationStatus
from app.models.subject import Subject
from app.models.user import Team, TeamType, User


REGISTER_URL = "/api/v1/auth/register/enterprise"
UPLOAD_URL = "/api/v1/auth/register/upload-license"
ADMIN_BASE = "/api/v1/admin/registrations"

_VALID_CREDIT = "91350100M000100Y4A"  # 18 位合法 (GB 32100-2015 字符集)
_PASSWORD = "Test1234!"


def _payload(**overrides):
    base = {
        "company_name": "测试充电运营公司",
        "credit_code": _VALID_CREDIT,
        "contact_name": "张三",
        "contact_phone": "13800138000",
        "contact_email": "zhangsan@example.com",
        "password": _PASSWORD,
        "apply_scope": "both",
        "agreed_to_terms": True,
    }
    base.update(overrides)
    return base


def _submit(client, **overrides):
    """提交一份注册申请 (公开端点, 无需认证)。"""
    return client.post(REGISTER_URL, json=_payload(**overrides))


def _jpeg():
    return b"\xff\xd8\xff\xe0" + b"\x00jpegbody" * 10


# ─── 异常保护: upload IO 故障 ─────────────────────────────────────────────────
class TestUploadExceptionSafety:
    def test_upload_empty_file_400(self, client, tmp_path, monkeypatch):
        """空文件 (magic 无从匹配) → 400, 不进落盘。"""
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        r = client.post(UPLOAD_URL, files={"file": ("empty.jpg", b"", "image/jpeg")})
        assert r.status_code == 400

    def test_upload_webp_success(self, client, tmp_path, monkeypatch):
        """WebP (RIFF magic) 上传成功 —— 补现有 jpeg/png/pdf 之外格式。"""
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00webpbody" * 10
        r = client.post(UPLOAD_URL, files={"file": ("lic.webp", content, "image/webp")})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["content_type"] == "image/webp"
        assert data["file_name"].endswith(".webp")
        assert os.path.exists(data["file_path"])

    def test_upload_extension_driven_by_magic_not_declared(self, client, tmp_path, monkeypatch):
        """声明 image/jpeg 但内容是 PDF magic → 落盘 ext/mime 由 magic 决定 (防伪造)。"""
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        content = b"%PDF-1.4\n" + b"\x00pdfbody" * 10
        r = client.post(UPLOAD_URL, files={"file": ("lic.jpg", content, "image/jpeg")})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["file_name"].endswith(".pdf")
        assert data["content_type"] == "application/pdf"

    def test_upload_disk_write_failure_returns_500(self, client, tmp_path, monkeypatch):
        """落盘 IO 故障 (OSError) → 受控 500 明确消息, 非裸 global 兜底 '服务器内部错误'。

        无 try/except 时 OSError 冒泡到 global_exception_handler → 通用兜底消息;
        加保护后转 HTTPException(500) 走 http_exception_handler → 明确业务消息。
        """
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))

        def boom(*a, **k):
            raise OSError("无法创建目录 (模拟磁盘故障)")

        monkeypatch.setattr(er_mod.os, "makedirs", boom)
        r = client.post(UPLOAD_URL, files={"file": ("lic.jpg", _jpeg(), "image/jpeg")})
        assert r.status_code == 500
        # 受控业务消息 (测试环境 HTTPException 走默认 handler → {"detail": ...});
        # 无保护时 OSError 裸冒泡, TestClient 直接抛 ServerError 拿不到响应。
        assert "文件保存" in r.json()["detail"]


# ─── 异常保护: approve provisioning 事务回滚 (核心) ───────────────────────────
class TestApproveExceptionSafety:
    def test_approve_commit_failure_rolls_back(self, client, db_session, monkeypatch):
        """provisioning 末尾 commit 持久化失败 → 必须 db.rollback() 清理 session。

        无保护时 RuntimeError 冒泡且 session 不回滚 → application 脏改 APPROVED +
        identity_map 残留半成品, 重试 approve 走幂等分支返回假成功 (DB 实际未落库)
        或因脏状态报错。加保护 rollback 后, 重试能正常开通。
        """
        _submit(client)
        app = db_session.query(RegistrationApplication).first()

        orig_commit = db_session.commit
        calls = []

        def flaky_commit():
            if not calls:
                calls.append(1)
                raise RuntimeError("首次 commit 持久化故障")
            return orig_commit()

        monkeypatch.setattr(db_session, "commit", flaky_commit)

        # 第一次 approve: commit 故障 → 500 + rollback
        r1 = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r1.status_code == 500
        assert "审批开通" in r1.json()["detail"]

        # 重试 approve: session 已回滚干净 → 正常开通 (非幂等假成功)
        r2 = client.post(f"{ADMIN_BASE}/{app.id}/approve")
        assert r2.status_code == 200, r2.text
        d2 = r2.json()["data"]
        assert d2["status"] == "approved"
        assert d2.get("ops_team_id") is not None
        assert d2.get("username", "").startswith("admin_")

        # DB 真实落库 (仅一份, 非首次 flush 的脏数据): 1 主体 + 1 ops_company Team
        db_session.expire_all()
        assert db_session.query(Subject).count() == 1
        assert (
            db_session.query(Team).filter(Team.type == TeamType.OPS_COMPANY).count() == 1
        )

    def test_approve_commit_failure_no_partial_db_rows(self, client, db_session, monkeypatch):
        """commit 失败回滚后, DB 不留半成品 Subject / Team (无脏企业开通数据)。"""
        _submit(client)
        app = db_session.query(RegistrationApplication).first()

        def boom():
            raise RuntimeError("commit 持久化故障")

        monkeypatch.setattr(db_session, "commit", boom)
        client.post(f"{ADMIN_BASE}/{app.id}/approve")  # 500

        db_session.rollback()  # 强制清事务 (防御, 兼容有无保护两种实现)
        db_session.expire_all()
        assert db_session.query(Subject).count() == 0
        assert db_session.query(Team).filter(Team.owner_subject_id.isnot(None)).count() == 0


# ─── 匿名访问门 ─────────────────────────────────────────────────────────────────
class TestAnonymousAccessGate:
    def test_anonymous_can_register(self, anon_client):
        """注册申请是公开端点 (注册前置) → 匿名可访问。"""
        r = anon_client.post(REGISTER_URL, json=_payload())
        assert r.status_code == 200

    def test_anonymous_can_upload(self, anon_client, tmp_path, monkeypatch):
        """执照上传是公开端点 → 匿名可访问。"""
        monkeypatch.setattr(er_mod, "_LICENSE_DIR", str(tmp_path))
        r = anon_client.post(
            UPLOAD_URL, files={"file": ("lic.jpg", _jpeg(), "image/jpeg")}
        )
        assert r.status_code == 200

    def test_anonymous_approve_401(self, anon_client):
        r = anon_client.post(f"{ADMIN_BASE}/1/approve")
        assert r.status_code == 401

    def test_anonymous_reject_401(self, anon_client):
        r = anon_client.post(f"{ADMIN_BASE}/1/reject", json={"review_remark": "x"})
        assert r.status_code == 401

    def test_anonymous_list_401(self, anon_client):
        r = anon_client.get(ADMIN_BASE)
        assert r.status_code == 401


# ─── 注册 / 拒绝 边界 ──────────────────────────────────────────────────────────
class TestRegisterAndRejectBoundaries:
    def test_register_minimal_body_200(self, anon_client):
        """仅必填字段 (company/credit/contact_name/phone/password/agreed) → 200。"""
        minimal = {
            "company_name": "最小公司",
            "credit_code": "91350100M000100Y4A",
            "contact_name": "李四",
            "contact_phone": "13800138001",
            "password": _PASSWORD,
            "agreed_to_terms": True,
        }
        r = anon_client.post(REGISTER_URL, json=minimal)
        assert r.status_code == 200, r.text

    def test_register_missing_contact_name_422(self, anon_client):
        body = {k: v for k, v in _payload().items() if k != "contact_name"}
        r = anon_client.post(REGISTER_URL, json=body)
        assert r.status_code == 422

    def test_reject_missing_remark_422(self, client, db_session):
        """reject 缺 review_remark (Pydantic min_length=1) → 422。"""
        _submit(client)
        app = db_session.query(RegistrationApplication).first()
        r = client.post(f"{ADMIN_BASE}/{app.id}/reject", json={})
        assert r.status_code == 422

    def test_reject_not_found_404(self, client):
        r = client.post(
            f"{ADMIN_BASE}/99999/reject", json={"review_remark": "不存在"}
        )
        assert r.status_code == 404
