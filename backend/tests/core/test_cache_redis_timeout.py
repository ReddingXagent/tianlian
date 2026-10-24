"""test_cache_redis_timeout.py — app/core/cache.py Redis 客户端 socket_timeout 加固回归测试

被测目标: CacheService 构造期 redis.from_url 的 socket 超时配置 (卡551af8a9)

根因(修复前 cache.py:166):
  `redis.from_url(url, decode_responses=True)` 无 socket_timeout / socket_connect_timeout。
  redis-py 默认两者 = None (无超时, 已实测 connection_kwargs 确认) → 两条致命路径:
  1. 构造期 self.client.ping(): TCP 建连成功但 Redis 无响应(网络黑洞/停顿)下永久 hang。
     而 cache.py 末尾 `cache = CacheService()` 是模块级单例, import 即执行 →
     全应用启动卡死在模块初始化。
  2. 运行期 get/set/delete: 阻塞调用无超时永不抛异常 → except 降级路径形同虚设,
     Redis 停顿时所有命中缓存的 API 请求全链路无限 hang。

  socket_timeout 一旦配置 (本次=3s), 两条路径的超时才会真正抛 redis.exceptions.
  TimeoutError, 被 CacheService 既有的 try/except 捕获 → 降级到内存缓存。

验证三件事:
  1. (真 RED) from_url 透传 socket_timeout / socket_connect_timeout, 且在
     client.connection_pool.connection_kwargs 生效为正数秒 —— 防回归(改回 None 即失败)。
  2. 运行期 client.get/set 抛 TimeoutError → get 返回 None、set 返回 False 且不向
     调用方抛 (降级生效)。修复前 socket_timeout=None 时 get/set 永久阻塞永不抛,
     None/False 永不可达; mock 直接抛 TimeoutError 等价"超时已触发", 验证降级链条。
  3. 构造期 ping 抛 TimeoutError → 降级内存 (enabled=False, client=None), 构造立即返回
     不 hang。修复前 ping 在网络黑洞永久 hang; mock 直接抛等价"超时已触发", 验证降级链条
     + 与测试 1 的超时配置共同保证真实场景不 hang。

口径: 3s 与 health.py check_redis 的 socket_connect_timeout=3 及 MQTT 健康检查
  socket timeout=3 全项目统一。
"""
import redis
import pytest

from app.core import cache as cache_module
from app.core.cache import CacheService


@pytest.fixture(autouse=True)
def _restore_singleton():
    """CacheService.__init__ 会写类属性 `CacheService._instance = self`, 污染全局单例
    (影响模块级 `cache = CacheService()` 以及其它用例)。用例前后还原。"""
    saved = CacheService._instance
    yield
    CacheService._instance = saved


def _ok_redis_mock():
    """redis.from_url 的成功替身: 返回 ping 成功的可控 mock client。"""
    from unittest.mock import MagicMock
    client = MagicMock()
    client.ping.return_value = True
    return client


# ─── 1. (真 RED) 构造期 from_url 必须带 socket 超时 ───

