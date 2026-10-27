"""
工程师管理 API 测试
覆盖: /engineers — 工程师列表、详情、创建、更新、删除
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
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_engineer(name="测试工程师", phone=None, level="junior", team_id=None):
    """创建测试工程师，返回 user_id"""
    phone = phone or f"1380000{abs(hash(name)) % 100000:05d}"
    payload = {
        "name": name,
        "phone": phone,
        "password": "test123456",
        "level": level,
    }
    if team_id is not None:
        payload["team_id"] = team_id
    resp = client.post(
        "/api/v1/engineers",
        json=payload,
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, f"创建工程师失败: {resp.text}"
    return resp.json()["data"]["id"]


# ========== 工程师列表 ==========

def test_list_engineers_empty():
    """测试空工程师列表"""
    resp = client.get("/api/v1/engineers", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "items" in data["data"]


def test_list_engineers_with_pagination():
    """测试工程师列表分页"""
    resp = client.get("/api/v1/engineers?page=1&page_size=10", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["page"] == 1
    assert data["data"]["page_size"] == 10


def test_list_engineers_with_level_filter():
    """测试按等级筛选工程师"""
    _create_engineer("初级工程师", level="junior")
    _create_engineer("中级工程师", level="middle")

    resp = client.get("/api/v1/engineers?level=junior", headers=_auth_headers())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    for item in items:
        assert item["level"] == "junior"


def test_list_engineers_with_status_filter():
    """测试按状态筛选工程师"""
    resp = client.get("/api/v1/engineers?status=active", headers=_auth_headers())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    for item in items:
        assert item["status"] == "active"


def test_list_engineers_with_team_filter():
    """测试按团队筛选工程师"""
    # 创建团队和工程师
    resp_team = client.post(
        "/api/v1/teams",
        json={"name": "筛选测试团队", "description": "用于测试团队筛选"},
        headers=_auth_headers(),
    )
    team_id = resp_team.json()["data"]["id"]

    _create_engineer("团队工程师", team_id=team_id)

    resp = client.get(f"/api/v1/engineers?team_id={team_id}", headers=_auth_headers())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    for item in items:
        assert item["team_id"] == team_id


def test_list_engineers_invalid_level():
    """测试无效的等级参数 (卡e4b484b8: level 收紧 Literal → Pydantic 422 前置拦截)"""
    resp = client.get("/api/v1/engineers?level=invalid", headers=_auth_headers())
    assert resp.status_code == 422


# ========== 工程师详情 ==========

def test_get_engineer_not_found():
    """测试获取不存在的工程师"""
    resp = client.get("/api/v1/engineers/999999", headers=_auth_headers())
    assert resp.status_code == 404


def test_get_engineer_success():
    """测试获取工程师详情成功"""
    eng_id = _create_engineer("详情测试工程师", level="senior")
    resp = client.get(f"/api/v1/engineers/{eng_id}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "详情测试工程师"
    assert data["level"] == "senior"


# ========== 创建工程师 ==========

def test_create_engineer_success():
    """测试创建工程师成功"""
    eng_id = _create_engineer("新工程师", phone="13800000001", level="middle")
    assert eng_id is not None

    # 验证可查询
    resp = client.get(f"/api/v1/engineers/{eng_id}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "新工程师"
    assert data["level"] == "middle"


def test_create_engineer_duplicate_phone():
    """测试创建重复手机号工程师"""
    phone = "13800000002"
    _create_engineer("工程师A", phone=phone)
    resp = client.post(
        "/api/v1/engineers",
        json={"name": "工程师B", "phone": phone, "password": "test123456", "level": "junior"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_create_engineer_invalid_level():
    """测试创建无效等级工程师"""
    resp = client.post(
        "/api/v1/engineers",
        json={"name": "无效工程师", "phone": "13800000003", "password": "test123456", "level": "invalid_level"},
        headers=_auth_headers(),
    )
    # 卡e4b484b8: level 收紧 Literal → Pydantic 422 前置拦截
    assert resp.status_code == 422


def test_create_engineer_with_team():
    """测试创建带团队的工程师"""
    # 先创建团队
    resp_team = client.post(
        "/api/v1/teams",
        json={"name": "工程师所属团队", "description": "测试用"},
        headers=_auth_headers(),
    )
    team_id = resp_team.json()["data"]["id"]

    eng_id = _create_engineer("团队归属工程师", team_id=team_id)
    resp = client.get(f"/api/v1/engineers/{eng_id}", headers=_auth_headers())
    assert resp.json()["data"]["team_id"] == team_id


def test_create_engineer_all_levels():
    """测试创建三种等级的工程师"""
    for level in ["junior", "middle", "senior"]:
        phone = f"138{abs(hash(level)) % 10000000000:010d}"[:11]
        resp = client.post(
            "/api/v1/engineers",
            json={"name": f"{level}_工程师", "phone": phone, "password": "test123456", "level": level},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, f"创建 {level} 失败: {resp.text}"
        assert resp.json()["data"]["level"] == level


# ========== 更新工程师 ==========

def test_update_engineer_success():
    """测试更新工程师成功"""
    eng_id = _create_engineer("原名工程师", level="junior")
    resp = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"name": "新名工程师", "level": "middle"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "新名工程师"
    assert data["level"] == "middle"


def test_update_engineer_not_found():
    """测试更新不存在的工程师"""
    resp = client.put("/api/v1/engineers/999999", json={"name": "不存在"}, headers=_auth_headers())
    assert resp.status_code == 404


def test_update_engineer_partial():
    """测试部分更新工程师"""
    eng_id = _create_engineer("部分更新工程师", level="junior")
    resp = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"phone": "13900000001"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["phone"] == "13900000001"


def test_update_engineer_password():
    """测试更新工程师密码"""
    eng_id = _create_engineer("改密工程师", phone="13800000005", level="junior")
    resp = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"password": "newpass123"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_update_engineer_status():
    """测试更新工程师状态"""
    eng_id = _create_engineer("状态工程师", level="junior")
    resp = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"status": "inactive"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "inactive"


def test_update_engineer_team():
    """测试更新工程师团队"""
    # 创建两个团队
    resp_team1 = client.post(
        "/api/v1/teams",
        json={"name": "团队A", "description": "团队A"},
        headers=_auth_headers(),
    )
    resp_team2 = client.post(
        "/api/v1/teams",
        json={"name": "团队B", "description": "团队B"},
        headers=_auth_headers(),
    )
    team_a = resp_team1.json()["data"]["id"]
    team_b = resp_team2.json()["data"]["id"]

    eng_id = _create_engineer("转队工程师", team_id=team_a)

    # 转到团队B
    resp = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"team_id": team_b},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["team_id"] == team_b


def test_update_engineer_invalid_level():
    """测试更新工程师为无效等级"""
    eng_id = _create_engineer("等级测试工程师", level="junior")
    resp = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"level": "invalid"},
        headers=_auth_headers(),
    )
    # 卡e4b484b8: level 收紧 Literal → Pydantic 422 前置拦截
    assert resp.status_code == 422


# ========== 删除工程师 ==========

def test_delete_engineer_success():
    """测试删除工程师成功"""
    eng_id = _create_engineer("待删除工程师", phone="13800000006")
    resp = client.delete(f"/api/v1/engineers/{eng_id}", headers=_auth_headers())
    assert resp.status_code == 200
    assert "已删除" in resp.json()["message"]

    # 验证已删除
    assert client.get(f"/api/v1/engineers/{eng_id}", headers=_auth_headers()).status_code == 404


def test_delete_engineer_not_found():
    """测试删除不存在的工程师"""
    resp = client.delete("/api/v1/engineers/999999", headers=_auth_headers())
    assert resp.status_code == 404


def test_get_engineer_not_regular_user():
    """测试获取非工程师用户应返回404"""
    # admin 是 SUPER_ADMIN 角色
    resp = client.get("/api/v1/engineers/1", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 团队隔离（任务卡 708350b3）==========

import bcrypt


@pytest.fixture
def team_pair(client):
    """两团队 + 两团队级用户(engineer) + token，用于 team_id 越权测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="工程师团队A", code="ENGTA")
    tb = Team(name="工程师团队B", code="ENGTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "eng123456"
    ua = User(
        username="eng_mgr_a", real_name="A主管", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="eng_mgr_b", real_name="B主管", role=UserRole.ENGINEER,
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
        "tokens": {"a": _tok("eng_mgr_a"), "b": _tok("eng_mgr_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_engineer_forces_own_team(client, team_pair):
    """团队级用户创建的工程师归属其本人 team；伪造 body team_id 不得越权。"""
    ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
    r = client.post(
        "/api/v1/engineers",
        json={"name": "A队新人", "password": "test123456", "team_id": tb.id},
        # 故意伪造 body team_id=B + X-Team-Id=B
        headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
    )
    assert r.status_code == 200
    assert r.json()["data"]["team_id"] == ta.id  # 锁本人 team


def test_list_engineers_filters_by_team(client, team_pair):
    """团队级用户仅见本 team 工程师；伪造 query team_id 不得越权。"""
    ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
    # A、B 各建一名工程师
    client.post("/api/v1/engineers", json={"name": "A队工程师", "password": "test123456"},
                headers=_h(team_pair["tokens"]["a"]))
    client.post("/api/v1/engineers", json={"name": "B队工程师", "password": "test123456"},
                headers=_h(team_pair["tokens"]["b"]))

    # A 故意伪造 ?team_id=B，仍只见本人 team
    r = client.get(
        f"/api/v1/engineers?team_id={tb.id}",
        headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) >= 1
    assert all(it["team_id"] == ta.id for it in items)
    assert all(it["name"] != "B队工程师" for it in items)

    # admin 看全部
    r = client.get("/api/v1/engineers", headers=_auth_headers())
    names = {it["name"] for it in r.json()["data"]["items"]}
    assert "A队工程师" in names and "B队工程师" in names


def test_cross_team_engineer_access_404(client, team_pair):
    """团队A访问/改/删团队B的工程师 → 404（伪造 X-Team-Id 也无效）。"""
    tb = team_pair["teams"]["b"]
    r = client.post("/api/v1/engineers", json={"name": "B专属工程师", "password": "test123456"},
                    headers=_h(team_pair["tokens"]["b"]))
    eng_b = r.json()["data"]["id"]

    ha = {**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)}
    assert client.get(f"/api/v1/engineers/{eng_b}", headers=ha).status_code == 404
    assert client.put(f"/api/v1/engineers/{eng_b}", json={"name": "篡改"}, headers=ha).status_code == 404
    assert client.delete(f"/api/v1/engineers/{eng_b}", headers=ha).status_code == 404

    # B 本人可正常访问
    assert client.get(f"/api/v1/engineers/{eng_b}", headers=_h(team_pair["tokens"]["b"])).status_code == 200


def test_team_user_cannot_reassign_team_id(client, team_pair):
    """团队级用户更新时 body team_id 被忽略（不可改归属到他队）。"""
    ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
    r = client.post("/api/v1/engineers", json={"name": "A队待改", "password": "test123456"},
                    headers=_h(team_pair["tokens"]["a"]))
    eng_id = r.json()["data"]["id"]

    # A 试图把工程师改归属到 B
    r = client.put(
        f"/api/v1/engineers/{eng_id}",
        json={"team_id": tb.id},
        headers=_h(team_pair["tokens"]["a"]),
    )
    assert r.status_code == 200
    # team_id 未变（仍为 A）
    from app.models.user import User
    s = client._sesh
    s.query(User).filter_by(id=eng_id).first()  # 触发会话
    refreshed = s.query(User).filter_by(id=eng_id).first()
    assert refreshed.team_id == ta.id

