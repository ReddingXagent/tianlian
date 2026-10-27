"""
卡片 b9b1c588 — [P2可靠性] Redis/队列编排四重缺口

覆盖:
1. compose worker 显式注入 CELERY_BROKER_URL / CELERY_RESULT_BACKEND / DB_POOL_SIZE
2. broker 独立 Redis 实例 (redis-broker) + noeviction, 与 cache redis 隔离
3. cache.delete_pattern / station_router.list_all_pods 用 scan_iter 替代 KEYS
4. station_router 四类键写入带 TTL, 提供 renew 心跳续租
"""
import json
import os
from unittest.mock import MagicMock

import pytest
import yaml

from app.core.station_router import StationRouter

COMPOSE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docker-compose.yml"
)


@pytest.fixture(scope="module")
def compose():
    with open(COMPOSE_PATH) as f:
        return yaml.safe_load(f)


# ─── 缺口1: worker 连不上 broker ───

class TestWorkerEnv:
    def test_worker_broker_env_explicit(self, compose):
        env = compose["services"]["worker"]["environment"]
        assert env["CELERY_BROKER_URL"] == "redis://redis-broker:6379/0", \
            "worker 必须显式注入 CELERY_BROKER_URL 指向独立 broker 实例"
        assert env["CELERY_RESULT_BACKEND"] == "redis://redis-broker:6379/1"

    def test_worker_db_pool_size(self, compose):
        env = compose["services"]["worker"]["environment"]
        assert env.get("DB_POOL_SIZE") == 20

    def test_worker_depends_on_broker(self, compose):
        deps = compose["services"]["worker"]["depends_on"]
        assert "redis-broker" in deps

    def test_worker_command_uses_core_celery_app(self, compose):
        cmd = compose["services"]["worker"]["command"]
        assert "app.core.celery_app" in cmd, \
            "app.tasks.celery_app 模块不存在, worker 会启动失败"


# ─── 缺口2: broker 独立实例 + noeviction ───

class TestBrokerIsolation:
    def test_broker_service_exists(self, compose):
        assert "redis-broker" in compose["services"]

    def test_broker_noeviction(self, compose):
        cmd = compose["services"]["redis-broker"]["command"]
        assert "noeviction" in cmd, "broker 禁止 LRU 逐出队列键"

    def test_backend_cache_url_differs_from_broker(self, compose):
        cache_url = compose["services"]["backend"]["environment"]["REDIS_URL"]
        broker_url = compose["services"]["worker"]["environment"]["CELERY_BROKER_URL"]
        # 不同实例主机名 → cache 与 broker 物理隔离
        cache_host = cache_url.split("//")[1].split("/")[0]
        broker_host = broker_url.split("//")[1].split("/")[0]
        assert cache_host != broker_host, \
            "cache 与 broker 不能共用同一 Redis 实例"


# ─── 缺口3: KEYS → scan_iter ───

class TestScanIter:
    def _make_cache_with_mock(self, monkeypatch):
        """构造 enabled=True 且 client 为 mock 的 CacheService 实例"""
        from app.core import cache as cache_mod
        svc = cache_mod.CacheService.__new__(cache_mod.CacheService)
        svc.enabled = True
        svc.client = MagicMock()
        return svc

    def test_delete_pattern_uses_scan_iter(self, monkeypatch):
        from app.core import cache as cache_mod
        cache_mod.clear_memory_cache()
        svc = self._make_cache_with_mock(monkeypatch)
        svc.client.scan_iter.return_value = iter(["tianlian:dev:1", "tianlian:dev:2"])
        svc.client.delete.return_value = 2

        n = svc.delete_pattern("dev:*")

        assert n == 2
        svc.client.scan_iter.assert_called_once_with("tianlian:dev:*")
        svc.client.keys.assert_not_called(), "delete_pattern 禁止使用阻塞的 KEYS"

    def test_delete_pattern_empty_returns_zero(self, monkeypatch):
        from app.core import cache as cache_mod
        cache_mod.clear_memory_cache()
        svc = self._make_cache_with_mock(monkeypatch)
        svc.client.scan_iter.return_value = iter([])
        assert svc.delete_pattern("none:*") == 0
        svc.client.delete.assert_not_called()

    def test_list_all_pods_uses_scan_iter(self):
        from app.core.station_router import StationRouter
        mock_redis = MagicMock()
        pods = [
            {"pod_id": "pod-01", "endpoint": "http://pod-01:8000"},
            {"pod_id": "pod-02", "endpoint": "http://pod-02:8000"},
        ]
        mock_redis.scan_iter.return_value = iter([
            "tianlian:route:pod:registry:pod-01",
            "tianlian:route:pod:registry:pod-02",
        ])
        mock_redis.get.side_effect = [json.dumps(p) for p in pods]

        router = StationRouter(local_only=False, redis_client=mock_redis)
        result = router.list_all_pods()

        assert [p["pod_id"] for p in result] == ["pod-01", "pod-02"]
        mock_redis.scan_iter.assert_called_once_with("tianlian:route:pod:registry:*")
        mock_redis.keys.assert_not_called(), "list_all_pods 禁止使用阻塞的 KEYS"


