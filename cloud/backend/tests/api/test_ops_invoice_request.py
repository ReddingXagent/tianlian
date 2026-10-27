"""运营-手动开票 API 测试 (用户端云端契约 §5.4, 工作卡 a09f8a21)

覆盖 app/api/v1/operate/ops_invoice_request.py (挂 /api/v1/ops 前缀):
- GET  /ops/invoice-requests                  待开票/全部列表 (按 team 隔离)
- POST /ops/invoice-requests/{id}/upload      multipart 上传发票文件 → ISSUED + 通知
- POST /ops/invoice-requests/{id}/reject      拒绝开票 → REJECTED + 通知

权限门: router-level require_permission("operate:manage") —— admin 恒通过,
operator/engineer 持有, viewer/auditor 不持 → 403; 匿名 → 401。
team scoping: invoice_request.team_id (创建时由订单 station→team 捕获);
admin 平台级豁免, 跨团队 → 404 (不泄露存在)。运营侧统一 success_response (code=200)。
"""
import os
import uuid

import bcrypt
import pytest
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter
from app.models.invoice_request import InvoiceRequest, InvoiceRequestStatus
from app.models.user import UserRole, User, Team
import app.services.invoice_notification as notif
import app.services.invoice_request_service as svc

OPS_URL = "/api/v1/ops/invoice-requests"


# ─── helpers ───

def _add_user(session, username, role=UserRole.OPERATOR, team_id=None, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_request(
    session,
    *,
    user_id,
    team_id,
    status=InvoiceRequestStatus.PENDING,
    amount=1000,
    title_name="张三",
    email=None,
    tax_number=None,
):
    """直接落一条 InvoiceRequest (绕过申请流程, 模拟任意状态/team)。"""
    r = InvoiceRequest(
        order_ids=f'["ord_{uuid.uuid4().hex[:8]}"]',
        user_id=user_id,
        team_id=team_id,
        title_type="personal",
        title_name=title_name,
        tax_number=tax_number,
        email=email,
        amount=amount,
        status=status,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _pdf(name="f.pdf"):
    return ("file", (name, b"%PDF-1.4 fake pdf body", "application/pdf"))


# ─── 两团队 + 两 operator + 一 C 端申请人 脚手架 ───

@pytest.fixture
def two_teams(client):
    s = client._sesh
    h = uuid.uuid4().hex[:6]
    ta = Team(name=f"INV团队A{h}", code=f"INVA{h}")
    tb = Team(name=f"INV团队B{h}", code=f"INVB{h}")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    cu = _add_user(s, f"inv_cu_{h}", UserRole.VIEWER)  # C 端申请人 (无 team)
    op_a = _add_user(s, f"inv_op_a_{h}", UserRole.OPERATOR, team_id=ta.id)
    op_b = _add_user(s, f"inv_op_b_{h}", UserRole.OPERATOR, team_id=tb.id)
    return {
        "s": s, "ta": ta, "tb": tb, "cu": cu, "op_a": op_a, "op_b": op_b, "h": h,
        "token_a": _login_token(client, f"inv_op_a_{h}"),
        "token_b": _login_token(client, f"inv_op_b_{h}"),
    }


# ==================== B1. 列表 team scoping ====================

class TestListRequests:
    """GET /ops/invoice-requests —— admin 全可见, team 级仅本 team。"""

    def test_admin_sees_all_teams(self, client, two_teams):
        t = two_teams
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id, title_name="A队申请")
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["tb"].id, title_name="B队申请")
        r = client.get(OPS_URL)  # admin (client 默认 token)
        assert r.status_code == 200
        assert r.json()["code"] == 200
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert {"A队申请", "B队申请"} <= names

    def test_team_user_sees_only_own_team(self, client, two_teams):
        t = two_teams
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id, title_name="A队申请")
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["tb"].id, title_name="B队申请")
        r = client.get(OPS_URL, headers=_auth(t["token_a"]))
        assert r.status_code == 200
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert "A队申请" in names
        assert "B队申请" not in names  # 跨 team 隔离

    def test_filter_by_status(self, client, two_teams):
        t = two_teams
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                      status=InvoiceRequestStatus.PENDING, title_name="待开")
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                      status=InvoiceRequestStatus.ISSUED, title_name="已开")
        r = client.get(OPS_URL, params={"status": "pending"}, headers=_auth(t["token_a"]))
        names = {i["title_name"] for i in r.json()["data"]["items"]}
        assert names == {"待开"}

    def test_list_item_contract_structure(self, client, two_teams):
        """列表项结构对齐契约 §5.4 (金额/抬头/税号/订单明细 + amount_yuan)。"""
        t = two_teams
        _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                      amount=12800, title_name="某某公司",
                      tax_number="91110000XXXXXXXX", email="u@e.com")
        r = client.get(OPS_URL, headers=_auth(t["token_a"]))
        item = r.json()["data"]["items"][0]
        for key in (
            "id", "status", "amount", "amount_yuan", "title_type", "title_name",
            "tax_number", "order_ids", "invoice_mode", "applied_at",
        ):
            assert key in item, f"列表项缺字段 {key}"
        assert item["amount_yuan"] == 128.0  # 12800 分 → 128.00 元
        assert item["tax_number"] == "91110000XXXXXXXX"


