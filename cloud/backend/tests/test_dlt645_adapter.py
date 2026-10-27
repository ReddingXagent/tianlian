"""
DLT645-2007 协议适配器集成测试 (Phase33-Task4)

覆盖 app/gateway/dlt645.py:
  - DLT645Codec: 帧编解码 (encode_read_request / decode_response / _encode_address / _parse_value)
  - DLT645Adapter: 生命周期 + read_data/read_by_di/read_energy/read_instantaneous/write_command
  - registry 集成: dlt645 协议自动注册

测试风格遵循 tests/test_health_probe.py: async 用 asyncio.run 包裹, 无 pytest-asyncio marker。
"""
import asyncio
import struct

import pytest

from app.gateway.dlt645 import DLT645Adapter, DLT645Codec
from app.gateway import get_registry


# ========== 测试辅助 ==========

def _build_response_frame(meter_address: str, di_code: str, value_bytes: bytes,
                          ctrl_code: int = 0x91) -> bytes:
    """独立构造 DLT645 响应帧，交叉验证 codec.decode_response (不复用生产 _simulate_response)"""
    codec = DLT645Codec()
    di_bytes = bytes.fromhex(di_code)
    data_domain = di_bytes + value_bytes
    addr = codec._encode_address(meter_address)

    frame = bytearray()
    frame.append(DLT645Codec.FRAME_START)
    frame.extend(addr)
    frame.append(DLT645Codec.FRAME_START)
    frame.append(ctrl_code)
    frame.append(len(data_domain))
    for b in data_domain:
        frame.append((b + 0x33) & 0xFF)
    cs = sum(frame) & 0xFF
    frame.append(cs)
    frame.append(DLT645Codec.FRAME_END)
    return bytes(frame)


# ========== DLT645Codec 编解码 ==========

class TestDLT645CodecEncode:
    """encode_read_request + _encode_address"""

    def test_encode_read_request_frame_structure(self):
        """请求帧结构: 68H | addr(6) | 68H | 11H | len | DI+0x33(4) | cs | 16H"""
        codec = DLT645Codec()
        frame = codec.encode_read_request("000101000001", "02010100")

        assert frame[0] == DLT645Codec.FRAME_START          # 0x68
        assert frame[7] == DLT645Codec.FRAME_START          # 第二个 0x68
        assert frame[8] == DLT645Codec.CMD_READ_DATA        # 0x11
        assert frame[9] == 4                                # 数据域长度 = DI 4 字节
        assert frame[-1] == DLT645Codec.FRAME_END           # 0x16
        assert len(frame) == 16                             # 1+6+1+1+1+4+1+1

    def test_encode_read_request_di_plus_0x33(self):
        """数据域每字节加 0x33: DI 02 01 01 00 → 35 34 34 33"""
        codec = DLT645Codec()
        frame = codec.encode_read_request("000101000001", "02010100")
        assert frame[10:14] == bytes([0x02 + 0x33, 0x01 + 0x33, 0x01 + 0x33, 0x00 + 0x33])

    def test_encode_read_request_checksum(self):
        """校验和 = 起始到校验和前所有字节的模 256 和"""
        codec = DLT645Codec()
        frame = codec.encode_read_request("000101000001", "02010100")
        expected_cs = sum(frame[:-2]) & 0xFF
        assert frame[-2] == expected_cs

    def test_encode_read_request_invalid_di_raises(self):
        """DI 码非 4 字节 → ValueError"""
        codec = DLT645Codec()
        with pytest.raises(ValueError):
            codec.encode_read_request("000101000001", "0201")  # 仅 2 字节

    def test_encode_address_little_endian_bcd(self):
        """表地址 12 位 BCD 小端序: "000101000001" → [01,00,00,01,01,00]"""
        codec = DLT645Codec()
        addr = codec._encode_address("000101000001")
        # 原地址按 2 字符分组: 00 01 01 00 00 01，小端反转存放
        assert addr == bytes([0x01, 0x00, 0x00, 0x01, 0x01, 0x00])

    def test_encode_address_pads_short(self):
        """短表号自动 zfill(12)"""
        codec = DLT645Codec()
        addr = codec._encode_address("1")
        assert len(addr) == 6


