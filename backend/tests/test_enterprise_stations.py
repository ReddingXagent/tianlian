"""
企业场站绑定 API 测试

覆盖:
- GET /enterprises/{id}/stations — 已绑定场站列表
- PUT /enterprises/{id}/stations — 绑定/解绑
- 越权绑定其他团队场站被拒 (403)
- 创建企业时可选传 station_ids
- GET /enterprises/{id}/available-stations — 可选场站列表
"""
import pytest


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def _create_team(client, headers, name="经营团队A"):
    """创建一个团队"""
    from app.models.user import Team
    s = client._sesh
    team = Team(name=name, code=name.replace("团队", "T"))
    s.add(team)
    s.commit()
    s.refresh(team)
    return team


def _create_station(client, team_id=None, name="测试场站", code="ST001"):
    """直接通过 session 创建场站"""
    from app.models.station import Station, StationStatus
    s = client._sesh
    st = Station(name=name, code=code, status=StationStatus.NORMAL, team_id=team_id)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


def _create_enterprise(client, headers, code="ENT_ST", name="场站测试企业", owner_team_id=None, station_ids=None):
    payload = {
        "name": name, "code": code, "status": "active",
    }
    if owner_team_id:
        payload["owner_team_id"] = owner_team_id
    if station_ids:
        payload["station_ids"] = station_ids
    return client.post("/api/v1/enterprises", json=payload, headers=headers)


def test_get_enterprise_stations_empty(client, seed_users):
    """企业未绑定场站时返回空列表"""
    headers = _auth(client)
    ent = _create_enterprise(client, headers, code="ENT_S001").json()["data"]
    resp = client.get(f"/api/v1/enterprises/{ent['id']}/stations", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_bind_stations_success(client, seed_users):
    """成功绑定场站"""
    headers = _auth(client)
    team = _create_team(client, headers)
    st1 = _create_station(client, team_id=team.id, name="场站A", code="STA_BIND1")
    st2 = _create_station(client, team_id=team.id, name="场站B", code="STA_BIND2")

    ent = _create_enterprise(client, headers, code="ENT_BIND1", owner_team_id=team.id).json()["data"]

    # 绑定
    resp = client.put(f"/api/v1/enterprises/{ent['id']}/stations", json={
        "station_ids": [st1.id, st2.id]
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert {s["id"] for s in data} == {st1.id, st2.id}

    # GET 确认
    get_resp = client.get(f"/api/v1/enterprises/{ent['id']}/stations", headers=headers)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) == 2


def test_unbind_stations(client, seed_users):
    """解绑场站（传空列表覆盖）"""
    headers = _auth(client)
    team = _create_team(client, headers)
    st = _create_station(client, team_id=team.id, name="场站C", code="STA_UNBIND")

    ent = _create_enterprise(client, headers, code="ENT_UNBIND", owner_team_id=team.id).json()["data"]

    # 先绑定
    client.put(f"/api/v1/enterprises/{ent['id']}/stations", json={"station_ids": [st.id]}, headers=headers)
    # 再解绑（传空列表）
    resp = client.put(f"/api/v1/enterprises/{ent['id']}/stations", json={"station_ids": []}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_bind_other_team_station_forbidden(client, seed_users):
    """绑定其他团队的场站被拒 (403)"""
    headers = _auth(client)
    team_a = _create_team(client, headers, name="团队A")
    team_b = _create_team(client, headers, name="团队B")

    # 场站属于团队B
    st_other = _create_station(client, team_id=team_b.id, name="外部场站", code="STA_OTHER")

    # 企业属于团队A
    ent = _create_enterprise(client, headers, code="ENT_CROSS", owner_team_id=team_a.id).json()["data"]

    # 尝试绑定团队B的场站
    resp = client.put(f"/api/v1/enterprises/{ent['id']}/stations", json={
        "station_ids": [st_other.id]
    }, headers=headers)
    assert resp.status_code == 403
    assert "不属于" in resp.json()["detail"]


def test_create_enterprise_with_station_ids(client, seed_users):
    """创建企业时传 station_ids 自动绑定"""
    headers = _auth(client)
    team = _create_team(client, headers, name="团队创健")
    st = _create_station(client, team_id=team.id, name="创建绑定场站", code="STA_CREATE")

    resp = _create_enterprise(client, headers, code="ENT_CREATE_BIND",
                              owner_team_id=team.id, station_ids=[st.id])
    assert resp.status_code == 200
    ent_id = resp.json()["data"]["id"]

    # 验证绑定
    get_resp = client.get(f"/api/v1/enterprises/{ent_id}/stations", headers=headers)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) == 1
    assert get_resp.json()["data"][0]["id"] == st.id


def test_available_stations_filtered_by_team(client, seed_users):
    """可选场站列表按 owner_team_id 过滤"""
    headers = _auth(client)
    team_a = _create_team(client, headers, name="团队可用A")
    team_b = _create_team(client, headers, name="团队可用B")

    st_a = _create_station(client, team_id=team_a.id, name="团队A场站", code="STA_AVAIL_A")
    st_b = _create_station(client, team_id=team_b.id, name="团队B场站", code="STA_AVAIL_B")

    ent = _create_enterprise(client, headers, code="ENT_AVAIL", owner_team_id=team_a.id).json()["data"]

    resp = client.get(f"/api/v1/enterprises/{ent['id']}/available-stations", headers=headers)
    assert resp.status_code == 200
    station_ids = [s["id"] for s in resp.json()["data"]]
    assert st_a.id in station_ids
    assert st_b.id not in station_ids


def test_stations_endpoint_404_for_nonexistent_enterprise(client, seed_users):
    """不存在的企业查场站返回 404"""
    headers = _auth(client)
    resp = client.get("/api/v1/enterprises/999999/stations", headers=headers)
    assert resp.status_code == 404


def test_enterprise_owner_team_id_in_detail(client, seed_users):
    """企业详情包含 owner_team_id"""
    headers = _auth(client)
    team = _create_team(client, headers, name="团队详情")
    ent = _create_enterprise(client, headers, code="ENT_TEAM_DETAIL", owner_team_id=team.id).json()["data"]
    assert ent["owner_team_id"] == team.id

    # GET 详情
    detail = client.get(f"/api/v1/enterprises/{ent['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["owner_team_id"] == team.id
