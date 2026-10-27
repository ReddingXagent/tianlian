"""app/core/station_router.py 单例双检锁(DCL)并发回归测试 (卡片 96ad0847)

被测目标: 模块级懒加载单例 _router_instance 的 check-then-act 竞态
  - get_station_router(): 读侧懒初始化
  - init_station_router(): 写侧显式覆盖

根因(修复前无锁):
  get_station_router() 在 `_router_instance is None` 检查与赋值之间没有临界区。
  FastAPI 同步端点在 threadpool 中并发执行 (pod_routes.py 8 处 + cross_pod.py
  3 处都调 get_station_router()), 多个请求线程同时通过 None 检查 → 各自构造
  StationRouter → 实例分裂, 最后赋值的覆盖前者, 单例契约被破坏; init_station_router
  写 _router_instance 与 get 读侧也无互斥。

样板 (DCL): app/services/ai_model_config.py 的 AIModelManager.__new__ 与
  app/services/predictive_maintenance/__init__.py 的 get_service() 均用
  `_lock = threading.Lock()` + 双重检查。

验证策略:
  CPython GIL 下纯 Python 构造无释放点, 裸跑多线程竞态难确定性复现 (见记忆
  cpython-gil-check-then-act-race-window-amplification)。故用 CountingRouter
  继承真实 StationRouter, 在 __init__ 内 sleep 撑开 check-then-act 窗口 + 计数
  构造次数, 做到确定性复现:
    RED (无锁)  → 多线程都通过 None 检查进入构造, construction_count == N
    GREEN (DCL) → 第一线程持锁构造, 其余在锁上等待, 醒来后第二次 None 检查为
                  False 直接返回, construction_count == 1, 不死锁。
"""
import threading
import time

import pytest

from app.core import station_router as sr_module
from app.core.station_router import get_station_router, init_station_router


@pytest.fixture(autouse=True)
def _reset_router_singleton(monkeypatch):
    """每个用例前后清理全局单例, 并强制单Pod模式, 避免触发 cache/Redis 依赖与跨用例污染。"""
    monkeypatch.setenv("POD_LOCAL_ONLY", "true")
    sr_module._router_instance = None
    yield
    sr_module._router_instance = None


# ─── 并发 get_station_router: 单例唯一 + 构造只发生一次 ───


def test_concurrent_get_station_router_single_construction(monkeypatch):
    """16 线程 barrier 同步后并发 get_station_router(): 必须全部同一实例且只构造一次。

    RED (无锁): CountingRouter.__init__ 的 sleep 撑开窗口, 16 线程同时通过 None 检查
        进入构造 → construction_count == 16, 断言 ==1 失败。
    GREEN (DCL): 第一线程持锁构造 (count=1), 其余在锁上等待, 醒来后第二次检查非 None
        直接返回 → construction_count == 1, 全部同一 id。
    """
    n_threads = 16
    construction_count = [0]
    cnt_lock = threading.Lock()
    original_cls = sr_module.StationRouter

    class CountingRouter(original_cls):
        """继承真实类保留行为; 构造时计数 + sleep 撑开 check-then-act 窗口。"""

        def __init__(self, *args, **kwargs):
            with cnt_lock:
                construction_count[0] += 1
            time.sleep(0.05)  # 放大窗口: 保证多线程同时通过 None 检查
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(sr_module, "StationRouter", CountingRouter)

    results = [None] * n_threads
    start_gate = threading.Barrier(n_threads)

    def worker(idx):
        start_gate.wait()  # 16 线程同时开跑, 最大化并发闯入
        results[idx] = get_station_router()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(not t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    # 1. 构造只发生一次 (DCL 的核心保证; 无锁下 == n_threads, 确定性 RED)
    assert construction_count[0] == 1, (
        f"并发下构造了 {construction_count[0]} 次, 期望 1 次 → "
        f"get_station_router 单例 check-then-act 竞态未加锁"
    )
    # 2. 全部返回同一实例
    unique_ids = {id(r) for r in results}
    assert len(unique_ids) == 1, (
        f"返回了 {len(unique_ids)} 个不同实例, 期望同一实例 → 单例分裂"
    )
    assert all(r is results[0] for r in results)


def test_get_station_router_repeated_call_returns_same_instance():
    """单线程重复调用返回同一实例 (单例基本契约, 锁内只构造一次的回归保护)。"""
    first = get_station_router()
    for _ in range(50):
        assert get_station_router() is first


# ─── init_station_router 覆盖语义 (写侧) ───


def test_init_station_router_override_then_get_returns_new():
    """init 显式覆盖单例后, get 返回新实例; 两次 init 产生不同实例, get 始终跟随最新。

    覆盖 init_station_router 的写路径(改后亦在锁内)契约不变。
    """
    first = init_station_router(local_only=True, pod_id="pod-A")
    assert get_station_router() is first

    second = init_station_router(local_only=True, pod_id="pod-B")
    assert second is not first
    assert second.pod_id == "pod-B"
    assert get_station_router() is second
