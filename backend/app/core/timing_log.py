"""请求级 timing 分段埋点 (卡 f78a8e44)

给生产慢请求簇 (telemetry/batch-report + pod/heartbeat) 加结构化分段日志,
抓突发窗实证, 定位 uvicorn 单进程 + 同步 SQLAlchemy 串行化写入的瓶颈段。

契约: 仅日志输出, 不改任何 API 行为。固定键 endpoint / batch_size / total_ms /
auth_ms / parse_ms / insert_ms / commit_ms, key=value 紧凑格式, 便于生产
journalctl 直接 grep "total_ms" / "slow_write_request" 抓突发窗。
"""
import logging

logger = logging.getLogger("app.core.timing_log")

# total_ms >= 阈值 视为慢请求, 走 warning 突显; 否则 info。
SLOW_THRESHOLD_MS = 500.0

# 输出顺序固定, 保证 journalctl 字段顺序稳定可读。
_FIXED_KEYS = (
    "endpoint",
    "batch_size",
    "total_ms",
    "auth_ms",
    "parse_ms",
    "insert_ms",
    "commit_ms",
)


def emit_write_timing(
    endpoint: str,
    batch_size: int,
    *,
    auth_ms: float,
    parse_ms: float,
    insert_ms: float,
    commit_ms: float,
    total_ms: float,
) -> None:
    """输出一条请求级 timing 分段日志。

    Args:
        endpoint: 端点标识(如 "telemetry/batch-report" / "pod/heartbeat")。
        batch_size: 本请求写入条数(heartbeat 等单条写端点固定 1)。
        auth_ms / parse_ms / insert_ms / commit_ms: 各段耗时(ms), 由调用方测。
        total_ms: 请求整体耗时(ms), 由调用方测(不强制等于各段之和)。

    total_ms >= SLOW_THRESHOLD_MS → logger.warning; 否则 logger.info。
    """
    fields = {
        "endpoint": endpoint,
        "batch_size": batch_size,
        "total_ms": round(total_ms, 2),
        "auth_ms": round(auth_ms, 2),
        "parse_ms": round(parse_ms, 2),
        "insert_ms": round(insert_ms, 2),
        "commit_ms": round(commit_ms, 2),
    }
    kv = " ".join(f"{k}={fields[k]}" for k in _FIXED_KEYS)
    if total_ms >= SLOW_THRESHOLD_MS:
        logger.warning("slow_write_request %s", kv)
    else:
        logger.info("write_request_timing %s", kv)
