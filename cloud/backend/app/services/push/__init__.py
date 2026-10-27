"""App push provider 抽象 (契约§8.4 P1).

卡 7f601f7f: JIGUANG 凭证齐备且启用时默认实现切换为 JPushProvider,
否则保持 LogPushProvider (no-op 降级)。调用方经 get_push_provider()
取用 (注入缝 set_push_provider 优先), 不硬绑具体厂商。
"""

from threading import Lock

from app.core.config import settings
from app.services.push.base import PushProvider
from app.services.push.log_provider import LogPushProvider

_provider = None
# 双检锁保护惰性初始化 (卡 5436785c): 多线程并发首调时避免重复构造 provider
# (同 wx_pay client 卡 692b3df7 模式: check None → lock → re-check None → init)。
_provider_lock = Lock()


def create_provider() -> PushProvider:
    """按配置构造默认 provider: JIGUANG 配置齐 → JPush, 否则 Log。"""
    if (
        getattr(settings, "JIGUANG_ENABLED", False)
        and getattr(settings, "JIGUANG_APP_KEY", None)
        and getattr(settings, "JIGUANG_MASTER_SECRET", None)
    ):
        from app.services.push.jpush_provider import JPushProvider

        return JPushProvider()
    return LogPushProvider()


def get_push_provider() -> PushProvider:
    """惰性初始化默认 provider (首次调用按配置决定), set_push_provider 可覆盖。

    线程安全: 双检锁保证并发首调只构造一次 (构造 + 赋值非原子, 无锁竞态下
    可能多次构造仅留最后一个); set_push_provider 覆盖语义不变 (直接写全局)。
    """
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:  # re-check: 持锁期间可能已被另一线程初始化
                _provider = create_provider()
    return _provider


def set_push_provider(provider: PushProvider) -> None:
    global _provider
    _provider = provider


# 惰性 re-export (包级 JPushProvider 可导入; 避免无谓引入 httpx 依赖链)
def __getattr__(name):
    if name == "JPushProvider":
        from app.services.push.jpush_provider import JPushProvider

        return JPushProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PushProvider",
    "LogPushProvider",
    "JPushProvider",
    "create_provider",
    "get_push_provider",
    "set_push_provider",
]
