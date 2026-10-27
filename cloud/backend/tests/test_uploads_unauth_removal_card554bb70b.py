"""
/uploads 未鉴权裸挂移除 + 凭证鉴权下载 — 任务卡 554bb70b

回归背景: commit c7760dff8 (车队充值) 在 main.py 重复挂载
app.mount("/uploads", StaticFiles(...)), 把 uploads/ 整目录(发票 PII +
车队付款凭证)匿名直挂, 绕过发票签名令牌设计。

覆盖:
- /uploads/* 任意静态路径匿名不可达 (404)
- 凭证下载端点: 未认证 401; 跨团队 fleet 用户 404; 本团队 200 取到文件
- 发票签名令牌下载端点回归锚点 (仍工作, 白名单匿名可达)
"""
import os

import bcrypt
import pytest

from app.core.config import settings
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.fleet_recharge import FleetRechargeRequest, RechargeStatus
from app.models.user import Team, User, UserRole


@pytest.fixture
def fleet_pair(client):
    """两个 fleet 类型团队 + 用户 + 企业 + 一条充值申请(带真实凭证文件)。"""
    s = client._sesh
    pwd = "fleet123456"

    ta = Team(name="凭证团队A", code="VCHTA", type="fleet")
    tb = Team(name="凭证团队B", code="VCHTB", type="fleet")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    def _u(name, team):
        u = User(
            username=name, real_name=name, role=UserRole.OPERATOR,
            team_id=team.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        return u

    _u("voucher_user_a", ta)
    _u("voucher_user_b", tb)
    s.commit()

    ent_a = Enterprise(name="凭证企业A", code="VCHEA", status=EnterpriseStatus.ACTIVE, owner_team_id=ta.id)
    ent_b = Enterprise(name="凭证企业B", code="VCHEB", status=EnterpriseStatus.ACTIVE, owner_team_id=tb.id)
    s.add_all([ent_a, ent_b])
    s.commit()
    s.refresh(ent_a)
    s.refresh(ent_b)

    # 落盘一个真实凭证文件
    upload_dir = os.path.join(settings.UPLOAD_DIR or "./uploads", "fleet_recharge")
    os.makedirs(upload_dir, exist_ok=True)
    fname = "card554bb70b_voucher.png"
    fpath = os.path.join(upload_dir, fname)
    content = b"\x89PNG\r\n\x1a\n" + b"card554bb70b" * 8
    with open(fpath, "wb") as f:
        f.write(content)

    req = FleetRechargeRequest(
        enterprise_id=ent_a.id,
        amount=100,
        voucher_url=f"/uploads/fleet_recharge/{fname}",
        status=RechargeStatus.PENDING,
    )
    s.add(req)
    s.commit()
    s.refresh(req)

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, r.text
        return r.json()["data"]["token"]

    return {
        "req_id": req.id,
        "fname": fname,
        "content": content,
        "tokens": {"a": _tok("voucher_user_a"), "b": _tok("voucher_user_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


class TestUploadsMountRemoved:
    def test_uploads_static_route_gone(self, anon_client, fleet_pair):
        """卡 554bb70b: /uploads 裸挂必须移除, 匿名直链不可达。"""
        r = anon_client.get(f"/uploads/fleet_recharge/{fleet_pair['fname']}")
        assert r.status_code == 404, r.text
        r2 = anon_client.get("/uploads/invoices/whatever.pdf")
        assert r2.status_code == 404


class TestVoucherDownloadAuth:
    def test_anonymous_401(self, anon_client, fleet_pair):
        r = anon_client.get(f"/api/v1/fleet/recharge/{fleet_pair['req_id']}/voucher")
        assert r.status_code == 401, r.text

    def test_cross_team_fleet_user_404(self, client, fleet_pair):
        """B 团队 fleet 用户访问 A 企业申请 → 404 不泄露存在性。"""
        r = client.get(
            f"/api/v1/fleet/recharge/{fleet_pair['req_id']}/voucher",
            headers=_h(fleet_pair["tokens"]["b"]),
        )
        assert r.status_code == 404, r.text

    def test_own_team_200(self, client, fleet_pair):
        r = client.get(
            f"/api/v1/fleet/recharge/{fleet_pair['req_id']}/voucher",
            headers=_h(fleet_pair["tokens"]["a"]),
        )
        assert r.status_code == 200, r.text
        assert r.content == fleet_pair["content"]
        assert r.headers["content-type"].startswith("image/png")

    def test_admin_200(self, client, fleet_pair):
        r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        headers = {"Authorization": f"Bearer {r.json()['data']['token']}"}
        r2 = client.get(
            f"/api/v1/fleet/recharge/{fleet_pair['req_id']}/voucher", headers=headers
        )
        assert r2.status_code == 200, r2.text
        assert r2.content == fleet_pair["content"]

    def test_nonexistent_404(self, client, fleet_pair):
        r = client.get(
            "/api/v1/fleet/recharge/999999/voucher",
            headers=_h(fleet_pair["tokens"]["a"]),
        )
        assert r.status_code == 404


class TestInvoiceFileTokenRegression:
    def test_invoice_file_download_still_works(self, client, db_session, tmp_path):
        """回归锚点: 发票签名令牌端点 (白名单匿名) 不受本次改动影响。"""

        from app.models.invoice_request import InvoiceRequest, InvoiceFileType, InvoiceRequestStatus
        from app.services import invoice_notification

        f = tmp_path / "inv_card554bb70b.pdf"
        f.write_bytes(b"%PDF-1.4 card554bb70b")

        inv = InvoiceRequest(
            user_id=1,
            order_ids='["ORD-CARD554BB70B"]',
            title_name="回归锚点发票",
            amount=10,
            status=InvoiceRequestStatus.ISSUED,
            invoice_file_path=str(f),
            invoice_file_type=InvoiceFileType.PDF,
            invoice_file_name="inv_card554bb70b.pdf",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        token = invoice_notification.generate_file_token(inv.id)
        r = client.get("/api/v1/business/invoice-file", params={"token": token})
        assert r.status_code == 200, r.text
        assert r.content == b"%PDF-1.4 card554bb70b"

        # 坏 token 仍 403
        r2 = client.get("/api/v1/business/invoice-file", params={"token": "garbage"})
        assert r2.status_code == 403
