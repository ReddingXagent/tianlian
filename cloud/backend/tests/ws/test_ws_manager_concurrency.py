#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app/ws/manager.py 并发竞态核实 + 生命周期补全 — 任务卡 936bb88a

═══ 核实结论 (Phase 1-3 根因调查 + 假设验证) ═══
任务卡担忧: disconnect(L130) 同步无锁改共享订阅字典, 与
broadcast_station / broadcast_device_subscribers (L271/280) 遍历并发时
疑似 "dict/set changed during iteration"。

经源码核实 + 本文件 asyncio.gather 并发回归测试验证:
  ❌ 竞态不存在 (已被前置卡 9a2ba0d0 的快照遍历缓解):
     - broadcast_channel        L265  list(...) 快照
     - broadcast_station        L274  set(...)   快照
     - broadcast_device_subscribers L283 set(...) 快照
     - broadcast_all            L291  list(...) 快照
     - disconnect 是纯同步 (无 await) → 相对其他 asyncio 任务原子执行
  故 disconnect 在 broadcast 的 await 让出期间修改 live 集合, 不影响 broadcast
  正在遍历的快照副本。本文件 Part A 的四个 asyncio.gather(disconnect ∥ broadcast)
  测试在当前源码下全绿 (GREEN), 证明竞态已缓解。

  ⚠️ 因此本卡不动源码 (铁律: 不修未坏之物)。本文件作用 = 锁定该安全行为:
     若后续有人 "优化" 掉 set(...)/list(...) 快照, Part A 测试立即转 RED。

═══ 前置卡已覆盖 (本文件不重复) ═══
  - 连接/断开/限流/心跳循环清理/广播(personal·channel·station·device·all)
    计数/订阅/状态           → tests/test_ws_coverage.py (卡 935c514b)
  - connect 限流竞态 + broadcast_channel/station 边遍历边断开 (SelfRemovingWS)
                            → tests/test_ws_coverage.py (卡 9a2ba0d0)
  - 鉴权失败(无token/无效/过期/禁用) → tests/ws/test_ws_auth.py

═══ 本卡新增 (真实缺口) ═══
  Part A: asyncio.gather 跨任务 disconnect ∥ broadcast (4 种广播, 强于 in-band)
  Part B: broadcast_device_subscribers 边遍历边断开 (前置卡漏测的第三种广播)
  Part C: heartbeat ↔ disconnect 生命周期双断开幂等
  Part D: 订阅去重 / 重连 (生命周期缺口)
