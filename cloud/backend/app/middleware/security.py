"""
安全头中间件

自动为所有响应添加安全相关 HTTP 头:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 1; mode=block
  - Strict-Transport-Security (生产环境)
  - Referrer-Policy: strict-origin-when-cross-origin
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # 内容类型嗅探保护
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 禁止在 iframe 中加载
        response.headers["X-Frame-Options"] = "DENY"

        # XSS 过滤器（旧浏览器兼容）
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # HSTS（仅生产环境启用）
        if os.getenv("ENV", "development") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Referrer 策略
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 移除可能暴露内部信息的响应头
        if "Server" in response.headers:
            del response.headers["Server"]

        return response