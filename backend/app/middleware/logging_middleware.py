"""
日志监控中间件

功能:
  - 每个请求自动注入 request_id (从请求头 X-Request-ID 或自动生成)
  - 记录请求方法/路径/状态码/处理耗时
  - 超过 100ms 标记 WARNING
  - 敏感信息自动脱敏
  - 响应头返回 X-Request-ID
  - 请求速率统计 (requests/s)
  - p50/p95/p99 延迟统计

吞吐量统计使用滑动窗口:
  _request_window: deque 存储 (timestamp_sec) 用于每秒计算请求速率
  REQUEST_LATENCY Histogram 自动提供 p50/p95/p99 (Prometheus _bucket 分桶)
"""
import time
import logging
from collections import deque
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.log_config import (
    set_request_id,
    set_user_id,
    set_client_ip,
    generate_request_id,
    get_request_id,
)
from app.metrics import observe_api_request, set_request_rate

logger = logging.getLogger("app.middleware.request")


# ─── 吞吐量统计 ───

# 滑动窗口：存储最近 10s 的请求时间戳（用于计算 requests/s）
_request_window: deque = deque(maxlen=10000)

# 最近一次更新 REQUEST_RATE gauge 的时间
_last_rate_update: float = 0.0

# 速率更新间隔（秒）
_RATE_UPDATE_INTERVAL: float = 5.0


def _update_request_rate():
    """
    更新请求速率统计
    使用滑动窗口法：统计过去 window_seconds 秒内的请求数 / window_seconds
    """
    global _last_rate_update
    now = time.time()

    # 减少 gauge 写入频率，避免不必要的开销
    if now - _last_rate_update < _RATE_UPDATE_INTERVAL:
        return

    window_seconds = 10.0
    cutoff = now - window_seconds

    # 清理过期记录（保留 deque 中最近的记录）
    while _request_window and _request_window[0] < cutoff:
        _request_window.popleft()

    count = len(_request_window)
    rate = count / window_seconds if window_seconds > 0 else 0.0
    set_request_rate(round(rate, 2))
    _last_rate_update = now


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    请求 ID 注入中间件
    
    为每个请求生成唯一 ID，注入到 contextvars 和响应头
    """

    async def dispatch(self, request: Request, call_next):
        # 从请求头获取或自动生成 request_id
        request_id = request.headers.get("X-Request-ID", generate_request_id())
        set_request_id(request_id)

        # 记录开始时间
        start_time = time.time()
        # round2f: 高精度起点, 供 dep 层测量 middleware→dep 调度延迟
        request.state.mw_inner_start = time.perf_counter()

        # 提取用户 IP
        client_ip = request.client.host if request.client else "-"
        set_client_ip(client_ip)

        # 提取用户 ID (如果已认证，从 JWT 解析)
        user_id = getattr(request.state, "user_id", "-")
        if user_id and user_id != "-":
            set_user_id(user_id)

        method = request.method
        path = request.url.path

        # 记录请求到滑动窗口（用于速率统计）
        _request_window.append(time.time())

        # 记录请求开始
        logger.info(
            "→ %s %s",
            method, path,
            extra={
                "method": method,
                "path": path,
                "client_ip": client_ip,
            },
        )

        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)
            duration_sec = duration_ms / 1000.0
            status_code = response.status_code

            # 记录详细的 API 请求延迟到 Prometheus
            observe_api_request(method, path, status_code, duration_sec)

            # 更新请求速率（滑动窗口）
            _update_request_rate()

            # 耗时超过 100ms 用 WARNING 级别记录
            log_level = logger.warning if duration_ms > 100 else logger.info
            log_level(
                "← %s %s %d %.1fms",
                method, path, status_code, duration_ms,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )

            # 响应头返回 request_id，方便前端排查
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            duration_sec = duration_ms / 1000.0

            # 记录错误请求的延迟
            observe_api_request(method, path, 500, duration_sec)
            _update_request_rate()

            logger.error(
                "← %s %s ERROR %.1fms: %s",
                method, path, duration_ms, str(exc),
                extra={
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )
            response = JSONResponse(
                status_code=500,
                content={"code": 500, "message": "服务器内部错误", "data": None},
            )
            response.headers["X-Request-ID"] = request_id
            return response


class RequestBodySizeMiddleware(BaseHTTPMiddleware):
    """限制请求体大小，防止大 payload 攻击"""

    MAX_SIZE = 10 * 1024 * 1024  # 10MB

    # 卡7502e6fb 缺陷2: 固件包(.bin 常见 20MB+)走独立上限; 端点内自设硬上限防滥用
    FIRMWARE_UPLOAD_PATHS = {"/api/v1/gateways/firmware/upload"}
    FIRMWARE_UPLOAD_MAX_SIZE = 200 * 1024 * 1024  # 200MB

    async def dispatch(self, request: Request, call_next):
        max_size = (
            self.FIRMWARE_UPLOAD_MAX_SIZE
            if request.url.path in self.FIRMWARE_UPLOAD_PATHS
            else self.MAX_SIZE
        )
        content_length = request.headers.get("content-length")
        if content_length:
            # content-length 头客户端可控; 非数字须优雅 400, 不应 int() ValueError
            # 冒泡被外层中间件吞成 500 + ERROR 日志噪声 (曾为 bug, 卡 50b47060 收尾)
            try:
                content_length_int = int(content_length)
            except (TypeError, ValueError):
                request_id = get_request_id()
                logger.warning(
                    "非法 Content-Length 头: %s",
                    content_length,
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": 400,
                        "request_id": request_id,
                    },
                )
                return JSONResponse(
                    status_code=400,
                    content={"code": 400, "message": "非法的 Content-Length 头", "data": None},
                    headers={"X-Request-ID": request_id},
                )
            if content_length_int > max_size:
                request_id = get_request_id()
                logger.warning(
                    "请求体过大: %s > %s",
                    content_length, max_size,
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": 413,
                        "request_id": request_id,
                    },
                )
                return JSONResponse(
                    status_code=413,
                    content={"code": 413, "message": f"请求体过大，最大允许 {max_size // (1024 * 1024)}MB", "data": None},
                    headers={"X-Request-ID": request_id},
                )
        return await call_next(request)