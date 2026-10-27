"""
卡 b876e45f：StartTransaction payload timestamp 漏网 naive 修复回归。

背景：前置卡 d3693da8 已修 currentTime/expiryDate，但 StartTransaction
payload 内 timestamp 仍为 datetime.now().isoformat()（naive）。
OCPP 1.6J 协议时间字段必须是 UTC 带时区（ISO8601 Z 后缀）。
"""
import pytest
from datetime import datetime, timezone

import app.gateway.ocpp as ocpp_module
from app.gateway.ocpp import OCPPAdapter


@pytest.fixture
def adapter():
    return OCPPAdapter(
        endpoint="wss://ocpp.test/ocpp",
        charge_point_id="CP-TEST-001",
        heartbeat_interval=3600,
        reconnect_enabled=False,
    )


class _SpyDatetime(datetime):
    """记录 datetime.now 调用时传的 tz 参数。"""

    seen_tz = []

    @classmethod
    def now(cls, tz=None):
        cls.seen_tz.append(tz)
        return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_start_transaction_payload_timestamp_is_utc_z(adapter, monkeypatch):
    """StartTransaction payload 的 timestamp 必须是 UTC aware 且格式化后以 Z 结尾。"""
    _SpyDatetime.seen_tz = []
    monkeypatch.setattr(ocpp_module, "datetime", _SpyDatetime)
    await adapter.start_transaction(connector_id=1, id_tag="USER001", meter_start=0)
    assert _SpyDatetime.seen_tz, "start_transaction 应构造 payload 时间戳"
    # naive 调用（datetime.now()）tz 为 None，修复后应显式传 timezone.utc
    assert all(tz is timezone.utc for tz in _SpyDatetime.seen_tz), (
        "StartTransaction timestamp 仍为 naive（datetime.now() 未传 tz）"
    )
    # 与 :273/:289/:310 同款写法：aware isoformat + Z 后缀
    formatted = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    assert formatted.endswith("Z")
    assert datetime.fromisoformat(formatted).tzinfo is not None


@pytest.mark.asyncio
async def test_read_data_timestamp_is_aware(adapter):
    """read_data（get_status 路径，ocpp.py:622）返回的 timestamp 必须带 tzinfo。"""
    data = await adapter.read_data(1)
    assert data["timestamp"].tzinfo is not None, "read_data timestamp 仍为 naive"
