"""
app/core/station_router.py 覆盖率补充测试（卡片 4829f2bb）

StationRouter 是纯内存/Redis 路由逻辑，不依赖 HTTP/DB。本文件用内存版
FakeRedis 模拟多Pod Redis 操作，覆盖以下此前未覆盖的分支：
- register / unregister（单Pod本地字典 + 多Pod Redis 三键写入/删除 + 异常降级）
- list_by_pod / list_by_region（单Pod本地筛选 + 多Pod Set 查询 + 异常降级）
- register_pod / get_pod_info / list_all_pods（单Pod + 多Pod registry + 异常降级）
- get_station_router / init_station_router（环境变量配置 + cache 注入 + 异常吞咽 + 单例缓存）
"""
import fnmatch
import json

import pytest

from app.core import station_router as sr_module
from app.core.station_router import (
    KEY_POD_REGISTRY,
    KEY_POD_STATIONS,
    KEY_REGION_STATIONS,
    KEY_STATION_ROUTE,
    REDIS_PREFIX,
    StationRouter,
    get_station_router,
    init_station_router,
)


# ---------- 内存版 Redis（仅实现 station_router 用到的子集）----------


class FakeRedis:
    """内存版 Redis：字符串 set/get/delete + 集合 sadd/srem/smembers/keys。"""

    def __init__(self):
        self._kv: dict[str, str] = {}
        self._sets: dict[str, set] = {}

    def get(self, key):
        return self._kv.get(key)

    def set(self, key, value, ex=None):
        # 卡片 b9b1c588: 路由键写入带 TTL; 替身只存值, ex 仅记录语义不做真过期
        self._kv[key] = value
        self._ttl = ex
        return True

    def expire(self, key, ttl):
        # 模拟真实 Redis: 不存在的键返回 False
        return key in self._kv or key in self._sets

    def delete(self, key):
        existed = key in self._kv
        self._kv.pop(key, None)
        return 1 if existed else 0

    def sadd(self, key, *values):
        s = self._sets.setdefault(key, set())
        added = 0
        for v in values:
            if v not in s:
                s.add(v)
                added += 1
        return added

    def srem(self, key, *values):
        s = self._sets.get(key, set())
        removed = 0
        for v in values:
            if v in s:
                s.discard(v)
                removed += 1
        return removed

    def smembers(self, key):
        return set(self._sets.get(key, set()))

    def keys(self, pattern):
        all_keys = list(self._kv.keys()) + list(self._sets.keys())
        return [k for k in all_keys if fnmatch.fnmatchcase(k, pattern)]

    def scan_iter(self, pattern):
        # 卡片 b9b1c588: list_all_pods 改用 scan_iter, 替身同 fnmatch 语义
        return iter(self.keys(pattern))


class BrokenRedis:
    """所有操作均抛异常，用于覆盖异常降级分支。"""

    @staticmethod
    def _boom(*args, **kwargs):
        raise RuntimeError("redis down")

    get = _boom
    set = _boom
    delete = _boom
    sadd = _boom
    srem = _boom
    smembers = _boom
    keys = _boom


class _BrokenCache:
    """cache.enabled 访问即抛异常，用于覆盖 get_station_router 的 except 吞咽分支。"""

    @property
    def enabled(self):
        raise RuntimeError("cache broken")


# ---------- fixtures ----------


@pytest.fixture(autouse=True)
def _reset_router_singleton():
    """每个测试前后清理全局单例，避免 get/init_station_router 跨测试污染。"""
    sr_module._router_instance = None
    yield
    sr_module._router_instance = None


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def local_router():
    """单Pod模式路由器。"""
    return StationRouter(
        local_only=True, pod_id="pod-01", region_id="north", endpoint="http://h1:8000"
    )


@pytest.fixture
def multi_router(fake_redis):
    """多Pod模式路由器（绑定 FakeRedis）。"""
    return StationRouter(
        local_only=False,
        redis_client=fake_redis,
        pod_id="pod-01",
        region_id="north",
        endpoint="http://h1:8000",
    )


