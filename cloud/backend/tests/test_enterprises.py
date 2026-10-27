"""
企业账户管理 API 测试

覆盖: /api/v1/enterprises/*
- 列表（分页/筛选/搜索）
- 创建（含编码唯一性校验、状态校验）
- 详情 / 更新 / 删除
"""
import pytest


def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def _create(client, headers, code="ENT001", name="测试企业A", status="active",
            balance=1000.0, credit_limit=5000.0):
    return client.post("/api/v1/enterprises", json={
        "name": name, "code": code, "contact": "张三", "phone": "13800000001",
        "balance": balance, "credit_limit": credit_limit, "status": status,
    }, headers=headers)


def test_list_enterprises_empty(client, seed_users):
    headers = _auth(client)
    resp = client.get("/api/v1/enterprises", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] >= 0


def test_create_and_get_enterprise(client, seed_users):
    headers = _auth(client)
    create = _create(client, headers)
    assert create.status_code == 200
    ent = create.json()["data"]
    assert ent["id"] > 0
    assert ent["code"] == "ENT001"
    assert ent["balance"] == 1000.0

    # 详情
    detail = client.get(f"/api/v1/enterprises/{ent['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "测试企业A"


def test_create_duplicate_code(client, seed_users):
    headers = _auth(client)
    assert _create(client, headers, code="DUP001").status_code == 200
    dup = _create(client, headers, code="DUP001", name="重复企业")
    assert dup.status_code == 400
    assert "已存在" in dup.json()["detail"]


def test_create_invalid_status(client, seed_users):
    headers = _auth(client)
    resp = _create(client, headers, code="ENT_BAD", status="frozen")
    assert resp.status_code == 422


def test_update_enterprise(client, seed_users):
    headers = _auth(client)
    ent = _create(client, headers, code="ENT_UPD").json()["data"]
    resp = client.put(f"/api/v1/enterprises/{ent['id']}", json={
        "name": "更新后企业", "balance": 2000.0, "status": "suspended",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "更新后企业"
    assert data["balance"] == 2000.0
    assert data["status"] == "suspended"


def test_delete_enterprise(client, seed_users):
    headers = _auth(client)
    # 卡 21205721: 非零余额/信用额度的企业 409 拒删(账本完整性优先),
    # 删除用例须创建零余额零额度的干净企业
    ent = _create(
        client, headers, code="ENT_DEL",
        balance=0.0, credit_limit=0.0,
    ).json()["data"]
    deleted = client.delete(f"/api/v1/enterprises/{ent['id']}", headers=headers)
    assert deleted.status_code == 200
    # 删除后查询应 404
    miss = client.get(f"/api/v1/enterprises/{ent['id']}", headers=headers)
    assert miss.status_code == 404


def test_get_nonexistent_enterprise(client, seed_users):
    headers = _auth(client)
    resp = client.get("/api/v1/enterprises/999999", headers=headers)
    assert resp.status_code == 404


def test_list_filter_and_search(client, seed_users):
    headers = _auth(client)
    _create(client, headers, code="ENT_F1", name="北京新能源公司")
    _create(client, headers, code="ENT_F2", name="上海物流公司", status="inactive")
    # 关键字搜索
    resp = client.get("/api/v1/enterprises?keyword=北京", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any("北京" in it["name"] for it in items)
    # 状态筛选
    resp2 = client.get("/api/v1/enterprises?status=inactive", headers=headers)
    assert all(it["status"] == "inactive" for it in resp2.json()["data"]["items"])


def test_enterprises_requires_auth(anon_client):
    """未登录访问返回 401"""
    resp = anon_client.get("/api/v1/enterprises")
    assert resp.status_code == 401


# ========== 团队隔离（任务卡 708350b3）==========

import bcrypt


@pytest.fixture
def team_pair(client):
    """两团队 + 两团队级用户(admin 角色以外的运营用户) + token。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="企业团队A", code="ENTTA")
    tb = Team(name="企业团队B", code="ENTTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "ent123456"
    ua = User(
        username="ent_mgr_a", real_name="A运营", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="ent_mgr_b", real_name="B运营", role=UserRole.ENGINEER,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "tokens": {"a": _tok("ent_mgr_a"), "b": _tok("ent_mgr_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_enterprise(session, owner_team_id, code, name="企业"):
    from app.models.enterprise import Enterprise, EnterpriseStatus
    ent = Enterprise(
        name=name, code=code, status=EnterpriseStatus.ACTIVE,
        owner_team_id=owner_team_id,
    )
    session.add(ent)
    session.commit()
    return ent


class TestEnterpriseTeamIsolation:
    """企业账户团队隔离（任务卡 708350b3）"""

    def test_create_forces_own_team(self, client, team_pair):
        """团队级用户创建的企业归属其本人 team；伪造 body owner_team_id 不得越权。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        r = client.post(
            "/api/v1/enterprises",
            json={"name": "A企业", "code": "ENT_A1", "owner_team_id": tb.id},
            headers=_h(team_pair["tokens"]["a"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["owner_team_id"] == ta.id  # 锁本人 team

    def test_list_filters_by_team(self, client, team_pair):
        """团队级用户仅见本 team 企业。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        _seed_enterprise(client._sesh, ta.id, "ENT_LA", "团队A企业")
        _seed_enterprise(client._sesh, tb.id, "ENT_LB", "团队B企业")

        r = client.get("/api/v1/enterprises", headers=_h(team_pair["tokens"]["a"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert all(it["owner_team_id"] == ta.id for it in items)
        assert all(it["name"] != "团队B企业" for it in items)

        # admin 看全部
        admin_h = _auth(client)
        r = client.get("/api/v1/enterprises", headers=admin_h)
        names = {it["name"] for it in r.json()["data"]["items"]}
        assert "团队A企业" in names and "团队B企业" in names

    def test_cross_team_access_returns_404(self, client, team_pair):
        """团队A访问/改/删团队B的企业 → 404。"""
        tb = team_pair["teams"]["b"]
        ent = _seed_enterprise(client._sesh, tb.id, "ENT_XB", "B专属企业")

        ha = _h(team_pair["tokens"]["a"])
        assert client.get(f"/api/v1/enterprises/{ent.id}", headers=ha).status_code == 404
        assert client.put(f"/api/v1/enterprises/{ent.id}", json={"name": "篡改"}, headers=ha).status_code == 404
        assert client.delete(f"/api/v1/enterprises/{ent.id}", headers=ha).status_code == 404

        # B 本人可访问
        assert client.get(f"/api/v1/enterprises/{ent.id}", headers=_h(team_pair["tokens"]["b"])).status_code == 200

    def test_team_user_cannot_reassign_owner_team(self, client, team_pair):
        """团队级用户更新时 body owner_team_id 被忽略。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        ent = _seed_enterprise(client._sesh, ta.id, "ENT_RA", "A待改企业")

        r = client.put(
            f"/api/v1/enterprises/{ent.id}",
            json={"owner_team_id": tb.id},
            headers=_h(team_pair["tokens"]["a"]),
        )
        assert r.status_code == 200
        from app.models.enterprise import Enterprise
        s = client._sesh
        refreshed = s.query(Enterprise).filter_by(id=ent.id).first()
        assert refreshed.owner_team_id == ta.id  # 未变

