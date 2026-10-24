"""app/middleware/logging_middleware.py 日志/限流中间件单测

RequestIDMiddleware:
  - 响应头注入 X-Request-ID (自定义 header 透传 / 自动生成唯一)
  - 异常端点 → 500 JSON + X-Request-ID
  - 慢请求 (>100ms) WARNING / 快请求 INFO
RequestBodySizeMiddleware:
  - 超大 body → 413
  - 正常 body 放行 / 无 content-length 放行
_update_request_rate:
  - 间隔外触发 set_request_rate (滑窗 count/10s)
  - 间隔内跳过 / 过期条目清理
"""
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import logging_middleware as mw
from app.middleware.logging_middleware import (
    RequestBodySizeMiddleware,
    RequestIDMiddleware,
)


@pytest.fixture
def app():
    a = FastAPI()

    @a.get("/ok")
    async def ok():
        return {"hello": "world"}

    @a.get("/slow")
    async def slow():
        time.sleep(0.12)  # >100ms 触发 WARNING
        return {"slow": True}

    @a.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @a.post("/echo")
    async def echo():
        return {"ok": True}

    # RequestID 后 add → 最外层 dispatch 最先执行 (先 set_request_id),
    # 使内层 RequestBodySize 413 时 get_request_id() 已就绪。
    a.add_middleware(RequestBodySizeMiddleware)
    a.add_middleware(RequestIDMiddleware)
    return a


@pytest.fixture
def client(app):
    # raise_server_exceptions=False: 让 /boom 的 500 经中间件返回响应而非 raise
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clean_window():
    """隔离模块级滑动窗口 (client fixture 请求会向其 append)。"""
    mw._request_window.clear()
    yield
    mw._request_window.clear()


# ────────────────────────────────────────────────────────────────────
# request_id 注入
# ────────────────────────────────────────────────────────────────────
class TestRequestIdInjection:
    def test_response_has_auto_request_id(self, client):
        r = client.get("/ok")
        assert r.status_code == 200
        rid = r.headers.get("X-Request-ID")
        assert rid
        assert len(rid) == 16  # generate_request_id → 16 hex

    def test_custom_request_id_passthrough(self, client):
        r = client.get("/ok", headers={"X-Request-ID": "my-trace-id"})
        assert r.headers["X-Request-ID"] == "my-trace-id"

    def test_auto_generated_unique_per_request(self, client):
        r1 = client.get("/ok")
        r2 = client.get("/ok")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


# ────────────────────────────────────────────────────────────────────
# 异常处理
# ────────────────────────────────────────────────────────────────────
class TestExceptionHandling:
    def test_exception_returns_500_json_with_request_id(self, client):
        r = client.get("/boom")
        assert r.status_code == 500
        assert r.headers["X-Request-ID"]  # 异常路径仍注入
        body = r.json()
        assert body["code"] == 500
        assert body["message"] == "服务器内部错误"
        assert body["data"] is None


# ────────────────────────────────────────────────────────────────────
# 慢/快请求日志级别
# ────────────────────────────────────────────────────────────────────
class TestRequestLogLevel:
    def test_slow_request_logged_as_warning(self, client, caplog):
        caplog.set_level(logging.DEBUG, logger="app.middleware.request")
        r = client.get("/slow")
        assert r.status_code == 200
        completes = [
            rec for rec in caplog.records
            if "←" in rec.getMessage() and "GET" in rec.getMessage()
            and "/slow" in rec.getMessage()
        ]
        assert completes, "未捕获响应完成日志"
        assert completes[-1].levelno == logging.WARNING  # duration > 100ms

    def test_fast_request_logged_as_info(self, client, caplog):
        caplog.set_level(logging.DEBUG, logger="app.middleware.request")
        client.get("/ok")
        completes = [
            rec for rec in caplog.records
            if "←" in rec.getMessage() and "/ok" in rec.getMessage()
        ]
        assert completes
        assert completes[-1].levelno == logging.INFO  # duration <= 100ms


# ────────────────────────────────────────────────────────────────────
# 请求体大小限制
# ────────────────────────────────────────────────────────────────────
class TestRequestBodySize:
    def test_oversize_body_rejected_413(self, client, monkeypatch):
        monkeypatch.setattr(RequestBodySizeMiddleware, "MAX_SIZE", 100)
        r = client.post("/echo", content="x" * 200)  # 200 > 100
        assert r.status_code == 413
        assert r.headers["X-Request-ID"]
        body = r.json()
        assert body["code"] == 413

    def test_normal_size_accepted(self, client, monkeypatch):
        monkeypatch.setattr(RequestBodySizeMiddleware, "MAX_SIZE", 100)
        r = client.post("/echo", content="x" * 50)  # 50 <= 100
        assert r.status_code == 200

    def test_no_content_length_accepted(self, client):
        """无 content-length header → 放行 (chunked / 无 body)。"""
        r = client.post("/echo")
        assert r.status_code == 200

    def test_non_numeric_content_length_returns_400(self, client):
        """content-length 非数字 → 优雅 400。

        缺陷修复 (曾为 bug): int('not-a-number') 抛 ValueError 冒泡, 被外层
        RequestIDMiddleware 的 except 吞成 500 + ERROR 日志噪声。客户端可控头
        的非法值应判 400, 不应污染 500 监控。
        """
        r = client.post("/echo", headers={"content-length": "not-a-number"})
        assert r.status_code == 400
        assert r.headers["X-Request-ID"]
        body = r.json()
        assert body["code"] == 400


# ────────────────────────────────────────────────────────────────────
# _update_request_rate 滑动窗口
# ────────────────────────────────────────────────────────────────────
class TestUpdateRequestRate:
    def test_writes_rate_when_interval_elapsed(self, monkeypatch):
        monkeypatch.setattr(mw, "_last_rate_update", 0.0)  # 强制触发 (now - 0 >= 5)
        now = time.time()
        mw._request_window.extend([now, now, now, now, now])  # 5 个最近
        called = []
        monkeypatch.setattr(mw, "set_request_rate", lambda rate: called.append(rate))
        mw._update_request_rate()
        assert called == [0.5]  # 5 / 10s

    def test_skipped_within_interval(self, monkeypatch):
        monkeypatch.setattr(mw, "_last_rate_update", time.time())  # 刚更新过
        called = []
        monkeypatch.setattr(mw, "set_request_rate", lambda rate: called.append(rate))
        mw._update_request_rate()
        assert called == []  # 间隔 < 5s, 跳过

    def test_expired_entries_evicted(self, monkeypatch):
        monkeypatch.setattr(mw, "_last_rate_update", 0.0)
        now = time.time()
        mw._request_window.extend([now - 20, now - 15, now, now, now])  # 2 过期 + 3 最近
        called = []
        monkeypatch.setattr(mw, "set_request_rate", lambda rate: called.append(rate))
        mw._update_request_rate()
        assert called == [0.3]  # 清理后剩 3 个最近 / 10s
        assert len(mw._request_window) == 3
