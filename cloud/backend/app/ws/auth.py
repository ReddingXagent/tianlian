"""
WebSocket 鉴权层 (P1 安全修复)

app/ws/routes.py 的 11 个 /ws/v1/* 端点原本零鉴权, 任何人可连接获取实时运营
数据 (设备状态 / 告警 / 工单 / 车队排队 / V2G 计划)。本模块为 WebSocket 提供与
HTTP 层 (enforce_auth / get_current_user) 等价的鉴权:

  - token 经 query param 传递: ws://host/ws/v1/realtime?token=<JWT>
    浏览器 WebSocket API 无法设置自定义请求头, 故用 query param 而非
    Authorization 头。生产建议 wss:// + 反向代理剥离 query, 防止 token 落入
    访问日志。
  - 复用 app.core.jwt_utils.decode_token 校验签名 / 过期 (双 key 灰度轮换兼容)。
  - 查 DB 确认用户存在且 status=active, 拦截离职/禁用员工持未过期 token 长连。
  - 任一环节失败 → close(code=4001, reason="未认证") 并返回 None (fail-closed)。

不使用 FastAPI Depends: WebSocket 端点鉴权在握手阶段, Depends 抛 HTTPException
无法转成 ws close frame, 故由端点显式调用本函数, 判断 user is None 后 return。
"""
from typing import Optional

import asyncio

from fastapi import WebSocket

from app.core.jwt_utils import decode_token

# WebSocket 鉴权拒绝码 (应用自定义范围 4000-4999)
WS_AUTH_DENIED_CODE = 4001


def _lookup_active_user_sync(username: str):
    """同步DB查询: 按用户名取用户, 异常/不存在返回 None (fail-closed)。

    Session 在函数内创建/关闭, 供 async authenticate_websocket 经
    asyncio.to_thread 调用, 避免阻塞事件循环 (卡67523030)。
    """
    import app.core.database as db_module
    from app.models.user import User

    session = db_module.SessionLocal()
    try:
        return session.query(User).filter(User.username == username).first()
    except Exception:
        return None
    finally:
        session.close()


async def authenticate_websocket(websocket: WebSocket) -> Optional[dict]:
    """鉴权 WebSocket 连接, 返回 user info 或 None (已 close)。

    成功: 返回 {"user_id", "username", "role", "team_id"}
    失败: await websocket.close(4001) 后返回 None, 调用方应直接 return。

    fail-closed: token 缺失 / 签名错误 / 过期 / 用户不存在 / 用户禁用 /
    DB 异常, 一律拒绝, 不向未认证方暴露具体原因。
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=WS_AUTH_DENIED_CODE, reason="未认证")
        return None

    # 1) token 签名 / 过期校验 (复用双 key 轮换的统一解码入口)
    try:
        payload = decode_token(token)
    except Exception:
        # ExpiredSignatureError / DecodeError / 其他解码异常 → 一律拒绝
        await websocket.close(code=WS_AUTH_DENIED_CODE, reason="未认证")
        return None

    username = payload.get("sub")
    if not username:
        await websocket.close(code=WS_AUTH_DENIED_CODE, reason="未认证")
        return None

    # 2) DB 校验: 用户存在且未禁用。
    #    SessionLocal 经 db_module 运行时属性读取 (见 _lookup_active_user_sync),
    #    确保 test_db fixture 对 SessionLocal 的覆盖能传播到本模块;
    #    DB 异常时 fail-closed (拒绝), 不放行。
    user = await asyncio.to_thread(_lookup_active_user_sync, username)

    if user is None or getattr(user, "status", "active") != "active":
        await websocket.close(code=WS_AUTH_DENIED_CODE, reason="未认证")
        return None

    # 3) token_version 比对 (卡 c6791952): 改密后递增, 旧 token (tv 不一致) 立即驱逐。
    #    与 HTTP 三路径 (auth.py:178, middleware/permission.py:107/161) 同口径 —
    #    修复前 WS 漏查 tv, 改密后旧 token 在 HTTP 立即 401 但仍可建 WS 连接收实时推送。
    if payload.get("tv", 0) != (getattr(user, "token_version", None) or 0):
        await websocket.close(code=WS_AUTH_DENIED_CODE, reason="未认证")
        return None

    role = user.role.value if hasattr(user.role, "value") else user.role
    return {
        "user_id": user.id,
        "username": user.username,
        "role": role,
        # 归属 team_id (卡 a579f89e): 供聚合频道做 team scope 过滤, 缺失 → None
        "team_id": getattr(user, "team_id", None),
    }
