"""开票契约 §5 逐字段对齐测试 (卡 47fc5070 / a09f8a21 复审)

v1.2 (commit 166c0bc7c) 复审锁定的三处可修差异, 每处对应一个测试类:
- T1 时间格式 (契约 §6): ISO8601 带时区 —— SQLite DateTime 列读回 naive,
  isoformat() 无 +00:00 后缀, 端侧解析歧义 → 序列化统一补 UTC 后缀。
- T2 ops 列表/详情字段 (契约 §5.4): 「记录 issuer/issued_at」→ ops 响应
  补 issuer/issued_at 别名 (实现层 reviewed_by/reviewed_at 双写)。
- T3 status 过滤大小写 (契约 §5.4 示例 ?status=PENDING): 大小写均须命中
  (ORM bind 双值本就等价, 测试锁定该行为防回归)。

注意: status 返回值小写 (pending/issued/rejected) 与契约 §5.2 示例大写
不一致 —— 但契约 §7 同字段全部小写 + 已交付 web 前端按小写对接,
判定为契约记法问题, 不改实现 (待丁哥决策项, 详见任务卡交付报告)。
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.invoice_request import InvoiceRequest, InvoiceRequestStatus
from app.models.user import UserRole, User, Team

import app.services.invoice_request_service as svc

BIZ_URL = "/api/v1/business/invoices"
OPS_URL = "/api/v1/ops/invoice-requests"


# ─── helpers ───

def _add_user(session, username, role=UserRole.OPERATOR, team_id=None, password="pw123456"):
    import bcrypt
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


def _seed_request(session, *, user_id, team_id, status=InvoiceRequestStatus.PENDING):
    r = InvoiceRequest(
        order_ids=f'["ord_{uuid.uuid4().hex[:8]}"]',
        user_id=user_id,
        team_id=team_id,
        title_type="personal",
        title_name="张三",
        amount=1000,
        status=status,
        email="cu@example.com",
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


@pytest.fixture
def ops_ctx(client):
    """团队 + operator + C 端申请人 + 一条 PENDING 申请。"""
    s = client._sesh
    h = uuid.uuid4().hex[:6]
    team = Team(name=f"对齐团队{h}", code=f"AL{h.upper()}")
    s.add(team)
    s.commit()
    s.refresh(team)
    cu = _add_user(s, f"al_cu_{h}", UserRole.VIEWER)
    op = _add_user(s, f"al_op_{h}", UserRole.OPERATOR, team_id=team.id)
    req = _seed_request(s, user_id=cu.id, team_id=team.id)
    return {
        "s": s, "team": team, "cu": cu, "op": op, "req": req, "h": h,
        "token": _login_token(client, f"al_op_{h}"),
        "cu_token": _login_token(client, f"al_cu_{h}"),
    }


# ==================== T1. 时间 ISO8601 带时区 (契约 §6) ====================

class TestTimezoneFormat:
    """created_at/issued_at/reject_reason 同载的 applied_at 等须带时区后缀。"""

    @pytest.mark.parametrize("field", ["created_at", "applied_at"])
    def test_user_list_time_has_tz(self, client, ops_ctx, field):
        r = client.get(BIZ_URL, headers=_auth(ops_ctx["cu_token"]))
        assert r.status_code == 200
        item = r.json()["data"]["items"][0]
        v = item[field]
        assert v, f"{field} 为空"
        assert v.endswith("+00:00") or "Z" in v, (
            f"{field}={v} 缺时区后缀 (契约 §6 ISO8601 带时区)"
        )

    def test_user_detail_issued_at_has_tz(self, client, ops_ctx, tmp_path, monkeypatch):
        """upload → ISSUED 后详情 issued_at 带时区。"""
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = ops_ctx
        r = client.post(
            f"{OPS_URL}/{t['req'].id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth(t["token"]),
        )
        assert r.status_code == 200, r.text
        d = client.get(f"{BIZ_URL}/{t['req'].id}", headers=_auth(t["cu_token"])).json()["data"]
        assert d["issued_at"], "ISSUED 后 issued_at 应有值"
        assert d["issued_at"].endswith("+00:00") or "Z" in d["issued_at"], (
            f"issued_at={d['issued_at']} 缺时区后缀"
        )

    def test_ops_list_time_has_tz(self, client, ops_ctx):
        r = client.get(OPS_URL, headers=_auth(ops_ctx["token"]))
        assert r.status_code == 200
        item = r.json()["data"]["items"][0]
        v = item["applied_at"]
        assert v, "applied_at 为空"
        assert v.endswith("+00:00") or "Z" in v


# ==================== T2. ops 响应补 issuer/issued_at (契约 §5.4) ====================

class TestOpsIssuerFields:
    """契约 §5.4 「记录 issuer/issued_at」→ ops 列表/详情须含这两个键。"""

    def test_upload_response_has_issuer_and_issued_at(self, client, ops_ctx, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = ops_ctx
        r = client.post(
            f"{OPS_URL}/{t['req'].id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth(t["token"]),
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "issuer" in d, "ops 响应缺 issuer (契约 §5.4)"
        assert "issued_at" in d, "ops 响应缺 issued_at (契约 §5.4)"
        assert d["issuer"] == t["op"].id
        assert d["issued_at"]

    def test_upload_issued_at_has_tz(self, client, ops_ctx, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "_INVOICE_UPLOAD_DIR", str(tmp_path))
        t = ops_ctx
        r = client.post(
            f"{OPS_URL}/{t['req'].id}/upload",
            files={"file": ("f.pdf", b"%PDF-1.4 fake", "application/pdf")},
            headers=_auth(t["token"]),
        )
        d = r.json()["data"]
        assert d["issued_at"].endswith("+00:00") or "Z" in d["issued_at"]

    def test_reject_response_has_issuer(self, client, ops_ctx):
        """reject 后 issuer=处理人, issued_at=None (未开具)。"""
        t = ops_ctx
        r = client.post(
            f"{OPS_URL}/{t['req'].id}/reject",
            json={"reject_reason": "材料不全"}, headers=_auth(t["token"]),
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "issuer" in d, "reject 响应缺 issuer (契约 §5.4)"
        assert d["issuer"] == t["op"].id
        assert d["issued_at"] is None  # 被拒未开具


# ==================== T3. status 过滤大小写等价 (契约 §5.4 示例大写) ====================

class TestStatusFilterCaseInsensitive:
    """契约 §5.4 示例 ?status=PENDING (大写) 与小写均须命中。

    ORM SAEnum bind_processor 对两种字面量等价转换 (SQLite/PG 同)。
    本类锁定该行为, 防将来改列类型/比较方式时静默破坏大写查询。
    """

    @pytest.mark.parametrize("status_val", ["pending", "PENDING"])
    def test_ops_list_filter_both_cases(self, client, ops_ctx, status_val):
        r = client.get(OPS_URL, params={"status": status_val}, headers=_auth(ops_ctx["token"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items, f"?status={status_val} 应命中已种子的 PENDING 申请"

    @pytest.mark.parametrize("status_val", ["issued", "ISSUED"])
    def test_user_list_filter_both_cases(self, client, ops_ctx, status_val):
        # 置为 ISSUED 再过滤
        t = ops_ctx
        t["s"].expire_all()
        row = t["s"].query(InvoiceRequest).filter(InvoiceRequest.id == t["req"].id).first()
        row.status = InvoiceRequestStatus.ISSUED
        row.reviewed_at = datetime.now(timezone.utc)
        row.invoice_file_path = "/tmp/f.pdf"
        row.invoice_file_type = "pdf"
        t["s"].commit()

        r = client.get(BIZ_URL, params={"status": status_val}, headers=_auth(t["cu_token"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items, f"?status={status_val} 应命中 ISSUED 申请"
