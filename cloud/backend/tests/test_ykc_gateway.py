"""
YKC 云快充 V1.6 适配器测试 (任务卡 9a5d070e)

覆盖 app/gateway/ykc.py:
  - 帧编解码: encode/decode/CRC16 (对照规格书样例报文) + 粘包切分/坏帧丢弃
  - 登录握手: TCP server 真实握手 + 鉴权 (桩编号已注册/未注册)
  - 遥测归一化: 0x13 实时数据解析 + pipeline 归一化 + 0x3B 交易记录/0x40 确认
  - 双格式识别: V1.6 (桩编号 7B/14位) vs V1.8+ (8B/16位) + Device.sn 双向匹配

测试风格遵循 tests/test_dlt645_adapter.py: async 用 asyncio.run 包裹, 无 pytest-asyncio marker。
"""
import asyncio
import socket
import struct
from datetime import datetime, timezone

import pytest

from app.gateway.ykc import (
    YKCAdapter,
    YKCCodec,
    YKCFrame,
    YKCFrameType,
    YKCLoginResult,
    crc16,
    decode_login,
    decode_realtime,
    decode_transaction,
    detect_protocol_version,
    encode_bcd,
    encode_cp56time2a,
    decode_cp56time2a,
    normalize_sn,
)
from app.gateway import get_registry


SN14 = "32010600019236"        # 14 位桩编号 (V1.6 原始形态)
SN16 = "00" + SN14             # 16 位桩编号 (V1.8+ 形态 = 14 位左补零)


# ========== 测试辅助 ==========

def build_login_body_v16(sn: str = SN14) -> bytes:
    """V1.6 登录体 30 字节: 桩(7) 类型(1) 枪数(1) 版本(1) 程序版本(8) 网络(1) sim(10) 运营商(1)"""
    return (
        encode_bcd(sn, 7)
        + bytes([0x00, 0x02, 0x10])               # 直流 / 2枪 / V1.6 (0x10 = 1.6×10)
        + b"v4.1.60\x00"                          # 程序版本 8 字节
        + bytes([0x01])                            # LAN
        + encode_bcd("12345678901234567890", 10)   # sim BCD 10 字节
        + bytes([0x04])                            # 其他运营商
    )


def build_login_body_v18(sn: str = SN16) -> bytes:
    """V1.8 登录体 31 字节: 桩编号 8 字节"""
    return (
        encode_bcd(sn, 8)
        + bytes([0x00, 0x02, 0x12])               # V1.8 (0x12)
        + b"v4.1.80\x00"
        + bytes([0x01])
        + encode_bcd("12345678901234567890", 10)
        + bytes([0x04])
    )


def build_realtime_body(sn: str, sn_len: int, *, status: int = 0x03,
                        voltage: int = 4001, current: int = 1500,
                        energy: int = 12340, trade_no: str = "0" * 32) -> bytes:
    """0x13 实时监测数据体。"""
    return (
        encode_bcd(trade_no, 16)
        + encode_bcd(sn, sn_len)
        + bytes([0x01, status, 0x01, 0x01])        # 枪1 / 状态 / 已归位 / 已插枪
        + struct.pack("<HH", voltage, current)     # 400.1V / 150.0A
        + bytes([60 + 50])                         # 枪线温度 60°C (偏移-50)
        + b"\x11" * 8                              # 枪线编码
        + bytes([80])                              # SOC 80%
        + bytes([35 + 50])                         # 电池组最高温度 35°C
        + struct.pack("<HH", 12, 30)               # 已充/剩余 分钟
        + struct.pack("<III", energy, energy, 20000)  # 充电度数/计损/已充金额 (4位小数)
        + struct.pack("<H", 0)                     # 硬件故障位
    )


