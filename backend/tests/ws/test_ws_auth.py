#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 端点鉴权测试 (P1 安全修复)

回归背景: app/ws/routes.py 的 11 个 /ws/v1/* 端点原本零鉴权, 任何人可连接获取
实时运营数据 (设备状态 / 告警 / 工单 / 车队排队 / V2G 计划)。修复后强制
?token=<JWT> query param 鉴权, 复用 HTTP 层 decode_token + DB 用户校验。

覆盖矩阵:
  - 无 token         → 拒绝连接 (close 4001, 客户端收不到 connected)
  - 无效 token (签名错误) → 拒绝
  - 过期 token       → 拒绝 (decode_token 抛 ExpiredSignatureError)
  - 禁用用户持有效签名 token → 拒绝 (DB 查询 status != active)
  - 改密后旧 token (tv 不一致) → 拒绝 (token_version 比对, 与 HTTP 同口径, 卡 c6791952)
  - 有效 token       → 正常连接 (收到 connected 握手)
  - 多端点覆盖 (realtime / dashboard / fleet/queue)

鉴权拒绝时 httpx-ws 在握手或 receive 阶段抛异常, 故 _try_connect 把整个连接
流程包进 try: 任何异常 → raised=True, msg 保持 None。断言落在 msg is None
(未收到 connected) 而非具体异常类型, 规避 ASGI transport 跨版本差异。
"""
import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(test_db):
    """每个测试独立 DB (覆盖 SessionLocal, seed admin)。"""
    pass


def _login_token() -> str:
    """登录 admin 拿 JWT (admin 由 test_db fixture seed)。"""
    r = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _sign_token(username: str, role: str = "engineer", user_id: int = 999) -> str:
    """直接签发 JWT (绕过登录), 用于构造禁用用户 / 非常规 payload 的测试 token。"""
    from app.core.jwt_utils import encode_token
    return encode_token({
        "sub": username,
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    })


def _sign_expired_token(username: str = "admin") -> str:
    """签发已过期 token (签名有效, exp 在过去)。"""
    from app.core.jwt_utils import encode_token
    return encode_token({
        "sub": username,
        "user_id": 1,
        "role": "admin",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
    })


def _seed_inactive_user(username: str = "inactive_ws_user"):
    """seed 一个 status=inactive 的用户 (无法通过登录拿 token, 故测试直接签发)。"""
    from app.core.database import SessionLocal
    from app.models.user import User, UserRole
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == username).first():
            db.add(User(
                username=username,
                password_hash=bcrypt.hashpw(b"pw_x", bcrypt.gensalt()).decode(),
                role=UserRole.ENGINEER,
                status="inactive",
            ))
            db.commit()
    finally:
        db.close()


async def _try_connect(url: str, receive_timeout: float = 2.5):
    """尝试连接并收首条消息, 返回 (msg_or_None, raised)。

    服务端鉴权拒绝 (accept 前 close 4001) 时, aconnect_ws / receive 抛异常。
    """
    transport = ASGIWebSocketTransport(app=app)
    msg = None
    raised = False
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws(url, client=ac) as ws:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=receive_timeout)
    except Exception:
        raised = True
    finally:
        try:
            await transport.aclose()
        except Exception:
            pass
    return msg, raised


# ════════════════════════════════════════════════════════════════════
# 拒绝路径: 无 token / 无效 token / 过期 token / 禁用用户
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_token_rejected_realtime():
    """无 token 连 /realtime → 拒绝 (P1 缺口核心: 不再裸奔放行)。"""
    msg, raised = await asyncio.wait_for(
        _try_connect("ws://test/ws/v1/realtime"), timeout=8.0,
    )
    assert msg is None, "无 token 不应收到 connected 握手"
    assert raised, "无 token 连接应被服务端拒绝"


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    """签名错误的 token → 拒绝。"""
    msg, raised = await asyncio.wait_for(
        _try_connect("ws://test/ws/v1/realtime?token=not.a.valid.jwt"), timeout=8.0,
    )
    assert msg is None
    assert raised


@pytest.mark.asyncio
async def test_expired_token_rejected():
    """过期 token (exp 在过去) → decode_token 抛 ExpiredSignatureError → 拒绝。"""
    token = _sign_expired_token()
    msg, raised = await asyncio.wait_for(
        _try_connect(f"ws://test/ws/v1/realtime?token={token}"), timeout=8.0,
    )
    assert msg is None
    assert raised


@pytest.mark.asyncio
async def test_inactive_user_rejected():
    """禁用用户持有效签名 token → DB 校验 status=inactive → 拒绝。

    锁定「查 DB 而非仅校验签名」的安全价值: 离职/禁用员工即便 token 未过期也不可连。
    """
    _seed_inactive_user()
    token = _sign_token(username="inactive_ws_user", role="engineer", user_id=8888)
    msg, raised = await asyncio.wait_for(
        _try_connect(f"ws://test/ws/v1/realtime?token={token}"), timeout=8.0,
    )
    assert msg is None
    assert raised


@pytest.mark.asyncio
async def test_no_token_rejected_fleet_path_param():
    """无 token 连带路径参数端点 /fleet/queue/{id} → 拒绝 (覆盖路径参数端点)。"""
    msg, raised = await asyncio.wait_for(
        _try_connect("ws://test/ws/v1/fleet/queue/5"), timeout=8.0,
    )
    assert msg is None
    assert raised


# ════════════════════════════════════════════════════════════════════
# 放行路径: 有效 token 正常连接
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_valid_token_accepted_realtime():
    """有效 token 连 /realtime → 收到 connected 握手。"""
    token = _login_token()
    msg, raised = await asyncio.wait_for(
        _try_connect(f"ws://test/ws/v1/realtime?token={token}"), timeout=8.0,
    )
    assert msg is not None, "有效 token 应收到 connected 握手"
    assert msg["type"] == "connected"
    assert msg["channel"] == "realtime"


@pytest.mark.asyncio
async def test_valid_token_accepted_multiple_channels():
    """有效 token 连 dashboard / devices / alerts → 均收到 connected。"""
    token = _login_token()
    for ch in ("dashboard", "devices", "alerts"):
        msg, _ = await asyncio.wait_for(
            _try_connect(f"ws://test/ws/v1/{ch}?token={token}"), timeout=10.0,
        )
        assert msg is not None, f"频道 {ch} 有效 token 未收到 connected"
        assert msg["type"] == "connected", f"频道 {ch} 握手类型错误: {msg.get('type')}"
        assert msg["channel"] == ch


@pytest.mark.asyncio
async def test_valid_token_accepted_fleet_queue():
    """有效 token 连 /fleet/queue/{id} → 收到 connected。"""
    token = _login_token()
    msg, _ = await asyncio.wait_for(
        _try_connect(f"ws://test/ws/v1/fleet/queue/5?token={token}"), timeout=10.0,
    )
    assert msg is not None
    assert msg["type"] == "connected"
    assert msg["channel"] == "fleet_queue"


# ════════════════════════════════════════════════════════════════════
# token_version 比对 (卡 c6791952): 改密后旧 token 在 WS 也应失效
# ════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_old_token_after_password_change_rejected():
    """改密递增 token_version 后, 旧 token 建 WS 应被拒 (卡 c6791952)。

    回归背景: HTTP 三路径 (auth.py:178, middleware/permission.py:107/161) 均比对
    tv, 改密后旧 token 立即 401; 但 WS 路径 (app/ws/auth.py) 修复前漏查 tv,
    旧 token 仍可建 WS 连接收实时推送。本测试走真实改密链路 (管理员重置密码
    递增 tv) 验证 WS 与 HTTP 同口径驱逐。

    步骤:
      1) 登录 admin 拿 token (login 签发带 tv, admin 初始 token_version=0)
      2) 调 POST /api/v1/users/{admin_id}/reset-password 递增 tv (→1)
      3) 旧 token (tv=0) 连 /realtime → 应被拒 (收不到 connected)
    """
    # 1) 登录拿 token (login 签发带 tv, admin 初始 token_version=0)
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()["data"]
    token = data["token"]
    admin_id = data["user"]["id"]

    # 2) 管理员重置密码 → token_version 递增 (与 auth.password_reset 同口径)。
    #    复用 module client 注入的 admin 凭证 (tv 仍=0, 鉴权通过后端点内递增)。
    reset_resp = client.post(
        f"/api/v1/users/{admin_id}/reset-password",
        json={"new_password": "Newpass123!"},
    )
    assert reset_resp.status_code == 200, reset_resp.text

    # 3) 旧 token (tv=0, 已与 DB tv=1 不一致) 连 WS → 应被拒
    msg, raised = await asyncio.wait_for(
        _try_connect(f"ws://test/ws/v1/realtime?token={token}"), timeout=8.0,
    )
    assert msg is None, "改密后旧 token (tv 不一致) 不应收到 connected 握手"
    assert raised, "改密后旧 token 建 WS 应被拒绝"
