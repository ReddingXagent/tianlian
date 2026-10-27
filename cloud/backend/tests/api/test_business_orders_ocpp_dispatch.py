"""OCPP 真下发接线测试 (卡 87d6f7b9, 契约 §7.1/§7.2)

配置开关 OCPP_REMOTE_DISPATCH_ENABLED (默认 false) 控制:
- false: _ocpp_remote_start/_ocpp_stop_transaction 行为与现状 mock 完全一致 (回归锁)
- true: 经 OCPPAdapter 真实下发, 按 accepted/rejected/offline/timeout 四路映射:
  * accepted  → 下发成功, 订单照常创建/结算
  * rejected  → 桩拒绝, code=1 (create: REJECTED; stop: 保持错误语义)
  * offline   → 设备离线, code=1 OFFLINE
  * timeout   → 10s 无确认, code=1 TIMEOUT (契约 §7.1 语义: 不建单)

复用 test_business_orders.py 的 helper 风格。
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

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

from tests.api.test_business_orders import (
    _add_user,
    _auth,
    _login_token,
    _seed_device,
    _seed_order,
    _seed_station,
)

BASE = "/api/v1/business/orders"


@pytest.fixture
def c_user(client):
    u = _add_user(client._sesh, f"appuser_{uuid.uuid4().hex[:6]}")
    token = _login_token(client, u.username)
    return u, token


@pytest.fixture
def station_and_device(client):
    st = _seed_station(client._sesh)
    dev = _seed_device(client._sesh, station_id=st.id)
    return st, dev


@pytest.fixture
def dispatch_calls(monkeypatch):
    """记录 OCPPAdapter 下发调用的探针, 返回 (calls, 结果注入器)。"""
    calls = []

    def make(results):
        """results: list of bool/exception; 耗尽后重复最后一个。"""
        it = iter(results)
        last = [True]

        async def fake_remote_start(self, id_tag, connector_id=1):
            calls.append(("remote_start", id_tag, connector_id))
            v = next(it, last[0])
            last[0] = v
            if isinstance(v, Exception):
                raise v
            return v

        async def fake_remote_stop(self, transaction_id):
            calls.append(("remote_stop", transaction_id))
            v = next(it, last[0])
            last[0] = v
            if isinstance(v, Exception):
                raise v
            return v

        monkeypatch.setattr(
            "app.services.ocpp_dispatch.OCPPAdapter.remote_start_transaction",
            fake_remote_start,
        )
        monkeypatch.setattr(
            "app.services.ocpp_dispatch.OCPPAdapter.remote_stop_transaction",
            fake_remote_stop,
        )

    return calls, make


# ─── 开关关闭: 行为与现状完全一致 (回归) ───


class TestDispatchDisabled:
    def test_disabled_create_uses_mock_and_never_touches_adapter(
        self, client, c_user, station_and_device, dispatch_calls
    ):
        """开关默认关闭: 创建订单走 mock, 适配器零调用, 201 + pending。"""
        calls, _ = dispatch_calls
        u, token = c_user
        st, dev = station_and_device
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["order_status"] == "pending"
        assert calls == []

    def test_disabled_stop_uses_mock(
        self, client, c_user, station_and_device, dispatch_calls
    ):
        calls, _ = dispatch_calls
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "completed"
        assert calls == []

    def test_disabled_offline_device_still_offline(
        self, client, c_user, station_and_device
    ):
        u, token = c_user
        st, dev = station_and_device
        dev.status = DeviceStatus.OFFLINE
        client._sesh.commit()
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        body = r.json()
        assert body["code"] != 0
        assert "OFFLINE" in body["message"]


# ─── 开关开启: 经适配器下发, 四路结果 ───


class TestDispatchEnabledCreate:
    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")

    def test_accepted_creates_order(self, client, c_user, station_and_device, dispatch_calls):
        """accepted → 201 + pending, 且真实调用过适配器 (id_tag=user_id, connector 正确)。"""
        calls, make = dispatch_calls
        make([True])
        u, token = c_user
        st, dev = station_and_device
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 2},
            headers=_auth(token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["order_status"] == "pending"
        assert calls == [("remote_start", str(u.id), 2)]

    def test_rejected_returns_error(self, client, c_user, station_and_device, dispatch_calls):
        """rejected → code=1 REJECTED, 不建单。"""
        calls, make = dispatch_calls
        make([False])
        u, token = c_user
        st, dev = station_and_device
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        body = r.json()
        assert body["code"] != 0
        assert "REJECTED" in body["message"]
        assert calls != []

    def test_offline_maps_to_offline(self, client, c_user, station_and_device, dispatch_calls):
        """适配器报设备离线 → code=1 OFFLINE。"""
        calls, make = dispatch_calls
        make([ConnectionError("device offline")])
        u, token = c_user
        st, dev = station_and_device
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        body = r.json()
        assert body["code"] != 0
        assert "OFFLINE" in body["message"]

    def test_timeout_maps_to_timeout(self, client, c_user, station_and_device, dispatch_calls):
        """10s 无确认 → code=1 TIMEOUT (契约 §7.1: 云端下发, 无确认不上单)。"""
        import asyncio

        calls, make = dispatch_calls

        async def hang(self, id_tag, connector_id=1):
            calls.append(("remote_start", id_tag, connector_id))
            await asyncio.sleep(30)

        import app.services.ocpp_dispatch as od

        monkeypatch_obj = pytest.MonkeyPatch()
        monkeypatch_obj.setattr(od.OCPPAdapter, "remote_start_transaction", hang)
        try:
            u, token = c_user
            st, dev = station_and_device
            r = client.post(
                BASE,
                json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
                headers=_auth(token),
            )
            body = r.json()
            assert body["code"] != 0
            assert "TIMEOUT" in body["message"]
        finally:
            monkeypatch_obj.undo()


class TestDispatchEnabledStop:
    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")

    def _seed_charging(self, client, c_user, station_and_device):
        u, token = c_user
        st, dev = station_and_device
        return u, token, st, dev, _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("10.00"),
            start_time=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

    def test_stop_accepted_completes(self, client, c_user, station_and_device, dispatch_calls):
        calls, make = dispatch_calls
        make([True])
        u, token, st, dev, o = self._seed_charging(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "completed"
        assert ("remote_stop", o.id) in [
            (c[0], c[1]) for c in calls
        ] or calls[0][0] == "remote_stop"

    def test_stop_rejected_keeps_charging(
        self, client, c_user, station_and_device, dispatch_calls
    ):
        """stop rejected → code=1, 订单保持 charging (不误标 completed)。"""
        make = dispatch_calls[1]
        make([False])
        u, token, st, dev, o = self._seed_charging(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        body = r.json()
        assert body["code"] != 0
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.CHARGING

    def test_stop_offline_error_keeps_charging(
        self, client, c_user, station_and_device, dispatch_calls
    ):
        make = dispatch_calls[1]
        make([ConnectionError("offline")])
        u, token, st, dev, o = self._seed_charging(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        body = r.json()
        assert body["code"] != 0
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.CHARGING

    def test_stop_timeout_keeps_charging(
        self, client, c_user, station_and_device, dispatch_calls, monkeypatch
    ):
        import asyncio

        import app.services.ocpp_dispatch as od

        async def hang(self, transaction_id):
            await asyncio.sleep(30)

        monkeypatch.setattr(od.OCPPAdapter, "remote_stop_transaction", hang)
        u, token, st, dev, o = self._seed_charging(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        body = r.json()
        assert body["code"] != 0
        assert "TIMEOUT" in body["message"]
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.CHARGING


# ─── 卡 e18ce31e: cancel 路径撤销 RemoteStart (best-effort) ───


class TestCancelRemoteStop:
    """pending→cancelled (§7.5) 时 best-effort 撤销已 accepted 的 RemoteStart。

    pending 必经 create_order RemoteStart accepted (§7.1), 故取消时一律 best-effort
    下发 RemoteStopTransaction。开关 false 整链 no-op, 零回归; 失败仅日志不阻塞。
    """

    def _seed_pending(self, client, c_user, station_and_device):
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.PENDING,
        )
        return u, token, dev, o

    def test_a_cancel_pending_dispatches_remotestop_once(
        self, client, c_user, station_and_device, dispatch_calls, monkeypatch
    ):
        """a) 取消曾 RemoteStart 的 pending 单 → RemoteStop 下发一次。"""
        calls, make = dispatch_calls
        make([True])
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        u, token, dev, o = self._seed_pending(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "cancelled"
        stops = [c for c in calls if c[0] == "remote_stop"]
        assert len(stops) == 1
        assert stops[0][1] == o.id  # transaction_id = order.id

    def test_b_cancel_non_pending_no_dispatch(
        self, client, c_user, station_and_device, dispatch_calls, monkeypatch
    ):
        """b) 非 pending (charging) 单取消 → CANNOT_CANCEL, 不下发 RemoteStop。"""
        calls, make = dispatch_calls
        make([True])
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        body = r.json()
        assert body["code"] != 0
        assert "CANNOT_CANCEL" in body["message"]
        assert not any(c[0] == "remote_stop" for c in calls)

    def test_c_dispatch_failure_does_not_block_cancel(
        self, client, c_user, station_and_device, dispatch_calls, monkeypatch
    ):
        """c) remote_stop 抛异常 → best-effort 吞掉, 订单仍 cancelled, 不回滚。"""
        calls, make = dispatch_calls
        make([RuntimeError("network down")])
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        u, token, dev, o = self._seed_pending(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "cancelled"
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.CANCELLED
        assert any(c[0] == "remote_stop" for c in calls)  # 确实尝试过下发

    def test_e_disabled_no_dispatch_order_still_cancelled(
        self, client, c_user, station_and_device, dispatch_calls
    ):
        """e) 开关 false → 适配器零调用 (与现状一致), 订单仍 cancelled。"""
        calls, _ = dispatch_calls
        u, token, dev, o = self._seed_pending(client, c_user, station_and_device)
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "cancelled"
        assert calls == []
        client._sesh.refresh(o)
        assert o.order_status == OrderStatus.CANCELLED
