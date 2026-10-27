"""
Modbus-RTU / MQTT 模拟器服务测试 - 覆盖率补强 ≥70%

被测: app/services/modbus_mqtt_simulator.py
设计: 纯逻辑无 DB 依赖, 直接实例化两个模拟器类走全部分支。

覆盖:
- ModbusSimulator init/connect/disconnect/read_data(连接+未连接)
- _generate_value (未知设备类型→0 / 未知参数→默认区间 / 精度<1 十位取整)
- parse_fault_code (短数据→正常 / 已知码映射 / 未知码)
- 三类设备类型 (inverter/pcs/meter) 参数集
- MQTTSimulator 全方法 (init/connect/disconnect/read_data连接+未连接/_generate_value未知参数)

注: 模块底部 test_simulators() 入口 + __main__ 未导入 logging 会 NameError,
属源码既有缺陷 (非本次范围), 70% 覆盖目标无需触及该入口。
"""
import pytest

from app.services.modbus_mqtt_simulator import ModbusSimulator, MQTTSimulator


# ═══════════════════════════════════════════════════════════════
# ModbusSimulator
# ═══════════════════════════════════════════════════════════════

class TestModbusSimulator:

    def test_init_defaults(self):
        sim = ModbusSimulator(device_type="inverter", address=7)
        assert sim.device_type == "inverter"
        assert sim.address == 7
        assert sim.connected is False
        # 参数范围 + 故障码表已加载
        assert "battery_soc" in sim.param_ranges["inverter"]
        assert 0x01 in sim.fault_codes["inverter"]

    @pytest.mark.asyncio
    async def test_connect_sets_connected(self):
        sim = ModbusSimulator("inverter", 1)
        ok = await sim.connect()
        assert ok is True
        assert sim.connected is True

    @pytest.mark.asyncio
    async def test_disconnect_clears_connected(self):
        # 覆盖 line 68-70 disconnect
        sim = ModbusSimulator("inverter", 1)
        await sim.connect()
        assert sim.connected is True
        ok = await sim.disconnect()
        assert ok is True
        assert sim.connected is False

    @pytest.mark.asyncio
    async def test_read_data_when_disconnected_returns_empty(self):
        # 覆盖 line 87-88 未连接返回 {}
        sim = ModbusSimulator("inverter", 1)
        assert await sim.read_data() == {}

    @pytest.mark.asyncio
    async def test_read_data_inverter_has_expected_fields(self):
        sim = ModbusSimulator("inverter", 3)
        await sim.connect()
        data = await sim.read_data()
        assert data["device_id"] == 3
        assert data["device_type"] == "inverter"
        assert "timestamp" in data
        assert "fault_code" in data  # 可能为 None 或某故障码
        # inverter 全部参数均生成
        for p in sim.param_ranges["inverter"]:
            assert p in data
        # 值范围抽查
        assert 220 <= data["grid_voltage_a"] <= 240
        assert 20 <= data["battery_soc"] <= 100

    @pytest.mark.asyncio
    async def test_read_data_pcs_type(self):
        # 覆盖 pcs 参数集分支
        sim = ModbusSimulator("pcs", 11)
        await sim.connect()
        data = await sim.read_data()
        assert data["device_type"] == "pcs"
        assert "dc_voltage" in data
        assert "ac_power" in data
        assert "efficiency" in data

    @pytest.mark.asyncio
    async def test_read_data_meter_type(self):
        # 覆盖 meter 参数集分支
        sim = ModbusSimulator("meter", 21)
        await sim.connect()
        data = await sim.read_data()
        assert data["device_type"] == "meter"
        assert "voltage_a" in data
        assert "power_total" in data

    def test_generate_value_unknown_device_type_returns_zero(self):
        # 覆盖 line 74-75 device_type 不在 param_ranges → return 0
        sim = ModbusSimulator("unknown_type", 1)
        assert sim._generate_value("any_param") == 0

    def test_generate_value_unknown_param_uses_default_range(self):
        # 参数名不在该类型范围 → 走默认 (0, 100, 1)
        sim = ModbusSimulator("inverter", 1)
        val = sim._generate_value("nonexistent_param")
        # base=50, variation=(100-0)*0.3=30 → [20, 80]
        assert isinstance(val, (int, float))
        assert 20 <= val <= 80

    def test_generate_value_precision_lt_one_rounds_to_ten(self):
        # 覆盖 line 83 precision<1 → round(value, -1) 十位对齐
        sim = ModbusSimulator("inverter", 1)
        for _ in range(20):
            v = sim._generate_value("grid_voltage_a")  # (220,240,0.1)
            assert 220 <= v <= 240
            assert v % 10 == 0  # 十位对齐

    @pytest.mark.asyncio
    async def test_read_data_unknown_device_type_does_not_crash(self):
        # [卡101bdfb3] 未知 device_type 不应在 self.fault_codes[device_type] 索引时 KeyError
        sim = ModbusSimulator("totally_unknown_type", 1)
        await sim.connect()
        data = await sim.read_data()
        assert isinstance(data, dict)
        assert data.get("device_type") == "totally_unknown_type"
        assert "fault_code" in data  # 回退为 None


