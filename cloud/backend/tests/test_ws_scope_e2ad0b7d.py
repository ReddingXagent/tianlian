#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 授权作用域测试 (卡 e2ad0b7d — IDOR 旁路修复)

背景: /ws/v1 带路径参数端点 (digital-twin station/device, fleet/queue,
fleet/v2g) 此前只认证 (authenticate_websocket, 4001) 不授权, 任意团队
用户可连他人团队的 station_id/device_id/enterprise_id 获取实时数据。
修复后 (app/ws/authorize.py):

  - 端点级: 跨团队 / 资源不存在 → close(4003, "无权访问"), 客户端收不到
    connected; 本团队 / admin → 正常握手。
  - 消息级: digital-twin station 端点的 subscribe_device 越权订阅 →
    收 error 消息且不订阅 (不断连); 本团队设备 → subscribed 回执。

鉴权/连接基建复用 tests/ws/test_ws_auth.py 的 httpx_ws 模式。
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
    """每个测试独立 DB (覆盖 SessionLocal, seed admin)。WS 授权层经
    db_module.SessionLocal 运行时读取, test_db 覆盖传播至 authorize.py。"""
    pass


# ─── seed 辅助 ────────────────────────────────────────────────────────

def _seed_team(db, name: str):
    from app.models.team import Team, TeamType
    team = Team(name=name, code=f"T{uuid.uuid4().hex[:8]}", type=TeamType.OPS_COMPANY)
    db.add(team)
    db.commit()
    return team


def _seed_user(db, username: str, team, role="engineer"):
    from app.models.user import User, UserRole
    user = User(
        username=username, password_hash=_hash("pw123456"),
        role=UserRole.ENGINEER, team_id=team.id, status="active",
    )
    db.add(user)
    db.commit()
    return user


def _hash(pw: str) -> str:
    """与 conftest seed admin 同源的快速哈希 (tests/_test_helpers._fast_hash)。"""
    from tests._test_helpers import _fast_hash
    return _fast_hash(pw)


def _seed_env():
    """seed 两个团队 + 各自 station/device/enterprise + 团队级用户 + 资源, 返回 dict。"""
    from app.core.database import SessionLocal
    from app.models.device import Device, DeviceType
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.station import Station, StationStatus
    from app.models.user import Team, TeamType, User, UserRole

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        team_a = Team(name=f"团队A{suffix}", code=f"TA{suffix}", type=TeamType.OPS_COMPANY)
        team_b = Team(name=f"团队B{suffix}", code=f"TB{suffix}", type=TeamType.OPS_COMPANY)
        db.add_all([team_a, team_b])
        db.commit()

        user_a = User(
            username=f"ua_{suffix}", password_hash=_hash("pw123456"),
            role=UserRole.ENGINEER, team_id=team_a.id, status="active",
        )
        db.add(user_a)
        db.commit()

        station_a = Station(name=f"站A{suffix}", code=f"SA{suffix}", team_id=team_a.id, status=StationStatus.NORMAL)
        station_b = Station(name=f"站B{suffix}", code=f"SB{suffix}", team_id=team_b.id, status=StationStatus.NORMAL)
        db.add_all([station_a, station_b])
        db.commit()

        device_a = Device(sn=f"DNA{suffix}", name=f"设备A{suffix}", code=f"DA{suffix}", type=DeviceType.CHARGER_DC, station_id=station_a.id)
        device_b = Device(sn=f"DNB{suffix}", name=f"设备B{suffix}", code=f"DB{suffix}", type=DeviceType.CHARGER_DC, station_id=station_b.id)
        db.add_all([device_a, device_b])
        db.commit()

        ent_a = Enterprise(name=f"企业A{suffix}", code=f"EA{suffix}", owner_team_id=team_a.id, status=EnterpriseStatus.ACTIVE)
        ent_b = Enterprise(name=f"企业B{suffix}", code=f"EB{suffix}", owner_team_id=team_b.id, status=EnterpriseStatus.ACTIVE)
        db.add_all([ent_a, ent_b])
        db.commit()

        return {
            "user_a": user_a.username, "station_a": station_a.id, "station_b": station_b.id,
            "device_a": device_a.id, "device_b": device_b.id,
            "ent_a": ent_a.id, "ent_b": ent_b.id,
        }
    finally:
        db.close()


def _token_for(username: str, password: str = "pw123456") -> str:
    """login 拿 JWT; 失败则回退直接签发 (login 端点策略随版本变化)。"""
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


def _admin_token() -> str:
    r = client.post(f"{_BASE}/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


async def _connect(url: str, token: str):
    """连接并尝试收首条消息。返回 (msg_or_None, raised)。

    授权拒绝 (close 4003) 时 aconnect_ws / receive 抛异常 → (None, True)。
    """
    transport = ASGIWebSocketTransport(app=app)
    msg = None
    raised = False
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"{url}?token={token}", client=ac) as ws:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
    except Exception:
        raised = True
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
    return msg, raised


