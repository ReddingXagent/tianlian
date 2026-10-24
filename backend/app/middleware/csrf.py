"""
CSRF 防护中间件 — Double Submit Cookie 模式

适用于前后端分离架构:
  1. 后端在 Set-Cookie 中下发 csrf_token (HttpOnly=False, SameSite=Strict)
  2. 前端从 Cookie 读取 token, 通过 X-CSRF-Token 请求头回传
  3. 后端校验 Cookie 中的 token 与 Header 中的 token 一致

安全状态:
  - 仅保护非幂等方法 (POST/PUT/DELETE/PATCH)
  - GET/HEAD/OPTIONS 不校验 CSRF
  - 携带 Authorization: Bearer 的请求跳过 CSRF (JWT 天然免疫)
  - 开发环境可配置跳过
"""
import os
import secrets
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.response import error_response

logger = logging.getLogger(__name__)

# 免 CSRF 的路径 (健康检查、登录等)
CSRF_EXEMPT_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/alert-webhook",
    "/api/v1/pod/register",
    "/api/v1/pod/heartbeat",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
}

# 需要 CSRF 保护的 HTTP 方法
CSRF_PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double Submit Cookie CSRF 防护中间件"""

    CSRF_COOKIE_NAME = "tianlian_csrf_token"
    CSRF_HEADER_NAME = "x-csrf-token"
    TOKEN_LENGTH = 32

    def _is_exempt(self, request: Request) -> bool:
        """判断请求是否豁免 CSRF 校验"""
        # 方法豁免
        if request.method not in CSRF_PROTECTED_METHODS:
            return True

        # 路径豁免
        if request.url.path in CSRF_EXEMPT_PATHS:
            return True

        # JWT 认证豁免 (Bearer token 天然免疫 CSRF)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return True

        # API Key 认证豁免 (X-API-Key 天然免疫 CSRF)
        if request.headers.get("x-api-key"):
            return True

        # 开发环境可选跳过
        if settings.DEBUG and os.getenv("SKIP_CSRF", "false").lower() == "true":
            return True

        return False

    def _generate_token(self) -> str:
        """生成安全的 CSRF token"""
        return secrets.token_urlsafe(self.TOKEN_LENGTH)

    async def _generate_token_response(self, request: Request, call_next):
        """为响应注入 CSRF token Cookie"""
        response = await call_next(request)

        # 只在没有 token 时才生成新的
        existing_token = request.cookies.get(self.CSRF_COOKIE_NAME)
        if not existing_token:
            token = self._generate_token()
            response.set_cookie(
                key=self.CSRF_COOKIE_NAME,
                value=token,
                httponly=False,  # 前端需要读取
                samesite="strict",
                secure=os.getenv("ENV", "development") == "production",
                path="/",
                max_age=3600,  # 1小时过期
            )

        return response

    async def _validate_csrf(self, request: Request) -> bool:
        """校验 CSRF token"""
        cookie_token = request.cookies.get(self.CSRF_COOKIE_NAME)
        header_token = request.headers.get(self.CSRF_HEADER_NAME)

        if not cookie_token or not header_token:
            return False

        # 恒定时间比较 (防止时序攻击)
        return secrets.compare_digest(cookie_token, header_token)

    async def dispatch(self, request: Request, call_next):
        # 豁免请求直接放行
        if self._is_exempt(request):
            return await self._generate_token_response(request, call_next)

        # 校验 CSRF
        if not await self._validate_csrf(request):
            logger.warning(
                "CSRF 校验失败: %s %s (ip=%s)",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=403,
                content=error_response(403, "CSRF 校验失败，请刷新页面后重试"),
                headers={
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                },
            )

        # CSRF 校验通过，继续处理
        return await call_next(request)
