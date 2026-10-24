#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
digital_twin WS 心跳缺口测试 (卡 f841c524)

背景: ws_manager 心跳循环会驱逐 _last_heartbeat 距今超 90s 的连接,
record_heartbeat 是唯一刷新手段。五个 WS 端点中 realtime/large-screen/
fleet_queue/fleet_v2g 的 ping 分支均已刷新, 唯 digital_twin 两处漏网:
  - /ws/v1/digital-twin/station/{id}: ping 分支回 pong 但不刷新
  - /ws/v1/digital-twin/global: wait_disconnect 丢弃一切消息, 无 ping 语义

修复后两端点 ping 均刷新 _last_heartbeat 并回 heartbeat pong。

连接/seed 基建照抄 tests/test_ws_scope_e2ad0b7d.py (httpx_ws 模式,
test_db 覆盖 SessionLocal 传播至授权层)。
"""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app
from app.ws import ws_manager

client = TestClient(app)

_BASE = "/api/v1"


@pytest.fixture(autouse=True)
def _setup(test_db):
    pass


def _hash(pw: str) -> str:
    from tests._test_helpers import _fast_hash
    return _fast_hash(pw)


def _seed_env():
    """seed 团队A + 用户 + 站点, 返回 {user_a, station_a}。"""
    from app.core.database import SessionLocal
    from app.models.station import Station, StationStatus
    from app.models.user import Team, TeamType, User, UserRole

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        team_a = Team(name=f"团队A{suffix}", code=f"TA{suffix}", type=TeamType.OPS_COMPANY)
        db.add(team_a)
        db.commit()
        user_a = User(
            username=f"ua_{suffix}", password_hash=_hash("pw123456"),
            role=UserRole.ENGINEER, team_id=team_a.id, status="active",
        )
        db.add(user_a)
        db.commit()
        station_a = Station(
            name=f"站A{suffix}", code=f"SA{suffix}",
            team_id=team_a.id, status=StationStatus.NORMAL,
        )
        db.add(station_a)
        db.commit()
        return {"user_a": user_a.username, "station_a": station_a.id}
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
        "sub": username, "role": "engineer",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    })


def _heartbeat_max() -> float:
    """当前 _last_heartbeat 全量最大时间戳 (服务器进程内共享, 测试同进程可读)。"""
    vals = ws_manager._last_heartbeat.values()
    return max(vals) if vals else 0.0


async def _ping_flow(url: str, token: str) -> dict:
    """连接 → 收 connected → 立即发 ping → 扫描 heartbeat pong。

    返回 {pong, ts_before, ts_after}。station 端点的 initial_data 可能因
    预存缺陷 (ThreeDModelType.GENERIC) 杀连接, 故 ping 握手后立即发送,
    与既有 subscribe 测试同样竞速策略; pong 可能被 initial_data/update
    消息穿插, 扫描时跳过。
    """
    result = {"pong": False, "ts_before": 0.0, "ts_after": 0.0}
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"{url}?token={token}", client=ac) as ws:
                m = await asyncio.wait_for(ws.receive_json(), timeout=8.0)
                assert m.get("type") == "connected", m
                result["ts_before"] = _heartbeat_max()
                await asyncio.sleep(0.05)
                await ws.send_json({"type": "ping"})
                deadline = asyncio.get_event_loop().time() + 8.0
                while asyncio.get_event_loop().time() < deadline:
                    result["ts_after"] = max(result["ts_after"], _heartbeat_max())
                    try:
                        m = await asyncio.wait_for(
                            ws.receive_json(),
                            timeout=max(0.05, deadline - asyncio.get_event_loop().time()),
                        )
                    except Exception:
                        break
                    if m.get("type") == "heartbeat":
                        result["pong"] = True
                        break
                result["ts_after"] = max(result["ts_after"], _heartbeat_max())
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
    return result


@pytest.mark.asyncio
async def test_station_ping_records_heartbeat():
    env = _seed_env()
    token = _token_for(env["user_a"])
    r = await _ping_flow(f"/ws/v1/digital-twin/station/{env['station_a']}", token)
    assert r["pong"], r
    assert r["ts_after"] > r["ts_before"], r


@pytest.mark.asyncio
async def test_global_ping_records_heartbeat():
    env = _seed_env()
    token = _token_for(env["user_a"])
    r = await _ping_flow("/ws/v1/digital-twin/global", token)
    assert r["pong"], r
    assert r["ts_after"] > r["ts_before"], r
