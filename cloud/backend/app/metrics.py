"""
天链V3 Prometheus 指标暴露模块

使用方法:
    from app.metrics import setup_metrics
    setup_metrics(app)

自动在 /metrics 端点暴露 Prometheus 格式指标。
"""

import time
import os
from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry, multiprocess


# ─── 注册表 ───
REGISTRY = CollectorRegistry()
# 若使用多进程 (gunicorn)，自动切换 multiprocess 模式
if os.environ.get("PROMETHEUS_MULTIPROC_MODE"):
    multiprocess.MultiProcessCollector(REGISTRY)

# ─── 应用信息 ───
APP_INFO = Info("tianlian_app", "天链V3 应用信息", registry=REGISTRY)

# ─── HTTP 请求指标 ───
REQUEST_COUNT = Counter(
    "tianlian_http_requests_total",
    "HTTP 请求总数",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "tianlian_http_request_duration_seconds",
    "HTTP 请求延迟 (秒)",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

REQUEST_IN_FLIGHT = Gauge(
    "tianlian_http_requests_in_flight",
    "当前处理中的 HTTP 请求数",
    registry=REGISTRY,
)

# ─── 业务指标 ───
ACTIVE_ALARMS = Gauge(
    "tianlian_active_alarms",
    "当前活跃告警数",
    registry=REGISTRY,
)

DEVICES_ONLINE = Gauge(
    "tianlian_devices_online",
    "当前在线设备数",
    registry=REGISTRY,
)

DEVICES_TOTAL = Gauge(
    "tianlian_devices_total",
    "设备总数",
    registry=REGISTRY,
)

WORKORDERS_PENDING = Gauge(
    "tianlian_workorders_pending",
    "待处理工单数",
    registry=REGISTRY,
)

WORKORDERS_TOTAL_TODAY = Gauge(
    "tianlian_workorders_created_today",
    "今日创建工单数",
    registry=REGISTRY,
)

WORKORDERS_COMPLETED_TODAY = Gauge(
    "tianlian_workorders_completed_today",
    "今日完成工单数",
    registry=REGISTRY,
)

GATEWAYS_ONLINE = Gauge(
    "tianlian_gateways_online",
    "在线网关数",
    registry=REGISTRY,
)

TELEMETRY_POINTS_PROCESSED = Counter(
    "tianlian_telemetry_points_processed_total",
    "遥测数据点处理总数",
    registry=REGISTRY,
)

DIAGNOSIS_TOTAL = Counter(
    "tianlian_diagnosis_total",
    "故障诊断请求总数",
    ["result"],
    registry=REGISTRY,
)

AI_TOKENS_USED = Counter(
    "tianlian_ai_tokens_used_total",
    "AI 诊断 Token 消耗总量",
    registry=REGISTRY,
)

# ─── 业务指标 (Phase35) ───

# 在线用户数
ACTIVE_USERS = Gauge(
    "tianlian_active_users",
    "当前在线用户数",
    registry=REGISTRY,
)

# 活跃设备数
ACTIVE_DEVICES = Gauge(
    "tianlian_active_devices",
    "当前活跃设备数",
    registry=REGISTRY,
)

# 告警速率 (带 level/type 标签)
ALARM_RATE = Counter(
    "tianlian_alarm_rate",
    "告警产生速率",
    ["level", "type"],
    registry=REGISTRY,
)

# 工单处理时长 (秒)
WORKORDER_DURATION = Histogram(
    "tianlian_workorder_duration_seconds",
    "工单处理时长 (秒)",
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600],
    registry=REGISTRY,
)

