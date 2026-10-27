"""工作卡 280c85ee — 云端配套④ IM-B服务商进件/统一下单/分账后端 (契约驱动)

契约: backend/docs/contracts/user-client-contract.md §2/§3/§4

覆盖:
- §2 支付: prepay 五字段逐一 / notify 幂等 / orders 查询 / SUB_MCH_FROZEN·NOT_READY 错误路径 / scene 校验
- §3 进件: 七态状态机迁移矩阵 (service 层) / 提交→AUDITING / advance→FINISH+sub_mchid / 查询 / 列表 team 隔离
- §4 平台服务费: CRUD + rate_bp 边界 + team 隔离
- 权限: VIEWER→403 / 匿名→401 / notify 白名单匿名可达
"""
from datetime import datetime

import bcrypt
import pytest

from app.models.merchant import ApplymentState, MerchantStatus, Merchant, MerchantType
from app.models.payment_order import PaymentOrder, PaymentStatus
from app.services.wx_pay import applyment as ap


# ─── 测试脚手架 ───

def _seed_team(client, name, code):
    from app.models.user import Team
    s = client._sesh
    t = Team(name=name, code=code)
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _seed_operator(client, username, team, pwd="mch123456"):
    from app.models.user import User, UserRole
    s = client._sesh
    u = User(
        username=username,
        real_name=username,
        role=UserRole.OPERATOR,
        team_id=team.id,
        status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": pwd}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json()["data"]["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _viewer_token(client):
    from app.models.user import User, UserRole
    s = client._sesh
    if not s.query(User).filter(User.username == "wx_viewer").first():
        s.add(
            User(
                username="wx_viewer",
                real_name="只读",
                role=UserRole.VIEWER,
                status="active",
                password_hash=bcrypt.hashpw(b"view123456", bcrypt.gensalt()).decode(),
            )
        )
        s.commit()
    r = client.post(
        "/api/v1/auth/login", data={"username": "wx_viewer", "password": "view123456"}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _applyment_payload(**over):
    p = {
        "merchant_type": "micro_merchant",
        "merchant_name": "张某某",
        "contact": {"name": "张某某", "phone": "138****0001"},
        "id_card": {"name": "张某某", "number": "***************001"},
        "settlement": {
            "account_type": "personal",
            "bank_name": "招商银行",
            "account_number": "************1234",
        },
        "station_ids": ["st_0001"],
    }
    p.update(over)
    return p


def _current_user_id(client):
    """client fixture 默认登录 admin, 取其 user.id (prepay 归属校验卡 031faccd)。"""
    from app.models.user import User
    return client._sesh.query(User).filter(User.username == "admin").one().id


def _seed_order_for_user(client, order_no, user_id):
    """建归属 user_id 的 ChargingOrder (最小链路: 站+桩+单), 供 prepay 归属校验通过。

    与 _link_merchant_to_order 区别: 不建商户链路, 供不关心 sub_mchid 的 prepay 测试。
    """
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.charging_order import ChargingOrder, OrderStatus

    s = client._sesh
    st = Station(
        name=f"站_{order_no}", code=f"ST_{order_no}",
        status=StationStatus.NORMAL,
    )
    s.add(st)
    s.commit()
    s.refresh(st)
    dev = Device(
        sn=f"SN_{order_no}", name="桩", code=f"CHG_{order_no}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st.id, rated_power=120.0,
    )
    s.add(dev)
    s.commit()
    s.refresh(dev)
    order = ChargingOrder(
        order_no=order_no, station_id=st.id, device_id=dev.id,
        user_id=user_id, order_status=OrderStatus.COMPLETED,
    )
    s.add(order)
    s.commit()
    return order


def _link_merchant_to_order(client, order_no, team_id, *, merchant_status, sub_mchid="2490000099", user_id=None):
    """seed 订单→站点→团队→商户 链路, 供 prepay 解析 sub_mchid + merchant_status。

    user_id: 绑定订单归属用户 (卡 031faccd prepay 归属校验); None → 绑当前登录 admin。
    """
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.charging_order import ChargingOrder, OrderStatus

    s = client._sesh
    st = Station(
        name=f"站_{order_no}", code=f"ST_{order_no}",
        status=StationStatus.NORMAL, team_id=team_id,
    )
    s.add(st)
    s.commit()
    s.refresh(st)
    dev = Device(
        sn=f"SN_{order_no}", name="桩", code=f"CHG_{order_no}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=st.id, rated_power=120.0,
    )
    s.add(dev)
    s.commit()
    s.refresh(dev)
    if user_id is None:
        user_id = _current_user_id(client)
    order = ChargingOrder(
        order_no=order_no, station_id=st.id, device_id=dev.id,
        user_id=user_id, order_status=OrderStatus.COMPLETED,
    )
    s.add(order)
    s.commit()
    m = Merchant(
        business_code=f"APL_{order_no}", team_id=team_id,
        merchant_type=MerchantType.MICRO_MERCHANT, merchant_name=f"商户_{order_no}",
        applyment_state=ApplymentState.FINISH, merchant_status=merchant_status,
        sub_mchid=sub_mchid,
    )
    s.add(m)
    s.commit()
    s.refresh(m)
    return m


def _refresh(session, obj):
    session.expire_all()
    return obj.__class__  # 返回类, 调用方自行 re-query


# ─── §3 进件状态机 (service 层纯函数 + 完整链路) ───

class TestApplymentStateMachine:
    """七态状态机迁移矩阵 (契约 §3.2)。"""

    def test_normal_path_editing_to_finish(self):
        s = ApplymentState.APPLYMENT_EDITING
        s = ap.transition(s, "submit")
        assert s == ApplymentState.AUDITING
        s = ap.transition(s, "audit_pass")
        assert s == ApplymentState.TO_BE_SIGNED
        s = ap.transition(s, "validate")
        assert s == ApplymentState.SIGNING
        s = ap.transition(s, "finish")
        assert s == ApplymentState.FINISH

    def test_reject_resubmit_loop(self):
        s = ap.transition(ApplymentState.AUDITING, "audit_reject")
        assert s == ApplymentState.REJECTED
        assert ap.transition(s, "resubmit") == ApplymentState.AUDITING

    def test_freeze_from_any_non_frozen_state(self):
        for st in ApplymentState:
            if st == ApplymentState.FROZEN:
                continue
            assert ap.transition(st, "freeze") == ApplymentState.FROZEN, st

    def test_frozen_unfreeze(self):
        assert ap.transition(ApplymentState.FROZEN, "unfreeze") == ApplymentState.AUDITING

    def test_illegal_transitions_return_none(self):
        # 跳级 / 终态后再迁移 → None
        assert ap.transition(ApplymentState.FINISH, "submit") is None
        assert ap.transition(ApplymentState.AUDITING, "finish") is None
        assert ap.transition(ApplymentState.APPLYMENT_EDITING, "finish") is None
        assert ap.transition(ApplymentState.FROZEN, "submit") is None
        assert ap.transition(ApplymentState.SIGNING, "audit_pass") is None

    def test_submit_state_initial(self, client):
        m = ap.submit_applyment(client._sesh, team_id=None, payload=_applyment_payload())
        assert m.applyment_state == ApplymentState.AUDITING
        assert m.merchant_status == MerchantStatus.PENDING
        assert m.sub_mchid is None
        assert m.business_code.startswith("APL_")

    def test_advance_to_finish_generates_sub_mchid_and_active(self, client):
        m = ap.submit_applyment(client._sesh, team_id=None, payload=_applyment_payload())
        for ev in ("audit_pass", "validate", "finish"):
            m = ap.advance(client._sesh, m, ev)
        assert m.applyment_state == ApplymentState.FINISH
        # 卡 d53a2f2f: mock 生成的 sub_mchid 带 mock_ 前缀 (原 "249" 前缀已改)
        assert m.sub_mchid and m.sub_mchid.startswith("mock_")
        assert m.merchant_status == MerchantStatus.ACTIVE

    def test_illegal_advance_raises(self, client):
        m = ap.submit_applyment(client._sesh, team_id=None, payload=_applyment_payload())
        with pytest.raises(ap.IllegalTransition):
            ap.advance(client._sesh, m, "finish")  # AUDITING 不能直接 finish

    def test_rejected_records_reason(self, client):
        m = ap.submit_applyment(client._sesh, team_id=None, payload=_applyment_payload())
        m = ap.advance(client._sesh, m, "audit_reject", reject_reason="材料不全")
        assert m.applyment_state == ApplymentState.REJECTED
        assert m.reject_reason == "材料不全"

    def test_to_be_signed_gets_validation_url(self, client):
        m = ap.submit_applyment(client._sesh, team_id=None, payload=_applyment_payload())
        m = ap.advance(client._sesh, m, "audit_pass")
        assert m.applyment_state == ApplymentState.TO_BE_SIGNED
        assert m.legal_validation_url and m.business_code in m.legal_validation_url


# ─── §3 进件端点 ───

class TestOpsMerchantsAPI:
    """运营平台 - 特约商户进件端点 (契约 §3.1/§3.2/§3.3)。"""

    def test_submit_returns_202_auditing(self, client):
        r = client.post("/api/v1/ops/merchants/applyment", json=_applyment_payload())
        assert r.status_code == 202
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["business_code"].startswith("APL_")
        assert data["data"]["applyment_state"] == "AUDITING"

    def test_get_applyment_detail(self, client):
        code = client.post(
            "/api/v1/ops/merchants/applyment", json=_applyment_payload()
        ).json()["data"]["business_code"]
        r = client.get(f"/api/v1/ops/merchants/applyment/{code}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["business_code"] == code
        assert d["applyment_state"] == "AUDITING"
        assert d["sub_mchid"] is None
        assert d["reject_reason"] is None
        assert "updated_at" in d

    def test_get_applyment_404(self, client):
        assert client.get("/api/v1/ops/merchants/applyment/APL_NOT_EXIST").status_code == 404

    def test_list_merchants_contract_shape(self, client):
        client.post("/api/v1/ops/merchants/applyment", json=_applyment_payload(merchant_name="A"))
        client.post("/api/v1/ops/merchants/applyment", json=_applyment_payload(merchant_name="B"))
        r = client.get("/api/v1/ops/merchants")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 2
        item = data["items"][0]
        # 契约 §3.3 列表项字段
        for key in ("business_code", "merchant_name", "merchant_type",
                    "applyment_state", "sub_mchid", "merchant_status",
                    "settlement", "profit_sharing_enabled", "station_ids"):
            assert key in item, f"列表项缺字段 {key}"
        assert "account_last4" in item["settlement"]

    def test_invalid_merchant_type_422(self, client):
        r = client.post(
            "/api/v1/ops/merchants/applyment",
            json=_applyment_payload(merchant_type="invalid_type"),
        )
        assert r.status_code == 422


# ─── §3 team 隔离 + 权限 ───

class TestMerchantTeamIsolation:
    def test_cross_team_404_and_list_scoping(self, client):
        ta = _seed_team(client, "商户团队A", "MCHTA")
        tb = _seed_team(client, "商户团队B", "MCHTB")
        tok_a = _seed_operator(client, "mch_op_a", ta)
        tok_b = _seed_operator(client, "mch_op_b", tb)

        code = client.post(
            "/api/v1/ops/merchants/applyment",
            json=_applyment_payload(merchant_name="A商户"),
            headers=_h(tok_a),
        ).json()["data"]["business_code"]

        # A 自己可查
        assert client.get(
            f"/api/v1/ops/merchants/applyment/{code}", headers=_h(tok_a)
        ).status_code == 200
        # B 跨团队查 → 404
        assert client.get(
            f"/api/v1/ops/merchants/applyment/{code}", headers=_h(tok_b)
        ).status_code == 404
        # B 列表只看本 team (空)
        assert client.get(
            "/api/v1/ops/merchants", headers=_h(tok_b)
        ).json()["data"]["total"] == 0
        # A 列表只看本 team (1)
        assert client.get(
            "/api/v1/ops/merchants", headers=_h(tok_a)
        ).json()["data"]["total"] == 1

    def test_admin_sees_all(self, client):
        ta = _seed_team(client, "商户团队C", "MCHTC")
        tok_a = _seed_operator(client, "mch_op_c", ta)
        client.post(
            "/api/v1/ops/merchants/applyment",
            json=_applyment_payload(), headers=_h(tok_a),
        )
        # admin (默认 client) 平台级全可见
        r = client.get("/api/v1/ops/merchants")
        assert r.json()["data"]["total"] >= 1


class TestMerchantPermission:
    def test_viewer_forbidden(self, client):
        tok = _viewer_token(client)
        r = client.post(
            "/api/v1/ops/merchants/applyment",
            json=_applyment_payload(), headers=_h(tok),
        )
        assert r.status_code == 403

    def test_anon_unauthorized(self, anon_client):
        r = anon_client.post("/api/v1/ops/merchants/applyment", json=_applyment_payload())
        assert r.status_code == 401


# ─── §2 支付 prepay ───

class TestPrepayContract:
    def test_prepay_five_fields_exactly(self, client):
        _seed_order_for_user(client, "ord_001", _current_user_id(client))
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_001", "openid": "oXXX", "scene": "miniprogram"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        five = data["data"]
        # 契约 §2.1: 端侧原样传入 wx.requestPayment, 五字段逐一 (camelCase)
        assert set(five.keys()) == {"timeStamp", "nonceStr", "package", "signType", "paySign"}
        assert five["signType"] == "RSA"
        assert five["package"].startswith("prepay_id=")
        assert len(five["timeStamp"]) > 0
        assert len(five["nonceStr"]) > 0
        assert len(five["paySign"]) > 0

    def test_prepay_scene_app(self, client):
        _seed_order_for_user(client, "ord_002", _current_user_id(client))
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_002", "openid": "oYYY", "scene": "app"},
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0
        assert set(r.json()["data"].keys()) == {"timeStamp", "nonceStr", "package", "signType", "paySign"}

    def test_prepay_invalid_scene_422(self, client):
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_003", "openid": "oZ", "scene": "web"},
        )
        assert r.status_code == 422

    def test_prepay_creates_payment_order_unpaid(self, client):
        _seed_order_for_user(client, "ord_track", _current_user_id(client))
        client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_track", "openid": "oT", "scene": "miniprogram"},
        )
        po = client._sesh.query(PaymentOrder).filter_by(business_order_no="ord_track").first()
        assert po is not None
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.prepay_id and po.prepay_id.startswith("wx")

    def test_prepay_sub_mch_frozen(self, client):
        team = _seed_team(client, "冻结团队", "FRZT")
        _link_merchant_to_order(
            client, "ord_frozen", team.id, merchant_status=MerchantStatus.FROZEN
        )
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_frozen", "openid": "oF", "scene": "miniprogram"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "SUB_MCH_FROZEN"
        assert body["data"] is None

    def test_prepay_sub_mch_not_ready(self, client):
        team = _seed_team(client, "未就绪团队", "PENDT")
        _link_merchant_to_order(
            client, "ord_pending", team.id, merchant_status=MerchantStatus.PENDING,
            sub_mchid=None,
        )
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_pending", "openid": "oP", "scene": "miniprogram"},
        )
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "SUB_MCH_NOT_READY"

    def test_prepay_active_merchant_succeeds(self, client):
        """关联 ACTIVE 商户 → 正常下单 (用真实 sub_mchid, 非默认降级)。"""
        team = _seed_team(client, "活跃团队", "ACTT")
        _link_merchant_to_order(
            client, "ord_active", team.id, merchant_status=MerchantStatus.ACTIVE,
            sub_mchid="2490000088",
        )
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_active", "openid": "oA", "scene": "miniprogram"},
        )
        assert r.json()["code"] == 0
        po = client._sesh.query(PaymentOrder).filter_by(business_order_no="ord_active").first()
        assert po.sub_mchid == "2490000088"


