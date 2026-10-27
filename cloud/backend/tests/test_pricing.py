"""
定价管理 API 测试 - Phase42

覆盖 backend/app/api/v1/pricing.py (时段电价 CRUD):
- GET    /api/v1/pricing          列表(筛选/分页/空数据)
- GET    /api/v1/pricing/{id}     详情(404)
- POST   /api/v1/pricing          创建(正常/无效时段类型/无效时间格式/缺必填)
- PUT    /api/v1/pricing/{id}     更新(404)
- DELETE /api/v1/pricing/{id}     删除(404)

认证模式参考 test_fleet_settlement.py: 全局 TestClient(app) + test_db autouse + Bearer token。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture (覆盖 SessionLocal + seed admin)。每个测试独立 DB。"""
    pass


def _auth_headers():
    """登录 admin 并返回 Bearer 认证头。"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _create_pricing(**overrides):
    """创建定价规则辅助。"""
    payload = {
        "name": "测试规则",
        "period_type": "peak",
        "start_time": "10:00",
        "end_time": "12:00",
        "electricity_price": 1.0,
        "service_fee_rate": 0.5,
        "parking_fee_per_hour": 0.0,
        "idle_penalty_per_min": 0.0,
        "is_active": True,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/pricing", json=payload, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ═══════════════════════════════════════════════════════════════
# 创建
# ═══════════════════════════════════════════════════════════════

def test_create_pricing():
    """正常创建定价规则"""
    data = _create_pricing(name="尖峰电价", period_type="peak", electricity_price=1.2)
    assert data["name"] == "尖峰电价"
    assert data["period_type"] == "peak"
    assert data["electricity_price"] == 1.2
    assert data["service_fee_rate"] == 0.5
    assert data["is_active"] is True
    assert "id" in data
    # start_time/end_time 是 Time 列，str 表示形如 "10:00:00"
    assert data["start_time"] is not None
    assert data["end_time"] is not None


def test_create_all_period_types():
    """四种时段类型均可创建"""
    for pt in ("peak", "shoulder", "valley", "flat"):
        resp = client.post("/api/v1/pricing", json={
            "name": f"规则-{pt}", "period_type": pt,
            "start_time": "10:00", "end_time": "12:00",
        }, headers=_auth_headers())
        assert resp.status_code == 200, f"{pt} 创建失败: {resp.text}"
        assert resp.json()["data"]["period_type"] == pt


def test_create_invalid_period_type():
    """无效时段类型 → 400"""
    resp = client.post("/api/v1/pricing", json={
        "name": "坏类型", "period_type": "invalid_xyz",
        "start_time": "10:00", "end_time": "12:00",
    }, headers=_auth_headers())
    assert resp.status_code == 400


def test_create_invalid_time_format():
    """无效时间格式 → 400"""
    resp = client.post("/api/v1/pricing", json={
        "name": "坏时间", "period_type": "flat",
        "start_time": "25:99", "end_time": "12:00",
    }, headers=_auth_headers())
    assert resp.status_code == 400


def test_create_missing_required_field():
    """缺少必填字段 name → 422"""
    resp = client.post("/api/v1/pricing", json={
        "period_type": "flat", "start_time": "10:00", "end_time": "12:00",
    }, headers=_auth_headers())
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 列表
# ═══════════════════════════════════════════════════════════════

def test_list_pricing_and_filter():
    """列表 + 时段筛选 + 启用筛选"""
    _create_pricing(name="尖", period_type="peak")
    _create_pricing(name="平", period_type="flat")
    _create_pricing(name="谷", period_type="valley")

    # 全量
    resp = client.get("/api/v1/pricing", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 3

    # 时段筛选
    resp = client.get("/api/v1/pricing?period_type=peak", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert all(i["period_type"] == "peak" for i in data["items"])

    # 启用筛选
    resp = client.get("/api/v1/pricing?is_active=true", headers=_auth_headers())
    assert resp.status_code == 200
    assert all(i["is_active"] is True for i in resp.json()["data"]["items"])


def test_list_pricing_empty():
    """空数据列表"""
    resp = client.get("/api/v1/pricing", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


def test_list_pricing_pagination():
    """分页"""
    for i in range(5):
        _create_pricing(name=f"规则{i}")
    resp = client.get("/api/v1/pricing?page=1&page_size=2", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] >= 5
    assert data["page"] == 1
    assert data["page_size"] == 2


# ═══════════════════════════════════════════════════════════════
# 详情
# ═══════════════════════════════════════════════════════════════

def test_get_pricing_detail():
    data = _create_pricing(name="详情规则")
    pid = data["id"]
    resp = client.get(f"/api/v1/pricing/{pid}", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == pid
    assert resp.json()["data"]["name"] == "详情规则"


def test_get_pricing_not_found():
    resp = client.get("/api/v1/pricing/99999", headers=_auth_headers())
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 更新
# ═══════════════════════════════════════════════════════════════

def test_update_pricing():
    data = _create_pricing(name="旧名", electricity_price=1.0, is_active=True)
    pid = data["id"]
    resp = client.put(f"/api/v1/pricing/{pid}", json={
        "name": "新名", "period_type": "valley",
        "electricity_price": 1.5, "is_active": False,
    }, headers=_auth_headers())
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["name"] == "新名"
    assert d["period_type"] == "valley"
    assert d["electricity_price"] == 1.5
    assert d["is_active"] is False


def test_update_pricing_not_found():
    resp = client.put("/api/v1/pricing/99999", json={"name": "x"}, headers=_auth_headers())
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 删除
# ═══════════════════════════════════════════════════════════════

def test_delete_pricing():
    data = _create_pricing(name="要删除")
    pid = data["id"]
    resp = client.delete(f"/api/v1/pricing/{pid}", headers=_auth_headers())
    assert resp.status_code == 200
    # 删除后查询应 404
    resp2 = client.get(f"/api/v1/pricing/{pid}", headers=_auth_headers())
    assert resp2.status_code == 404


def test_delete_pricing_not_found():
    resp = client.delete("/api/v1/pricing/99999", headers=_auth_headers())
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════

def test_unauthorized_request_rejected():
    """无 token 访问受保护端点 → 401/403"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/pricing")
    assert resp.status_code in (401, 403)