"""
import asyncio
from datetime import datetime

import pytest

from app.ws import manager as ws_manager_mod
from app.ws.manager import WebSocketManager
from app.ws.schemas import WebSocketMessage, create_data_message


# ----------------------------------------------------------------------
# 测试替身
# ----------------------------------------------------------------------

class FakeWS:
    """记录发送消息的假 WebSocket, 可模拟 send/close 失败。"""

    def __init__(self, *, raise_on_send=False, raise_on_close=False):
        self.sent = []
        self.raise_on_send = raise_on_send
        self.raise_on_close = raise_on_close
        self.closed = None
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        if self.raise_on_close:
            raise RuntimeError("close failed")
        self.closed = (code, reason)

    async def send_json(self, data):
        if self.raise_on_send:
            raise RuntimeError("send failed")
        self.sent.append(data)


class YieldingFakeWS(FakeWS):
    """send_json 主动让出控制权 (await sleep(0)), 放大广播迭代间的并发窗口。

    关键: 只有 broadcast 在迭代中让出, disconnect 任务才有机会在迭代期间修改
    live 集合 → 才能暴露 "changed during iteration" 竞态。无快照时此替身必触发。
    """

    async def send_json(self, data):
        await asyncio.sleep(0)  # 强制调度切换, 让并发的 disconnect 插入
        if self.raise_on_send:
            raise RuntimeError("send failed")
        self.sent.append(data)


class SelfRemovingWS(FakeWS):
    """广播到达时把自己从 manager 断开 → 模拟广播中途连接失效 (in-band)。"""

    def __init__(self, mgr, **kwargs):
        super().__init__(**kwargs)
        self._mgr = mgr

    async def send_json(self, data):
        self._mgr.disconnect(self)  # 从正在遍历的 list/set 移除自身


# ======================================================================
# Part A: asyncio.gather 跨任务 disconnect ∥ broadcast (竞态核实)
#   每个测试: N 个连接 + 并发 disconnect 一半 + 多次 broadcast。
#   快照遍历 → GREEN; 若移除 set(...)/list(...) 快照 → RuntimeError (RED)。
# ======================================================================

class TestConcurrentDisconnectAndBroadcast:
    """跨任务并发: disconnect 与 broadcast 同时跑, 不得 'changed during iteration'。"""

    @pytest.mark.asyncio
    async def test_concurrent_disconnect_and_broadcast_channel(self):
        mgr = WebSocketManager()
        conns = [YieldingFakeWS() for _ in range(20)]
        for ws in conns:
            await mgr.connect(ws, channel="alerts")
        msg = create_data_message("alerts", {"x": 1})

        async def broadcast_many():
            for _ in range(20):
                await mgr.broadcast_channel(msg, "alerts")

        async def disconnect_half():
            for ws in conns[:10]:
                mgr.disconnect(ws)
                await asyncio.sleep(0)  # 让 broadcast 在迭代间插入

        # 不抛 RuntimeError
        await asyncio.gather(broadcast_many(), disconnect_half())

        assert all(w not in mgr.all_connections for w in conns[:10])
        assert all(w in mgr.all_connections for w in conns[10:])
        # 留存的一半至少收到一条广播
        assert any(w.sent for w in conns[10:])

    @pytest.mark.asyncio
    async def test_concurrent_disconnect_and_broadcast_station(self):
        mgr = WebSocketManager()
        conns = [YieldingFakeWS() for _ in range(20)]
        for ws in conns:
            await mgr.connect(ws, channel="digital_twin", station_id=5)
        msg = create_data_message("digital_twin", {"s": 1})

        async def broadcast_many():
            for _ in range(20):
                await mgr.broadcast_station(5, msg)

        async def disconnect_half():
            for ws in conns[:10]:
                mgr.disconnect(ws)
                await asyncio.sleep(0)

        await asyncio.gather(broadcast_many(), disconnect_half())

        assert all(w not in mgr.station_connections[5] for w in conns[:10])
        assert all(w in mgr.station_connections[5] for w in conns[10:])

    @pytest.mark.asyncio
    async def test_concurrent_disconnect_and_broadcast_device_subscribers(self):
        """任务卡明确点名 broadcast_device_subscribers (L280)。"""
        mgr = WebSocketManager()
        conns = [YieldingFakeWS() for _ in range(20)]
        for ws in conns:
            await mgr.connect(ws, channel="digital_twin")
            mgr.subscribe_device(ws, 11)
        msg = WebSocketMessage(type="update", channel="device", payload={"d": 1}, device_id=11)

        async def broadcast_many():
            for _ in range(20):
                await mgr.broadcast_device_subscribers(11, msg)

        async def disconnect_half():
            for ws in conns[:10]:
                mgr.disconnect(ws)
                await asyncio.sleep(0)

        await asyncio.gather(broadcast_many(), disconnect_half())

        assert mgr.get_device_subscriber_count(11) == 10
        assert all(w not in mgr.device_subscriptions[11] for w in conns[:10])
        assert all(w in mgr.device_subscriptions[11] for w in conns[10:])

    @pytest.mark.asyncio
    async def test_concurrent_disconnect_and_broadcast_all(self):
        mgr = WebSocketManager()
        conns = [YieldingFakeWS() for _ in range(20)]
        for ws in conns:
            await mgr.connect(ws, channel="realtime")
        msg = create_data_message("realtime", {"all": True})

        async def broadcast_many():
            for _ in range(20):
                await mgr.broadcast_all(msg)

        async def disconnect_half():
            for ws in conns[:10]:
                mgr.disconnect(ws)
                await asyncio.sleep(0)

        await asyncio.gather(broadcast_many(), disconnect_half())

        assert mgr.get_total_count() == 10
        assert all(w not in mgr.all_connections for w in conns[:10])

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_disconnect_broadcast_device(self):
        """订阅侧并发: 边 subscribe 边 disconnect 边 broadcast_device_subscribers。

        disconnect 内部 `for device_id in list(self.device_subscriptions.keys())`
        已用 list() 快照 keys; subscribe 新增 key 期间遍历不得崩。
        """
        mgr = WebSocketManager()
        ws_holder = []

        async def subscriber():
            for i in range(30):
                ws = YieldingFakeWS()
                ws_holder.append(ws)
                await mgr.connect(ws, channel="digital_twin")
                mgr.subscribe_device(ws, 11)
                await asyncio.sleep(0)

        async def disconnector():
            for _ in range(30):
                if ws_holder:
                    mgr.disconnect(ws_holder.pop())
                await asyncio.sleep(0)

        msg = WebSocketMessage(type="update", channel="device", payload={"d": 1}, device_id=11)

        async def broadcaster():
            for _ in range(30):
                await mgr.broadcast_device_subscribers(11, msg)

        # 三路并发: 不得抛 (KeyError / changed during iteration)
        await asyncio.gather(subscriber(), disconnector(), broadcaster())
        # 最终结构自洽: 订阅者集合 == 仍存活且订阅的连接
        live = {w for w in ws_holder if w in mgr.all_connections}
        assert mgr.device_subscriptions.get(11, set()) <= mgr.all_connections | live


# ======================================================================
# Part B: broadcast_device_subscribers 边遍历边断开 (前置卡漏测的第三种)
# ======================================================================

class TestBroadcastDeviceSubscribersMidIteration:
    """device 订阅集合在广播迭代中被 disconnect 修改 → 快照遍历保护。"""

    @pytest.mark.asyncio
    async def test_broadcast_device_survives_mid_iteration_disconnect(self):
        mgr = WebSocketManager()
        conns = [SelfRemovingWS(mgr) for _ in range(5)]
        for ws in conns:
            await mgr.connect(ws, channel="digital_twin")
            mgr.subscribe_device(ws, 11)

        msg = WebSocketMessage(type="update", channel="device", payload={"d": 1}, device_id=11)
        # 不抛 "Set changed size during iteration"
        await mgr.broadcast_device_subscribers(11, msg)
        # 5 个连接都在广播到达时被自身断开
        assert len(mgr.all_connections) == 0
        assert mgr.get_device_subscriber_count(11) == 0


# ======================================================================
# Part C: heartbeat ↔ disconnect 生命周期竞态核实
#   场景: _heartbeat_loop 判定 ws 超时 → await ws.close() 让出 →
#        handler finally 也 disconnect(ws) → 心跳 resume 再 disconnect(ws)。
#   disconnect 用 discard / pop(None) / .get 默认值 → 必须幂等, 不抛 KeyError。
# ======================================================================

class TestHeartbeatDisconnectLifecycle:
    """心跳踢线与 handler 并发 disconnect 的生命周期安全性。"""

    @pytest.mark.asyncio
    async def test_double_disconnect_concurrent_is_idempotent(self):
        """两个任务并发对同一 ws disconnect (心跳 + handler) → 幂等, 结构一致。"""
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin", station_id=3)
        mgr.subscribe_device(ws, 99)
        assert mgr.get_total_count() == 1

        async def disconnect_after_yield():
            await asyncio.sleep(0)
            mgr.disconnect(ws)

        # 两路并发 disconnect (asyncio 在 sync disconnect 边界串行化, 验证幂等契约)
        await asyncio.gather(disconnect_after_yield(), disconnect_after_yield())

        assert ws not in mgr.all_connections
        assert ws not in mgr.connection_metadata
        assert ws not in mgr._last_heartbeat
        assert ws not in mgr.station_connections.get(3, set())
        assert ws not in mgr.device_subscriptions.get(99, set())
        assert mgr.get_total_count() == 0

    @pytest.mark.asyncio
    async def test_heartbeat_loop_and_handler_disconnect_no_corruption(self, monkeypatch):
        """真实 _heartbeat_loop 踢线 + handler 并发 disconnect 不破坏内部结构。

        强制 ws 心跳超时 (timestamp 拨旧), 心跳循环将 close→disconnect;
        与此同时模拟 route handler 的 finally 也 disconnect 同一 ws。
        注: BUG-5 (channel="system" 心跳消息 ValidationError, 见 test_ws_coverage 头)
        使存活连接也被判 stale, 但不影响本测试 —— 无论触发路径, 双断开须幂等。
        """
        monkeypatch.setattr(ws_manager_mod, "WS_HEARTBEAT_INTERVAL", 0)
        monkeypatch.setattr(ws_manager_mod, "WS_HEARTBEAT_TIMEOUT", 10.0)
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="realtime", station_id=7)
        mgr._last_heartbeat[ws] = datetime.now().timestamp() - 1000  # 强制 stale

        async def handler_disconnect_during_heartbeat():
            await asyncio.sleep(0.1)  # 等心跳循环跑到 close→disconnect 之间
            mgr.disconnect(ws)

        await mgr.start_heartbeat()
        await asyncio.gather(
            asyncio.sleep(0.3),
            handler_disconnect_during_heartbeat(),
        )
        await mgr.stop_heartbeat()

        # 最终状态一致, 无残留, 无 KeyError 外溢
        assert ws not in mgr.all_connections
        assert ws not in mgr.connection_metadata
        assert ws not in mgr._last_heartbeat
        assert ws not in mgr.station_connections.get(7, set())


# ======================================================================
# Part D: 生命周期缺口 — 订阅去重 / 重连
# ======================================================================

class TestSubscriptionAndReconnect:
    """subscribe_device 去重 + connect→disconnect→reconnect 状态干净复用。"""

    @pytest.mark.asyncio
    async def test_subscribe_device_dedup(self):
        """同一 ws 重复订阅同一 device → set 去重, 订阅者计数仍为 1。"""
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin")
        mgr.subscribe_device(ws, 7)
        mgr.subscribe_device(ws, 7)  # 重复
        mgr.subscribe_device(ws, 7)  # 再重复
        assert mgr.get_device_subscriber_count(7) == 1
        assert len(mgr.device_subscriptions[7]) == 1

        # 不同 ws 订阅同 device → 计数 2
        ws2 = FakeWS()
        await mgr.connect(ws2, channel="digital_twin")
        mgr.subscribe_device(ws2, 7)
        assert mgr.get_device_subscriber_count(7) == 2

    @pytest.mark.asyncio
    async def test_reconnect_reuses_clean_state(self):
        """connect → disconnect → reconnect (同一 ws 对象), 不泄漏, 元数据重建。"""
        mgr = WebSocketManager()
        ws = FakeWS()

        r1 = await mgr.connect(ws, channel="realtime")
        assert r1["channel"] == "realtime"
        assert mgr.get_total_count() == 1
        assert ws in mgr._last_heartbeat

        mgr.disconnect(ws)
        assert mgr.get_total_count() == 0
        assert ws not in mgr._last_heartbeat

        # 重连: 同一 ws 对象换频道再连, 计数回到 1 (证明 disconnect 已彻底清理)
        r2 = await mgr.connect(ws, channel="alerts")
        assert r2["channel"] == "alerts"
        assert mgr.get_total_count() == 1
        assert mgr.connection_metadata[ws]["channel"] == "alerts"
        assert ws in mgr._last_heartbeat

        mgr.disconnect(ws)
        assert mgr.get_total_count() == 0

    @pytest.mark.asyncio
    async def test_reconnect_after_subscribe_cleanup(self):
        """重连前订阅过的设备, disconnect 后订阅关系清空, 重连不残留旧订阅。"""
        mgr = WebSocketManager()
        ws = FakeWS()
        await mgr.connect(ws, channel="digital_twin")
        mgr.subscribe_device(ws, 42)
        assert mgr.get_device_subscriber_count(42) == 1

        mgr.disconnect(ws)
        assert mgr.get_device_subscriber_count(42) == 0

        # 重连后旧订阅不复活
        await mgr.connect(ws, channel="digital_twin")
        assert mgr.get_device_subscriber_count(42) == 0
