"""用户端开票申请 API 测试 (用户端云端契约 §5, 工作卡 a09f8a21)

覆盖 app/api/v1/business_invoices.py (挂 /api/v1/business 前缀):
- POST /business/invoices                  用户提交开票申请 (仅 PAID+未开票, 金额汇总成分) → 202
- GET  /business/invoices                  用户申请列表 (轻量版, 无 invoice_file)
- GET  /business/invoices/{invoice_id}     申请详情 (PENDING/REJECTED 无 file, ISSUED 返回签名 URL)
- POST /business/invoices/{invoice_id}/send-email  补发/改发邮箱 (仅 ISSUED)

C 端用户端契约统一 code=0 (与运营侧 success_response code=200 区分, 见 wx_pay/response.py)。
认证: get_current_user (任意 active 用户, 不限 role) —— 用 VIEWER 模拟 C 端用户,
其名下挂 PAID 充电订单。状态机: pending → issued/rejected (rejected 不占位, 可重申)。
"""
import uuid
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.invoice_request import InvoiceRequest, InvoiceRequestStatus
from app.models.station import Station, StationStatus
from app.models.user import UserRole, User

BIZ_URL = "/api/v1/business/invoices"


# ─── helpers ───

def _add_user(session, username, role=UserRole.VIEWER, team_id=None, password="pw123456"):
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


