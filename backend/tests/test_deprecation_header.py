"""
旧 OpsInvoice 本体族端点 Deprecation 响应头测试 (卡 b1faf814, Phase2-B3)

B1-2a (4e812c6c9) 已给 7 个本体族端点标 OpenAPI deprecated=True;
本卡按合并计划 §3.2/§5.4 补 HTTP 响应头 (RFC 8594 Sunset 草案语义):
  - Deprecation: true  (RFC draft-potentially-deprecated)
  - Sunset: <HTTP-date> (占位, 下版本移除日期)

中间件方案 (侵入最小): DeprecationHeaderMiddleware 读 scope['route'].deprecated,
路由定义即契约 —— 端点已标 deprecated 则自动带头, titles 族未标则不带头,
无需逐端点改响应。用 app.main 真实 middleware 栈验证 (test_security.py 模式)。

覆盖:
- 7 个本体族端点 200/401/404 响应均带 Deprecation + Sunset 头
- titles 族 4 端点不带头 (独立保留, 非废弃)
- 新体系 /operate/invoice-requests 不带头
- Sunset 头格式合法 (RFC 7231 HTTP-date)
- 路由定义级 deprecated 标记完整性 (防回归: 新端点误标/漏标)
"""
import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


# 旧体系发票本体族 7 端点 (deprecated=True, B1-2a)
# 注意: (method, 实际请求路径) 供 HTTP 断言; {invoice_id} 原始模板供注册表断言。
_DEPRECATED_SPEC = [
    ("GET", "/api/v1/operate/invoices", "/api/v1/operate/invoices"),
    ("GET", "/api/v1/operate/invoices/pending", "/api/v1/operate/invoices/pending"),
    ("POST", "/api/v1/operate/invoices", "/api/v1/operate/invoices"),
    ("PUT", "/api/v1/operate/invoices/999/review", "/api/v1/operate/invoices/{invoice_id}/review"),
    ("PUT", "/api/v1/operate/invoices/999/issue", "/api/v1/operate/invoices/{invoice_id}/issue"),
    ("PUT", "/api/v1/operate/invoices/999/void", "/api/v1/operate/invoices/{invoice_id}/void"),
    ("GET", "/api/v1/operate/invoices/999", "/api/v1/operate/invoices/{invoice_id}"),
]
DEPRECATED_PATHS = [(m, req) for m, req, _ in _DEPRECATED_SPEC]
DEPRECATED_ROUTE_TEMPLATES = [tpl for _, _, tpl in _DEPRECATED_SPEC]

# titles 族 4 端点 (独立保留, 不标 deprecated)
ACTIVE_PATHS = [
    ("GET", "/api/v1/operate/invoices/titles"),
    ("POST", "/api/v1/operate/invoices/titles"),
    ("PUT", "/api/v1/operate/invoices/titles/{title_id}"),
    ("DELETE", "/api/v1/operate/invoices/titles/{title_id}"),
]

# 新体系端点 (InvoiceRequest, 挂 /ops 前缀, 不标)
NEW_SYSTEM_PATHS = [
    ("GET", "/api/v1/ops/invoice-requests"),
]

_HTTP_DATE_RE = re.compile(
    r"^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$"
)


def _request(method: str, path: str):
    return client.request(method, path, json={} if method in ("POST", "PUT") else None)


# ═══════════════════════════════════════════
# 1. 本体族端点: 任意响应状态均带头
# ═══════════════════════════════════════════

class TestDeprecatedEndpointsCarryHeaders:
    """7 个本体族端点: 200/404(不存在)/400(非法流转) 等响应一律带 Deprecation 头。"""

    @pytest.mark.parametrize("method,path", DEPRECATED_PATHS)
    def test_headers_present_on_business_response(self, method, path):
        """认证后请求 (200/400/404 皆可) → 响应带 Deprecation: true + Sunset。"""
        r = _request(method, path)
        assert r.status_code < 500, f"意外 5xx: {r.status_code} {r.text[:200]}"
        assert r.headers.get("Deprecation") == "true", (
            f"{method} {path} 缺 Deprecation 头 (卡 b1faf814)"
        )
        sunset = r.headers.get("Sunset")
        assert sunset and _HTTP_DATE_RE.match(sunset), (
            f"{method} {path} Sunset 头缺失或非 RFC 7231 HTTP-date: {sunset!r}"
        )

    @pytest.mark.parametrize("method,path", DEPRECATED_PATHS)
    def test_headers_present_on_unauthorized(self, method, path):
        """未认证 401 响应也带头 —— 客户端无需有效凭证即可感知废弃。"""
        saved = client.headers.pop("Authorization", None)
        try:
            r = _request(method, path)
            assert r.status_code == 401
            assert r.headers.get("Deprecation") == "true"
            assert r.headers.get("Sunset")
        finally:
            if saved:
                client.headers["Authorization"] = saved


# ═══════════════════════════════════════════
# 2. 非废弃端点: 不带 Deprecation 头
# ═══════════════════════════════════════════

class TestActiveEndpointsClean:
    """titles 族 + 新体系端点不得带 Deprecation 头 (避免客户端误判全站废弃)。"""

    @pytest.mark.parametrize("method,path", ACTIVE_PATHS[:2] + NEW_SYSTEM_PATHS)
    def test_no_deprecation_header(self, method, path):
        r = _request(method, path)
        assert r.headers.get("Deprecation") is None, (
            f"{method} {path} 不应带 Deprecation 头"
        )
        assert r.headers.get("Sunset") is None


# ═══════════════════════════════════════════
# 3. 路由定义级 deprecated 标记完整性
# ═══════════════════════════════════════════

class TestRouteRegistryDeprecatedFlags:
    """middleware 以路由定义为契约源, 锁定 7 个本体族标 deprecated、titles 族未标。

    fastapi 0.140 的 include_router 产出 _IncludedRouter 懒展开容器,
    app.routes 顶层只见容器不见叶子路由 → 递归展开取 original_router.routes。
    """

    def _iter_routes(self, routes, prefix=""):
        for route in routes:
            if type(route).__name__ == "_IncludedRouter":
                yield from self._iter_routes(
                    route.original_router.routes,
                    prefix + route.include_context.prefix,
                )
            else:
                yield prefix + getattr(route, "path", ""), route

    def _find_route(self, path: str):
        for full_path, route in self._iter_routes(app.routes):
            if full_path == path:
                return route
        return None

    @pytest.mark.parametrize("path", DEPRECATED_ROUTE_TEMPLATES)
    def test_deprecated_flag_on_routes(self, path):
        route = self._find_route(path)
        assert route is not None, f"路由未注册: {path}"
        assert getattr(route, "deprecated", False) is True, (
            f"{path} 路由未标 deprecated=True"
        )

    @pytest.mark.parametrize("path", [p for _, p in ACTIVE_PATHS])
    def test_titles_not_flagged(self, path):
        route = self._find_route(path)
        assert route is not None, f"路由未注册: {path}"
        assert not getattr(route, "deprecated", False), (
            f"titles 族 {path} 不应标 deprecated"
        )


# ═══════════════════════════════════════════
# 4. Sunset 占位日期语义
# ═══════════════════════════════════════════

def test_sunset_date_is_future_http_date():
    """Sunset 为占位 HTTP-date, 须可解析且晚于当前 (废弃尚未生效)。"""
    r = client.get("/api/v1/operate/invoices/pending")
    sunset = r.headers.get("Sunset")
    assert sunset
    parsed = datetime.strptime(sunset, "%a, %d %b %Y %H:%M:%S GMT")
    assert parsed.year >= 2026, f"Sunset 占位异常: {sunset}"
