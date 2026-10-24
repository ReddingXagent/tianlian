"""请求级 timing 分段埋点与调度诊断 warning

归集所有请求级 timing 仪表, 从 telemetry.py 抽离 (卡 4c8120a6 纯重构, 零行为变更):

- 两个 marker dep (timing_start_dep / timing_end_auth_dep): auth 在 dependencies
  阶段执行(先于端点函数体), 无法在端点内直接测耗时; 用 marker 在 auth 前后打点,
  经 request.state 把起点与 auth 结束点传给端点, 供 emit_write_timing 计算
  auth_ms / parse_ms。
- dispatch / auth_internal 慢调度 warning: round2d/round2f 诊断事件循环/线程池
  调度延迟的 marker; mw_inner_start 由最内层 middleware 写入 request.state。

契约: 仅日志输出, 不改任何 API 行为。分段日志正文 (write_request_timing /
slow_write_request) 由 app.core.timing_log.emit_write_timing 产出, 本模块只负责
打点与慢调度 warning。
"""
import logging
import time
from fastapi import Request

logger = logging.getLogger("app.core.timing")

# round2d/round2f 慢调度阈值(ms)。
# dispatch / mw_to_dep = middleware→auth dep 调度延迟; auth_internal = auth 函数体
# 内部耗时(DB/缓存)。超阈值走 warning 突显, 供生产 journalctl 抓调度瓶颈。
_DISPATCH_SLOW_MS = 200.0
_AUTH_INTERNAL_SLOW_MS = 100.0


def warn_dispatch_slow(request: Request, t_enter: float) -> None:
    """round2f: 测量 middleware→线程池 dispatch 延迟, >=200ms 走 warning。

    t_enter = auth dep 函数体入口 perf_counter 时刻; mw_inner_start 由最内层
    middleware 写入 request.state。两者差即 dispatch 调度延迟。
    """
    _mw_start = getattr(request.state, "mw_inner_start", None)
    if _mw_start is not None:
        _dispatch_ms = (t_enter - _mw_start) * 1000
        if _dispatch_ms >= _DISPATCH_SLOW_MS:
            logger.warning(
                "dispatch_slow path=%s ms=%.2f",
                request.url.path, _dispatch_ms,
            )


def warn_auth_internal_slow(path_label: str, t_enter: float) -> None:
    """round2d: auth 函数体内部计时, >=100ms 走 warning。

    path_label 为分支标识(cache_hit/cache_miss/token), 非请求路径。
    auth_internal_ms >= 100 → 函数内慢(DB/缓存);
    auth_internal_ms << auth_ms(外部marker) → 调度延迟(线程池排队/loop忙)。
    """
    _auth_internal_ms = (time.perf_counter() - t_enter) * 1000
    if _auth_internal_ms >= _AUTH_INTERNAL_SLOW_MS:
        logger.warning("auth_internal_slow path=%s ms=%.2f", path_label, _auth_internal_ms)


async def timing_start_dep(request: Request) -> None:
    """auth 前 marker: 记请求起点 + 测 mw_inner_start→首个 dep 的调度延迟。"""
    request.state.timing_start = time.perf_counter()
    # round2f: 测量 innermost middleware → 首个 dep 的调度延迟
    _mw_start = getattr(request.state, "mw_inner_start", None)
    if _mw_start is not None:
        _mw_to_dep_ms = (request.state.timing_start - _mw_start) * 1000
        if _mw_to_dep_ms >= _DISPATCH_SLOW_MS:
            logger.warning(
                "mw_to_dep_slow path=%s ms=%.2f",
                request.url.path, _mw_to_dep_ms,
            )


async def timing_end_auth_dep(request: Request) -> None:
    """auth 后 marker: 记 auth 结束点, 供端点计算 auth_ms / parse_ms。"""
    request.state.timing_auth_end = time.perf_counter()
