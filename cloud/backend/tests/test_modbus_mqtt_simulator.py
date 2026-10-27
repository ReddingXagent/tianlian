"""test_modbus_mqtt_simulator.py — Modbus/MQTT模拟器单元测试

覆盖: ModbusSimulator (连接/断开/读数据/值生成/故障码解析/未知设备类型),
MQTTSimulator (连接/断开/读数据/值生成), test_simulators 入口。
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock

from app.services.modbus_mqtt_simulator import (
    ModbusSimulator,
    MQTTSimulator,
    test_simulators,
)


# 强制 connect/disconnect 的 except 分支: 对 connected 赋值必抛。
# 构造实例后再换 __class__ (布局兼容的子类), __init__ 不受影响。
class _ConnectedAssignRaisesModbus(ModbusSimulator):
    def __setattr__(self, key, value):
        if key == "connected":
            raise RuntimeError("forced connected-assign failure")
        super().__setattr__(key, value)


class _ConnectedAssignRaisesMQTT(MQTTSimulator):
    def __setattr__(self, key, value):
        if key == "connected":
            raise RuntimeError("forced connected-assign failure")
        super().__setattr__(key, value)


def _raise_runtime(*args, **kwargs):
    raise RuntimeError("forced failure")


# ─── ModbusSimulator ───

class TestModbusSimulatorInit:
    def test_defaults(self):
        sim = ModbusSimulator()
        assert sim.device_type == "inverter"
        assert sim.address == 1
        assert sim.connected is False

    def test_custom(self):
        sim = ModbusSimulator("pcs", 11)
        assert sim.device_type == "pcs"
        assert sim.address == 11

    def test_param_ranges_exist(self):
        sim = ModbusSimulator()
        assert "inverter" in sim.param_ranges
        assert "pcs" in sim.param_ranges
        assert "meter" in sim.param_ranges

    def test_fault_codes_exist(self):
        sim = ModbusSimulator()
        assert "inverter" in sim.fault_codes
        assert None in sim.fault_codes["meter"]  # meter has no faults


class TestModbusConnect:
    @pytest.mark.asyncio
    async def test_connect(self):
        sim = ModbusSimulator()
        result = await sim.connect()
        assert result is True
        assert sim.connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        sim = ModbusSimulator()
        await sim.connect()
        result = await sim.disconnect()
        assert result is True
        assert sim.connected is False


class TestModbusReadData:
    @pytest.mark.asyncio
    async def test_not_connected_returns_empty(self):
        sim = ModbusSimulator()
        data = await sim.read_data()
        assert data == {}

    @pytest.mark.asyncio
    async def test_connected_returns_data(self):
        sim = ModbusSimulator("inverter", 1)
        await sim.connect()
        data = await sim.read_data()
        assert "device_id" in data
        assert "device_type" in data
        assert "timestamp" in data
        assert "fault_code" in data
        assert "grid_voltage_a" in data

    @pytest.mark.asyncio
    async def test_pcs_data(self):
        sim = ModbusSimulator("pcs", 11)
        await sim.connect()
        data = await sim.read_data()
        assert "dc_voltage" in data
        assert "efficiency" in data

    @pytest.mark.asyncio
    async def test_meter_data(self):
        sim = ModbusSimulator("meter", 21)
        await sim.connect()
        data = await sim.read_data()
        assert "voltage_a" in data
        assert "voltage_b" in data
        assert "voltage_c" in data

    @pytest.mark.asyncio
    async def test_read_data_unknown_device_type_does_not_crash(self):
        """未知 device_type 不应在 self.fault_codes[device_type] 索引时 KeyError。"""
        sim = ModbusSimulator("totally_unknown_type", 1)
        await sim.connect()
        data = await sim.read_data()
        assert isinstance(data, dict)
        assert data.get("device_type") == "totally_unknown_type"
        assert "fault_code" in data  # 回退为 None


class TestGenerateValue:
    def test_inverter_param(self):
        sim = ModbusSimulator("inverter")
        val = sim._generate_value("grid_voltage_a")
        # Should be in range (220-240 ± 30%)
        assert 150 < val < 300

    def test_unknown_device_type(self):
        sim = ModbusSimulator("unknown")
        val = sim._generate_value("anything")
        assert val == 0

    def test_unknown_param(self):
        sim = ModbusSimulator("inverter")
        val = sim._generate_value("nonexistent")
        # Default range (0, 100, 1)
        assert isinstance(val, (int, float))


class TestParseFaultCode:
    def test_short_data(self):
        sim = ModbusSimulator()
        assert sim.parse_fault_code(b"\x00") == "正常"

    def test_empty_data(self):
        sim = ModbusSimulator()
        assert sim.parse_fault_code(b"") == "正常"

    def test_known_code_overvoltage(self):
        sim = ModbusSimulator()
        result = sim.parse_fault_code(b"\x00\x01")
        assert "过压" in result

    def test_known_code_frequency(self):
        sim = ModbusSimulator()
        result = sim.parse_fault_code(b"\x00\x27")
        assert "频率" in result

    def test_unknown_code(self):
        sim = ModbusSimulator()
        result = sim.parse_fault_code(b"\xFF\xFF")
        assert "未知" in result


# ─── MQTTSimulator ───

class TestMQTTSimulatorInit:
    def test_defaults(self):
        sim = MQTTSimulator()
        assert sim.charger_id == "C001"
        assert sim.connected is False

    def test_custom_id(self):
        sim = MQTTSimulator("C999")
        assert sim.charger_id == "C999"

    def test_state_ranges(self):
        sim = MQTTSimulator()
        assert "charging_power" in sim.state_ranges
        assert "soc" in sim.state_ranges


class TestMQTTConnect:
    @pytest.mark.asyncio
    async def test_connect(self):
        sim = MQTTSimulator()
        result = await sim.connect()
        assert result is True
        assert sim.connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self):
        sim = MQTTSimulator()
        await sim.connect()
        result = await sim.disconnect()
        assert result is True
        assert sim.connected is False


class TestMQTTReadData:
    @pytest.mark.asyncio
    async def test_not_connected(self):
        sim = MQTTSimulator()
        data = await sim.read_data()
        assert data == {}

    @pytest.mark.asyncio
    async def test_connected(self):
        sim = MQTTSimulator("C001")
        await sim.connect()
        data = await sim.read_data()
        assert data["charger_id"] == "C001"
        assert "timestamp" in data
        assert "status" in data
        assert "charging_power" in data
        assert "soc" in data
        assert "fault_code" in data

    @pytest.mark.asyncio
    async def test_status_in_valid_set(self):
        sim = MQTTSimulator()
        await sim.connect()
        data = await sim.read_data()
        assert data["status"] in ("charging", "idle", "fault")


class TestMQTTGenerateValue:
    def test_known_param(self):
        sim = MQTTSimulator()
        val = sim._generate_value("soc")
        assert isinstance(val, (int, float))

    def test_unknown_param(self):
        sim = MQTTSimulator()
        val = sim._generate_value("nonexistent")
        assert isinstance(val, (int, float))


# ─── test_simulators 入口 ───

class TestSimulatorsEntry:
    @pytest.mark.asyncio
    async def test_runs_without_error(self):
        """模块入口 test_simulators() 完整跑通 Modbus + MQTT 模拟, 不抛异常。

        (早期版本曾有 logging 未导入的 bug 导致跳过; 现源码用模块级 logger,
        已修复, 此处真实调用覆盖入口函数全部分支。)
        """
        result = await test_simulators()
        assert result is None  # 入口函数无返回值


# ─── 异常分支 (各 except Exception 兜底) ───

class TestModbusExceptionBranches:
    @pytest.mark.asyncio
    async def test_connect_exception_returns_false(self):
        """connect: 对 connected 赋值抛 → except → 返回 False。"""
        sim = ModbusSimulator()
        sim.__class__ = _ConnectedAssignRaisesModbus
        assert await sim.connect() is False

    @pytest.mark.asyncio
    async def test_disconnect_exception_returns_false(self):
        """disconnect: 对 connected 赋值抛 → except → 返回 False。"""
        sim = ModbusSimulator()
        sim.__class__ = _ConnectedAssignRaisesModbus
        assert await sim.disconnect() is False

    def test_generate_value_exception_returns_zero(self):
        """_generate_value: range_def 解包失败 (非 3 元组) → except → 返回 0。"""
        sim = ModbusSimulator("inverter")
        sim.param_ranges["inverter"]["grid_voltage_a"] = "not-a-tuple"  # 字符串解包报错
        assert sim._generate_value("grid_voltage_a") == 0

    @pytest.mark.asyncio
    async def test_read_data_exception_returns_empty(self, monkeypatch):
        """read_data: _generate_value 抛 → except → 返回 {}。"""
        sim = ModbusSimulator("inverter")
        await sim.connect()
        monkeypatch.setattr(sim, "_generate_value", _raise_runtime)
        assert await sim.read_data() == {}

    def test_parse_fault_code_exception_returns_error_text(self):
        """parse_fault_code: len(int) 抛 TypeError → except → 返回 '解析异常'。"""
        sim = ModbusSimulator()
        assert sim.parse_fault_code(12345) == "解析异常"


class TestMQTTExceptionBranches:
    @pytest.mark.asyncio
    async def test_connect_exception_returns_false(self):
        sim = MQTTSimulator()
        sim.__class__ = _ConnectedAssignRaisesMQTT
        assert await sim.connect() is False

    @pytest.mark.asyncio
    async def test_disconnect_exception_returns_false(self):
        sim = MQTTSimulator()
        sim.__class__ = _ConnectedAssignRaisesMQTT
        assert await sim.disconnect() is False

    def test_generate_value_exception_returns_zero(self):
        sim = MQTTSimulator()
        sim.state_ranges["soc"] = "not-a-tuple"
        assert sim._generate_value("soc") == 0

    @pytest.mark.asyncio
    async def test_read_data_exception_returns_empty(self, monkeypatch):
        sim = MQTTSimulator()
        await sim.connect()
        monkeypatch.setattr(sim, "_generate_value", _raise_runtime)
        assert await sim.read_data() == {}