# API请求延迟 (秒) — 与现有 REQUEST_LATENCY 互补，添加 path label 明细
API_REQUEST_DURATION = Histogram(
    "tianlian_request_duration_seconds",
    "API 请求延迟 (秒)",
    ["method", "path", "status_code"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

# 队列积压
QUEUE_BACKLOG = Gauge(
    "tianlian_queue_backlog",
    "队列积压数",
    ["queue"],
    registry=REGISTRY,
)

# 请求速率 (requests/s) — 周期性写入
REQUEST_RATE = Gauge(
    "tianlian_request_rate_per_sec",
    "请求速率 (requests/s)",
    registry=REGISTRY,
)

# ─── 数据库指标 ───
DB_CONNECTION_POOL_SIZE = Gauge(
    "tianlian_db_connection_pool_size",
    "数据库连接池大小",
    registry=REGISTRY,
)

DB_CONNECTIONS_ACTIVE = Gauge(
    "tianlian_db_connections_active",
    "活跃数据库连接数",
    registry=REGISTRY,
)

DB_CONNECTIONS_IDLE = Gauge(
    "tianlian_db_connections_idle",
    "空闲数据库连接数",
    registry=REGISTRY,
)

DB_CONNECTIONS_WAITING = Gauge(
    "tianlian_db_connections_waiting",
    "等待数据库连接数",
    registry=REGISTRY,
)


def _metric_path_label(request: "Request") -> str:
    """返回用于 metrics label 的路径(卡 284132f2)。

    优先用路由模板(request.scope["route"].path, 如 /telemetry/device/{device_id}/latest),
    其基数有界(=路由数); 避免原始 request.url.path(含真实 id)产生无界唯一 label ——
    prometheus_client 对每个唯一 label 组合永久驻留一个 series, 路径参数(device_id /
    station_id / wo_id 等)会使 series 数随历史出现过的 id 无界增长 → 进程堆随时间膨胀 →
    放大 CPython full-GC 停顿(单 uvicorn worker 表现为间歇 loop_lag, 生产 200-1100ms)。
    路由模板在 routing 后由 scope["route"] 提供; 未匹配路由(404/静态, scope 无 route)时
    回退原始 path, 行为同旧实现。
    """
    template = getattr(request.scope.get("route"), "path", None)
    return template if template else request.url.path


def setup_metrics(app: FastAPI):
    """为 FastAPI 应用配置 Prometheus 指标中间件和端点"""

    APP_INFO.info({
        "name": getattr(app, "title", "天链V3"),
        "version": getattr(app, "version", "3.0.0"),
    })

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        REQUEST_IN_FLIGHT.inc()
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        REQUEST_IN_FLIGHT.dec()

        # 记录请求计数和延迟
        # 卡 284132f2: 用路由模板(基数有界)而非原始 URL 做 label —— 见 _metric_path_label
        endpoint = _metric_path_label(request)
        method = request.method
        status_code = response.status_code

        REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
        ).inc()

        REQUEST_LATENCY.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

        # 记录更细粒度的 API 请求延迟（含 path 和 status_code）
        observe_api_request(method, endpoint, status_code, duration)

        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Prometheus 指标端点"""
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app


# ─── 业务指标更新辅助函数 ───

def update_alarm_metrics(active_count: int):
    """更新活跃告警数"""
    ACTIVE_ALARMS.set(active_count)


def update_device_metrics(online: int, total: int):
    """更新设备指标"""
    DEVICES_ONLINE.set(online)
    DEVICES_TOTAL.set(total)


def update_workorder_metrics(pending: int, created_today: int, completed_today: int):
    """更新工单指标"""
    WORKORDERS_PENDING.set(pending)
    WORKORDERS_TOTAL_TODAY.set(created_today)
    WORKORDERS_COMPLETED_TODAY.set(completed_today)


def update_gateway_metrics(online: int):
    """更新网关指标"""
    GATEWAYS_ONLINE.set(online)


def increment_telemetry(count: int = 1):
    """递增遥测数据点计数"""
    TELEMETRY_POINTS_PROCESSED.inc(count)


def record_diagnosis(result_type: str):
    """记录一次诊断请求"""
    DIAGNOSIS_TOTAL.labels(result=result_type).inc()


def record_ai_tokens(count: int):
    """记录 AI Token 消耗"""
    AI_TOKENS_USED.inc(count)


def update_db_metrics(pool_size: int, active_connections: int, idle_connections: int = 0, waiting_connections: int = 0):
    """更新数据库连接池指标"""
    DB_CONNECTION_POOL_SIZE.set(pool_size)
    DB_CONNECTIONS_ACTIVE.set(active_connections)
    DB_CONNECTIONS_IDLE.set(idle_connections)
    DB_CONNECTIONS_WAITING.set(waiting_connections)


def update_active_users(count: int):
    """更新在线用户数"""
    ACTIVE_USERS.set(count)


def update_active_devices(count: int):
    """更新活跃设备数"""
    ACTIVE_DEVICES.set(count)


def record_alarm(level: str, alarm_type: str, count: int = 1):
    """记录告警产生"""
    ALARM_RATE.labels(level=level, type=alarm_type).inc(count)


def record_workorder_duration(duration_seconds: float):
    """记录工单处理时长"""
    WORKORDER_DURATION.observe(duration_seconds)


def observe_api_request(method: str, path: str, status_code: int, duration_seconds: float):
    """记录 API 请求延迟"""
    API_REQUEST_DURATION.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).observe(duration_seconds)


def update_queue_backlog(queue: str, count: int):
    """更新队列积压"""
    QUEUE_BACKLOG.labels(queue=queue).set(count)


def set_request_rate(rate: float):
    """设置请求速率"""
    REQUEST_RATE.set(rate)