# ═══════════════════════════════════════════════════════════════
# parse_fault_code
# ═══════════════════════════════════════════════════════════════

class TestParseFaultCode:

    def test_short_data_returns_normal(self):
        # 覆盖 line 108-109 len<2 → "正常"
        sim = ModbusSimulator("inverter", 1)
        assert sim.parse_fault_code(b"") == "正常"
        assert sim.parse_fault_code(b"\x00") == "正常"

    def test_known_codes_mapped(self):
        # 覆盖 line 110-122 fault_map 已知码
        sim = ModbusSimulator("inverter", 1)
        assert sim.parse_fault_code(b"\x00\x01") == "电网过压"      # 0x01
        assert sim.parse_fault_code(b"\x00\x03") == "电网欠压"      # 0x03
        assert sim.parse_fault_code(b"\x00\x27") == "电网频率异常"  # 0x27
        assert sim.parse_fault_code(b"\x00\x3C") == "逆变器过温"    # 0x3C
        assert sim.parse_fault_code(b"\x00\x50") == "绝缘阻抗低"    # 0x50
        assert sim.parse_fault_code(b"\x00\x7E") == "电池过压"      # 0x7E
        assert sim.parse_fault_code(b"\x00\xA0") == "电池过温"      # 0xA0
        assert sim.parse_fault_code(b"\x01\x01") == "功率模块故障"  # 0x0101
        assert sim.parse_fault_code(b"\x02\x01") == "通信故障"      # 0x0201

    def test_unknown_code_returns_unknown(self):
        # 覆盖 line 122 未映射码 → "未知故障(0xXXXX)"
        sim = ModbusSimulator("inverter", 1)
        result = sim.parse_fault_code(b"\xff\xff")  # 0xFFFF 未映射
        assert result.startswith("未知故障")
        assert "FFFF" in result


# ═══════════════════════════════════════════════════════════════
# MQTTSimulator
# ═══════════════════════════════════════════════════════════════

class TestMQTTSimulator:

    def test_init_defaults(self):
        sim = MQTTSimulator(charger_id="C002")
        assert sim.charger_id == "C002"
        assert sim.connected is False
        assert "charging_power" in sim.state_ranges
        assert None in sim.fault_codes  # 含正常(None)

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        # 覆盖 line 145-147 connect + 149-151 disconnect
        sim = MQTTSimulator("C001")
        assert await sim.connect() is True
        assert sim.connected is True
        assert await sim.disconnect() is True
        assert sim.connected is False

    @pytest.mark.asyncio
    async def test_read_data_when_disconnected_returns_empty(self):
        # 覆盖 line 162-163 未连接返回 {}
        sim = MQTTSimulator("C001")
        assert await sim.read_data() == {}

    @pytest.mark.asyncio
    async def test_read_data_has_expected_fields(self):
        sim = MQTTSimulator("C001")
        await sim.connect()
        data = await sim.read_data()
        assert data["charger_id"] == "C001"
        assert "timestamp" in data
        assert data["status"] in ("charging", "idle", "fault")
        assert "fault_code" in data
        # 所有 state_ranges 参数均生成
        for p in sim.state_ranges:
            assert p in data
        # 值范围抽查
        assert 0 <= data["soc"] <= 100

    def test_generate_value_unknown_param_default(self):
        # 覆盖 line 154 未知参数 → 默认 (0,100,1)
        sim = MQTTSimulator("C001")
        val = sim._generate_value("no_such_param")
        assert 20 <= val <= 80  # base 50 ± variation 30