# ─── 缺口4: station_router 键 TTL + 心跳续租 ───

class _TTLTrackingRedis(MagicMock):
    """记录每个 key 的 expire 值, 并可对 get 返回已 set 的值"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.expire_calls = []
        self._store = {}
        self._sets = {}

    def set(self, key, value, ex=None):
        self._store[key] = value
        if ex is not None:
            self.expire_calls.append((key, ex))
        return True

    def sadd(self, key, member):
        self._sets.setdefault(key, set()).add(member)
        return 1

    def expire(self, key, ttl):
        # 模拟真实 Redis 语义: 不存在的键返回 False, 不会复活已过期键
        if key not in self._store and key not in self._sets:
            return False
        self.expire_calls.append((key, ttl))
        return True

    def get(self, key):
        return self._store.get(key)

    def ttl(self, key):
        for k, ex in reversed(self.expire_calls):
            if k == key:
                return ex
        return -2


class TestStationRouterTTL:
    def make_router(self):
        r = _TTLTrackingRedis()
        router = StationRouter.__new__(StationRouter)
        router.local_only = False
        router.redis = r
        router.pod_id = "pod-01"
        router.region_id = "default"
        router.endpoint = "http://localhost:8000"
        return router, r

    def test_register_sets_ttl_on_all_keys(self):
        from app.core.station_router import ROUTE_TTL
        router, r = self.make_router()
        assert router.register(42, "pod-01", "south") is True

        written = [k for k, _ in r.expire_calls]
        assert "tianlian:route:station:route:42" in written
        assert "tianlian:route:pod:pod-01:stations" in written
        assert "tianlian:route:region:south:stations" in written
        for _, ttl in r.expire_calls:
            assert ttl == ROUTE_TTL and ttl > 0

    def test_register_pod_sets_ttl(self):
        from app.core.station_router import ROUTE_TTL
        router, r = self.make_router()
        assert router.register_pod("pod-02", "south", "http://pod-02:8000") is True
        assert ("tianlian:route:pod:registry:pod-02", ROUTE_TTL) in r.expire_calls

    def test_renew_extends_ttl(self):
        from app.core.station_router import ROUTE_TTL
        router, r = self.make_router()
        router.register(42, "pod-01", "south")
        router.register_pod("pod-01", "south", "http://x")

        before = len(r.expire_calls)
        renewed = router.renew(station_id=42, pod_id="pod-01", region_id="south")

        assert renewed > 0
        assert len(r.expire_calls) > before
        # 续租后 key TTL 仍为正且等于 TTL 常量
        assert r.ttl("tianlian:route:station:route:42") == ROUTE_TTL
        assert r.ttl("tianlian:route:pod:registry:pod-01") == ROUTE_TTL

    def test_renew_unknown_keys_returns_zero(self):
        router, r = self.make_router()
        assert router.renew(station_id=999, pod_id="ghost", region_id="void") == 0
