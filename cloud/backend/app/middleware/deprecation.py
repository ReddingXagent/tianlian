"""
废弃端点响应头中间件 (卡 b1faf814, Phase2-B3)

对路由定义已标 deprecated=True 的端点, 响应自动注入:
  - Deprecation: true   (RFC draft-potentially-deprecated 语义)
  - Sunset: <HTTP-date> (RFC 8594, 移除日期占位)

路由定义即契约源: 端点标了 deprecated 就带头, 没标就不带, 零逐端点改动。
首用场景: 旧 OpsInvoice 发票本体族 7 端点 (B1-2a 卡 6d06831d 已标),
titles 族与新体系 /ops/invoice-requests 未标, 不受影响。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 占位: 下版本移除日期 (合并计划 §3.2 "保留一个版本周期"), 拍板后可改
SUNSET_PLACEHOLDER = "Fri, 01 Jan 2027 00:00:00 GMT"


class DeprecationHeaderMiddleware(BaseHTTPMiddleware):
    """deprecated 路由响应头注入。

    FastAPI 匹配路由后会把 APIRoute 放进 request.scope['route'],
    其 deprecated 属性即路由定义的标记 (含 include_router 透传)。
    404/未匹配时 scope 无 route → 自然跳过, 不误伤。
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        route = request.scope.get("route")
        if route is not None and getattr(route, "deprecated", None):
            response.headers["Deprecation"] = "true"
            response.headers.setdefault("Sunset", SUNSET_PLACEHOLDER)
        return response
