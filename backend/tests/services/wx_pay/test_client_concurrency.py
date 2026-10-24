"""get_wxpay_client 并发初始化测试 (工作卡 692b3df7)

验证双检锁: 多线程并发调用 get_wxpay_client 时只创建一个单例实例, 无竞态重复初始化。
参考 AIModelManager 模式: check → lock → re-check → init。
"""
import threading

from app.services.wx_pay import get_wxpay_client, reset_wxpay_client_for_testing
from app.services.wx_pay import mock_client as wxpay_mock_module


def test_concurrent_calls_return_same_instance():
    """10 线程并发 get_wxpay_client → 同一实例 (id 相同)。"""
    reset_wxpay_client_for_testing(None)
    try:
        results = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()  # 同时放行, 制造竞态
            results.append(get_wxpay_client())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        first_id = id(results[0])
        assert all(id(r) == first_id for r in results), \
            "并发调用应返回同一单例实例"
    finally:
        reset_wxpay_client_for_testing(None)


def test_singleton_initializes_only_once():
    """并发初始化时 MockWxPayClient.__init__ 只被调用一次。"""
    reset_wxpay_client_for_testing(None)
    init_count = {"n": 0}
    lock = threading.Lock()

    # patch 计数 __new__ (dataclass 无自定义 __init__, 计 __new__ 即创建计数)
    original_new = wxpay_mock_module.MockWxPayClient.__new__

    def counting_new(cls, *args, **kwargs):
        with lock:
            init_count["n"] += 1
        return original_new(cls)

    wxpay_mock_module.MockWxPayClient.__new__ = staticmethod(counting_new)
    try:
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            get_wxpay_client()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert init_count["n"] == 1, \
            f"双检锁下应只创建一次, 实际创建 {init_count['n']} 次"
    finally:
        wxpay_mock_module.MockWxPayClient.__new__ = original_new
        reset_wxpay_client_for_testing(None)


def test_reset_then_reinit_yields_new_instance():
    """重置全局实例后重新调用 → 新实例 (id 与上次不同), 验证重置生效。"""
    reset_wxpay_client_for_testing(None)
    c1 = get_wxpay_client()
    id1 = id(c1)

    reset_wxpay_client_for_testing(None)
    c2 = get_wxpay_client()
    id2 = id(c2)

    assert id1 != id2, "重置后应重建出新实例"
    # 再次重置并发验证
    reset_wxpay_client_for_testing(None)

    results = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(get_wxpay_client())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(id(r) == id(results[0]) for r in results)
    reset_wxpay_client_for_testing(None)
