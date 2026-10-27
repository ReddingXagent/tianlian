"""
GET /security/threats 去模拟化 (卡 e488b135)

原代码返回硬编码 2 条 mock 威胁 (brute_force 10.0.0.1 / sql_injection 10.0.0.2)。
真实数据源: audit_logs 中 module=auth + result=failure 的记录 → 派生 brute_force 威胁
(失败登录即爆破尝试, auth.py 锁定逻辑 5 次失败即锁定可佐证)。
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog


def _seed_failed_logins(s, *, count=3, ip="203.0.113.50", username="admin"):
    """插入 count 条失败登录审计, 返回对象列表。先清表排除 client fixture 登录痕迹。"""
    s.query(AuditLog).delete()
    s.commit()
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    rows = [
        AuditLog(
            user_id=None,
            username=username,
            user_role="admin",
            action="login",
            module="auth",
            ip_address=ip,
            result="failure",
            error_msg="用户名或密码错误",
            timestamp=base + timedelta(minutes=i),
        )
        for i in range(count)
    ]
    s.add_all(rows)
    s.commit()
    for r in rows:
        s.refresh(r)
    return rows


def _seed_success_login(s, *, ip="10.20.30.99"):
    """插入 1 条成功登录: 不应被识别为威胁。"""
    s.query(AuditLog).delete()
    s.commit()
    row = AuditLog(
        username="admin",
        user_role="admin",
        action="login",
        module="auth",
        ip_address=ip,
        result="success",
        timestamp=datetime.now(timezone.utc),
    )
    s.add(row)
    s.commit()
    s.refresh(row)
    return row


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """每个测试用独立 DB。"""
    pass


# ── 真实数据派生 ──

def test_threats_returns_derived_from_audit_failures(client):
    """失败登录审计 → /threats 返回派生的 brute_force 威胁, 字段映射正确。"""
    s = client._sesh
    _seed_failed_logins(s, count=3, ip="203.0.113.50", username="admin")

    r = client.get("/api/v1/security/threats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["total"] == 3
    items = data["items"]
    assert len(items) == 3

    first = items[0]
    assert first["type"] == "brute_force"
    assert first["source_ip"] == "203.0.113.50"
    assert first["target"] == "admin"
    assert first["status"] in ("active", "blocked", "warning")
    assert first["severity"] in ("low", "medium", "high", "critical")
    assert first["timestamp"]  # ISO 时间串存在
    # 不再含模拟数据特征 (原代码: 10.0.0.1/10.0.0.2/sql_injection)
    assert all(it["source_ip"] not in ("10.0.0.1", "10.0.0.2") for it in items)
    assert all(it["type"] != "sql_injection" for it in items)


def test_threats_empty_db_returns_empty(client):
    """空 audit_logs → 空列表, 绝不返回 mock。"""
    s = client._sesh
    s.query(AuditLog).delete()
    s.commit()

    r = client.get("/api/v1/security/threats")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


def test_threats_ignores_success_logins(client):
    """成功登录不构成威胁: 只有成功记录时列表为空。"""
    s = client._sesh
    _seed_success_login(s)

    r = client.get("/api/v1/security/threats")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


def test_threats_ignores_non_auth_failures(client):
    """非 auth 模块的失败 (如设备操作失败) 不识别为登录威胁。"""
    s = client._sesh
    s.query(AuditLog).delete()
    s.commit()
    s.add(AuditLog(
        username="op1", user_role="operator",
        action="update", module="devices",
        ip_address="198.51.100.7", result="failure",
        timestamp=datetime.now(timezone.utc),
    ))
    s.commit()

    r = client.get("/api/v1/security/threats")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0


def test_threats_pagination(client):
    """分页: page/page_size 切分, 按时间倒序。"""
    s = client._sesh
    _seed_failed_logins(s, count=5)

    p1 = client.get("/api/v1/security/threats?page=1&page_size=2").json()["data"]
    p2 = client.get("/api/v1/security/threats?page=2&page_size=2").json()["data"]
    assert p1["total"] == 5
    assert len(p1["items"]) == 2
    assert len(p2["items"]) == 2
    ids1 = {it["id"] for it in p1["items"]}
    ids2 = {it["id"] for it in p2["items"]}
    assert ids1.isdisjoint(ids2)
    # 时间倒序: 第1页首条 ≥ 第2页末条
    t1 = datetime.fromisoformat(p1["items"][0]["timestamp"])
    t2 = datetime.fromisoformat(p2["items"][-1]["timestamp"])
    assert t1 >= t2


# ── 权限: security:manage ──

def _login(client, username, password):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def test_threats_requires_manage_permission(client, seed_users):
    """viewer 无 security:manage → 403。"""
    token = _login(client, "viewer1", "view123")
    r = client.get("/api/v1/security/threats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_threats_unauthenticated(anon_client):
    """匿名 → 401。"""
    r = anon_client.get("/api/v1/security/threats")
    assert r.status_code == 401
