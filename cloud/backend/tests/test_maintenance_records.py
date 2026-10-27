"""
设备维护记录 API 测试
覆盖: /maintenance-records — CRUD 操作
"""
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """种子 station + device（任务卡 ab5c5f17：治理后端点校验 device 存在性，
    admin 豁免 team，仅需 device 存在；旧测试用幽灵 device_id，此处补种子）。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    s = test_db["session"]
    s.add(Station(id=1, name="种子站", code="SEEDST01", status=StationStatus.NORMAL))
    s.commit()
    for did in (1, 2, 42, 99):
        s.add(Device(id=did, sn=f"SN-SEED-{did}", name=f"种子设备{did}",
                     code=f"SEED{did}", type=DeviceType.PV_INVERTER,
                     status=DeviceStatus.ONLINE, station_id=1, health_score=85.0))
    s.commit()


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    assert token, "Login did not return token"
    return token


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_record(headers, **overrides):
    defaults = dict(device_id=1, title="测试维护记录", type="preventive", description="测试描述")
    defaults.update(overrides)
    resp = client.post("/api/v1/maintenance-records", json=defaults, headers=headers)
    assert resp.status_code == 200, f"Create failed: {resp.text}"
    return resp.json()["data"]


# ========== 鉴权检查 ==========

def test_list_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/maintenance-records")
    assert resp.status_code == 403 or resp.status_code == 401


def test_create_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.post("/api/v1/maintenance-records", json={"device_id": 1, "title": "x"})
    assert resp.status_code == 403 or resp.status_code == 401


# ========== CRUD 操作 ==========

def test_list_maintenance_records():
    headers = _auth_headers()
    _create_record(headers)

    resp = client.get("/api/v1/maintenance-records", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


def test_list_filter_by_device_id():
    headers = _auth_headers()
    _create_record(headers, device_id=42, title="设备42维护")
    _create_record(headers, device_id=99, title="设备99维护")

    resp = client.get("/api/v1/maintenance-records?device_id=42", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["device_id"] == 42 for i in items)


def test_list_filter_by_type():
    headers = _auth_headers()
    _create_record(headers, type="preventive", title="预防")
    _create_record(headers, type="emergency", title="紧急")

    resp = client.get("/api/v1/maintenance-records?type=emergency", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["type"] == "emergency" for i in items)


def test_list_filter_by_status():
    headers = _auth_headers()
    _create_record(headers, title="状态测试")

    resp = client.get("/api/v1/maintenance-records?status=planned", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["status"] == "planned" for i in items)


def test_list_invalid_type():
    headers = _auth_headers()
    resp = client.get("/api/v1/maintenance-records?type=invalid", headers=headers)
    assert resp.status_code == 400  # query 过滤参数仍服务端校验 (卡 6031add1 triage 跳过收紧)


def test_get_maintenance_record():
    headers = _auth_headers()
    rec = _create_record(headers, title="详情测试")

    resp = client.get(f"/api/v1/maintenance-records/{rec['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "详情测试"


def test_get_nonexistent_record():
    headers = _auth_headers()
    resp = client.get("/api/v1/maintenance-records/99999", headers=headers)
    assert resp.status_code == 404


def test_create_maintenance_record():
    headers = _auth_headers()
    payload = {
        "device_id": 1,
        "title": "季度维护",
        "type": "preventive",
        "description": "季度预防性维护检查",
        "cost": 50000,
    }
    resp = client.post("/api/v1/maintenance-records", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "季度维护"
    assert data["type"] == "preventive"
    assert data["status"] == "planned"
    assert data["cost"] == 50000
    assert data["device_id"] == 1


def test_create_with_all_fields():
    headers = _auth_headers()
    now = datetime(2026, 6, 23, 10, 0, 0)
    payload = {
        "device_id": 2,
        "station_id": 1,
        "engineer_id": 1,
        "type": "corrective",
        "title": "全面维护",
        "description": "设备全面检查与维护",
        "solution": "更换损坏部件",
        "parts_replaced": "保险丝x2, 散热风扇",
        "cost": 120000,
        "planned_at": now.isoformat(),
        "started_at": now.isoformat(),
    }
    resp = client.post("/api/v1/maintenance-records", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["type"] == "corrective"
    assert data["parts_replaced"] == "保险丝x2, 散热风扇"
    assert data["cost"] == 120000
    assert data["station_id"] == 1


def test_create_invalid_type():
    headers = _auth_headers()
    resp = client.post("/api/v1/maintenance-records", json={
        "device_id": 1, "title": "x", "type": "bad_type"
    }, headers=headers)
    assert resp.status_code == 422  # Literal 前置 (卡 6031add1)


def test_update_maintenance_record():
    headers = _auth_headers()
    rec = _create_record(headers, title="原始标题")

    resp = client.put(f"/api/v1/maintenance-records/{rec['id']}", json={
        "title": "更新标题",
        "status": "in_progress",
        "cost": 999,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "更新标题"
    assert data["status"] == "in_progress"
    assert data["cost"] == 999


def test_update_status_to_completed():
    headers = _auth_headers()
    rec = _create_record(headers)

    resp = client.put(f"/api/v1/maintenance-records/{rec['id']}", json={
        "status": "completed",
        "solution": "维护完成",
        "completed_at": "2026-06-23T12:00:00",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["solution"] == "维护完成"


def test_update_nonexistent():
    headers = _auth_headers()
    resp = client.put("/api/v1/maintenance-records/99999", json={
        "title": "不存在"
    }, headers=headers)
    assert resp.status_code == 404


def test_update_invalid_status():
    headers = _auth_headers()
    rec = _create_record(headers)

    resp = client.put(f"/api/v1/maintenance-records/{rec['id']}", json={
        "status": "invalid_status"
    }, headers=headers)
    assert resp.status_code == 422  # Literal 前置 (卡 6031add1)


def test_delete_maintenance_record():
    headers = _auth_headers()
    rec = _create_record(headers, title="待删除")

    resp = client.delete(f"/api/v1/maintenance-records/{rec['id']}", headers=headers)
    assert resp.status_code == 200

    # 确认已删除
    resp = client.get(f"/api/v1/maintenance-records/{rec['id']}", headers=headers)
    assert resp.status_code == 404


def test_delete_nonexistent():
    headers = _auth_headers()
    resp = client.delete("/api/v1/maintenance-records/99999", headers=headers)
    assert resp.status_code == 404


# ========== 分页测试 ==========

def test_pagination():
    headers = _auth_headers()
    for i in range(5):
        _create_record(headers, title=f"分页测试_{i}")

    resp = client.get("/api/v1/maintenance-records?page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) <= 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] >= 5