def _route_key(station_id):
    return f"{REDIS_PREFIX}station:route:{station_id}"


def _pod_set_key(pod_id):
    return f"{REDIS_PREFIX}pod:{pod_id}:stations"


def _region_set_key(region_id):
    return f"{REDIS_PREFIX}region:{region_id}:stations"


def _pod_registry_key(pod_id):
    return f"{REDIS_PREFIX}pod:registry:{pod_id}"


# ---------- 初始化 / 基础工具 ----------


class TestStationRouterInit:
    def test_local_only_keeps_config(self, local_router):
        assert local_router.local_only is True
        assert local_router.pod_id == "pod-01"
        assert local_router.region_id == "north"
        assert local_router.endpoint == "http://h1:8000"

    def test_multi_without_redis_degrades_to_local(self):
        # 多Pod模式但未提供 redis → 降级为单Pod
        r = StationRouter(local_only=False, redis_client=None)
        assert r.local_only is True
        assert r.redis is None

    def test_multi_with_redis_stays_multi(self, fake_redis):
        r = StationRouter(local_only=False, redis_client=fake_redis)
        assert r.local_only is False
        assert r.redis is fake_redis

    def test_get_redis_key_format(self, local_router):
        key = local_router._get_redis_key(KEY_STATION_ROUTE, station_id=42)
        assert key == f"{REDIS_PREFIX}station:route:42"

    def test_default_route_reflects_config(self, local_router):
        assert local_router._default_route() == {
            "pod_id": "pod-01",
            "region_id": "north",
            "endpoint": "http://h1:8000",
        }


# ---------- 单Pod模式：路由查询 / 注册 / 移除 / 列表 ----------


class TestRouteLocal:
    def test_route_station_returns_default(self, local_router):
        route = local_router.route_station(100)
        assert route["pod_id"] == "pod-01"
        assert route["region_id"] == "north"
        assert route["endpoint"] == "http://h1:8000"

    def test_route_device_with_station_id_uses_route_station(self, local_router):
        route = local_router.route_device(1, station_id=100)
        assert route == local_router._default_route()

    def test_route_device_without_station_id_returns_local(self, local_router):
        route = local_router.route_device(1)
        assert route == local_router._default_route()


class TestRegisterLocal:
    def test_register_stores_in_local_dict(self, local_router):
        ok = local_router.register(100, "pod-02", "south", endpoint="http://h2:8000")
        assert ok is True
        stored = local_router._local_routes[100]
        assert stored["pod_id"] == "pod-02"
        assert stored["region_id"] == "south"
        assert stored["endpoint"] == "http://h2:8000"
        assert "updated_at" in stored

    def test_register_default_endpoint(self, local_router):
        # endpoint=None → 默认 http://{pod_id}:8000
        local_router.register(101, "pod-03", "east")
        assert local_router._local_routes[101]["endpoint"] == "http://pod-03:8000"

    def test_unregister_existing(self, local_router):
        local_router.register(100, "pod-02", "south")
        assert 100 in local_router._local_routes
        assert local_router.unregister(100) is True
        assert 100 not in local_router._local_routes

    def test_unregister_missing_is_idempotent(self, local_router):
        # 不存在的路由移除也返回 True（幂等）
        assert local_router.unregister(999) is True


class TestListLocal:
    def test_list_by_pod_match(self, local_router):
        local_router.register(1, "pod-01", "north")
        local_router.register(2, "pod-01", "north")
        assert set(local_router.list_by_pod("pod-01")) == {1, 2}

    def test_list_by_pod_no_match_returns_empty(self, local_router):
        # pod_id 不等于本 pod → []（覆盖 line 276）
        local_router.register(1, "pod-01", "north")
        assert local_router.list_by_pod("pod-99") == []

    def test_list_by_region_match(self, local_router):
        local_router.register(1, "pod-01", "north")
        assert local_router.list_by_region("north") == [1]

    def test_list_by_region_no_match_returns_empty(self, local_router):
        # region_id 不等于本 region → []（覆盖 line 301）
        local_router.register(1, "pod-01", "north")
        assert local_router.list_by_region("south") == []


