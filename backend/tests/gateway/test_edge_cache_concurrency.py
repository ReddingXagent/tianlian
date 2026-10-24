"""
get_edge_cache() TOCTOU 竞态测试。

背景:
    模块级全局 _cache_instances: Dict[str, EdgeCache] = {}
    get_edge_cache() 原实现为 check-then-act (无锁):
        if name not in _cache_instances:           # check
            _cache_instances[name] = EdgeCache(...)  # act (构造发生在 check 与 assign 之间)
        return _cache_instances[name]

    多线程并发调用同名 get_edge_cache 时, 各线程可同时通过 `not in` 检查,
    各自构造实例 → 重复实例 (TOCTOU 竞态)。

本测试通过放慢 EdgeCache.__init__ 放大 check 与 act 之间的窗口,
使竞态在无锁实现下确定性复现 (构造计数 == 线程数);
双重检查锁修复后, 构造计数必须 == 1。

详见记忆: cpython-gil-check-then-act-race-window-amplification
"""
import threading
import time

import pytest

from app.gateway import edge_cache as ec_module
from app.gateway.edge_cache import get_edge_cache, reset_edge_caches


def test_get_edge_cache_concurrent_creates_single_instance(monkeypatch):
    """多线程经 Barrier 同时起跑调用 get_edge_cache(同名), 应只构造一个实例。"""
    reset_edge_caches()

    # 放慢构造函数, 放大 `if name not in` 与赋值之间的竞态窗口
    construction_count = 0
    count_lock = threading.Lock()
    real_init = ec_module.EdgeCache.__init__

    def slow_init(self, *args, **kwargs):
        nonlocal construction_count
        with count_lock:
            construction_count += 1
        time.sleep(0.05)  # 让其它线程在此期间都通过 `not in` 检查
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(ec_module.EdgeCache, "__init__", slow_init)

    num_threads = 8
    barrier = threading.Barrier(num_threads)  # 所有线程同时起跑
    results: list = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()
        cache = get_edge_cache("race-name", ttl_seconds=10, max_entries=10)
        with results_lock:
            results.append(cache)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 1. 所有线程拿到的必须是同一个实例
    assert len(results) == num_threads
    first = results[0]
    assert all(cache is first for cache in results), "并发调用返回了不同实例"

    # 2. 全局只应构造一次 (双重检查锁保证) —— 无锁实现此处 == num_threads
    assert construction_count == 1, (
        f"TOCTOU 竞态: 构造了 {construction_count} 次, 期望 1 次"
    )


def test_get_edge_cache_concurrent_different_names_isolated(monkeypatch):
    """不同名并发不应互相影响: 每个名字各构造一次, 同名仍是单例。"""
    reset_edge_caches()

    real_init = ec_module.EdgeCache.__init__

    def slow_init(self, *args, **kwargs):
        time.sleep(0.02)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(ec_module.EdgeCache, "__init__", slow_init)

    names = [f"cache-{i}" for i in range(4)]
    per_thread = 3  # 每个名字 3 个线程并发抢
    barrier = threading.Barrier(len(names) * per_thread)
    results: list = []
    results_lock = threading.Lock()

    def worker(name):
        barrier.wait()
        cache = get_edge_cache(name)
        with results_lock:
            results.append((name, cache))

    threads = [
        threading.Thread(target=worker, args=(name,))
        for name in names
        for _ in range(per_thread)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 每个名字的多个线程拿到同一个实例; 不同名字实例互不相同
    by_name: dict = {}
    for name, cache in results:
        by_name.setdefault(name, set()).add(id(cache))

    for name in names:
        assert len(by_name[name]) == 1, f"名字 {name} 出现了多个实例"

    distinct = {id(c) for _, c in results}
    assert len(distinct) == len(names), "不同名字应得到互不相同的实例"
