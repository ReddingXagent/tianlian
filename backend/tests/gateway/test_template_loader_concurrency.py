"""
get_template_loader() / reset_template_loader() 模块级单例线程安全测试。

背景:
    template_loader.py 原实现存在两处模块级单例层竞态:

    缺陷1 (get_template_loader 重 IO 在单例锁内):
        _loader_lock = threading.Lock()

        def get_template_loader(template_dir=None):
            global _global_loader
            if _global_loader is None:
                with _loader_lock:
                    if _global_loader is None:
                        _global_loader = TemplateLoader(...)
                        _global_loader.load_all()   # ← 全目录扫描 + 逐文件 YAML 解析全在锁内
            return _global_loader

        load_all() 的整段文件系统扫描 + YAML 解析发生在模块单例锁 _loader_lock 临界区内。
        并发首调时, 其余线程全部阻塞在 _loader_lock 上; 模板目录大 / 文件系统慢时表现为
        hang —— 这正是 gateway registry 卡 (626c3fe1) 里 16 线程触发 real_init 卡住的同型根因。
        附加竞态: 实例在 load_all 完成前就已通过 `_global_loader = ...` 发布, 先于 load_all
        越过外层 `is None` 检查的线程会直接 `return _global_loader` 重读, 拿到未加载实例。

    缺陷2 (reset_template_loader 无锁写):
        def reset_template_loader():
            global _global_loader
            _global_loader = None          # ← 不持 _loader_lock

        与 get_template_loader 的 DCL 读竞态: get 末尾 `return _global_loader` 在锁外重读,
        reset 恰好夹在 `if _global_loader is None` 检查与 `return` 之间则返回 None;
        更严重者 reset 夹在赋值(375)与 load_all()(376)之间, 则 `None.load_all()` 抛 AttributeError。

修复方案:
    1. get_template_loader: 模块锁内仅做 构造 + 发布赋值; load_all 移到模块锁外,
       用实例级 RLock(self._lock) + _loaded 标志保证后到线程不重复 load;
       全局读一次到局部变量, 杜绝 return 重读竞态。
    2. reset_template_loader: 纳入 _loader_lock, 与 get 的构造临界区互斥。

本测试:
    - test 1 (单线程, 确定性 RED): load_all 绝不能在模块单例锁内执行。
    - test 2 (16 线程并发首调): 单例身份唯一 + load_all 仅一次 + 无 hang + load 不在锁内。
    - test 3 (reset/get 并发): 用 sys.setswitchinterval 放大 GIL 切换暴露 check-then-act 窗口,
      断言无 None 返回 / 无异常 / 终态有效。

参照: tests/gateway/test_registry_concurrency.py, tests/gateway/test_edge_cache_concurrency.py
详见记忆: cpython-gil-check-then-act-race-window-amplification
"""
import sys
import threading
import time

import pytest

from app.gateway import template_loader as tl_module
from app.gateway.template_loader import (
    TemplateLoader,
    get_template_loader,
    reset_template_loader,
)

_loader_lock = tl_module._loader_lock


def test_get_template_loader_loads_outside_module_lock(monkeypatch):
    """load_all 的重 IO 必须在模块单例锁外执行, 否则并发首调全部阻塞。"""
    reset_template_loader()

    observed: list = []
    real_load_all = TemplateLoader.load_all

    def spy_load_all(self):
        # _loader_lock.locked() == True 表示 load_all 正在模块锁内运行(缺陷1)
        observed.append(_loader_lock.locked())
        return real_load_all(self)

    monkeypatch.setattr(TemplateLoader, "load_all", spy_load_all)

    try:
        loader = get_template_loader()
        assert loader is not None
        assert observed, "load_all 未被调用"
        # 修复后 load_all 必须在模块锁外 → locked() == False
        assert observed[0] is False, (
            "load_all 在模块单例锁 _loader_lock 内执行 → 并发首调全部阻塞 (缺陷1)"
        )
    finally:
        reset_template_loader()


