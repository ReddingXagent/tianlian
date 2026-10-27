"""充电生命周期错误路径测试 — 契约 §7 (卡 46c42489, 不改生产代码)

钉死 §7 已实现但零测试覆盖的 5 个契约错误路径 + §7.2 stop 幂等语义:
- §7.1 CONNECTOR_BUSY: 创建订单时同 device+connector 已有 pending/charging 订单
- §7.1 OFFLINE:        设备离线
- §7.1 EXISTING_ORDER: 用户已有 pending/charging 未完成订单再创建
- §7.2 ORDER_NOT_CHARGING: stop 非 charging 状态 (pending) 订单
- §7.5 CANNOT_CANCEL:  取消非 pending 状态订单
- §7.2 幂等: 终态订单重复 stop 返回当前状态, 不重复下发 StopTransaction

契约: docs/contracts/user-client-contract.md §7 (v1.2)。
响应口径: 业务错误 HTTP 200 + code!=0 + message=原因码 (契约 §6)。
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

BASE = "/api/v1/business/orders"


# ─── helpers (模式参照 tests/test_business_order_detail.py) ───

def _add_user(session, username, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=UserRole.VIEWER,
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


@pytest.fixture
def c_user(client):
    """C 端用户 + 登录 token。"""
    u = _add_user(client._sesh, f"appuser_{uuid.uuid4().hex[:6]}")
    return u, _login_token(client, u.username)


@pytest.fixture
def station_and_device(client):
    st = Station(
        name="错误路径测试站",
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


def _seed_order(session, *, user_id, station_id, device_id, connector_id=1,
                order_status=OrderStatus.PENDING, charged_kwh=None,
                total_amount=None, start_time=None, duration_minutes=None):
    """指定状态的充电订单 (错误路径前置数据)。

    created_at 走模型默认 = 当前时刻 → pending 不会被建单防御的
    10 分钟超时清理 (cancel_stale_pending_for_user) 误取消,
    EXISTING_ORDER 语义可稳定断言。
    """
    o = ChargingOrder(
        order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        user_type=UserType.APP,
        connector_id=connector_id,
        order_status=order_status,
        payment_status=OrderPaymentStatus.UNPAID,
        charged_kwh=charged_kwh,
        total_amount=total_amount,
        start_time=start_time,
        duration_minutes=duration_minutes,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _create_body(st, dev, connector_id=1):
    return {
        "station_id": st.id,
        "device_id": dev.id,
        "connector_id": connector_id,
        "user_type": "app",
    }


# =====================================================================
# §7.1 POST /business/orders — CONNECTOR_BUSY
# =====================================================================

class TestConnectorBusy:
    def test_connector_busy_pending(self, client, c_user, station_and_device):
        """错误: 同 device+connector 已有他人 pending 订单 → CONNECTOR_BUSY。

        用另一用户的占用单排除 EXISTING_ORDER 优先命中 (实现的校验顺序:
        用户未完成订单在前, connector 占用在后)。
        """
        u, token = c_user
        st, dev = station_and_device
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh, user_id=other.id, station_id=st.id, device_id=dev.id,
            connector_id=1,
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CONNECTOR_BUSY"
        assert body["data"] is None

    def test_connector_busy_charging(self, client, c_user, station_and_device):
        """错误: 同 connector 已有 charging 订单 → CONNECTOR_BUSY。"""
        u, token = c_user
        st, dev = station_and_device
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh, user_id=other.id, station_id=st.id, device_id=dev.id,
            connector_id=2, order_status=OrderStatus.CHARGING,
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 2),
                        headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CONNECTOR_BUSY"

    def test_other_connector_available(self, client, c_user, station_and_device):
        """正常: connector 1 被占, 换 connector 2 → 201 pending。"""
        u, token = c_user
        st, dev = station_and_device
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh, user_id=other.id, station_id=st.id, device_id=dev.id,
            connector_id=1,
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 2),
                        headers=_auth(token))
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["order_status"] == "pending"
        assert body["data"]["payment_status"] == "unpaid"


# =====================================================================
# §7.1 POST /business/orders — OFFLINE
# =====================================================================

class TestOffline:
    def test_device_offline(self, client, c_user, station_and_device):
        """错误: 设备 OFFLINE → code!=0 OFFLINE。"""
        _, token = c_user
        st, dev = station_and_device
        dev.status = DeviceStatus.OFFLINE
        client._sesh.commit()
        r = client.post(f"{BASE}", json=_create_body(st, dev),
                        headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "OFFLINE"
        assert body["data"] is None

    def test_device_online_ok(self, client, c_user, station_and_device):
        """正常: 设备在线 → 201。"""
        _, token = c_user
        st, dev = station_and_device
        r = client.post(f"{BASE}", json=_create_body(st, dev),
                        headers=_auth(token))
        assert r.status_code == 201, r.text
        assert r.json()["code"] == 0


# =====================================================================
# §7.1 POST /business/orders — EXISTING_ORDER
# =====================================================================

class TestExistingOrder:
    def test_existing_pending_order(self, client, c_user, station_and_device):
        """错误: 用户已有 pending 订单 (新鲜, 未超时) → EXISTING_ORDER。"""
        u, token = c_user
        st, dev = station_and_device
        # 旧单占 connector 2, 新请求打 connector 1 → 排除 CONNECTOR_BUSY 干扰
        _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            connector_id=2,
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "EXISTING_ORDER"
        assert body["data"] is None

    def test_existing_charging_order(self, client, c_user, station_and_device):
        """错误: 用户已有 charging 订单 → EXISTING_ORDER (charging 绝不超时放行)。"""
        u, token = c_user
        st, dev = station_and_device
        _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            connector_id=2, order_status=OrderStatus.CHARGING,
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "EXISTING_ORDER"

    def test_no_active_order_create_ok(self, client, c_user, station_and_device):
        """正常: 用户历史订单均为终态 (completed/cancelled) → 可再建单 201。"""
        u, token = c_user
        st, dev = station_and_device
        _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            connector_id=2, order_status=OrderStatus.COMPLETED,
        )
        _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            connector_id=2, order_status=OrderStatus.CANCELLED,
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers=_auth(token))
        assert r.status_code == 201, r.text
        assert r.json()["code"] == 0


# =====================================================================
# §7.2 POST /orders/{id}/stop — ORDER_NOT_CHARGING
# =====================================================================

class TestOrderNotCharging:
    def test_stop_pending_order(self, client, c_user, station_and_device):
        """错误: pending 订单 stop → ORDER_NOT_CHARGING, 状态不变。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
        )
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_CHARGING"
        assert body["data"] is None
        # 状态未被误改
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.PENDING

    def test_stop_charging_order_ok(self, client, c_user, station_and_device):
        """正常: charging 订单 stop → completed + stop_reason=user_manual。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("23.50"),
            total_amount=Decimal("35.25"),
            start_time=datetime(2026, 8, 8, 6, 31, tzinfo=timezone.utc),
            duration_minutes=45,
        )
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["order_id"] == o.order_no
        assert data["order_status"] == "completed"
        assert data["stop_reason"] == "user_manual"
        assert data["charged_kwh"] == 23.50
        assert data["total_amount"] == 3525


# =====================================================================
# §7.2 stop 幂等语义
# =====================================================================

class TestStopIdempotency:
    def test_stop_completed_returns_current_state(self, client, c_user,
                                                  station_and_device):
        """幂等: completed 订单重复 stop → 200 code=0 返回当前状态,
        不重复下发 StopTransaction (mock 路径下以 stop_reason/字段保持佐证)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            order_status=OrderStatus.COMPLETED,
            charged_kwh=Decimal("23.50"),
            total_amount=Decimal("35.25"),
            duration_minutes=45,
        )
        o.stop_reason = "full"
        client._sesh.commit()

        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["order_id"] == o.order_no
        assert data["order_status"] == "completed"
        # 返回当前状态而非重新结算: stop_reason 保持 full, 未被覆写为 user_manual
        assert data["stop_reason"] == "full"

    def test_stop_cancelled_returns_current_state(self, client, c_user,
                                                  station_and_device):
        """幂等: cancelled 订单 stop → 返回当前 cancelled 状态 (非 ORDER_NOT_CHARGING)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            order_status=OrderStatus.CANCELLED,
        )
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["order_status"] == "cancelled"

    def test_stop_twice_second_is_idempotent(self, client, c_user,
                                             station_and_device):
        """幂等: charging → stop (completed) → 再 stop → 第二次返回当前状态。
        第二次不重新结算 (stop_reason/时长不因 now 变化被覆写)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("10.00"),
            total_amount=Decimal("15.00"),
            start_time=datetime(2026, 8, 8, 6, 31, tzinfo=timezone.utc),
            duration_minutes=45,
        )
        r1 = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r1.status_code == 200 and r1.json()["code"] == 0
        first = r1.json()["data"]
        assert first["order_status"] == "completed"

        r2 = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r2.status_code == 200 and r2.json()["code"] == 0
        second = r2.json()["data"]
        # 幂等: 第二次返回第一次结算的结果, 不重复下发/重新结算
        assert second["order_status"] == "completed"
        assert second["stop_reason"] == first["stop_reason"] == "user_manual"
        assert second["duration_minutes"] == first["duration_minutes"]
        assert second["total_amount"] == first["total_amount"]


# =====================================================================
# §7.5 POST /orders/{id}/cancel — CANNOT_CANCEL
# =====================================================================

class TestCannotCancel:
    @pytest.mark.parametrize("status", [
        OrderStatus.CHARGING,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    ])
    def test_cancel_non_pending(self, client, c_user, station_and_device, status):
        """错误: 非 pending 状态取消 → CANNOT_CANCEL, 状态不变。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
            order_status=status,
        )
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CANNOT_CANCEL"
        assert body["data"] is None
        client._sesh.refresh(o)
        assert o.order_status == status

    def test_cancel_pending_ok(self, client, c_user, station_and_device):
        """正常: pending 取消 → cancelled。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
        )
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["order_id"] == o.order_no
        assert body["data"]["order_status"] == "cancelled"
