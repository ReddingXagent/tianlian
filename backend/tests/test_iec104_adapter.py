"""
IEC60870-5-104 协议适配器集成测试 (Phase33-Task4)

覆盖 app/gateway/iec104.py:
  - ASDUType / CauseOfTransmission 枚举
  - ASDUCodec: encode_general_interrogation / encode_single_command / decode_asdu 各类型
  - IEC104Client: 生命周期 + read_data/read_*/write_command/general_interrogation/clock_sync
  - registry 集成: iec104 协议自动注册

测试风格遵循 tests/test_health_probe.py: async 用 asyncio.run 包裹。
"""
import asyncio
import struct

import pytest

from app.gateway.iec104 import (
    IEC104Client,
    ASDUCodec,
    ASDUType,
    CauseOfTransmission,
)
from app.gateway import get_registry


# ========== 枚举 ==========

class TestEnums:
    def test_asdu_type_values(self):
        assert ASDUType.M_SP_NA == 1
        assert ASDUType.M_ME_NC == 13
        assert ASDUType.C_IC_NA == 100
        assert ASDUType.C_CS_NA == 103

    def test_cause_of_transmission_values(self):
        assert CauseOfTransmission.PERIODIC == 1
        assert CauseOfTransmission.ACTIVATION == 6
        assert CauseOfTransmission.INTERROGATED == 20


# ========== ASDUCodec 编码 ==========

class TestASDUCodecEncode:
    def test_encode_general_interrogation_structure(self):
        """总召唤: TypeID=100, VSQ=1, COT=ACTIVATION, QOI=0x14"""
        asdu = ASDUCodec.encode_general_interrogation(common_address=1)
        assert asdu[0] == ASDUType.C_IC_NA          # 100
        assert asdu[1] == 0x01                        # VSQ: SQ=0, N=1
        assert asdu[2] == CauseOfTransmission.ACTIVATION
        assert asdu[-1] == 0x14                       # QOI 总召唤限定词
        assert len(asdu) == 10

    def test_encode_general_interrogation_common_address(self):
        """common_address 编码到 CASDU 高字节"""
        asdu = ASDUCodec.encode_general_interrogation(common_address=2)
        # casdu_lo=0x00 (asdu[4]), casdu_hi=common_address&0xFF (asdu[5])
        assert asdu[5] == 2

    def test_encode_single_command_on(self):
        """合闸: SCO=0x01"""
        asdu = ASDUCodec.encode_single_command(ioa=1, value=True, common_address=1)
        assert asdu[0] == ASDUType.C_SC_NA            # 45
        assert asdu[-1] == 0x01                        # SCO 合闸

    def test_encode_single_command_off(self):
        """分闸: SCO=0x00"""
        asdu = ASDUCodec.encode_single_command(ioa=1, value=False, common_address=1)
        assert asdu[-1] == 0x00

    def test_encode_single_command_ioa_little_endian(self):
        """IOA 3 字节小端: ioa=258 → [0x02, 0x01, 0x00]"""
        asdu = ASDUCodec.encode_single_command(ioa=258, value=True, common_address=1)
        # IOA 起始于 asdu[6] (TypeID/VSQ/COT2/CASDU2 = 6 字节)
        assert asdu[6] == 0x02
        assert asdu[7] == 0x01
        assert asdu[8] == 0x00


# ========== ASDUCodec 解码 ==========