class TestRegisterPodLocal:
    def test_register_pod_local_returns_false(self, local_router):
        # 单Pod模式不支持 Pod 注册
        assert local_router.register_pod("pod-02", "south", "http://h2:8000") is False

    def test_get_pod_info_self_returns_local(self, local_router):
        assert local_router.get_pod_info("pod-01") == local_router._local_pod_info

    def test_get_pod_info_other_returns_none(self, local_router):
        assert local_router.get_pod_info("pod-99") is None

    def test_list_all_pods_local(self, local_router):
        assert local_router.list_all_pods() == [local_router._local_pod_info]


# ---------- 多Pod模式：Redis 读写 + 异常降级 ----------


class TestRouteMulti:
    def test_route_station_redis_hit(self, multi_router):
        multi_router.register(100, "pod-02", "south", endpoint="http://h2:8000")
        route = multi_router.route_station(100)
        assert route["pod_id"] == "pod-02"
        assert route["region_id"] == "south"
        assert route["endpoint"] == "http://h2:8000"

    def test_route_station_redis_miss_returns_default(self, multi_router):
        # 未注册 → 兜底默认路由
        assert multi_router.route_station(404) == multi_router._default_route()

    def test_route_station_redis_error_degrades(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        # get 抛异常 → 降级默认
        assert r.route_station(1) == r._default_route()


class TestRegisterMulti:
    def test_register_writes_three_redis_keys(self, multi_router, fake_redis):
        ok = multi_router.register(100, "pod-02", "south", endpoint="http://h2:8000")
        assert ok is True

        # 1. 场站路由
        stored = json.loads(fake_redis._kv[_route_key(100)])
        assert stored["pod_id"] == "pod-02"
        assert stored["region_id"] == "south"
        assert stored["endpoint"] == "http://h2:8000"
        assert "updated_at" in stored

        # 2. Pod 场站集合
        assert fake_redis._sets[_pod_set_key("pod-02")] == {"100"}
        # 3. 区域场站集合
        assert fake_redis._sets[_region_set_key("south")] == {"100"}

    def test_register_default_endpoint(self, multi_router, fake_redis):
        multi_router.register(101, "pod-03", "east")
        assert json.loads(fake_redis._kv[_route_key(101)])["endpoint"] == "http://pod-03:8000"

    def test_register_redis_error_returns_false(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        assert r.register(1, "pod-02", "south") is False


class TestUnregisterMulti:
    def test_unregister_removes_route_and_set_members(self, multi_router, fake_redis):
        multi_router.register(100, "pod-02", "south")
        assert multi_router.unregister(100) is True

        assert _route_key(100) not in fake_redis._kv
        assert "100" not in fake_redis._sets.get(_pod_set_key("pod-02"), set())
        assert "100" not in fake_redis._sets.get(_region_set_key("south"), set())

    def test_unregister_redis_error_returns_false(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        # route_station 内部 try 吞掉 get 异常返回默认路由，delete 抛异常 → False
        assert r.unregister(1) is False


class TestListMulti:
    def test_list_by_pod_redis(self, multi_router):
        multi_router.register(1, "pod-02", "south")
        multi_router.register(2, "pod-02", "south")
        multi_router.register(3, "pod-03", "south")
        assert set(multi_router.list_by_pod("pod-02")) == {1, 2}

    def test_list_by_region_redis(self, multi_router):
        multi_router.register(1, "pod-02", "south")
        multi_router.register(2, "pod-02", "north")
        assert set(multi_router.list_by_region("south")) == {1}

    def test_list_by_pod_redis_error_returns_empty(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        assert r.list_by_pod("pod-02") == []

    def test_list_by_region_redis_error_returns_empty(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        assert r.list_by_region("south") == []


class TestRegisterPodMulti:
    def test_register_pod_writes_registry(self, multi_router, fake_redis):
        ok = multi_router.register_pod(
            "pod-02", "south", "http://h2:8000", version="3.1.0", metadata={"az": "a"}
        )
        assert ok is True
        info = json.loads(fake_redis._kv[_pod_registry_key("pod-02")])
        assert info["pod_id"] == "pod-02"
        assert info["region_id"] == "south"
        assert info["endpoint"] == "http://h2:8000"
        assert info["version"] == "3.1.0"
        assert info["metadata"] == {"az": "a"}
        assert "registered_at" in info

    def test_register_pod_redis_error_returns_false(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        assert r.register_pod("pod-02", "south", "http://h2:8000") is False


class TestGetPodInfoMulti:
    def test_get_pod_info_hit(self, multi_router):
        multi_router.register_pod("pod-02", "south", "http://h2:8000")
        info = multi_router.get_pod_info("pod-02")
        assert info is not None
        assert info["pod_id"] == "pod-02"
        assert info["endpoint"] == "http://h2:8000"

    def test_get_pod_info_miss_returns_none(self, multi_router):
        assert multi_router.get_pod_info("pod-99") is None

    def test_get_pod_info_redis_error_returns_none(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        assert r.get_pod_info("pod-02") is None


class TestListAllPodsMulti:
    def test_list_all_pods_scans_registry(self, multi_router):
        multi_router.register_pod("pod-02", "south", "http://h2:8000")
        multi_router.register_pod("pod-03", "north", "http://h3:8000")
        pods = multi_router.list_all_pods()
        assert sorted(p["pod_id"] for p in pods) == ["pod-02", "pod-03"]

    def test_list_all_pods_empty_when_no_registry(self, multi_router):
        assert multi_router.list_all_pods() == []

    def test_list_all_pods_redis_error_returns_local(self):
        r = StationRouter(local_only=False, redis_client=BrokenRedis())
        # keys 抛异常 → 兜底返回本地 pod 信息
        assert r.list_all_pods() == [r._local_pod_info]


# ---------- 全局单例：get_station_router / init_station_router ----------


class TestGlobalRouter:
    def test_get_station_router_default_local(self, monkeypatch):
        monkeypatch.setenv("POD_LOCAL_ONLY", "true")
        monkeypatch.setenv("POD_ID", "pod-01")
        monkeypatch.setenv("REGION_ID", "default")
        monkeypatch.setenv("POD_ENDPOINT", "http://localhost:8000")
        r = get_station_router()
        assert r.local_only is True
        assert r.pod_id == "pod-01"
        # 单例已缓存，再次调用返回同一实例
        assert sr_module._router_instance is r
        assert get_station_router() is r

    def test_get_station_router_multi_cache_disabled_degrades(self, monkeypatch):
        # 多Pod但 cache 未启用 → redis_client=None → 降级本地
        monkeypatch.setenv("POD_LOCAL_ONLY", "false")
        from app.core.cache import cache

        monkeypatch.setattr(cache, "enabled", False)
        r = get_station_router()
        assert r.local_only is True
        assert r.redis is None

    def test_get_station_router_multi_injects_cache_client(self, monkeypatch, fake_redis):
        monkeypatch.setenv("POD_LOCAL_ONLY", "false")
        from app.core.cache import cache

        monkeypatch.setattr(cache, "enabled", True)
        monkeypatch.setattr(cache, "client", fake_redis)
        r = get_station_router()
        assert r.local_only is False
        assert r.redis is fake_redis

    def test_get_station_router_cache_exception_swallowed(self, monkeypatch):
        # cache.enabled 访问抛异常 → except 吞咽，redis_client 保持 None → 降级
        monkeypatch.setenv("POD_LOCAL_ONLY", "false")
        from unittest.mock import patch

        with patch("app.core.cache.cache", _BrokenCache()):
            r = get_station_router()
        assert r.local_only is True
        assert r.redis is None

    def test_init_station_router_sets_global_singleton(self, fake_redis):
        r = init_station_router(
            local_only=False,
            redis_client=fake_redis,
            pod_id="pod-xx",
            region_id="r",
            endpoint="http://x:8000",
        )
        assert r.local_only is False
        assert r.redis is fake_redis
        assert r.pod_id == "pod-xx"
        # 全局单例已设置，get_station_router 复用同一实例
        assert sr_module._router_instance is r
        assert get_station_router() is r
