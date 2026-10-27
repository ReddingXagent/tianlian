#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RBAC 读端点授权测试 (卡 70916969-7482-41e3-9c32-1cf60593bc76)

roles/permissions 读端点此前只有认证(get_current_user)无授权(裸读)。
修复后:
  - viewer 打 GET /roles, /roles/{id}, /roles/tree, /permissions → 403
  - admin 打同端点 → 200

复用 test_rbac_enforcement 的 rbac_env fixture 模式:
_check_admin_or_permission -> get_user_permissions 用 SessionLocal 直连库,
须 monkeypatch 指向测试库, 否则查不到用户误判 401。
"""
import bcrypt
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.user import User, UserRole


@pytest.fixture
def read_guard_env(client, monkeypatch):
    import app.core.database as db_module
    s = client._sesh
    engine = s.get_bind()
    if not s.query(User).filter(User.username == "rg_viewer").first():
        s.add(User(
            username="rg_viewer",
            password_hash=bcrypt.hashpw(b"view123", bcrypt.gensalt()).decode(),
            real_name="rg_viewer",
            role=UserRole.VIEWER,
            status="active",
        ))
    s.commit()
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))
    yield client


def _hdr(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login failed {username}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


READ_ENDPOINTS = [
    "/api/v1/roles",
    "/api/v1/roles/1",
    "/api/v1/roles/tree",
    "/api/v1/permissions",
]


class TestRolesReadGuard:
    def test_viewer_forbidden(self, read_guard_env):
        """viewer 裸读全部读端点 → 403"""
        h = _hdr(read_guard_env, "rg_viewer", "view123")
        for path in READ_ENDPOINTS:
            r = read_guard_env.get(path, headers=h)
            assert r.status_code == 403, f"viewer GET {path} => {r.status_code} (期望403)"

    def test_admin_allowed(self, read_guard_env):
        """admin 读不回归 → 全 200"""
        h = _hdr(read_guard_env, "admin", "admin123")
        for path in READ_ENDPOINTS:
            r = read_guard_env.get(path, headers=h)
            assert r.status_code == 200, f"admin GET {path} => {r.status_code} (期望200)"
