# -*- coding: utf-8 -*-
"""测试共享：FastAPI 路由路径收集工具。

fastapi 0.140+ / starlette 1.3+ 起，``include_router`` 的子路由被包装在
``_IncludedRouter(original_router)`` 中，不再扁平展开到 ``app.routes`` 顶层。
直接 ``[r.path for r in app.routes]`` 只能取到顶层注册项，漏掉所有经由
``include_router`` 挂载的子路由（即绝大多数业务端点）。

对此有两套互补的解法，按场景选用：

* HTTP API 端点 -> 读 ``app.openapi()["paths"]``（强制展开所有路由器），
  参考 ``tests/test_auth_enforcement.py::_all_endpoints``。
* WebSocket 端点 -> openapi schema **不收录** WS 路由，必须用本模块的
  :func:`collect_route_paths` 递归 ``original_router.routes`` 才能取到真实路径。
"""


def collect_route_paths(routes):
    """递归收集 routes 中所有路径（含 include_router 嵌套的子路由）。

    遍历每条路由：取其 ``path``（若有），再沿 ``original_router`` 属性下钻
    递归展开 ``_IncludedRouter`` 包装的子路由器。旧版 fastapi 无
    ``original_router`` 属性时退化为纯顶层遍历，保持向后兼容。
    """
    paths = []
    for r in routes:
        path = getattr(r, "path", None)
        if path:
            paths.append(path)
        original = getattr(r, "original_router", None)
        if original is not None:
            paths.extend(collect_route_paths(getattr(original, "routes", [])))
    return paths
