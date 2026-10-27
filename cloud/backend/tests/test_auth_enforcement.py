"""
认证强制测试 (P0 安全)

验证所有非白名单 API 端点在无 token 时返回 401，白名单端点可匿名访问。
端点清单从 app.routes 动态提取，配合 auth.is_public_path 单一真相源，
确保新增端点自动纳入回归 —— 任何人新增裸露端点都会被这里捕获。
"""
import re
import pytest

from app.api.v1.auth import is_public_path

# 仅测这些方法（排除 HEAD/OPTIONS 等自动派生方法）
_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _all_endpoints(app):
    """提取 app 中所有 /api/v1/* HTTP 端点 -> [(method, concrete_path, is_public)]。

    fastapi 0.140 起 include_router 改为懒加载：v1 路由被包进 _IncludedRouter，
    不再扁平铺进 app.routes，isinstance(route, Route) 遍历会漏掉全部 v1 端点。
    因此改读 app.openapi() 的 paths —— 它强制展开所有已注册路由器，给出真实端点清单。

    路径参数 {xxx} 替换为 1，便于直接请求（认证依赖在资源解析前拦截，不依赖真实数据）。
    仅扫描 /api/v1/* —— 排除 FastAPI 自带的文档端点（/docs /openapi.json /redoc /），
    那些不纳入业务端点认证回归。
    """
    endpoints = []
    seen = set()
    for path, ops in app.openapi().get("paths", {}).items():
        if not path.startswith("/api/v1/"):
            continue
        for method in sorted(ops):
            method = method.upper()
            if method not in _HTTP_METHODS:
                continue
            concrete = re.sub(r"\{[^}]+\}", "1", path)
            key = (method, concrete)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append((method, concrete, is_public_path(path)))
    return endpoints


def test_protected_endpoints_require_auth(anon_client):
    """所有非白名单端点无 token 必须返回 401。"""
    failures = []
    checked = 0
    for method, path, public in _all_endpoints(anon_client.app):
        if public:
            continue
        checked += 1
        resp = anon_client.request(method, path)
        if resp.status_code != 401:
            failures.append(f"{method} {path} -> {resp.status_code}")
    assert checked > 0, "未提取到任何受保护端点，端点扫描逻辑可能有误"
    assert not failures, (
        f"{len(failures)}/{checked} 个受保护端点无 token 未返回 401:\n"
        + "\n".join(failures[:80])
    )


# 真正匿名可访问的端点：豁免全局认证 **且** 无自身认证。
# 注意 telemetry 不在此列 —— 它豁免全局 enforce_auth，但自身要求网关 X-API-Key
# 或 Bearer token（无 token 仍 401），属于"豁免全局、保留自身认证"的另一类。
_ANONYMOUS_ENDPOINTS = [
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/live"),
    ("GET", "/api/v1/livez"),
    ("GET", "/api/v1/ready"),
    ("GET", "/api/v1/readyz"),
    ("GET", "/api/v1/ping"),
    ("POST", "/api/v1/auth/login"),      # 缺表单 -> 422/400，但不应 401
    ("POST", "/api/v1/auth/register"),   # 缺 body -> 422，但不应 401
    ("POST", "/api/v1/auth/sms/send"),   # 缺 body -> 422，但不应 401
]


def test_anonymous_endpoints_accessible_without_token(anon_client):
    """真匿名端点无 token 不应返回 401（认证拒绝）。"""
    failures = []
    for method, path in _ANONYMOUS_ENDPOINTS:
        resp = anon_client.request(method, path)
        if resp.status_code == 401:
            failures.append(f"{method} {path} -> 401")
    assert not failures, (
        f"{len(failures)} 个匿名端点无 token 误返回 401:\n" + "\n".join(failures)
    )


def test_valid_token_passes_global_auth(client):
    """带有效 token（client fixture 默认注入 admin token）应通过全局认证。"""
    resp = client.get("/api/v1/users")
    assert resp.status_code != 401, f"有效 token 被全局认证拒绝: {resp.status_code}"