def _seed_other_user(client, username="other_owner"):
    """建另一个普通用户 (非当前 admin), 返回 user.id —— 供他人订单归属测试。"""
    from app.models.user import User, UserRole
    s = client._sesh
    u = User(
        username=username, real_name=username,
        role=UserRole.OPERATOR, status="active",
        password_hash=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u.id


class TestPrepayOwnership:
    """卡 031faccd — prepay 端点订单归属校验 (route 层)。

    安全契约: 调 payment.prepay 前必须校验
      1) 订单存在  2) order.user_id == 当前登录 user.id
    不存在 / 非本人订单统一回 ORDER_NOT_FOUND (不泄露存在性, 防枚举)。
    """

    def test_prepay_order_not_found(self, client):
        """订单不存在 → biz_error ORDER_NOT_FOUND (不进 payment service)。"""
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_never_exists", "openid": "oX", "scene": "miniprogram"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None
        # 未落 PaymentOrder (校验在 service 前)
        assert (
            client._sesh.query(PaymentOrder)
            .filter_by(business_order_no="ord_never_exists")
            .first()
            is None
        )

    def test_prepay_other_users_order_returns_not_found(self, client):
        """他人订单 (order.user_id != 当前 user) → ORDER_NOT_FOUND, 不泄露存在性。"""
        other_uid = _seed_other_user(client)
        _seed_order_for_user(client, "ord_others", other_uid)
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_others", "openid": "oX", "scene": "miniprogram"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_prepay_own_order_succeeds(self, client):
        """本人订单 → 正常五字段 (归属校验通过, 对照组)。"""
        _seed_order_for_user(client, "ord_mine", _current_user_id(client))
        r = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_mine", "openid": "oX", "scene": "miniprogram"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert set(data["data"].keys()) == {
            "timeStamp", "nonceStr", "package", "signType", "paySign"
        }

    def test_prepay_anon_unauthorized(self, anon_client):
        """无认证 → 401 (FastAPI HTTPException, 非业务 code)。"""
        r = anon_client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_x", "openid": "oX", "scene": "miniprogram"},
        )
        assert r.status_code == 401


