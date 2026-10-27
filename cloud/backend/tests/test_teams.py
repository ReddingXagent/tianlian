"""
团队管理 API 测试
覆盖: /teams — 团队列表、详情、创建、更新、删除、成员管理
注: teams 路由已加认证保护 + RBAC(admin/operator)
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


def _create_team(name="测试团队"):
    """创建测试团队，返回 team_id"""
    resp = client.post(
        "/api/v1/teams",
        json={"name": name, "description": "测试团队描述"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, f"创建团队失败: {resp.text}"
    return resp.json()["data"]["id"]


# ========== 鉴权检查 (无 token 应返回 401) ==========
# 注: conftest autouse 会给 module-level client 注入 admin token，
# 所以匿名测试必须用独立的 TestClient 实例。

def _anon_client():
    """创建无认证的 TestClient（不受 conftest 自动注入 token 影响）"""
    return TestClient(app)

def test_list_teams_requires_auth():
    """无 token 访问团队列表应返回401"""
    assert _anon_client().get("/api/v1/teams").status_code == 401

def test_get_team_requires_auth():
    """无 token 访问团队详情应返回401"""
    assert _anon_client().get("/api/v1/teams/1").status_code == 401

def test_create_team_requires_auth():
    """无 token 创建团队应返回401"""
    resp = _anon_client().post("/api/v1/teams", json={"name": "test"})
    assert resp.status_code == 401

def test_update_team_requires_auth():
    """无 token 更新团队应返回401"""
    resp = _anon_client().put("/api/v1/teams/1", json={"name": "test"})
    assert resp.status_code == 401

def test_delete_team_requires_auth():
    """无 token 删除团队应返回401"""
    resp = _anon_client().delete("/api/v1/teams/1")
    assert resp.status_code == 401


# ========== 团队列表 ==========

def test_list_teams_empty():
    """测试空团队列表"""
    resp = client.get("/api/v1/teams", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "items" in data["data"]


def test_list_teams_with_pagination():
    """测试团队列表分页"""
    resp = client.get("/api/v1/teams?page=1&page_size=10", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["page"] == 1
    assert data["data"]["page_size"] == 10


def test_list_teams_with_status_filter():
    """测试团队状态筛选"""
    resp = client.get("/api/v1/teams?status=active", headers=_auth_headers())
    assert resp.status_code == 200


# ========== 团队详情 ==========

def test_get_team_not_found():
    """测试获取不存在的团队"""
    resp = client.get("/api/v1/teams/999999", headers=_auth_headers())
    assert resp.status_code == 404


def test_get_team_success():
    """测试获取团队详情成功"""
    team_id = _create_team("详情测试团队")
    resp = client.get(f"/api/v1/teams/{team_id}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "详情测试团队"
    assert "members" in data


# ========== 创建团队 ==========

def test_create_team_success():
    """测试创建团队成功"""
    team_id = _create_team("创建测试团队")
    assert team_id is not None

    # 验证可查询
    resp = client.get(f"/api/v1/teams/{team_id}", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "创建测试团队"


def test_create_team_duplicate_name():
    """测试创建重复名称团队"""
    _create_team("重复团队名")
    resp = client.post(
        "/api/v1/teams",
        json={"name": "重复团队名"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_create_team_with_leader(test_db):
    """测试创建带负责人的团队"""
    # 直接在测试函数中创建用户
    from app.models.user import User
    from app.api.v1.auth import get_password_hash
    from app.models.user import UserRole
    db = test_db["SessionLocal"]()
    user = User(
        username="leader_user",
        password_hash=get_password_hash("test123"),
        real_name="leader_user",
        role=UserRole.ENGINEER,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()

    resp = client.post(
        "/api/v1/teams",
        json={"name": "带负责人团队", "leader_id": user_id, "description": "有负责人"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["leader_id"] == user_id


# ========== 更新团队 ==========

def test_update_team_success():
    """测试更新团队成功"""
    team_id = _create_team("原团队名")
    resp = client.put(
        f"/api/v1/teams/{team_id}",
        json={"name": "新团队名", "description": "更新后的描述"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "新团队名"


def test_update_team_not_found():
    """测试更新不存在的团队"""
    resp = client.put("/api/v1/teams/999999", json={"name": "不存在"}, headers=_auth_headers())
    assert resp.status_code == 404


def test_update_team_partial():
    """测试部分更新团队"""
    team_id = _create_team("部分更新团队")
    resp = client.put(
        f"/api/v1/teams/{team_id}",
        json={"description": "仅更新描述"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["description"] == "仅更新描述"


# ========== 删除团队 ==========

def test_delete_team_success():
    """测试删除团队成功"""
    team_id = _create_team("待删除团队")
    resp = client.delete(f"/api/v1/teams/{team_id}", headers=_auth_headers())
    assert resp.status_code == 200
    assert "已删除" in resp.json()["message"]

    # 验证已删除
    assert client.get(f"/api/v1/teams/{team_id}", headers=_auth_headers()).status_code == 404


def test_delete_team_not_found():
    """测试删除不存在的团队"""
    resp = client.delete("/api/v1/teams/999999", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 成员管理 ==========

def test_get_team_members_empty():
    """测试获取空团队成员列表"""
    team_id = _create_team("空团队")
    resp = client.get(f"/api/v1/teams/{team_id}/members", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["total"] == 0


def test_get_team_members_not_found():
    """测试获取不存在的团队成员"""
    resp = client.get("/api/v1/teams/999999/members", headers=_auth_headers())
    assert resp.status_code == 404


def test_add_team_member_success(test_db):
    """测试添加团队成员"""
    team_id = _create_team("成员测试团队")

    # 直接在测试函数中创建用户
    from app.models.user import User
    from app.api.v1.auth import get_password_hash
    from app.models.user import UserRole
    db = test_db["SessionLocal"]()
    user = User(
        username="member1",
        password_hash=get_password_hash("test123"),
        real_name="member1",
        role=UserRole.ENGINEER,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()

    resp = client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"user_id": user_id, "role": "engineer"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200

    # 验证成员已添加
    resp = client.get(f"/api/v1/teams/{team_id}/members", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1


def test_add_member_team_not_found(test_db):
    """测试向不存在的团队添加成员"""
    from app.models.user import User
    from app.api.v1.auth import get_password_hash
    from app.models.user import UserRole
    db = test_db["SessionLocal"]()
    user = User(
        username="member2",
        password_hash=get_password_hash("test123"),
        real_name="member2",
        role=UserRole.ENGINEER,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()

    resp = client.post(
        "/api/v1/teams/999999/members",
        json={"user_id": user_id},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_add_member_user_not_found():
    """测试添加不存在的用户到团队"""
    team_id = _create_team("用户不存在团队")
    resp = client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"user_id": 999999},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_remove_team_member_success(test_db):
    """测试移除团队成员"""
    team_id = _create_team("移除成员团队")

    from app.models.user import User
    from app.api.v1.auth import get_password_hash
    from app.models.user import UserRole
    db = test_db["SessionLocal"]()
    user = User(
        username="member3",
        password_hash=get_password_hash("test123"),
        real_name="member3",
        role=UserRole.ENGINEER,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()

    # 先添加
    client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"user_id": user_id},
        headers=_auth_headers(),
    )

    # 再移除
    resp = client.delete(f"/api/v1/teams/{team_id}/members/{user_id}", headers=_auth_headers())
    assert resp.status_code == 200
    assert "已从团队" in resp.json()["message"]


def test_remove_member_not_found():
    """测试移除不存在的成员"""
    team_id = _create_team("移除不存在成员团队")
    resp = client.delete(f"/api/v1/teams/{team_id}/members/999999", headers=_auth_headers())
    assert resp.status_code == 404