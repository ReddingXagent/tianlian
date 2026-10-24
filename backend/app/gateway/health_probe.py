"""
数据管道健康探针
检查所有协议网关的连接状态、吞吐量、延迟
支持断连自动重试（指数退避）+ 告警通知集成（on_alert 回调注入）

Phase33-Task3:
  - record_request 增加 latency_ms，统计平均延迟
  - reconnect_adapter 增加 on_alert 回调，重连失败触发告警
  - monitor_and_reconnect 编排：断连感知 → 自动重连 → 失败告警
"""
from typing import Dict, Any, Optional, Callable
import time
import asyncio
import logging
from .registry import get_registry

logger = logging.getLogger(__name__)

_last_metrics: Dict[str, Any] = {
    "total_requests": 0,
    "total_errors": 0,
    "total_bytes": 0,
    "total_latency_ms": 0.0,
    "latency_count": 0,
    "start_time": time.time()
}


def _reset_metrics() -> None:
    """重置统计计数器（测试与冷启动用）"""
    global _last_metrics
    _last_metrics = {
        "total_requests": 0,
        "total_errors": 0,
        "total_bytes": 0,
        "total_latency_ms": 0.0,
        "latency_count": 0,
        "start_time": time.time(),
    }


def record_request(bytes_count: int = 0, error: bool = False, latency_ms: Optional[float] = None):
    """记录一次请求统计

    Args:
        bytes_count: 本次请求字节数
        error: 是否出错
        latency_ms: 本次请求延迟（毫秒），累计后用于计算平均延迟
    """
    _last_metrics["total_requests"] += 1
    _last_metrics["total_bytes"] += bytes_count
    if error:
        _last_metrics["total_errors"] += 1
    if latency_ms is not None:
        _last_metrics["total_latency_ms"] += latency_ms
        _last_metrics["latency_count"] += 1


def _avg_latency_ms() -> float:
    """平均延迟（毫秒），无样本返回 0"""
    count = _last_metrics["latency_count"]
    if count <= 0:
        return 0
    return round(_last_metrics["total_latency_ms"] / count, 2)


async def check_gateway_health() -> Dict[str, Any]:
    """检查所有已注册协议的健康状态"""
    registry = get_registry()
    protocols = registry.list_protocols()
    device_types = registry.list_device_types()

    elapsed = time.time() - _last_metrics["start_time"]
    requests_per_sec = _last_metrics["total_requests"] / elapsed if elapsed > 0 else 0

    return {
        "protocols": {
            "registered_count": len(protocols),
            "registered": [{"type": k, "adapter": v} for k, v in protocols.items()],
            "device_type_mappings": device_types
        },
        "throughput": {
            "total_requests": _last_metrics["total_requests"],
            "total_errors": _last_metrics["total_errors"],
            "total_bytes": _last_metrics["total_bytes"],
            "requests_per_sec": round(requests_per_sec, 2),
            "avg_latency_ms": _avg_latency_ms(),
            "error_rate_pct": round(
                _last_metrics["total_errors"] / _last_metrics["total_requests"] * 100, 2
            ) if _last_metrics["total_requests"] > 0 else 0
        }
    }


def get_throughput_stats() -> Dict[str, Any]:
    """获取吞吐量统计"""
    elapsed = time.time() - _last_metrics["start_time"]
    requests_per_sec = _last_metrics["total_requests"] / elapsed if elapsed > 0 else 0
    return {
        "total_requests": _last_metrics["total_requests"],
        "total_errors": _last_metrics["total_errors"],
        "total_bytes": _last_metrics["total_bytes"],
        "requests_per_sec": round(requests_per_sec, 2),
        "avg_latency_ms": _avg_latency_ms(),
        "uptime_seconds": round(elapsed),
        "error_rate_pct": round(
            _last_metrics["total_errors"] / _last_metrics["total_requests"] * 100, 2
        ) if _last_metrics["total_requests"] > 0 else 0
    }


async def reconnect_adapter(
    device_type: str,
    config: Dict[str, Any],
    max_retries: int = 3,
    on_alert: Optional[Callable[[str, str, str], None]] = None,
) -> bool:
    """
    重连指定协议适配器（指数退避）

    重试间隔: 1s, 2s, 4s

    Args:
        on_alert: 重连失败告警回调 (device_type, message, level)，由调用方注入真实告警实现
    """
    registry = get_registry()
    adapter = registry.get_adapter(device_type, config)
    if not adapter:
        logger.warning("重连失败: 设备类型 %s 无适配器", device_type)
        if on_alert:
            on_alert(device_type, f"{device_type} 断连重连失败：未注册适配器", "warning")
        return False

    base_delay = 1.0
    for attempt in range(max_retries):
        delay = base_delay * (2 ** attempt)
        try:
            logger.info("重连 %s 第%d次尝试 (延迟%ds)...", device_type, attempt+1, delay)
            await adapter.disconnect()
            await asyncio.sleep(delay)
            result = await adapter.connect()
            if result:
                logger.info("%s 重连成功", device_type)
                return True
        except Exception as e:
            logger.error("%s 第%d次重连失败: %s", device_type, attempt+1, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)

    logger.error("%s 重连失败（已重试%d次）", device_type, max_retries)
    if on_alert:
        on_alert(device_type, f"{device_type} 断连，已重试 {max_retries} 次仍失败", "critical")
    return False


async def monitor_and_reconnect(
    device_type: str,
    config: Dict[str, Any],
    on_alert: Optional[Callable[[str, str, str], None]] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    断连自动重连编排：感知断连 → 自动重连 → 失败告警

    检查适配器连接状态，断连时自动调用 reconnect_adapter 重连；
    重连失败由 reconnect_adapter 通过 on_alert 触发告警通知。

    Returns:
        attempted: 是否尝试过重连（已连接则为 False）
        reconnected: 最终是否连接成功
        reason: 结果原因
    """
    registry = get_registry()
    adapter = registry.get_adapter(device_type, config)
    if adapter is None:
        if on_alert:
            on_alert(device_type, f"{device_type} 监控失败：未注册适配器", "warning")
        return {"attempted": False, "reconnected": False, "reason": "no_adapter"}
    if getattr(adapter, "is_connected", lambda: False)():
        return {"attempted": False, "reconnected": True, "reason": "already_connected"}
    ok = await reconnect_adapter(device_type, config, max_retries=max_retries, on_alert=on_alert)
    return {
        "attempted": True,
        "reconnected": ok,
        "reason": "reconnected" if ok else "reconnect_failed",
    }
