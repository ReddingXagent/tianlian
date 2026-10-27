"""test_cache_concurrency.py — app/core/cache.py 内存缓存线程安全回归测试

被测目标: 模块级共享 dict _MEMORY_CACHE 的并发访问
  _memory_get / _memory_set / _memory_delete / _memory_delete_pattern / _evict_stale

根因(修复前无锁, FastAPI 同步端点在 threadpool 中并发执行):
  1. _memory_get 过期分支 `del _MEMORY_CACHE[key]` —— 多线程同时命中过期条目,
     第二个 del 抛 KeyError。应改 pop(key, None)。
  2. _evict_stale `[k for k,(exp,_) in _MEMORY_CACHE.items() if exp<now]` 迭代 items()
     期间, 并发 _memory_set 插入新 key 改变 dict size —— CPython 抛
     'RuntimeError: dictionary changed size during iteration' (>1000 条目高负载真实路径)。
  3. _memory_delete_pattern 列表推导迭代期间并发修改 —— 同样 RuntimeError。
  4. get/set/delete 之间 check-then-act 无原子性。

验证: N 线程 barrier 同时闯入 + 构造 >1000 条目触发 _evict_stale, 千次以上迭代
零异常、无死锁。修复前为概率性崩溃 (CPython GIL 下窗口存在), 修复后确定性安全。
"""
import threading
import time

import pytest

from app.core.cache import (
    _MEMORY_CACHE,
    _memory_delete,
    _memory_delete_pattern,
    _memory_get,
    _memory_set,
    clear_memory_cache,
)


@pytest.fixture(autouse=True)
def _isolate_memory_cache():
    """每个用例前后清空模块级共享缓存, 避免用例间互相污染。"""
    clear_memory_cache()
    yield
    clear_memory_cache()


# ─── get / set / delete 混战 ───

def test_concurrent_get_set_delete_no_exception():
    """多线程混战 get/set/delete: 修复前 check-then-act 竞态 + 过期 del 会抛异常。

    8 线程 × 2000 次迭代 = 16000+ 次并发操作 (满足"1000+ 次迭代"验收)。
    """
    errors = []
    n_threads = 8
    iterations = 2000
    barrier = threading.Barrier(n_threads)

    def worker(tid):
        try:
            barrier.wait()
            for i in range(iterations):
                key = f"k:{tid}:{i % 64}"
                _memory_set(key, i, ttl=60)
                _memory_get(key)
                if i % 7 == 0:
                    _memory_delete(key)
        except BaseException as e:  # noqa: BLE001 — 并发混战需捕获一切
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(not t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    assert not errors, f"并发 get/set/delete 抛异常: {[type(e).__name__ for e in errors[:5]]}"


# ─── _evict_stale 迭代期间并发 set ───

def test_evict_stale_concurrent_with_set_no_runtime_error():
    """构造 >1000 条目高频触发 _evict_stale, 与并发 _memory_set 竞争:
    迭代期间 dict size 变化不得抛 RuntimeError。

    RED 复现: _evict_stale 迭代 items() 时另一线程 set 插入新 key → CPython
    'dictionary changed size during iteration'。预填 1200 过期条目保证首次 set 即触发,
    之后 x:* 条目积累到 1000+ 持续触发 evict 高频迭代, 与 setter 线程必然交错。
    """
    now = time.time()
    for i in range(1200):
        _MEMORY_CACHE[f"seed:{i}"] = (now - 100, "stale")  # 直接置过期态

    errors = []
    n_threads = 8
    iterations = 3000
    barrier = threading.Barrier(n_threads)

    def setter(tid):
        try:
            barrier.wait()
            for i in range(iterations):
                _memory_set(f"x:{tid}:{i}", i, ttl=60)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=setter, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(not t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    assert not errors, (
        "evict 迭代期间并发 set 抛异常: "
        + ", ".join(f"{type(e).__name__}: {e}" for e in errors[:3])
    )


# ─── _memory_get 过期分支并发 del → KeyError ───

def test_memory_get_expired_concurrent_no_keyerror():
    """多线程同时读同一过期条目: _memory_get 过期删除必须 pop(key, None), 不得抛 KeyError。

    RED 复现: 过期 entry 被多线程并发命中, 无锁下多线程都执行 `del _MEMORY_CACHE[key]`,
    仅一个成功, 其余抛 KeyError。
    """
    errors = []
    n_threads = 16
    rounds = 100
    now = time.time()

    for r in range(rounds):
        key = f"exp:{r}"
        _MEMORY_CACHE[key] = (now - 1, "v")  # 直接置过期态

        barrier = threading.Barrier(n_threads)

        def getter(_key=key):
            try:
                _memory_get(_key)
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        def b_getter():
            barrier.wait()
            getter()

        threads = [threading.Thread(target=b_getter) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert not errors, f"并发读过期条目抛异常: {[type(e).__name__ for e in errors[:5]]}"


# ─── _memory_delete_pattern 迭代期间并发修改 ───

def test_delete_pattern_concurrent_no_exception():
    """_memory_delete_pattern 列表推导迭代整个 dict 期间, 并发 _memory_set 持续增长 size:
    不得抛 RuntimeError (dictionary changed size during iteration) / KeyError。

    RED 复现: _memory_delete_pattern 的 `[k for k in _MEMORY_CACHE if ...]` 迭代全部 key,
    迭代期间 setter 插入新唯一 key 改变 size → CPython RuntimeError。
    (关键: setter 必须用唯一新 key 才会真正增长 dict size —— 重复 set 同 key 只改值不增 size,
    不会触发迭代器 size 检查。总量控制在 <1000 避免触发 _evict_stale 干扰, 聚焦 delete_pattern。)
    """
    errors = []
    n_threads = 8
    set_iterations = 100  # 8 线程 × 100 = 800 新 key, 加预填 <1000, 不触发 _evict_stale

    # 预填少量 key, 让 delete_pattern 有内容可迭代
    for i in range(50):
        _MEMORY_CACHE[f"pad:{i}"] = (time.time() + 60, i)

    barrier = threading.Barrier(n_threads * 2)

    def pattern_deleter():
        try:
            barrier.wait()
            for _ in range(set_iterations * 10):  # 高频迭代整个 dict
                _memory_delete_pattern("nomatch")  # 不匹配 → 不删, 但仍遍历全 dict
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    def setter(tid):
        try:
            barrier.wait()
            for i in range(set_iterations):
                _memory_set(f"grow:{tid}:{i}", i, ttl=60)  # 唯一新 key, 持续增 size
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = (
        [threading.Thread(target=pattern_deleter) for _ in range(n_threads)]
        + [threading.Thread(target=setter, args=(t,)) for t in range(n_threads)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(not t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    assert not errors, f"delete_pattern 并发抛异常: {[type(e).__name__ for e in errors[:5]]}"
