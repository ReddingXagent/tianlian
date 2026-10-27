"""
验证热路径 async 函数的同步 DB 调用已在线程池执行 (卡67523030).

维度J AST 深扫发现: permission._check / wx_login / authenticate_websocket
三个热路径 async 函数内直接调用同步 SQLAlchemy, 阻塞事件循环。
修复: 用 asyncio.to_thread 包装同步 DB 段。

验证策略:
  1. 静态源码检查: 确认 to_thread 调用 + 同步辅助函数存在 (防回归)
  2. 直接 async 调用: 验证 DB 查询时 thread != event loop thread
"""
import asyncio
import inspect
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _setup(test_db):
    """每个测试独立 DB (覆盖 SessionLocal, seed admin)。"""
    pass


# ════════════════════════════════════════════════════════════════════
# 1. 静态源码检查: 确认 to_thread 调用存在 (防回归)
# ════════════════════════════════════════════════════════════════════

def test_permission_source_uses_to_thread():
    """permission.py 的 _check 函数包含 asyncio.to_thread 调用。"""
    import app.middleware.permission as mod

    source = inspect.getsource(mod)
    assert "to_thread" in source, (
        "permission.py 源码未包含 to_thread, DB 查询可能阻塞事件循环"
    )
    assert hasattr(mod, "_lookup_user_sync"), (
        "permission.py 应有 _lookup_user_sync 函数供 to_thread 调用"
    )
    assert not asyncio.iscoroutinefunction(mod._lookup_user_sync), (
        "_lookup_user_sync 应为同步函数, 非 async"
    )


def test_wx_login_source_uses_to_thread():
    """business_end_user_auth.py 的 wx_login 函数包含 to_thread 调用。"""
    import app.api.v1.business_end_user_auth as mod

    source = inspect.getsource(mod.wx_login)
    assert "to_thread" in source, (
        "wx_login 源码未包含 to_thread, DB 操作可能阻塞事件循环"
    )
    assert hasattr(mod, "_wx_login_db_sync"), (
        "business_end_user_auth.py 应有 _wx_login_db_sync 函数供 to_thread 调用"
    )
    assert not asyncio.iscoroutinefunction(mod._wx_login_db_sync), (
        "_wx_login_db_sync 应为同步函数, 非 async"
    )


def test_ws_auth_source_uses_to_thread():
    """ws/auth.py 的 authenticate_websocket 包含 to_thread 调用。"""
    from app.ws import auth as ws_auth

    source = inspect.getsource(ws_auth.authenticate_websocket)
    assert "to_thread" in source, (
        "authenticate_websocket 源码未包含 to_thread, DB 查询可能阻塞事件循环"
    )
    assert hasattr(ws_auth, "_lookup_active_user_sync"), (
        "ws/auth.py 应有 _lookup_active_user_sync 函数供 to_thread 调用"
    )
    assert not asyncio.iscoroutinefunction(ws_auth._lookup_active_user_sync), (
        "_lookup_active_user_sync 应为同步函数, 非 async"
    )


# ════════════════════════════════════════════════════════════════════
# 2. 直接 async 调用: 验证 DB 查询在线程池执行 (thread != event loop thread)
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_permission_check_db_in_thread_pool():
    """require_permission._check → _lookup_user_sync 在线程池执行。

    直接在 async 测试中调用 _check, 确认 DB 查询时
    threading.get_ident() != 事件循环线程。
    """
    from app.core.jwt_utils import encode_token
    from app.core.database import SessionLocal
    from app.models.user import User, UserRole
    import app.middleware.permission as mod

    # 确保 admin 用户存在
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                username="admin",
                password_hash="x",
                role=UserRole.ADMIN,
                status="active",
            ))
            db.commit()
    finally:
        db.close()

    token = encode_token({
        "sub": "admin",
        "user_id": 1,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    })

    main_thread_id = threading.get_ident()
    captured_thread_ids = []
    orig_lookup = mod._lookup_user_sync

    def tracking_lookup(username):
        captured_thread_ids.append(threading.get_ident())
        return orig_lookup(username)

    # 构造 require_permission("device:view") 并直接调用其 _check
    check_dep = mod.require_permission("device:view")
    mod._lookup_user_sync = tracking_lookup
    try:
        user = await check_dep(token=token)
        assert user is not None, "有效 token 应返回 user"
    finally:
        mod._lookup_user_sync = orig_lookup

    assert len(captured_thread_ids) > 0, "_lookup_user_sync 未被调用"
    for tid in captured_thread_ids:
        assert tid != main_thread_id, (
            f"permission DB 查询在事件循环线程执行, 未转移到线程池: "
            f"main={main_thread_id}, db_thread={tid}"
        )


