"""
卡 05ccb577: get_energy_trend 日期跨度上限(366天)加固测试
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

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


def test_trend_normal_span_ok():
    resp = client.get(
        "/api/v1/energy/trend?start_date=2026-01-01&end_date=2026-01-07&granularity=day",
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["period"] == {"start": "2026-01-01", "end": "2026-01-07"}


def test_trend_oversized_span_rejected():
    resp = client.get(
        "/api/v1/energy/trend?start_date=2000-01-01&end_date=2099-12-31",
        headers=_auth(),
    )
    assert resp.json()["code"] == 400, f"期望code=400, 实际={resp.json()['code']}"
    assert "366" in resp.json()["message"]


def test_trend_boundary_366_days_ok():
    resp = client.get(
        "/api/v1/energy/trend?start_date=2025-01-01&end_date=2026-01-01",  # 恰 366 天
        headers=_auth(),
    )
    assert resp.status_code == 200


def test_trend_boundary_367_days_rejected():
    resp = client.get(
        "/api/v1/energy/trend?start_date=2025-01-01&end_date=2026-01-03",  # 367 天
        headers=_auth(),
    )
    assert resp.json()["code"] == 400, f"期望code=400, 实际={resp.json()['code']}"


def test_trend_start_only_ok():
    resp = client.get(
        "/api/v1/energy/trend?start_date=2026-01-01", headers=_auth())
    assert resp.status_code == 200


def test_trend_end_only_ok():
    resp = client.get(
        "/api/v1/energy/trend?end_date=2026-01-07", headers=_auth())
    assert resp.status_code == 200