class TestDLT645CodecDecode:
    """decode_response 各分支"""

    def test_decode_normal_response_known_di(self):
        """正常应答 (0x91) + DI_MAP 内 DI → 解析出 name/value/unit

        DI=02010100 (voltage_a, scale 0.1), value_bytes=0x05 0x22 → BCD "2205" → 220.5 V
        """
        codec = DLT645Codec()
        frame = _build_response_frame("000101000001", "02010100", b"\x05\x22", ctrl_code=0x91)
        result = codec.decode_response(frame)

        assert result is not None
        assert result["ctrl_code"] == 0x91
        assert result["di_code"] == "02010100"
        assert result["name"] == "voltage_a"
        assert result["unit"] == "V"
        assert result["value"] == pytest.approx(220.5)

    def test_decode_normal_response_unknown_di(self):
        """DI 不在 DI_MAP → 返回 di_code/value_raw 但无 name/value"""
        codec = DLT645Codec()
        frame = _build_response_frame("000101000001", "99999999", b"\x05\x22", ctrl_code=0x91)
        result = codec.decode_response(frame)

        assert result is not None
        assert result["di_code"] == "99999999"
        assert "name" not in result
        assert "value" not in result
        assert "value_raw" in result

    def test_decode_exception_response(self):
        """异常应答 (0xD1) → 返回 error 标志"""
        codec = DLT645Codec()
        frame = _build_response_frame("000101000001", "02010100", b"", ctrl_code=0xD1)
        result = codec.decode_response(frame)
        assert result == {"ctrl_code": 0xD1, "error": True}

    def test_decode_too_short_returns_none(self):
        """帧 < 12 字节 → None"""
        codec = DLT645Codec()
        assert codec.decode_response(b"\x68\x00") is None

    def test_decode_bad_first_start_returns_none(self):
        """首字节非 0x68 → None"""
        codec = DLT645Codec()
        frame = _build_response_frame("000101000001", "02010100", b"\x05\x22")
        frame = bytes([0x00]) + frame[1:]
        assert codec.decode_response(frame) is None

    def test_decode_bad_second_start_returns_none(self):
        """第二个起始符 (frame[7]) 非 0x68 → None"""
        codec = DLT645Codec()
        frame = bytearray(_build_response_frame("000101000001", "02010100", b"\x05\x22"))
        frame[7] = 0x00
        assert codec.decode_response(bytes(frame)) is None

    def test_decode_data_len_overflow_returns_none(self):
        """数据域长度声明超过帧实际长度 → None"""
        codec = DLT645Codec()
        frame = bytearray(_build_response_frame("000101000001", "02010100", b"\x05\x22"))
        frame[9] = 0xFF  # 声明 255 字节数据域，远超实际
        assert codec.decode_response(bytes(frame)) is None


class TestDLT645CodecParseValue:
    """_parse_value BCD / 大端回退 / 空"""

    def test_parse_value_bcd(self):
        """b'\\x01\\x23' 反转后 23 01 → BCD "2301" → 2301.0"""
        codec = DLT645Codec()
        assert codec._parse_value(b"\x01\x23") == 2301.0

    def test_parse_value_binary_fallback(self):
        """非 BCD 字节 (0x0A low=10>9) → 回退大端整数"""
        codec = DLT645Codec()
        assert codec._parse_value(b"\x0A") == 10.0

    def test_parse_value_empty(self):
        """空数据 → 0.0"""
        codec = DLT645Codec()
        assert codec._parse_value(b"") == 0.0

    def test_di_map_non_empty(self):
        """DI_MAP 含已知数据标识"""
        assert "00000000" in DLT645Codec.DI_MAP          # 组合有功总电能
        assert "02010100" in DLT645Codec.DI_MAP          # A 相电压
        assert DLT645Codec.DI_MAP["02010100"][0] == "voltage_a"


