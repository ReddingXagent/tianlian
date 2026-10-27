#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS 发送背压防护 — 任务卡 faead57b

半死客户端 (TCP 存活但不读) 会让 send_json 无限阻塞:
websockets 库语义下 transport 缓冲满 → send 不抛错、无超时,
一个慢客户端即可卡死整个广播循环 / 心跳清理循环。

manager.py 修复: 全部 await 发送路径包 asyncio.wait_for(WS_SEND_TIMEOUT),
超时与普通异常同路处理 (warning + 短超时 close + disconnect)。

本文件用 FakeWebSocket 模拟慢客户端 (send_json 永久挂起), 验证:
  1. 慢客户端广播驱逐: 广播能返回, 快连接全收到, 慢连接被移除
  2. 心跳 ping 超时驱逐: 阻塞连接被清理, 正常连接收到 ping, 单轮不挂起
  3. send_personal_message 超时不挂起且清理连接
"""
import asyncio

import pytest

from app.ws import manager as ws_manager_mod
from app.ws.manager import WebSocketManager
from app.ws.schemas import WebSocketMessage, create_data_message


class FakeWS:
    """记录发送消息的假 WebSocket, 可模拟慢客户端 (send_json 挂起)。"""

    def __init__(self, *, send_delay=None, raise_on_send=False):
        self.sent = []
        self.send_delay = send_delay  # None=即时返回; float=挂起秒数
        self.raise_on_send = raise_on_send
        self.closed = None
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    async def send_json(self, data):
        if self.raise_on_send:
            raise RuntimeError("send failed")
        if self.send_delay is not None:
            await asyncio.sleep(self.send_delay)
        self.sent.append(data)


async def _register(mgr: WebSocketManager, ws: FakeWS, channel="realtime", **kwargs):
    """绕过 accept 网络路径, 直接登记连接 (等价 connect 完成后的状态)。"""
    mgr.channel_connections[channel].append(ws)
    station_id = kwargs.get("station_id")
    if station_id is not None:
        mgr.station_connections.setdefault(station_id, set()).add(ws)
    mgr.all_connections.add(ws)
    mgr.connection_metadata[ws] = {
        "channel": channel,
        "station_id": station_id,
        "metadata": kwargs.get("metadata", {}),
    }
    import datetime as dt
    mgr._last_heartbeat[ws] = dt.datetime.now(dt.timezone.utc).timestamp()


# ======================================================================
# 1. 慢客户端广播驱逐
# ======================================================================

class TestSlowClientBroadcastEviction:

    @pytest.mark.asyncio
    async def test_broadcast_channel_slow_client_evicted(self, monkeypatch):
        """3 连接入频道, 1 个 send_json 挂起 → 广播在超时内返回, 快连接全收到, 慢连接被移除。"""
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        fast1, slow, fast2 = FakeWS(), FakeWS(send_delay=999), FakeWS()
        for ws in (fast1, slow, fast2):
            await _register(mgr, ws, channel="realtime")

        msg = create_data_message(channel="realtime", payload={"k": 1})
        await asyncio.wait_for(mgr.broadcast_channel(msg, "realtime"), timeout=10)

        assert [msg.dict()] == fast1.sent
        assert [msg.dict()] == fast2.sent
        assert slow not in mgr.all_connections
        assert slow not in mgr.channel_connections["realtime"]
        assert slow.closed is not None
        # 快连接存活
        assert fast1 in mgr.all_connections and fast2 in mgr.all_connections

    @pytest.mark.asyncio
    async def test_broadcast_all_slow_client_evicted(self, monkeypatch):
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        fast, slow = FakeWS(), FakeWS(send_delay=999)
        for ws in (fast, slow):
            await _register(mgr, ws)

        msg = create_data_message(channel="realtime", payload={"k": 1})
        await asyncio.wait_for(mgr.broadcast_all(msg), timeout=10)
        assert len(fast.sent) == 1
        assert slow not in mgr.all_connections

    @pytest.mark.asyncio
    async def test_broadcast_station_slow_client_evicted(self, monkeypatch):
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        fast, slow = FakeWS(), FakeWS(send_delay=999)
        for ws in (fast, slow):
            await _register(mgr, ws, channel="digital_twin", station_id=7)

        msg = create_data_message(channel="digital_twin", payload={"k": 1})
        await asyncio.wait_for(mgr.broadcast_station(7, msg), timeout=10)
        assert len(fast.sent) == 1
        assert slow not in mgr.station_connections.get(7, set())

    @pytest.mark.asyncio
    async def test_broadcast_device_subscribers_slow_client_evicted(self, monkeypatch):
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        fast, slow = FakeWS(), FakeWS(send_delay=999)
        for ws in (fast, slow):
            await _register(mgr, ws, channel="digital_twin")
        mgr.subscribe_device(fast, 42)
        mgr.subscribe_device(slow, 42)

        msg = create_data_message(channel="digital_twin", payload={"k": 1})
        await asyncio.wait_for(mgr.broadcast_device_subscribers(42, msg), timeout=10)
        assert len(fast.sent) == 1
        assert mgr.get_device_subscriber_count(42) == 1

    @pytest.mark.asyncio
    async def test_broadcast_team_scoped_slow_client_evicted(self, monkeypatch):
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        fast = FakeWS()
        slow = FakeWS(send_delay=999)
        await _register(mgr, fast, metadata={"team_id": 3})
        await _register(mgr, slow, metadata={"team_id": 3})

        msg = create_data_message(channel="alerts", payload={"k": 1})
        await asyncio.wait_for(mgr.broadcast_team_scoped(msg, team_id=3), timeout=10)
        assert len(fast.sent) == 1
        assert slow not in mgr.all_connections


# ======================================================================
# 2. 心跳 ping 超时驱逐
# ======================================================================

class TestHeartbeatPingTimeout:

    @pytest.mark.asyncio
    async def test_heartbeat_ping_slow_client_evicted(self, monkeypatch):
        """阻塞 ping 的连接被清理, 正常连接收到 ping, 单轮心跳在超时内完成。"""
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        normal, blocking = FakeWS(), FakeWS(send_delay=999)
        for ws in (normal, blocking):
            await _register(mgr, ws)

        # 直接跑单轮逻辑 (不进 while True): 用内部等价序列
        await asyncio.wait_for(
            mgr._heartbeat_pass_once(), timeout=10
        )

        assert any(m.get("type") == "heartbeat" for m in normal.sent)
        assert blocking not in mgr.all_connections
        assert blocking not in mgr._last_heartbeat
        assert normal in mgr.all_connections


# ======================================================================
# 3. send_personal_message 超时
# ======================================================================

class TestSendPersonalMessageTimeout:

    @pytest.mark.asyncio
    async def test_send_personal_message_slow_client_cleaned(self, monkeypatch):
        monkeypatch.setattr(ws_manager_mod, "WS_SEND_TIMEOUT", 0.2)
        mgr = WebSocketManager()
        slow = FakeWS(send_delay=999)
        await _register(mgr, slow)

        msg = create_data_message(channel="realtime", payload={"k": 1})
        await asyncio.wait_for(mgr.send_personal_message(msg, slow), timeout=10)

        assert slow not in mgr.all_connections
        assert slow.closed is not None
