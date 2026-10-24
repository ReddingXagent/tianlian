"""
站点管理 API 测试
覆盖: list, get, create, update, delete
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


# ========== 鉴权检查 ==========

def test_stations_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/stations")
    assert resp.status_code == 401


def test_station_detail_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/stations/1")
    assert resp.status_code == 401


def test_create_station_requires_auth(anon_client):
    resp = anon_client.post("/api/v1/stations", json={"name": "test", "region": "HN"})
    assert resp.status_code == 401


# ========== CRUD 流程 ==========

def test_list_stations_empty():
    token = _login()
    resp = client.get("/api/v1/stations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "items" in data["data"]


def test_list_stations_with_filters():
    token = _login()
    # status filter
    resp = client.get("/api/v1/stations?status=normal", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # city filter
    resp = client.get("/api/v1/stations?city=上海", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # keyword filter
    resp = client.get("/api/v1/stations?keyword=测试", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_get_station_not_found():
    token = _login()
    resp = client.get("/api/v1/stations/999999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert "不存在" in resp.json()["message"]


def test_create_station_success():
    """创建站点 - 自动生成编码"""
    token = _login()
    payload = {
        "name": "测试站点001",
        "region": "HN",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
        "address": "测试路1号",
        "status": "normal",
    }
    resp = client.post(
        "/api/v1/stations",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["name"] == "测试站点001"
    assert data["data"]["code"].startswith("Z")  # 自动生成编码
    station_id = data["data"]["id"]

    # 可查询
    resp = client.get(f"/api/v1/stations/{station_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == station_id


def test_create_station_duplicate_code_auto():
    """测试自动生成编码（编码不会重复）"""
    token = _login()
    # 两次创建应该得到不同的编码
    r1 = client.post("/api/v1/stations", json={"name": "站点A", "region": "HN"}, headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200

    r2 = client.post("/api/v1/stations", json={"name": "站点B", "region": "HN"}, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r1.json()["data"]["code"] != r2.json()["data"]["code"]  # 编码不同


def test_update_station_success():
    token = _login()
    # 先创建
    create_resp = client.post(
        "/api/v1/stations",
        json={"name": "原站点名", "region": "HN"},
        headers={"Authorization": f"Bearer {token}"}
    )
    station_id = create_resp.json()["data"]["id"]

    # 更新
    resp = client.put(
        f"/api/v1/stations/{station_id}",
        json={"name": "新站点名", "city": "北京市"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["name"] == "新站点名"
    assert data["data"]["city"] == "北京市"


def test_update_station_not_found():
    token = _login()
    resp = client.put(
        "/api/v1/stations/999999",
        json={"name": "不存在"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404


def test_delete_station_success():
    token = _login()
    create_resp = client.post(
        "/api/v1/stations",
        json={"name": "待删除站点", "region": "HN"},
        headers={"Authorization": f"Bearer {token}"}
    )
    station_id = create_resp.json()["data"]["id"]

    resp = client.delete(f"/api/v1/stations/{station_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "已删除" in resp.json()["message"]

    # 验证已删除
    resp = client.get(f"/api/v1/stations/{station_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ========== 站点分配团队 ==========

def test_assign_station_success():
    """分配站点给运维团队 - 成功"""
    token = _login()
    # 先创建团队
    team_resp = client.post(
        "/api/v1/teams",
        json={"name": "分配测试团队", "region": "HN"},
        headers={"Authorization": f"Bearer {token}"}
    )
    team_id = team_resp.json()["data"]["id"]

    # 创建站点
    create_resp = client.post(
        "/api/v1/stations",
        json={"name": "待分配站点", "region": "HN"},
        headers={"Authorization": f"Bearer {token}"}
    )
    station_id = create_resp.json()["data"]["id"]

    # 分配
    resp = client.put(
        f"/api/v1/stations/{station_id}/assign",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["team_id"] == team_id
    assert data["data"]["team_name"] == "分配测试团队"

    # 验证 site.team_id 已更新
    detail_resp = client.get(f"/api/v1/stations/{station_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail_resp.json()["data"]["team_id"] == team_id


def test_assign_station_not_found():
    """分配不存在的站点 - 404"""
    token = _login()
    resp = client.put(
        "/api/v1/stations/999999/assign",
        json={"team_id": 1},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404
    assert "不存在" in resp.json()["message"]


def test_assign_station_team_not_found():
    """分配到不存在的团队 - 400"""
    token = _login()
    create_resp = client.post(
        "/api/v1/stations",
        json={"name": "无团队站点", "region": "HN"},
        headers={"Authorization": f"Bearer {token}"}
    )
    station_id = create_resp.json()["data"]["id"]

    resp = client.put(
        f"/api/v1/stations/{station_id}/assign",
        json={"team_id": 99999},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["message"]


# ========== 审计归属 (卡 3c751d01) ==========

def test_station_audit_records_real_operator():
    """创建/删除站点的审计记录归属真实操作用户，而非 user_id=0/"admin" 硬编码"""
    from app.models.audit_log import AuditLog
    from app.models.user import User
    token = _login()
    import app.core.database as _dbmod
    s = _dbmod.SessionLocal()
    admin = s.query(User).filter(User.username == "admin").first()
    assert admin is not None and admin.id != 0

    resp = client.post("/api/v1/stations", headers={"Authorization": f"Bearer {token}"},
                       json={"name": "审计归属测试站", "region": "HN"})
    assert resp.status_code == 200
    station_id = resp.json()["data"]["id"]

    log = (s.query(AuditLog)
           .filter(AuditLog.module == "stations", AuditLog.action == "create",
                   AuditLog.target_id == str(station_id))
           .order_by(AuditLog.id.desc()).first())
    assert log is not None, "站点创建应产生审计记录"
    assert log.user_id == admin.id
    assert log.username == admin.username

    resp = client.delete(f"/api/v1/stations/{station_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    log = (s.query(AuditLog)
           .filter(AuditLog.module == "stations", AuditLog.action == "delete",
                   AuditLog.target_id == str(station_id))
           .order_by(AuditLog.id.desc()).first())
    assert log is not None, "站点删除应产生审计记录"
    assert log.user_id == admin.id
    assert log.username == admin.username