# ─── §2.2 回调幂等 ───

class TestNotifyIdempotent:
    def _prepay_out(self, client, order_id):
        _seed_order_for_user(client, order_id, _current_user_id(client))
        client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": order_id, "openid": "oX", "scene": "miniprogram"},
        )
        client._sesh.expire_all()
        return (
            client._sesh.query(PaymentOrder)
            .filter_by(business_order_no=order_id)
            .first()
            .out_trade_no
        )

    def test_notify_marks_paid(self, client):
        out = self._prepay_out(client, "ord_pay1")
        body = {
            "out_trade_no": out, "transaction_id": "4200001234",
            "trade_state": "SUCCESS", "amount": {"total": 0},
        }
        r = client.post("/api/v1/business/payments/notify", json=body)
        assert r.status_code == 200
        assert r.json() == {"code": "SUCCESS", "message": "成功"}
        client._sesh.expire_all()
        po = client._sesh.query(PaymentOrder).filter_by(out_trade_no=out).first()
        assert po.payment_status == PaymentStatus.PAID
        assert po.wx_transaction_id == "4200001234"
        assert po.paid_at is not None
        assert po.notify_processed is True
        assert po.notify_count == 1

    def test_notify_idempotent_repeat(self, client):
        out = self._prepay_out(client, "ord_pay2")
        body = {
            "out_trade_no": out, "transaction_id": "4200009999",
            "trade_state": "SUCCESS", "amount": {"total": 0},
        }
        client.post("/api/v1/business/payments/notify", json=body)
        client.post("/api/v1/business/payments/notify", json=body)
        client._sesh.expire_all()
        po = client._sesh.query(PaymentOrder).filter_by(out_trade_no=out).first()
        # 幂等: 第二次不重复处理 (transaction_id 不被覆盖, 状态仍 PAID), 但 count 累加
        assert po.notify_count == 2
        assert po.wx_transaction_id == "4200009999"
        assert po.payment_status == PaymentStatus.PAID

    def test_notify_anon_accessible(self, anon_client):
        """notify 在白名单, IM-B回调无 user token 也可达。"""
        body = {
            "out_trade_no": "TL_NOT_EXIST", "transaction_id": "4200",
            "trade_state": "SUCCESS", "amount": {"total": 0},
        }
        r = anon_client.post("/api/v1/business/payments/notify", json=body)
        assert r.status_code == 200
        assert r.json()["code"] == "SUCCESS"

    def test_notify_bad_body_fail(self, anon_client):
        """验签/解析失败 → FAIL (mock: 非法 JSON body)。"""
        r = anon_client.post(
            "/api/v1/business/payments/notify",
            content=b"not-json", headers={"content-type": "application/json"},
        )
        assert r.json()["code"] == "FAIL"


