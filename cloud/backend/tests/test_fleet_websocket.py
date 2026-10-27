#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fleet WebSocket 实时推送测试 - 排队队列 + V2G 计划状态

覆盖:
- FleetRealtimeHandler 快照查询 (排队队列 / V2G)
- WS 端点连接 (/ws/v1/fleet/queue/{station_id}, /ws/v1/fleet/v2g/{enterprise_id})
"""
import asyncio
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app
from app.models.charging_queue import ChargingQueue, ChargingQueueStatus
from tests._route_helpers import collect_route_paths

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(test_db):
    """每个测试使用独立数据库"""
    pass


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _seed_queue(station_id=1, n_waiting=2, n_charging=1):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        for i in range(n_waiting):
            db.add(ChargingQueue(
                station_id=station_id, vehicle_id=1000 + i,
                priority=100, status=ChargingQueueStatus.WAITING.value,
                required_energy_kwh=30.0, target_soc=0.8,
                estimated_wait_minutes=i * 15,
            ))
        for j in range(n_charging):
            db.add(ChargingQueue(
                station_id=station_id, vehicle_id=2000 + j,
                priority=100, status=ChargingQueueStatus.CHARGING.value,
                required_energy_kwh=50.0, target_soc=0.9,
                estimated_wait_minutes=0,
            ))
        db.commit()
    finally:
        db.close()


def _seed_v2g(enterprise_id, vehicle_id, n_scheduled=2, n_completed=1):
    from app.core.database import SessionLocal
    from app.models.fleet_v2g import FleetV2GPlan, V2GPlanStatus
    db = SessionLocal()
    try:
        for i in range(n_scheduled):
            db.add(FleetV2GPlan(
                enterprise_id=enterprise_id, vehicle_id=vehicle_id,
                plan_date=date(2026, 7, 24), status=V2GPlanStatus.SCHEDULED,
                target_soc_min=20.0, target_soc_max=80.0,
            ))
        for j in range(n_completed):
            db.add(FleetV2GPlan(
                enterprise_id=enterprise_id, vehicle_id=vehicle_id,
                plan_date=date(2026, 7, 23), status=V2GPlanStatus.COMPLETED,
                target_soc_min=20.0, target_soc_max=80.0,
            ))
        db.commit()
    finally:
        db.close()


def _login_token():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json().get("data", {}).get("token")


def _make_enterprise(code=None):
    from app.core.database import SessionLocal
    from app.models.enterprise import Enterprise
    code = code or f"ENT_FWS_{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        ent = Enterprise(name=f"FleetWS企业_{code}", code=code, balance=10000.00)
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.id
    finally:
        db.close()


def _make_vehicle(enterprise_id, plate=None, vin=None):
    suffix = uuid.uuid4().hex[:8]
    plate = plate or f"豫A-FWS-{suffix}"
    vin = vin or f"LSVAU2FWS{suffix}"
    headers = {"Authorization": f"Bearer {_login_token()}"}
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json={"plate_number": plate, "vin": vin, "driver_name": "司", "driver_phone": "13800000001"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


# ======================================================================
# Handler 快照查询
# ======================================================================

class TestFleetHandlerSnapshots:
    """FleetRealtimeHandler 快照方法"""

    def test_charging_queue_snapshot(self):
        _seed_queue(station_id=1, n_waiting=2, n_charging=1)
        from app.ws.fleet_handler import FleetRealtimeHandler
        snap = FleetRealtimeHandler().get_charging_queue_snapshot(station_id=1)

        assert snap["station_id"] == 1
        assert snap["total"] == 3
        assert snap["waiting_count"] == 2
        assert snap["charging_count"] == 1
        assert isinstance(snap["status_counts"], dict)
        assert snap["status_counts"].get("waiting") == 2
        assert snap["status_counts"].get("charging") == 1
        assert "timestamp" in snap

    def test_charging_queue_snapshot_empty(self):
        from app.ws.fleet_handler import FleetRealtimeHandler
        snap = FleetRealtimeHandler().get_charging_queue_snapshot(station_id=999)

        assert snap["station_id"] == 999
        assert snap["total"] == 0
        assert snap["waiting_count"] == 0
        assert snap["charging_count"] == 0
        assert snap["status_counts"] == {}

    def test_v2g_snapshot(self):
        ent = _make_enterprise()
        veh = _make_vehicle(ent)
        _seed_v2g(ent, veh, n_scheduled=2, n_completed=1)

        from app.ws.fleet_handler import FleetRealtimeHandler
        snap = FleetRealtimeHandler().get_v2g_snapshot(enterprise_id=ent)

        assert snap["enterprise_id"] == ent
        assert snap["total_plans"] == 3
        assert snap["plan_status_counts"].get("scheduled") == 2
        assert snap["plan_status_counts"].get("completed") == 1
        assert "timestamp" in snap

    def test_v2g_snapshot_empty(self):
        from app.ws.fleet_handler import FleetRealtimeHandler
        snap = FleetRealtimeHandler().get_v2g_snapshot(enterprise_id=99999)

        assert snap["enterprise_id"] == 99999
        assert snap["total_plans"] == 0
        assert snap["plan_status_counts"] == {}


# ======================================================================
# WS 路由注册
# ======================================================================

class TestFleetWSRoutes:
    """fleet WS 路由注册到 app"""

    def test_fleet_ws_routes_registered(self):
        ws_paths = {p for p in collect_route_paths(app.routes) if "/ws/" in p}
        assert "/ws/v1/fleet/queue/{station_id}" in ws_paths
        assert "/ws/v1/fleet/v2g/{enterprise_id}" in ws_paths

    def test_fleet_channels_supported_by_manager(self):
        from app.ws.manager import WebSocketManager
        mgr = WebSocketManager()
        assert "fleet_queue" in mgr.channel_connections
        assert "fleet_v2g" in mgr.channel_connections

    def test_fleet_channel_message_schema(self):
        from app.ws.schemas import WebSocketMessage
        # fleet 频道必须在 channel 白名单中
        msg = WebSocketMessage(type="data", channel="fleet_queue", payload={"total": 0})
        assert msg.channel == "fleet_queue"
        msg2 = WebSocketMessage(type="data", channel="fleet_v2g", payload={"total_plans": 0})
        assert msg2.channel == "fleet_v2g"


# ======================================================================
# 真实 WS 连接
# ======================================================================

async def _assert_connected(url: str, expected_channel: str):
    """连接 fleet push 端点并校验 connected 握手。

    容忍 httpx-ws ASGI transport 在服务端持续推送时关闭的 teardown 时序 quirk
    (EndOfStream/ExceptionGroup, 非业务缺陷): 断言放在 teardown 之外以保持严格校验。
    """
    msg = None
    transport = ASGIWebSocketTransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
                await ws.close()
    except Exception:
        pass
    try:
        await transport.aclose()
    except Exception:
        pass
    assert msg is not None, f"{url} 未收到连接消息"
    assert msg["type"] == "connected"
    assert msg["channel"] == expected_channel
    return msg


@pytest.mark.asyncio
async def test_ws_connect_fleet_queue():
    """连接 /ws/v1/fleet/queue/{station_id} 收到 connected 消息"""
    _seed_queue(station_id=5, n_waiting=1, n_charging=0)
    await asyncio.wait_for(
        _assert_connected(f"ws://test/ws/v1/fleet/queue/5?token={_login_token()}", "fleet_queue"),
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_ws_connect_fleet_v2g():
    """连接 /ws/v1/fleet/v2g/{enterprise_id} 收到 connected 消息"""
    await asyncio.wait_for(
        _assert_connected(f"ws://test/ws/v1/fleet/v2g/1?token={_login_token()}", "fleet_v2g"),
        timeout=10.0,
    )
