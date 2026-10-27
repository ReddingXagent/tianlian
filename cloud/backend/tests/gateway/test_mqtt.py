"""
MQTT 3.1.1 适配器单元测试。

覆盖：
    - TLS 配置 / 端口自动切换
    - connect/disconnect 生命周期 + 回调
    - subscribe_device
    - read_data/read_telemetry、write_command/send_control
    - parse_fault_message / _parse_fault_level
    - on_disconnect 触发重连
    - get_tls_info / get_reconnect_status
"""
from datetime import timezone

import pytest

from app.gateway.mqtt import MQTTAdapter


@pytest.fixture
def adapter():
    return MQTTAdapter(broker="mqtt.test", client_id="gw-test-001")


@pytest.fixture
def callbacks():
    """记录回调调用次数。"""
    state = {"connect": 0, "disconnect": 0, "message": None}

    async def on_connect():
        state["connect"] += 1

    async def on_disconnect():
        state["disconnect"] += 1

    return state, on_connect, on_disconnect


# ========== TLS / 端口 ==========

def test_default_port_plain():
    a = MQTTAdapter(broker="h")
    assert a.port == 1883
    assert a.tls_enabled is False


def test_tls_switches_port_to_8883():
    a = MQTTAdapter(broker="h", tls_enabled=True)
    assert a.port == 8883
    assert a.tls_enabled is True


def test_tls_keeps_custom_port():
    a = MQTTAdapter(broker="h", tls_enabled=True, port=8884)
    assert a.port == 8884


def test_get_tls_info(adapter):
    info = adapter.get_tls_info()
    assert info["enabled"] is False
    assert info["broker"] == "mqtt.test"
    assert info["port"] == 1883


def test_get_tls_info_enabled():
    a = MQTTAdapter(broker="h", tls_enabled=True, tls_client_cert="/x.pem", tls_ca_cert="/ca.pem")
    info = a.get_tls_info()
    assert info["enabled"] is True
    assert info["client_cert"] is True
    assert info["ca_cert"] is True


# ========== 生命周期 ==========

@pytest.mark.asyncio
async def test_initialize_plain(adapter):
    assert await adapter.initialize() is True
    assert adapter.initialized is True


@pytest.mark.asyncio
async def test_connect_invokes_callback(callbacks):
    state, on_connect, on_disconnect = callbacks
    a = MQTTAdapter(broker="h", on_connect_callback=on_connect)
    assert await a.connect() is True
    assert a.connected is True
    assert a._reconnect_count == 0
    assert state["connect"] == 1


@pytest.mark.asyncio
async def test_connect_callback_exception_swallowed():
    """连接回调抛异常不应影响 connect 返回。"""
    async def boom():
        raise ValueError("boom")

    a = MQTTAdapter(broker="h", on_connect_callback=boom)
    assert await a.connect() is True


@pytest.mark.asyncio
async def test_disconnect_invokes_callback(callbacks):
    state, on_connect, on_disconnect = callbacks
    a = MQTTAdapter(broker="h", on_disconnect_callback=on_disconnect)
    await a.connect()
    await a.disconnect()
    assert a.connected is False
    assert state["disconnect"] == 1


@pytest.mark.asyncio
async def test_disconnect_callback_exception_swallowed():
    async def boom():
        raise ValueError("boom")

    a = MQTTAdapter(broker="h", on_disconnect_callback=boom)
    await a.connect()
    assert await a.disconnect() is True


# ========== 订阅 / 读写 ==========

@pytest.mark.asyncio
async def test_subscribe_device(adapter):
    assert await adapter.subscribe_device("TCU001") is True
    assert "tcu/TCU001/report" in adapter._subscriptions


@pytest.mark.asyncio
async def test_read_data(adapter):
    data = await adapter.read_data(1)
    assert data["tcu_address"] == "TCU001"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_read_telemetry_utc_aware(adapter):
    data = await adapter.read_telemetry("TCU001")
    assert data["timestamp"].tzinfo is not None


@pytest.mark.asyncio
async def test_write_command(adapter):
    assert await adapter.write_command(1, {"cmd": "on"}) is True


@pytest.mark.asyncio
async def test_send_control(adapter):
    assert await adapter.send_control("TCU001", {"cmd": "on"}) is True


# ========== 故障解析 ==========

def test_parse_fault_message(adapter):
    msg = {
        "message_type": 0x122006,
        "tcu_address": "TCU001",
        "sequence_no": 7,
        "fault_level": 0x01,
        "fault_code": 0x00AB,
        "fault_detail": ["over-temp"],
        "timestamp": "2026-08-06T00:00:00Z",
    }
    info = adapter.parse_fault_message(msg)
    assert info["message_type"] == 0x122006
    assert info["tcu_address"] == "TCU001"
    assert info["fault_level"] == "emergency"
    assert info["fault_code"] == "0x00AB"
    assert info["fault_detail"] == ["over-temp"]


def test_parse_fault_level_mapping(adapter):
    assert adapter._parse_fault_level(0x01) == "emergency"
    assert adapter._parse_fault_level(0x02) == "serious"
    assert adapter._parse_fault_level(0x03) == "warning_serious"
    assert adapter._parse_fault_level(0x04) == "warning_general"
    assert adapter._parse_fault_level(0xFF) == "unknown"


def test_parse_fault_code_returns_none(adapter):
    assert adapter.parse_fault_code(b"\x01") is None


# ========== 重连 ==========

def test_get_reconnect_status_default(adapter):
    status = adapter.get_reconnect_status()
    assert status["enabled"] is True
    assert status["reconnecting"] is False
    assert status["attempts"] == 0
    assert status["max_attempts"] == 10


@pytest.mark.asyncio
async def test_reconnect_loop_gives_up_after_max_attempts(monkeypatch):
    """connect 持续失败时，重连 max_attempts 次后放弃（count 不被 connect 归零）。"""
    a = MQTTAdapter(
        broker="h",
        reconnect_enabled=True,
        reconnect_max_attempts=1,
        reconnect_base_delay=0.01,
    )

    async def fail_connect():
        raise ConnectionError("模拟连接失败")

    monkeypatch.setattr(a, "connect", fail_connect)
    await a._reconnect_loop()
    # 失败 1 次（== max_attempts）后退出，connect 未成功所以 count 未被归零
    assert a._reconnect_count == 1
    assert a.connected is False


@pytest.mark.asyncio
async def test_on_disconnect_triggers_reconnect():
    """on_disconnect 在启用重连时应启动重连任务。"""
    a = MQTTAdapter(
        broker="h",
        reconnect_enabled=True,
        reconnect_max_attempts=1,
        reconnect_base_delay=0.5,  # 拉长，避免循环真正执行 connect
    )
    await a.on_disconnect()
    assert a._reconnecting is True
    assert a._reconnect_task is not None
    # 清理
    a._cancel_reconnect()


@pytest.mark.asyncio
async def test_on_disconnect_disabled_reconnect():
    a = MQTTAdapter(broker="h", reconnect_enabled=False)
    await a.on_disconnect()
    assert a._reconnecting is False
    assert a._reconnect_task is None
