"""
运营-用户类型管理 API 测试 (P0 运营核心补齐)

覆盖 /api/v1/operate/users:
- 列表 / 搜索 / 状态筛选
- 统计 (by_role / by_status / total / active_count / by_user_type)
- 按用户类型筛选 (合法类型 200 / 非法类型 400)
- 编辑用户 (正常 / 404 / 无效 status 422 / 空串 email 归一为 None)
- 匿名拒绝 (401)
"""
import bcrypt

from app.models.user import User, UserRole


def _seed_user(session, username, role=UserRole.VIEWER, status="active", **kw):
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(b"pwd123456", bcrypt.gensalt()).decode(),
        real_name=kw.get("real_name", username),
        phone=kw.get("phone"),
        email=kw.get("email"),
        role=role,
        status=status,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


# ==================== 列表 / 搜索 / 筛选 ====================

class TestOperateUsersList:
    def test_list_users(self, client):
        # admin 由 conftest seed
        r = client.get("/api/v1/operate/users")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 1
        assert "admin" in {u["username"] for u in data["items"]}

    def test_list_users_search(self, client):
        _seed_user(client._sesh, "searchtarget", real_name="靶子用户", phone="13800000000")
        r = client.get("/api/v1/operate/users?search=searchtarget")
        items = r.json()["data"]["items"]
        assert items and all("searchtarget" in (i["username"] or "") for i in items)

    def test_list_users_status_filter(self, client):
        _seed_user(client._sesh, "act_user", status="active")
        _seed_user(client._sesh, "susp_user", status="suspended")
        r = client.get("/api/v1/operate/users?status=suspended")
        items = r.json()["data"]["items"]
        assert items and all(i["status"] == "suspended" for i in items)


# ==================== 统计 ====================

class TestOperateUsersStats:
    def test_stats_structure(self, client):
        _seed_user(client._sesh, "stat1", status="active")
        _seed_user(client._sesh, "stat2", status="inactive")
        r = client.get("/api/v1/operate/users/stats")
        assert r.status_code == 200
        s = r.json()["data"]
        # 五个聚合键齐全
        assert {"by_role", "by_status", "total", "active_count", "by_user_type"} <= set(s)
        # admin + stat1 + stat2
        assert s["total"] >= 3
        # admin + stat1 处于 active
        assert s["active_count"] >= 2
        # by_user_type 覆盖全部 5 个类型
        assert set(s["by_user_type"].keys()) == {"app", "card", "vin", "interconnect", "enterprise"}


# ==================== 按类型筛选 ====================

class TestOperateUsersByType:
    def test_valid_type(self, client):
        r = client.get("/api/v1/operate/users/by-type/app")
        assert r.status_code == 200
        assert "items" in r.json()["data"]

    def test_invalid_type(self, client):
        r = client.get("/api/v1/operate/users/by-type/unknown")
        assert r.status_code == 400
        assert "无效的用户类型" in r.json()["detail"]


# ==================== 编辑用户 ====================

class TestOperateUserUpdate:
    def test_update_user(self, client):
        u = _seed_user(client._sesh, "editme", real_name="旧名", phone="13900000000")
        r = client.put(f"/api/v1/operate/users/{u.id}", json={
            "real_name": "新名", "phone": "13900000001",
            "status": "inactive", "email": "x@y.com",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["real_name"] == "新名"
        assert data["phone"] == "13900000001"
        assert data["status"] == "inactive"
        assert data["email"] == "x@y.com"

    def test_update_user_not_found(self, client):
        r = client.put("/api/v1/operate/users/99999", json={"real_name": "x"})
        assert r.status_code == 404

    def test_update_user_invalid_status(self, client):
        """status 不在白名单 → 422 (卡fbc05dc8: Literal前置拦截, 不再是业务400)"""
        u = _seed_user(client._sesh, "badstatus")
        r = client.put(f"/api/v1/operate/users/{u.id}", json={"status": "frozen"})
        assert r.status_code == 422

    def test_update_user_empty_email_normalized(self, client):
        """空串 email 归一为 None（空串保护）"""
        u = _seed_user(client._sesh, "emptymail")
        r = client.put(f"/api/v1/operate/users/{u.id}", json={"email": "  "})
        assert r.status_code == 200
        assert r.json()["data"]["email"] is None


# ==================== 鉴权 ====================

class TestOperateUsersAuth:
    def test_anon_list_denied(self, anon_client):
        assert anon_client.get("/api/v1/operate/users").status_code == 401

    def test_anon_update_denied(self, anon_client):
        r = anon_client.put("/api/v1/operate/users/1", json={"real_name": "x"})
        assert r.status_code == 401