# ==================== B2. 上传发票文件 → ISSUED (契约 §5.4) ====================

class TestUpload:
    """POST /ops/invoice-requests/{id}/upload —— magic bytes 校验 + 落盘 → ISSUED。"""

    def test_upload_pdf_to_issued(self, client, two_teams, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "issued"
        assert d["invoice_file_type"] == "pdf"
        assert d["reviewed_by"] == t["op_a"].id
        # 文件真实落盘
        t["s"].expire_all()
        fresh = t["s"].query(InvoiceRequest).filter(InvoiceRequest.id == req.id).first()
        assert fresh.invoice_file_path
        assert os.path.exists(fresh.invoice_file_path)

    def test_upload_image_jpeg(self, client, two_teams, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.jpg", b"\xff\xd8\xffjpegdata", "image/jpeg")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 200
        assert r.json()["data"]["invoice_file_type"] == "image"

    def test_upload_ofd(self, client, two_teams, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.ofd", b"PK\x03\x04zipdata", "application/ofd")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 200
        assert r.json()["data"]["invoice_file_type"] == "ofd"

    def test_upload_wrong_magic_400(self, client, two_teams):
        """声明 pdf 但内容无 PDF magic → 400 (防伪造扩展名)。"""
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.pdf", b"plain text not pdf", "application/pdf")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 400

    def test_upload_bad_content_type_400(self, client, two_teams):
        """content_type 不在白名单 → 400。"""
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.exe", b"%PDF-1.4", "application/x-msdownload")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 400

    def test_upload_oversize_400(self, client, two_teams, monkeypatch):
        """超过 10MB 上限 → 413 (卡7502e6fb 早拒; 用小阈值模拟, 避免构造 10MB body)。"""
        monkeypatch.setattr(svc, "MAX_INVOICE_FILE_BYTES", 10)
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.pdf", b"%PDF" + b"x" * 50, "application/pdf")},
            headers=_auth(t["token_a"]),
        )
        # 卡7502e6fb: read() 前 file.size 早拒, 400 → 413
        assert r.status_code == 413

    def test_upload_non_pending_400(self, client, two_teams, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                            status=InvoiceRequestStatus.ISSUED)
        r = client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 400

    def test_upload_cross_team_404(self, client, two_teams, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)  # 属 A 队
        r = client.post(  # B 队 operator 越权上传
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_auth(t["token_b"]),
        )
        assert r.status_code == 404

    def test_upload_unknown_404(self, client, two_teams):
        t = two_teams
        r = client.post(
            f"{OPS_URL}/999999/upload",
            files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_auth(t["token_a"]),
        )
        assert r.status_code == 404

    def test_upload_triggers_notification(self, client, two_teams, tmp_path, monkeypatch):
        """ISSUED 后触发 notify_invoice_issued (契约 §5.5)。"""
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        called = {}
        monkeypatch.setattr(notif, "notify_invoice_issued", lambda r, file_url=None, db=None, openid=None: called.setdefault("ok", True))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        client.post(
            f"{OPS_URL}/{req.id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_auth(t["token_a"]),
        )
        assert called.get("ok") is True


# ==================== B3. 拒绝开票 → REJECTED (契约 §5.4) ====================

class TestReject:
    """POST /ops/invoice-requests/{id}/reject —— 仅 PENDING 可拒绝。"""

    def test_reject_to_rejected(self, client, two_teams):
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/reject",
            json={"reject_reason": "材料不全"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "rejected"
        assert d["reject_reason"] == "材料不全"
        assert d["reviewed_by"] == t["op_a"].id

    def test_reject_empty_reason_422(self, client, two_teams):
        """空拒绝原因 → 422 (Pydantic min_length=1)。"""
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/reject",
            json={"reject_reason": ""}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 422

    def test_reject_whitespace_reason_422(self, client, two_teams):
        """纯空格拒绝原因 → 422 (service 层 strip 校验)。"""
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/reject",
            json={"reject_reason": "   "}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 422

    def test_reject_non_pending_400(self, client, two_teams):
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                            status=InvoiceRequestStatus.ISSUED)
        r = client.post(
            f"{OPS_URL}/{req.id}/reject",
            json={"reject_reason": "x"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 400

    def test_reject_cross_team_404(self, client, two_teams):
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        r = client.post(
            f"{OPS_URL}/{req.id}/reject",
            json={"reject_reason": "x"}, headers=_auth(t["token_b"]),
        )
        assert r.status_code == 404

    def test_reject_triggers_notification(self, client, two_teams, monkeypatch):
        """REJECTED 后触发 notify_invoice_rejected (契约 §5.5, 卡4b14971e)。"""
        called = {}
        monkeypatch.setattr(notif, "notify_invoice_rejected", lambda r, db=None, openid=None: called.setdefault("ok", True))
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id)
        client.post(
            f"{OPS_URL}/{req.id}/reject",
            json={"reject_reason": "材料不全"}, headers=_auth(t["token_a"]),
        )
        assert called.get("ok") is True


# ==================== B4. 权限门 (router-level operate:manage) ====================

class TestPermissionGate:
    """viewer 不持 operate:manage → 403; 匿名 → 401。"""

    @pytest.fixture
    def viewer_token(self, client):
        h = uuid.uuid4().hex[:6]
        _add_user(client._sesh, f"inv_viewer_{h}", UserRole.VIEWER)
        return _login_token(client, f"inv_viewer_{h}")

    def test_viewer_list_403(self, client, viewer_token):
        r = client.get(OPS_URL, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_upload_403(self, client, viewer_token):
        r = client.post(
            f"{OPS_URL}/1/upload",
            files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")},
            headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    def test_viewer_reject_403(self, client, viewer_token):
        r = client.post(
            f"{OPS_URL}/1/reject",
            json={"reject_reason": "x"}, headers=_auth(viewer_token),
        )
        assert r.status_code == 403

    def test_anonymous_401(self, client):
        client.headers.pop("Authorization", None)
        r = client.get(OPS_URL)
        assert r.status_code == 401


# ==================== B5. rate limit 防洪水 (卡 669d54ac) ====================

class TestRateLimit:
    """ops 开票三端点 rate limit (conftest 默认关闭, 本类 monkeypatch 开启 limiter)。

    文件上传端点 (10MB, 磁盘 IO) 严格 10/min; reject 30/min; list 60/min。
    参考 test_business_rate_limit.py 既定模式: 打满配额后下一次 429。
    """

    @pytest.fixture
    def enable_rate_limit(self, client: TestClient, monkeypatch):
        """开启 limiter 并为 conftest app 补齐 SlowAPI handler (RateLimitExceeded → 429)。"""
        limiter.reset()
        monkeypatch.setattr(limiter, "enabled", True)
        client.app.state.limiter = limiter
        client.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        yield
        limiter.reset()

    def test_upload_rate_limit_429(self, client, two_teams, enable_rate_limit):
        """上传发票文件限流 10/min: 第 11 次返回 429 (磁盘 IO 洪水防护)。

        用不存在 invoice_id 打满配额 —— 限流装饰器在端点执行前消耗配额,
        前 10 次业务返回 404 (不污染真实 InvoiceRequest 状态机), 第 11 次 429。
        """
        t = two_teams
        headers = _auth(t["token_a"])
        files = {"file": ("f.pdf", b"%PDF-1.4", "application/pdf")}
        codes = []
        for _ in range(11):
            r = client.post(f"{OPS_URL}/999999/upload", files=files, headers=headers)
            codes.append(r.status_code)

        assert all(c != 429 for c in codes[:10]), f"前 10 次不应限流, 实际: {codes}"
        assert codes[10] == 429, f"第 11 次应 429, 实际: {codes}"

    def test_reject_rate_limit_429(self, client, two_teams, enable_rate_limit):
        """拒绝开票限流 30/min: 第 31 次返回 429。

        用合法 reason + 不存在 invoice_id: 限流装饰器包裹端点函数, 端点内抛 404
        时配额已消耗 (不污染真实 InvoiceRequest 状态机)。注意不能用非法 body
        触发 422 —— Pydantic body 校验先于 slowapi 限流执行, 配额不会消耗。
        """
        t = two_teams
        headers = _auth(t["token_a"])
        codes = []
        for _ in range(31):
            r = client.post(
                f"{OPS_URL}/999999/reject",
                json={"reject_reason": "测试拒绝"}, headers=headers,
            )
            codes.append(r.status_code)

        assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
        assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"

    def test_list_rate_limit_429(self, client, two_teams, enable_rate_limit):
        """开票申请列表限流 60/min: 第 61 次返回 429。"""
        t = two_teams
        headers = _auth(t["token_a"])
        codes = []
        for _ in range(61):
            r = client.get(OPS_URL, headers=headers)
            codes.append(r.status_code)

        assert all(c != 429 for c in codes[:60]), f"前 60 次不应限流, 实际: {codes}"
        assert codes[60] == 429, f"第 61 次应 429, 实际: {codes}"

    def test_void_rate_limit_429(self, client, two_teams, enable_rate_limit):
        """红冲限流 30/min: 第 31 次返回 429。

        与 reject 同模式: 合法 body + 不存在 invoice_id, 限流装饰器在端点内
        404 前已消耗配额, 不污染真实状态机。
        """
        t = two_teams
        headers = _auth(t["token_a"])
        codes = []
        for _ in range(31):
            r = client.post(
                f"{OPS_URL}/999999/void",
                json={"reason": "开票信息有误"}, headers=headers,
            )
            codes.append(r.status_code)

        assert all(c != 429 for c in codes[:30]), f"前 30 次不应限流, 实际: {codes}"
        assert codes[30] == 429, f"第 31 次应 429, 实际: {codes}"


# ==================== B6. 红冲 void (Phase2-B2, 卡 f42bdf5a) ====================

class TestVoid:
    """POST /ops/invoice-requests/{id}/void —— 红冲已开发票 (R1 方案b: status 三态不变,
    issued 发票加 voided 标记字段)。

    守卫: 仅 ISSUED 可红冲; 已红冲重复红冲 → 400 (防误操作覆盖首红冲记录);
    reason 必填; team 隔离同 upload/reject (跨团队 404); 红冲不动金额/发票文件。
    """

    def _seed_issued(self, t, **kw):
        """落一条 ISSUED 申请 (含发票文件信息, 模拟已上传开具)。"""
        kw.setdefault("status", InvoiceRequestStatus.ISSUED)
        r = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id, **kw)
        r.invoice_file_path = "/tmp/fake_invoice.pdf"
        r.invoice_file_name = "f.pdf"
        r.invoice_file_type = "pdf"
        t["s"].commit()
        t["s"].refresh(r)
        return r

    def test_void_issued_ok(self, client, two_teams):
        """红冲 issued 发票 → 200; status 保持 issued + voided=true + 审计三件套。"""
        t = two_teams
        req = self._seed_issued(t)
        r = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "开票信息有误"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "issued"       # R1 方案b: 状态机三态不变
        assert d["voided"] is True
        assert d["void_reason"] == "开票信息有误"
        assert d["voided_by"] == t["op_a"].id
        assert d["voided_at"]                # ISO8601 字符串
        # DB 落库核实
        t["s"].expire_all()
        fresh = t["s"].query(InvoiceRequest).filter(InvoiceRequest.id == req.id).first()
        assert fresh.voided is True
        assert fresh.void_reason == "开票信息有误"
        assert fresh.voided_by == t["op_a"].id
        assert fresh.voided_at is not None
        # 金额/发票文件不动
        assert fresh.amount == 1000
        assert fresh.invoice_file_path == "/tmp/fake_invoice.pdf"

    def test_void_pending_400(self, client, two_teams):
        """非 issued (pending) → 400。"""
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                            status=InvoiceRequestStatus.PENDING)
        r = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "x"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 400

    def test_void_rejected_400(self, client, two_teams):
        """非 issued (rejected) → 400。"""
        t = two_teams
        req = _seed_request(t["s"], user_id=t["cu"].id, team_id=t["ta"].id,
                            status=InvoiceRequestStatus.REJECTED)
        r = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "x"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 400

    def test_void_twice_400(self, client, two_teams):
        """重复红冲 → 400 (锁定: 非幂等, 防覆盖首红冲审计记录)。"""
        t = two_teams
        req = self._seed_issued(t)
        first = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "第一次红冲"}, headers=_auth(t["token_a"]),
        )
        assert first.status_code == 200
        t["s"].expire_all()
        second = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "第二次红冲"}, headers=_auth(t["token_a"]),
        )
        assert second.status_code == 400
        # 首红冲记录不被覆盖
        t["s"].expire_all()
        fresh = t["s"].query(InvoiceRequest).filter(InvoiceRequest.id == req.id).first()
        assert fresh.void_reason == "第一次红冲"

    def test_void_missing_reason_422(self, client, two_teams):
        """缺 reason → 422 (Pydantic required)。"""
        t = two_teams
        req = self._seed_issued(t)
        r = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 422

    def test_void_empty_reason_422(self, client, two_teams):
        """空/纯空格 reason → 422 (service 层 strip 校验)。"""
        t = two_teams
        req = self._seed_issued(t)
        r = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "   "}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 422

    def test_void_cross_team_404(self, client, two_teams):
        """跨团队红冲 → 404 (不泄露存在)。"""
        t = two_teams
        req = self._seed_issued(t)  # 属 A 队
        r = client.post(  # B 队 operator 越权红冲
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "x"}, headers=_auth(t["token_b"]),
        )
        assert r.status_code == 404

    def test_void_unknown_404(self, client, two_teams):
        t = two_teams
        r = client.post(
            f"{OPS_URL}/999999/void",
            json={"reason": "x"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 404

    def test_void_visible_in_ops_list(self, client, two_teams):
        """红冲后 ops 列表项携带 voided 标记字段 (契约只增不破)。"""
        t = two_teams
        req = self._seed_issued(t)
        r = client.post(
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "开票有误"}, headers=_auth(t["token_a"]),
        )
        assert r.status_code == 200
        lst = client.get(OPS_URL, params={"status": "issued"},
                         headers=_auth(t["token_a"]))
        item = next(
            i for i in lst.json()["data"]["items"] if i["id"] == req.id
        )
        assert item["voided"] is True
        assert item["void_reason"] == "开票有误"

    def test_unvoided_list_item_voided_false(self, client, two_teams):
        """未红冲的列表项 voided=False (字段恒出现, 便于前端无脑渲染)。"""
        t = two_teams
        self._seed_issued(t, title_name="未红冲项")
        lst = client.get(OPS_URL, params={"status": "issued"},
                         headers=_auth(t["token_a"]))
        item = next(
            i for i in lst.json()["data"]["items"] if i["title_name"] == "未红冲项"
        )
        assert item["voided"] is False


# ==================== B7. C 端红冲可见性 (Phase2-B2, 卡 f42bdf5a) ====================

class TestVoidVisibleOnClientSide:
    """红冲后 C 端 GET /business/invoices 列表/详情可见 voided 状态 (R1 方案b)。

    申请挂独立新团队 (非 two_teams 的 A/B 队), 故红冲用 client 默认 admin
    token (平台级豁免 team 隔离); C 端查询用申请人本人 token。
    """

    def _issued_for_cu(self, client):
        """建团队+站点+PAID订单+申请, DB 置 ISSUED, 返回 (session, invoice_id, token)。"""
        from app.models.station import Station, StationStatus
        from app.models.user import Team
        from app.models.charging_order import ChargingOrder, OrderPaymentStatus
        from decimal import Decimal

        s = client._sesh
        h = uuid.uuid4().hex[:6]
        team = Team(name=f"红冲团队{h}", code=f"VD{h.upper()}")
        s.add(team)
        s.commit()
        s.refresh(team)
        st = Station(
            name=f"红冲站{h}", code=f"ST{uuid.uuid4().hex[:6].upper()}",
            address="测试地址", status=StationStatus.NORMAL, team_id=team.id,
        )
        s.add(st)
        s.commit()
        s.refresh(st)
        cu = _add_user(s, f"vd_cu_{h}", UserRole.VIEWER, team_id=team.id)
        order = ChargingOrder(
            order_no=f"ord_{uuid.uuid4().hex[:12]}", station_id=st.id,
            device_id=1, user_id=cu.id,
            paid_amount=Decimal("10.00"), payment_status=OrderPaymentStatus.PAID,
        )
        s.add(order)
        s.commit()
        req = InvoiceRequest(
            order_ids=f'["{order.order_no}"]', user_id=cu.id, team_id=team.id,
            title_type="personal", title_name="张三", amount=1000,
            status=InvoiceRequestStatus.ISSUED,
            invoice_file_path="/tmp/fake.pdf", invoice_file_name="f.pdf",
            invoice_file_type="pdf",
        )
        s.add(req)
        s.commit()
        s.refresh(req)
        token = _login_token(client, f"vd_cu_{h}")
        return s, req, token

    def test_client_list_shows_voided(self, client, two_teams):
        s, req, token = self._issued_for_cu(client)
        r = client.post(  # client 默认 admin (平台级豁免 team 隔离)
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "开票信息有误"},
        )
        assert r.status_code == 200, r.text

        s.expire_all()
        lst = client.get("/api/v1/business/invoices", headers=_auth(token))
        assert lst.status_code == 200
        item = next(
            i for i in lst.json()["data"]["items"] if i["invoice_id"] == req.id
        )
        assert item["voided"] is True

    def test_client_detail_shows_voided(self, client, two_teams):
        s, req, token = self._issued_for_cu(client)
        r = client.post(  # client 默认 admin (平台级豁免 team 隔离)
            f"{OPS_URL}/{req.id}/void",
            json={"reason": "开票信息有误"},
        )
        assert r.status_code == 200, r.text

        s.expire_all()
        detail = client.get(f"/api/v1/business/invoices/{req.id}", headers=_auth(token))
        assert detail.status_code == 200
        d = detail.json()["data"]
        assert d["voided"] is True
        assert d["status"] == "issued"  # 三态不变
