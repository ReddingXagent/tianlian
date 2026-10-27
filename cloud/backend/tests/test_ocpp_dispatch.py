"""ocpp_dispatch 单元测试 (卡 77ca88d8)

覆盖:
1. _dispatch_timeout env 三态 (合法/非法/缺省回落 10.0)
2. remote_stop 桩ID语义: charge_point_id = 订单所属设备 sn (拿不到 device 兜底 ORDER{id})
3. remote_start/remote_stop 均使用 _dispatch_timeout 的值
4. dispatch_enabled 开关行为锁
"""
import asyncio
from types import SimpleNamespace

import pytest

import app.services.ocpp_dispatch as od
from app.services.ocpp_dispatch import DispatchResult, _dispatch_timeout, dispatch_enabled


# ─── 1. timeout env 三态 ───


class TestDispatchTimeout:
    def test_env_valid(self, monkeypatch):
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "3.5")
        assert _dispatch_timeout() == 3.5

    def test_env_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "abc")
        assert _dispatch_timeout() == 10.0

    def test_env_nonpositive_falls_back(self, monkeypatch):
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "0")
        assert _dispatch_timeout() == 10.0
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "-2")
        assert _dispatch_timeout() == 10.0

    def test_env_absent_default(self, monkeypatch):
        monkeypatch.delenv("OCPP_DISPATCH_TIMEOUT_SEC", raising=False)
        assert _dispatch_timeout() == 10.0


# ─── 2/3. remote_stop 桩ID语义 + timeout 接线 (探针适配器) ───


@pytest.fixture
def probe(monkeypatch):
    """替换 OCPPAdapter: 记录构造参数与方法调用, 返回 (记录, 结果注入器)。"""
    calls = []

    def make(result=True):
        async def fake_start(self, id_tag, connector_id=1):
            calls.append(("remote_start", self.charge_point_id, id_tag, connector_id))
            return result

        async def fake_stop(self, transaction_id):
            calls.append(("remote_stop", self.charge_point_id, transaction_id))
            return result

        monkeypatch.setattr(od.OCPPAdapter, "remote_start_transaction", fake_start)
        monkeypatch.setattr(od.OCPPAdapter, "remote_stop_transaction", fake_stop)

    return calls, make


class _FakeDevice:
    def __init__(self, id=1, sn="SN123"):
        self.id = id
        self.sn = sn


class TestRemoteStopChargePointId:
    def test_uses_device_sn_via_session(self, probe, client):
        """挂 session 的订单 → charge_point_id = device.sn。"""
        calls, make = probe
        make(True)
        from tests.api.test_business_orders import _seed_device, _seed_order, _seed_station

        st = _seed_station(client._sesh)
        dev = _seed_device(client._sesh, station_id=st.id)
        assert dev.sn  # seed 保证有 sn
        from datetime import datetime, timezone

        from app.models.charging_order import OrderStatus

        o = _seed_order(
            client._sesh,
            user_id=1,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
        )
        # 会话内对象 → object_session 可解析
        client._sesh.add(o)
        client._sesh.commit()

        assert od.remote_stop(o) == DispatchResult.ACCEPTED
        assert calls == [("remote_stop", dev.sn, o.id)]

    def test_falls_back_to_order_id_without_session(self, probe, caplog):
        """无 DB 会话/无 device → 兜底 ORDER{id} + 警告日志。"""
        calls, make = probe
        make(True)
        o = SimpleNamespace(id=99, device_id=None)
        with caplog.at_level("WARNING"):
            assert od.remote_stop(o) == DispatchResult.ACCEPTED
        assert calls == [("remote_stop", "ORDER99", 99)]
        assert any("ORDER99" in r.message for r in caplog.records)


