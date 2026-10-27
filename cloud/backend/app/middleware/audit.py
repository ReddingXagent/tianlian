"""
审计日志中间件 — ASGI 自动拦截 + @audit_log 装饰器

ASGI 中间件自动记录所有 POST/PUT/DELETE 请求到审计日志。
装饰器用于精细控制特定路由的审计细节。
"""
from __future__ import annotations

import functools
import logging
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

# ─── 不需要审计的路径前缀 ───
SKIP_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/health",
    "/api/v1/operation-log",
    "/api/v1/operation-log/stats",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
}

# ─── 写操作 HTTP 方法 ───
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    ASGI 中间件 — 自动拦截 POST/PUT/PATCH/DELETE 请求并记录审计日志
    不会阻塞请求处理，审计失败不影响业务逻辑。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 非写操作或跳过路径 → 直接放行
        if request.method not in WRITE_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(skip) for skip in SKIP_PATHS):
            return await call_next(request)

        # 用户信息在 call_next 之后提取 —— enforce_auth (路由依赖) 在请求处理期才把
        # 用户挂到 request.state.user (卡 a1c26a22), 提取必须晚于依赖执行。

        # 提取 IP
        ip_address = None
        try:
            ip_address = request.client.host if request.client else None
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip_address = forwarded.split(",")[0].strip()
        except Exception:
            pass

        # 推断 action
        action_map = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
        action = action_map.get(request.method, "other")

        # 推断 module (从 URL 路径第二段)
        parts = path.strip("/").split("/")
        module = parts[2] if len(parts) > 2 else parts[-1] if parts else "unknown"

        # 提取 target_id (路径中最后的数字)
        target_id = None
        for part in reversed(parts):
            if part.isdigit():
                target_id = part
                break

        detail = f"{request.method} {path}"

        # 用户变量先初始化 —— call_next 抛异常 (5xx) 时 except 分支要引用,
        # 若只在 try 内赋值会 UnboundLocalError → failure 审计被吞永不落库
        user_id = None
        username = None

        # 执行请求
        try:
            response = await call_next(request)

            # 尝试提取用户信息（不阻塞; enforce_auth 已在此前执行并挂 state）
            try:
                if hasattr(request.state, "user"):
                    user = request.state.user
                    user_id = getattr(user, "id", None)
                    username = getattr(user, "username", None)
            except Exception:
                pass

            # 匿名/未认证请求不落审计 (无 user 可归属, 避免噪音)
            if not user_id:
                return response

            if 200 <= response.status_code < 300:
                # 成功写操作
                try:
                    audit_service.log_crud(
                        user_id=user_id,
                        username=username or "unknown",
                        action=action,
                        module=module,
                        target_id=target_id,
                        target_desc=f"{action} {module} #{target_id}" if target_id else f"{action} {module}",
                        detail=detail,
                        ip=ip_address,
                    )
                except Exception as e:
                    logger.warning("审计日志记录失败: %s", e)
            elif response.status_code >= 400:
                # 业务拒绝/校验失败/越权 (409/422/403...) 是攻击与误操作探测信号,
                # 必须留痕 result=failure (修复前该分支零审计)
                try:
                    audit_service.log(
                        user_id=user_id,
                        username=username or "unknown",
                        action=action,
                        module=module,
                        target_id=target_id,
                        detail=detail,
                        ip_address=ip_address,
                        result="failure",
                        error_msg=f"HTTP {response.status_code}",
                    )
                except Exception as e:
                    logger.warning("审计日志记录失败: %s", e)
            return response
        except Exception as e:
            # 操作失败也记录 (call_next 抛异常时依赖已执行, state.user 已可提取)
            try:
                if hasattr(request.state, "user"):
                    user = request.state.user
                    user_id = getattr(user, "id", None)
                    username = getattr(user, "username", None)
            except Exception:
                pass
            try:
                audit_service.log(
                    user_id=user_id,
                    username=username or "unknown",
                    action=action,
                    module=module,
                    target_id=target_id,
                    detail=detail,
                    ip_address=ip_address,
                    result="failure",
                    error_msg=str(e)[:200],
                )
            except Exception:
                pass
            raise


