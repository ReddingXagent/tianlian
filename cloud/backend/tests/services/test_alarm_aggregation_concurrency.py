"""告警聚合防风暴并发安全测试 (卡 a7c7ee05)

被测: app/services/alarm_aggregation.py 的模块级全局 _storm_counters。

风险:
1. _storm_counters 是模块级全局可变 dict, 无锁保护。
2. _clean_storm_counters() 遍历 _storm_counters.items() 同时 del key,
   多线程下抛 'dictionary changed size during iteration' RuntimeError。
3. check_anti_storm() 的 check-then-act (len 读 → append 写) 非原子,
   多线程可同时通过 ANTI_STORM_MAX_TRIGGERS 上限检查 → 上限被绕过。

验证:
(a) _clean_storm_counters (迭代) 与 check_anti_storm (写) 并发不产生 RuntimeError。
(b) 多线程并发 check_anti_storm 同 key, 允许触发次数 <= ANTI_STORM_MAX_TRIGGERS。
"""
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.services import alarm_aggregation as aa
from app.services.alarm_aggregation import (
    check_anti_storm,
    ANTI_STORM_MAX_TRIGGERS,
)


@pytest.fixture(autouse=True)
def _isolate_storm_counters():
    """每个用例前后清空模块级防风暴计数器, 避免跨用例/跨线程残留。"""
    aa._storm_counters.clear()
    yield
    aa._storm_counters.clear()


class TestAntiStormConcurrency:

    def test_concurrent_clean_and_check_no_runtime_error(self, monkeypatch):
        """(a) _clean_storm_counters 迭代与 check_anti_storm 写并发不产生 RuntimeError。

        修复前: _clean_storm_counters 遍历 _storm_counters.items() 时, 其他线程
                新增/del key 改变 dict 大小 → CPython 抛 'dictionary changed size
                during iteration' RuntimeError (被 try/except 吞并记 exception 日志)。
        修复后: 锁串行化所有读写 → RuntimeError 不发生 → logger.exception 不被调用。
        """
        recorded = []

        def fake_exception(msg, *args, **kwargs):
            recorded.append(msg)

        monkeypatch.setattr(aa.logger, "exception", fake_exception)

        # 预填大量过期 key, 放大 _clean_storm_counters 的迭代窗口, 提高竞态命中率
        old = datetime.now(timezone.utc) - timedelta(seconds=120)
        for i in range(200):
            aa._storm_counters[(i, i)] = [old]

        stop = threading.Event()

        def cleaner():
            while not stop.is_set():
                aa._clean_storm_counters()

        def checker():
            # 持续用递增新 key 调 check_anti_storm → 每次新增 dict entry 改变 size
            i = 0
            while not stop.is_set():
                aa.check_anti_storm(1000 + i, 2000)
                i += 1

        workers = [threading.Thread(target=cleaner) for _ in range(4)]
        workers += [threading.Thread(target=checker) for _ in range(4)]
        for t in workers:
            t.start()
        # 给足时间让迭代/写并发充分发生
        threading.Event().wait(0.3)
        stop.set()
        for t in workers:
            t.join()

        # 修复前 _clean_storm_counters 抛 RuntimeError 被吞 → 记录 "清理防风暴计数器异常"
        clean_errors = [m for m in recorded if "清理防风暴" in m]
        assert clean_errors == [], (
            f"并发清理触发 'dict changed size' RuntimeError (被 try/except 吞): "
            f"{len(clean_errors)} 次, 样本: {clean_errors[:3]}"
        )

    def test_concurrent_calls_do_not_bypass_max_triggers(self, monkeypatch):
        """(b) check_anti_storm 的 len 读 → append 写非原子, 多线程可绕过上限。

        CPython GIL 下该竞态窗口极窄、难以自然稳定复现 (实测 barrier + 50 线程
        + 1us switchinterval 仅偶发触发 allowed>MAX)。故用线程感知容器放大 append
        前的窗口 (主动让出 GIL), 精确模拟"线程在 len 检查通过后、append 完成前被
        切走"的最坏时机, 确定性暴露 check-then-act 非原子性。

        修复前: 多线程同时通过 len 检查 → allowed 远超 MAX_TRIGGERS。
        修复后: 锁串行化整个 check 关键段 → allowed == MAX_TRIGGERS。
        """
        class YieldingList(list):
            """list 子类: append 前主动让出 GIL, 放大 len→append 竞态窗口。"""
            def append(self, x):
                threading.Event().wait(0.002)
                super().append(x)

        class YieldingDict(dict):
            """dict 子类: 把赋入的普通 list 包装成 YieldingList。"""
            def __setitem__(self, k, v):
                if isinstance(v, list) and not isinstance(v, YieldingList):
                    v = YieldingList(v)
                super().__setitem__(k, v)

        monkeypatch.setattr(aa, "_storm_counters", YieldingDict())
        # 屏蔽 _clean_storm_counters 的 dict 迭代竞态噪音, 纯测 check-then-act
        monkeypatch.setattr(aa, "_clean_storm_counters", lambda: None)

        device_id, rule_id = 1, 10
        n_threads = 10
        calls_per_thread = 2  # 共 20 次调用, MAX=3

        allowed = []
        allowed_lock = threading.Lock()
        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()  # 所有线程同时放行, 最大化并发对齐
            local = [check_anti_storm(device_id, rule_id)
                     for _ in range(calls_per_thread)]
            with allowed_lock:
                allowed.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_allowed = sum(1 for r in allowed if r is True)
        # 修复前: 竞态使 total_allowed == 20 (>>3); 修复后: == 3
        assert total_allowed <= ANTI_STORM_MAX_TRIGGERS, (
            f"并发竞态绕过防风暴上限: 允许 {total_allowed} 次 > "
            f"{ANTI_STORM_MAX_TRIGGERS}"
        )
