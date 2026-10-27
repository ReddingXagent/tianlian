#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 聚合频道团队作用域测试 (卡 a579f89e — 水平越权修复)

背景: /ws/v1 的 6 个聚合端点 (realtime/dashboard/devices/alerts/workorders/
dashboard/large-screen) 此前认证后推送【全平台】聚合数据, 任意团队级用户
可读取他人团队设备/站点/告警/工单。修复后 (app/ws/realtime_handler.py +
app/ws/routes.py): 团队级用户只收本 team 数据, 平台管理员收全量, 语义与
HTTP /stats/* team_scope (卡 820cf187) 一致 — 范围过滤而非拒绝访问。

连接基建复用 tests/test_ws_scope_e2ad0b7d.py 的 httpx_ws 模式。
"""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app

client = TestClient(app)

_BASE = "/api/v1"


@pytest.fixture(autouse=True)
def _setup(test_db):
    """每个测试独立 DB (覆盖 SessionLocal, seed admin)。WS 层经
    db_module.SessionLocal 运行时读取, test_db 覆盖传播至 handler。"""
    pass


# ─── seed 辅助 ────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    from tests._test_helpers import _fast_hash
    return _fast_hash(pw)


def _seed_env():
    """seed teamA/teamB 各一站点/设备/告警/工单 + teamA 团队级用户。

    命名带唯一 suffix, 断言「推送数据不含 B 团队资源」按名字过滤判别。
    """
    from app.core.database import SessionLocal
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.device import Device, DeviceType
    from app.models.station import Station, StationStatus
    from app.models.user import Team, TeamType, User, UserRole
    from app.models.workorder import WorkOrder, WorkOrderStatus

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        team_a = Team(name=f"聚合A{suffix}", code=f"WA{suffix}", type=TeamType.OPS_COMPANY)
        team_b = Team(name=f"聚合B{suffix}", code=f"WB{suffix}", type=TeamType.OPS_COMPANY)
        db.add_all([team_a, team_b])
        db.commit()

        user_a = User(
            username=f"wa_{suffix}", password_hash=_hash("pw123456"),
            role=UserRole.OPERATOR, team_id=team_a.id, status="active",
        )
        db.add(user_a)
        db.commit()

        station_a = Station(name=f"聚合A站{suffix}", code=f"WSA{suffix}", team_id=team_a.id, status=StationStatus.NORMAL)
        station_b = Station(name=f"聚合B站{suffix}", code=f"WSB{suffix}", team_id=team_b.id, status=StationStatus.NORMAL)
        db.add_all([station_a, station_b])
        db.commit()

        device_a = Device(sn=f"WSNA{suffix}", name=f"聚合A桩{suffix}", code=f"WDA{suffix}",
                          type=DeviceType.CHARGER_DC, station_id=station_a.id,
                          status="online", health_score=90)
        device_b = Device(sn=f"WSNB{suffix}", name=f"聚合B桩{suffix}", code=f"WDB{suffix}",
                          type=DeviceType.CHARGER_DC, station_id=station_b.id,
                          status="online", health_score=60)
        db.add_all([device_a, device_b])
        db.commit()

        db.add_all([
            Alarm(device_id=device_a.id, station_id=station_a.id, level=AlarmLevel.WARNING,
                  status=AlarmStatus.ACTIVE, content=f"A告警{suffix}"),
            Alarm(device_id=device_b.id, station_id=station_b.id, level=AlarmLevel.CRITICAL,
                  status=AlarmStatus.ACTIVE, content=f"B告警{suffix}"),
            WorkOrder(id=f"WA-WO-A-{suffix}", fault_desc=f"A工单{suffix}", station_id=station_a.id,
                      device_id=device_a.id, status=WorkOrderStatus.PENDING, creator_id=user_a.id),
            WorkOrder(id=f"WA-WO-B-{suffix}", fault_desc=f"B工单{suffix}", station_id=station_b.id,
                      device_id=device_b.id, status=WorkOrderStatus.PENDING, creator_id=user_a.id),
        ])
        db.commit()

        return {"suffix": suffix, "user_a": user_a.username,
                "station_a": station_a.id, "station_b": station_b.id,
                "device_a": device_a.id, "device_b": device_b.id}
    finally:
        db.close()


def _token_for(username: str, password: str = "pw123456") -> str:
    r = client.post(f"{_BASE}/auth/login", data={"username": username, "password": password})
    if r.status_code == 200:
        data = r.json().get("data", {})
        tok = data.get("token") or data.get("access_token")
        if tok:
            return tok
    from datetime import datetime, timedelta, timezone
    from app.core.jwt_utils import encode_token
    return encode_token({
        "sub": username, "role": "operator",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    })


def _admin_token() -> str:
    r = client.post(f"{_BASE}/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


async def _collect(url: str, token: str, want_channels: list, timeout: float = 8.0) -> dict:
    """连接聚合频道, 收到 connected 后按 channel 收集首条 data 消息, 返回 {channel: payload}。

    推送消息统一 type="data", 靠 channel 区分 (见 app/ws/schemas.create_data_message)。
    """
    got = {}
    remaining = set(want_channels)
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"{url}?token={token}", client=ac) as ws:
                first = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                assert first.get("type") == "connected", first
                deadline = asyncio.get_event_loop().time() + timeout
                while remaining:
                    msg = await asyncio.wait_for(
                        ws.receive_json(), timeout=max(0.1, deadline - asyncio.get_event_loop().time())
                    )
                    if msg.get("type") == "data" and msg.get("channel") in remaining:
                        got[msg["channel"]] = msg.get("payload")
                        remaining.discard(msg["channel"])
                await ws.close()
    except Exception:
        # teardown 阶段 httpx-ws 后台任务可能抛 EndOfStream (同 test_websocket_api 时序 quirk),
        # 只要目标消息已收齐就不影响断言
        if remaining:
            raise
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
    return got


# ════════════════════════════════════════════════════════════════════
# 1. 团队级用户 → 推送只含本 team
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_team_user_dashboard_scoped():
    """realtime 频道 dashboard 聚合: A 用户只见 A 站/桩/告警/工单计数"""
    env = _seed_env()
    data = await _collect("/ws/v1/realtime", _token_for(env["user_a"]), ["dashboard"])
    d = data["dashboard"]
    assert d["stations"]["total"] == 1, d
    assert d["devices"]["total"] == 1, d
    assert d["alarms"]["active"] == 1, d          # 只有 A 告警
    assert d["alarms"]["critical"] == 0, d        # B 的 critical 不可见
    assert d["workorders"]["pending"] == 1, d


@pytest.mark.asyncio
async def test_team_user_devices_scoped():
    """devices 频道: A 用户设备列表不含 B 设备名"""
    env = _seed_env()
    data = await _collect("/ws/v1/devices", _token_for(env["user_a"]), ["devices"])
    names = [dv["name"] for dv in data["devices"]["devices"]]
    assert f"聚合A桩{env['suffix']}" in names, names
    assert f"聚合B桩{env['suffix']}" not in names, names


@pytest.mark.asyncio
async def test_team_user_alarms_scoped():
    """alerts 频道: A 用户告警样本不含 B 告警内容/站点名"""
    env = _seed_env()
    data = await _collect("/ws/v1/alerts", _token_for(env["user_a"]), ["alerts"])
    stations = [al.get("station") for al in data["alerts"]["alarms"]]
    assert f"聚合A站{env['suffix']}" in stations, stations
    assert f"聚合B站{env['suffix']}" not in stations, stations


@pytest.mark.asyncio
async def test_team_user_workorders_scoped():
    """workorders 频道: A 用户工单计数只算本 team"""
    env = _seed_env()
    data = await _collect("/ws/v1/workorders", _token_for(env["user_a"]), ["workorders"])
    assert data["workorders"]["pending"] == 1, data


@pytest.mark.asyncio
async def test_team_user_dashboard_channel_scoped():
    """dashboard 频道: 与 realtime 同 handler, 同样被过滤"""
    env = _seed_env()
    data = await _collect("/ws/v1/dashboard", _token_for(env["user_a"]), ["dashboard"])
    assert data["dashboard"]["devices"]["total"] == 1, data


@pytest.mark.asyncio
async def test_team_user_large_screen_scoped():
    """large-screen 频道: 聚合推送同样被过滤"""
    env = _seed_env()
    data = await _collect(
        "/ws/v1/dashboard/large-screen", _token_for(env["user_a"]), ["large_screen"]
    )
    assert data["large_screen"]["stations"]["total"] == 1, data


# ════════════════════════════════════════════════════════════════════
# 2. 平台管理员 → 全量
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_admin_sees_all():
    """admin 连 realtime: 看到两 team 全部资源"""
    env = _seed_env()
    data = await _collect("/ws/v1/realtime", _admin_token(), ["dashboard"])
    d = data["dashboard"]
    assert d["stations"]["total"] >= 2, d
    assert d["devices"]["total"] >= 2, d
    assert d["alarms"]["critical"] >= 1, d
    assert d["workorders"]["pending"] >= 2, d


# ════════════════════════════════════════════════════════════════════
# 3. 未认证 / 无 token → close(4001)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/ws/v1/realtime", "/ws/v1/dashboard", "/ws/v1/devices",
    "/ws/v1/alerts", "/ws/v1/workorders", "/ws/v1/dashboard/large-screen",
])
async def test_unauthenticated_rejected(path):
    """无 token 连接 → close(4001), 收不到 connected"""
    raised = False
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"ws://test{path}", client=ac) as ws:
                await asyncio.wait_for(ws.receive_json(), timeout=3.0)
    except Exception:
        raised = True
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
    assert raised
