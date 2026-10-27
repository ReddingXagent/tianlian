"""app/core/station_router.py _local_routes 并发竞态测试 (卡片 0524736f)

被测目标: StationRouter 单Pod模式下 _local_routes 本地字典的并发安全。
单例 DCL 已由 663f1a341 修复 (见 test_station_router_singleton.py), 本文件
只覆盖字典本身的两类竞态。

根因(修复前):
  local_only 分支的 register/unregister/list 对 self._local_routes 无任何互斥:
  1. unregister: `if station_id in self._local_routes: del self._local_routes[...]`
     是 check-then-act; 两个线程并发 unregister 同一 station_id, 都通过 `in`
     检查后各自 `del` → 第二个抛 KeyError。
  2. list_by_pod/list_by_region: `list(self._local_routes.keys())` 迭代活字典;
     并发 register 改变字典 size → CPython 抛 "dictionary changed size during
     iteration"。

修复: StationRouter.__init__ 加 self._lock=threading.RLock(); local_only 分支的
  register/unregister/list 全部纳入临界区; unregister 改 pop(station_id, None)
  原子化; list 在锁内取 keys 快照。Redis 分支(Redis 自身原子)与函数签名零改动。

验证(RED→GREEN): CPython GIL 下纯字节码 check-then-act 竞态自然多线程极难稳定
  复现 (见记忆 cpython-gil-check-then-act-race-window-amplification), 故用线程
  感知 dict 子类放大不可观测窗口, 在修复前代码上确定性复现 KeyError/RuntimeError,
  修复后退化为普通 dict 行为, 测试仍绿。这是合法的并发测试技术(放大窗口), 不改被测
  生产逻辑。

并发测试铁律: threading.Barrier(N) 的 N 必须严格等于实际调用 wait() 的线程数,
  否则死锁伪装成全量卡死。本文件每个 barrier 的 N 都与 wait 线程数严格一致。
"""
import sys
import threading
import time

import pytest

from app.core.station_router import StationRouter


# ─── 窗口放大: 线程感知 dict 子类 (合法的并发测试技术) ───


class _ContainsRaceDict(dict):
    """放大 unregister 的 check-then-act (`if sid in d: del d[sid]`) 窗口。

    __contains__ 返回 True 后主动 sleep 让出 GIL, 使并发 unregister 同 key 都
    通过 `in` 检查 → 第二个 del 抛 KeyError。修复后 unregister 走 pop (原子, 不经
    __contains__), 此放大退化为普通 dict, 测试仍绿。
    """

    _yield = 0.002

    def __contains__(self, key):
        has = super().__contains__(key)
        if has:
            time.sleep(self._yield)  # 释放时间片, 让其他 unregister 也通过检查
        return has


class _IterRaceDict(dict):
    """放大 list(d.keys()) 的迭代窗口。

    keys() 返回慢速生成器, 每个 key 让出 GIL; 并发 register/unregister 改变
    size → CPython 字典迭代器抛 "dictionary changed size during iteration"。
    修复后 list 在锁内取快照, 写操作阻塞在锁上, 迭代期间无 size 变更 → 绿。
    """

    _yield = 0.0008

    def keys(self):
        # 迭代活字典本身 (dict.keys(self)); size 变更 → CPython 抛 RuntimeError。
        for k in dict.keys(self):
            time.sleep(self._yield)  # 撑开迭代窗口
            yield k


@pytest.fixture(autouse=True)
def _tight_switch_interval():
    """压低 GIL 切换间隔放大竞态可见性, 用例后还原 (合法并发测试辅助)。"""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    yield
    sys.setswitchinterval(old)


def _run_concurrent(n_threads, target, timeout=60):
    """barrier 同步后 n_threads 线程并发跑 target, 返回 (异常列表, 存活标志列表)。

    barrier 的 parties == n_threads == 实际 wait() 线程数 (铁律)。
    """
    barrier = threading.Barrier(n_threads)
    errors = []

    def worker():
        try:
            barrier.wait()
            target()
        except Exception as e:  # noqa: BLE001 - 测试需捕获一切并发异常并归类
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    alive = [t.is_alive() for t in threads]
    return errors, alive


# ─── ① 16 线程并发 register/unregister 同一批 station_id ───


