"""
卡 27eb37e6: analyze_efficiency 日期参数无界读放大加固测试
- 跨度上限 366 天（与 get_energy_trend 卡 05ccb577 一致）
- 反序区间（end_date < start_date）拒绝，防负能耗假数据

该端点响应为裸 EfficiencyAnalysisResponse（无 data 信封），查询窗口动态取
now±2h 锚点（卡 7b7a7444，遥测种子以 now 为锚）。
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.device import Device

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth():
    return {"Authorization": f"Bearer {_login()}"}


def _seed_telemetry(db, device_id, hours=10):
    from app.models.telemetry import Telemetry
    now = datetime.now(timezone.utc)
    for i in range(hours):
        db.add(Telemetry(
            device_id=device_id,
            timestamp=now - timedelta(hours=i),
            battery_soc=50.0 + i * 0.5,
            battery_temperature=25.0 + (i % 10),
            grid_power_total=50.0 + i * 2,
            grid_power_factor=0.95 - i * 0.01,
            inv_power_a=40.0 + i * 1.5,
            charger_power=8.0 + i * 0.3,
        ))
    db.commit()


def _seed_devices(db, ids_types):
    devs = [Device(id=i, sn=f'DEV-{i}', name=f'设备{i}', type=t, station_id=1, status='online')
            for i, t in ids_types]
    db.add_all(devs)
    db.commit()
    for i, _ in ids_types:
        _seed_telemetry(db, i)
    return [i for i, _ in ids_types]


def test_efficiency_normal_span_ok(test_db):
    db = test_db['session']
    ids = _seed_devices(db, [(200, 'PV_INVERTER')])
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": ids,
            "start_date": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_devices"] == 1
    assert "total_energy_kwh" in data
    assert "efficiency_score" in data
    assert isinstance(data["breakdown_by_device"], list)
    assert len(data["breakdown_by_device"]) == 1


def test_efficiency_multi_device_ok(test_db):
    db = test_db['session']
    ids = _seed_devices(db, [(201, 'PV_INVERTER'), (202, 'CHARGER_DC'), (203, 'BATTERY')])
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": ids,
            "start_date": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_devices"] == 3
    assert len(data["breakdown_by_device"]) == 3


def test_efficiency_oversized_span_rejected(test_db):
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": [200],
            "start_date": "2000-01-01T00:00:00",
            "end_date": "2099-12-31T00:00:00",
        },
        headers=_auth(),
    )
    assert resp.status_code == 422, f"期望422, 实际={resp.status_code}: {resp.text}"
    assert "366" in resp.text


def test_efficiency_boundary_366_days_ok(test_db):
    db = test_db['session']
    ids = _seed_devices(db, [(210, 'PV_INVERTER')])
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": ids,
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2026-01-01T00:00:00",  # 恰 366 天
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text


def test_efficiency_boundary_367_days_rejected(test_db):
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": [210],
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2026-01-03T00:00:00",  # 367 天
        },
        headers=_auth(),
    )
    assert resp.status_code == 422, f"期望422, 实际={resp.status_code}: {resp.text}"


def test_efficiency_reversed_span_rejected(test_db):
    resp = client.post(
        "/api/v1/analytics/efficiency-analysis",
        json={
            "device_ids": [210],
            "start_date": "2026-01-07T00:00:00",
            "end_date": "2026-01-01T00:00:00",  # 反序区间
        },
        headers=_auth(),
    )
    assert resp.status_code == 422, f"期望422, 实际={resp.status_code}: {resp.text}"
    assert "start" in resp.text
