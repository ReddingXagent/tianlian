"""僵尸 pending 订单清理接线测试 (卡 eb9f824b)

覆盖:
- celery task maintenance.cleanup_stale_pending_orders 手动调用:
  超 cutoff 的 pending → cancelled (stop_reason=pending_timeout),
  未超时 pending / charging / completed 不动。
- celery_app 注册名 + beat_schedule 含 */5 调度 (queue=maintenance)。
- (加分项3) create_order CONNECTOR_BUSY 分支的超时豁免:
  他人超时 pending 占桩 → 清理后放行 201; 新鲜 pending / charging 占桩 → 仍 BUSY。

设计: task 测试走 test_db fixture (task 内懒加载 SessionLocal → 被覆盖为测试库);
busy 豁免测试走 conftest client (API 集成)。
"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest

import app.tasks.maintenance_tasks  # noqa: F401 触发 @shared_task 注册

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


# ─── helpers ───

def _seed_order(session, *, order_no, user_id, station_id, device_id,
                connector_id=1, status=OrderStatus.PENDING, created_at=None):
    o = ChargingOrder(
        order_no=order_no,
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        user_type=UserType.APP,
        connector_id=connector_id,
        order_status=status,
        payment_status=OrderPaymentStatus.UNPAID,
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


# ═══════════════════════════════════════════════════════════════
# Celery task 注册 + beat_schedule
# ═══════════════════════════════════════════════════════════════

class TestTaskRegistration:
    def test_task_registered_in_celery_app(self):
        from app.core.celery_app import celery_app
        assert "maintenance.cleanup_stale_pending_orders" in celery_app.tasks

    def test_in_beat_schedule_every_5min(self):
        from app.core.celery_app import celery_app
        sched = celery_app.conf.beat_schedule.get("stale-pending-order-cleanup")
        assert sched is not None, "beat_schedule 缺 stale-pending-order-cleanup"
        assert sched["task"] == "maintenance.cleanup_stale_pending_orders"
        assert sched["schedule"].minute == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55} \
            or str(sched["schedule"]._orig_minute) == "*/5"
        assert sched["options"].get("queue") == "maintenance"


# ═══════════════════════════════════════════════════════════════
# Task 手动调用 (真实 DB)
# ═══════════════════════════════════════════════════════════════

class TestCleanupTaskRun:
    @pytest.fixture(autouse=True)
    def _patch_session_local(self, test_db, monkeypatch):
        # _run_db_task 用模块级 SessionLocal (import 时绑定) → monkeypatch 到
        # test_db 的测试库 SessionLocal (卡 a6e2e562: 还原由 monkeypatch 兜底)。
        import app.tasks.maintenance_tasks as mt
        monkeypatch.setattr(mt, "SessionLocal", test_db["SessionLocal"])

    def test_stale_pending_cancelled_by_task(self, test_db):
        from app.tasks.maintenance_tasks import cleanup_stale_pending_orders_task
        db = test_db["session"]
        old = datetime.now(timezone.utc) - timedelta(minutes=15)
        _seed_order(db, order_no="TASK_OLD1", user_id=100, station_id=1,
                    device_id=1, created_at=old)

        result = cleanup_stale_pending_orders_task()

        assert result["cancelled"] >= 1
        db.expire_all()
        order = db.query(ChargingOrder).filter_by(order_no="TASK_OLD1").one()
        assert order.order_status == OrderStatus.CANCELLED
        assert order.stop_reason == "pending_timeout"

    def test_fresh_and_non_pending_untouched(self, test_db):
        from app.tasks.maintenance_tasks import cleanup_stale_pending_orders_task
        db = test_db["session"]
        now = datetime.now(timezone.utc)
        _seed_order(db, order_no="TASK_FRESH", user_id=100, station_id=1,
                    device_id=1, created_at=now - timedelta(minutes=3))
        _seed_order(db, order_no="TASK_CHG", user_id=101, station_id=1,
                    device_id=2, status=OrderStatus.CHARGING,
                    created_at=now - timedelta(minutes=60))
        _seed_order(db, order_no="TASK_DONE", user_id=102, station_id=1,
                    device_id=3, status=OrderStatus.COMPLETED,
                    created_at=now - timedelta(minutes=60))

        cleanup_stale_pending_orders_task()

        db.expire_all()
        assert db.query(ChargingOrder).filter_by(order_no="TASK_FRESH").one().order_status == OrderStatus.PENDING
        assert db.query(ChargingOrder).filter_by(order_no="TASK_CHG").one().order_status == OrderStatus.CHARGING
        assert db.query(ChargingOrder).filter_by(order_no="TASK_DONE").one().order_status == OrderStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════
# (加分项3) CONNECTOR_BUSY 分支的超时豁免 (API 集成)
# ═══════════════════════════════════════════════════════════════

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
    assert r.status_code == 200, f"登录失败: {r.text[:200]}"
    return r.json()["data"]["token"]


@pytest.fixture
def c_user(client):
    u = _add_user(client._sesh, f"appuser_{uuid.uuid4().hex[:6]}")
    return u, _login_token(client, u.username)


@pytest.fixture
def station_and_device(client):
    st = Station(
        name="清理豁免测试站",
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


def _create_body(st, dev, connector_id=1):
    return {
        "station_id": st.id,
        "device_id": dev.id,
        "connector_id": connector_id,
        "user_type": "app",
    }


class TestConnectorBusyTimeoutExemption:
    def test_stale_pending_other_user_freed(self, client, c_user, station_and_device):
        """加分项3: 他人超时 pending 僵尸单占桩 → 自动清理后放行 201。"""
        u, token = c_user
        st, dev = station_and_device
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh, order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
            user_id=other.id, station_id=st.id, device_id=dev.id, connector_id=1,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201, r.text
        assert r.json()["code"] == 0

    def test_fresh_pending_other_user_still_busy(self, client, c_user, station_and_device):
        """新鲜 pending 占桩 (未超时) → 仍 CONNECTOR_BUSY。"""
        _, token = c_user
        st, dev = station_and_device
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh, order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
            user_id=other.id, station_id=st.id, device_id=dev.id, connector_id=1,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=3),
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CONNECTOR_BUSY"

    def test_charging_other_user_still_busy(self, client, c_user, station_and_device):
        """charging 占桩 (真实充电中) → 绝不清理, 仍 CONNECTOR_BUSY。"""
        _, token = c_user
        st, dev = station_and_device
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh, order_no=f"TL{uuid.uuid4().hex[:14].upper()}",
            user_id=other.id, station_id=st.id, device_id=dev.id, connector_id=1,
            status=OrderStatus.CHARGING,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=60),
        )
        r = client.post(f"{BASE}", json=_create_body(st, dev, 1),
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "CONNECTOR_BUSY"


# ═══════════════════════════════════════════════════════════════
# 卡 e18ce31e: cleanup 三路径 pending→cancelled 撤销 RemoteStop (best-effort)
# ═══════════════════════════════════════════════════════════════

def _stub_remote_stop(monkeypatch):
    """探针: 记录 OCPPAdapter.remote_stop_transaction 调用, 返回 calls 列表。"""
    import app.services.ocpp_dispatch as od

    calls = []

    async def fake_stop(self, transaction_id):
        calls.append(("remote_stop", transaction_id))
        return True

    monkeypatch.setattr(od.OCPPAdapter, "remote_stop_transaction", fake_stop)
    return calls


class TestCleanupRemoteStop:
    """cleanup 三函数 pending→cancelled 时 best-effort 下发 RemoteStop。

    开关 true → 每条取消路径下发一次 (曾 RemoteStart 的 pending 必撤销);
    开关 false → 零调用 (与现状一致, 零回归)。
    """

    def _stale(self, db, *, user_id=100, device_id=1, connector_id=1, order_no=None):
        old = datetime.now(timezone.utc) - timedelta(minutes=15)
        return _seed_order(
            db, order_no=order_no or f"CL{uuid.uuid4().hex[:8].upper()}",
            user_id=user_id, station_id=1, device_id=device_id,
            connector_id=connector_id, created_at=old,
        )

    def test_stale_batch_dispatches_remotestop(self, test_db, monkeypatch):
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        calls = _stub_remote_stop(monkeypatch)
        db = test_db["session"]
        o = self._stale(db)
        from app.services.order_cleanup_service import cleanup_stale_pending_orders

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)
        assert result["cancelled"] >= 1
        assert ("remote_stop", o.id) in calls

    def test_for_user_dispatches_remotestop(self, test_db, monkeypatch):
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        calls = _stub_remote_stop(monkeypatch)
        db = test_db["session"]
        o = self._stale(db, user_id=200)
        from app.services.order_cleanup_service import cancel_stale_pending_for_user

        n = cancel_stale_pending_for_user(db, user_id=200, timeout_minutes=10)
        assert n >= 1
        assert ("remote_stop", o.id) in calls

    def test_for_connector_dispatches_remotestop(self, test_db, monkeypatch):
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        calls = _stub_remote_stop(monkeypatch)
        db = test_db["session"]
        o = self._stale(db, device_id=7, connector_id=3)
        from app.services.order_cleanup_service import (
            cancel_stale_pending_for_connector,
        )

        n = cancel_stale_pending_for_connector(
            db, device_id=7, connector_id=3, timeout_minutes=10
        )
        assert n >= 1
        assert ("remote_stop", o.id) in calls

    def test_disabled_no_dispatch(self, test_db, monkeypatch):
        monkeypatch.delenv("OCPP_REMOTE_DISPATCH_ENABLED", raising=False)
        calls = _stub_remote_stop(monkeypatch)
        db = test_db["session"]
        self._stale(db)
        from app.services.order_cleanup_service import cleanup_stale_pending_orders

        cleanup_stale_pending_orders(db, timeout_minutes=10)
        assert calls == []
