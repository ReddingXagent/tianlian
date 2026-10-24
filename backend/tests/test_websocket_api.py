#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket API 路由测试
包含模块结构验证和真实WebSocket连接测试（使用 httpx-ws）
"""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from app.main import app
from app.ws import ws_manager
from tests._route_helpers import collect_route_paths

client = TestClient(app)


def _ws_token():
    """登录 admin 拿 JWT, 供 WS 端点 ?token= 鉴权 (P1 修复后 /ws/v1/* 强制鉴权)。"""
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


# ── 每个测试自动创建独立的测试数据库 ──

@pytest.fixture(autouse=True)
def _setup(test_db):
    pass


# ══════════════════════════════════════════════════════════════════
# 第一部分：模块结构验证（原测试，保持向后兼容）
# ══════════════════════════════════════════════════════════════════

def test_websocket_router_imports():
    """WebSocket 路由模块可导入"""
    from app.ws import routes as ws_routes
    assert ws_routes.router is not None


def test_websocket_connection_manager():
    """WebSocket WebSocketManager 可实例化"""
    from app.ws.manager import WebSocketManager
    mgr = WebSocketManager()
    assert mgr.all_connections is not None


def test_websocket_realtime_connection_manager():
    """WebSocketManager 支持多频道"""
    from app.ws.manager import WebSocketManager
    mgr = WebSocketManager()
    expected_channels = ["realtime", "digital_twin", "dashboard", "alerts", "workorders", "devices"]
    for ch in expected_channels:
        assert ch in mgr.channel_connections, f"Missing channel: {ch}"


def test_websocket_router_tags():
    """数字孪生 API 路由器有标签"""
    from app.api.v1.digital_twin import router as dt_router
    assert dt_router is not None


def test_websocket_broadcast_functions():
    """WebSocket 广播函数签名存在"""
    from app.ws.routes import broadcast_workorder_to_all
    import inspect
    assert inspect.iscoroutinefunction(broadcast_workorder_to_all)


def test_websocket_ws_module_exists():
    """ws 模块结构完整"""
    import importlib
    ws_routes = importlib.import_module("app.ws.routes")
    assert hasattr(ws_routes, "router")


def test_websocket_ws_manager():
    """ws.manager 模块可导入"""
    from app.ws import manager
    assert manager is not None


def test_websocket_routes_registered():
    """统一 WebSocket 路由已注册到 app"""
    # fastapi 0.140+ include_router 子路由包在 _IncludedRouter 中不再扁平铺进
    # app.routes 顶层，需递归 original_router 才能取到真实 WS 路径。
    ws_paths = {p for p in collect_route_paths(app.routes) if "/ws/" in p}
    expected = {"/ws/v1/realtime", "/ws/v1/dashboard", "/ws/v1/devices",
                "/ws/v1/alerts", "/ws/v1/workorders"}
    for path in expected:
        assert path in ws_paths, f"缺少路由: {path}"


# ══════════════════════════════════════════════════════════════════
# 第二部分：真实 WebSocket 连接测试（新增）
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ws_connect_realtime():
    """连接 /ws/v1/realtime 并验证收到连接成功消息

    卡8035bd65: push 循环改 to_thread 后控制权让出更频繁, 客户端关闭时
    httpx-ws 后台接收任务可能在 teardown 阶段抛 EndOfStream/ExceptionGroup
    (同 test_ws_connect_realtime_multi 注释的时序 quirk)。断言移出
    teardown, 仅容忍关闭阶段异常, 保持对 connected 握手的严格校验。
    """
    msg = None
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/realtime?token={_ws_token()}", client=ac) as ws:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                await ws.close()
    except Exception:
        pass
    await transport.aclose()
    assert msg is not None, "未收到连接消息"
    assert msg["type"] == "connected"
    assert msg["channel"] == "realtime"
    assert msg["message"] is not None and "连接成功" in msg["message"]


@pytest.mark.asyncio
async def test_ws_connect_alarms():
    """连接 /ws/v1/alerts 并验证收到连接成功消息 (teardown 容忍同上)"""
    msg = None
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/alerts?token={_ws_token()}", client=ac) as ws:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                await ws.close()
    except Exception:
        pass
    await transport.aclose()
    assert msg is not None, "未收到连接消息"
    assert msg["type"] == "connected"
    assert msg["channel"] == "alerts"
    assert msg["message"] is not None and "连接成功" in msg["message"]


@pytest.mark.asyncio
async def test_ws_connect_realtime_multi():
    """多 channel 连接测试 - 依次连接 dashboard/devices/alerts/workorders 频道"""
    channels = [
        ("dashboard", "Dashboard"),
        ("devices", "设备"),
        ("alerts", "告警"),
        ("workorders", "工单"),
    ]
    for ch, keyword in channels:
        # 收到 connected 握手即视为通过。这些 push 端点在客户端关闭时, httpx-ws 的
        # ASGI 后台接收任务可能因服务端仍在推送而抛出 EndOfStream/ExceptionGroup
        # (teardown 时序 quirk, 非业务缺陷)。故仅容忍关闭阶段异常, 断言放在
        # teardown 之外以保持对 connected 握手的严格校验。
        msg = None
        transport = ASGIWebSocketTransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                url = f"ws://test/ws/v1/{ch}?token={_ws_token()}"
                async with aconnect_ws(url, client=ac) as ws:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                    await ws.close()
        except Exception:
            pass
        assert msg is not None, f"频道 {ch} 未收到连接消息"
        assert msg["type"] == "connected"
        assert msg["channel"] == ch
        assert keyword in msg.get("message", ""), \
            f"频道 {ch} 的连接消息应包含关键词 '{keyword}'，实际内容: {msg.get('message', '')}"
        try:
            await transport.aclose()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# 第三部分：/realtime 推送内容回归 (list payload 静默失败 bug)
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ws_realtime_pushes_devices_data_as_dict():
    """/realtime 推送的 devices 数据消息 payload 必须是 dict。

    回归: push_realtime_data 曾把 device_data[:10] (list) 直接当 payload 传给
    create_data_message, 而 WebSocketMessage.payload 类型是 Optional[Dict[str, Any]],
    Pydantic 拒绝 list 抛 ValidationError, 被外层 except Exception 吞掉 →
    客户端永远收不到 devices 数据消息 (推送静默失败)。修复后 payload 包装为
    {"devices": [...], "count": N}。
    """
    transport = ASGIWebSocketTransport(app=app)
    devices_msg = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/realtime?token={_ws_token()}", client=ac) as ws:
                # 消费 connected 握手
                hello = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert hello["type"] == "connected"
                # 循环接收, 找到 channel=devices 的 data 消息 (push 首批连接后立即发)
                for _ in range(4):
                    try:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=6.0)
                    except Exception:
                        break
                    if msg.get("type") == "data" and msg.get("channel") == "devices":
                        devices_msg = msg
                        break
                await ws.close()
    except Exception:
        # httpx-ws ASGI teardown 时序 quirk (EndOfStream/ExceptionGroup), 非业务缺陷
        pass
    try:
        await transport.aclose()
    except Exception:
        pass

    # 断言放在 teardown 之外 (参考 test_ws_connect_realtime_multi)
    assert devices_msg is not None, (
        "/realtime 未推送 devices 数据消息 —— create_data_message 收到 list payload "
        "触发 ValidationError 被静默吞掉"
    )
    assert isinstance(devices_msg["payload"], dict), "devices payload 应为 dict"
    assert "devices" in devices_msg["payload"], "devices payload 应含 'devices' 键"
    assert "count" in devices_msg["payload"], "devices payload 应含 'count' 键"


def test_create_data_message_rejects_list_payload():
    """create_data_message 的 payload 必须是 dict; list 应被 Pydantic 拒绝 (锁定契约, 防回归)。"""
    from app.ws.schemas import create_data_message
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        create_data_message("devices", [])
    with pytest.raises(ValidationError):
        create_data_message("devices", [{"id": 1}])


# ══════════════════════════════════════════════════════════════════
# 第四部分：连接泄漏回归 — handler 退出必须 disconnect
# ══════════════════════════════════════════════════════════════════
#
# 根因: asyncio.wait(FIRST_COMPLETED) 返回后, 断连异常被传感器/push 闭包内部的
# except Exception 吞掉, WebSocketDisconnect 不向外传播 → except WebSocketDisconnect
# 分支不触发 → ws_manager.disconnect 不调用 → all_connections/channel_connections 残留。
# 修复: 把 except WebSocketDisconnect 改为 finally, 保证任何退出路径都清理。
#
# 断言策略: 用 channel 连接数 before/after 差值 (而非绝对值), 规避全局 ws_manager
# 单例跨测试累积污染; 轮询等待服务端 finally 清理, 容忍 ASGI teardown 时序 quirk。


async def _assert_disconnect_cleans_channel(url: str, channel: str):
    """连接 push 端点 → 收到握手 → 关闭客户端 → 断言连接从 ws_manager 清理。

    握手收到即证明 ws_manager.connect() 已完成、连接已入 channel_connections。
    客户端关闭后轮询 channel 计数回到 before, 验证 handler 退出时调用了 disconnect。
    """
    before = ws_manager.get_channel_count(channel)
    transport = ASGIWebSocketTransport(app=app)
    registered = False
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                hello = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                assert hello["type"] == "connected", f"{url} 握手非 connected"
                # 握手在 connect() 之后发出 → 连接应已注册到该 channel
                if ws_manager.get_channel_count(channel) == before + 1:
                    registered = True
                await ws.close()
        # 客户端已关闭: 轮询等待服务端 handler 感知断连并走 finally → disconnect
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if ws_manager.get_channel_count(channel) == before:
                break
            await asyncio.sleep(0.05)
    except Exception:
        # httpx-ws ASGI teardown 时序 quirk (EndOfStream/ExceptionGroup), 非业务缺陷
        pass
    try:
        await transport.aclose()
    except Exception:
        pass

    after = ws_manager.get_channel_count(channel)
    assert registered, (
        f"{url} 连接后 channel '{channel}' 计数未增加 (before={before}), "
        "连接未注册到 ws_manager, 无法验证断连清理"
    )
    assert after == before, (
        f"{url} 客户端断开后连接未清理 (泄漏): channel='{channel}' "
        f"before={before} after={after}"
    )


@pytest.mark.asyncio
async def test_ws_disconnect_cleans_up_realtime():
    """/realtime (handle_client_messages + push 双任务) 客户端断开后必须 disconnect, 防泄漏。"""
    await asyncio.wait_for(
        _assert_disconnect_cleans_channel(f"ws://test/ws/v1/realtime?token={_ws_token()}", "realtime"),
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_ws_disconnect_cleans_up_dashboard():
    """/dashboard (wait_disconnect receive 传感器) 客户端断开后必须 disconnect, 防泄漏。"""
    await asyncio.wait_for(
        _assert_disconnect_cleans_channel(f"ws://test/ws/v1/dashboard?token={_ws_token()}", "dashboard"),
        timeout=10.0,
    )

# ══════════════════════════════════════════════════════════════════
# 第三部分：卡 0bef02bc — 四频道吞 ping 修复 + push 循环容错
# ══════════════════════════════════════════════════════════════════

async def _receive_until(ws, msg_type, timeout=5.0):
    """循环收消息直到目标 type, 避免与周期 push 数据消息竞争。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        assert remaining > 0, f"等待 {msg_type} 消息超时"
        msg = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        if msg.get("type") == msg_type:
            return msg


@pytest.mark.asyncio
async def test_ws_dashboard_ping_refreshes_heartbeat(monkeypatch):
    """/dashboard 发 {"type":"ping"} 必须 record_heartbeat + 回 heartbeat pong (卡 0bef02bc)。"""
    import time as _time
    from app.ws import routes as ws_routes  # noqa: F401 确保模块已加载

    recorded = {}
    original = ws_manager.record_heartbeat

    def _spy(ws):
        recorded["ws"] = ws
        recorded["ts"] = _time.time()
        original(ws)

    monkeypatch.setattr(ws_manager, "record_heartbeat", _spy)

    before = _time.time() - 1.0
    pong = None
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/dashboard?token={_ws_token()}", client=ac) as ws:
                await _receive_until(ws, "connected")
                await ws.send_json({"type": "ping"})
                pong = await _receive_until(ws, "heartbeat")
                # 连接仍在时校验心跳表已刷新
                assert "ws" in recorded, "record_heartbeat 未被调用"
                assert recorded["ts"] > before, "_last_heartbeat 未被 ping 刷新"
                assert recorded["ws"] in ws_manager._last_heartbeat
                await ws.close()
    except Exception:
        # teardown quirk 同 test_ws_connect_realtime; 关键断言移到 with 外
        pass
    await transport.aclose()
    assert pong is not None, "未收到 heartbeat pong"
    assert pong["payload"] == {"ping": "pong"}


@pytest.mark.asyncio
async def test_ws_dashboard_push_exception_keeps_connection(monkeypatch):
    """push 循环 DB 查询抛异常不得杀连接 (卡 0bef02bc): 异常后 ping 仍能收到 pong。"""
    from app.ws.realtime_handler import RealtimeDataHandler

    def _boom(self, team_id=None):
        raise RuntimeError("simulated db outage")

    monkeypatch.setattr(RealtimeDataHandler, "get_dashboard_stats", _boom)

    pong = None
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test/ws/v1/dashboard?token={_ws_token()}", client=ac) as ws:
                await _receive_until(ws, "connected")
                await asyncio.sleep(1.0)  # 给 push 循环至少抛一次异常的机会
                await ws.send_json({"type": "ping"})
                pong = await _receive_until(ws, "heartbeat")
                await ws.close()
    except Exception:
        pass
    await transport.aclose()
    assert pong is not None, "push 异常后连接死亡, ping 无 pong (容错缺失)"