# ─── §2.3 订单/支付状态查询 ───

class TestOrderStatusQuery:
    def test_unpaid_placeholder_when_no_payment(self, client):
        r = client.get("/api/v1/business/orders/ord_none")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["order_id"] == "ord_none"
        assert d["payment_status"] == "UNPAID"
        assert d["transaction_id"] is None
        assert d["paid_at"] is None

    def test_paid_after_notify(self, client):
        _seed_order_for_user(client, "ord_q1", _current_user_id(client))
        client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_q1", "openid": "oX", "scene": "miniprogram"},
        )
        client._sesh.expire_all()
        po = client._sesh.query(PaymentOrder).filter_by(business_order_no="ord_q1").first()
        client.post(
            "/api/v1/business/payments/notify",
            json={"out_trade_no": po.out_trade_no, "transaction_id": "4200111",
                  "trade_state": "SUCCESS", "amount": {"total": 0}},
        )
        r = client.get("/api/v1/business/orders/ord_q1")
        d = r.json()["data"]
        assert d["payment_status"] == "PAID"
        assert d["transaction_id"] == "4200111"
        assert d["paid_at"] is not None

    def test_get_own_order_lightweight(self, client):
        """卡 b9518748 — 查询本人订单 (有 PAID PaymentOrder) → 正常返回 paid 信息。"""
        _seed_order_for_user(client, "ord_own", _current_user_id(client))
        s = client._sesh
        s.add(
            PaymentOrder(
                out_trade_no="TL_own", business_order_no="ord_own",
                openid="oOWN", scene="miniprogram", sub_mchid="2490000099", amount_fen=200,
                payment_status=PaymentStatus.PAID,
                wx_transaction_id="4200OWN", paid_at=datetime(2026, 8, 8, 15, 18),
            )
        )
        s.commit()
        client._sesh.expire_all()
        r = client.get("/api/v1/business/orders/ord_own")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["payment_status"] == "PAID"
        assert d["transaction_id"] == "4200OWN"
        assert d["paid_at"] is not None

    def test_get_other_users_order_returns_unpaid(self, client):
        """卡 b9518748 — 查询他人订单 → 返回 UNPAID 占位, 不泄露订单存在性与支付信息。"""
        # 建一个归属"他人" (user_id != 当前 admin) 的订单 + PAID 支付行
        _seed_order_for_user(client, "ord_other", user_id=_current_user_id(client) + 999999)
        s = client._sesh
        s.add(
            PaymentOrder(
                out_trade_no="TL_other", business_order_no="ord_other",
                openid="oSECRET", scene="miniprogram", sub_mchid="2490000099", amount_fen=500,
                payment_status=PaymentStatus.PAID,
                wx_transaction_id="4200SECRET", paid_at=datetime(2026, 8, 8, 9, 0),
            )
        )
        s.commit()
        client._sesh.expire_all()
        r = client.get("/api/v1/business/orders/ord_other")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["payment_status"] == "UNPAID"
        assert d["transaction_id"] is None
        assert d["paid_at"] is None

    def test_get_nonexistent_order_returns_unpaid(self, client):
        """卡 b9518748 — 查询不存在订单 → UNPAID (现有行为不变, 不泄露存在性)。"""
        r = client.get("/api/v1/business/orders/ord_never_exists")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["payment_status"] == "UNPAID"
        assert d["transaction_id"] is None
        assert d["paid_at"] is None


