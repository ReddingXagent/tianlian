"""
缓存统计 API 测试

覆盖: GET /api/v1/cache/stats (卡 c3763bf5)
- Redis 真实路径: enabled + client 时走 client.info(), backend=='redis', hit_rate 数学正确
- 降级诚实路径: backend=='memory', hit_rate=None, 不再伪造 87.5/128/2.4
- 字段结构与类型
- 非 platform admin 被拒 (403)
"""
import pytest


class _FakeRedisClient:
    """假 Redis client, 只实现 info()"""

    def __init__(self, info_dict):
        self._info = info_dict

    def info(self):
        return self._info


def _force_redis(monkeypatch, info_dict):
    from app.core import cache as cache_module
    monkeypatch.setattr(cache_module.cache, "enabled", True)
    monkeypatch.setattr(cache_module.cache, "client", _FakeRedisClient(info_dict))


def _force_memory(monkeypatch):
    from app.core import cache as cache_module
    monkeypatch.setattr(cache_module.cache, "enabled", False)
    monkeypatch.setattr(cache_module.cache, "client", None)


# ─── Redis 真实路径 ───

def test_cache_stats_redis_backend_and_hit_rate_math(client, monkeypatch):
    """enabled+client 时走 client.info(), hit_rate=hits/(hits+misses)*100"""
    _force_redis(monkeypatch, {
        "keyspace_hits": 75,
        "keyspace_misses": 25,
        "used_memory": 5 * 1024 * 1024,
        "keyspace": {"db0": {"keys": 3}, "db1": {"keys": 4}},
    })
    resp = client.get("/api/v1/cache/stats")
    assert resp.status_code == 200
    stats = resp.json()["data"]
    assert stats["backend"] == "redis"
    assert stats["hit_rate"] == pytest.approx(75.0)
    assert stats["total_keys"] == 7
    assert stats["used_memory_mb"] == pytest.approx(5.0)


def test_cache_stats_redis_zero_misses(client, monkeypatch):
    """零 miss 时 hit_rate=100, 不除零"""
    _force_redis(monkeypatch, {
        "keyspace_hits": 10,
        "keyspace_misses": 0,
        "used_memory": 1024,
        "keyspace": {"db0": {"keys": 1}},
    })
    stats = client.get("/api/v1/cache/stats").json()["data"]
    assert stats["backend"] == "redis"
    assert stats["hit_rate"] == pytest.approx(100.0)


def test_cache_stats_redis_info_error_falls_back_to_memory(client, monkeypatch):
    """client.info() 抛异常 → 诚实降级 memory, 不伪造"""
    class _Boom:
        def info(self):
            raise RuntimeError("redis down")

    from app.core import cache as cache_module
    monkeypatch.setattr(cache_module.cache, "enabled", True)
    monkeypatch.setattr(cache_module.cache, "client", _Boom())
    stats = client.get("/api/v1/cache/stats").json()["data"]
    assert stats["backend"] == "memory"


# ─── 降级诚实路径 ───

def test_cache_stats_memory_backend_honest(client, monkeypatch):
    """enabled=False → backend=='memory', hit_rate=None, 无 87.5/128/2.4 伪造值"""
    _force_memory(monkeypatch)
    resp = client.get("/api/v1/cache/stats")
    assert resp.status_code == 200
    stats = resp.json()["data"]
    assert stats["backend"] == "memory"
    assert stats["hit_rate"] is None
    # 旧伪造契约不得复活
    assert stats != {"hit_rate": 87.5, "total_keys": 128, "used_memory_mb": 2.4, "backend": "mock"}
    assert stats["total_keys"] != 128 or stats["backend"] != "mock"


def test_cache_stats_memory_total_keys_counts_memory_cache(client, monkeypatch):
    """memory 路径 total_keys = len(_MEMORY_CACHE) (锁内取)"""
    from app.core import cache as cache_module
    _force_memory(monkeypatch)
    with cache_module._MEMORY_CACHE_LOCK:
        cache_module._MEMORY_CACHE.clear()
        cache_module._MEMORY_CACHE["k1"] = (9999999999.0, "v")
        cache_module._MEMORY_CACHE["k2"] = (9999999999.0, "v")
    try:
        stats = client.get("/api/v1/cache/stats").json()["data"]
        assert stats["backend"] == "memory"
        assert stats["total_keys"] == 2
    finally:
        with cache_module._MEMORY_CACHE_LOCK:
            cache_module._MEMORY_CACHE.clear()


# ─── 结构 / 权限 ───

def test_cache_stats_returns_200(client, monkeypatch):
    """端点可访问，返回统一响应格式"""
    _force_memory(monkeypatch)
    resp = client.get("/api/v1/cache/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert "data" in body


def test_cache_stats_fields_present(client, monkeypatch):
    """统计字段齐全"""
    _force_memory(monkeypatch)
    stats = client.get("/api/v1/cache/stats").json()["data"]
    for key in ("hit_rate", "total_keys", "used_memory_mb", "backend"):
        assert key in stats, f"缺少字段 {key}"
    assert isinstance(stats["total_keys"], int)


def test_cache_stats_forbidden_for_non_admin(client, monkeypatch, seed_users):
    """viewer 非 platform admin → 403"""
    _force_memory(monkeypatch)
    from tests.conftest import _get_token
    token = _get_token(client, "viewer1", "view123")
    client.headers["Authorization"] = f"Bearer {token}"
    try:
        resp = client.get("/api/v1/cache/stats")
        assert resp.status_code == 403
    finally:
        client.headers.pop("Authorization", None)


def test_cache_stats_unauthenticated_rejected(anon_client):
    """匿名 → 401"""
    resp = anon_client.get("/api/v1/cache/stats")
    assert resp.status_code == 401
