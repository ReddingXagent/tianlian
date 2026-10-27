"""TDengine 超时加固回归测试 (卡 2bfe5ffd)

被测目标:
  1. app/core/tdengine.py get_tdengine_conn(): taosrest.connect 必须携带
     timeout=TDENGINE_TIMEOUT (默认 5s, TDENGINE_TIMEOUT env 可配)。
     taosrest 的 timeout 是 **连接级** 参数 —— TaosRestConnection.__init__ 把它
     传给 RestClient → requests，作用于该连接上每一次 execute/query 的 HTTP
     请求。缺失时底层 requests 无限挂起，TDengine 半死会拖垮 API 线程池。
  2. 锁不泄漏: connect 抛异常/超时后 _lock 必须被释放 (with 语义), 后续调用
     不被死锁卡住; _conn 回退 None 支持重试。
  3. TDengineWriter 写/读路径降级: execute/query 抛 requests 超时/连接拒绝
     异常时, 写路径记日志跳过不抛 (返回 0), 读路径返回空结构 (None/[])。

全部 mock taosrest, 无真实 TDengine 依赖。
"""
import threading
import time
from unittest.mock import MagicMock

import pytest

from app.core import tdengine as tdengine_module
from app.services.tdengine_writer import TDengineWriter


@pytest.fixture(autouse=True)
def _reset_tdengine_singleton():
    """每个用例前后清理全局单例, 避免跨用例污染。"""
    original_conn = tdengine_module._conn
    tdengine_module._conn = None
    yield
    tdengine_module._conn = original_conn


def _inject_taosrest(monkeypatch, connect_impl):
    fake_taosrest = MagicMock()
    fake_taosrest.connect = connect_impl
    monkeypatch.setattr(tdengine_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdengine_module, "taosrest", fake_taosrest, raising=False)
    return fake_taosrest


# ─── 1. connect 必须携带 timeout ───


def test_connect_passes_timeout_kwarg(monkeypatch):
    """connect 收到 timeout=TDENGINE_TIMEOUT (默认 5.0), 连接级 requests 超时生效。"""
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return MagicMock(name="tdengine_conn")

    _inject_taosrest(monkeypatch, fake_connect)

    assert tdengine_module.get_tdengine_conn() is not None
    assert captured.get("timeout") == tdengine_module.TDENGINE_TIMEOUT == 5.0


def test_connect_timeout_env_override(monkeypatch):
    """TDENGINE_TIMEOUT=0.5 env → 模块常量与 connect 传参同步生效 (float 秒)。"""
    monkeypatch.setattr(tdengine_module, "TDENGINE_TIMEOUT", 0.5)
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return MagicMock(name="tdengine_conn")

    _inject_taosrest(monkeypatch, fake_connect)

    tdengine_module.get_tdengine_conn()
    assert captured.get("timeout") == 0.5


# ─── 2. 三态失败: 锁不泄漏 + _conn 回退 + 后续调用不被死锁卡住 ───


@pytest.mark.parametrize("mode", ["hang_timeout", "timeout", "refused"])
def test_connect_failure_releases_lock_and_no_deadlock(monkeypatch, mode):
    """挂起(超时异常)/超时/拒绝三态: connect 抛异常 → 返回 None, 锁释放, 后续调用快速返回。"""
    def failing_connect(**kwargs):
        if mode == "hang_timeout":
            # 模拟底层 requests 受 timeout 约束后抛出的超时族异常
            raise TimeoutError("REST 请求超时 (timeout=5s 生效)")
        if mode == "timeout":
            import requests
            raise requests.exceptions.ReadTimeout("read timed out")
        import requests
        raise requests.exceptions.ConnectionError("connection refused")

    _inject_taosrest(monkeypatch, failing_connect)

    assert tdengine_module.get_tdengine_conn() is None
    assert tdengine_module._conn is None
    # 锁必须已释放: 后续调用 (含显式抢锁的 close) 不被卡住
    assert not tdengine_module._lock.locked(), "connect 失败后 _lock 未释放 → 死锁风险"

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(tdengine_module.get_tdengine_conn()))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert all(not t.is_alive() for t in threads), "后续并发调用被死锁卡住"
    assert results == [None] * 8


def test_connect_hang_bounded_by_timeout_then_recovers(monkeypatch):
    """挂起态: connect 睡眠超过 TDENGINE_TIMEOUT 后模拟超时异常抛出 → 上层可恢复。

    真实场景中挂起由底层 requests timeout 截断; 此处用 sleep(timeout)+raise 确定性
    模拟同一时序: 调用方在有限时间内拿到 None 而非永久阻塞, 且随后服务恢复
    (connect 成功) 时单例可正常重建。
    """
    monkeypatch.setattr(tdengine_module, "TDENGINE_TIMEOUT", 0.2)
    state = {"calls": 0}

    def flaky_connect(**kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            time.sleep(kwargs.get("timeout", 0.2))
            raise TimeoutError("simulated requests timeout")
        return MagicMock(name="tdengine_conn")

    _inject_taosrest(monkeypatch, flaky_connect)

    t0 = time.monotonic()
    assert tdengine_module.get_tdengine_conn() is None
    assert time.monotonic() - t0 < 5, "挂起未被 timeout 截断 → 线程池被拖垮"
    # 服务恢复后重试成功
    conn = tdengine_module.get_tdengine_conn()
    assert conn is not None
    assert tdengine_module._conn is conn


# ─── 3. Writer 写/读路径降级: 绝不把异常抛进遥测热路径 ───


class _FakeResult:
    """模拟 taosrest Result: 支持 len()/下标/fields。"""

    def __init__(self, rows, fields):
        self._rows = rows
        self.fields = fields

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, i):
        return self._rows[i]

    def __iter__(self):
        return iter(self._rows)


@pytest.fixture
def writer_with_conn(monkeypatch):
    """注入已建好的单例连接, 返回 (writer, conn_mock)。"""
    conn = MagicMock(name="conn")
    tdengine_module._conn = conn

    import app.services.tdengine_writer as writer_mod
    monkeypatch.setattr(writer_mod, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(writer_mod, "get_tdengine_conn", lambda: conn)
    return TDengineWriter(), conn


_RECORDS = [{"device_id": 1, "station_id": 2, "region_id": "default", "grid_power_total": 1.5}]


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("requests timeout"),
        __import__("requests").exceptions.ReadTimeout("read timed out"),
        __import__("requests").exceptions.ConnectionError("refused"),
    ],
    ids=["hang-timeout", "read-timeout", "refused"],
)
def test_write_path_degrades_on_failure(writer_with_conn, exc):
    """写路径: execute 抛超时/拒绝 → 记日志+跳过, 返回 0, 不抛进遥测热路径。"""
    writer, conn = writer_with_conn
    conn.execute.side_effect = exc

    assert writer.write_pv(_RECORDS) == 0


def test_read_path_degrades_on_failure(writer_with_conn):
    """读路径: query 抛超时族异常 → query_latest 返回 None / query_range 返回 []。"""
    writer, conn = writer_with_conn
    conn.query.side_effect = TimeoutError("requests timeout")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    assert writer.query_latest(1, "pv") is None
    assert writer.query_range(1, "pv", now - __import__("datetime").timedelta(hours=1), now) == []


def test_read_path_returns_data_when_healthy(writer_with_conn):
    """健康路径回归: query 正常时数据结构与降级前一致。"""
    writer, conn = writer_with_conn
    field = MagicMock()
    field.name = "last(ts)"
    conn.query.return_value = _FakeResult([[1700000000000]], [field])

    data = writer.query_latest(1, "pv")
    assert data == {"last(ts)": 1700000000000}
