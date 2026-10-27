#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回归测试 (卡8035bd65): ws 推送循环同步DB阻塞事件循环。

两部分:
  1. RealtimeDataHandler.get_dashboard_stats 改 SQL 聚合 (func.count / count /
     func.avg) 后统计口径不变 — 空表零值 + 种子数据精确断言。
  2. /ws/v1/dashboard push 循环的 handler.get_dashboard_stats 经
     asyncio.to_thread 在线程池执行, 不在事件循环线程 (线程 ident 证据)。

注意: realtime_handler 模块级 `from app.core.database import SessionLocal`
import 时按值绑定, test_db 对 db_module.SessionLocal 的覆盖不传播,
故测试内 monkeypatch 该模块的 SessionLocal 指向测试库 (同 test_ws_coverage
对 digital_twin_handler 的做法)。
"""
import threading
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.core import database as db_module
from app.main import app
import app.ws.realtime_handler as rt_mod
from app.ws.realtime_handler import RealtimeDataHandler
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.station import Station, StationStatus
from app.models.workorder import WorkOrder, WorkOrderStatus


@pytest.fixture(autouse=True)
def _setup(test_db, monkeypatch):
    """独立测试 DB + 把 realtime_handler.SessionLocal 指向测试库。"""
    # 卡 a579f89e: realtime_handler 改经 db_module.SessionLocal 运行时属性读取,
    # test_db 对模块级 SessionLocal 的覆盖自动传播, 无需再 patch rt_mod
    pass


def _seed(db):
    """2设备(1在线/1离线, 健康度80与None) + 2站点(1正常) + 3告警(2活跃/1critical) + 3工单。"""
    db.add(Station(name="s1", code="S1", status=StationStatus.NORMAL))
    db.add(Station(name="s2", code="S2", status=StationStatus.CLOSED))
    db.flush()
    db.add(Device(sn="d1", name="d1", type=DeviceType.PV_INVERTER, station_id=1,
                  status=DeviceStatus.ONLINE, health_score=80.0))
    db.add(Device(sn="d2", name="d2", type=DeviceType.PV_INVERTER, station_id=1,
                  status=DeviceStatus.OFFLINE, health_score=None))
    db.flush()
    # ORM default=100.0 只有未传键才生效; 显式 None 保留 (需 flush 前改写 attribute)
    from sqlalchemy import update
    db.execute(update(Device).where(Device.sn == "d2").values(health_score=None))
    db.add(Alarm(device_id=1, level=AlarmLevel.CRITICAL, status=AlarmStatus.ACTIVE, content="c1"))
    db.add(Alarm(device_id=1, level=AlarmLevel.INFO, status=AlarmStatus.ACTIVE, content="c2"))
    db.add(Alarm(device_id=1, level=AlarmLevel.CRITICAL, status=AlarmStatus.RESOLVED, content="c3"))
    db.add(WorkOrder(id="w1", status=WorkOrderStatus.PENDING, device_id=1))
    db.add(WorkOrder(id="w2", status=WorkOrderStatus.PROCESSING, device_id=1))
    db.add(WorkOrder(id="w3", status=WorkOrderStatus.COMPLETED, device_id=1,
                     finish_time=datetime.now(timezone.utc)))
    db.commit()


# ─── 1. get_dashboard_stats 聚合口径 ─────────────────────────────────

def test_dashboard_stats_empty_table_zero_values():
    """空表: 全部计数为 0, 平均健康度回退 100, 比率 0。"""
    stats = RealtimeDataHandler().get_dashboard_stats()
    assert stats["devices"] == {"total": 0, "online": 0, "offline": 0, "online_rate": 0}
    assert stats["stations"] == {"total": 0, "normal": 0, "rate": 0}
    assert stats["alarms"] == {"active": 0, "critical": 0}
    assert stats["workorders"] == {"pending": 0, "processing": 0, "today_completed": 0}
    assert stats["health"]["average"] == 100


def test_dashboard_stats_aggregation_matches_seeded_data():
    """种子数据: 设备/站点/告警/工单/健康度口径与原 .all() 逐条数一致。"""
    db = db_module.SessionLocal()
    try:
        _seed(db)
    finally:
        db.close()

    stats = RealtimeDataHandler().get_dashboard_stats()
    assert stats["devices"] == {"total": 2, "online": 1, "offline": 1, "online_rate": 50.0}
    assert stats["stations"] == {"total": 2, "normal": 1, "rate": 50.0}
    # critical 仅统计 active (原逻辑在 active 集合内数 critical)
    assert stats["alarms"] == {"active": 2, "critical": 1}
    assert stats["workorders"] == {"pending": 1, "processing": 1, "today_completed": 1}
    # health_score 显式置 None 的设备不计入平均: 只有 80
    assert stats["health"]["average"] == 80.0


# ─── 2. push 循环 to_thread 线程卸载 ─────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_push_loop_runs_db_off_loop(monkeypatch):
    """/ws/v1/dashboard 推送循环的 get_dashboard_stats 在线程池执行。"""
    loop_thread = threading.get_ident()
    seen_threads = []
    orig = RealtimeDataHandler.get_dashboard_stats

    def spy(self, team_id=None):
        # 卡 a579f89e: handler 方法新增 team_id 参数, spy 签名同步
        seen_threads.append(threading.get_ident())
        return orig(self, team_id)

    monkeypatch.setattr(RealtimeDataHandler, "get_dashboard_stats", spy)

    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as ac:
        # token: admin 由 test_db seed; 直接走登录拿 JWT
        from fastapi.testclient import TestClient
        token = TestClient(app).post(
            "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
        ).json()["data"]["token"]
        async with aconnect_ws(f"ws://test/ws/v1/dashboard?token={token}", client=ac) as ws:
            # 等第一条 dashboard data 消息 (推送周期 5s, 首推立即)
            for _ in range(5):
                msg = await ws.receive_json()
                if msg.get("type") == "data" and msg.get("channel") == "dashboard":
                    break
            else:
                pytest.fail("未收到 dashboard data 推送")

    assert seen_threads, "推送循环未调用 get_dashboard_stats"
    assert all(t != loop_thread for t in seen_threads), (
        f"DB查询仍在事件循环线程执行: loop={loop_thread} seen={seen_threads}"
    )


def test_routes_source_uses_to_thread_for_handlers():
    """静态防回归: routes.py 的 handler DB 调用必须经 asyncio.to_thread。"""
    import app.ws.routes as routes
    src = open(routes.__file__, encoding="utf-8").read()
    assert "asyncio.to_thread(handler.get_dashboard_stats" in src
    assert "asyncio.to_thread(handler.get_device_realtime_update" in src
    assert "asyncio.to_thread(handler.get_charging_queue_snapshot" in src