def test_concurrent_first_call_single_instance_and_load_outside_lock(monkeypatch):
    """16 线程经 Barrier 同时起跑首调 get_template_loader:
       单例身份唯一 + load_all 仅一次 + 无 hang + load_all 不在模块锁内。
    """
    reset_template_loader()

    load_count = 0
    count_lock = threading.Lock()
    load_under_module_lock: list = []
    real_load_all = TemplateLoader.load_all

    def slow_spy_load_all(self):
        nonlocal load_count
        with count_lock:
            load_count += 1
        load_under_module_lock.append(_loader_lock.locked())
        time.sleep(0.03)  # 放大并发窗口, 模拟文件系统慢
        return real_load_all(self)

    monkeypatch.setattr(TemplateLoader, "load_all", slow_spy_load_all)

    try:
        num_threads = 16
        barrier = threading.Barrier(num_threads)  # N 严格 == wait() 线程数
        results: list = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            loader = get_template_loader()
            with results_lock:
                results.append(loader)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "get_template_loader 并发首调 hang"

        # 1. 单例身份唯一
        assert len(results) == num_threads
        first = results[0]
        assert all(loader is first for loader in results), "并发调用返回了不同实例"

        # 2. load_all 全局只应执行一次 (实例锁 + _loaded 保证)
        assert load_count == 1, f"load_all 应只执行一次, 实际 {load_count} 次"

        # 3. 关键: load_all 绝不能在模块单例锁内 (缺陷1 根因) —— 缺陷实现此处 == True
        assert load_under_module_lock, "load_all 未被调用"
        assert not any(load_under_module_lock), (
            "load_all 在模块单例锁内执行 → 并发首调全部阻塞 (registry 卡 626c3fe1 根因)"
        )

        # 4. 实例确实加载完成 (默认模板目录存在, 11 个 yaml)
        assert first._loaded is True
    finally:
        reset_template_loader()


def test_reset_and_get_concurrent_no_corruption(monkeypatch):
    """reset_template_loader() 与 get_template_loader() 并发:
       不得返回 None, 不得抛异常, 终态必须是有效的已加载单例。

    缺陷2 (reset 无锁) 下, get 的 `return _global_loader` 锁外重读会撞上 reset 的裸 None 写,
    返回 None; 或 reset 夹在赋值与 load_all() 之间触发 None.load_all() → AttributeError。
    用 sys.setswitchinterval 极小化 GIL 切换间隔, 确定性放大 check-then-act 窗口。
    """
    reset_template_loader()

    real_load_all = TemplateLoader.load_all

    def slow_load_all(self):
        time.sleep(0.005)  # 拉长 _global_loader 处于"已发布 / 加载中"的过渡窗口
        return real_load_all(self)

    monkeypatch.setattr(TemplateLoader, "load_all", slow_load_all)

    problems: list = []
    problems_lock = threading.Lock()
    old_interval = sys.getswitchinterval()

    try:
        sys.setswitchinterval(1e-5)  # 放大 GIL 切换, 暴露 check-then-act 竞态窗口

        num_getters = 8
        num_resetters = 4
        barrier = threading.Barrier(num_getters + num_resetters)  # N == 12 == wait() 数
        iterations = 300

        def getter():
            barrier.wait()
            for _ in range(iterations):
                try:
                    loader = get_template_loader()
                    if loader is None:
                        with problems_lock:
                            problems.append("get_template_loader 返回 None")
                        continue
                    # 立即使用, 探测半发布 / 未加载实例
                    loader.list_device_types()
                except Exception as e:  # noqa: BLE001 - 收集竞态产生的任意异常
                    with problems_lock:
                        problems.append(f"使用异常: {e!r}")

        def resetter():
            barrier.wait()
            for _ in range(iterations):
                try:
                    reset_template_loader()
                except Exception as e:  # noqa: BLE001
                    with problems_lock:
                        problems.append(f"reset 异常: {e!r}")

        threads = [threading.Thread(target=getter) for _ in range(num_getters)]
        threads += [threading.Thread(target=resetter) for _ in range(num_resetters)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive(), "reset/get 并发 hang"

        assert not problems, f"reset/get 竞态破坏单例一致性: {problems[:5]}"

        # 终态: reset 风暴过后, get 仍能返回有效已加载单例
        final = get_template_loader()
        assert isinstance(final, TemplateLoader)
        assert final._loaded is True
    finally:
        sys.setswitchinterval(old_interval)
        reset_template_loader()
