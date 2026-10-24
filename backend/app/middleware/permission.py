"""
权限中间件 — @require_permission 装饰器 + 权限工具函数

提供权限检查: @require_permission("device:view")

JWT payload 格式:
{
    "sub": "username",
    "user_id": 123,
    "role": "admin",
    "permissions": [...],
    "exp": ...
}
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.models.rbac import ROLE_PERMISSIONS_MATRIX

logger = logging.getLogger(__name__)

# 轻量级 oauth2_scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_user_permissions(user) -> list[str]:
    """
    获取用户的所有权限 (通过主角色 + 关联角色)
    纯函数，不依赖其他模块
    """
    role_val = user.role.value if hasattr(user.role, 'value') else user.role
    perms = list(ROLE_PERMISSIONS_MATRIX.get(role_val, []))

    # 从关联角色 (user_roles) 获取额外权限
    if hasattr(user, 'assigned_roles') and user.assigned_roles:
        for r in user.assigned_roles:
            if r.name != role_val:
                perms.extend(p.name for p in r.permissions)

    return list(set(perms))


def _lookup_user_sync(username: str) -> "User":
    """同步DB查询: 按用户名取用户, 不存在抛 401。

    Session 在函数内创建/关闭 (不跨线程传递), 供 async 热路径经
    asyncio.to_thread 调用, 避免同步 SQLAlchemy 阻塞事件循环。
    延迟导入确保 conftest 对 app.core.database.SessionLocal 的运行时
    覆盖 (测试库注入) 传播到本模块。
    """
    from app.models.user import User
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is not None:
            # session 关闭后 user 为 detached: 预加载权限校验所需的
            # 关联属性 (assigned_roles / 每角色的 permissions), 避免调用方
            # 惰性加载报 DetachedInstanceError。
            for r in user.assigned_roles:
                _ = r.permissions
        return user
    finally:
        db.close()


def require_permission(
    permission: Union[str, List[str]],
):
    """
    权限检查依赖注入
    返回一个依赖项，可在路由中使用: Depends(require_permission("device:view"))

    注意: 此函数返回另一个依赖函数，该函数接收 token 参数
    """
    async def _check(token: str = Depends(oauth2_scheme)):
        # 延迟导入避免循环
        from jwt.exceptions import DecodeError, ExpiredSignatureError
        from app.core.jwt_utils import decode_token

        if not token:
            raise HTTPException(status_code=401, detail="未提供认证凭证")

        try:
            payload = decode_token(token)
            username = payload.get("sub")
            if not username:
                raise HTTPException(status_code=401, detail="无效的认证凭证")
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="认证凭证已过期")
        except DecodeError:
            raise HTTPException(status_code=401, detail="无效的认证凭证")

        user = await asyncio.to_thread(_lookup_user_sync, username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        # 每请求防线 (卡 5d6a978b): 非 active 拒; token_version 比对驱逐改密前旧 token
        if user.status != "active":
            raise HTTPException(status_code=401, detail="账户状态异常")
        if payload.get("tv", 0) != (user.token_version or 0):
            raise HTTPException(status_code=401, detail="认证凭证已失效")

        role_val = user.role.value if hasattr(user.role, 'value') else user.role

        # ADMIN / SUPER_ADMIN 始终通过
        if role_val in ("admin", "super_admin"):
            return user

        required_perms = [permission] if isinstance(permission, str) else list(permission)
        user_perms = get_user_permissions(user)

        if not any(p in user_perms for p in required_perms):
            logger.warning(
                "权限不足: user=%s role=%s required=%s",
                user.username, role_val, required_perms,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要: {', '.join(required_perms)}",
            )
        return user

    return _check


def require_role(*roles: str):
    """
    角色校验依赖
    返回一个依赖项: Depends(require_role("admin", "operator"))
    """
    async def _check(token: str = Depends(oauth2_scheme)):
        from jwt.exceptions import DecodeError, ExpiredSignatureError
        from app.core.jwt_utils import decode_token

        if not token:
            raise HTTPException(status_code=401, detail="未提供认证凭证")

        try:
            payload = decode_token(token)
            username = payload.get("sub")
            if not username:
                raise HTTPException(status_code=401, detail="无效的认证凭证")
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="认证凭证已过期")
        except DecodeError:
            raise HTTPException(status_code=401, detail="无效的认证凭证")

        user = await asyncio.to_thread(_lookup_user_sync, username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        # 每请求防线 (卡 5d6a978b): 非 active 拒; token_version 比对驱逐改密前旧 token
        if user.status != "active":
            raise HTTPException(status_code=401, detail="账户状态异常")
        if payload.get("tv", 0) != (user.token_version or 0):
            raise HTTPException(status_code=401, detail="认证凭证已失效")

        user_role = user.role.value if hasattr(user.role, 'value') else user.role
        if user_role in ("admin", "super_admin"):
            return user
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要角色: {', '.join(roles)}",
            )
        return user

    return _check


def require_write_permission(write_perm: str):
    """路由级「读放行 / 写授权」守卫 (P2, 卡 1bd3b6e2)。

    全局 enforce_auth 已统一强制认证 (白名单除外); 本守卫只补授权:
      - GET / HEAD / OPTIONS: 直接放行 — 保持既有读访问 (仅认证, 不查权限),
        避免对读端点引入回归。
      - POST / PUT / PATCH / DELETE: 委托 require_permission(write_perm) 校验。
        admin/super_admin 恒通过; 持 write_perm 的角色 (operator/现场运营角色) 通过;
        viewer/auditor (不持任何写权限) → 403。

    用于业务模块路由整体挂载: viewer 可读不可写, 写需对应 module:manage 权限。
    用法:
      router = APIRouter(dependencies=[Depends(require_write_permission("fleet:manage"))])

    设计要点:
    - 复用 require_permission 的 token 解码 + admin 旁路 + 权限矩阵查询, 不重复实现。
    - 路由级依赖在请求体解析前执行, 故 viewer 写请求即使 body 非法也先得 403
      (不会被 422 掩盖), 利于测试断言。
    """
    inner = require_permission(write_perm)

    async def _check(
        request: Request,
        token: str = Depends(oauth2_scheme),
    ):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None  # 读: 仅认证 (全局 enforce_auth 保障)
        return await inner(token=token)

    return _check