"""
工单扩展5端点测试
覆盖: /work-orders — checkin / support / spare-parts / rate / stats
路径与字段签名严格对齐 frontend/src/api/index.ts workorderAPI。
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


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_wo(headers, **overrides):
    defaults = dict(fault_desc="测试故障", type="repair", level="warning")
    defaults.update(overrides)
    resp = client.post("/api/v1/work-orders", json=defaults, headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]


def _to_active(h, wo_id):
    """推进到处理中（已接单 → 处理中）。"""
    client.post(f"/api/v1/work-orders/{wo_id}/accept", headers=h)
    client.post(f"/api/v1/work-orders/{wo_id}/start", headers=h)


def _to_completed(h, wo_id):
    """推进到已验收完成。"""
    _to_active(h, wo_id)
    client.post(f"/api/v1/work-orders/{wo_id}/complete", headers=h)
    client.post(f"/api/v1/work-orders/{wo_id}/verify", headers=h)


# ========== 到场签到 ==========

def test_checkin_success():
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/checkin", json={
        "latitude": 31.2304, "longitude": 121.4737,
        "address": "上海市浦东新区", "note": "已到场", "photo_url": "https://cdn/x.jpg",
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["order_id"] == wo["id"]
    assert data["latitude"] == 31.2304
    assert data["photo_url"] == "https://cdn/x.jpg"


def test_checkin_not_found():
    h = _auth_headers()
    resp = client.post("/api/v1/work-orders/WO-NOTEXIST/checkin", json={"note": "x"}, headers=h)
    assert resp.status_code == 404


def test_checkin_wrong_status():
    """待处理（无人接单）工单不允许签到 → 409。"""
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/checkin", json={"note": "x"}, headers=h)
    assert resp.status_code == 409


# ========== 申请支援 ==========

def test_support_success():
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/support", json={
        "reason": "逆变器固件异常需远程协助", "remote": True,
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reason"] == "逆变器固件异常需远程协助"
    assert data["remote"] is True


def test_support_not_found():
    h = _auth_headers()
    resp = client.post("/api/v1/work-orders/WO-NOTEXIST/support", json={"reason": "x"}, headers=h)
    assert resp.status_code == 404


def test_support_missing_reason():
    """reason 必填 → 422。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/support", json={"remote": True}, headers=h)
    assert resp.status_code == 422


def test_support_wrong_status():
    h = _auth_headers()
    wo = _create_wo(h)
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/support", json={"reason": "x"}, headers=h)
    assert resp.status_code == 409


# ========== 申请备件 ==========

def test_spare_parts_success():
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/spare-parts", json={
        "part_name": "IGBT模块", "part_model": "FF50R12", "quantity": 2, "reason": "原模块烧毁",
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["part_name"] == "IGBT模块"
    assert data["quantity"] == 2
    assert data["part_model"] == "FF50R12"


def test_spare_parts_not_found():
    h = _auth_headers()
    resp = client.post("/api/v1/work-orders/WO-NOTEXIST/spare-parts",
                       json={"part_name": "x", "quantity": 1, "reason": "x"}, headers=h)
    assert resp.status_code == 404


def test_spare_parts_invalid_quantity():
    """quantity 必须 >= 1 → 422。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/spare-parts",
                       json={"part_name": "x", "quantity": 0, "reason": "x"}, headers=h)
    assert resp.status_code == 422


# ========== 验收评价 ==========

def test_rate_success():
    h = _auth_headers()
    wo = _create_wo(h)
    _to_completed(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/rate", json={
        "response_rating": 5, "quality_rating": 4, "attitude_rating": 5, "comment": "响应很快",
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["response_rating"] == 5
    assert data["quality_rating"] == 4
    assert data["attitude_rating"] == 5
    assert data["comment"] == "响应很快"


def test_rate_not_found():
    h = _auth_headers()
    resp = client.post("/api/v1/work-orders/WO-NOTEXIST/rate",
                       json={"response_rating": 5, "quality_rating": 5, "attitude_rating": 5}, headers=h)
    assert resp.status_code == 404


def test_rate_invalid_rating():
    """星级必须 1-5 → 422。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_completed(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/rate",
                       json={"response_rating": 6, "quality_rating": 5, "attitude_rating": 5}, headers=h)
    assert resp.status_code == 422


def test_rate_wrong_status():
    """未完成工单不允许评价 → 409。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_active(h, wo["id"])
    resp = client.post(f"/api/v1/work-orders/{wo['id']}/rate",
                       json={"response_rating": 5, "quality_rating": 5, "attitude_rating": 5}, headers=h)
    assert resp.status_code == 409


def test_rate_duplicate():
    """同一工单只能评价一次 → 第二次 409。"""
    h = _auth_headers()
    wo = _create_wo(h)
    _to_completed(h, wo["id"])
    payload = {"response_rating": 5, "quality_rating": 5, "attitude_rating": 5}
    r1 = client.post(f"/api/v1/work-orders/{wo['id']}/rate", json=payload, headers=h)
    assert r1.status_code == 200
    r2 = client.post(f"/api/v1/work-orders/{wo['id']}/rate", json=payload, headers=h)
    assert r2.status_code == 409


# ========== 工单统计 ==========

def test_stats_success():
    h = _auth_headers()
    _create_wo(h)
    resp = client.get("/api/v1/work-orders/stats", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert "status_distribution" in data
    assert "level_distribution" in data
    assert "type_distribution" in data


def test_stats_group_by_date():
    h = _auth_headers()
    _create_wo(h)
    resp = client.get("/api/v1/work-orders/stats?group_by=date", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "groups" in data
    assert isinstance(data["groups"], dict)


def test_stats_group_by_status():
    h = _auth_headers()
    _create_wo(h)
    resp = client.get("/api/v1/work-orders/stats?group_by=status", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # pending 工单应被聚合到 status 分组
    assert data["groups"].get("pending", 0) >= 1


def test_stats_route_not_swallowed():
    """关键：/stats 不能被 /{workorder_id} 路由吞掉。"""
    h = _auth_headers()
    resp = client.get("/api/v1/work-orders/stats", headers=h)
    assert resp.status_code != 404