def build_transaction_body(sn: str, sn_len: int, trade_no: str = "3" * 32) -> bytes:
    """0x3B 交易记录体。"""
    now = encode_cp56time2a(datetime(2026, 9, 28, 12, 30, 45, tzinfo=timezone.utc))
    body = bytearray()
    body += encode_bcd(trade_no, 16)
    body += encode_bcd(sn, sn_len)
    body += bytes([0x01])            # 枪号
    body += now + now                # 开始/结束时间
    for _ in range(4):               # 尖/峰/平/谷: 单价+电量+计损+金额
        body += struct.pack("<IIII", 130000, 10000, 10000, 13000)
    body += int(10000).to_bytes(5, "little")   # 电表总起值 1.0000
    body += int(22340).to_bytes(5, "little")   # 电表总止值 2.2340
    body += struct.pack("<II", 12340, 12340)   # 总电量/计损总电量
    body += struct.pack("<I", 16000)           # 消费金额 1.6000
    body += b"LSVAA123456789012"              # VIN 17 字节
    body += bytes([0x01])                     # app 启动
    body += now                               # 交易时间
    body += bytes([0x41])                     # 停止原因: SOC 达到 100%
    body += b"\x00" * 7 + b"\x54"             # 物理卡号 8 字节
    return bytes(body)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def recv_frame(reader: asyncio.StreamReader) -> bytes:
    """从 asyncio 流收一帧完整报文。"""
    head = await asyncio.wait_for(reader.readexactly(2), timeout=3.0)
    length = head[1]
    return head + await asyncio.wait_for(reader.readexactly(length + 2), timeout=3.0)


# ========== CRC16 (对照规格书样例) ==========

class TestCRC16:
    def test_login_ack_sample(self):
        """规格书 §6.2 登录应答样例: ...02 55031412782305 00 → CRC DA4C"""
        payload = bytes.fromhex("0000") + b"\x00\x02" + bytes.fromhex("55031412782305") + b"\x00"
        assert struct.pack("<H", crc16(payload)) == bytes.fromhex("DA4C")

    def test_crc_low_byte_first(self):
        payload = b"\x00\x00\x00\x02" + encode_bcd("550314127823 05".replace(" ", ""), 7) + b"\x00"
        frame = YKCFrame(seq=0, frame_type=0x02, body=encode_bcd("55031412782305", 7) + b"\x00").encode()
        assert frame[:1] == b"\x68"
        assert struct.unpack("<H", frame[-2:])[0] == crc16(payload)


# ========== 帧编解码 ==========

class TestYKCCodec:
    def test_roundtrip(self):
        frame = YKCFrame(seq=5, frame_type=YKCFrameType.LOGIN, body=build_login_body_v16()).encode()
        decoded = YKCCodec().decode(frame)
        assert decoded.seq == 5
        assert decoded.frame_type == YKCFrameType.LOGIN
        assert decoded.body == build_login_body_v16()

    def test_length_byte(self):
        """长度 = 序列号(2)+加密(1)+类型(1)+消息体(N)。"""
        body = build_login_body_v16()
        frame = YKCFrame(seq=0, frame_type=0x01, body=body).encode()
        assert frame[1] == 2 + 1 + 1 + len(body)  # 0x22 = 34, 同规格书样例

    def test_bad_start_rejected(self):
        with pytest.raises(YKCCodec.FrameError, match="起始标志"):
            YKCCodec().decode(b"\x00" * 20)

    def test_bad_crc_rejected(self):
        frame = bytearray(YKCFrame(seq=1, frame_type=0x03, body=b"\x01\x02").encode())
        frame[-1] ^= 0xFF
        with pytest.raises(YKCCodec.FrameError, match="CRC"):
            YKCCodec().decode(bytes(frame))

    def test_short_frame_rejected(self):
        with pytest.raises(YKCCodec.FrameError, match="过短"):
            YKCCodec().decode(b"\x68\x00")

    def test_extract_frames_sticky_and_garbage(self):
        f1 = YKCFrame(seq=1, frame_type=0x03, body=b"\x01\x02").encode()
        f2 = YKCFrame(seq=2, frame_type=0x03, body=b"\x03\x04").encode()
        partial = f2[:5]
        frames, rest = YKCCodec().extract_frames(b"\xFF\xFF" + f1 + f2 + partial)
        assert [f.seq for f in frames] == [1, 2]
        assert rest == partial

    def test_extract_frames_discards_bad_crc(self):
        bad = bytearray(YKCFrame(seq=1, frame_type=0x03, body=b"\x01").encode())
        bad[-2] ^= 0x01
        good = YKCFrame(seq=2, frame_type=0x03, body=b"\x02").encode()
        frames, _ = YKCCodec().extract_frames(bytes(bad) + good)
        assert [f.seq for f in frames] == [2]


# ========== 双格式识别 ==========

