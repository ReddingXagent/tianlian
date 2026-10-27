#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色管理 API 测试（/api/v1/roles）

覆盖角色 CRUD + 权限树 + 系统角色保护 + 详情/404。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """覆盖 SessionLocal，使权限校验也连测试库。"""
    pass


def _login(username="admin", password="admin123"):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


class TestRoles:
    """角色管理 /roles 端点"""

    def test_list_roles(self):
        """列表 — 含种子系统角色 + user_count 统计"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/roles", headers=h)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert data["total"] >= 5  # 5 个系统角色
        names = [r["name"] for r in data["items"]]
        assert "admin" in names
        assert "user_count" in data["items"][0]

    def test_permission_tree(self):
        """权限树 — 按 resource 分组，含 children"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/roles/tree", headers=h)
        assert resp.status_code == 200
        tree = resp.json()["data"]["tree"]
        assert isinstance(tree, list)
        assert len(tree) > 0
        node = tree[0]
        for key in ("key", "title", "children"):
            assert key in node
        # device 资源应存在且子节点为叶子
        resources = [n["key"] for n in tree]
        assert "device" in resources
        device_node = next(n for n in tree if n["key"] == "device")
        assert device_node["children"][0]["is_leaf"] is True

    def test_create_custom_role(self):
        """创建自定义角色 — 权限正确关联"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/v1/roles", json={
            "name": "custom_engineer",
            "display_name": "自定义工程师",
            "description": "测试自定义角色",
            "permissions": ["device:view", "device:create", "alarm:view"],
        }, headers=h)
        assert resp.status_code == 201
        d = resp.json()["data"]
        assert d["name"] == "custom_engineer"
        assert d["display_name"] == "自定义工程师"
        assert d["is_system"] is False
        assert "device:view" in d["permissions"]
        assert "alarm:view" in d["permissions"]

    def test_create_duplicate_role(self):
        """重名角色返回 400"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        payload = {"name": "dup_role", "display_name": "重复角色"}
        assert client.post("/api/v1/roles", json=payload, headers=h).status_code == 201
        resp = client.post("/api/v1/roles", json=payload, headers=h)
        assert resp.status_code == 400

    def test_update_role(self):
        """更新角色 — display_name + 权限替换"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/roles", json={
            "name": "upd_role", "display_name": "更新前", "permissions": ["device:view"],
        }, headers=h).json()["data"]
        resp = client.put(f"/api/v1/roles/{created['id']}", json={
            "display_name": "更新后",
            "permissions": ["device:view", "device:edit", "device:delete"],
        }, headers=h)
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["display_name"] == "更新后"
        assert "device:delete" in d["permissions"]
        assert len(d["permissions"]) == 3

    def test_get_role_detail_and_404(self):
        """详情 + 不存在 404"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        roles = client.get("/api/v1/roles", headers=h).json()["data"]["items"]
        rid = roles[0]["id"]
        assert client.get(f"/api/v1/roles/{rid}", headers=h).status_code == 200
        assert client.get("/api/v1/roles/99999", headers=h).status_code == 404

    def test_delete_custom_role(self):
        """删除自定义角色 — 删除后 404"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/roles", json={
            "name": "del_role", "display_name": "待删除角色",
        }, headers=h).json()["data"]
        assert client.delete(f"/api/v1/roles/{created['id']}", headers=h).status_code == 200
        assert client.get(f"/api/v1/roles/{created['id']}", headers=h).status_code == 404

    def test_delete_system_role_fails(self):
        """系统内置角色不可删除 — 返回 400"""
        token = _login()
        h = {"Authorization": f"Bearer {token}"}
        roles = client.get("/api/v1/roles", headers=h).json()["data"]["items"]
        sys_role = next(r for r in roles if r["is_system"])
        resp = client.delete(f"/api/v1/roles/{sys_role['id']}", headers=h)
        assert resp.status_code == 400

    def test_unauthorized_access(self):
        """未认证访问返回 401/403"""
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.get("/api/v1/roles").status_code in (401, 403)
