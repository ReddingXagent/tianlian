"""caplog 环境噪声守卫 (卡 057c8a9e)

根因: RequestIDMiddleware 对 duration>100ms 的请求发 WARNING (logger
"app.middleware.request")。串行全量长跑机器负载高时, login/测试内请求随机超
100ms → 该 WARNING 实时混入当前测试 caplog.records → 严格断言族
(all(levelno < WARNING) / 条数 / records[0]) 随机红; 轻载重放即绿
(卡 145af9a1 不可复现之谜同根因)。

conftest 的 autouse fixture _silence_env_slow_request_log 在测试边界把
"app.middleware.request" 压到 ERROR 并 teardown 恢复 (显式测中间件日志的
tests/core/test_logging_middleware.py 自带 caplog.set_level(DEBUG, ...) 前置
覆盖, 不受影响)。本守卫用「真实慢请求 + test_timing_log 同款严格断言」组合:
隔离一旦被移除, 本文件立即 RED —— 防 caplog 断言族回归。
"""
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.logging_middleware import RequestIDMiddleware
from app.core.timing_log import emit_write_timing


@pytest.fixture
def slow_app():
    """最小真中间件 app: /slow 稳定 >100ms → RequestIDMiddleware 发 WARNING。"""
    a = FastAPI()

    @a.get("/slow")
    async def slow():
        time.sleep(0.12)  # >100ms 阈值, 稳定触发慢请求 WARNING
        return {"slow": True}

    a.add_middleware(RequestIDMiddleware)
    return a


class TestSlowRequestNoiseIsolated:
    def test_timing_log_strict_assert_survives_real_slow_request(self, slow_app, caplog):
        """受害形态复刻: 同窗口真实慢请求下, timing_log 严格断言不得被噪声击穿。

        复现链 (修复前 RED): ← GET /slow 200 1xx.xms (WARNING) 实时进
        caplog.records → all(levelno < WARNING) 断言失败。
        """
        caplog.set_level(logging.INFO, logger="app.core.timing_log")
        emit_write_timing(
            "telemetry/batch-report", 3,
            auth_ms=1.0, parse_ms=2.0, insert_ms=10.0, commit_ms=5.0,
            total_ms=18.0,
        )
        with TestClient(slow_app) as c:
            r = c.get("/slow")
        assert r.status_code == 200
        noisy = [rec.getMessage() for rec in caplog.records if rec.levelno >= logging.WARNING]
        assert not noisy, f"慢请求 WARNING 噪声混入 caplog (隔离失效): {noisy}"

    def test_middleware_explicit_set_level_still_captures(self, slow_app, caplog):
        """兼容性守护: 显式 caplog.set_level(DEBUG, "app.middleware.request")
        的中间件行为测试 (同 tests/core/test_logging_middleware.py 形态) 仍能
        捕获慢请求 WARNING —— 隔离不得吞掉显式被测行为。
        """
        caplog.set_level(logging.DEBUG, logger="app.middleware.request")
        with TestClient(slow_app) as c:
            r = c.get("/slow")
        assert r.status_code == 200
        completes = [
            rec for rec in caplog.records
            if "←" in rec.getMessage() and "/slow" in rec.getMessage()
        ]
        assert completes, "显式 set_level 下未捕获响应完成日志"
        assert completes[-1].levelno == logging.WARNING