class TestDualFormat:
    def test_detect_v16_by_length_and_version_byte(self):
        assert detect_protocol_version(build_login_body_v16()) == 16

    def test_detect_v18_by_length(self):
        assert detect_protocol_version(build_login_body_v18()) == 18

    def test_decode_login_v16(self):
        login = decode_login(build_login_body_v16())
        assert login["sn"] == SN14
        assert login["sn_len"] == 7
        assert login["protocol_version"] == 16
        assert login["gun_count"] == 2
        assert login["pile_type"] == 0

    def test_decode_login_v18(self):
        login = decode_login(build_login_body_v18())
        assert login["sn"] == SN16
        assert login["sn_len"] == 8
        assert login["protocol_version"] == 18

    def test_sn_normalize_14_to_16(self):
        """14 位左补零到 16 位; Device.sn 两种形态都认。"""
        assert normalize_sn(SN14) == SN16
        assert normalize_sn(SN16) == SN16
        assert normalize_sn("abc") == "abc"
        assert normalize_sn("") == ""

    def test_device_sn_match_both_formats(self):
        """模拟 Device.sn=16位 / 14位 两种登记形态, 14/16 位登录编号都能匹配。"""
        for device_sn in (SN16, SN14):
            for login_sn in (SN14, SN16):
                assert normalize_sn(login_sn) == normalize_sn(device_sn) or login_sn == device_sn


# ========== 报文体解析 ==========

class TestBodyDecode:
    def test_decode_realtime(self):
        data = decode_realtime(build_realtime_body(SN14, 7), 7)
        assert data["sn"] == SN14
        assert data["status_name"] == "charging"
        assert data["voltage"] == pytest.approx(400.1)
        assert data["current"] == pytest.approx(150.0)
        assert data["power"] == pytest.approx(60.015, abs=1e-3)
        assert data["gun_temp"] == 60
        assert data["soc"] == 80
        assert data["max_battery_temp"] == 35
        assert data["energy"] == pytest.approx(1.234)
        assert data["amount"] == pytest.approx(2.0)
        assert data["has_fault"] is False

    def test_decode_realtime_v18(self):
        data = decode_realtime(build_realtime_body(SN16, 8), 8)
        assert data["sn"] == SN16
        assert data["voltage"] == pytest.approx(400.1)

    def test_decode_realtime_too_short(self):
        with pytest.raises(YKCCodec.FrameError, match="过短"):
            decode_realtime(b"\x00" * 10, 7)

    def test_cp56time2a_roundtrip(self):
        dt = datetime(2026, 9, 28, 12, 30, 45, 123000, tzinfo=timezone.utc)
        assert decode_cp56time2a(encode_cp56time2a(dt)) == dt

    def test_cp56time2a_decode_beijing_wallclock(self, monkeypatch):
        """卡 3364cef4: 桩按北京墙钟打包 CP56Time2a, decode 应得 06:30 UTC (aware)。"""
        monkeypatch.setattr("app.core.config.settings.YKC_DEVICE_TIMEZONE", "Asia/Shanghai")
        # 墙钟 2026-09-28 14:30:45.123 (毫秒域 = 45s123ms → 0xB79E)
        raw = bytes([0x43, 0xB0, 30, 14, (1 << 5) | 28, 9, 26])  # 周一
        assert decode_cp56time2a(raw) == datetime(
            2026, 9, 28, 6, 30, 45, 123000, tzinfo=timezone.utc
        )

    def test_cp56time2a_decode_configurable_tz(self, monkeypatch):
        """卡 3364cef4: settings 可配置, NY 墙钟 08:30 → 12:30 UTC。"""
        monkeypatch.setattr("app.core.config.settings.YKC_DEVICE_TIMEZONE", "America/New_York")
        raw = bytes([0x00, 0x00, 30, 8, 28, 9, 26])  # 2026-09-28 08:30:00.000 墙钟
        assert decode_cp56time2a(raw) == datetime(
            2026, 9, 28, 12, 30, 0, tzinfo=timezone.utc
        )

    def test_cp56time2a_decode_invalid_tz_fallback(self, monkeypatch):
        """卡 3364cef4: 非法时区配置回退 Asia/Shanghai。"""
        monkeypatch.setattr("app.core.config.settings.YKC_DEVICE_TIMEZONE", "Not/AZone")
        raw = bytes([0x00, 0x00, 30, 14, 28, 9, 26])  # 墙钟 14:30 → 06:30 UTC
        assert decode_cp56time2a(raw) == datetime(
            2026, 9, 28, 6, 30, 0, tzinfo=timezone.utc
        )

    def test_cp56time2a_encode_beijing_wallclock(self, monkeypatch):
        """卡 3364cef4: encode 应产出桩业务时区墙钟字段 (06:30 UTC → 14:30 上海墙钟)。"""
        monkeypatch.setattr("app.core.config.settings.YKC_DEVICE_TIMEZONE", "Asia/Shanghai")
        dt = datetime(2026, 9, 28, 6, 30, 45, 123000, tzinfo=timezone.utc)
        assert encode_cp56time2a(dt) == bytes([0x43, 0xB0, 30, 14, (1 << 5) | 28, 9, 26])

    def test_decode_transaction(self):
        txn = decode_transaction(build_transaction_body(SN14, 7), 7)
        assert txn["sn"] == SN14
        assert txn["gun_no"] == 1
        assert txn["total_energy"] == pytest.approx(1.234)
        assert txn["total_amount"] == pytest.approx(1.6)
        assert txn["meter_start"] == pytest.approx(1.0)
        assert txn["meter_stop"] == pytest.approx(2.234)
        assert txn["stop_reason"] == 0x41
        assert txn["vin"] == "LSVAA123456789012"
        assert txn["start_time"].year == 2026

    def test_decode_transaction_too_short(self):
        with pytest.raises(YKCCodec.FrameError, match="过短"):
            decode_transaction(b"\x00" * 20, 7)