def _seed_station(session, *, team_id=None, tag=""):
    st = Station(
        name=f"开票站{tag}{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_order(
    session,
    *,
    user_id,
    station_id,
    paid_amount=Decimal("10.00"),
    payment_status=OrderPaymentStatus.PAID,
    device_id=1,
    order_no=None,
):
    o = ChargingOrder(
        order_no=order_no or f"ord_{uuid.uuid4().hex[:12]}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        paid_amount=paid_amount,
        payment_status=payment_status,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _apply(client, token, order_ids, **extra):
    """提交开票申请, 默认个人抬头「张三」。"""
    payload = {"order_ids": order_ids, "title_type": "personal", "title_name": "张三"}
    payload.update(extra)
    return client.post(BIZ_URL, json=payload, headers=_auth(token))


@pytest.fixture
def cu(client):
    """C 端用户上下文: 团队 + 用户 + 团队站点 + 两张 PAID 订单 (10.00 / 5.50 元)。

    卡 71062d84: 场站必须挂 team (无 team 的申请无法被任何团队运营接单,
    apply 已拒绝 team 缺失), 故 fixture 显式建团队。
    """
    from app.models.user import Team
    h = uuid.uuid4().hex[:6]
    s = client._sesh
    team = Team(name=f"开票团队{h}", code=f"TM{h.upper()}")
    s.add(team)
    s.commit()
    s.refresh(team)
    st = _seed_station(s, team_id=team.id, tag=h)
    u = _add_user(s, f"cu_{h}", team_id=team.id)
    o1 = _seed_order(s, user_id=u.id, station_id=st.id, paid_amount=Decimal("10.00"))
    o2 = _seed_order(s, user_id=u.id, station_id=st.id, paid_amount=Decimal("5.50"))
    return {
        "s": s, "u": u, "st": st, "team": team, "o1": o1, "o2": o2, "h": h,
        "token": _login_token(client, f"cu_{h}"),
    }


def _set_issued(session, invoice_id, file_type="pdf"):
    """DB 直接把申请置为 ISSUED + 文件信息 (绕过 upload, 供 get/send-email 测试)。"""
    req = session.query(InvoiceRequest).filter(InvoiceRequest.id == invoice_id).first()
    req.status = InvoiceRequestStatus.ISSUED
    req.invoice_file_path = "/tmp/fake_invoice.pdf"
    req.invoice_file_type = file_type
    session.commit()
    return req


# ==================== A1. 提交申请 (契约 §5.1) ====================

class TestApplyInvoice:
    """POST /business/invoices → 202 code=0 (仅 PAID+未开票, 金额汇总成分)。"""

    def test_personal_apply_returns_202_and_pending(self, client, cu):
        r = _apply(client, cu["token"], [cu["o1"].order_no])
        assert r.status_code == 202, r.text
        d = r.json()
        assert d["code"] == 0
        assert d["data"]["status"] == "pending"
        assert d["data"]["amount"] == 1000  # 10.00 元 → 1000 分
        assert isinstance(d["data"]["invoice_id"], int)

    def test_company_apply_with_tax_number(self, client, cu):
        r = _apply(
            client, cu["token"], [cu["o1"].order_no],
            title_type="company", title_name="某某科技有限公司",
            tax_number="91110000XXXXXXXX",
        )
        assert r.status_code == 202
        assert r.json()["data"]["status"] == "pending"

    def test_multi_order_amount_aggregation(self, client, cu):
        """多单金额汇总: 10.00 + 5.50 = 15.50 元 → 1550 分。"""
        r = _apply(client, cu["token"], [cu["o1"].order_no, cu["o2"].order_no])
        assert r.status_code == 202
        assert r.json()["data"]["amount"] == 1550

    def test_unpaid_order_rejected_biz_error(self, client, cu):
        """非 PAID 订单 → HTTP 200 + code!=0 ORDER_NOT_PAID (卡 418a675a)。"""
        o = _seed_order(
            cu["s"], user_id=cu["u"].id, station_id=cu["st"].id,
            paid_amount=Decimal("8.00"), payment_status=OrderPaymentStatus.UNPAID,
        )
        r = _apply(client, cu["token"], [o.order_no])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_PAID"
        assert body["data"] is None

    def test_duplicate_pending_order_biz_error(self, client, cu):
        """订单已在 PENDING 申请中 → code!=0 INVOICE_DUPLICATE。"""
        _apply(client, cu["token"], [cu["o1"].order_no])
        r = _apply(client, cu["token"], [cu["o1"].order_no])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_DUPLICATE"
        assert body["data"] is None

    def test_rejected_order_can_reapply(self, client, cu):
        """REJECTED 不占位 → 同一订单可重新申请 (契约 §5.4)。"""
        req = InvoiceRequest(
            order_ids=f'["{cu["o1"].order_no}"]', user_id=cu["u"].id,
            title_type="personal", title_name="张三", amount=1000,
            status=InvoiceRequestStatus.REJECTED,
        )
        cu["s"].add(req)
        cu["s"].commit()
        r = _apply(client, cu["token"], [cu["o1"].order_no])
        assert r.status_code == 202

    def test_company_missing_tax_number_422(self, client, cu):
        """company 抬头缺税号 → 422 (service 层校验)。"""
        r = _apply(
            client, cu["token"], [cu["o1"].order_no],
            title_type="company", title_name="某某公司",
        )
        assert r.status_code == 422

    def test_empty_order_ids_422(self, client, cu):
        """空 order_ids → 422 (Pydantic min_length=1)。"""
        r = client.post(
            BIZ_URL, json={"order_ids": [], "title_name": "张三"},
            headers=_auth(cu["token"]),
        )
        assert r.status_code == 422

    def test_order_not_owned_biz_error(self, client, cu):
        """他人订单 → code!=0 ORDER_NOT_FOUND (不泄露存在)。"""
        other = _add_user(cu["s"], f"other_{cu['h']}")
        o = _seed_order(cu["s"], user_id=other.id, station_id=cu["st"].id)
        r = _apply(client, cu["token"], [o.order_no])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_order_not_exist_biz_error(self, client, cu):
        r = _apply(client, cu["token"], ["ord_ghost_9999"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_duplicate_order_ids_dedup(self, client, cu):
        """同一 order_id 重复传入 → 去重保序, 金额不翻倍。"""
        r = _apply(client, cu["token"], [cu["o1"].order_no, cu["o1"].order_no])
        assert r.status_code == 202
        assert r.json()["data"]["amount"] == 1000  # 去重后只算一次


# ==================== A2. 列表 (契约 §5.2 轻量版) ====================

class TestListInvoices:
    """GET /business/invoices —— 只看自己, 轻量版无 invoice_file。"""

    def test_list_only_own_invoices(self, client, cu):
        _apply(client, cu["token"], [cu["o1"].order_no])
        # 另一用户申请一条 (同站, 别的订单)
        other = _add_user(cu["s"], f"other_{cu['h']}")
        oo = _seed_order(cu["s"], user_id=other.id, station_id=cu["st"].id)
        otok = _login_token(client, f"other_{cu['h']}")
        _apply(client, otok, [oo.order_no])

        r = client.get(BIZ_URL, headers=_auth(cu["token"]))
        assert r.status_code == 200
        assert r.json()["code"] == 0
        items = r.json()["data"]["items"]
        # 自己的列表含 o1, 不含 other 的订单
        assert any(cu["o1"].order_no in i["order_ids"] for i in items)
        assert all(oo.order_no not in i["order_ids"] for i in items)

    def test_list_lightweight_no_invoice_file(self, client, cu):
        _apply(client, cu["token"], [cu["o1"].order_no])
        r = client.get(BIZ_URL, headers=_auth(cu["token"]))
        item = r.json()["data"]["items"][0]
        assert "invoice_file" not in item  # 轻量版不返回文件信息

    def test_list_filter_by_status(self, client, cu):
        _apply(client, cu["token"], [cu["o1"].order_no])
        r = client.get(BIZ_URL, params={"status": "pending"}, headers=_auth(cu["token"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items  # 至少一条
        assert all(i["status"] == "pending" for i in items)


# ==================== A3. 详情 (契约 §5.2 invoice_file 仅 ISSUED) ====================

class TestGetInvoice:
    """GET /business/invoices/{id} —— PENDING/REJECTED 无 file, ISSUED 有签名 URL。"""

    def test_get_pending_no_file(self, client, cu):
        inv = _apply(client, cu["token"], [cu["o1"].order_no]).json()["data"]
        r = client.get(f"{BIZ_URL}/{inv['invoice_id']}", headers=_auth(cu["token"]))
        assert r.status_code == 200
        assert r.json()["data"]["invoice_file"] is None  # PENDING 无文件

    def test_get_issued_has_signed_url(self, client, cu):
        inv = _apply(client, cu["token"], [cu["o1"].order_no]).json()["data"]
        _set_issued(cu["s"], inv["invoice_id"])
        r = client.get(f"{BIZ_URL}/{inv['invoice_id']}", headers=_auth(cu["token"]))
        assert r.status_code == 200
        f = r.json()["data"]["invoice_file"]
        assert f is not None
        assert "token=" in f["file_url"]  # 签名令牌 (契约 §5.5)
        assert f["file_type"] == "pdf"

    def test_get_cross_user_biz_error(self, client, cu):
        inv = _apply(client, cu["token"], [cu["o1"].order_no]).json()["data"]
        other = _add_user(cu["s"], f"other_{cu['h']}")
        otok = _login_token(client, f"other_{cu['h']}")
        r = client.get(f"{BIZ_URL}/{inv['invoice_id']}", headers=_auth(otok))
        assert r.status_code == 200
        body = r.json()  # 他人申请不泄露存在
        assert body["code"] != 0
        assert body["message"] == "INVOICE_REQUEST_NOT_FOUND"
        assert body["data"] is None

    def test_get_not_exist_biz_error(self, client, cu):
        r = client.get(f"{BIZ_URL}/999999", headers=_auth(cu["token"]))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_REQUEST_NOT_FOUND"
        assert body["data"] is None


# ==================== A4. 补发/改发邮箱 (契约 §5.3) ====================

class TestSendEmail:
    """POST /business/invoices/{id}/send-email —— 仅 ISSUED 可发, 响应 {sent: true}。"""

    def test_send_email_issued_ok(self, client, cu):
        inv = _apply(client, cu["token"], [cu["o1"].order_no]).json()["data"]
        _set_issued(cu["s"], inv["invoice_id"])
        r = client.post(
            f"{BIZ_URL}/{inv['invoice_id']}/send-email",
            json={"email": "new@example.com"}, headers=_auth(cu["token"]),
        )
        assert r.status_code == 200
        assert r.json()["data"]["sent"] is True
        # 改发: 申请邮箱已更新为最新
        cu["s"].expire_all()
        fresh = cu["s"].query(InvoiceRequest).filter(InvoiceRequest.id == inv["invoice_id"]).first()
        assert fresh.email == "new@example.com"

    def test_send_email_pending_biz_error(self, client, cu):
        inv = _apply(client, cu["token"], [cu["o1"].order_no]).json()["data"]
        r = client.post(
            f"{BIZ_URL}/{inv['invoice_id']}/send-email",
            json={"email": "x@example.com"}, headers=_auth(cu["token"]),
        )
        assert r.status_code == 200
        body = r.json()  # 尚未开具, 无法发送
        assert body["code"] != 0
        assert body["message"] == "INVOICE_NOT_ISSUED"
        assert body["data"] is None

    def test_send_email_cross_user_biz_error(self, client, cu):
        inv = _apply(client, cu["token"], [cu["o1"].order_no]).json()["data"]
        other = _add_user(cu["s"], f"other_{cu['h']}")
        otok = _login_token(client, f"other_{cu['h']}")
        r = client.post(
            f"{BIZ_URL}/{inv['invoice_id']}/send-email",
            json={"email": "x@example.com"}, headers=_auth(otok),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_REQUEST_NOT_FOUND"
        assert body["data"] is None