# ─── §2 财务边界 (工作卡 16209d26) ───

class TestPrepayFinancialBoundary:
    """卡 16209d26 — 重复 prepay 掩盖已支付 / 查询异常零日志 / 单号 UTC 日期 三处缺口。

    修复点 1 重复 prepay 掩盖已支付:
      - 已有 PAID 行 → raise 业务错误 (ORDER_ALREADY_PAID)
      - 已有 UNPAID 行 → 复用其 out_trade_no 重新发起 (刷新 prepay_id, 不新建行)
      - get_order_payment 状态优先级 PAID > UNPAID > CLOSED
    修复点 2: _lookup_merchant_by_order 查询异常补 logger.exception (含 business_order_no)
    修复点 3: generate_out_trade_no 用 Asia/Shanghai 业务日, 不用 UTC
    """

    def test_prepay_reuses_unpaid_row_idempotent(self, client):
        """已有 UNPAID 行: 重复 prepay 复用 out_trade_no 重新发起, 不新建行。"""
        _seed_order_for_user(client, "ord_reuse", _current_user_id(client))
        r1 = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_reuse", "openid": "oR", "scene": "miniprogram"},
        )
        assert r1.json()["code"] == 0
        client._sesh.expire_all()
        po1 = (
            client._sesh.query(PaymentOrder)
            .filter_by(business_order_no="ord_reuse")
            .one()
        )
        first_out, first_prepay = po1.out_trade_no, po1.prepay_id

        r2 = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_reuse", "openid": "oR", "scene": "miniprogram"},
        )
        assert r2.json()["code"] == 0
        client._sesh.expire_all()
        rows = (
            client._sesh.query(PaymentOrder)
            .filter_by(business_order_no="ord_reuse")
            .all()
        )
        assert len(rows) == 1                       # 复用, 不新建行
        assert rows[0].out_trade_no == first_out    # 单号复用
        assert rows[0].prepay_id != first_prepay    # 重新发起, prepay_id 刷新
        assert rows[0].payment_status == PaymentStatus.UNPAID

    def test_prepay_rejects_already_paid(self, client):
        """已 PAID 订单重复 prepay → ORDER_ALREADY_PAID (code!=0, data=null)。"""
        _seed_order_for_user(client, "ord_paid2", _current_user_id(client))
        client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_paid2", "openid": "oP", "scene": "miniprogram"},
        )
        client._sesh.expire_all()
        out = (
            client._sesh.query(PaymentOrder)
            .filter_by(business_order_no="ord_paid2")
            .one()
            .out_trade_no
        )
        client.post(
            "/api/v1/business/payments/notify",
            json={
                "out_trade_no": out, "transaction_id": "4200",
                "trade_state": "SUCCESS", "amount": {"total": 0},
            },
        )
        r2 = client.post(
            "/api/v1/business/payments/prepay",
            json={"order_id": "ord_paid2", "openid": "oP", "scene": "miniprogram"},
        )
        body = r2.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_ALREADY_PAID"
        assert body["data"] is None

    def test_get_order_payment_priority_paid_over_unpaid(self, client):
        """同 order 多行 PaymentOrder: get_order_payment 优先级 PAID > UNPAID > CLOSED。"""
        from app.models.payment_order import PayScene
        from app.services.wx_pay import payment as paymod

        s = client._sesh
        # 故意让最新行 (id 最大) = CLOSED 最低优先级, 暴露 "order_by id desc 取最新行" 的 bug
        for i, st in enumerate(
            (PaymentStatus.PAID, PaymentStatus.UNPAID, PaymentStatus.CLOSED)
        ):
            s.add(
                PaymentOrder(
                    out_trade_no=f"TL_prio_{i}",
                    business_order_no="ord_prio",
                    openid="oX",
                    scene=PayScene.MINIPROGRAM,
                    sub_mchid="2490000000",
                    amount_fen=0,
                    payment_status=st,
                )
            )
        s.commit()
        info = paymod.get_order_payment(s, "ord_prio")
        assert info is not None
        assert info["payment_status"] == "PAID"

    def test_lookup_merchant_logs_on_exception(self, caplog):
        """_lookup_merchant_by_order 查询异常 → 降级 None 且 logger.exception 含 business_order_no。"""
        import logging

        from app.services.wx_pay import payment as paymod

        class BoomDB:
            def query(self, *a, **k):
                raise RuntimeError("db boom")

        with caplog.at_level(logging.ERROR, logger="app.services.wx_pay.payment"):
            result = paymod._lookup_merchant_by_order(BoomDB(), "ord_log_ctx")
        assert result is None
        msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("ord_log_ctx" in m for m in msgs), msgs

    def test_out_trade_no_uses_cst_business_day(self, monkeypatch):
        """generate_out_trade_no 取 Asia/Shanghai 业务日 (非 UTC), 跨日边界验证。"""
        from datetime import datetime as real_dt, timezone

        from app.services.wx_pay import payment as paymod

        # UTC 2026-08-07 18:00 == CST 2026-08-08 02:00 (UTC/CST 跨日)
        base_utc = real_dt(2026, 8, 7, 18, 0, 0, tzinfo=timezone.utc)

        class FakeDateTime:
            @classmethod
            def now(cls, tz=None):
                return base_utc if tz is None else base_utc.astimezone(tz)

        monkeypatch.setattr(paymod, "datetime", FakeDateTime)
        no = paymod.generate_out_trade_no()
        # UTC 业务日=20260807 / CST 业务日=20260808 → 必须取 CST
        assert no.startswith("TL_20260808_")
        assert len(no) == len("TL_20260808_") + 16  # secrets.token_hex(8) → 16 hex


