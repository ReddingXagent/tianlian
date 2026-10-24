"""手动开票申请 后端测试 (用户端云端契约 §5, 工作卡 a09f8a21)

覆盖:
- 申请校验: PAID/归属/重复/金额汇总/抬头税号
- 用户端列表/详情 (签名 file_url 仅 ISSUED)
- 补发/改发邮箱 (仅 ISSUED, SMTP mock)
- 运营端: 列表 team 隔离 / 上传(magic bytes+状态机+通知) / 拒绝 / 跨团队 404
- 状态机: REJECTED 后可重新申请
- 签名 URL: 有效/篡改/过期; 下载端点 (白名单免登录)
- 认证: 匿名 401 / 缺权限 403
"""
import bcrypt
import pytest
from decimal import Decimal

from app.services import invoice_notification


# ─── 脚手架 ─────────────────────────────────────────────────────────────────

def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json()["data"]["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def c_user(client):
    """C端用户(带 team)+ 场站 + 设备 + token。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    team = Team(name="开票C端团队", code="INVC")
    s.add(team)
    s.commit()
    s.refresh(team)

    pwd = "cuser123456"
    u = User(
        username="inv_cuser", real_name="开票用户", role=UserRole.VIEWER,
        team_id=team.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    s.refresh(u)

    st = Station(name="开票站", code="INVSTA", address="测试地址",
                 status=StationStatus.NORMAL, team_id=team.id)
    s.add(st)
    s.commit()
    s.refresh(st)
    dev = Device(sn="INVSN01", name="桩#1", code="INVDEV01", type=DeviceType.CHARGER_DC,
                 status=DeviceStatus.ONLINE, station_id=st.id, rated_power=120.0)
    s.add(dev)
    s.commit()
    s.refresh(dev)

    return {
        "user": u, "team": team, "station": st, "device": dev,
        "token": _login(client, "inv_cuser", pwd),
        "pwd": pwd,
    }


@pytest.fixture
def other_user(client):
    """另一个 C端用户 (用于越权测试)。"""
    from app.models.user import User, UserRole
    s = client._sesh
    pwd = "other123456"
    u = User(
        username="inv_other", real_name="他人", role=UserRole.VIEWER,
        status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return {"user": u, "token": _login(client, "inv_other", pwd), "pwd": pwd}


def _make_order(client, c_user, order_no, paid_yuan, status_paid=True, user_id=None):
    from app.models.charging_order import (
        ChargingOrder, OrderPaymentStatus, OrderStatus, UserType, PaymentMethod,
    )
    s = client._sesh
    o = ChargingOrder(
        order_no=order_no,
        station_id=c_user["station"].id,
        device_id=c_user["device"].id,
        user_id=user_id if user_id is not None else c_user["user"].id,
        user_type=UserType.APP,
        paid_amount=Decimal(str(paid_yuan)),
        total_amount=Decimal(str(paid_yuan)),
        payment_status=OrderPaymentStatus.PAID if status_paid else OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT,
    )
    s.add(o)
    s.commit()
    s.refresh(o)
    return o


def _apply(client, token, order_ids, title_type="personal", title_name="张三",
           tax_number=None, receive_email=None):
    payload = {"order_ids": order_ids, "title_type": title_type, "title_name": title_name}
    if tax_number:
        payload["tax_number"] = tax_number
    if receive_email:
        payload["receive_email"] = receive_email
    return client.post("/api/v1/business/invoices", json=payload, headers=_h(token))


@pytest.fixture
def team_pair(client):
    """两运营团队 + 两 operator 用户(具 operate:manage) + token, 用于 ops team 隔离测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="开票运营A", code="INVOA")
    tb = Team(name="开票运营B", code="INVOB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)
    pwd = "invop123456"

    def mk(name, team):
        u = User(
            username=name, real_name=name, role=UserRole.OPERATOR,
            team_id=team.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return u

    ua, ub = mk("inv_op_a", ta), mk("inv_op_b", tb)
    return {
        "teams": {"a": ta, "b": tb},
        "users": {"a": ua, "b": ub},
        "tokens": {"a": _login(client, "inv_op_a", pwd), "b": _login(client, "inv_op_b", pwd)},
    }


# ─── 申请校验 ────────────────────────────────────────────────────────────────

class TestApply:
    def test_apply_single_paid_order(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_001", 128.00)
        r = _apply(client, c_user["token"], ["INV_ORD_001"], title_name="张三")
        assert r.status_code == 202
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "pending"
        assert body["data"]["amount"] == 12800  # 128 元 → 分

    def test_apply_amount_summary_multi_orders(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_002", 100.00)
        _make_order(client, c_user, "INV_ORD_003", 28.50)
        r = _apply(client, c_user["token"], ["INV_ORD_002", "INV_ORD_003"], title_name="张三")
        assert r.status_code == 202
        assert r.json()["data"]["amount"] == 12850  # 128.50 元 → 分

    def test_apply_unpaid_order_rejected(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_004", 50.00, status_paid=False)
        r = _apply(client, c_user["token"], ["INV_ORD_004"])
        # 卡 418a675a: 业务错误 HTTP 200 + code!=0 (契约 §6)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_PAID"
        assert body["data"] is None

    def test_apply_other_users_order_not_leaked(self, client, c_user, other_user):
        # 订单归属 other_user, c_user 申请 → 不泄露存在, 报 ORDER_NOT_FOUND
        _make_order(client, c_user, "INV_ORD_005", 50.00, user_id=other_user["user"].id)
        r = _apply(client, c_user["token"], ["INV_ORD_005"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_apply_nonexistent_order(self, client, c_user):
        r = _apply(client, c_user["token"], ["NOT_EXIST"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_apply_duplicate_order_conflict(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_006", 30.00)
        r1 = _apply(client, c_user["token"], ["INV_ORD_006"])
        assert r1.status_code == 202
        # 同一订单再次申请 (上一条仍 PENDING) → code!=0 INVOICE_DUPLICATE
        r2 = _apply(client, c_user["token"], ["INV_ORD_006"])
        assert r2.status_code == 200
        body = r2.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_DUPLICATE"
        assert body["data"] is None

    def test_apply_company_title_requires_tax_number(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_007", 60.00)
        r = _apply(client, c_user["token"], ["INV_ORD_007"],
                   title_type="company", title_name="某某科技有限公司")
        # 输入校验类 (卡 418a675a 判定: 校验保留 HTTPException 422)
        assert r.status_code == 422
        assert "税号" in r.json()["detail"]

    def test_apply_company_title_with_tax_ok(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_008", 60.00)
        r = _apply(client, c_user["token"], ["INV_ORD_008"],
                   title_type="company", title_name="某某科技有限公司",
                   tax_number="91110000XXXXXXXX")
        assert r.status_code == 202

    def test_apply_empty_order_list(self, client, c_user):
        r = _apply(client, c_user["token"], [])
        assert r.status_code in (400, 422)

    def test_apply_records_receive_email(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_009", 20.00)
        r = _apply(client, c_user["token"], ["INV_ORD_009"],
                   receive_email="user@example.com")
        assert r.status_code == 202
        inv_id = r.json()["data"]["invoice_id"]
        detail = client.get(f"/api/v1/business/invoices/{inv_id}", headers=_h(c_user["token"]))
        assert detail.json()["data"]["email"] == "user@example.com"

    def test_apply_concurrent_double_submit_caught_by_recheck(self, client, c_user, monkeypatch):
        """TOCTOU 防护 (卡4b14971e 修复点1): 首次占用检查通过后, commit 前另一并发请求
        已占用同一订单 → 二次校验拦截, 抛 409 且不落库 (杜绝 PENDING 双开)。"""
        import app.services.invoice_request_service as svc
        from app.models.invoice_request import InvoiceRequest

        _make_order(client, c_user, "INV_ORD_TOCTOU", 30.00)
        calls = {"n": 0}

        def fake_used(db, user_id):
            calls["n"] += 1
            if calls["n"] == 1:
                return set()  # 首次检查: 未占用 (并发窗口)
            return {"INV_ORD_TOCTOU"}  # 二次校验: 已被并发请求占用

        monkeypatch.setattr(svc, "_used_order_nos", fake_used)
        r = _apply(client, c_user["token"], ["INV_ORD_TOCTOU"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_DUPLICATE"
        # 二次校验在 commit 前 → DB 无新申请
        s = client._sesh
        assert s.query(InvoiceRequest).filter(
            InvoiceRequest.user_id == c_user["user"].id
        ).count() == 0

    def test_apply_rejects_none_paid_amount(self, client, c_user):
        """None 金额 guard (卡4b14971e 修复点4): DB 中 PAID 订单 paid_amount 为 NULL
        (历史脏数据 / raw SQL 写入; ORM default 会把显式 None 归零, 但绕过 ORM 写入的
        历史数据仍可能为 NULL) → 显式 422, 不静默归零开 0 元发票。"""
        from app.models.charging_order import (
            ChargingOrder, OrderPaymentStatus, OrderStatus, UserType, PaymentMethod,
        )
        s = client._sesh
        o = ChargingOrder(
            order_no="INV_ORD_NONE_AMT",
            station_id=c_user["station"].id,
            device_id=c_user["device"].id,
            user_id=c_user["user"].id,
            user_type=UserType.APP,
            paid_amount=Decimal("30.00"),
            total_amount=Decimal("30.00"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
        )
        s.add(o)
        s.commit()
        s.refresh(o)
        # 模拟历史脏数据: bulk update 绕过 ORM default, 将实付金额置 NULL
        s.query(ChargingOrder).filter(ChargingOrder.id == o.id).update(
            {ChargingOrder.paid_amount: None}
        )
        s.commit()
        s.expire_all()
        r = _apply(client, c_user["token"], ["INV_ORD_NONE_AMT"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_AMOUNT_INVALID"
        assert body["data"] is None


# ─── 跨团队归属 (卡 71062d84) ─────────────────────────────────────────────────

class TestApplyTeamConsistency:
    """发票申请 team 归属完整性。

    缺陷: 原实现只取首单场站 team (`if team_id is None: team_id = ...`)。
    - 场景A: 勾选跨团队两单 → 整张发票挂首单团队, 另一团队 ops 永不可见;
    - 场景B: station 缺失/已删 → team_id=None → 所有团队级 ops 不可见,
      仅平台 admin 可见, 申请永久滞留 PENDING。
    修复: 检测到多 team 或 team 缺失 → 422 拒绝 (方案①, 见 commit 说明)。
    """

    def test_apply_cross_team_orders_rejected(self, client, c_user, team_pair):
        # 单次勾选两团队场站的订单 → 422, 提示分开申请
        o1 = _make_order(client, c_user, "INV_ORD_XTEAM_1", 20.00)
        # 在团队 B 建第二场站 + 设备, 订单挂过去 (归属同一 c_user)
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        st2 = Station(name="跨团队站", code="INVSTAXB", address="地址B",
                      status=StationStatus.NORMAL, team_id=team_pair["teams"]["b"].id)
        s.add(st2)
        s.commit()
        s.refresh(st2)
        dev2 = Device(sn="INVSNXB", name="桩B", code="INVDEVXB",
                      type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                      station_id=st2.id, rated_power=120.0)
        s.add(dev2)
        s.commit()
        s.refresh(dev2)
        o2 = _make_order(client, c_user, "INV_ORD_XTEAM_2", 30.00)
        s.query(type(o2)).filter(
            type(o2).order_no == "INV_ORD_XTEAM_2"
        ).update({"station_id": st2.id, "device_id": dev2.id})
        s.commit()
        s.expire_all()

        r = _apply(client, c_user["token"], ["INV_ORD_XTEAM_1", "INV_ORD_XTEAM_2"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CROSS_TEAM_ORDERS"
        assert body["data"] is None
        # 拒绝后不落库 (无 PENDING 残留占住订单)
        from app.models.invoice_request import InvoiceRequest
        assert s.query(InvoiceRequest).filter(
            InvoiceRequest.order_ids.contains("INV_ORD_XTEAM_1")
        ).count() == 0

    def test_apply_cross_team_reversed_order_rejected(self, client, c_user, team_pair):
        """跨团队订单与勾选顺序无关: 首单 team=B 亦拒绝 (防「首单 team」侥幸通过)。"""
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        st2 = Station(name="跨团队站C", code="INVSTAXC", address="地址C",
                      status=StationStatus.NORMAL, team_id=team_pair["teams"]["b"].id)
        s.add(st2)
        s.commit()
        s.refresh(st2)
        dev2 = Device(sn="INVSNXC", name="桩C", code="INVDEVXC",
                      type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                      station_id=st2.id, rated_power=120.0)
        s.add(dev2)
        s.commit()
        s.refresh(dev2)
        from app.models.charging_order import ChargingOrder
        _make_order(client, c_user, "INV_ORD_XTEAM_3", 20.00)
        _make_order(client, c_user, "INV_ORD_XTEAM_4", 30.00)
        s.query(ChargingOrder).filter(
            ChargingOrder.order_no == "INV_ORD_XTEAM_4"
        ).update({"station_id": st2.id, "device_id": dev2.id})
        s.commit()
        s.expire_all()

        # 跨团队单在前
        r = _apply(client, c_user["token"], ["INV_ORD_XTEAM_4", "INV_ORD_XTEAM_3"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CROSS_TEAM_ORDERS"

    def test_apply_same_team_multi_orders_ok(self, client, c_user):
        """同团队多单合并申请不受影响 (回归保护)。"""
        _make_order(client, c_user, "INV_ORD_SAMETEAM_1", 20.00)
        _make_order(client, c_user, "INV_ORD_SAMETEAM_2", 30.00)
        r = _apply(client, c_user["token"],
                   ["INV_ORD_SAMETEAM_1", "INV_ORD_SAMETEAM_2"])
        assert r.status_code == 202
        assert r.json()["data"]["amount"] == 5000

    def test_apply_station_missing_rejected(self, client, c_user):
        """订单的 station 已删 (station_id 悬空) → 422, 不产生 team_id=None 的
        平台孤儿申请 (所有团队级 ops 不可见, 仅 admin 可见)。"""
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.charging_order import ChargingOrder
        s = client._sesh
        st = Station(name="待删站", code="INVSTADEL", address="地址D",
                     status=StationStatus.NORMAL, team_id=c_user["team"].id)
        s.add(st)
        s.commit()
        s.refresh(st)
        dev = Device(sn="INVSNDEL", name="桩D", code="INVDEVDEL",
                     type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                     station_id=st.id, rated_power=120.0)
        s.add(dev)
        s.commit()
        s.refresh(dev)
        _make_order(client, c_user, "INV_ORD_STADEL", 40.00)
        s.query(ChargingOrder).filter(
            ChargingOrder.order_no == "INV_ORD_STADEL"
        ).update({"station_id": st.id, "device_id": dev.id})
        s.commit()
        s.expire_all()

        # 场站被删除 → 订单 station_id 悬空 (无 FK 约束或软删场景)
        s.query(Station).filter(Station.id == st.id).delete()
        s.query(Device).filter(Device.id == dev.id).delete()
        s.commit()
        s.expire_all()

        r = _apply(client, c_user["token"], ["INV_ORD_STADEL"])
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "STATION_NOT_FOUND"
        assert body["data"] is None
        from app.models.invoice_request import InvoiceRequest
        assert s.query(InvoiceRequest).filter(
            InvoiceRequest.order_ids.contains("INV_ORD_STADEL")
        ).count() == 0


# ─── 用户端 列表 / 详情 ──────────────────────────────────────────────────────

class TestUserListDetail:
    def test_list_returns_own_requests_only(self, client, c_user, other_user):
        _make_order(client, c_user, "INV_ORD_010", 10.00, user_id=other_user["user"].id)
        # other_user 申请
        _apply(client, other_user["token"], ["INV_ORD_010"])
        # c_user 申请自己的
        _make_order(client, c_user, "INV_ORD_011", 10.00)
        _apply(client, c_user["token"], ["INV_ORD_011"])

        r = client.get("/api/v1/business/invoices", headers=_h(c_user["token"]))
        body = r.json()["data"]
        assert body["total"] == 1
        ids = [it["order_ids"] for it in body["items"]]
        assert ["INV_ORD_011"] in ids

    def test_detail_pending_has_no_invoice_file(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_012", 15.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_012"]).json()["data"]["invoice_id"]
        r = client.get(f"/api/v1/business/invoices/{inv_id}", headers=_h(c_user["token"]))
        assert r.json()["data"]["invoice_file"] is None

    def test_detail_other_user_not_found(self, client, c_user, other_user):
        _make_order(client, c_user, "INV_ORD_013", 15.00, user_id=other_user["user"].id)
        inv_id = _apply(client, other_user["token"], ["INV_ORD_013"]).json()["data"]["invoice_id"]
        r = client.get(f"/api/v1/business/invoices/{inv_id}", headers=_h(c_user["token"]))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_REQUEST_NOT_FOUND"
        assert body["data"] is None


# ─── 补发 / 改发邮箱 ─────────────────────────────────────────────────────────

class TestSendEmail:
    def test_send_email_pending_rejected(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_014", 15.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_014"]).json()["data"]["invoice_id"]
        r = client.post(f"/api/v1/business/invoices/{inv_id}/send-email",
                        json={"email": "x@example.com"}, headers=_h(c_user["token"]))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "INVOICE_NOT_ISSUED"
        assert body["data"] is None

    def test_send_email_after_issued(self, client, c_user, monkeypatch):
        _make_order(client, c_user, "INV_ORD_015", 15.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_015"]).json()["data"]["invoice_id"]

        called = {}
        def fake_send(to_email, subject, body_text, attachment_path=None):
            called["to"] = to_email
            return True
        monkeypatch.setattr(invoice_notification, "send_invoice_email", fake_send)

        # 运营上传发票 → ISSUED
        pdf = b"%PDF-1.4\nfake pdf content"
        up = client.post(
            f"/api/v1/ops/invoice-requests/{inv_id}/upload",
            files={"file": ("f.pdf", pdf, "application/pdf")},
        )
        assert up.status_code == 200

        # 补发到新邮箱
        r = client.post(f"/api/v1/business/invoices/{inv_id}/send-email",
                        json={"email": "new@example.com"}, headers=_h(c_user["token"]))
        assert r.status_code == 200
        assert r.json()["data"]["sent"] is True
        assert called.get("to") == "new@example.com"


# ─── 运营端: 列表 team 隔离 ───────────────────────────────────────────────────

class TestOpsList:
    def test_admin_sees_all(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_016", 12.00)
        _apply(client, c_user["token"], ["INV_ORD_016"])
        r = client.get("/api/v1/ops/invoice-requests")  # client 默认 admin
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1

    def test_team_isolation(self, client, c_user, team_pair):
        # c_user 的申请 team_id = 开票C端团队; team_pair A/B 是另外两个团队
        _make_order(client, c_user, "INV_ORD_017", 12.00)
        _apply(client, c_user["token"], ["INV_ORD_017"])
        # A 运营看不到 C端团队的申请
        r = client.get("/api/v1/ops/invoice-requests", headers=_h(team_pair["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0
        # admin 全可见
        r2 = client.get("/api/v1/ops/invoice-requests")
        assert r2.json()["data"]["total"] >= 1


# ─── 运营端: 上传发票文件 ─────────────────────────────────────────────────────

class TestOpsUpload:
    def test_upload_pdf_to_issued(self, client, c_user, monkeypatch):
        _make_order(client, c_user, "INV_ORD_018", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_018"]).json()["data"]["invoice_id"]

        notified = {}
        def fake_notify(req, file_url=None, db=None, openid=None):
            notified["id"] = req.id
        monkeypatch.setattr(invoice_notification, "notify_invoice_issued", fake_notify)

        pdf = b"%PDF-1.4\nfake pdf content"
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("发票.pdf", pdf, "application/pdf")})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["status"] == "issued"
        assert body["invoice_file_type"] == "pdf"
        assert notified.get("id") == inv_id  # 上传后触发通知

    def test_upload_bad_magic_bytes_rejected(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_019", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_019"]).json()["data"]["invoice_id"]
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.pdf", b"not a real pdf", "application/pdf")})
        assert r.status_code == 400
        assert "校验失败" in r.json()["detail"]

    def test_upload_image_jpeg(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_020", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_020"]).json()["data"]["invoice_id"]
        jpeg = b"\xff\xd8\xff\xe0fake jpeg"
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.jpg", jpeg, "image/jpeg")})
        assert r.status_code == 200
        assert r.json()["data"]["invoice_file_type"] == "image"

    def test_upload_ofd_zip(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_021", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_021"]).json()["data"]["invoice_id"]
        ofd = b"PK\x03\x04ofd content"
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.ofd", ofd, "application/ofd")})
        assert r.status_code == 200
        assert r.json()["data"]["invoice_file_type"] == "ofd"

    def test_upload_non_pending_rejected(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_022", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_022"]).json()["data"]["invoice_id"]
        pdf = b"%PDF-1.4\ncontent"
        client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                    files={"file": ("f.pdf", pdf, "application/pdf")})
        # 再次上传 (已 ISSUED) → 400
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.pdf", pdf, "application/pdf")})
        assert r.status_code == 400

    def test_upload_oversize_rejected(self, client, c_user, monkeypatch):
        from app.services import invoice_request_service
        _make_order(client, c_user, "INV_ORD_023", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_023"]).json()["data"]["invoice_id"]
        # 把上限调到 10 字节, 触发 size 校验 (避免构造 10MB 文件)
        monkeypatch.setattr(invoice_request_service, "MAX_INVOICE_FILE_BYTES", 10)
        pdf = b"%PDF-1.4\nthis is way too long to pass"
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.pdf", pdf, "application/pdf")})
        # 卡7502e6fb: read() 前 file.size 早拒, 400 → 413
        assert r.status_code == 413
        assert "10MB" in r.json()["detail"]

    def test_upload_cross_team_404(self, client, c_user, team_pair):
        _make_order(client, c_user, "INV_ORD_024", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_024"]).json()["data"]["invoice_id"]
        pdf = b"%PDF-1.4\ncontent"
        # A 运营上传 C端团队的申请 → 404 (不泄露存在)
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.pdf", pdf, "application/pdf")},
                        headers=_h(team_pair["tokens"]["a"]))
        assert r.status_code == 404

    def test_upload_cleans_orphan_file_on_commit_failure(self, client, c_user, monkeypatch):
        """文件孤儿防护 (卡4b14971e 修复点3): commit 失败时, 已落盘的发票文件必须清理,
        否则磁盘残留而 DB 无引用。"""
        import os
        from sqlalchemy.orm import Session
        from app.services import invoice_request_service

        _make_order(client, c_user, "INV_ORD_ORPHAN", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_ORPHAN"]).json()["data"]["invoice_id"]

        upload_dir = os.path.abspath(invoice_request_service._INVOICE_UPLOAD_DIR)
        before = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()

        def boom_commit(self, *a, **kw):
            raise RuntimeError("db commit down")
        monkeypatch.setattr(Session, "commit", boom_commit)

        pdf = b"%PDF-1.4\nfake pdf content"
        with pytest.raises(RuntimeError):
            client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                        files={"file": ("f.pdf", pdf, "application/pdf")})

        after = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()
        assert before == after  # 无新增孤儿文件


# ─── 运营端: 拒绝 + 状态机 ────────────────────────────────────────────────────

class TestOpsReject:
    def test_reject_to_rejected(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_025", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_025"]).json()["data"]["invoice_id"]
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/reject",
                        json={"reject_reason": "抬头错误"})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["status"] == "rejected"
        assert body["reject_reason"] == "抬头错误"

    def test_reject_without_reason_rejected(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_026", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_026"]).json()["data"]["invoice_id"]
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/reject",
                        json={"reject_reason": ""})
        assert r.status_code == 422

    def test_reject_cross_team_404(self, client, c_user, team_pair):
        _make_order(client, c_user, "INV_ORD_027", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_027"]).json()["data"]["invoice_id"]
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/reject",
                        json={"reject_reason": "x"}, headers=_h(team_pair["tokens"]["a"]))
        assert r.status_code == 404

    def test_reapply_after_rejected_allowed(self, client, c_user):
        """REJECTED 后用户可对同一订单重新申请 (新建 InvoiceRequest)。"""
        _make_order(client, c_user, "INV_ORD_028", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_028"]).json()["data"]["invoice_id"]
        # 拒绝
        client.post(f"/api/v1/ops/invoice-requests/{inv_id}/reject",
                    json={"reject_reason": "抬头错误"})
        # 同一订单重新申请 → 应成功 (REJECTED 不占位)
        r = _apply(client, c_user["token"], ["INV_ORD_028"])
        assert r.status_code == 202
        assert r.json()["data"]["invoice_id"] != inv_id  # 新建一条

    def test_reject_triggers_user_notification(self, client, c_user, monkeypatch):
        """拒绝通知 (卡4b14971e 修复点2): 拒绝成功后触发 notify_invoice_rejected,
        用户无需轮询即知被拒 (best-effort 不阻断主流程)。"""
        notified = {}

        def fake_notify(req, db=None, openid=None):
            notified["id"] = req.id
            notified["reason"] = req.reject_reason

        monkeypatch.setattr(invoice_notification, "notify_invoice_rejected",
                            fake_notify, raising=False)

        _make_order(client, c_user, "INV_ORD_REJ_NTF", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_REJ_NTF"]).json()["data"]["invoice_id"]
        r = client.post(f"/api/v1/ops/invoice-requests/{inv_id}/reject",
                        json={"reject_reason": "抬头错误"})
        assert r.status_code == 200
        assert notified.get("id") == inv_id
        assert notified.get("reason") == "抬头错误"


# ─── 签名 URL + 下载端点 ──────────────────────────────────────────────────────

class TestSignedUrl:
    def test_token_roundtrip(self):
        tok = invoice_notification.generate_file_token(99)
        assert invoice_notification.verify_file_token(tok) == 99

    def test_tampered_token_invalid(self):
        tok = invoice_notification.generate_file_token(99)
        assert invoice_notification.verify_file_token(tok[:-2] + "aa") is None
        assert invoice_notification.verify_file_token("garbage") is None

    def test_expired_token_invalid(self, monkeypatch):
        # max_age=-1: age(整数秒, ≥0) 恒 > -1 → 立即判定过期 (SignatureExpired)
        monkeypatch.setattr(invoice_notification, "SIGNED_URL_MAX_AGE", -1)
        tok = invoice_notification.generate_file_token(7)
        assert invoice_notification.verify_file_token(tok) is None

    def test_download_endpoint_valid(self, client, c_user):
        _make_order(client, c_user, "INV_ORD_029", 18.00)
        inv_id = _apply(client, c_user["token"], ["INV_ORD_029"]).json()["data"]["invoice_id"]
        client.post(f"/api/v1/ops/invoice-requests/{inv_id}/upload",
                    files={"file": ("f.pdf", b"%PDF-1.4\ncontent", "application/pdf")})
        # 从详情取签名 file_url
        detail = client.get(f"/api/v1/business/invoices/{inv_id}", headers=_h(c_user["token"]))
        file_url = detail.json()["data"]["invoice_file"]["file_url"]
        token = file_url.split("token=")[1]
        # 白名单免登录: 用 anon_client (无 Authorization) 下载
        client.headers.pop("Authorization", None)
        r = client.get(f"/api/v1/business/invoice-file?token={token}")
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_download_endpoint_invalid_token(self, client):
        client.headers.pop("Authorization", None)
        r = client.get("/api/v1/business/invoice-file?token=bad")
        assert r.status_code == 403

    def test_download_endpoint_missing_token(self, client):
        client.headers.pop("Authorization", None)
        r = client.get("/api/v1/business/invoice-file")
        assert r.status_code == 422  # Query(...) required


# ─── 邮件发送 mock ────────────────────────────────────────────────────────────

class TestEmailNotification:
    def test_send_invoice_email_mock_path_no_smtp(self, monkeypatch):
        # SMTP 未配置 → mock 日志路径, 返回 True
        import app.services.invoice_notification as mod
        monkeypatch.setattr(mod, "_smtp_configured", lambda: False)
        assert mod.send_invoice_email("a@b.com", "s", "b") is True

    def test_send_invoice_email_smtp_path(self, monkeypatch):
        import app.services.invoice_notification as mod
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)
        called = {}

        def fake_smtp(to_email, subject, body_text, attachment_path=None):
            called["to"] = to_email
        monkeypatch.setattr(mod, "_smtp_send", fake_smtp)

        assert mod.send_invoice_email("a@b.com", "s", "b", "/x/y.pdf") is True
        assert called["to"] == "a@b.com"

    def test_send_invoice_email_smtp_failure_returns_false(self, monkeypatch):
        import app.services.invoice_notification as mod
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)

        def boom(*a, **kw):
            raise RuntimeError("smtp down")
        monkeypatch.setattr(mod, "_smtp_send", boom)
        assert mod.send_invoice_email("a@b.com", "s", "b") is False

    def test_notify_invoice_issued_sends_email_when_email_present(self, monkeypatch):
        called = {}
        monkeypatch.setattr(invoice_notification, "send_invoice_email",
                            lambda *a, **kw: called.__setitem__("sent", True))
        monkeypatch.setattr(invoice_notification, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(invoice_notification, "_push_app_notification", lambda r, **kw: None)

        class Req:
            id = 1
            user_id = 2
            amount = 12800
            email = "user@example.com"
            title_name = "张三"
            invoice_file_path = None
        invoice_notification.notify_invoice_issued(Req())
        assert called.get("sent") is True

    def test_notify_invoice_issued_no_email_skips(self, monkeypatch):
        called = {}
        monkeypatch.setattr(invoice_notification, "send_invoice_email",
                            lambda *a, **kw: called.__setitem__("sent", True))
        monkeypatch.setattr(invoice_notification, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(invoice_notification, "_push_app_notification", lambda r, **kw: None)

        class Req:
            id = 1
            user_id = 2
            amount = 12800
            email = None
            title_name = "张三"
            invoice_file_path = None
        invoice_notification.notify_invoice_issued(Req())
        assert "sent" not in called

    def test_notify_invoice_rejected_sends_email_when_email_present(self, monkeypatch):
        called = {}
        monkeypatch.setattr(invoice_notification, "send_invoice_email",
                            lambda *a, **kw: called.__setitem__("sent", True))
        monkeypatch.setattr(invoice_notification, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(invoice_notification, "_push_app_notification", lambda r, **kw: None)

        class Req:
            id = 1
            user_id = 2
            amount = 12800
            email = "user@example.com"
            title_name = "张三"
            reject_reason = "抬头错误"
            invoice_file_path = None

        invoice_notification.notify_invoice_rejected(Req())
        assert called.get("sent") is True

    def test_notify_invoice_rejected_no_email_skips(self, monkeypatch):
        called = {}
        monkeypatch.setattr(invoice_notification, "send_invoice_email",
                            lambda *a, **kw: called.__setitem__("sent", True))
        monkeypatch.setattr(invoice_notification, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(invoice_notification, "_push_app_notification", lambda r, **kw: None)

        class Req:
            id = 1
            user_id = 2
            amount = 12800
            email = None
            title_name = "张三"
            reject_reason = "抬头错误"
            invoice_file_path = None

        invoice_notification.notify_invoice_rejected(Req())
        assert "sent" not in called


# ─── 认证 / 权限 ─────────────────────────────────────────────────────────────

class TestAuth:
    def test_anon_apply_unauthorized(self, client, anon_client):
        r = anon_client.post("/api/v1/business/invoices",
                             json={"order_ids": ["x"], "title_name": "张三"})
        assert r.status_code == 401

    def test_anon_list_unauthorized(self, client, anon_client):
        r = anon_client.get("/api/v1/business/invoices")
        assert r.status_code == 401

    def test_ops_requires_permission(self, client, c_user):
        # c_user 是 VIEWER, 无 operate:manage → 403
        r = client.get("/api/v1/ops/invoice-requests", headers=_h(c_user["token"]))
        assert r.status_code == 403
