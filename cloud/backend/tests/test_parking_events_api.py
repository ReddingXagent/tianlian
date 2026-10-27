"""
无人值守占位费自动化 — 占位事件接入端点测试 (工作卡 f0db2036)

覆盖 POST /api/v1/parking/events (单条) + /parking/events/batch (批量):
① 进场未离场 → PENDING
② 含离场 → 触发占位费计费(独立账单 BILLED)
③ 批量上报
④ 幂等: 同事件重复上报 → 同一 id
⑤ 鉴权: 无 token → 401/403
⑥ 站点不存在 → 404

鉴权复用 get_current_gateway_or_user(X-API-Key 网关 / Bearer 用户);
认证/DB 模式参考 test_charging_sessions.py。
"""
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """注入 test_db(override SessionLocal + seed admin), 每测试独立 DB。"""
    pass


def _auth_headers():
    resp = client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, code="STPE01"):
    from app.models.station import Station, StationStatus
    st = Station(name="占位事件测试站", code=code, address="测试地址",
                 status=StationStatus.NORMAL)
    session.add(st); session.commit(); session.refresh(st)
    return st


def _seed_parking_price(session, station_id, free_minutes=30, hourly_rate=6.0):
    from datetime import date
    from app.models.pricing_v2 import ParkingPrice
    session.add(ParkingPrice(
        station_id=station_id, free_minutes=free_minutes,
        hourly_rate=Decimal(str(hourly_rate)), enable_night_rate=False,
        effective_date=date(2026, 1, 1), is_active=True,
    )); session.commit()


# ═══════════════════════════════════════════════════════════════
# ① 进场未离场 → PENDING
# ═══════════════════════════════════════════════════════════════

def test_report_open_event_pending(test_db):
    s = test_db["session"]
    st = _seed_station(s)
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "京A12345", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["fee_status"] == "pending"
    assert data["exit_at"] is None
    assert data["plate_number"] == "京A12345"


# ═══════════════════════════════════════════════════════════════
# ② 含离场 → 触发占位费计费(独立账单 BILLED)
# ═══════════════════════════════════════════════════════════════

def test_report_event_with_exit_settles(test_db):
    """在场 120min, 无订单, free=30, rate=6 → billable 90 → fee 9.00 (BILLED)。"""
    s = test_db["session"]
    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)

    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "京B88888", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
        "exit_at": "2026-07-28T12:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["fee_status"] == "billed"
    assert data["fee_amount"] == 9.0
    assert data["occupancy_minutes"] == 120
    assert data["match_order_id"] is None


# ═══════════════════════════════════════════════════════════════
# ③ 批量上报
# ═══════════════════════════════════════════════════════════════

def test_report_batch(test_db):
    s = test_db["session"]
    st = _seed_station(s)
    resp = client.post("/api/v1/parking/events/batch", json={
        "events": [
            {"plate_number": "京C1", "station_id": st.id,
             "enter_at": "2026-07-28T10:00:00"},
            {"plate_number": "京C2", "station_id": st.id,
             "enter_at": "2026-07-28T10:00:00",
             "exit_at": "2026-07-28T10:10:00"},
        ]
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["count"] == 2
    assert len(data["events"]) == 2


# ═══════════════════════════════════════════════════════════════
# ④ 幂等: 同事件重复上报 → 同一 id
# ═══════════════════════════════════════════════════════════════

def test_report_idempotent(test_db):
    s = test_db["session"]
    st = _seed_station(s)
    _seed_parking_price(s, st.id)
    payload = {
        "plate_number": "京D99999", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
        "exit_at": "2026-07-28T11:00:00",
    }
    r1 = client.post("/api/v1/parking/events", json=payload, headers=_auth_headers())
    assert r1.status_code == 200, r1.text
    id1 = r1.json()["data"]["id"]

    r2 = client.post("/api/v1/parking/events", json=payload, headers=_auth_headers())
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == id1

    from app.models.parking_event import OccupancyEvent
    count = s.query(OccupancyEvent).filter(
        OccupancyEvent.plate_number == "京D99999").count()
    assert count == 1


# ═══════════════════════════════════════════════════════════════
# ⑤ 鉴权: 无 token → 401/403
# ═══════════════════════════════════════════════════════════════

def test_report_unauthorized(test_db):
    s = test_db["session"]
    st = _seed_station(s)
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "京E1", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
    })
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════
# ⑥ 站点不存在 → 404
# ═══════════════════════════════════════════════════════════════

def test_report_station_not_found(test_db):
    resp = client.post("/api/v1/parking/events", json={
        "plate_number": "京F1", "station_id": 999999,
        "enter_at": "2026-07-28T10:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# ⑦ 进场后再报离场 → 更新同事件并计费
# ═══════════════════════════════════════════════════════════════

def test_report_open_then_exit_updates_same_event(test_db):
    s = test_db["session"]
    st = _seed_station(s)
    _seed_parking_price(s, st.id, free_minutes=30, hourly_rate=6.0)

    r1 = client.post("/api/v1/parking/events", json={
        "plate_number": "京G1", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
    }, headers=_auth_headers())
    assert r1.status_code == 200
    assert r1.json()["data"]["fee_status"] == "pending"

    r2 = client.post("/api/v1/parking/events", json={
        "plate_number": "京G1", "station_id": st.id,
        "enter_at": "2026-07-28T10:00:00",
        "exit_at": "2026-07-28T12:00:00",  # 120min
    }, headers=_auth_headers())
    assert r2.status_code == 200, r2.text
    data = r2.json()["data"]
    assert data["id"] == r1.json()["data"]["id"]
    assert data["fee_status"] == "billed"     # 离场触发计费
    assert data["fee_amount"] == 9.0
