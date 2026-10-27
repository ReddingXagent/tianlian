"""SZBus 对时链时区测试 (卡 b4788b6b): CP56Time2A 对时字段=桩业务本地墙钟。

云端容器默认 UTC 部署, 旧实现 datetime.now() 把 UTC 墙钟打包下发,
桩被对慢上海 8h。修复后对时/记录时间统一走 _device_now() (Asia/Shanghai)。
"""
import struct
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import app.gateway.szbus as szbus_mod
from app.gateway.szbus import Cmd, SZBusFrame, SZBusGateway, decode_cp56time2a

# 固定时刻: 上海 2026-10-13 10:30 = UTC 02:30 (云端 UTC 容器同一瞬间)
UTC_NOW = datetime(2026, 10, 13, 2, 30, tzinfo=timezone.utc)
SH_NOW = UTC_NOW.astimezone(ZoneInfo("Asia/Shanghai"))


def _make_gw() -> SZBusGateway:
    gw = SZBusGateway("127.0.0.1", 8767)
    gw._seq = 100
    return gw


def _session() -> dict:
    return {
        "checked_in": True, "sn": "13800000100001",
        "version": 0x16, "manufacturer": 0x01,
        "device_id": szbus_mod.sn_to_device_id("13800000100001"),
    }


def _hhmm(cp56: bytes) -> tuple:
    _, mi, h, *_ = struct.unpack("<H5B", cp56[:7])
    return h, mi


# ----- _device_now helper -----

def test_device_now_uses_configured_shanghai_tz():
    now = szbus_mod._device_now()
    assert now.tzinfo is not None
    # 与同一瞬间的 UTC 时刻差 8h(上海无夏令时), 且与真实当前时刻接近
    assert now.utcoffset().total_seconds() == 8 * 3600
    drift = abs((now.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
    assert drift < 5


def test_device_now_follows_settings(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SZBUS_DEVICE_TIMEZONE", "UTC", raising=False)
    assert szbus_mod._device_now().utcoffset().total_seconds() == 0


def test_device_now_falls_back_on_bad_config(monkeypatch, caplog):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SZBUS_DEVICE_TIMEZONE", "Not/AZone", raising=False)
    now = szbus_mod._device_now()
    assert now.utcoffset().total_seconds() == 8 * 3600  # 回退上海


# ----- HEARTBEAT_ACK 对时路径 -----

async def test_heartbeat_ack_packs_shanghai_wallclock(monkeypatch):
    monkeypatch.setattr(szbus_mod, "_device_now", lambda: SH_NOW)
    gw = _make_gw()
    frame = SZBusFrame(1, 0x16, 0x01, _session()["device_id"], Cmd.HEARTBEAT, b"")
    reply = await gw._dispatch(frame, _session())
    assert reply.cmd == Cmd.HEARTBEAT_ACK
    # 上海墙钟 10:30, 而非 UTC 02:30
    assert _hhmm(reply.body) == (10, 30)


# ----- 0x12 工作参数对时路径 -----

def test_make_work_param_packs_shanghai_wallclock(monkeypatch):
    monkeypatch.setattr(szbus_mod, "_device_now", lambda: SH_NOW)
    gw = _make_gw()
    wp = gw._make_work_param(_session())
    assert wp.cmd == Cmd.WORK_PARAM
    assert _hhmm(wp.body) == (10, 30)
    # 对时域后的保活/超时/上报间隔不受影响
    assert wp.body[7:10] == bytes([30, 3, 30])


# ----- encode_cp56time2a 语义(aware 输入按自身墙钟字段打包, 函数禁改) -----

def test_encode_cp56time2a_aware_keeps_wall_fields():
    from app.gateway.szbus import encode_cp56time2a
    raw = encode_cp56time2a(SH_NOW)
    _, mi, h, d, mo, y = struct.unpack("<H5B", raw)
    assert (h, mi) == (10, 30) and (d, mo, y) == (13, 10, 26)
    # round-trip: naive 还原墙钟字段
    assert decode_cp56time2a(raw) == datetime(2026, 10, 13, 10, 30)