def test_concurrent_register_unregister_same_batch_no_exception():
    """16 线程并发对同一批 station_id 反复 register/unregister: 零异常 + 终态一致。

    RED(无锁): _ContainsRaceDict 放大 unregister 的 check-then-act, 并发 del 同
        key → KeyError。
    GREEN: register/unregister 在 self._lock 临界区, unregister 走 pop 原子化 →
        零异常; 每 (register, unregister) 成对, 终态 _local_routes 为空。
    """
    router = StationRouter(local_only=True)
    router._local_routes = _ContainsRaceDict()
    ids = list(range(1000, 1016))  # 16 个 station_id
    n_threads = 16
    iters = 40

    def target():
        for _ in range(iters):
            for sid in ids:
                router.register(sid, "pod-01", "default")
                router.unregister(sid)

    errors, alive = _run_concurrent(n_threads, target)
    assert not any(alive), "线程未在超时内结束 → 死锁"
    assert not errors, (
        f"并发 register/unregister 抛异常: {[type(e).__name__ for e in errors[:5]]}"
    )
    # 终态一致: 成对操作后所有路由应已移除 (每 sid 的 register 数 == unregister 数)
    assert len(router._local_routes) == 0, (
        f"终态残留 {len(router._local_routes)} 条路由"
    )


# ─── ② register 与 list 并发: 零 RuntimeError (dict changed size) ───


def test_concurrent_register_and_list_no_runtime_error():
    """register(写) 与 list_by_pod(读迭代) 并发: 零 RuntimeError。

    RED(无锁): _IterRaceDict 的慢速 keys() 撑开迭代窗口, 并发 register 改 size →
        "dictionary changed size during iteration"。
    GREEN: list 在 self._lock 内取 keys 快照, 写操作阻塞在锁上 → 迭代期间无变更。
    """
    router = StationRouter(local_only=True, pod_id="pod-01", region_id="default")
    router._local_routes = _IterRaceDict()
    # 预热若干 key, 保证 list 迭代非空
    for sid in range(2000, 2004):
        router.register(sid, "pod-01", "default")

    n_mut = 4   # 写线程
    n_read = 4  # 读(list)线程
    mut_iters = 400
    read_iters = 40
    errors = []
    # barrier 的 parties == 写线程 + 读线程 == 实际 wait 线程数 (铁律)
    barrier = threading.Barrier(n_mut + n_read)

    def mutator(idx):
        try:
            barrier.wait()
            base = idx * 10000  # 各写线程互不重叠的 key 区间, 自身 register→unregister 不与他人冲突
            for i in range(mut_iters):
                sid = base + i
                router.register(sid, "pod-01", "default")  # 加 key → size 增
                router.unregister(sid)                      # 删 key → size 减
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            barrier.wait()
            for _ in range(read_iters):
                router.list_by_pod("pod-01")  # 内部 list(self._local_routes.keys())
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=mutator, args=(i,)) for i in range(n_mut)]
    threads += [threading.Thread(target=reader) for _ in range(n_read)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not any(t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    assert not errors, (
        f"register/list 并发抛异常: {[type(e).__name__ for e in errors[:5]]}"
    )


# ─── ③ 重复 unregister 同一 key: 零 KeyError ───


def test_concurrent_unregister_same_key_no_keyerror():
    """16 线程并发 unregister 同一 station_id: 零 KeyError。

    RED(无锁): _ContainsRaceDict 放大窗口, 16 线程都通过 `in` 检查 → 15 个 del
        抛 KeyError。
    GREEN: unregister 走 pop(station_id, None) 原子 + 临界区 → 重复移除静默成功。
    """
    router = StationRouter(local_only=True)
    router._local_routes = _ContainsRaceDict()
    router.register(4242, "pod-01", "default")  # 预置唯一 key
    n_threads = 16
    calls = 200

    def target():
        for _ in range(calls):
            router.unregister(4242)  # 反复移除同一 key

    errors, alive = _run_concurrent(n_threads, target)
    assert not any(alive), "线程未在超时内结束 → 死锁"
    assert not errors, (
        f"并发 unregister 抛异常: {[type(e).__name__ for e in errors[:5]]}"
    )
    assert 4242 not in router._local_routes