# ─── §4 平台服务费配置 ───

class TestPlatformFee:
    def test_create_list_update_delete(self, client):
        r = client.post(
            "/api/v1/ops/platform-fee",
            json={"rate_bp": 100, "scope": "all", "enabled": False},
        )
        assert r.status_code == 201
        cfg = r.json()["data"]
        assert cfg["rate_bp"] == 100
        assert cfg["enabled"] is False
        assert cfg["scope"] == "all"
        cid = cfg["id"]

        # list
        assert client.get("/api/v1/ops/platform-fee").json()["data"]["total"] >= 1
        # update
        r = client.put(
            f"/api/v1/ops/platform-fee/{cid}",
            json={"rate_bp": 200, "scope": "whitelist", "user_ids": [1, 2]},
        )
        assert r.json()["data"]["rate_bp"] == 200
        assert r.json()["data"]["scope"] == "whitelist"
        assert r.json()["data"]["user_ids"] == [1, 2]
        # delete
        assert client.delete(f"/api/v1/ops/platform-fee/{cid}").status_code == 200

    def test_rate_bp_boundary(self, client):
        # 超 3000 → 422 (Pydantic Field le=3000)
        assert client.post("/api/v1/ops/platform-fee", json={"rate_bp": 3001}).status_code == 422
        assert client.post("/api/v1/ops/platform-fee", json={"rate_bp": -1}).status_code == 422
        # 边界 0 / 3000 合法
        assert client.post("/api/v1/ops/platform-fee", json={"rate_bp": 0}).status_code == 201
        assert client.post("/api/v1/ops/platform-fee", json={"rate_bp": 3000}).status_code == 201

    def test_team_isolation_cross_team_404(self, client):
        ta = _seed_team(client, "费率团队A", "FEETA")
        tb = _seed_team(client, "费率团队B", "FEETB")
        tok_a = _seed_operator(client, "fee_op_a", ta)
        tok_b = _seed_operator(client, "fee_op_b", tb)
        cid = client.post(
            "/api/v1/ops/platform-fee", json={"rate_bp": 50}, headers=_h(tok_a),
        ).json()["data"]["id"]
        # A 可改
        assert client.put(
            f"/api/v1/ops/platform-fee/{cid}", json={"rate_bp": 60}, headers=_h(tok_a),
        ).status_code == 200
        # B 跨团队改 → 404
        assert client.put(
            f"/api/v1/ops/platform-fee/{cid}", json={"rate_bp": 99}, headers=_h(tok_b),
        ).status_code == 404
        # B 列表只看本 team (空)
        assert client.get(
            "/api/v1/ops/platform-fee", headers=_h(tok_b),
        ).json()["data"]["total"] == 0

    def test_enabled_default_false(self, client):
        """契约 §4: 当前 enabled=false, 支付流程零感知。"""
        r = client.post("/api/v1/ops/platform-fee", json={"rate_bp": 100})
        assert r.json()["data"]["enabled"] is False


