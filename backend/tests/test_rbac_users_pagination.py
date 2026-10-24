"""
RBAC 用户列表分页 + N+1 消除测试 (卡 1ec60182)
"""
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, class_mapper

from app.models.user import User, UserRole
from app.models.rbac import RoleTable, user_role_table


def _get_token(client, username="admin", password="admin123"):
    resp = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"login 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    token = (data.get("data", {}).get("token") or data.get("token")
             or data.get("data", {}).get("access_token") or data.get("access_token"))
    assert token, f"login 响应未含 token: {data}"
    return token


@pytest.fixture
def rbac_users_env(client, seed_users):
    """准备 ≥5 用户，其中 engineer1 关联一个额外角色（带权限），用于分页与 N+1 测试。"""
    s = client._sesh
    # 补足到 5 个用户 (seed_users 已有 4 个)
    for i in range(5, 8):
        username = f"page_user_{i}"
        if not s.query(User).filter(User.username == username).first():
            s.add(User(
                username=username,
                password_hash="x",
                real_name=f"分页用户{i}",
                role=UserRole.OPERATOR,
                status="active",
            ))
    s.commit()
    return s


class TestListRbacUsersPagination:
    def test_pagination_default_and_total(self, client, seed_users, rbac_users_env):
        token = _get_token(client)
        resp = client.get("/api/v1/rbac/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 7
        assert len(data["items"]) == 7  # 少于 page_size 时全量返回
        assert set(data["items"][0].keys()) >= {"id", "username", "role", "permissions"}

    def test_page_size_limit(self, client, seed_users, rbac_users_env):
        token = _get_token(client)
        resp = client.get("/api/v1/rbac/users?page=1&page_size=2",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] == 7
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_page2_content_disjoint(self, client, seed_users, rbac_users_env):
        token = _get_token(client)
        p1 = client.get("/api/v1/rbac/users?page=1&page_size=3",
                        headers={"Authorization": f"Bearer {token}"}).json()["data"]
        p2 = client.get("/api/v1/rbac/users?page=2&page_size=3",
                        headers={"Authorization": f"Bearer {token}"}).json()["data"]
        p3 = client.get("/api/v1/rbac/users?page=3&page_size=3",
                        headers={"Authorization": f"Bearer {token}"}).json()["data"]
        ids = [u["id"] for u in p1["items"] + p2["items"] + p3["items"]]
        assert len(ids) == len(set(ids)) == 7
        assert p3["items"]  # 第3页有1条

    def test_out_of_range_page_empty(self, client, seed_users, rbac_users_env):
        token = _get_token(client)
        resp = client.get("/api/v1/rbac/users?page=99&page_size=20",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["total"] == 7

    def test_page_size_over_limit_422(self, client, seed_users):
        token = _get_token(client)
        resp = client.get("/api/v1/rbac/users?page_size=101",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422

    def test_non_admin_403(self, client, seed_users):
        token = _get_token(client, "viewer1", "view123")
        resp = client.get("/api/v1/rbac/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_no_n_plus_one_queries(self, client, seed_users, rbac_users_env):
        """≥3 用户含关联角色时，SQL 查询次数不随用户数线性增长（selectinload 固定查询数）。"""
        s = client._sesh
        # 给 engineer1 关联一个额外角色（seed_roles_and_permissions 已在 conftest 建角色）
        eng = s.query(User).filter(User.username == "engineer1").first()
        extra = s.query(RoleTable).filter(RoleTable.name == "dispatcher").first()
        if extra and extra not in eng.assigned_roles:
            eng.assigned_roles.append(extra)
            s.commit()

        token = _get_token(client)
        # 先请求一次暖化 (登录等已发生)
        client.get("/api/v1/rbac/users?page=1&page_size=20",
                   headers={"Authorization": f"Bearer {token}"})

        count = {"n": 0}
        engine = s.get_bind()

        def _count(conn, cursor, statement, parameters, context, executemany):
            count["n"] += 1

        event.listen(engine, "before_cursor_execute", _count)
        try:
            resp = client.get("/api/v1/rbac/users?page=1&page_size=20",
                              headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _count)

        # 固定上限: 1 count + 1 users + 2 selectinload (roles, permissions) + 少量鉴权余量
        assert count["n"] <= 6, f"检测到 {count['n']} 条 SQL，疑似 N+1"
