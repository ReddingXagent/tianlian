#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 端点业务测试 (卡 3a9d3d70; 死函数清扫卡 d9fe226f)

补全 app/ws/routes.py 12 个 /ws/v1/* 端点的业务覆盖。
鉴权拒绝/放行路径由 tests/ws/test_ws_auth.py (8 用例) 覆盖, 本文件聚焦:

  A. broadcast_workorder_to_all 单元测试 (mock ws_manager): 验证转发函数构造的
     WebSocketMessage 形状及对 ws_manager.broadcast_team_scoped 的精确路由。
     (卡 d9fe226f: 其余 4 个零调用 broadcast_* 死包装已删除)

  B. 端点集成测试 (httpx_ws 真实连接 + 真实 ws_manager): 验证握手 / 初始数据 /
     广播下发 / 客户端交互回执。端点连上后 push 循环会持续发 data 消息,
     用 _recv_until 过滤匹配, 不依赖严格时序。广播下发直接调 ws_manager 底层方法。
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from unittest.mock import AsyncMock

from app.main import app
from app.ws import ws_manager
from app.ws.routes import (
    broadcast_workorder_to_all,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(test_db):
    """每个测试独立 DB (覆盖 SessionLocal, seed admin)。WS 鉴权与端点 handler
    均经 db_module.SessionLocal 运行时读取, test_db 覆盖传播至本模块。"""
    pass


# ─── 辅助 ────────────────────────────────────────────────────────────

_TOKEN_CACHE = {"v": None}


def _token() -> str:
    """登录 admin 拿 JWT 并缓存。

    JWT 签名用固定 test SECRET_KEY, payload sub=admin; 每 test 新库均 seed
    active admin, 故同一 token 跨 test 仍通过鉴权, 缓存安全。
    """
    if _TOKEN_CACHE["v"] is None:
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert r.status_code == 200, r.text
        _TOKEN_CACHE["v"] = r.json()["data"]["token"]
    return _TOKEN_CACHE["v"]


async def _recv_until(ws, predicate, timeout: float = 8.0, max_msgs: int = 80):
    """循环 receive_json 直到 predicate(msg) 命中, 返回该 msg。

    端点 push 循环会插入 data 消息, 本函数把无关消息过滤掉找到目标。
    超时或连接被关闭 → 抛 asyncio.TimeoutError (调用方判定未收到)。
    """
    deadline = asyncio.get_event_loop().time() + timeout
    for _ in range(max_msgs):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError("recv_until 超时未匹配目标消息")
        try:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        except (asyncio.TimeoutError, Exception):
            raise asyncio.TimeoutError("连接关闭或等待超时, 未匹配目标消息")
        if predicate(msg):
            return msg
    raise asyncio.TimeoutError(f"扫描 {max_msgs} 条消息仍未匹配目标")


def _drain_connected(ws, channel: str, timeout: float = 8.0):
    """等待并校验 connected 握手 (并保证 client 已进入 ws_manager 连接池)。"""
    return _recv_until(
        ws,
        lambda m: m.get("type") == "connected" and m.get("channel") == channel,
        timeout=timeout,
    )


# ════════════════════════════════════════════════════════════════════
# A. broadcast_workorder_to_all 单元测试 (mock ws_manager)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_broadcast_workorder_to_all_message_shape(monkeypatch):
    """broadcast_workorder_to_all → 调 broadcast_team_scoped (卡 434f741a: 由
    broadcast_all 迁移至团队作用域广播), channel=workorders, team_id 缺省 None
    (语义=只发 admin; _broadcast_wo 调度前会显式传工单归属 team)。"""
    mock = AsyncMock()
    monkeypatch.setattr(ws_manager, "broadcast_team_scoped", mock)

    await broadcast_workorder_to_all({"wo_id": "WO-001", "status": "processing"})

    mock.assert_awaited_once()
    msg = mock.await_args.args[0]
    assert msg.type == "notification"
    assert msg.channel == "workorders"
    assert msg.payload == {"wo_id": "WO-001", "status": "processing"}
    # 未显式指定 team → None (只发 admin), 不再是 broadcast_all 全量
    assert mock.await_args.kwargs.get("team_id") is None


# ════════════════════════════════════════════════════════════════════
# B. 端点集成测试 (真实连接 + 真实 ws_manager)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_realtime_client_receives_global_broadcast():
    """连 /realtime 后, broadcast_all 全局广播应送达本客户端。

    覆盖核心业务契约: 客户端进入 ws_manager.all_connections 后, service 层调
    ws_manager.broadcast_all, 在场客户端收到 notification+alerts。
    """
    from app.ws.schemas import WebSocketMessage
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/realtime?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "realtime")
                await ws_manager.broadcast_all(
                    WebSocketMessage(
                        type="notification", channel="alerts", payload={"id": 99, "message": "广播告警"}
                    )
                )
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "alerts",
                )
                assert msg["payload"]["id"] == 99
                assert msg["payload"]["message"] == "广播告警"
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_dashboard_client_receives_global_broadcast():
    """连 /dashboard 的客户端能收到 broadcast_all 全局广播。"""
    from app.ws.schemas import WebSocketMessage
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/dashboard?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "dashboard")
                await ws_manager.broadcast_all(
                    WebSocketMessage(type="notification", channel="dashboard", payload={"k": "v"})
                )
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "dashboard",
                )
                assert msg["payload"] == {"k": "v"}
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_alerts_client_receives_channel_broadcast():
    """连 /alerts 的客户端收到 broadcast_channel("alerts") 频道广播
    (而非 broadcast_all), 验证频道级路由。"""
    from app.ws.schemas import WebSocketMessage
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/alerts?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "alerts")
                await ws_manager.broadcast_channel(
                    WebSocketMessage(type="notification", channel="alerts", payload={"level": "warning"}),
                    "alerts",
                )
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "alerts",
                )
                assert msg["payload"]["level"] == "warning"
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_devices_client_receives_broadcast():
    """连 /devices 的客户端能收到 broadcast_all 全局广播。"""
    from app.ws.schemas import WebSocketMessage
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/devices?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "devices")
                await ws_manager.broadcast_all(
                    WebSocketMessage(type="notification", channel="devices", payload={"online": 10})
                )
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "devices",
                )
                assert msg["payload"] == {"online": 10}
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_workorders_client_receives_workorder_broadcast(monkeypatch):
    """连 /workorders 后, broadcast_workorder_to_all 的工单广播应送达本客户端。

    预存缺陷隔离 (卡 a579f89e 已解一半): realtime_handler 原导入时绑定生产库
    SessionLocal (非 test_db), 已改经 db_module 运行时属性读取; 但 get_workorder_updates
    仅 catch (ValueError, TypeError) 不 catch LookupError, 生产库历史脏 status
    'ACCEPTED' → ORM LookupError; 且 workorders 端点 push 循环无 try/except → 连接
    断开。本测试聚焦广播路由 (broadcast_workorder_to_all 不走 handler), 故 stub 掉
    该查询方法保持连接存活。生产代码不在本卡修复范围。
    """
    from app.ws.realtime_handler import RealtimeDataHandler
    monkeypatch.setattr(
        RealtimeDataHandler, "get_workorder_updates", lambda self, team_id=None: {}
    )

    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/workorders?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "workorders")
                await broadcast_workorder_to_all({"wo_id": "WO-2026", "status": "completed"})
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "workorders",
                )
                assert msg["payload"]["wo_id"] == "WO-2026"
                assert msg["payload"]["status"] == "completed"
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_fleet_queue_receives_connected_and_initial_snapshot():
    """连 /fleet/queue/{id} → 收到 connected(fleet_queue) + 初始队列快照 data。"""
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/fleet/queue/5?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                handshake = await _drain_connected(ws, "fleet_queue")
                assert "station=5" in handshake.get("message", "")
                snapshot = await _recv_until(
                    ws, lambda m: m.get("type") == "data" and m.get("channel") == "fleet_queue"
                )
                # 空库快照: station_id 回显, total=0
                assert snapshot["payload"]["station_id"] == 5
                assert snapshot["payload"]["total"] == 0
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_fleet_v2g_receives_connected_and_initial_snapshot():
    """连 /fleet/v2g/{id} → 收到 connected(fleet_v2g) + 初始 V2G 快照 data。"""
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/fleet/v2g/9?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                handshake = await _drain_connected(ws, "fleet_v2g")
                assert "enterprise=9" in handshake.get("message", "")
                snapshot = await _recv_until(
                    ws, lambda m: m.get("type") == "data" and m.get("channel") == "fleet_v2g"
                )
                assert snapshot["payload"]["enterprise_id"] == 9
                assert snapshot["payload"]["total_plans"] == 0
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_digital_twin_global_receives_connected():
    """连 /digital-twin/global (纯 wait_disconnect, 无 push 循环) → 仅收到 connected。

    回归价值: 该端点曾因纯 sleep 循环无断连感知致连接泄漏, 已改 receive 传感器。
    本用例确认握手正常, 连接可正常建立。
    """
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/digital-twin/global?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "connected"
                    and m.get("channel") == "digital_twin",
                    timeout=5.0,
                )
                assert msg is not None
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_fleet_v2g_receives_channel_broadcast():
    """连 /fleet/v2g/{id} 的客户端收到 fleet_v2g 频道广播
    (验证 fleet_v2g 频道级路由 + payload 含 enterprise_id, 与 fleet_queue 对称)。

    注: /dashboard/large-screen 与 /digital-twin/device/{id} 两端点未覆盖 ——
    前者 WebSocketMessage.channel Literal (schemas.py) 不含 "large_screen",
    消息构造即抛 ValidationError 被吞, 客户端收不到任何消息; 后者为纯 send-only
    推送循环无 receive 断连传感器, teardown hang。均为生产预存缺陷, 不在本卡
    (仅测试, 红线禁改 app/) 修复范围。
    """
    from app.ws.schemas import WebSocketMessage
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/fleet/v2g/9?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "fleet_v2g")
                await ws_manager.broadcast_channel(
                    WebSocketMessage(
                        type="notification",
                        channel="fleet_v2g",
                        payload={"enterprise_id": 9, "total_plans": 3},
                    ),
                    "fleet_v2g",
                )
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "fleet_v2g"
                    and m.get("payload", {}).get("enterprise_id") == 9,
                )
                assert msg["payload"]["total_plans"] == 3
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_digital_twin_station_receives_connected_and_initial():
    """连 /digital-twin/station/{id} → 收到 connected(digital_twin, station_id) +
    initial_data。空库下站点不存在, initial_data payload 为 {"error": ...} 但消息必发。"""
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/digital-twin/station/777?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                handshake = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "connected"
                    and m.get("channel") == "digital_twin"
                    and m.get("station_id") == 777,
                )
                assert "777" in handshake.get("message", "")
                initial = await _recv_until(
                    ws, lambda m: m.get("type") == "initial_data", timeout=6.0
                )
                assert initial["channel"] == "digital_twin"
                assert initial["station_id"] == 777
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_fleet_queue_ping_returns_heartbeat():
    """连 /fleet/queue/{id} 后发 {type:ping} → 收到 heartbeat 回执 (心跳保活契约)。"""
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/fleet/queue/3?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "fleet_queue")
                await ws.send_json({"type": "ping"})
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "heartbeat"
                    and m.get("channel") == "fleet_queue",
                )
                assert msg["payload"] == {"ping": "pong"}
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_realtime_subscribe_returns_subscribed():
    """连 /realtime 后发 {type:subscribe, channel:alerts} → 收到 subscribed 回执。"""
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/realtime?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "realtime")
                await ws.send_json({"type": "subscribe", "channel": "alerts"})
                msg = await _recv_until(
                    ws, lambda m: m.get("type") == "subscribed"
                )
                assert msg["channel"] == "alerts"
                assert "alerts" in msg.get("message", "")
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_fleet_queue_receives_channel_broadcast():
    """连 /fleet/queue/{id} 的客户端收到 fleet_queue 频道广播
    (验证 fleet_queue 频道级路由 + payload 含 station_id)。"""
    from app.ws.schemas import WebSocketMessage
    transport = ASGIWebSocketTransport(app=app)
    url = f"ws://test/ws/v1/fleet/queue/5?token={_token()}"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                await _drain_connected(ws, "fleet_queue")
                await ws_manager.broadcast_channel(
                    WebSocketMessage(
                        type="notification",
                        channel="fleet_queue",
                        payload={"station_id": 5, "total": 2},
                    ),
                    "fleet_queue",
                )
                msg = await _recv_until(
                    ws,
                    lambda m: m.get("type") == "notification"
                    and m.get("channel") == "fleet_queue"
                    and m.get("payload", {}).get("station_id") == 5,
                )
                assert msg["payload"]["total"] == 2
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
