"""
操作日志/审计日志端点权限测试 (卡 7c394dfb)
非 admin 且无 audit:view 权限的登录用户应 403；admin 放行；未登录 401。
"""


def _get_token(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json().get("data", {}).get("token", "")


def test_list_logs_engineer_forbidden(client, seed_users):
    """非 admin 无 audit:view 权限用户访问日志列表 → 403"""
    token = _get_token(client, "engineer1", "eng123")
    resp = client.get("/api/v1/operation-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_stats_engineer_forbidden(client, seed_users):
    """非 admin 无 audit:view 权限用户访问统计 → 403"""
    token = _get_token(client, "engineer1", "eng123")
    resp = client.get("/api/v1/operation-log/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_list_logs_viewer_forbidden(client, seed_users):
    """viewer 访问日志列表 → 403"""
    token = _get_token(client, "viewer1", "view123")
    resp = client.get("/api/v1/operation-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_list_logs_admin_allowed(client, seed_users):
    """admin 访问日志列表 → 200"""
    token = _get_token(client, "admin", "admin123")
    resp = client.get("/api/v1/operation-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_stats_admin_allowed(client, seed_users):
    """admin 访问统计 → 200"""
    token = _get_token(client, "admin", "admin123")
    resp = client.get("/api/v1/operation-log/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_requires_auth(anon_client):
    """未登录访问日志列表 → 401"""
    assert anon_client.get("/api/v1/operation-log").status_code == 401


def test_stats_requires_auth(anon_client):
    """未登录访问统计 → 401"""
    assert anon_client.get("/api/v1/operation-log/stats").status_code == 401
