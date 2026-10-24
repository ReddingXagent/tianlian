"""app/core/tdengine.py get_tdengine_conn() 单例双检锁(DCL)并发回归测试 (卡片 cf448d22)

被测目标: 模块级懒加载单例 _conn 的 check-then-act 竞态
  - get_tdengine_conn(): 读侧懒初始化 (调 taosrest.connect)
  - close_tdengine():    写侧显式置 None

根因(修复前无锁):
  get_tdengine_conn() 在 `_conn is None` 检查与赋值之间没有临界区。
  tdengine_writer.py 4 处调用 get_tdengine_conn() (write_telemetry_batch /
  query_pv / query_battery / query_charger), FastAPI 同步端点在 threadpool
  中并发执行, 多个线程同时通过 None 检查 → 各自 taosrest.connect() → 多余
  连接被最后赋值者覆盖后泄漏。全仓 7 个模块级单例工厂中唯一的漏网之鱼
  (其余如 get_vpp_lp_optimizer / get_station_router 均已 DCL)。

样板 (DCL): app/services/vpp/lp_optimizer.py:466 get_vpp_lp_optimizer
  `_lock = threading.Lock()` + 双重检查。

验证策略:
  CPython GIL 下纯 Python 赋值无释放点, 裸跑多线程竞态难确定性复现 (见记忆
  cpython-gil-check-then-act-race-window-amplification)。故在 fake_connect
  内 sleep 撑开 check-then-act 窗口 + 计数调用次数, 做到确定性复现:
    RED (无锁)  → 多线程都通过 None 检查进入 connect, connect_count == N
    GREEN (DCL) → 第一线程持锁 connect, 其余在锁上等待, 醒来后第二次 None
                  检查为 False 直接返回, connect_count == 1, 不死锁。
"""
import threading
import time
from unittest.mock import MagicMock

import pytest

from app.core import tdengine as tdengine_module


@pytest.fixture(autouse=True)
def _reset_tdengine_singleton():
    """每个用例前后清理全局单例, 避免跨用例污染。"""
    original_conn = tdengine_module._conn
    tdengine_module._conn = None
    yield
    tdengine_module._conn = original_conn


# ─── 并发 get_tdengine_conn: 单例唯一 + connect 只发生一次 ───


def test_concurrent_get_tdengine_conn_single_connect(monkeypatch):
    """16 线程 barrier 同步后并发 get_tdengine_conn(): taosrest.connect 必须只调 1 次, 且全部同一连接。

    RED (无锁): fake_connect 的 sleep 撑开窗口, 16 线程同时通过 None 检查进入
        connect → connect_count == 16, 断言 ==1 失败, 多余连接被覆盖泄漏。
    GREEN (DCL): 第一线程持锁 connect (count=1), 其余在锁上等待, 醒来后第二次
        检查非 None 直接返回 → connect_count == 1, 全部同一实例。
    """
    n_threads = 16
    connect_count = [0]
    cnt_lock = threading.Lock()

    def fake_connect(**kwargs):
        with cnt_lock:
            connect_count[0] += 1
        time.sleep(0.05)  # 放大窗口: 保证多线程同时通过 None 检查
        return MagicMock(name="tdengine_conn")

    fake_taosrest = MagicMock()
    fake_taosrest.connect = fake_connect

    # 强制 TDengine 可用路径 (测试环境无 taosrest), 注入计数 connect
    monkeypatch.setattr(tdengine_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdengine_module, "taosrest", fake_taosrest, raising=False)

    results = [None] * n_threads
    start_gate = threading.Barrier(n_threads)

    def worker(idx):
        start_gate.wait()  # 16 线程同时开跑, 最大化并发闯入
        results[idx] = tdengine_module.get_tdengine_conn()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(not t.is_alive() for t in threads), "线程未在超时内结束 → 死锁"
    # 1. connect 只发生一次 (DCL 的核心保证; 无锁下 == n_threads, 确定性 RED)
    assert connect_count[0] == 1, (
        f"并发下调用了 {connect_count[0]} 次 taosrest.connect, 期望 1 次 → "
        f"get_tdengine_conn 单例 check-then-act 竞态未加锁"
    )
    # 2. 全部返回同一连接实例
    assert all(r is results[0] for r in results), "返回了不同实例 → 单例分裂"


# ─── 失败回退: connect 抛异常 → _conn 回退 None, 下次重试 (保留原有逻辑) ───


def test_get_tdengine_conn_failure_fallback_resets_none(monkeypatch):
    """connect 抛异常时 _conn 回退 None 且返回 None; 后续可重试。"""
    def raising_connect(**kwargs):
        raise RuntimeError("boom")

    fake_taosrest = MagicMock()
    fake_taosrest.connect = raising_connect

    monkeypatch.setattr(tdengine_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdengine_module, "taosrest", fake_taosrest, raising=False)

    assert tdengine_module.get_tdengine_conn() is None
    assert tdengine_module._conn is None  # 回退保留


# ─── 不可用短路: taosrest 未安装 → 直接返回 None, 不触达 connect ───


def test_get_tdengine_conn_unavailable_returns_none(monkeypatch):
    """TDENGINE_AVAILABLE=False 时短路返回 None, 不调用 taosrest.connect。"""
    called = {"n": 0}
    fake_taosrest = MagicMock()

    def _connect(**kwargs):
        called["n"] += 1

    fake_taosrest.connect = _connect

    monkeypatch.setattr(tdengine_module, "TDENGINE_AVAILABLE", False)
    monkeypatch.setattr(tdengine_module, "taosrest", fake_taosrest, raising=False)

    assert tdengine_module.get_tdengine_conn() is None
    assert called["n"] == 0


# ─── 单线程重复调用: 单例基本契约 ───


def test_get_tdengine_conn_repeated_call_returns_same_instance(monkeypatch):
    """单线程重复调用返回同一连接 (锁内只 connect 一次的回归保护)。"""
    def fake_connect(**kwargs):
        return MagicMock(name="tdengine_conn")

    fake_taosrest = MagicMock()
    fake_taosrest.connect = fake_connect

    monkeypatch.setattr(tdengine_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdengine_module, "taosrest", fake_taosrest, raising=False)

    first = tdengine_module.get_tdengine_conn()
    for _ in range(50):
        assert tdengine_module.get_tdengine_conn() is first
