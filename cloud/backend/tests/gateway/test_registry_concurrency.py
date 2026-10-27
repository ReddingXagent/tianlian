"""
get_registry() / reset_registry() 模块级单例 TOCTOU 竞态测试。

背景:
    registry.py 原实现:
        _global_registry: Optional[ProtocolRegistry] = None   # 模块级全局

        def get_registry(template_dir=None):
            global _global_registry
            if _global_registry is None:                       # check
                _global_registry = ProtocolRegistry(...)        # act (构造)
                _global_registry.auto_discover()                # act (扫描)
            return _global_registry

    多线程并发首次调用 get_registry 时, 各线程可同时通过 `is None` 检查,
    各自构造实例 + 扫描 → 重复构造/扫描 (TOCTOU 竞态), 返回不同实例。

    修复方案: 参照 app/services/ai_model_config.py 的双重检查锁(DCL):
        _registry_lock = threading.Lock()
        def get_registry(...):
            if _global_registry is None:
                with _registry_lock:
                    if _global_registry is None:               # 内层二次检查
                        _global_registry = ProtocolRegistry(...)
                        _global_registry.auto_discover()
            return _global_registry

    本测试通过放慢 ProtocolRegistry.__init__ 放大 check 与 act 之间的窗口,
    使竞态在无锁实现下确定性复现 (构造计数 == 线程数);
    DCL 修复后, 构造计数必须 == 1, 所有线程拿到同一实例。

    参照: tests/gateway/test_edge_cache_concurrency.py
    详见记忆: cpython-gil-check-then-act-race-window-amplification
"""
import threading
import time

import pytest

from app.gateway import registry as registry_module
from app.gateway.registry import (
    ProtocolRegistry,
    get_registry,
    reset_registry,
)
from app.gateway.template_loader import reset_template_loader


def test_get_registry_concurrent_creates_single_instance(monkeypatch):
    """16 线程经 Barrier 同时起跑调用 get_registry(), 应只构造一个实例。"""
    reset_registry()

    # 放慢构造函数, 放大 `if _global_registry is None` 与赋值之间的竞态窗口
    construction_count = 0
    count_lock = threading.Lock()
    real_init = ProtocolRegistry.__init__

    def slow_init(self, *args, **kwargs):
        nonlocal construction_count
        with count_lock:
            construction_count += 1
        time.sleep(0.05)  # 让其它线程在此期间都通过 `is None` 检查
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(ProtocolRegistry, "__init__", slow_init)
    # auto_discover 会真实扫描 gateway 包; 测试只验证单例语义, 屏蔽扫描副作用
    monkeypatch.setattr(ProtocolRegistry, "auto_discover", lambda self, *a, **kw: None)
    # template_loader 单例已做线程安全加固 (见 test_template_loader_concurrency),
    # _load_mapping_from_templates 现走真实路径: registry DCL 保证 real_init 单线程,
    # 不会并发触碰 loader。原 monkeypatch 返回 {} 的隔离 (规避 loader 非线程安全) 已移除。

    try:
        num_threads = 16
        barrier = threading.Barrier(num_threads)  # 所有线程同时起跑
        results: list = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            reg = get_registry()
            with results_lock:
                results.append(reg)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 1. 所有线程拿到的必须是同一个实例
        assert len(results) == num_threads
        first = results[0]
        assert all(reg is first for reg in results), "并发调用返回了不同实例"

        # 2. 全局只应构造一次 (DCL 保证) —— 无锁实现此处 == num_threads
        assert construction_count == 1, (
            f"TOCTOU 竞态: 构造了 {construction_count} 次, 期望 1 次"
        )
    finally:
        reset_registry()
        reset_template_loader()


def test_reset_registry_under_concurrent_get_is_safe(monkeypatch):
    """reset_registry() 与 get_registry() 并发不应破坏单例一致性。"""
    real_init = ProtocolRegistry.__init__

    def slow_init(self, *args, **kwargs):
        time.sleep(0.02)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(ProtocolRegistry, "__init__", slow_init)
    monkeypatch.setattr(ProtocolRegistry, "auto_discover", lambda self, *a, **kw: None)

    reset_registry()
    try:
        num_getters = 8
        num_resetters = 2
        barrier = threading.Barrier(num_getters + num_resetters)  # 所有线程同时起跑
        instances: list = []
        lock = threading.Lock()

        def getter():
            barrier.wait()
            reg = get_registry()
            with lock:
                instances.append(reg)

        def resetter():
            barrier.wait()
            for _ in range(3):
                reset_registry()

        threads = [threading.Thread(target=getter) for _ in range(num_getters)]
        threads += [threading.Thread(target=resetter) for _ in range(num_resetters)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 不抛异常即通过; reset 后 get_registry 仍能返回有效实例
        final = get_registry()
        assert isinstance(final, ProtocolRegistry)
    finally:
        reset_registry()
        reset_template_loader()
