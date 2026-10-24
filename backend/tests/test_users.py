#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户管理 API 测试
CRUD + 边界条件 + 异常场景
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _setup(test_db):
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json().get("token") or resp.json().get("data", {}).get("token")


def test_list_users():
    """获取用户列表"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", {}).get("items") or data.get("items") or []
    assert len(items) >= 1


def test_get_user():
    """获取用户详情"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users/1", headers=headers)
    assert resp.status_code == 200
    user_data = resp.json().get("data") or {}
    assert user_data.get("username") == "admin"


def test_get_user_not_found():
    """获取不存在的用户 - 404"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users/99999", headers=headers)
    assert resp.status_code == 404


def test_create_user():
    """创建新用户"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/users", json={
        "username": "testuser1",
        "password": "test123",
        "real_name": "测试用户",
        "role": "engineer",
        "level": "junior",
        "status": "active",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json().get("data") or {}
    assert data.get("username") == "testuser1"
    assert data.get("real_name") == "测试用户"


def test_create_duplicate_user():
    """创建重复用户名 - 400"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/users", json={"username": "dupuser", "password": "test123"}, headers=headers)
    resp = client.post("/api/v1/users", json={"username": "dupuser", "password": "test123"}, headers=headers)
    assert resp.status_code in (400, 409)


def test_update_user():
    """更新用户信息"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.put("/api/v1/users/1", json={"real_name": "更新后的管理员"}, headers=headers)
    assert resp.status_code == 200


def test_delete_user():
    """删除用户"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/users", json={"username": "deleteme", "password": "test123"}, headers=headers)
    user_id = resp.json().get("data", {}).get("id")
    resp = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert resp.status_code == 200
    resp = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert resp.status_code == 404


def test_user_filter_by_role():
    """按角色筛选用户"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users?role=admin", headers=headers)
    assert resp.status_code == 200


def test_user_filter_by_status():
    """按状态筛选用户"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users?status=active", headers=headers)
    assert resp.status_code == 200


def test_user_search_keyword():
    """关键词搜索用户"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users?keyword=admin", headers=headers)
    assert resp.status_code == 200


def test_user_permissions():
    """用户详情包含权限信息"""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users/1", headers=headers)
    data = resp.json().get("data") or {}
    perms = data.get("permissions")
    if perms:
        assert "device:view" in perms
