"""
SSL证书管理 API 测试
覆盖: /ssl — 证书列表、详情、申请、续期、配置更新、删除、健康检查、自动续期
"""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_cert(test_db, **overrides):
    from app.models.ssl_certificate import SSLCertificate
    defaults = dict(
        domain=f"test-{datetime.now().strftime('%H%M%S%f')}.example.com",
        email="admin@test.com",
        status="active",
        auto_renew=True,
        renew_days_before=30,
        not_after=datetime.now(timezone.utc) + timedelta(days=90),
    )
    defaults.update(overrides)
    cert = SSLCertificate(**defaults)
    db = test_db["SessionLocal"]()
    db.add(cert)
    db.commit()
    db.refresh(cert)
    domain = cert.domain
    db.close()
    return domain


# 鉴权(匿名 401 / 越权 403 / 参数 422)统一在
# tests/test_ssl_certificates_authorization.py 用 anon_client/client 覆盖。
# 此处原有 *_requires_auth 用模块级 client，被 conftest autouse 注入 admin
# token 后无法表达真匿名 → 已迁移，避免假红（任务卡 55f8d345）。


# ========== 列表 ==========

def test_list_empty():
    resp = client.get("/api/v1/ssl/certificates", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["certificates"] == []


def test_list_with_data(test_db):
    _create_cert(test_db)
    resp = client.get("/api/v1/ssl/certificates", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["certificates"]) == 1
    cert = data["certificates"][0]
    assert "domain" in cert
    assert "status" in cert
    assert "days_remaining" in cert


def test_list_pagination(test_db):
    """证书列表分页 — certificates 受 page_size 限制，total 全量，翻页正确"""
    for i in range(3):
        _create_cert(test_db, domain=f"pg{i}-{datetime.now().strftime('%H%M%S%f')}.example.com")
    resp = client.get("/api/v1/ssl/certificates?page_size=2", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["certificates"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    # 翻第二页：剩余 1 条
    resp2 = client.get("/api/v1/ssl/certificates?page_size=2&page=2", headers=_auth_headers())
    assert resp2.status_code == 200
    assert len(resp2.json()["certificates"]) == 1


# ========== 详情 ==========

def test_get_detail(test_db):
    domain = _create_cert(test_db)
    resp = client.get(f"/api/v1/ssl/certificates/{domain}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == domain
    assert data["email"] == "admin@test.com"
    assert data["auto_renew"] is True


def test_get_not_found():
    resp = client.get("/api/v1/ssl/certificates/notexist.com", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 申请证书 ==========
# Background tasks use SessionLocal (prod DB) which doesn't exist in test,
# so we mock background_tasks to avoid the error.

def test_request_certificate(test_db):
    from unittest.mock import patch
    with patch("app.api.v1.ssl_certificates._async_request_cert"):
        resp = client.post("/api/v1/ssl/certificates", json={
            "domain": "new.example.com",
            "email": "admin@new.com",
            "auto_renew": True,
        }, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["domain"] == "new.example.com"


def test_request_duplicate(test_db):
    domain = _create_cert(test_db)
    resp = client.post("/api/v1/ssl/certificates", json={
        "domain": domain,
    }, headers=_auth_headers())
    assert resp.status_code == 409


# ========== 续期 ==========
# Note: renew triggers background task, same as request_certificate

def test_renew_success(test_db):
    from unittest.mock import patch
    domain = _create_cert(test_db)
    with patch("app.api.v1.ssl_certificates._async_renew_cert"):
        resp = client.post(f"/api/v1/ssl/certificates/{domain}/renew", json={
            "domain": domain,
            "staging": True,
        }, headers=_auth_headers())
    assert resp.status_code == 200


def test_renew_not_found():
    resp = client.post("/api/v1/ssl/certificates/notexist.com/renew", json={
        "domain": "notexist.com",
    }, headers=_auth_headers())
    assert resp.status_code == 404


# ========== 更新配置 ==========

def test_update_config(test_db):
    domain = _create_cert(test_db)
    resp = client.put(f"/api/v1/ssl/certificates/{domain}/config", json={
        "auto_renew": False,
        "renew_days_before": 14,
    }, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_renew"] is False


def test_update_config_not_found():
    resp = client.put("/api/v1/ssl/certificates/notexist.com/config", json={
        "auto_renew": False,
    }, headers=_auth_headers())
    assert resp.status_code == 404


# ========== 删除 ==========

def test_delete_success(test_db):
    domain = _create_cert(test_db)
    resp = client.delete(f"/api/v1/ssl/certificates/{domain}", headers=_auth_headers())
    assert resp.status_code == 200


def test_delete_not_found():
    resp = client.delete("/api/v1/ssl/certificates/notexist.com", headers=_auth_headers())
    assert resp.status_code == 404


def test_delete_then_list_empty(test_db):
    domain = _create_cert(test_db)
    client.delete(f"/api/v1/ssl/certificates/{domain}", headers=_auth_headers())
    resp = client.get("/api/v1/ssl/certificates", headers=_auth_headers())
    assert resp.json()["total"] == 0


# ========== 健康检查 ==========

def test_health_check_empty():
    resp = client.get("/api/v1/ssl/health-check", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["healthy"] == 0


def test_health_check_with_active_cert(test_db):
    _create_cert(test_db, status="active", not_after=datetime.now(timezone.utc) + timedelta(days=90))
    resp = client.get("/api/v1/ssl/health-check", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["healthy"] == 1


def test_health_check_with_expired_cert(test_db):
    # days_remaining is a @property computed from not_after, so just set not_after in the past
    _create_cert(test_db, status="expired", not_after=datetime.now(timezone.utc) - timedelta(days=1))
    resp = client.get("/api/v1/ssl/health-check", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["expired"] >= 1


def test_health_check_expiring_soon(test_db):
    _create_cert(test_db, status="active", not_after=datetime.now(timezone.utc) + timedelta(days=10), renew_days_before=30)
    resp = client.get("/api/v1/ssl/health-check", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["expiring_soon"] >= 1


# ========== 自动续期触发 ==========

def test_auto_renew_trigger(test_db):
    from unittest.mock import patch
    _create_cert(test_db, auto_renew=True, not_after=datetime.now(timezone.utc) + timedelta(days=5), renew_days_before=30)
    with patch("app.api.v1.ssl_certificates._async_renew_cert"):
        resp = client.post("/api/v1/ssl/auto-renew", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "total_certificates" in data
    assert "needs_renewal" in data


def test_auto_renew_cert_not_needing_renewal(test_db):
    from unittest.mock import patch
    _create_cert(test_db, auto_renew=True, not_after=datetime.now(timezone.utc) + timedelta(days=90), renew_days_before=30)
    with patch("app.api.v1.ssl_certificates._async_renew_cert"):
        resp = client.post("/api/v1/ssl/auto-renew", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_certificates"] >= 1
    assert data["needs_renewal"] == 0