# ========== DLT645Adapter ==========

class TestDLT645AdapterLifecycle:
    """生命周期 + 配置"""

    def test_protocol_type(self):
        adapter = DLT645Adapter()
        assert adapter.protocol_type == "dlt645"

    def test_default_config(self):
        adapter = DLT645Adapter()
        assert adapter.baudrate == 2400
        assert adapter.parity == "even"
        assert adapter.retry_count == 3
        assert isinstance(adapter.codec, DLT645Codec)

    def test_initialize(self):
        adapter = DLT645Adapter()
        assert asyncio.run(adapter.initialize()) is True
        assert adapter.initialized is True

    def test_connect_disconnect(self):
        adapter = DLT645Adapter()
        assert asyncio.run(adapter.connect()) is True
        assert adapter.is_connected() is True
        assert asyncio.run(adapter.disconnect()) is True
        assert adapter.is_connected() is False


class TestDLT645AdapterRead:
    """数据读取 (走 _simulate_response 模拟链路)"""

    def test_read_by_di_returns_decoded(self):
        adapter = DLT645Adapter()
        result = asyncio.run(adapter.read_by_di("02010100"))
        assert result is not None
        assert result["di_code"] == "02010100"
        assert result["name"] == "voltage_a"

    def test_read_data_aggregates_all_di(self):
        """read_data 遍历整个 DI_MAP，返回聚合遥测"""
        adapter = DLT645Adapter()
        telemetry = asyncio.run(adapter.read_data(device_address=1))
        assert telemetry["meter_address"] == adapter.meter_address
        assert "timestamp" in telemetry
        # 至少包含电压/电流/电能等已知字段
        assert "voltage_a" in telemetry
        assert "grid_frequency" in telemetry
        assert "positive_active_energy_total" in telemetry

    def test_read_energy(self):
        adapter = DLT645Adapter()
        energy = asyncio.run(adapter.read_energy())
        assert "positive_active_energy_total" in energy
        assert "reverse_active_energy_total" in energy

    def test_read_instantaneous(self):
        adapter = DLT645Adapter()
        instant = asyncio.run(adapter.read_instantaneous())
        assert "voltage_a" in instant
        assert "current_a" in instant
        assert "active_power_total" in instant
        assert "grid_frequency" in instant

    def test_read_data_auto_connect(self):
        """未连接时 read_data 自动 connect"""
        adapter = DLT645Adapter()
        assert adapter.is_connected() is False
        asyncio.run(adapter.read_data(1))
        assert adapter.is_connected() is True


class TestDLT645AdapterControl:
    """控制指令"""

    def test_write_command_calls_broadcast(self):
        """write_command 委托 broadcast_time_sync，返回 True"""
        adapter = DLT645Adapter()
        assert asyncio.run(adapter.write_command(1, {})) is True

    def test_broadcast_time_sync(self):
        adapter = DLT645Adapter()
        assert asyncio.run(adapter.broadcast_time_sync()) is True

    def test_change_baudrate(self):
        adapter = DLT645Adapter()
        assert asyncio.run(adapter.change_baudrate(9600)) is True
        assert adapter.baudrate == 9600

    def test_parse_fault_code_returns_none(self):
        adapter = DLT645Adapter()
        assert adapter.parse_fault_code(b"\x00\x01") is None


# ========== Registry 集成 ==========

class TestDLT645Registry:
    """dlt645 协议在全局 registry 自动注册"""

    def test_dlt645_registered(self):
        reg = get_registry()
        assert reg.has_adapter("dlt645") is True

    def test_dlt645_in_list_protocols(self):
        reg = get_registry()
        assert reg.list_protocols().get("dlt645") == "DLT645Adapter"
