"""metrics 中间件 label 规范化测试 — 卡 284132f2

路径参数(device_id/station_id/wo_id 等)若以原始 URL 做 prometheus label,
每个唯一参数值产生一条永久 series → prometheus_client 堆随时间无界膨胀 →
放大 CPython full-GC 停顿(单 worker 表现为间歇 loop_lag)。
验证 label 取路由模板(基数有界)而非原始 path。
"""
from __future__ import annotations

from types import SimpleNamespace

from starlette.requests import Request

from app.metrics import _metric_path_label


def _make_request(path: str, route_path: str | None = None) -> Request:
    """构造最小 Starlette Request; route_path=None 模拟未匹配(无 scope["route"])。"""
    scope: dict = {
        "type": "http",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    if route_path is not None:
        # 真实 Starlette Route 匹配后 scope["route"] 暴露 .path 模板串
        scope["route"] = SimpleNamespace(path=route_path)
    return Request(scope)


def test_path_label_uses_route_template_when_matched():
    """匹配到路由 → label 用模板(含 {param}), 不暴露真实 id。"""
    req = _make_request(
        path="/api/v1/telemetry/device/12345/latest",
        route_path="/api/v1/telemetry/device/{device_id}/latest",
    )
    label = _metric_path_label(req)
    assert label == "/api/v1/telemetry/device/{device_id}/latest"
    assert "12345" not in label


def test_path_label_bounded_across_distinct_ids():
    """不同 device_id 命中同一路由 → label 相同(基数有界, 不随 id 膨胀)。"""
    template = "/api/v1/telemetry/device/{device_id}/latest"
    r1 = _make_request("/api/v1/telemetry/device/1/latest", template)
    r2 = _make_request("/api/v1/telemetry/device/999/latest", template)
    assert _metric_path_label(r1) == _metric_path_label(r2) == template


def test_path_label_falls_back_to_raw_when_no_route():
    """未匹配(404/静态资源, scope 无 route)→ 回退原始 path, 行为同旧实现。"""
    req = _make_request("/api/v1/telemetry/batch-report", route_path=None)
    assert _metric_path_label(req) == "/api/v1/telemetry/batch-report"
