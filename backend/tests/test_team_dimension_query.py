"""列表 API team_id 查询参数 (卡 2285f54a)。

GET /stations、/devices、/work-orders 三个列表加可选 team_id 查询参数:
- admin 可指定任意团队;
- 普通用户传非本团队 team_id → 403;
- 无参默认行为不变 (按当前登录用户 scoping)。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login(username: str, password: str = "admin123"):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"Authorization": f"Bearer {data.get('token') or data.get('data', {}).get('token')}"}


@pytest.fixture
def env(test_db):
    """两团队 + 各一站一点一单一设备 + 团队内 ENGINEER 用户。"""
    admin_h = _login("admin")

    def _team(name: str) -> int:
        resp = client.post("/api/v1/teams", json={"name": name}, headers=admin_h)
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["id"]

    team_a, team_b = _team("维度查询A组"), _team("维度查询B组")

    def _station(name: str, team_id: int) -> int:
        resp = client.post(
            "/api/v1/stations",
            json={"name": name, "region": "HN", "team_id": team_id},
            headers=admin_h,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["id"]

    st_a = _station("A组站点", team_a)
    st_b = _station("B组站点", team_b)

    def _device(code: str, station_id: int):
        resp = client.post(
            "/api/v1/devices",
            json={"code": code, "name": f"设备{code}", "station_id": str(station_id)},
            headers=admin_h,
        )
        assert resp.status_code == 200, resp.text

    _device("TQA-01", st_a)
    _device("TQB-01", st_b)

    def _wo(desc: str, station_id: int):
        resp = client.post(
            "/api/v1/work-orders",
            json={"fault_desc": desc, "station_id": station_id, "device_id": None},
            headers=admin_h,
        )
        assert resp.status_code == 200, resp.text

    # 工单号 WO-<date>-<HHMMSS> 秒级精度, 同秒两条会撞主键 → 间隔 >1s
    import time
    _wo("A组工单", st_a)
    time.sleep(1.1)
    _wo("B组工单", st_b)

    # 团队A工程师 (operational 权限集含三个 edit 权限)
    from app.models.user import User, UserRole
    from app.api.v1.auth import get_password_hash

    s = test_db["SessionLocal"]()
    s.add(User(
        username="eng_dim_a",
        password_hash=get_password_hash("test123"),
        role=UserRole.ENGINEER,
        status="active",
        team_id=team_a,
    ))
    s.commit()
    s.close()

    eng_h = _login("eng_dim_a", "test123")
    return {"team_a": team_a, "team_b": team_b, "st_a": st_a, "admin_h": admin_h, "eng_h": eng_h}


# ── admin 指定任意团队 ──

def test_admin_query_stations_by_team(env):
    data = client.get(f"/api/v1/stations?team_id={env['team_a']}", headers=env["admin_h"]).json()["data"]
    names = [i["name"] for i in data["items"]]
    assert names == ["A组站点"]


def test_admin_query_devices_by_team(env):
    data = client.get(f"/api/v1/devices?team_id={env['team_b']}", headers=env["admin_h"]).json()["data"]
    codes = [i["code"] for i in data["items"]]
    assert codes == ["TQB-01"]


def test_admin_query_workorders_by_team(env):
    data = client.get(f"/api/v1/work-orders?team_id={env['team_a']}", headers=env["admin_h"]).json()["data"]
    descs = [i["fault_desc"] for i in data["items"]]
    assert descs == ["A组工单"]


# ── 普通用户越权 → 403 ──

@pytest.mark.parametrize("path", ["/api/v1/stations", "/api/v1/devices", "/api/v1/work-orders"])
def test_non_admin_cross_team_403(env, path):
    resp = client.get(f"{path}?team_id={env['team_b']}", headers=env["eng_h"])
    assert resp.status_code == 403, f"{path} 普通用户查他团应 403, 实际 {resp.status_code}"


# ── 普通用户查本团队 → 200 且只含本团队数据 ──

@pytest.mark.parametrize("path", ["/api/v1/stations", "/api/v1/devices", "/api/v1/work-orders"])
def test_non_admin_own_team_ok(env, path):
    resp = client.get(f"{path}?team_id={env['team_a']}", headers=env["eng_h"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1


# ── 无参默认行为不变 ──

def test_default_no_param_admin_sees_all(env):
    assert client.get("/api/v1/stations", headers=env["admin_h"]).json()["data"]["total"] == 2


def test_default_no_param_engineer_scoped(env):
    data = client.get("/api/v1/stations", headers=env["eng_h"]).json()["data"]
    assert [i["name"] for i in data["items"]] == ["A组站点"]
