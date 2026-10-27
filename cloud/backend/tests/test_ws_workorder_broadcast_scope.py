#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS 工单广播团队作用域测试 (卡 434f741a — 跨团队泄露修复)

背景: workorders 包 11 处 _broadcast_wo 经 broadcast_workorder_to_all →
broadcast_all 无差别群发, payload 含 fault_desc/solution/engineer真名/reason,
团队B用户连任意 /ws/v1/* 频道即可收到团队A工单敏感事件 (HTTP 层已按卡
ed509541 跨团队404, 此WS广播面漏网)。

修复后: _broadcast_wo 调度前同步查 _workorder_team_id, 经
ws_manager.broadcast_team_scoped 过滤 — 团队匹配连接 + 平台 admin 连接收;
工单无归属站点 (team_id=None) → 只发 admin。

本文件覆盖三条连接 (teamA用户 / teamB用户 / admin) 的收发矩阵。
连接基建复用 tests/test_ws_team_scope.py 的 httpx_ws 模式。
"""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app
from app.ws.schemas import WebSocketMessage
from app.ws import ws_manager
from app.ws.routes import broadcast_workorder_to_all
from app.api.v1.workorders.helpers import _broadcast_wo

client = TestClient(app)

_BASE = "/api/v1"


@pytest.fixture(autouse=True)
def _setup(test_db):
    """每个测试独立 DB (覆盖 SessionLocal, seed admin)。WS 鉴权与
    _workorder_team_id 均经 db_module.SessionLocal 运行时读取, 覆盖可传播。"""
    pass


# ─── seed / token 辅助 (参照 test_ws_team_scope.py) ───────────────────

def _hash(pw: str) -> str:
    from tests._test_helpers import _fast_hash
    return _fast_hash(pw)


def _seed_env():
    """seed teamA/teamB + 各一团队级用户 + 各一站点; teamA 站点挂一张工单。

    工单只建 teamA 的 (广播事件模拟 teamA 工单流转); 另建一张无站点工单
    用于「无归属站点 → 只发 admin」分支。
    """
    from app.core.database import SessionLocal
    from app.models.station import Station, StationStatus
    from app.models.user import Team, TeamType, User, UserRole
    from app.models.workorder import WorkOrder, WorkOrderStatus

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        team_a = Team(name=f"广播A{suffix}", code=f"BA{suffix}", type=TeamType.OPS_COMPANY)
        team_b = Team(name=f"广播B{suffix}", code=f"BB{suffix}", type=TeamType.OPS_COMPANY)
        db.add_all([team_a, team_b])
        db.commit()

        user_a = User(username=f"ba_{suffix}", password_hash=_hash("pw123456"),
                      role=UserRole.OPERATOR, team_id=team_a.id, status="active")
        user_b = User(username=f"bb_{suffix}", password_hash=_hash("pw123456"),
                      role=UserRole.OPERATOR, team_id=team_b.id, status="active")
        db.add_all([user_a, user_b])
        db.commit()

        station_a = Station(name=f"广播A站{suffix}", code=f"BSA{suffix}",
                            team_id=team_a.id, status=StationStatus.NORMAL)
        db.add(station_a)
        db.commit()

        wo_a = WorkOrder(id=f"BA-WO-A-{suffix}", fault_desc=f"A工单{suffix}",
                         station_id=station_a.id, status=WorkOrderStatus.PENDING)
        wo_none = WorkOrder(id=f"BA-WO-NONE-{suffix}", fault_desc=f"无站点工单{suffix}",
                            station_id=None, status=WorkOrderStatus.PENDING)
        db.add_all([wo_a, wo_none])
        db.commit()

        return {"suffix": suffix, "team_a": team_a.id, "team_b": team_b.id,
                "user_a": user_a.username, "user_b": user_b.username,
                "wo_a": wo_a.id, "wo_none": wo_none.id}
    finally:
        db.close()


def _token_for(username: str) -> str:
    r = client.post(f"{_BASE}/auth/login",
                    data={"username": username, "password": "pw123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _admin_token() -> str:
    r = client.post(f"{_BASE}/auth/login",
                    data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


async def _recv_until(ws, predicate, timeout: float = 8.0):
    """循环 receive_json 直到 predicate 命中; 超时抛 asyncio.TimeoutError
    (调用方把「收不到」判定为过滤生效)。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError("recv_until 超时未匹配目标消息")
        try:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        except asyncio.TimeoutError:
            raise
        except Exception:
            raise asyncio.TimeoutError("连接关闭, 未匹配目标消息")
        if predicate(msg):
            return msg


def _wo_notification_pred(marker: str):
    return lambda m: (m.get("type") == "notification"
                      and m.get("channel") == "workorders"
                      and m.get("payload", {}).get("marker") == marker)


def _open_ws(transport_holder, token: str):
    """建立 /ws/v1/workorders 连接的 context manager 组合 (transport 需外部 aclose)。"""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        transport_holder["t"] = ASGIWebSocketTransport(app=app)
        ac = AsyncClient(transport=transport_holder["t"], base_url="http://test")
        async with ac:
            async with aconnect_ws(f"ws://test/ws/v1/workorders?token={token}", client=ac) as ws:
                yield ws

    return _ctx()


async def _assert_timeout(ws, marker: str, timeout: float = 3.0):
    """断言在 timeout 内收不到 marker 工单事件 (过滤生效)。"""
    with pytest.raises(asyncio.TimeoutError):
        await _recv_until(ws, _wo_notification_pred(marker), timeout=timeout)


# ════════════════════════════════════════════════════════════════════
# 1. 三连接矩阵: teamA 收 / admin 收 / teamB 收不到
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_team_scoped_broadcast_matrix(monkeypatch):
    """teamA 工单事件: teamA 用户收到, admin 收到, teamB 用户收不到。

    同时覆盖 _broadcast_wo 全链路 (team_id 同步查 + broadcast_team_scoped 过滤)。
    stub 掉 realtime_handler 的工单查询 (预存缺陷隔离, 同 test_ws_business.py)。
    """
    from app.ws.realtime_handler import RealtimeDataHandler
    monkeypatch.setattr(
        RealtimeDataHandler, "get_workorder_updates", lambda self, team_id=None: {}
    )

    env = _seed_env()
    marker = f"m{env['suffix']}"
    payload = {"id": env["wo_a"], "fault_desc": f"A故障{env['suffix']}",
               "status": "processing", "marker": marker}

    holders = [{"t": None}, {"t": None}, {"t": None}]
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        async with _open_ws(holders[0], _token_for(env["user_a"])) as ws_a, \
                   _open_ws(holders[1], _token_for(env["user_b"])) as ws_b, \
                   _open_ws(holders[2], _admin_token()) as ws_admin:
            # 等三条连接均握手完成并进入连接池
            for ws in (ws_a, ws_b, ws_admin):
                await _recv_until(
                    ws, lambda m: m.get("type") == "connected"
                    and m.get("channel") == "workorders", timeout=8.0,
                )
            assert ws_manager.get_channel_count("workorders") == 3

            # 走 _broadcast_wo 全链路 (同步上下文 + running loop → ensure_future 分支)
            _broadcast_wo(db, "dispatched", payload)

            # teamA 收到
            msg = await _recv_until(ws_a, _wo_notification_pred(marker))
            assert msg["payload"]["event"] == "dispatched"
            assert msg["payload"]["fault_desc"] == payload["fault_desc"]
            # admin 收到
            msg = await _recv_until(ws_admin, _wo_notification_pred(marker))
            assert msg["payload"]["id"] == env["wo_a"]
            # teamB 收不到 (timeout = pass)
            await _assert_timeout(ws_b, marker)
    finally:
        db.close()
        for h in holders:
            try:
                if h["t"] is not None:
                    await h["t"].aclose()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════
# 2. 工单无归属站点 → 只发 admin
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stationless_workorder_only_admin(monkeypatch):
    """无站点工单 (team_id=None): admin 收到, teamA/teamB 团队用户均收不到。"""
    from app.ws.realtime_handler import RealtimeDataHandler
    monkeypatch.setattr(
        RealtimeDataHandler, "get_workorder_updates", lambda self, team_id=None: {}
    )

    env = _seed_env()
    marker = f"n{env['suffix']}"
    payload = {"id": env["wo_none"], "status": "pending", "marker": marker}

    holders = [{"t": None}, {"t": None}, {"t": None}]
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        async with _open_ws(holders[0], _token_for(env["user_a"])) as ws_a, \
                   _open_ws(holders[1], _token_for(env["user_b"])) as ws_b, \
                   _open_ws(holders[2], _admin_token()) as ws_admin:
            for ws in (ws_a, ws_b, ws_admin):
                await _recv_until(
                    ws, lambda m: m.get("type") == "connected"
                    and m.get("channel") == "workorders", timeout=8.0,
                )

            _broadcast_wo(db, "created", payload)

            await _recv_until(ws_admin, _wo_notification_pred(marker))
            await _assert_timeout(ws_a, marker)
            await _assert_timeout(ws_b, marker)
    finally:
        db.close()
        for h in holders:
            try:
                if h["t"] is not None:
                    await h["t"].aclose()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════
# 3. 跨频道覆盖: teamB 连其他 /ws/v1/* 频道同样收不到 teamA 工单广播
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_other_channel_team_b_excluded(monkeypatch):
    """teamB 用户连 /ws/v1/realtime (广播走 all_connections 快照, 非频道限定):
    teamA 工单事件不送达。防止「换频道绕过过滤」的旁路。"""
    from app.ws.realtime_handler import RealtimeDataHandler
    monkeypatch.setattr(
        RealtimeDataHandler, "get_workorder_updates", lambda self, team_id=None: {}
    )
    monkeypatch.setattr(
        RealtimeDataHandler, "get_dashboard_stats", lambda self, team_id=None: {}
    )
    monkeypatch.setattr(
        RealtimeDataHandler, "get_device_status", lambda self, team_id=None: []
    )
    monkeypatch.setattr(
        RealtimeDataHandler, "get_alarm_updates", lambda self, team_id=None: []
    )

    env = _seed_env()
    marker = f"r{env['suffix']}"
    payload = {"id": env["wo_a"], "status": "processing", "marker": marker}

    transport_holder = {"t": None}
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        transport_holder["t"] = ASGIWebSocketTransport(app=app)
        async with AsyncClient(transport=transport_holder["t"], base_url="http://test") as ac:
            async with aconnect_ws(
                f"ws://test/ws/v1/realtime?token={_token_for(env['user_b'])}", client=ac
            ) as ws_b:
                await _recv_until(
                    ws_b, lambda m: m.get("type") == "connected"
                    and m.get("channel") == "realtime", timeout=8.0,
                )
                _broadcast_wo(db, "dispatched", payload)
                await _assert_timeout(ws_b, marker)
    finally:
        db.close()
        try:
            if transport_holder["t"] is not None:
                await transport_holder["t"].aclose()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
# 4. 单元级: broadcast_team_scoped 过滤语义 + broadcast_workorder_to_all 透传
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_broadcast_team_scoped_filters_by_metadata():
    """纯单元验证 broadcast_team_scoped: 只发 team 匹配 + admin(None) 连接;
    team_id=None 消息只发 admin。用真实 ws_manager + 注入假连接。"""
    import gc

    class _FakeWS:
        def __init__(self):
            self.sent = []
        async def send_json(self, data):
            self.sent.append(data)

    ws_a, ws_b, ws_admin = _FakeWS(), _FakeWS(), _FakeWS()
    msg = WebSocketMessage(type="notification", channel="workorders", payload={"k": "v"})
    try:
        ws_manager.all_connections.update({ws_a, ws_b, ws_admin})
        ws_manager.connection_metadata.update({
            ws_a: {"metadata": {"team_id": 1, "role": "operator"}},
            ws_b: {"metadata": {"team_id": 2, "role": "operator"}},
            ws_admin: {"metadata": {"team_id": None, "role": "admin"}},
        })
        await ws_manager.broadcast_team_scoped(msg, team_id=1)
        assert len(ws_a.sent) == 1 and ws_a.sent[0]["payload"] == {"k": "v"}
        assert len(ws_admin.sent) == 1
        assert ws_b.sent == []  # team 不匹配 → 零投递

        await ws_manager.broadcast_team_scoped(msg, team_id=None)
        assert len(ws_admin.sent) == 2   # admin 再收一条
        assert len(ws_a.sent) == 1       # team 连接不再收
    finally:
        ws_manager.all_connections.difference_update({ws_a, ws_b, ws_admin})
        for w in (ws_a, ws_b, ws_admin):
            ws_manager.connection_metadata.pop(w, None)
            ws_manager._last_heartbeat.pop(w, None)
        del ws_a, ws_b, ws_admin
        gc.collect()  # 假连接未 disconnect, 防句柄残留影响后续测试


@pytest.mark.asyncio
async def test_broadcast_workorder_to_all_routes_team_scope(monkeypatch):
    """broadcast_workorder_to_all(workorder_data, team_id) → 调
    broadcast_team_scoped(msg, team_id=...), 语义=卡 a579f89e HTTP 一致。"""
    from unittest.mock import AsyncMock
    mock = AsyncMock()
    monkeypatch.setattr(ws_manager, "broadcast_team_scoped", mock)

    await broadcast_workorder_to_all({"wo_id": "WO-1", "status": "processing"}, team_id=7)

    mock.assert_awaited_once()
    args = mock.await_args.args
    msg = args[0]
    assert msg.type == "notification"
    assert msg.channel == "workorders"
    assert msg.payload == {"wo_id": "WO-1", "status": "processing"}
    assert mock.await_args.kwargs.get("team_id") == 7
