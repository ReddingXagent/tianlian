"""
Runbook审批流 API 测试
覆盖: /runbook/approvals — pending列表、历史、审批、拒绝、超时检查、统计
"""
import pytest
from datetime import datetime, timedelta, timezone
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


def _create_approval(test_db, **overrides):
    from app.models.runbook_approval import RunbookApproval
    defaults = dict(
        runbook_id="RB-TEST-001",
        alarm_id=1,
        step_index=0,
        step_description="测试步骤",
        action_type="command",
        command_preview="echo hello",
        risk_level="high",
        rollback_preview="echo rollback",
        status="pending",
        required_level="manager",
        auto_execute_after_approval=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
    )
    defaults.update(overrides)
    approval = RunbookApproval(**defaults)
    db = test_db["SessionLocal"]()
    db.add(approval)
    db.commit()
    db.refresh(approval)
    approval_id = approval.id
    db.close()
    return approval_id


# ========== 鉴权检查 ==========

def test_pending_requires_auth(anon_client):
    """匿名访问 → 401。模块级 client 会被 _auth_module_level_client 注入
    admin token(假绿), 故用 anon_client 测真匿名(任务卡 b198e42c 坑)。"""
    assert anon_client.get("/api/v1/runbook/approvals/pending").status_code == 401


def test_history_requires_auth(anon_client):
    assert anon_client.get("/api/v1/runbook/approvals/history").status_code == 401


def test_approve_requires_auth(anon_client):
    assert anon_client.post("/api/v1/runbook/approvals/999/approve",
                            json={"comment": "ok"}).status_code == 401


def test_reject_requires_auth(anon_client):
    assert anon_client.post("/api/v1/runbook/approvals/999/reject",
                            json={"reason": "bad"}).status_code == 401


def test_stats_requires_auth(anon_client):
    assert anon_client.get("/api/v1/runbook/approvals/stats").status_code == 401


# ========== Pending列表 ==========

def test_pending_empty():
    resp = client.get("/api/v1/runbook/approvals/pending", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["items"] == []


def test_pending_with_data(test_db):
    _create_approval(test_db)
    resp = client.get("/api/v1/runbook/approvals/pending", headers=_auth_headers())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["runbook_id"] == "RB-TEST-001"


def test_pending_filter_by_risk(test_db):
    _create_approval(test_db, risk_level="critical")
    resp = client.get("/api/v1/runbook/approvals/pending?risk_level=high", headers=_auth_headers())
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 0


def test_pending_excludes_expired(test_db):
    _create_approval(test_db, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    resp = client.get("/api/v1/runbook/approvals/pending", headers=_auth_headers())
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 0


def test_pending_pagination(test_db):
    for i in range(3):
        _create_approval(test_db, step_index=i, alarm_id=i + 1)
    resp = client.get("/api/v1/runbook/approvals/pending?page=1&page_size=2", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] == 3


# ========== 审批历史 ==========

def test_history_empty():
    resp = client.get("/api/v1/runbook/approvals/history", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["items"] == []


def test_history_filter_by_status(test_db):
    _create_approval(test_db, status="approved")
    resp = client.get("/api/v1/runbook/approvals/history?status=pending", headers=_auth_headers())
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 0


def test_history_includes_all_statuses(test_db):
    _create_approval(test_db, status="approved")
    resp = client.get("/api/v1/runbook/approvals/history", headers=_auth_headers())
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 1


# ========== 审批通过 ==========

def test_approve_success(test_db):
    aid = _create_approval(test_db)
    resp = client.post(f"/api/v1/runbook/approvals/{aid}/approve", json={"comment": "looks good"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["status"] == "approved"


def test_approve_not_found():
    resp = client.post("/api/v1/runbook/approvals/99999/approve", json={"comment": "ok"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 404


def test_approve_already_processed(test_db):
    aid = _create_approval(test_db, status="approved")
    resp = client.post(f"/api/v1/runbook/approvals/{aid}/approve", json={"comment": "again"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 400


def test_approve_expired(test_db):
    aid = _create_approval(test_db, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    resp = client.post(f"/api/v1/runbook/approvals/{aid}/approve", json={"comment": "late"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 400


# ========== 审批拒绝 ==========

def test_reject_success(test_db):
    aid = _create_approval(test_db)
    resp = client.post(f"/api/v1/runbook/approvals/{aid}/reject", json={"reason": "too risky"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert data["data"]["status"] == "rejected"


def test_reject_not_found():
    resp = client.post("/api/v1/runbook/approvals/99999/reject", json={"reason": "no"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 404


def test_reject_already_processed(test_db):
    aid = _create_approval(test_db, status="rejected")
    resp = client.post(f"/api/v1/runbook/approvals/{aid}/reject", json={"reason": "again"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 400


# ========== 超时检查 ==========

def test_expire_check_no_expired(test_db):
    _create_approval(test_db)
    resp = client.post("/api/v1/runbook/approvals/expire-check", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["expired_count"] == 0


def test_expire_check_with_expired(test_db):
    _create_approval(test_db, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    resp = client.post("/api/v1/runbook/approvals/expire-check", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["expired_count"] == 1


# ========== 统计 ==========

def test_stats_empty():
    resp = client.get("/api/v1/runbook/approvals/stats", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["pending"] == 0
    assert data["approved"] == 0
    assert data["rejected"] == 0
    assert data["expired"] == 0


def test_stats_with_data(test_db):
    _create_approval(test_db, status="pending")
    _create_approval(test_db, status="approved", alarm_id=2, step_index=1)
    _create_approval(test_db, status="rejected", alarm_id=3, step_index=2)
    resp = client.get("/api/v1/runbook/approvals/stats", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert data["pending"] == 1
    assert data["approved"] == 1
    assert data["rejected"] == 1
