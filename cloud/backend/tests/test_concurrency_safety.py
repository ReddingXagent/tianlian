"""test_concurrency_safety.py — 单例双重检查锁并发安全测试

被测目标:
- app/services/vpp/auto_scheduler.py::get_vpp_auto_scheduler

验证手段:
- threading.Barrier 让 N 个线程同时闯入 getter,最大化 check-then-set 竞态窗口
- 慢构造 (time.sleep) 进一步放大窗口,确保无锁时多线程各自创建实例
- 断言"构造次数 == 1" + "所有线程拿到同一实例"

不连真 DB / 不依赖 TDengine: patch 整个类名为计数 fake,完全隔离。
"""
import threading
import time
from unittest.mock import patch

from app.services.vpp import auto_scheduler as auto_mod


# ─── get_vpp_auto_scheduler 并发安全 ───

def test_get_vpp_auto_scheduler_concurrent_singleton():
    """多线程同时调用 get_vpp_auto_scheduler,双重检查锁保证只构造一次。

    RED 复现路径(无锁):barrier 释放后 N 线程都读到 _auto_scheduler is None,
    各自进入 VPPAutoScheduler() 构造 → 构造计数 == N。
    """
    auto_mod._auto_scheduler = None

    state = {"count": 0}
    state_lock = threading.Lock()

    class SlowScheduler:
        """慢构造 fake,扩大竞态窗口;每次构造计数 +1"""
        def __init__(self):
            time.sleep(0.05)
            with state_lock:
                state["count"] += 1

    n_threads = 10
    barrier = threading.Barrier(n_threads)
    results = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()  # 全部线程就绪后同时放行
        inst = auto_mod.get_vpp_auto_scheduler()
        with results_lock:
            results.append(inst)

    try:
        with patch.object(auto_mod, "VPPAutoScheduler", SlowScheduler):
            threads = [threading.Thread(target=worker) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            assert all(not t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    finally:
        auto_mod._auto_scheduler = None  # 清理,避免污染其他用例

    assert state["count"] == 1, (
        f"单例竞态未修复:期望只构造 1 次,实际构造 {state['count']} 次"
    )
    assert len(results) == n_threads
    assert all(r is results[0] for r in results), "并发返回了不同实例"