# ========== TCP 登录握手 + 遥测归一化 + 交易记录 ==========

class TestYKCServerHandshake:
    def test_login_heartbeat_realtime_transaction_flow(self, monkeypatch):
        """完整链路: 登录→心跳→实时数据(归一化)→交易记录→确认。V1.6 帧。"""
        captured = []

        async def run():
            adapter = YKCAdapter(host="127.0.0.1", port=free_port())
            await adapter.initialize()

            async def fake_pipeline_execute(payload):
                captured.append(payload)

            adapter._pipeline.execute = fake_pipeline_execute
            monkeypatch.setattr(
                "app.gateway.ykc.find_device_by_sn",
                lambda sn: {"sn": SN16} if normalize_sn(sn) == SN16 else None,
            )
            monkeypatch.setattr("app.gateway.ykc.mark_device_online", lambda sn: True)
            await adapter.connect()
            try:
                reader, writer = await asyncio.open_connection(adapter.host, adapter.port)
                # 1. 登录
                writer.write(YKCFrame(seq=0, frame_type=0x01, body=build_login_body_v16()).encode())
                await writer.drain()
                ack = YKCCodec().decode(await recv_frame(reader))
                assert ack.frame_type == 0x02
                assert ack.seq == 0
                assert ack.body[-1] == YKCLoginResult.SUCCESS
                assert ack.body[:-1] == encode_bcd(SN14, 7)
                # 2. 心跳
                hb_body = encode_bcd(SN14, 7) + bytes([0x01, 0x00])
                writer.write(YKCFrame(seq=1, frame_type=0x03, body=hb_body).encode())
                await writer.drain()
                hb_ack = YKCCodec().decode(await recv_frame(reader))
                assert hb_ack.frame_type == 0x04
                assert hb_ack.body == encode_bcd(SN14, 7) + bytes([0x01, 0x00])
                # 3. 实时数据 → 归一化
                writer.write(YKCFrame(seq=2, frame_type=0x13, body=build_realtime_body(SN14, 7)).encode())
                await writer.drain()
                await asyncio.sleep(0.1)
                assert any(p.get("voltage") == pytest.approx(400.1) for p in captured)
                assert captured[0]["device_sn"] == SN16  # 归一化为 16 位
                assert captured[0]["protocol"] == "ykc"
                # 4. 交易记录 → 0x40 确认
                writer.write(YKCFrame(seq=3, frame_type=0x3B, body=build_transaction_body(SN14, 7)).encode())
                await writer.drain()
                txn_ack = YKCCodec().decode(await recv_frame(reader))
                assert txn_ack.frame_type == 0x40
                assert txn_ack.seq == 3
                assert txn_ack.body == encode_bcd("3" * 32, 16) + b"\x00"
                assert any(p.get("type") == "transaction" and p.get("energy") == pytest.approx(1.234) for p in captured)
                writer.close()
                await writer.wait_closed()
            finally:
                await adapter.shutdown()

        asyncio.run(run())

    def test_unregistered_pile_login_rejected(self, monkeypatch):
        """桩编号未注册 Device → 登录失败 0x01。"""
        async def run():
            adapter = YKCAdapter(host="127.0.0.1", port=free_port())
            await adapter.initialize()
            monkeypatch.setattr("app.gateway.ykc.find_device_by_sn", lambda sn: None)
            await adapter.connect()
            try:
                reader, writer = await asyncio.open_connection(adapter.host, adapter.port)
                writer.write(YKCFrame(seq=0, frame_type=0x01, body=build_login_body_v16()).encode())
                await writer.drain()
                ack = YKCCodec().decode(await recv_frame(reader))
                assert ack.frame_type == 0x02
                assert ack.body[-1] == YKCLoginResult.FAILURE
                writer.close()
                await writer.wait_closed()
            finally:
                await adapter.shutdown()

        asyncio.run(run())

    def test_v18_login_with_16_digit_sn(self, monkeypatch):
        """V1.8 帧: 8 字节桩编号, Device.sn=14位也能匹配 (归一化双向)。"""
        async def run():
            adapter = YKCAdapter(host="127.0.0.1", port=free_port())
            await adapter.initialize()
            # Device 按 14 位登记, 桩用 16 位 V1.8 帧登录
            monkeypatch.setattr(
                "app.gateway.ykc.find_device_by_sn",
                lambda sn: {"sn": SN14} if normalize_sn(sn) == normalize_sn(SN14) else None,
            )
            monkeypatch.setattr("app.gateway.ykc.mark_device_online", lambda sn: True)
            await adapter.connect()
            try:
                reader, writer = await asyncio.open_connection(adapter.host, adapter.port)
                writer.write(YKCFrame(seq=0, frame_type=0x01, body=build_login_body_v18(SN16)).encode())
                await writer.drain()
                ack = YKCCodec().decode(await recv_frame(reader))
                assert ack.body[-1] == YKCLoginResult.SUCCESS
                assert ack.body[:-1] == encode_bcd(SN16, 8)
                # V1.8 遥测帧
                writer.write(YKCFrame(seq=1, frame_type=0x03,
                                      body=encode_bcd(SN16, 8) + bytes([0x01, 0x00])).encode())
                await writer.drain()
                hb_ack = YKCCodec().decode(await recv_frame(reader))
                assert hb_ack.body == encode_bcd(SN16, 8) + bytes([0x01, 0x00])
                assert adapter.get_online_piles()[SN16]["version"] == 18
                writer.close()
                await writer.wait_closed()
            finally:
                await adapter.shutdown()

        asyncio.run(run())

    def test_business_frame_before_login_rejected(self, monkeypatch):
        """未登录先发业务帧: 不回复 (登录成功后才允许后续交互)。"""
        async def run():
            adapter = YKCAdapter(host="127.0.0.1", port=free_port())
            await adapter.initialize()
            monkeypatch.setattr("app.gateway.ykc.find_device_by_sn", lambda sn: {"sn": SN16})
            await adapter.connect()
            try:
                reader, writer = await asyncio.open_connection(adapter.host, adapter.port)
                writer.write(YKCFrame(seq=0, frame_type=0x13, body=build_realtime_body(SN14, 7)).encode())
                await writer.drain()
                with pytest.raises(asyncio.TimeoutError):
                    await recv_frame(reader)
                writer.close()
                await writer.wait_closed()
            finally:
                await adapter.shutdown()

        asyncio.run(run())


# ========== registry 接入 ==========

class TestRegistryIntegration:
    def test_ykc_auto_registered(self):
        registry = get_registry()
        assert registry.has_adapter("ykc")
        adapter_class = registry._protocol_classes["ykc"]
        assert adapter_class is YKCAdapter


# ========== settings 配置项 ==========

class TestSettings:
    def test_ykc_disabled_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.YKC_GATEWAY_ENABLED is False
        assert s.YKC_GATEWAY_PORT == 8767
        assert s.YKC_GATEWAY_HOST == "0.0.0.0"
