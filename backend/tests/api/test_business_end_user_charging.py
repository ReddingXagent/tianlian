"""卡 089b01b2 — C端充电订单薄路由 (start-by-sn / pay / complete, 契约§7 端侧路径).

端侧调用 (BASE_URL=/api/v1, 无 /business 前缀):
- POST /charging-orders/start-by-sn   扫码启动 (sn → 设备 → 建单 + OCPP RemoteStart)
- POST /charging-orders/{id}/pay      直接支付 (wx.requestPayment 五字段)
- POST /charging-orders/{id}/complete 完成充电 (StopTransaction → completed)

鉴权: get_current_end_user (aud=end_user); 运营 token / 匿名 → 401。
订单归属: ChargingOrder.user_id == end_user.id (契约 §8.5 end_user_id↔user_id 映射落地)。
"""
import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.end_user import EndUser
from app.models.station import Station, StationStatus

AUTH_URL = "/api/v1/business/auth/wx-login"
BASE = "/api/v1/charging-orders"


def _login(client, code):
    r = client.post(AUTH_URL, json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _end_user(client, code):
    openid = "mock_" + hashlib.sha1(code.encode()).hexdigest()[:16]
    return client._sesh.query(EndUser).filter(EndUser.wx_openid == openid).one()


@pytest.fixture
def station_and_device(client):
    st = Station(
        name="C端充电站",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
    )
    client._sesh.add(st)
    client._sesh.commit()
    client._sesh.refresh(st)
    dev = Device(
        sn=f"SN{uuid.uuid4().hex[:10]}",
        name="充电桩",
        code=f"CHG{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC,
        status=DeviceStatus.ONLINE,
        station_id=st.id,
        rated_power=120.0,
        gun_count=2,
    )
    client._sesh.add(dev)
    client._sesh.commit()
    client._sesh.refresh(dev)
    return st, dev


def _seed_order(session, *, end_user_id, station_id, device_id, connector_id=1,
                order_status=OrderStatus.CHARGING, charged_kwh=Decimal("23.50"),
                total_amount=Decimal("35.25"), start_time=None,
                duration_minutes=45, payment_status=OrderPaymentStatus.UNPAID):
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=station_id,
        device_id=device_id,
        user_id=end_user_id,
        user_type=UserType.APP,
        connector_id=connector_id,
        order_status=order_status,
        payment_status=payment_status,
        charged_kwh=charged_kwh,
        total_amount=total_amount,
        start_time=start_time or datetime(2026, 8, 8, 6, 31, tzinfo=timezone.utc),
        duration_minutes=duration_minutes,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


# =====================================================================
# POST /charging-orders/start-by-sn
# =====================================================================

class TestStartBySn:
    def test_start_by_sn_ok(self, client, station_and_device):
        _, dev = station_and_device
        token = _login(client, "chg-user-1")
        r = client.post(f"{BASE}/start-by-sn", json={"sn": dev.sn},
                        headers=_headers(token))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["order_status"] == "pending"
        assert data["payment_status"] == "unpaid"
        assert data["device_id"] == dev.id
        assert data["connector_id"] == 1  # 默认枪号
        # 归属当前 C端用户 (契约 §8.5 映射)
        eu = _end_user(client, "chg-user-1")
        order = (
            client._sesh.query(ChargingOrder)
            .filter(ChargingOrder.order_no == data["order_id"])
            .one()
        )
        assert order.user_id == eu.id

    def test_start_by_sn_with_connector_id(self, client, station_and_device):
        _, dev = station_and_device
        token = _login(client, "chg-user-1b")
        r = client.post(f"{BASE}/start-by-sn",
                        json={"sn": dev.sn, "connector_id": 2},
                        headers=_headers(token))
        assert r.status_code == 201, r.text
        assert r.json()["data"]["connector_id"] == 2

    def test_start_by_sn_device_not_found(self, client):
        token = _login(client, "chg-user-2")
        r = client.post(f"{BASE}/start-by-sn", json={"sn": "NON_EXISTENT_SN"},
                        headers=_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "DEVICE_NOT_FOUND"
        assert body["data"] is None

    def test_start_by_sn_anonymous_401(self, anon_client, station_and_device):
        _, dev = station_and_device
        r = anon_client.post(f"{BASE}/start-by-sn", json={"sn": dev.sn})
        assert r.status_code == 401

    def test_start_by_sn_operate_token_401(self, client, station_and_device):
        """运营 token (aud 不符) 调 C端端点必须 401 (契约 §8 隔离)。"""
        _, dev = station_and_device
        r = client.post("/api/v1/auth/login",
                        data={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        admin_token = r.json()["data"]["token"]
        r2 = client.post(f"{BASE}/start-by-sn", json={"sn": dev.sn},
                         headers=_headers(admin_token))
        assert r2.status_code == 401


# =====================================================================
# POST /charging-orders/{id}/pay
# =====================================================================

class TestPay:
    def test_pay_ok(self, client, station_and_device):
        st, dev = station_and_device
        token = _login(client, "pay-user-1")
        eu = _end_user(client, "pay-user-1")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id)
        r = client.post(f"{BASE}/{o.order_no}/pay",
                        json={"openid": "oPayTest1", "scene": "miniprogram"},
                        headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        assert set(body["data"].keys()) == {
            "timeStamp", "nonceStr", "package", "signType", "paySign"
        }

    def test_pay_not_own_order(self, client, station_and_device):
        """他人订单支付 → ORDER_NOT_FOUND (不泄露存在性, 同 §7 口径)。"""
        st, dev = station_and_device
        other = _login(client, "pay-other")
        other_eu = _end_user(client, "pay-other")
        o = _seed_order(client._sesh, end_user_id=other_eu.id, station_id=st.id,
                        device_id=dev.id)
        mine = _login(client, "pay-mine")
        r = client.post(f"{BASE}/{o.order_no}/pay",
                        json={"openid": "oX", "scene": "miniprogram"},
                        headers=_headers(mine))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"

    def test_pay_order_not_found(self, client):
        token = _login(client, "pay-nf")
        r = client.post(f"{BASE}/TL_NOT_EXIST/pay",
                        json={"openid": "oX", "scene": "miniprogram"},
                        headers=_headers(token))
        assert r.status_code == 200
        assert r.json()["message"] == "ORDER_NOT_FOUND"

    def test_pay_anonymous_401(self, anon_client, client, station_and_device):
        st, dev = station_and_device
        o = _seed_order(client._sesh, end_user_id=999999, station_id=st.id,
                        device_id=dev.id)
        r = anon_client.post(f"{BASE}/{o.order_no}/pay",
                             json={"openid": "oX", "scene": "miniprogram"})
        assert r.status_code == 401


# =====================================================================
# POST /charging-orders/{id}/complete
# =====================================================================

class TestComplete:
    def test_complete_ok(self, client, station_and_device):
        st, dev = station_and_device
        token = _login(client, "cmp-user-1")
        eu = _end_user(client, "cmp-user-1")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id, order_status=OrderStatus.CHARGING)
        r = client.post(f"{BASE}/{o.order_no}/complete", headers=_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["order_id"] == o.order_no
        assert data["order_status"] == "completed"
        assert data["stop_reason"] == "user_manual"
        assert data["charged_kwh"] == 23.50
        assert data["total_amount"] == 3525

    def test_complete_not_charging(self, client, station_and_device):
        """pending 订单 complete → ORDER_NOT_CHARGING, 状态不变。"""
        st, dev = station_and_device
        token = _login(client, "cmp-user-2")
        eu = _end_user(client, "cmp-user-2")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id, order_status=OrderStatus.PENDING)
        r = client.post(f"{BASE}/{o.order_no}/complete", headers=_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_CHARGING"
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.PENDING

    def test_complete_idempotent_completed(self, client, station_and_device):
        """幂等: completed 订单 complete → 返回当前状态, 不重复结算。"""
        st, dev = station_and_device
        token = _login(client, "cmp-user-3")
        eu = _end_user(client, "cmp-user-3")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id, order_status=OrderStatus.COMPLETED,
                        charged_kwh=Decimal("10.00"),
                        total_amount=Decimal("15.00"))
        o.stop_reason = "full"
        client._sesh.commit()
        r = client.post(f"{BASE}/{o.order_no}/complete", headers=_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["order_status"] == "completed"
        assert body["data"]["stop_reason"] == "full"  # 未被覆写

    def test_complete_not_own_order(self, client, station_and_device):
        st, dev = station_and_device
        other = _login(client, "cmp-other")
        other_eu = _end_user(client, "cmp-other")
        o = _seed_order(client._sesh, end_user_id=other_eu.id, station_id=st.id,
                        device_id=dev.id)
        mine = _login(client, "cmp-mine")
        r = client.post(f"{BASE}/{o.order_no}/complete", headers=_headers(mine))
        assert r.status_code == 200
        assert r.json()["message"] == "ORDER_NOT_FOUND"

    def test_complete_anonymous_401(self, anon_client, client, station_and_device):
        st, dev = station_and_device
        o = _seed_order(client._sesh, end_user_id=999999, station_id=st.id,
                        device_id=dev.id)
        r = anon_client.post(f"{BASE}/{o.order_no}/complete")
        assert r.status_code == 401