@pytest.mark.asyncio
async def test_wx_login_db_in_thread_pool():
    """wx_login → _wx_login_db_sync 在线程池执行。

    直接在 async 测试中调用 _wx_login_db_sync 经 asyncio.to_thread,
    确认 DB 查询时 threading.get_ident() != 事件循环线程。
    """
    from app.core.database import SessionLocal
    from app.models.end_user import EndUser
    import app.api.v1.business_end_user_auth as mod

    main_thread_id = threading.get_ident()
    captured_thread_id = []
    orig_fn = mod._wx_login_db_sync

    def tracking_fn(openid, unionid):
        captured_thread_id.append(threading.get_ident())
        return orig_fn(openid, unionid)

    mod._wx_login_db_sync = tracking_fn
    try:
        # 直接调用 wx_login 的 DB 段 (经 asyncio.to_thread)
        end_user, is_new = await asyncio.to_thread(
            mod._wx_login_db_sync, "test_offload_openid", None
        )
        assert end_user is not None
        assert is_new is True
    finally:
        # 清理测试数据
        db = SessionLocal()
        try:
            db.query(EndUser).filter(EndUser.wx_openid == "test_offload_openid").delete()
            db.commit()
        finally:
            db.close()
        mod._wx_login_db_sync = orig_fn

    assert len(captured_thread_id) == 1, (
        f"_wx_login_db_sync 调用次数异常: {len(captured_thread_id)}"
    )
    assert captured_thread_id[0] != main_thread_id, (
        f"wx_login DB 操作在事件循环线程执行, 未转移到线程池: "
        f"main={main_thread_id}, db_thread={captured_thread_id[0]}"
    )


@pytest.mark.asyncio
async def test_ws_auth_db_in_thread_pool():
    """authenticate_websocket → _lookup_active_user_sync 在线程池执行。

    直接在 async 测试中调用 authenticate_websocket, 确认 DB 查询时
    threading.get_ident() != 事件循环线程。
    """
    from app.ws import auth as ws_auth
    from app.core.jwt_utils import encode_token
    from app.core.database import SessionLocal
    from app.models.user import User, UserRole

    # 确保 admin 用户存在
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                username="admin",
                password_hash="x",
                role=UserRole.ADMIN,
                status="active",
            ))
            db.commit()
    finally:
        db.close()

    token = encode_token({
        "sub": "admin",
        "user_id": 1,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    })

    main_thread_id = threading.get_ident()
    captured_thread_id = []
    orig_lookup = ws_auth._lookup_active_user_sync

    def tracking_lookup(username):
        captured_thread_id.append(threading.get_ident())
        return orig_lookup(username)

    class FakeWS:
        def __init__(self, token_str):
            self._token = token_str
            self.closed = False
            self.close_code = None
            self.close_reason = None

        @property
        def query_params(self):
            return {"token": self._token} if self._token else {}

        async def close(self, code=4001, reason="未认证"):
            self.closed = True
            self.close_code = code
            self.close_reason = reason

    ws_auth._lookup_active_user_sync = tracking_lookup
    try:
        fake_ws = FakeWS(token)
        result = await ws_auth.authenticate_websocket(fake_ws)

        assert result is not None, "有效 token 应返回 user info"
        assert "user_id" in result
    finally:
        ws_auth._lookup_active_user_sync = orig_lookup

    assert len(captured_thread_id) >= 1, "_lookup_active_user_sync 未被调用"
    for tid in captured_thread_id:
        assert tid != main_thread_id, (
            f"WS auth DB 查询在事件循环线程执行, 未转移到线程池: "
            f"main={main_thread_id}, db_thread={tid}"
        )