# ─── 卡 7669b9b1 — mock 模式伪造面: 生产/非 DEBUG 下 notify 拒绝 ───

class TestNotifyMockGuard:
    """WX_PAY_MODE=mock 且非开发环境时, 公开回调端点必须拒绝处理 (不落 PAID)。

    攻击链: mock 不验签 → 伪造 SUCCESS 报文 → 0 元购电。守卫放 router 层
    (侵入最小), 用 settings.ENVIRONMENT/DEBUG 判定, 不引入新配置项。
    """

    def _forge_notify(self, client, out):
        return client.post(
            "/api/v1/business/payments/notify",
            json={
                "out_trade_no": out, "transaction_id": "fake_tx",
                "trade_state": "SUCCESS", "amount": {"total": 0},
            },
        )

    def test_mock_prod_notify_rejected(self, client, monkeypatch):
        """mock + ENVIRONMENT=production + DEBUG=False → 503, 订单不落 PAID。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WX_PAY_MODE", "mock")
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "DEBUG", False)

        out = TestNotifyIdempotent._prepay_out(TestNotifyIdempotent(), client, "ord_guard1")
        r = self._forge_notify(client, out)
        assert r.status_code == 503
        assert r.json()["code"] == "FAIL"
        client._sesh.expire_all()
        po = client._sesh.query(PaymentOrder).filter_by(out_trade_no=out).first()
        assert po.payment_status != PaymentStatus.PAID
        assert po.paid_at is None

    def test_mock_debug_false_dev_env_still_blocked(self, client, monkeypatch):
        """mock + DEBUG=False (即使 ENVIRONMENT 非 production) → 同样拒绝。

        与 config.py 生产判定口径一致: DEBUG=False 即非开发形态。
        """
        from app.core.config import settings
        monkeypatch.setattr(settings, "WX_PAY_MODE", "mock")
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        monkeypatch.setattr(settings, "DEBUG", False)

        out = TestNotifyIdempotent._prepay_out(TestNotifyIdempotent(), client, "ord_guard2")
        r = self._forge_notify(client, out)
        assert r.status_code == 503

    def test_mock_debug_true_notify_still_works(self, client, monkeypatch):
        """mock + DEBUG=True (开发/测试) → notify 保留可用。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WX_PAY_MODE", "mock")
        monkeypatch.setattr(settings, "DEBUG", True)

        out = TestNotifyIdempotent._prepay_out(TestNotifyIdempotent(), client, "ord_guard3")
        r = self._forge_notify(client, out)
        assert r.status_code == 200
        assert r.json()["code"] == "SUCCESS"
        client._sesh.expire_all()
        po = client._sesh.query(PaymentOrder).filter_by(out_trade_no=out).first()
        assert po.payment_status == PaymentStatus.PAID

    def test_real_mode_not_blocked(self, client, monkeypatch):
        """real 模式 → 不走 mock 拒绝分支 (只断言非 503; 真实验签在 service 层)。"""
        from app.core.config import settings
        monkeypatch.setattr(settings, "WX_PAY_MODE", "real")
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "DEBUG", False)

        r = client.post(
            "/api/v1/business/payments/notify",
            content=b"{}", headers={"content-type": "application/json"},
        )
        assert r.status_code != 503