class TestASDUCodecDecode:
    def test_decode_single_point(self):
        """M_SP_NA (1): 单点信息 + 质量"""
        asdu = bytes([1, 1, 3, 0, 0, 1, 5, 0, 0, 0x81])  # siq=0x81 → value=1, quality_valid=1
        result = ASDUCodec.decode_asdu(asdu)
        assert result["type_id"] == 1
        assert result["type_name"] == "M_SP_NA"
        assert result["ioa"] == 5
        assert result["value"] is True
        assert result["quality_valid"] is True

    def test_decode_normalized_measure(self):
        """M_ME_NA (9): 归一化测量值 = raw / 32767"""
        raw = 16384
        asdu = bytes([9, 1, 3, 0, 0, 1, 5, 0, 0]) + struct.pack(">h", raw) + bytes([0x00])
        result = ASDUCodec.decode_asdu(asdu)
        assert result["raw_value"] == 16384
        assert result["normalized_value"] == pytest.approx(16384 / 32767.0)

    def test_decode_scaled_measure(self):
        """M_ME_NB (11): 标度化测量值"""
        asdu = bytes([11, 1, 3, 0, 0, 1, 5, 0, 0]) + struct.pack(">h", 100) + bytes([0x00])
        result = ASDUCodec.decode_asdu(asdu)
        assert result["raw_value"] == 100

    def test_decode_short_float_measure(self):
        """M_ME_NC (13): 短浮点"""
        asdu = bytes([13, 1, 3, 0, 0, 1, 5, 0, 0]) + struct.pack(">f", 3.14)
        result = ASDUCodec.decode_asdu(asdu)
        assert result["float_value"] == pytest.approx(3.14, abs=1e-3)

    def test_decode_integrated(self):
        """M_IT_NA (15): 累计量 uint32"""
        asdu = bytes([15, 1, 3, 0, 0, 1, 5, 0, 0]) + struct.pack(">I", 123456)
        result = ASDUCodec.decode_asdu(asdu)
        assert result["raw_value"] == 123456

    def test_decode_too_short_returns_none(self):
        """ASDU < 7 字节 → None"""
        assert ASDUCodec.decode_asdu(b"\x01\x02\x03") is None

    def test_decode_unknown_type_name(self):
        """未知 type_id → type_name = UNKNOWN(...)"""
        asdu = bytes([200, 1, 3, 0, 0, 1, 0])  # len=7 恰好通过长度门槛
        result = ASDUCodec.decode_asdu(asdu)
        assert result["type_name"] == "UNKNOWN(200)"


# ========== IEC104Client 生命周期 ==========

class TestIEC104ClientLifecycle:
    def test_protocol_type(self):
        client = IEC104Client()
        assert client.protocol_type == "iec104"

    def test_default_config(self):
        client = IEC104Client()
        assert client.port == 2404
        assert client.common_address == 1
        assert client.k == 12
        assert client.w == 8
        assert client.use_tls is False

    def test_initialize(self):
        client = IEC104Client()
        assert asyncio.run(client.initialize()) is True
        assert client.initialized is True

    def test_connect_disconnect(self):
        client = IEC104Client()
        assert asyncio.run(client.connect()) is True
        assert client.is_connected() is True
        assert asyncio.run(client.disconnect()) is True
        assert client.is_connected() is False


# ========== IEC104Client 数据读取 ==========

class TestIEC104ClientRead:
    def test_read_data_aggregates_all(self):
        """read_data 聚合 analog + digital + integrated + timestamp/common_address"""
        client = IEC104Client()
        telemetry = asyncio.run(client.read_data(device_address=1))
        assert "timestamp" in telemetry
        assert telemetry["common_address"] == client.common_address
        # 模拟量
        assert "bus_voltage_a" in telemetry
        assert "active_power_total" in telemetry
        # 数字量
        assert "breaker_cb101_status" in telemetry
        assert "grid_connected" in telemetry
        # 累计量
        assert "energy_import" in telemetry

    def test_read_analog_values(self):
        client = IEC104Client()
        analog = asyncio.run(client.read_analog_values())
        assert "bus_voltage_a" in analog
        assert "grid_frequency" in analog
        assert "irradiance" in analog

    def test_read_digital_values(self):
        client = IEC104Client()
        digital = asyncio.run(client.read_digital_values())
        assert "breaker_cb101_status" in digital
        assert "fire_alarm_status" in digital

    def test_read_integrated_values(self):
        client = IEC104Client()
        integrated = asyncio.run(client.read_integrated_values())
        assert "energy_import" in integrated
        assert "pv_total_energy" in integrated


# ========== IEC104Client 控制 ==========

class TestIEC104ClientControl:
    def test_write_command(self):
        client = IEC104Client()
        assert asyncio.run(client.write_command(1, {"ioa": 5, "value": True})) is True

    def test_send_command(self):
        client = IEC104Client()
        assert asyncio.run(client.send_command(ioa=5, value=False)) is True

    def test_general_interrogation(self):
        client = IEC104Client()
        assert asyncio.run(client.general_interrogation()) is True

    def test_clock_sync(self):
        client = IEC104Client()
        assert asyncio.run(client.clock_sync()) is True

    def test_parse_fault_code_returns_none(self):
        client = IEC104Client()
        assert client.parse_fault_code(b"\x00\x01") is None


# ========== Registry 集成 ==========

class TestIEC104Registry:
    def test_iec104_registered(self):
        reg = get_registry()
        assert reg.has_adapter("iec104") is True

    def test_iec104_in_list_protocols(self):
        reg = get_registry()
        assert reg.list_protocols().get("iec104") == "IEC104Client"