class TestTimeoutWiring:
    def test_remote_start_uses_env_timeout(self, probe, monkeypatch):
        """env=0.05 + 挂起协程 → TIMEOUT, 证明 remote_start 走 _dispatch_timeout。"""
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "0.05")

        async def hang(self, id_tag, connector_id=1):
            await asyncio.sleep(30)

        monkeypatch.setattr(od.OCPPAdapter, "remote_start_transaction", hang)
        dev = _FakeDevice()
        assert od.remote_start(dev, 1, "tag") == DispatchResult.TIMEOUT

    def test_remote_stop_uses_env_timeout(self, probe, monkeypatch):
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "0.05")

        async def hang(self, transaction_id):
            await asyncio.sleep(30)

        monkeypatch.setattr(od.OCPPAdapter, "remote_stop_transaction", hang)
        o = SimpleNamespace(id=99, device_id=None)
        assert od.remote_stop(o) == DispatchResult.TIMEOUT


# ─── 4. dispatch_enabled 开关行为锁 ───


class TestDispatchEnabled:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1", True), ("true", True), ("True", True), ("yes", True),
            ("0", False), ("false", False), ("False", False), ("", False),
        ],
    )
    def test_env_values(self, monkeypatch, raw, expected):
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", raw)
        assert dispatch_enabled() is expected

    def test_absent_uses_settings_default_false(self, monkeypatch):
        monkeypatch.delenv("OCPP_REMOTE_DISPATCH_ENABLED", raising=False)
        from app.core.config import get_settings

        assert dispatch_enabled() is bool(get_settings().OCPP_REMOTE_DISPATCH_ENABLED)


# ─── 5. remote_stop_best_effort (卡 e18ce31e: pending→cancelled 撤销 RemoteStart) ───


class TestRemoteStopBestEffort:
    """best-effort 撤销: 开关 false no-op / 开关 true 下发一次 / 失败仅日志不抛。

    调用方 (cancel_order / order_cleanup) 在 pending→cancelled 时调用, 不应关心下发
    成败 —— 失败/超时/异常由本函数吞掉 + warning, 绝不向上传播、绝不阻塞取消。
    """

    def test_disabled_is_noop_adapter_never_touched(self, probe, monkeypatch):
        """开关 false → 不构造 adapter / 不走 asyncio, 零调用, 直接返回 None。"""
        calls, make = probe
        make(True)
        monkeypatch.delenv("OCPP_REMOTE_DISPATCH_ENABLED", raising=False)
        o = SimpleNamespace(id=99, order_no="TL99", device_id=None)
        assert od.remote_stop_best_effort(o) is None
        assert calls == []

    def test_enabled_dispatches_once(self, probe, monkeypatch):
        """开关 true + adapter accepted → 下发一次, 返回 None (best-effort 无返回值)。"""
        calls, make = probe
        make(True)
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        o = SimpleNamespace(id=99, order_no="TL99", device_id=None)
        assert od.remote_stop_best_effort(o) is None
        stops = [c for c in calls if c[0] == "remote_stop"]
        assert len(stops) == 1
        assert stops[0][2] == 99  # transaction_id = order.id

    def test_exception_does_not_raise(self, monkeypatch, caplog):
        """adapter 抛异常 → best-effort 吞掉, 返回 None, warning 含订单号与原因。"""
        async def boom(self, transaction_id):
            raise RuntimeError("network down")

        monkeypatch.setattr(od.OCPPAdapter, "remote_stop_transaction", boom)
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        o = SimpleNamespace(id=99, order_no="TLBOOM", device_id=None)
        with caplog.at_level("WARNING"):
            assert od.remote_stop_best_effort(o) is None
        assert any(
            "TLBOOM" in r.message and "network down" in r.message for r in caplog.records
        ), [r.message for r in caplog.records]

    def test_timeout_logs_warning_no_raise(self, monkeypatch, caplog):
        """超时 → 转为 warning 含订单号, 不抛 (调用方取消流程不受影响)。"""
        monkeypatch.setenv("OCPP_REMOTE_DISPATCH_ENABLED", "1")
        monkeypatch.setenv("OCPP_DISPATCH_TIMEOUT_SEC", "0.05")

        async def hang(self, transaction_id):
            await asyncio.sleep(30)

        monkeypatch.setattr(od.OCPPAdapter, "remote_stop_transaction", hang)
        o = SimpleNamespace(id=99, order_no="TLTO", device_id=None)
        with caplog.at_level("WARNING"):
            assert od.remote_stop_best_effort(o) is None
        assert any("TLTO" in r.message for r in caplog.records)