def test_from_url_passes_socket_timeouts(monkeypatch):
    """修复前: redis.from_url 仅传 decode_responses → connection_kwargs 中
    socket_timeout / socket_connect_timeout 均为 None (无超时 → 网络黑洞永久 hang)。
    修复后: 必须透传并生效为正数秒。

    用 spy 调真实 from_url (而非 mock), 断言到 redis-py 真实 connection_kwargs,
    防止"传了参数但被吃掉"的假绿。本机/CI 有无 Redis 不影响 (ping 失败降级, kwargs 已捕获)。
    """
    captured = {}
    real_from_url = cache_module.redis.from_url

    def spy_from_url(url, **kwargs):
        client = real_from_url(url, **kwargs)
        captured["call_kwargs"] = dict(kwargs)
        captured["conn_kwargs"] = dict(client.connection_pool.connection_kwargs)
        return client

    monkeypatch.setattr(cache_module.redis, "from_url", spy_from_url)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    CacheService()  # 真实构造; ping 在无 Redis 时快速 ConnectionRefused 降级, 不影响断言

    call_kw = captured["call_kwargs"]
    conn_kw = captured["conn_kwargs"]

    # 调用层: from_url 被传了超时
    assert call_kw.get("socket_timeout") == 3, (
        f"from_url 未传 socket_timeout(={call_kw.get('socket_timeout')})")
    assert call_kw.get("socket_connect_timeout") == 3, (
        f"from_url 未传 socket_connect_timeout(={call_kw.get('socket_connect_timeout')})")
    # 生效层: redis-py 真实连接池接受了超时 (防"传了但没生效"的假绿)
    assert conn_kw.get("socket_timeout") == 3, (
        f"connection_kwargs.socket_timeout={conn_kw.get('socket_timeout')} "
        "未生效 → 运行期 get/set 无超时, Redis 停顿全链路 hang")
    assert conn_kw.get("socket_connect_timeout") == 3, (
        f"connection_kwargs.socket_connect_timeout={conn_kw.get('socket_connect_timeout')} "
        "未生效 → 启动/建连期 ping 无超时, 应用启动卡死")


# ─── 2. 运行期 get/set 超时降级到内存, 不向调用方抛 ───

def test_get_timeout_degrades_to_none(monkeypatch):
    """运行期 client.get 抛 redis.exceptions.TimeoutError → CacheService.get 降级返回 None。
    修复前 socket_timeout=None: get 永久阻塞永不抛 → None 永不可达 → 命中缓存的请求 hang。"""
    mock_client = _ok_redis_mock()
    mock_client.get.side_effect = redis.exceptions.TimeoutError("socket timeout")
    monkeypatch.setattr(cache_module.redis, "from_url", lambda *a, **k: mock_client)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    svc = CacheService()
    assert svc.enabled is True  # ping 成功, Redis 路径就绪

    cache_module.clear_memory_cache()  # 保证内存未命中, 强制走 Redis.get → 抛 TimeoutError
    assert svc.get("miss-key") is None  # 降级 None, 不抛


def test_set_timeout_degrades_to_false(monkeypatch):
    """运行期 client.setex 抛 redis.exceptions.TimeoutError → CacheService.set 返回 False。
    内存层在 client 调用前已写入 (_memory_set 先于 setex), 故降级后内存仍可读。"""
    mock_client = _ok_redis_mock()
    mock_client.setex.side_effect = redis.exceptions.TimeoutError("socket timeout")
    monkeypatch.setattr(cache_module.redis, "from_url", lambda *a, **k: mock_client)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    svc = CacheService()
    assert svc.enabled is True

    result = svc.set("k", "v", expire=30)
    assert result is False  # Redis 超时 → 降级 False, 不抛
    assert cache_module._memory_get("k") == "v"  # 内存层仍生效


# ─── 3. 构造期 ping 超时降级内存, enabled=False, 不 hang ───

def test_ping_timeout_degrades_to_memory(monkeypatch):
    """构造期 client.ping 抛 redis.exceptions.TimeoutError → 降级 (enabled=False,
    client=None), 构造立即返回不 hang。模块级 `cache = CacheService()` 在网络黑洞下
    因 socket_timeout 才会结束 (否则永久 hang 卡死整个应用启动)。降级后 get/set 走内存。"""
    mock_client = _ok_redis_mock()
    mock_client.ping.side_effect = redis.exceptions.TimeoutError("socket timeout")
    monkeypatch.setattr(cache_module.redis, "from_url", lambda *a, **k: mock_client)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    svc = CacheService()  # ping 超时 → except → 降级, 立即返回 (mock 等价"超时已触发")

    assert svc.enabled is False
    assert svc.client is None
    # 降级后不再触碰 Redis (client=None), 走内存
    svc.set("k", "v", expire=30)
    assert svc.get("k") == "v"
