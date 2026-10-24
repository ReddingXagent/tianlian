"""
/fleet/enterprises 路由别名测试

验证 enterprises.router 在 /fleet 前缀下挂载后:
- GET    /api/v1/fleet/enterprises          列表
- POST   /api/v1/fleet/enterprises          创建
- GET    /api/v1/fleet/enterprises/{id}     详情
- PUT    /api/v1/fleet/enterprises/{id}     更新
- DELETE /api/v1/fleet/enterprises/{id}     删除

并验证别名与原 /enterprises 路由共享同一份数据（同一 router 两前缀挂载，
不是独立实现），且原 /enterprises 路由不受影响。
"""
import pytest


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def _create_via_fleet(client, headers, code="FLEET001", name="车队企业A",
                      balance=500.0, credit_limit=3000.0):
    return client.post("/api/v1/fleet/enterprises", json={
        "name": name, "code": code, "contact": "李四", "phone": "13900000001",
        "balance": balance, "credit_limit": credit_limit, "status": "active",
    }, headers=headers)


def test_fleet_alias_list(client, seed_users):
    """GET /fleet/enterprises 返回 200 + 标准分页结构"""
    headers = _auth(client)
    resp = client.get("/api/v1/fleet/enterprises", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] >= 0
    assert isinstance(body["data"]["items"], list)


def test_fleet_alias_create_and_detail(client, seed_users):
    """POST /fleet/enterprises 创建 + GET /fleet/enterprises/{id} 详情"""
    headers = _auth(client)
    created = _create_via_fleet(client, headers)
    assert created.status_code == 200, created.text
    ent = created.json()["data"]
    assert ent["id"] > 0
    assert ent["code"] == "FLEET001"

    detail = client.get(f"/api/v1/fleet/enterprises/{ent['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "车队企业A"


def test_fleet_alias_update(client, seed_users):
    """PUT /fleet/enterprises/{id} 更新"""
    headers = _auth(client)
    ent = _create_via_fleet(client, headers, code="FLEET_UPD").json()["data"]
    resp = client.put(f"/api/v1/fleet/enterprises/{ent['id']}", json={
        "name": "车队企业-改名", "balance": 8888.0, "status": "suspended",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "车队企业-改名"
    assert data["balance"] == 8888.0
    assert data["status"] == "suspended"


def test_fleet_alias_delete(client, seed_users):
    """DELETE /fleet/enterprises/{id} 删除后再查应 404"""
    headers = _auth(client)
    # 卡 21205721: 非零余额/信用额度的企业 409 拒删(账本完整性优先),
    # 删除用例须创建零余额零额度的干净企业
    ent = _create_via_fleet(
        client, headers, code="FLEET_DEL",
        balance=0.0, credit_limit=0.0,
    ).json()["data"]
    deleted = client.delete(f"/api/v1/fleet/enterprises/{ent['id']}", headers=headers)
    assert deleted.status_code == 200
    miss = client.get(f"/api/v1/fleet/enterprises/{ent['id']}", headers=headers)
    assert miss.status_code == 404


def test_fleet_alias_requires_auth(anon_client):
    """未登录访问 /fleet/enterprises 返回 401（与原路由一致的鉴权）"""
    resp = anon_client.get("/api/v1/fleet/enterprises")
    assert resp.status_code == 401


def test_fleet_alias_shares_data_with_enterprises_route(client, seed_users):
    """别名与原 /enterprises 路由共享同一份数据：
    经 /fleet/enterprises 创建，原 /enterprises 列表可读到；反之亦然。
    证明是同一 router 的双前缀挂载，而非独立实现。"""
    headers = _auth(client)

    # 经别名创建
    ent = _create_via_fleet(client, headers, code="FLEET_SHARED").json()["data"]

    # 原路由列表可见该企业
    listing = client.get("/api/v1/enterprises", headers=headers).json()["data"]["items"]
    assert any(it["id"] == ent["id"] and it["code"] == "FLEET_SHARED" for it in listing)

    # 原路由详情可读
    detail = client.get(f"/api/v1/enterprises/{ent['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == ent["id"]


def test_original_enterprises_route_still_works(client, seed_users):
    """原有 /enterprises 路由不受别名挂载影响（回归保护）"""
    headers = _auth(client)
    resp = client.post("/api/v1/enterprises", json={
        "name": "原路由企业", "code": "ORIG001", "status": "active",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["code"] == "ORIG001"
    listing = client.get("/api/v1/enterprises", headers=headers)
    assert listing.status_code == 200