# ═══════════════════════════════════════════
# 装饰器方式 (精细控制)
# ═══════════════════════════════════════════


def audit_action(
    action: str,
    module: str,
    target_id_fn: Optional[Callable] = None,
    target_desc_fn: Optional[Callable] = None,
    detail_fn: Optional[Callable] = None,
) -> Callable:
    """
    审计日志装饰器 — 自动在 API 路由函数执行后记录操作

    用法:
        @router.delete("/users/{user_id}")
        @audit_action("delete", "users",
                       target_id_fn=lambda r, kwargs: kwargs.get("user_id"),
                       target_desc_fn=lambda r, kwargs: f"删除用户 {kwargs.get('user_id')}")
        async def delete_user(user_id: int, db: Session = Depends(get_db)):
            ...

    参数:
        action: 操作类型 (create/update/delete/export/config 等)
        module: 模块名 (users/devices/alarms/workorders 等)
        target_id_fn: 从路由参数中提取 target_id 的 lambda
        target_desc_fn: 生成 target_desc 的 lambda
        detail_fn: 生成 detail 的 lambda
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 执行原函数
            result = await func(*args, **kwargs)

            try:
                # 尝试从 kwargs 中获取当前用户和请求信息
                current_user = None
                for v in kwargs.values():
                    if hasattr(v, 'id') and hasattr(v, 'username') and hasattr(v, 'role'):
                        current_user = v
                        break

                if current_user:
                    target_id = target_id_fn(result, kwargs) if target_id_fn else None
                    target_desc = target_desc_fn(result, kwargs) if target_desc_fn else None
                    detail = detail_fn(result, kwargs) if detail_fn else None

                    audit_service.log_crud(
                        user_id=current_user.id,
                        username=current_user.username,
                        action=action,
                        module=module,
                        target_id=str(target_id) if target_id else None,
                        target_desc=target_desc,
                        detail=detail,
                    )
                else:
                    logger.debug("审计日志: 未找到当前用户信息, 跳过记录")
            except Exception as e:
                logger.warning("审计日志记录失败: %s", e)

            return result
        return wrapper
    return decorator


def audit_crud(module: str) -> Callable:
    """
    简化的 CRUD 审计装饰器
    自动从路由参数中提取 user_id 等信息

    用法:
        @router.post("/devices")
        @audit_crud("devices")
        async def create_device(current_user=Depends(get_current_user), ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 从函数名推断 action
            fn_name = func.__name__
            if 'create' in fn_name or 'add' in fn_name:
                action = 'create'
            elif 'delete' in fn_name or 'remove' in fn_name:
                action = 'delete'
            elif 'update' in fn_name or 'edit' in fn_name or any(x in fn_name for x in ['put', 'patch']):
                action = 'update'
            elif 'export' in fn_name:
                action = 'export'
            else:
                action = 'update'

            # 找出当前用户
            current_user = None
            for v in kwargs.values():
                if hasattr(v, 'id') and hasattr(v, 'username'):
                    current_user = v
                    break

            try:
                result = await func(*args, **kwargs)

                if current_user:
                    target_id = None
                    for k, v in kwargs.items():
                        if k.endswith('_id') or k == 'id' or k.endswith('Id'):
                            target_id = v
                            break

                    audit_service.log_crud(
                        user_id=current_user.id,
                        username=current_user.username,
                        action=action,
                        module=module,
                        target_id=str(target_id) if target_id else None,
                        target_desc=f"{module} {action} 操作",
                    )

                return result
            except Exception as e:
                # 即使操作失败也记录审计日志
                if current_user:
                    audit_service.log(
                        user_id=current_user.id,
                        username=current_user.username,
                        action=action,
                        module=module,
                        result='failure',
                        error_msg=str(e)[:200],
                    )
                raise
        return wrapper
    return decorator
