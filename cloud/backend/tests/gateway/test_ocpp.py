"""
OCPP 1.6J 适配器单元测试。

覆盖：
    - 连接/断开/关闭生命周期
    - BootNotification / Heartbeat / Authorize / StatusNotification / DataTransfer
    - StartTransaction / StopTransaction 全流程
    - MeterValues（含 None/空值边界）
    - 远程控制（remote_start/stop/reset/change_availability）
    - read_data / write_command / health_check / get_ocpp_info
    - 缺陷 1/2/3 回归保护（标注 @pytest.mark）
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.gateway.ocpp import (
    OCPPAdapter,
    OCPPAction,
    OCPPMessageType,
    ChargePointStatus,
    RegistrationStatus,
)


# ========== fixtures ==========

@pytest.fixture
def adapter():
    """默认 OCPP 适配器（关闭重连、心跳拉长避免干扰测试）。"""
    return OCPPAdapter(
        endpoint="wss://ocpp.test/ocpp",
        charge_point_id="CP-TEST-001",
        heartbeat_interval=3600,
        reconnect_enabled=False,
    )


# ========== 常量 ==========

def test_message_type_constants():
    assert OCPPMessageType.CALL == 2
    assert OCPPMessageType.CALL_RESULT == 3
    assert OCPPMessageType.CALL_ERROR == 4


def test_action_constants():
    assert OCPPAction.START_TRANSACTION == "StartTransaction"
    assert OCPPAction.STOP_TRANSACTION == "StopTransaction"
    assert OCPPAction.BOOT_NOTIFICATION == "BootNotification"


def test_status_constants():
    assert ChargePointStatus.AVAILABLE == "Available"
    assert ChargePointStatus.CHARGING == "Charging"
    assert RegistrationStatus.ACCEPTED == "Accepted"
    assert RegistrationStatus.REJECTED == "Rejected"


# ========== 生命周期 ==========

@pytest.mark.asyncio
async def test_initialize(adapter):
    assert await adapter.initialize() is True
    assert adapter.initialized is True


@pytest.mark.asyncio
async def test_connect_registers_and_starts_heartbeat(adapter):
    assert await adapter.connect() is True
    assert adapter.connected is True
    # BootNotification 被 Accepted → 注册成功
    assert adapter.is_registered() is True
    # 心跳任务应已创建
    assert adapter._heartbeat_task is not None
    # 清理
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_clears_state(adapter):
    await adapter.connect()
    await adapter.disconnect()
    assert adapter.connected is False
    assert adapter.is_registered() is False
    assert adapter._heartbeat_task is None
    # pending_calls 清空
    assert adapter._pending_calls == {}


@pytest.mark.asyncio
async def test_disconnect_cancels_pending_calls(adapter):
    import asyncio
    fut = asyncio.get_event_loop().create_future()
    adapter._pending_calls["msg-1"] = fut
    await adapter.disconnect()
    assert fut.cancelled() or fut.done()
    assert adapter._pending_calls == {}


@pytest.mark.asyncio
async def test_shutdown_when_connected(adapter):
    await adapter.connect()
    assert await adapter.shutdown() is True
    assert adapter.connected is False
    assert adapter.initialized is False


@pytest.mark.asyncio
async def test_shutdown_when_not_connected(adapter):
    # 未连接直接 shutdown 不应报错
    assert await adapter.shutdown() is True
    assert adapter.initialized is False


# ========== BootNotification / Heartbeat / Authorize ==========

@pytest.mark.asyncio
async def test_send_boot_notification(adapter):
    resp = await adapter.send_boot_notification(
        charge_point_model="DC-120kW",
        charge_point_vendor="VendorX",
        firmware_version="2.0.0",
    )
    assert resp["status"] == RegistrationStatus.ACCEPTED
    assert resp["interval"] == adapter.heartbeat_interval
    assert "currentTime" in resp
    # boot payload 被记录
    assert adapter._last_boot_notification is not None
    assert adapter._last_boot_notification["chargePointModel"] == "DC-120kW"
    assert adapter._last_boot_notification["chargePointSerialNumber"] == "CP-TEST-001"
    assert adapter._last_boot_notification["firmwareVersion"] == "2.0.0"


@pytest.mark.asyncio
async def test_send_heartbeat(adapter):
    resp = await adapter.send_heartbeat()
    assert "currentTime" in resp


@pytest.mark.asyncio
async def test_send_authorize(adapter):
    resp = await adapter.send_authorize("RFID-0001")
    assert resp["idTagInfo"]["status"] == "Accepted"
    assert "expiryDate" in resp["idTagInfo"]


# ========== StartTransaction ==========

@pytest.mark.asyncio
async def test_start_transaction_sets_transaction_id(adapter):
    resp = await adapter.start_transaction(
        connector_id=1, id_tag="USER001", meter_start=100
    )
    assert resp["idTagInfo"]["status"] == "Accepted"
    assert resp["transactionId"] == 10001
    assert adapter.get_transaction_id() == 10001


@pytest.mark.asyncio
async def test_start_transaction_with_reservation(adapter):
    resp = await adapter.start_transaction(
        connector_id=1, id_tag="USER001", meter_start=0, reservation_id=555
    )
    assert resp["transactionId"] == 10001


# ========== StopTransaction：正常流程 ==========

@pytest.mark.asyncio
async def test_stop_transaction_normal_flow(adapter):
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=100)
    resp = await adapter.stop_transaction(
        transaction_id=10001, meter_stop=500, reason="Local"
    )
    assert resp["idTagInfo"]["status"] == "Accepted"
    # 正常结束后活跃交易清空
    assert adapter.get_transaction_id() is None


# ========== 缺陷 2：transaction_id 匹配 + meter_stop 合理性校验 ==========

@pytest.mark.asyncio
async def test_stop_transaction_mismatched_id_rejected(adapter):
    """缺陷2: transaction_id 与活跃交易不匹配应 Rejected（原实现静默 Accepted）。"""
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=0)
    resp = await adapter.stop_transaction(transaction_id=99999, meter_stop=10)
    assert resp["idTagInfo"]["status"] == "Rejected"
    # 拒绝时不应清空活跃交易（交易仍有效）
    assert adapter.get_transaction_id() == 10001
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_stop_transaction_no_active_transaction_rejected(adapter):
    """缺陷2: 无活跃交易时 stop 应 Rejected。"""
    resp = await adapter.stop_transaction(transaction_id=10001, meter_stop=10)
    assert resp["idTagInfo"]["status"] == "Rejected"


@pytest.mark.asyncio
async def test_stop_transaction_negative_meter_stop_rejected(adapter):
    """缺陷2: meter_stop 负值不合理应 Rejected。"""
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=0)
    resp = await adapter.stop_transaction(transaction_id=10001, meter_stop=-5)
    assert resp["idTagInfo"]["status"] == "Rejected"
    assert adapter.get_transaction_id() == 10001
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_stop_transaction_meter_stop_below_start_rejected(adapter):
    """缺陷2: meter_stop 小于 meter_start（表读数倒退）应 Rejected。"""
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=1000)
    resp = await adapter.stop_transaction(transaction_id=10001, meter_stop=500)
    assert resp["idTagInfo"]["status"] == "Rejected"
    assert adapter.get_transaction_id() == 10001
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_stop_transaction_meter_stop_equal_start_accepted(adapter):
    """边界: meter_stop == meter_start（零电量）应 Accepted。"""
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=1000)
    resp = await adapter.stop_transaction(transaction_id=10001, meter_stop=1000)
    assert resp["idTagInfo"]["status"] == "Accepted"
    assert adapter.get_transaction_id() is None


# ========== 缺陷 1：StopTransaction 时间戳必须 UTC aware ==========

@pytest.mark.asyncio
async def test_stop_transaction_timestamp_is_utc_aware(adapter):
    """缺陷1: 交易结束时间戳用于计费对账，必须带时区（aware），不能 naive。"""
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=0)
    resp = await adapter.stop_transaction(transaction_id=10001, meter_stop=100)
    # 返回值必须暴露时间戳供对账
    assert "timestamp" in resp, "StopTransaction 响应应包含 timestamp 供计费对账"
    parsed = datetime.fromisoformat(resp["timestamp"])
    assert parsed.tzinfo is not None, "时间戳 naive，计费对账时区错乱"


# ========== 缺陷 3：MeterValues None/空值防护 ==========

@pytest.mark.asyncio
async def test_send_meter_values_none_does_not_crash(adapter):
    """缺陷3: values=None 原实现 len(None) → TypeError。"""
    resp = await adapter.send_meter_values(
        connector_id=1, transaction_id=10001, values=None
    )
    assert resp["status"] == "Rejected"


@pytest.mark.asyncio
async def test_send_meter_values_empty_list_does_not_crash(adapter):
    """缺陷3: values=[] 空列表防护。"""
    resp = await adapter.send_meter_values(
        connector_id=1, transaction_id=10001, values=[]
    )
    assert resp["status"] == "Rejected"


@pytest.mark.asyncio
async def test_send_meter_values_normal(adapter):
    resp = await adapter.send_meter_values(
        connector_id=1,
        transaction_id=10001,
        values=[{"timestamp": "2026-08-06T00:00:00Z", "sampledValue": [{"value": "400"}]}],
    )
    assert resp == {}


# ========== StatusNotification / DataTransfer ==========

@pytest.mark.asyncio
async def test_send_status_notification(adapter):
    resp = await adapter.send_status_notification(
        connector_id=1, status=ChargePointStatus.CHARGING, error_code="NoError"
    )
    assert resp == {}


@pytest.mark.asyncio
async def test_send_data_transfer_minimal(adapter):
    resp = await adapter.send_data_transfer(vendor_id="Tianlian")
    assert resp["status"] == "Accepted"


@pytest.mark.asyncio
async def test_send_data_transfer_full(adapter):
    resp = await adapter.send_data_transfer(
        vendor_id="Tianlian", message_id="msg-1", data={"k": "v"}
    )
    assert resp["status"] == "Accepted"


# ========== 远程控制 ==========

@pytest.mark.asyncio
async def test_remote_start_transaction(adapter):
    assert await adapter.remote_start_transaction("USER001", connector_id=1) is True


@pytest.mark.asyncio
async def test_remote_stop_transaction(adapter):
    await adapter.start_transaction(connector_id=1, id_tag="USER001")
    assert await adapter.remote_stop_transaction(10001) is True
    assert adapter.get_transaction_id() is None


@pytest.mark.asyncio
async def test_reset(adapter):
    assert await adapter.reset("Hard") is True


@pytest.mark.asyncio
async def test_change_availability(adapter):
    assert await adapter.change_availability(1, "Operative") is True


# ========== read_data / write_command ==========

@pytest.mark.asyncio
async def test_read_data_idle(adapter):
    data = await adapter.read_data(1)
    assert data["connector_id"] == 1
    assert data["status"] == ChargePointStatus.AVAILABLE
    assert data["transaction_id"] is None
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_read_data_charging(adapter):
    await adapter.start_transaction(connector_id=1, id_tag="USER001")
    data = await adapter.read_data(1)
    assert data["status"] == ChargePointStatus.CHARGING
    assert data["transaction_id"] == 10001


@pytest.mark.asyncio
async def test_write_command_remote_start(adapter):
    ok = await adapter.write_command(
        1, {"action": "remote_start", "id_tag": "USER001"}
    )
    assert ok is True


@pytest.mark.asyncio
async def test_write_command_remote_stop(adapter):
    ok = await adapter.write_command(
        1, {"action": "remote_stop", "transaction_id": 10001}
    )
    assert ok is True


@pytest.mark.asyncio
async def test_write_command_reset(adapter):
    ok = await adapter.write_command(1, {"action": "reset", "reset_type": "Soft"})
    assert ok is True


@pytest.mark.asyncio
async def test_write_command_change_availability(adapter):
    ok = await adapter.write_command(
        1, {"action": "change_availability", "availability": "Operative"}
    )
    assert ok is True


@pytest.mark.asyncio
async def test_write_command_unknown_action(adapter):
    ok = await adapter.write_command(1, {"action": "noop"})
    assert ok is False


def test_parse_fault_code_returns_none(adapter):
    assert adapter.parse_fault_code(b"\x01\x02") is None


# ========== 状态查询 ==========

@pytest.mark.asyncio
async def test_health_check_disconnected(adapter):
    health = await adapter.health_check()
    assert health["protocol"] == "ocpp"
    assert health["registered"] is False
    assert health["transaction_active"] is False
    assert health["heartbeat_interval"] == 3600


@pytest.mark.asyncio
async def test_health_check_charging(adapter):
    await adapter.connect()
    await adapter.start_transaction(connector_id=1, id_tag="USER001")
    health = await adapter.health_check()
    assert health["registered"] is True
    assert health["transaction_active"] is True
    await adapter.disconnect()


def test_get_ocpp_info(adapter):
    info = adapter.get_ocpp_info()
    assert info["charge_point_id"] == "CP-TEST-001"
    assert info["protocol"] == "ocpp"
    assert info["version"] == "1.6-J"
    assert info["registered"] is False
    assert info["transaction_active"] is False


# ========== 入网状态钩子（任务卡 1256e7fa）==========

@pytest.mark.asyncio
async def test_connect_invokes_mark_device_online(adapter):
    """connect() BootNotification ACCEPTED 后应调用 mark_device_online。"""
    from app.gateway import ocpp as ocpp_mod
    with patch.object(ocpp_mod, "mark_device_online", return_value=True) as mocked:
        await adapter.connect()
        mocked.assert_called_once_with("CP-TEST-001")
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_connect_tolerates_provision_hook_failure(adapter):
    """入网登记抛错也不影响 connect 返回 True（网关通信不得被登记阻断）。"""
    from app.gateway import ocpp as ocpp_mod
    with patch.object(ocpp_mod, "mark_device_online", side_effect=RuntimeError("db down")):
        result = await adapter.connect()
    assert result is True
    assert adapter.is_registered() is True
    await adapter.disconnect()


def test_mark_device_online_empty_id_safe():
    """空 charge_point_id 直接返回 False，不触 DB。"""
    from app.gateway.ocpp import mark_device_online
    assert mark_device_online("") is False
    assert mark_device_online(None) is False


def test_mark_device_online_unknown_device_no_op(monkeypatch):
    """未匹配到设备 → 返回 False，不抛、不写。"""
    from app.gateway import ocpp as ocpp_mod

    class _FakeQ:
        def __init__(self, *a, **kw):
            pass

        def filter(self, *a, **kw):
            return self

        def first(self):
            return None

    class _FakeSession:
        def query(self, *_a, **_kw):
            return _FakeQ()

        def commit(self):
            raise AssertionError("未匹配设备不应 commit")

        def close(self):
            pass

    monkeypatch.setattr(ocpp_mod, "SessionLocal", lambda: _FakeSession(), raising=False)
    # SessionLocal 在 mark_device_online 内部 import 时读取，patch 模块属性即可
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", lambda: _FakeSession())
    assert ocpp_mod.mark_device_online("UNKNOWN-CP") is False


def test_mark_device_online_promotes_provisioning(monkeypatch):
    """PROVISIONING 设备首次连接 → 置 ONLINE；已 ONLINE 幂等不写。"""
    from app.gateway import ocpp as ocpp_mod
    from app.models.device import Device, DeviceType, DeviceStatus, ProvisionStatus

    calls = {"committed": 0}

    class _FakeDevice:
        def __init__(self, status):
            self.provision_status = status

    class _FakeQ:
        def __init__(self, found):
            self._found = found

        def filter(self, *a, **kw):
            return self

        def first(self):
            return self._found

    class _FakeSession:
        def __init__(self, found):
            self._q = _FakeQ(found)

        def query(self, *_a, **_kw):
            return self._q

        def commit(self):
            calls["committed"] += 1

        def close(self):
            pass

    # PROVISIONING → 应 commit 一次
    sess = _FakeSession(_FakeDevice(ProvisionStatus.PROVISIONING))
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess)
    assert ocpp_mod.mark_device_online("CP-1") is True
    assert sess._q._found.provision_status == ProvisionStatus.ONLINE
    assert calls["committed"] == 1

    # ONLINE → 幂等，不 commit
    sess2 = _FakeSession(_FakeDevice(ProvisionStatus.ONLINE))
    monkeypatch.setattr(db_mod, "SessionLocal", lambda: sess2)
    assert ocpp_mod.mark_device_online("CP-1") is True
    assert calls["committed"] == 1
