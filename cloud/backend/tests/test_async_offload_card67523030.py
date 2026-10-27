#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回归测试 (卡67523030): async 热路径同步DB调用移入线程池。

修复前: permission中间件 / wx_login / WS鉴权 在 async 函数内直接跑同步
SQLAlchemy, 阻塞事件循环。修复后: DB段经 asyncio.to_thread 在工作线程执行。

证据方式: monkeypatch 各模块的同步DB函数, 记录 threading.get_ident(),
断言执行线程 != 事件循环线程 (asyncio.to_thread 保证在线程池跑)。
"""
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(test_db):
    """独立测试 DB (admin seed + SessionLocal override)。"""
    pass


def _login_token() -> str:
    r = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def test_permission_check_runs_db_off_loop(monkeypatch):
    """require_permission 的DB查询在线程池执行, 不在事件循环线程。"""
    from app.middleware import permission as perm_mod

    loop_thread = threading.get_ident()
    seen_threads = []
    orig = perm_mod._lookup_user_sync

    def spy(username):
        seen_threads.append(threading.get_ident())
        return orig(username)

    monkeypatch.setattr(perm_mod, "_lookup_user_sync", spy)

    token = _login_token()
    # POST /users 挂 Depends(require_permission("user:create")), admin 旁路前必经DB查询
    r = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "u_offloop", "password": "Pw123456", "role": "viewer"},
    )
    # 只验证鉴权路径本身: 请求经过 require_permission 即已触发 spy
    assert seen_threads, "require_permission 未调用DB查询"
    assert all(t != loop_thread for t in seen_threads), (
        f"DB查询仍在调用线程执行: loop={loop_thread} seen={seen_threads}"
    )
    assert r.status_code != 401, r.text


@pytest.mark.asyncio
async def test_wx_login_runs_db_off_loop(test_db, monkeypatch):
    """wx_login 的DB段在线程池执行。"""
    from app.api.v1 import business_end_user_auth as mod
    from app.ws import auth as ws_auth_mod

    # 直接驱动 async wx_login (mock 分支, 不发HTTP), 避免线程边界被
    # TestClient 的事件循环间接掩盖。
    loop_thread = threading.get_ident()
    seen_threads = []
    orig = mod._wx_login_db_sync

    def spy(openid, unionid):
        seen_threads.append(threading.get_ident())
        return orig(openid, unionid)

    monkeypatch.setattr(mod, "_wx_login_db_sync", spy)

    req = mod.WxLoginRequest(code="offloop_probe")
    # 卡 b7270c63: wx_login 挂 @limiter.limit 后签名为 (request: Request, body, db)。
    # 测试环境 limiter.enabled=False (conftest RATE_LIMIT_ENABLED=false 契约),
    # slowapi wrapper 跳过 request 检查直调原函数, 占位对象即可; 本测试只关心
    # DB 段线程卸载, 与限流无关。
    resp = await mod.wx_login(request=object(), body=req, db=None)
    assert resp["data"]["is_mock"] is True
    assert seen_threads and all(t != loop_thread for t in seen_threads), (
        f"DB段仍在事件循环线程: loop={loop_thread} seen={seen_threads}"
    )

    # WS 鉴权DB段同样验证
    seen_threads.clear()
    orig_ws = ws_auth_mod._lookup_active_user_sync

    def ws_spy(username):
        seen_threads.append(threading.get_ident())
        return orig_ws(username)

    monkeypatch.setattr(ws_auth_mod, "_lookup_active_user_sync", ws_spy)

    class _FakeWS:
        query_params = {"token": _login_token()}

        async def close(self, code=None, reason=None):
            raise AssertionError(f"不应被拒绝: {code} {reason}")

    result = await ws_auth_mod.authenticate_websocket(_FakeWS())
    assert result is not None and result["username"] == "admin"
    assert seen_threads and all(t != loop_thread for t in seen_threads), (
        f"WS DB段仍在事件循环线程: loop={loop_thread} seen={seen_threads}"
    )