def _env_ids():
    """同步 seed 并返回资源 id 集合 (pytest.mark.asyncio 测试内调用)。"""
    return _seed_env()


# ════════════════════════════════════════════════════════════════════
# 端点级: 跨团队 4 端点 → close 4003 (收不到 connected)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cross_team_station_denied():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/digital-twin/station/{env['station_b']}", _token_for(env["user_a"]))
    assert raised and msg is None


@pytest.mark.asyncio
async def test_cross_team_device_denied():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/digital-twin/device/{env['device_b']}", _token_for(env["user_a"]))
    assert raised and msg is None


@pytest.mark.asyncio
async def test_cross_team_fleet_queue_denied():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/fleet/queue/{env['station_b']}", _token_for(env["user_a"]))
    assert raised and msg is None


@pytest.mark.asyncio
async def test_cross_team_fleet_v2g_denied():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/fleet/v2g/{env['ent_b']}", _token_for(env["user_a"]))
    assert raised and msg is None


# ════════════════════════════════════════════════════════════════════
# 资源不存在 → 同样 4003 (不泄露存在性)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_nonexistent_station_denied():
    env = _env_ids()
    msg, raised = await _connect("/ws/v1/digital-twin/station/9999999", _token_for(env["user_a"]))
    assert raised and msg is None


@pytest.mark.asyncio
async def test_nonexistent_enterprise_denied():
    env = _env_ids()
    msg, raised = await _connect("/ws/v1/fleet/v2g/9999999", _token_for(env["user_a"]))
    assert raised and msg is None


# ════════════════════════════════════════════════════════════════════
# 放行: 本团队 + admin 豁免 → 收到 connected
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_same_team_station_allowed():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/digital-twin/station/{env['station_a']}", _token_for(env["user_a"]))
    assert not raised and msg is not None
    assert msg.get("type") == "connected"


@pytest.mark.asyncio
async def test_same_team_fleet_v2g_allowed():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/fleet/v2g/{env['ent_a']}", _token_for(env["user_a"]))
    assert not raised and msg is not None
    assert msg.get("type") == "connected"


@pytest.mark.asyncio
async def test_admin_exempt_cross_team_allowed():
    """admin 平台级豁免: 连他人团队站点正常握手。"""
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/digital-twin/station/{env['station_b']}", _admin_token())
    assert not raised and msg is not None
    assert msg.get("type") == "connected"


@pytest.mark.asyncio
async def test_admin_exempt_fleet_queue_allowed():
    env = _env_ids()
    msg, raised = await _connect(f"/ws/v1/fleet/queue/{env['station_b']}", _admin_token())
    assert not raised and msg is not None
    assert msg.get("type") == "connected"


# ════════════════════════════════════════════════════════════════════
# 消息级: subscribe_device 越权 → error 回执 + 不订阅 (不断连)
# ════════════════════════════════════════════════════════════════════

async def _subscribe_flow(station_id: int, device_id: int, token: str) -> dict:
    """连 station 端点, 发 subscribe_device, 扫描回执。返回 {subscribed, error}。

    注意: 端点的 initial_data (DigitalTwinHandler) 会因 ThreeDModelType.GENERIC
    缺失抛 AttributeError (预存缺陷, 既有测试用不存在的 station_id 绕开),
    杀死 handle_client_messages → 1011 断连。故把 subscribe 消息提前到握手后
    立即发送, 与 initial_data 的 send 竞速入队 receive 队列, 在连接死亡前
    拿到回执; 3 次重试对抗时序抖动。
    """
    result = {"subscribed": False, "error": False}
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(f"/ws/v1/digital-twin/station/{station_id}?token={token}", client=ac) as ws:
                # 等握手后立即投递订阅 (勿先消费 initial_data)
                m = await asyncio.wait_for(ws.receive_json(), timeout=8.0)
                assert m.get("type") == "connected", m
                await ws.send_json({"type": "subscribe_device", "device_id": device_id})
                deadline = asyncio.get_event_loop().time() + 8.0
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        m = await asyncio.wait_for(ws.receive_json(), timeout=deadline - asyncio.get_event_loop().time())
                    except Exception as e:
                        result["exc"] = repr(e)
                        break
                    if m.get("type") == "subscribed":
                        result["subscribed"] = True
                        break
                    if m.get("type") == "error":
                        result["error"] = True
                        result["msgs"] = result.get("msgs", [])
                        break
                    result.setdefault("msgs", []).append(m.get("type"))
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
    return result


@pytest.mark.asyncio
async def test_subscribe_device_cross_team_rejected():
    env = _env_ids()
    token = _token_for(env["user_a"])
    r = await _subscribe_flow(env["station_a"], env["device_b"], token)
    assert r["error"] and not r["subscribed"], r


@pytest.mark.asyncio
async def test_subscribe_device_same_team_ok():
    env = _env_ids()
    token = _token_for(env["user_a"])
    r = await _subscribe_flow(env["station_a"], env["device_a"], token)
    assert r["subscribed"] and not r["error"], r
