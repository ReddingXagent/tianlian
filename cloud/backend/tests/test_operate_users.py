"""
运营-用户类型管理 API 测试

覆盖 /api/v1/operate/users 全部端点:
- GET /users                    用户列表(含 search/status 过滤)
- GET /users/stats              用户统计(按角色/状态/类型)
- GET /users/by-type/{type}     按类型筛选(含 400 校验)
- PUT /users/{id}               编辑运营用户(正常更新/404/422)
"""
import pytest

from app.models.user import User, UserRole


def _seed_users(client):
    """造 3 个不同角色/状态的用户"""
    s = client._sesh
    users = [
        User(username="app_user_1", password_hash="x", real_name="APP张三",
             phone="13800000001", role=UserRole.ADMIN, status="active"),
        User(username="engineer_li", password_hash="x", real_name="工程师李四",
             phone="13800000002", role=UserRole.ENGINEER, status="active"),
        User(username="inactive_wang", password_hash="x", real_name="停用王五",
             phone="13800000003", role=UserRole.ENGINEER, status="inactive"),
    ]
    s.add_all(users)
    s.commit()
    return users


class TestOperateUsers:
    """用户列表 / 统计 / 按类型筛选"""

    def test_list_users_and_search(self, client):
        """列表返回 + 关键字搜索命中"""
        _seed_users(client)

        r = client.get("/api/v1/operate/users")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 3
        assert len(data["items"]) >= 3

        # 搜索 real_name
        searched = client.get("/api/v1/operate/users?search=APP张三").json()["data"]
        assert searched["total"] >= 1
        assert any(item["real_name"] == "APP张三" for item in searched["items"])

    def test_list_users_filter_by_status(self, client):
        """status 过滤"""
        _seed_users(client)
        r = client.get("/api/v1/operate/users?status=inactive").json()["data"]
        assert r["total"] >= 1
        assert all(item["status"] == "inactive" for item in r["items"])

    def test_users_stats(self, client):
        """统计包含总数/活跃数/按角色分组"""
        _seed_users(client)
        stats = client.get("/api/v1/operate/users/stats").json()["data"]

        assert stats["total"] >= 3
        assert stats["active_count"] >= 2  # 2 个 active
        assert "by_status" in stats
        assert "by_role" in stats
        assert "by_user_type" in stats
        # by_user_type 覆盖全部合法类型
        for t in ["app", "card", "vin", "interconnect", "enterprise"]:
            assert t in stats["by_user_type"]

    def test_users_by_type_invalid_returns_400(self, client):
        """非法用户类型返回 400"""
        r = client.get("/api/v1/operate/users/by-type/hacker")
        assert r.status_code == 400

    def test_users_by_type_valid(self, client):
        """合法类型返回 200(即便数据为空)"""
        r = client.get("/api/v1/operate/users/by-type/app")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert "total" in data


class TestUpdateUser:
    """PUT /api/v1/operate/users/{id}"""

    def test_update_user_success(self, client):
        """正常更新用户信息"""
        users = _seed_users(client)
        uid = users[0].id

        r = client.put(f"/api/v1/operate/users/{uid}", json={
            "real_name": "APP张三改",
            "phone": "13900000001",
            "email": "updated@example.com",
            "status": "inactive",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["real_name"] == "APP张三改"
        assert data["phone"] == "13900000001"
        assert data["email"] == "updated@example.com"
        assert data["status"] == "inactive"

    def test_update_user_not_found(self, client):
        """不存在的用户返回 404"""
        r = client.put("/api/v1/operate/users/99999", json={
            "real_name": "不存在",
        })
        assert r.status_code == 404

    def test_update_user_invalid_status(self, client):
        """非法 status 值返回 422"""
        users = _seed_users(client)
        uid = users[0].id

        r = client.put(f"/api/v1/operate/users/{uid}", json={
            "status": "hacked",
        })
        assert r.status_code == 422

    def test_update_user_partial(self, client):
        """部分更新（仅修改 real_name）"""
        users = _seed_users(client)
        uid = users[1].id

        r = client.put(f"/api/v1/operate/users/{uid}", json={
            "real_name": "工程师李四改名",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["real_name"] == "工程师李四改名"
        # 其他字段保持不变
        assert data["status"] == "active"
