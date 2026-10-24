"""AuditMiddleware 失败分支留痕测试 (维度H·操作审计留痕深化)

修复前两缺陷 (app/middleware/audit.py):
1. 非 2xx 写操作 (409 业务拒绝 / 422 校验失败 / 403 越权) 零审计留痕 —
   既不进 2xx 分支也不进 except 分支, 直接 return response。
   而这恰是最该留痕的场景: 账本拒删 409、非法调账 422、越权 403 都是探测信号。
2. except 分支引用 try 块内才赋值的 user_id/username → call_next 抛异常时
   UnboundLocalError 被内层 except 吞掉 → failure 审计永不落库。

修复:
- user_id/username 提前初始化 (try 之前)
- 4xx 走 audit_service.log(result="failure", error_msg=f"HTTP {status}")
- except 分支 error_msg=str(e)[:200], 不再 UnboundLocalError

复用 test_audit_middleware_state_user.py 的自建带中间件 app 模式。
"""
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

import app.core.database as db_module
from app.api.v1 import api_router
from app.middleware.audit import AuditMiddleware
from app.models.audit_log import AuditLog


@pytest.fixture()
def audit_client(client):
    """带 AuditMiddleware 的 client, 与 conftest client 共享同一测试库。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.add_middleware(AuditMiddleware)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['data']['token']}"
        yield c


def _failure_rows(db, action: str, module: str):
    # 审计行由 audit_service 经 SessionLocal() 另一连接提交, 用新会话查
    db.commit()
    fresh = db_module.SessionLocal()
    try:
        return (
            fresh.query(AuditLog)
            .filter(
                AuditLog.action == action,
                AuditLog.module == module,
                AuditLog.result == "failure",
            )
            .all()
        )
    finally:
        fresh.close()


def test_delete_rejected_409_records_failure_audit(audit_client, db_session):
    """删除有余额资金账户被 409 拒 → failure 审计落库 (修复前零留痕)。"""
    r = audit_client.post("/api/v1/fleet/funds", json={
        "account_name": "audit-reject-fund",
        "balance": 100.0,
    })
    assert r.status_code == 200, r.text
    fund_id = r.json()["data"]["id"]

    r2 = audit_client.delete(f"/api/v1/fleet/funds/{fund_id}")
    assert r2.status_code == 409, r2.text

    rows = _failure_rows(db_session, "delete", "fleet")
    assert len(rows) >= 1, "409 拒删未触发 failure 审计"
    row = rows[-1]
    assert row.user_id is not None
    assert row.username == "admin"
    assert row.error_msg, "failure 审计缺少 error_msg"
    assert "409" in row.error_msg


def test_invalid_put_422_records_failure_audit(audit_client, db_session):
    """PUT 非法载荷被 422 拒 → failure 审计落库 (修复前零留痕)。"""
    r = audit_client.post("/api/v1/fleet/funds", json={
        "account_name": "audit-422-fund",
        "balance": 10.0,
    })
    assert r.status_code == 200, r.text
    fund_id = r.json()["data"]["id"]

    # balance 传字符串 → Pydantic 422
    r2 = audit_client.put(f"/api/v1/fleet/funds/{fund_id}", json={"balance": "not-a-number"})
    assert r2.status_code == 422, r2.text

    rows = _failure_rows(db_session, "update", "fleet")
    assert len(rows) >= 1, "422 校验拒绝未触发 failure 审计"
    row = rows[-1]
    assert row.user_id is not None
    assert row.error_msg and "422" in row.error_msg


def test_anonymous_non_2xx_no_audit(client, db_session):
    """匿名 (无 token) 的非 2xx 写操作不落审计 (无 user 可归属, 避免噪音)。"""
    client.headers.pop("Authorization", None)
    r = client.post("/api/v1/fleet/funds", json={"account_name": "anon-req"})
    assert r.status_code == 401
    assert _failure_rows(db_session, "create", "fleet") == []


def test_unhandled_exception_records_failure_audit(client, db_session):
    """call_next 抛异常 (业务 500) → failure 审计落库, 不再 UnboundLocalError。"""
    app = FastAPI()

    def set_user(request: Request):
        class _U:
            id = 1
            username = "boom-user"
        request.state.user = _U()

    @app.post("/api/v1/boom")
    async def boom(request: Request, _u=Depends(set_user)):
        raise RuntimeError("simulated server error")

    app.add_middleware(AuditMiddleware)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/api/v1/boom")
        assert r.status_code == 500

    db_session.commit()
    fresh = db_module.SessionLocal()
    try:
        rows = (
            fresh.query(AuditLog)
            .filter(AuditLog.module == "boom", AuditLog.result == "failure")
            .all()
        )
    finally:
        fresh.close()
    assert len(rows) >= 1, "500 异常分支未落 failure 审计 (UnboundLocalError 修复验证)"
    row = rows[-1]
    assert row.user_id == 1
    assert "simulated server error" in (row.error_msg or "")
