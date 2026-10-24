"""
操作日志/审计日志 API 测试
覆盖: /operation-log — 日志列表、筛选、统计
"""
import pytest
from app.models.audit_log import AuditLog
from datetime import datetime, timezone


def _get_token(client, username="admin", password="admin123"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    if r.status_code != 200:
        return ""
    inner = r.json().get("data", {})
    return inner.get("token", "")


# ========== 鉴权检查 ==========

def test_list_logs_requires_auth(anon_client):
    """无 token 访问日志列表应返回401"""
    assert anon_client.get("/api/v1/operation-log").status_code == 401


def test_stats_requires_auth(anon_client):
    """无 token 访问统计应返回401"""
    assert anon_client.get("/api/v1/operation-log/stats").status_code == 401


# ========== 日志列表 ==========

def test_list_logs_empty(client, seed_users):
    """测试日志列表返回正常"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "items" in data["data"]
    assert "total" in data["data"]


def test_list_logs_with_pagination(client, seed_users):
    """测试日志列表分页"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?page=1&page_size=20", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_with_action_filter(client, seed_users):
    """测试按操作类型筛选"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?action=login", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_with_module_filter(client, seed_users):
    """测试按模块筛选"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?module=auth", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_with_username_filter(client, seed_users):
    """测试按用户名筛选"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?username=admin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_with_result_filter(client, seed_users):
    """测试按结果筛选"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?result=success", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_with_hours_filter(client, seed_users):
    """测试按时间范围筛选"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?hours=24", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_combined_filters(client, seed_users):
    """测试组合筛选"""
    token = _get_token(client)
    resp = client.get(
        "/api/v1/operation-log?action=login&module=auth&result=success&hours=48",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_list_logs_max_page_size(client, seed_users):
    """测试最大分页大小"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?page_size=100", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_list_logs_invalid_page(client, seed_users):
    """测试无效分页参数"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?page=0", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


# ========== 统计 ==========

def test_get_stats(client, seed_users):
    """测试获取日志统计"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_stats_structure(client, seed_users):
    """测试统计结构"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    assert "total_logs" in data
    assert "today_logs" in data
    assert "failed_logs" in data


# ========== 多种操作类型 ==========

def test_list_logs_after_login(client, seed_users):
    """登录后应产生日志"""
    token = _get_token(client)
    resp = client.get("/api/v1/operation-log?action=login", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_list_logs_different_actions(client, seed_users, db_session):
    """测试不同操作类型的日志"""
    log1 = AuditLog(
        action="create",
        module="devices",
        username="admin",
        ip_address="127.0.0.1",
        result="success",
        detail="test create",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(log1)
    db_session.commit()

    token = _get_token(client)
    resp = client.get("/api/v1/operation-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["total"] >= 1


def test_list_logs_different_modules(client, seed_users, db_session):
    """测试不同模块的日志"""
    log1 = AuditLog(
        action="login",
        module="auth",
        username="admin",
        ip_address="127.0.0.1",
        result="success",
        detail="test login",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(log1)
    db_session.commit()

    token = _get_token(client)
    resp = client.get("/api/v1/operation-log", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["total"] >= 1
