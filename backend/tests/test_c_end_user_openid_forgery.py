"""卡 9bee42cc — C端 pay 端点 openid 防伪造硬化.

契约 §8.5 / business.py:59-60: 切真实IM-B后 openid 必须从已认证用户记录取
(EndUser.wx_openid 唯一真相源), 禁止信任端侧 body.openid。
攻击面: 持有效 end_user token + 他人 openid → PaymentOrder.openid 与支付主体脱钩。
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
from app.models.payment_order import PaymentOrder
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
        name="openid防伪站",
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


def _seed_order(session, *, end_user_id, station_id, device_id):
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=station_id,
        device_id=device_id,
        user_id=end_user_id,
        user_type=UserType.APP,
        connector_id=1,
        order_status=OrderStatus.CHARGING,
        payment_status=OrderPaymentStatus.UNPAID,
        charged_kwh=Decimal("10.00"),
        total_amount=Decimal("15.00"),
        start_time=datetime(2026, 8, 8, 6, 31, tzinfo=timezone.utc),
        duration_minutes=30,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


class TestPayOpenidAntiForgery:
    def test_forged_openid_ignored(self, client, station_and_device):
        """伪造他人 openid → 落库仍是本人 wx_openid (不信任 body.openid)。"""
        st, dev = station_and_device
        token = _login(client, "forgery-user-1")
        eu = _end_user(client, "forgery-user-1")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id)
        r = client.post(f"{BASE}/{o.order_no}/pay",
                        json={"openid": "attacker_openid", "scene": "miniprogram"},
                        headers=_headers(token))
        assert r.status_code == 200, r.text
        assert r.json()["code"] == 0
        po = (client._sesh.query(PaymentOrder)
              .filter(PaymentOrder.business_order_no == o.order_no)
              .one())
        assert po.openid == eu.wx_openid
        assert po.openid != "attacker_openid"

    def test_own_order_openid_from_user_record(self, client, station_and_device):
        """正常本人订单 → openid 落库为本人 wx_openid。"""
        st, dev = station_and_device
        token = _login(client, "forgery-user-2")
        eu = _end_user(client, "forgery-user-2")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id)
        r = client.post(f"{BASE}/{o.order_no}/pay",
                        json={"openid": "whatever", "scene": "miniprogram"},
                        headers=_headers(token))
        assert r.status_code == 200, r.text
        assert r.json()["code"] == 0
        po = (client._sesh.query(PaymentOrder)
              .filter(PaymentOrder.business_order_no == o.order_no)
              .one())
        assert po.openid == eu.wx_openid

    def test_not_own_order_order_not_found(self, client, station_and_device):
        """非本人订单 → ORDER_NOT_FOUND (不泄露存在性)。"""
        st, dev = station_and_device
        _login(client, "forgery-other")
        other_eu = _end_user(client, "forgery-other")
        o = _seed_order(client._sesh, end_user_id=other_eu.id, station_id=st.id,
                        device_id=dev.id)
        mine = _login(client, "forgery-mine")
        r = client.post(f"{BASE}/{o.order_no}/pay",
                        json={"openid": "oX", "scene": "miniprogram"},
                        headers=_headers(mine))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"

    def test_empty_wx_openid_no_fallback(self, client, station_and_device):
        """wx_openid 异常为空串 (列为 NOT NULL, None 落不了库) → 受控业务错误,
        不得回退 body.openid。"""
        st, dev = station_and_device
        token = _login(client, "forgery-user-3")
        eu = _end_user(client, "forgery-user-3")
        o = _seed_order(client._sesh, end_user_id=eu.id, station_id=st.id,
                        device_id=dev.id)
        eu.wx_openid = ""
        client._sesh.commit()
        r = client.post(f"{BASE}/{o.order_no}/pay",
                        json={"openid": "attacker_openid", "scene": "miniprogram"},
                        headers=_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        # 绝不回退到 body.openid
        assert "attacker_openid" not in str(body)
        assert client._sesh.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == o.order_no).count() == 0
