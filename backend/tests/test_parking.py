"""
停车折扣方案管理 API 测试

覆盖: /api/v1/parking/discounts/*
- 列表（分页/筛选）
- 创建（含折扣类型校验）
- 详情 / 更新 / 删除
"""
import pytest


@pytest.fixture(autouse=True)
def _seed_station(client):
    """seed station(id=1) 供折扣 CRUD。

    team scoping（任务卡 1c19b59a）后 create/update/delete 折扣前置校验站点归属，
    站点不存在 → 404；admin 经 is_platform_admin 豁免 team，仅需站点存在故补 seed。
    """
    from app.models.station import Station, StationStatus
    s = client._sesh
    if not s.query(Station).filter(Station.id == 1).first():
        s.add(Station(id=1, name="停车测试站", code="PKG_STA_001", status=StationStatus.NORMAL))
    s.commit()


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def _create(client, headers, station_id=1, merchant="测试商户", dtype="free_minutes"):
    return client.post("/api/v1/parking/discounts", json={
        "station_id": station_id,
        "merchant_name": merchant,
        "discount_type": dtype,
        "free_minutes": 30,
        "discount_percent": 0,
        "fixed_amount": 0,
        "is_active": True,
    }, headers=headers)


def test_list_parking_discounts(client, seed_users):
    headers = _auth(client)
    resp = client.get("/api/v1/parking/discounts", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
    assert "items" in resp.json()["data"]


def test_create_and_get_discount(client, seed_users):
    headers = _auth(client)
    create = _create(client, headers, merchant="万达广场")
    assert create.status_code == 200
    d = create.json()["data"]
    assert d["id"] > 0
    assert d["merchant_name"] == "万达广场"
    assert d["discount_type"] == "free_minutes"
    assert d["free_minutes"] == 30

    detail = client.get(f"/api/v1/parking/discounts/{d['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == d["id"]


def test_create_invalid_discount_type(client, seed_users):
    headers = _auth(client)
    resp = _create(client, headers, dtype="invalid_type")
    assert resp.status_code == 400
    assert "折扣类型" in resp.json()["detail"]


def test_update_discount(client, seed_users):
    headers = _auth(client)
    d = _create(client, headers, merchant="更新前").json()["data"]
    resp = client.put(f"/api/v1/parking/discounts/{d['id']}", json={
        "merchant_name": "更新后",
        "discount_type": "percentage",
        "discount_percent": 80,
        "is_active": False,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["merchant_name"] == "更新后"
    assert data["discount_type"] == "percentage"
    assert float(data["discount_percent"]) == 80.0
    assert data["is_active"] is False


def test_delete_discount(client, seed_users):
    headers = _auth(client)
    d = _create(client, headers, merchant="删除目标").json()["data"]
    resp = client.delete(f"/api/v1/parking/discounts/{d['id']}", headers=headers)
    assert resp.status_code == 200
    miss = client.get(f"/api/v1/parking/discounts/{d['id']}", headers=headers)
    assert miss.status_code == 404


def test_list_filter_by_station_and_active(client, seed_users):
    headers = _auth(client)
    _create(client, headers, station_id=1001, merchant="站点A商户")
    _create(client, headers, station_id=1002, merchant="站点B商户")
    # 按站点筛选
    resp = client.get("/api/v1/parking/discounts?station_id=1001", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(it["station_id"] == 1001 for it in items)
    # 按启用状态筛选
    resp2 = client.get("/api/v1/parking/discounts?is_active=true", headers=headers)
    assert all(it["is_active"] is True for it in resp2.json()["data"]["items"])


def test_get_nonexistent_discount(client, seed_users):
    headers = _auth(client)
    resp = client.get("/api/v1/parking/discounts/999999", headers=headers)
    assert resp.status_code == 404


# ════════════════════════════════════════════════════════════
# DB 异常路径 (卡 a6e2e562): 业务查询/写库抛异常 → 503, 不裸抛 stack
# ════════════════════════════════════════════════════════════
def _stub_auth_and_boom_db(client, monkeypatch, *, query_chain="first"):
    """stub 鉴权链 (enforce_auth + get_current_user) 为 admin + override get_db 为炸 session。

    enforce_auth 内部直接函数调用 get_current_user(token, db) —— 若 db 为炸 session 会先于
    端点 try 块炸。故 override enforce_auth 为 no-op、get_current_user 返回内存 admin,
    鉴权完全不碰 boom db; require_write_permission 走 SessionLocal 真实测试库, admin 恒通过。
    仅端点业务查询 (db=boom) 在 try 块内炸。

    用 monkeypatch.setitem 管理 dependency_overrides, 测试结束自动还原 (避免污染 session 级 app)。
    """
    from unittest.mock import MagicMock
    from sqlalchemy.exc import OperationalError
    from app.api.v1.auth import enforce_auth, get_current_user
    from app.core.database import get_db
    from app.models.user import User, UserRole

    admin = User(id=1, username="admin", role=UserRole.ADMIN, status="active")
    overrides = client.app.dependency_overrides
    monkeypatch.setitem(overrides, enforce_auth, lambda: None)
    monkeypatch.setitem(overrides, get_current_user, lambda: admin)

    boom = MagicMock()
    chained = MagicMock()
    chained.filter.return_value = chained
    chained.join.return_value = chained
    chained.order_by.return_value = chained
    chained.offset.return_value = chained
    chained.limit.return_value = chained
    getattr(chained, query_chain).side_effect = OperationalError(
        "SELECT 1", {}, Exception("db down")
    )
    boom.query.return_value = chained
    monkeypatch.setitem(overrides, get_db, lambda: boom)
    return boom


def test_list_db_error_503(client, seed_users, monkeypatch):
    """列表查询 (.all) 抛异常 → 503, 不裸抛 stack。"""
    _stub_auth_and_boom_db(client, monkeypatch, query_chain="all")
    resp = client.get("/api/v1/parking/discounts")
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == "服务暂时不可用"


def test_create_db_error_503(client, seed_users, monkeypatch):
    """创建写库 (commit 前 .first 查重不存在 → add+commit) 抛异常 → 503。

    注: create 端点先 assert_station_team_access(走 boom db 查 Station).first —— boom.first 炸。
    """
    _stub_auth_and_boom_db(client, monkeypatch, query_chain="first")
    resp = client.post("/api/v1/parking/discounts", json={
        "station_id": 1, "discount_type": "free_minutes", "free_minutes": 30,
    })
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == "服务暂时不可用"


def test_business_404_not_swallowed_by_503(client, seed_users):
    """业务 HTTPException (404) 不应被 503 兜底吞掉 —— 验证 except HTTPException: raise。"""
    headers = _auth(client)
    # 真实库, 不 stub: 详情查不到 → 404 (非 503)
    resp = client.get("/api/v1/parking/discounts/999999", headers=headers)
    assert resp.status_code == 404
