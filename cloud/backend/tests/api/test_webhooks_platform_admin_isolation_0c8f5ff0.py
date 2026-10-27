# -*- coding: utf-8 -*-
# 审计 #4 越权高危回归 (卡 0c8f5ff0): webhooks.py 8 端点零归属隔离
# Webhook 模型无 team_id, 任意 operator 可改/删/重定向任意回调 URL,
# 任意认证用户可读全平台投递日志 payload 原文。
# 修复: router 级追加 require_platform_admin (对齐 vpp.py 4502884d 先例)。
# 断言: operator/viewer → 403; admin (默认 client) → 非 401/403。
from unittest.mock import AsyncMock

import bcrypt
import pytest

from app.models.user import User, UserRole

WEBHOOKS = "/api/v1/webhooks"

# 全部 8 端点 (method, path, json_body)。路径含 {id} 的用 999 (不存在的 id,
# operator 断言在依赖层被拦不会进 handler; admin 断言只看权限不看业务)。
WEBHOOK_ENDPOINTS = [
    ("GET", f"{WEBHOOKS}", None),
    ("POST", f"{WEBHOOKS}", {
        "name": "隔离测试回调",
        "url": "https://example.com/hooks/iso",
        "event_types": ["alert"],
    }),
    ("GET", f"{WEBHOOKS}/999", None),
    ("PUT", f"{WEBHOOKS}/999", {"name": "篡改名"}),
    ("DELETE", f"{WEBHOOKS}/999", None),
    ("PUT", f"{WEBHOOKS}/999/toggle", {"enabled": False}),
    ("POST", f"{WEBHOOKS}/999/test", None),
    ("GET", f"{WEBHOOKS}/999/deliveries", None),
]


def _login_as(client, username, password, real_name, role):
    s = client._sesh
    if not s.query(User).filter(User.username == username).first():
        s.add(User(
            username=username,
            password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            real_name=real_name,
            role=role,
            status="active",
        ))
        s.commit()
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


@pytest.fixture
def operator_headers(client):
    return _login_as(client, "wh_iso_operator", "op123456",
                     "webhook隔离测试操作员", UserRole.OPERATOR)


@pytest.fixture
def viewer_headers(client):
    return _login_as(client, "wh_iso_viewer", "vw123456",
                     "webhook隔离测试观察者", UserRole.VIEWER)


@pytest.mark.parametrize("method,path,body", WEBHOOK_ENDPOINTS)
def test_operator_forbidden_on_all_webhook_endpoints(client, operator_headers, method, path, body):
    resp = client.request(method, path, json=body, headers=operator_headers)
    assert resp.status_code == 403, (
        f"OPERATOR 访问 {method} {path} 应 403，实际 {resp.status_code}\n{resp.text}"
    )


@pytest.mark.parametrize("method,path,body", WEBHOOK_ENDPOINTS)
def test_viewer_forbidden_on_all_webhook_endpoints(client, viewer_headers, method, path, body):
    resp = client.request(method, path, json=body, headers=viewer_headers)
    assert resp.status_code == 403, (
        f"VIEWER 访问 {method} {path} 应 403，实际 {resp.status_code}\n{resp.text}"
    )


@pytest.mark.parametrize("method,path,body", WEBHOOK_ENDPOINTS)
def test_admin_allowed_on_all_webhook_endpoints(client, monkeypatch, method, path, body):
    # POST /{id}/test 真发送会外发网络请求 → mock _deliver 隔离 (仅权限断言)
    if path.endswith("/test"):
        monkeypatch.setattr("app.api.v1.webhooks._deliver", AsyncMock())
    resp = client.request(method, path, json=body)
    assert resp.status_code not in (401, 403), (
        f"ADMIN 访问 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )
