"""AuditMiddleware request.state.user 注入测试 (卡 a1c26a22)

根因: enforce_auth 原先只校验 token 丢弃返回值, request.state.user 全仓库无赋值点,
AuditMiddleware 在 `if not user_id: return await call_next(request)` 永远提前放行,
全局自动审计失效 → 17 个资金敏感文件写操作零审计留痕。

修复两处:
1. app/api/v1/auth.py enforce_auth 校验后挂 request.state.user / user_id
2. app/middleware/audit.py 用户提取挪到 call_next 之后 (路由依赖在请求处理期才执行,
   提取早于依赖执行永远拿到空)

本文件验证:
1. 需认证路径的写操作 (POST/PUT) 触发 AuditMiddleware 落库 result=success, user_id/username 非空
2. 资金敏感模块 (fleet_funds) 写操作审计留痕 — 修复前零留痕的重灾区
3. 匿名 401 请求不落审计 (无 user 可归属)

注: conftest client fixture 的 session 级 app 不挂 AuditMiddleware (与生产 app.main.app
的中间件栈不同), 故本文件自建带中间件的 app。DB 环境复用 client fixture —— 其对模块级
SessionLocal 的 override 是全局的, 新 app 的 get_db / enforce_auth / audit_service 均落到
同一测试库。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.core.database as db_module
from app.api.v1 import api_router
from app.middleware.audit import AuditMiddleware
from app.models.audit_log import AuditLog


@pytest.fixture()
def audit_client(client):
    """带 AuditMiddleware 的 client, 与 conftest client 共享同一测试库 (SessionLocal override 全局)。"""
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


def _audit_rows(db, action: str, module: str):
    # 直接开新会话查 —— 审计行由 audit_service 经 SessionLocal() 另一连接提交,
    # db (conftest client fixture 的长会话) 对另连接提交的行可见性不稳定
    db.commit()  # 结束 db 的旧读事务快照
    fresh = db_module.SessionLocal()
    try:
        return (
            fresh.query(AuditLog)
            .filter(AuditLog.action == action, AuditLog.module == module)
            .all()
        )
    finally:
        fresh.close()


def test_write_op_records_audit_with_user(audit_client, db_session):
    """普通需认证写操作 → AuditMiddleware 自动落库且 user_id/username 非空。"""
    r = audit_client.post("/api/v1/fleet/funds", json={
        "account_name": "audit-test-fund",
        "balance": 100.0,
    })
    assert r.status_code == 200, r.text

    # module 取 URL 第3段: /api/v1/fleet/funds → 'fleet'
    rows = _audit_rows(db_session, "create", "fleet")
    assert len(rows) >= 1, "fleet_funds POST 未触发自动审计落库"
    row = rows[-1]
    assert row.user_id is not None
    assert row.username == "admin"
    assert row.result == "success"
    assert "POST /api/v1/fleet/funds" in (row.detail or "")


def test_fleet_funds_update_records_audit(audit_client, db_session):
    """资金敏感模块 PUT 调账 → 审计留痕 (修复前该路径零留痕)。"""
    r = audit_client.post("/api/v1/fleet/funds", json={
        "account_name": "audit-put-fund",
        "balance": 50.0,
    })
    assert r.status_code == 200, r.text
    fund_id = r.json()["data"]["id"]

    r2 = audit_client.put(f"/api/v1/fleet/funds/{fund_id}", json={"balance": 200.0})
    assert r2.status_code == 200, r2.text

    rows = _audit_rows(db_session, "update", "fleet")
    assert len(rows) >= 1, "fleet_funds PUT 未触发自动审计落库"
    row = rows[-1]
    assert row.user_id is not None
    assert row.username == "admin"
    assert row.result == "success"
    assert str(fund_id) == (row.target_id or "")


def test_anonymous_write_no_audit(client, db_session):
    """匿名请求被 enforce_auth 401 拦截 → 不落审计（无 user 可归属）。"""
    client.headers.pop("Authorization", None)
    r = client.post("/api/v1/fleet/funds", json={"account_name": "anon"})
    assert r.status_code == 401
    assert _audit_rows(db_session, "create", "fleet") == []
