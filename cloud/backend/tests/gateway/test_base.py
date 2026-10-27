"""
设备适配器基类（DeviceAdapter / TelemetryPoint）单元测试。

覆盖：
    - TelemetryPoint.parse（无符号/有符号/scale/register_count）
    - register_telemetry_points / get_telemetry_point / parse_telemetry_value
    - DeviceAdapter 默认生命周期（initialize/shutdown/reset）
    - is_connected / is_initialized
    - health_check 默认实现
"""
from datetime import datetime

import pytest

from app.gateway.base import DeviceAdapter, PointType, TelemetryPoint


# ========== TelemetryPoint.parse ==========

def test_parse_unsigned_with_scale():
    point = TelemetryPoint(name="v", address=0, point_type=PointType.VOLTAGE,
                           scale=0.1, unit="V")
    assert point.parse(2205) == pytest.approx(220.5)


def test_parse_default_scale_1():
    point = TelemetryPoint(name="c", address=0)
    assert point.parse(42) == 42


def test_parse_signed_negative_16bit():
    # 16 位有符号：0xFFFF 应解析为 -1
    point = TelemetryPoint(name="p", address=0, scale=1.0, is_signed=True, register_count=1)
    assert point.parse(0xFFFF) == pytest.approx(-1.0)


def test_parse_signed_negative_value():
    # 0xFF9C = 65436 → 减 65536 = -100
    point = TelemetryPoint(name="temp", address=0, scale=0.1, is_signed=True, register_count=1)
    assert point.parse(0xFF9C) == pytest.approx(-10.0)


def test_parse_signed_positive_within_range():
    point = TelemetryPoint(name="x", address=0, scale=1.0, is_signed=True, register_count=1)
    assert point.parse(100) == 100


# ========== DeviceAdapter 遥测点管理 ==========

class _ConcreteAdapter(DeviceAdapter):
    protocol_type = "concrete"

    async def connect(self):
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False
        return True

    async def read_data(self, device_address):
        return {}

    async def write_command(self, device_address, command):
        return True

    def parse_fault_code(self, raw_data):
        return None


@pytest.fixture
def adapter():
    return _ConcreteAdapter()


def test_register_and_get_telemetry_point(adapter):
    points = [
        TelemetryPoint("voltage", 0, PointType.VOLTAGE, 0.1, "V"),
        TelemetryPoint("power", 10, PointType.POWER, 0.1, "kW"),
    ]
    adapter.register_telemetry_points(points)
    assert adapter.get_telemetry_point("voltage") is not None
    assert adapter.get_telemetry_point("power").unit == "kW"
    assert len(adapter.telemetry_points) == 2


def test_get_telemetry_point_unknown(adapter):
    assert adapter.get_telemetry_point("nope") is None


def test_parse_telemetry_value(adapter):
    adapter.register_telemetry_points([
        TelemetryPoint("voltage", 0, PointType.VOLTAGE, 0.1, "V"),
    ])
    assert adapter.parse_telemetry_value("voltage", 2205) == pytest.approx(220.5)


def test_parse_telemetry_value_unknown_point(adapter):
    assert adapter.parse_telemetry_value("missing", 100) is None


# ========== 生命周期 ==========

@pytest.mark.asyncio
async def test_default_initialize(adapter):
    assert await adapter.initialize() is True
    assert adapter.is_initialized() is True


@pytest.mark.asyncio
async def test_default_shutdown_when_connected(adapter):
    await adapter.connect()
    assert await adapter.shutdown() is True
    assert adapter.is_connected() is False
    assert adapter.is_initialized() is False
    assert adapter.telemetry_points == {}


@pytest.mark.asyncio
async def test_default_shutdown_when_not_connected(adapter):
    assert await adapter.shutdown() is True


@pytest.mark.asyncio
async def test_default_reset(adapter):
    await adapter.connect()
    ok = await adapter.reset()
    assert ok is True
    assert adapter.is_connected() is True  # reset 后重连


# ========== health_check ==========

@pytest.mark.asyncio
async def test_health_check_disconnected(adapter):
    health = await adapter.health_check()
    assert health["protocol"] == "concrete"
    assert health["connected"] is False
    assert health["status"] == "disconnected"


@pytest.mark.asyncio
async def test_health_check_connected(adapter):
    await adapter.connect()
    health = await adapter.health_check()
    assert health["connected"] is True
    assert health["status"] == "healthy"


def test_point_type_enum_values():
    assert PointType.VOLTAGE.value == "voltage"
    assert PointType.ENERGY.value == "energy"
    assert PointType.PERCENTAGE.value == "percentage"
