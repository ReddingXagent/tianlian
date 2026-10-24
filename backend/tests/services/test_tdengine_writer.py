"""TDengineWriter 单元测试 (卡 a32fb821)

卡 eedd9431 去重: 原 tests/test_tdengine_writer.py (根目录, 卡 6c2bd8ae) 是本文件的
近重复子集 (37 vs 39 测试; 根目录 test_write_charger_no_conn_returns_zero 仅改名缺失, 其余
全部被本文件覆盖; 本文件额外含 test_custom_batch_size / test_write_charger_disabled)。
根目录旧文件已删, 本文件为唯一权威副本。

被测模块: app/services/tdengine_writer.py (462 行)

全部外部依赖 mock，绝不连真 TDengine，测试可离线跑。
覆盖:
  - 可用性门控 (TDENGINE_AVAILABLE)
  - 连接获取 (get_tdengine_conn None 短路)
  - 空记录短路
  - SQL 生成正确性 (子表名 / TAGS / 时间戳序列化 / 缺失字段填 NULL)
  - 批量分片 batch_size 边界 + 批内失败不污染下一批
  - execute 异常降级
  - write_pv / write_battery / write_charger
  - query_latest / query_range / query_station_stats (pv/battery/charger/unknown)
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.services import tdengine_writer as tdw_module
from app.services.tdengine_writer import TDengineWriter


# ========== helpers ==========

class _FakeField:
    """模拟 taosrest 查询结果的列定义。"""

    def __init__(self, name):
        self.name = name


class FakeResult(list):
    """模拟 taosrest 查询结果: 支持 len()/索引/迭代 + .fields 列定义。"""

    def __init__(self, rows=(), fields=()):
        super().__init__(rows)
        self.fields = list(fields)


@pytest.fixture
def fake_conn(monkeypatch):
    """TDENGINE_AVAILABLE=True 并注入一个 MagicMock 连接。

    每个 write_xxx/query_xxx 调用 get_tdengine_conn() 拿到同一个连接，
    query 默认返回空结果，execute 默认 no-op；具体测试可自行覆写。
    """
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    conn = MagicMock()
    conn.query = MagicMock(return_value=FakeResult())
    conn.execute = MagicMock()
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: conn)
    return conn


def _capture_sql(conn):
    """把 conn.execute 的所有入参 SQL 收集到列表。"""
    sqls = []
    conn.execute.side_effect = lambda sql: sqls.append(sql)
    return sqls


# ========== __init__ ==========

def test_default_batch_size():
    assert TDengineWriter().batch_size == 500


def test_custom_batch_size():
    assert TDengineWriter(batch_size=7).batch_size == 7


# ========== write_pv ==========

def test_write_pv_disabled(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert TDengineWriter().write_pv([{"device_id": 1}]) == 0


def test_write_pv_no_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: None)
    assert TDengineWriter().write_pv([{"device_id": 1}]) == 0


def test_write_pv_empty_records(fake_conn):
    assert TDengineWriter().write_pv([]) == 0
    fake_conn.execute.assert_not_called()


def test_write_pv_success_and_sql(fake_conn):
    sqls = _capture_sql(fake_conn)
    ts = datetime(2026, 1, 2, 3, 4, 5)
    n = TDengineWriter(batch_size=500).write_pv([{
        "device_id": 7,
        "station_id": 9,
        "region_id": "east",
        "timestamp": ts,
        "grid_voltage_a": 220.0,
        "pv1_power": 5.5,
    }])

    assert n == 1
    assert fake_conn.execute.call_count == 1
    sql = sqls[0]
    # 自动建子表 USING ... TAGS
    assert "INSERT INTO d_7 USING telemetry_pv TAGS (7, 9, 'east')" in sql
    # 时间戳按 strftime("%Y-%m-%d %H:%M:%S.%f") 序列化
    assert "'2026-01-02 03:04:05.000000'" in sql
    # 提供的字段值进 VALUES
    assert "220.0" in sql
    assert "5.5" in sql
    # 缺失字段填 NULL
    assert "NULL" in sql


def test_write_pv_string_timestamp(fake_conn):
    sqls = _capture_sql(fake_conn)
    TDengineWriter().write_pv([{"device_id": 1, "timestamp": "2026-01-01 00:00:00"}])
    assert "'2026-01-01 00:00:00'" in sqls[0]


def test_write_pv_default_tags_when_missing(fake_conn):
    sqls = _capture_sql(fake_conn)
    TDengineWriter().write_pv([{"device_id": 3}])  # 无 station_id/region_id
    assert "USING telemetry_pv TAGS (3, 0, 'default')" in sqls[0]


def test_write_pv_batch_split(fake_conn):
    fake_conn.execute = MagicMock()
    w = TDengineWriter(batch_size=2)
    records = [
        {"device_id": i, "station_id": 1, "timestamp": datetime(2026, 1, 1)}
        for i in range(5)
    ]
    n = w.write_pv(records)
    # batch_size=2 → 3 批 (2,2,1)，每条一个 SQL → execute 5 次，全部成功
    assert n == 5
    assert fake_conn.execute.call_count == 5


def test_write_pv_execute_exception_degrades(fake_conn):
    # 任意 execute 抛异常 → 整批失败但不崩溃，本批不计入 total_written
    fake_conn.execute.side_effect = RuntimeError("connection lost")
    w = TDengineWriter(batch_size=500)
    n = w.write_pv([{"device_id": 1}, {"device_id": 2}])
    assert n == 0


def test_write_pv_partial_batch_failure(fake_conn):
    # batch_size=2, 4 条 → 2 批; 第一批首条 execute 抛异常时该毒调用被逐条隔离跳过,
    # 同批后续健康记录 (record1) 不再被旧码误杀, 照常写入; 第二批不受影响 (卡 1b312e62 D1)。
    calls = []

    def _execute(sql):
        calls.append(sql)
        if len(calls) == 1:  # 仅第一次调用抛异常
            raise RuntimeError("first batch down")

    fake_conn.execute.side_effect = _execute
    w = TDengineWriter(batch_size=2)
    records = [{"device_id": i, "timestamp": datetime(2026, 1, 1)} for i in range(4)]
    n = w.write_pv(records)
    assert n == 3  # record0 跳过; record1/record2/record3 三条健康记录成功


# ========== write_battery ==========

def test_write_battery_success_and_sql(fake_conn):
    sqls = _capture_sql(fake_conn)
    n = TDengineWriter().write_battery([{
        "device_id": 5,
        "station_id": 2,
        "region_id": "r",
        "timestamp": datetime(2026, 1, 1),
        "battery_soc": 80.0,
        "battery_voltage": 512.0,
    }])
    assert n == 1
    sql = sqls[0]
    assert "INSERT INTO d_5 USING telemetry_battery TAGS (5, 2, 'r')" in sql
    assert "80.0" in sql
    assert "512.0" in sql


def test_write_battery_empty_and_disabled(monkeypatch, fake_conn):
    assert TDengineWriter().write_battery([]) == 0
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert TDengineWriter().write_battery([{"device_id": 1}]) == 0


def test_write_battery_no_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: None)
    assert TDengineWriter().write_battery([{"device_id": 1}]) == 0


# ========== write_charger ==========

def test_write_charger_success_and_sql(fake_conn):
    sqls = _capture_sql(fake_conn)
    n = TDengineWriter().write_charger([{
        "device_id": 11,
        "station_id": 3,
        "region_id": "z",
        "timestamp": datetime(2026, 1, 1),
        "charger_voltage": 400.0,
        "charger_current": 32.0,
    }])
    assert n == 1
    sql = sqls[0]
    assert "INSERT INTO d_11 USING telemetry_charger TAGS (11, 3, 'z')" in sql
    assert "400.0" in sql
    assert "32.0" in sql


def test_write_charger_no_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: None)
    assert TDengineWriter().write_charger([{"device_id": 1}]) == 0


def test_write_charger_disabled(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert TDengineWriter().write_charger([{"device_id": 1}]) == 0


# ========== write_xxx 对称分支 (parametrize) ==========

@pytest.mark.parametrize("method", ["write_pv", "write_battery", "write_charger"])
def test_write_method_disabled(monkeypatch, method):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert getattr(TDengineWriter(), method)([{"device_id": 1}]) == 0


@pytest.mark.parametrize("method", ["write_pv", "write_battery", "write_charger"])
def test_write_method_execute_exception_degrades(fake_conn, method):
    fake_conn.execute.side_effect = RuntimeError("conn lost")
    w = TDengineWriter()
    n = getattr(w, method)([{
        "device_id": 1, "station_id": 1, "timestamp": datetime(2026, 1, 1),
    }])
    assert n == 0


@pytest.mark.parametrize("method", ["write_pv", "write_battery", "write_charger"])
def test_write_method_string_timestamp(fake_conn, method):
    sqls = _capture_sql(fake_conn)
    getattr(TDengineWriter(), method)([{"device_id": 1, "timestamp": "2026-01-01 00:00:00"}])
    assert "'2026-01-01 00:00:00'" in sqls[0]


@pytest.mark.parametrize("method", ["write_battery", "write_charger"])
def test_write_method_empty_records(fake_conn, method):
    assert getattr(TDengineWriter(), method)([]) == 0
    fake_conn.execute.assert_not_called()


# ========== query_latest ==========

def test_query_latest_found(fake_conn):
    rows = [[1, 220.0, 5.5]]
    fields = [_FakeField("ts"), _FakeField("grid_voltage_a"), _FakeField("pv1_power")]
    fake_conn.query.return_value = FakeResult(rows, fields)

    data = TDengineWriter().query_latest(7, "pv")
    assert data == {"ts": 1, "grid_voltage_a": 220.0, "pv1_power": 5.5}
    sql = fake_conn.query.call_args[0][0]
    assert "SELECT LAST(*) FROM d_7" in sql


def test_query_latest_no_data(fake_conn):
    fake_conn.query.return_value = FakeResult()
    assert TDengineWriter().query_latest(7, "pv") is None


def test_query_latest_disabled(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert TDengineWriter().query_latest(1, "pv") is None


def test_query_latest_no_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: None)
    assert TDengineWriter().query_latest(1, "pv") is None


def test_query_latest_exception_returns_none(fake_conn):
    fake_conn.query.side_effect = RuntimeError("query failed")
    assert TDengineWriter().query_latest(1, "pv") is None


# ========== query_range ==========

def test_query_range_found(fake_conn):
    rows = [[1, 220.0], [2, 221.0]]
    fields = [_FakeField("ts"), _FakeField("grid_voltage_a")]
    fake_conn.query.return_value = FakeResult(rows, fields)

    out = TDengineWriter().query_range(
        3, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2), limit=100
    )
    assert out == [
        {"ts": 1, "grid_voltage_a": 220.0},
        {"ts": 2, "grid_voltage_a": 221.0},
    ]
    sql = fake_conn.query.call_args[0][0]
    assert "SELECT * FROM d_3" in sql
    assert "WHERE ts >= '2026-01-01 00:00:00'" in sql
    assert "AND ts <= '2026-01-02 00:00:00'" in sql
    assert "ORDER BY ts DESC" in sql
    assert "LIMIT 100" in sql


def test_query_range_empty(fake_conn):
    fake_conn.query.return_value = FakeResult()
    out = TDengineWriter().query_range(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == []


def test_query_range_disabled(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert TDengineWriter().query_range(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2)) == []


def test_query_range_no_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: None)
    out = TDengineWriter().query_range(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == []


def test_query_range_exception_returns_empty(fake_conn):
    fake_conn.query.side_effect = RuntimeError("boom")
    out = TDengineWriter().query_range(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == []


# ========== query_station_stats ==========

def test_query_station_stats_pv(fake_conn):
    rows = [[10.0, 20.0, 100]]
    fields = [_FakeField("avg_power"), _FakeField("max_power"), _FakeField("data_points")]
    fake_conn.query.return_value = FakeResult(rows, fields)

    out = TDengineWriter().query_station_stats(5, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out["avg_power"] == 10.0
    assert out["data_points"] == 100
    sql = fake_conn.query.call_args[0][0]
    assert "FROM telemetry_pv" in sql
    assert "station_id = 5" in sql
    assert "AVG(grid_power_total)" in sql
    assert "MAX(grid_power_total)" in sql


def test_query_station_stats_battery(fake_conn):
    fake_conn.query.return_value = FakeResult([[80.0]], [_FakeField("avg_soc")])
    out = TDengineWriter().query_station_stats(2, "battery", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == {"avg_soc": 80.0}
    sql = fake_conn.query.call_args[0][0]
    assert "FROM telemetry_battery" in sql
    assert "AVG(battery_soc)" in sql


def test_query_station_stats_charger(fake_conn):
    fake_conn.query.return_value = FakeResult([[30.0]], [_FakeField("avg_power")])
    out = TDengineWriter().query_station_stats(8, "charger", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == {"avg_power": 30.0}
    sql = fake_conn.query.call_args[0][0]
    assert "FROM telemetry_charger" in sql
    assert "AVG(charger_power)" in sql


def test_query_station_stats_unknown_type(fake_conn):
    # 未知 table_type → 白名单校验 fail-fast 抛 ValueError，不发起查询 (卡 26e833c5)
    with pytest.raises(ValueError):
        TDengineWriter().query_station_stats(1, "wind", datetime(2026, 1, 1), datetime(2026, 1, 2))
    fake_conn.query.assert_not_called()


def test_query_station_stats_disabled(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", False)
    assert TDengineWriter().query_station_stats(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2)) is None


def test_query_station_stats_no_data(fake_conn):
    fake_conn.query.return_value = FakeResult()
    out = TDengineWriter().query_station_stats(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out is None


def test_query_station_stats_no_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: None)
    out = TDengineWriter().query_station_stats(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out is None


def test_query_station_stats_exception_returns_none(fake_conn):
    fake_conn.query.side_effect = RuntimeError("agg failed")
    out = TDengineWriter().query_station_stats(1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out is None


# ========== 输入校验器 (卡 26e833c5) 纯函数 + query 路径 fail-fast 边界 ==========
#
# 现有 write/query 测试多走"正常路径"或经 write_xxx 间接覆盖校验; 这里对 5 个 _validate_*
# 纯函数做直接断言(返回值/异常文案), 并补 query_latest / query_range / query_station_stats
# 的 fail-fast 边界: 校验失败先于可用性检查, 异常向上抛出不查库。

from app.services.tdengine_writer import (  # noqa: E402
    _validate_id, _validate_table_type, _validate_limit, _validate_time_range,
    _validate_region, _format_ts, _QUERY_LIMIT_MIN, _QUERY_LIMIT_MAX,
)


# ── _validate_id ──

def test_validate_id_accepts_int():
    assert _validate_id(7) == 7


def test_validate_id_coerces_numeric_string():
    assert _validate_id("42") == 42
    assert _validate_id("42", "device_id") == 42


def test_validate_id_rejects_none():
    # name 默认 "id" → 文案 "非法 id"
    with pytest.raises(ValueError, match="非法 id"):
        _validate_id(None)


def test_validate_id_uses_custom_name_in_message():
    with pytest.raises(ValueError, match="非法 device_id"):
        _validate_id(None, "device_id")


def test_validate_id_rejects_negative():
    with pytest.raises(ValueError, match="必须 >= 0"):
        _validate_id(-1)


def test_validate_id_rejects_injection_string():
    with pytest.raises(ValueError):
        _validate_id("1; DROP TABLE d")


# ── _validate_table_type ──

@pytest.mark.parametrize("t", ["pv", "battery", "charger"])
def test_validate_table_type_whitelist(t):
    assert _validate_table_type(t) == t


@pytest.mark.parametrize("bad", ["", "wind", "legacy", "pv;", "PV", None])
def test_validate_table_type_rejects_unknown(bad):
    with pytest.raises(ValueError, match="非法 table_type"):
        _validate_table_type(bad)


# ── _validate_limit ──

def test_validate_limit_accepts_in_range():
    assert _validate_limit(100) == 100
    assert _validate_limit(_QUERY_LIMIT_MIN) == _QUERY_LIMIT_MIN
    assert _validate_limit(_QUERY_LIMIT_MAX) == _QUERY_LIMIT_MAX


def test_validate_limit_rejects_below_min():
    with pytest.raises(ValueError, match="允许范围"):
        _validate_limit(0)


def test_validate_limit_rejects_above_max():
    with pytest.raises(ValueError, match="允许范围"):
        _validate_limit(_QUERY_LIMIT_MAX + 1)


def test_validate_limit_rejects_non_int():
    with pytest.raises(ValueError, match="非法 limit"):
        _validate_limit("abc")


# ── _validate_time_range ──

def test_validate_time_range_ok():
    s, e = datetime(2026, 1, 1), datetime(2026, 1, 2)
    # 不抛即通过 (返回 None)
    assert _validate_time_range(s, e) is None


def test_validate_time_range_equal_ok():
    assert _validate_time_range(datetime(2026, 1, 1), datetime(2026, 1, 1)) is None


def test_validate_time_range_reversed():
    with pytest.raises(ValueError, match=r"start.* > .*end"):
        _validate_time_range(datetime(2026, 1, 2), datetime(2026, 1, 1))


def test_validate_time_range_non_datetime():
    with pytest.raises(ValueError, match="必须为 datetime"):
        _validate_time_range("2026-01-01", datetime(2026, 1, 2))


# ── _validate_region ──

def test_validate_region_none_defaults():
    assert _validate_region(None) == "default"


def test_validate_region_valid():
    assert _validate_region("east-zone_1") == "east-zone_1"


@pytest.mark.parametrize("bad", ["", "a b", "区", "x" * 33, "a'b", "a;b"])
def test_validate_region_rejects(bad):
    with pytest.raises(ValueError, match="非法 region_id"):
        _validate_region(bad)


# ── _format_ts ──

def test_format_ts_none_defaults_utc_now():
    out = _format_ts(None)
    assert isinstance(out, str)
    assert len(out) == 26  # "%Y-%m-%d %H:%M:%S.%f"


def test_format_ts_naive_passthrough():
    out = _format_ts(datetime(2026, 1, 2, 10, 0, 0))
    assert out == "2026-01-02 10:00:00.000000"


def test_format_ts_aware_to_utc():
    from zoneinfo import ZoneInfo
    SHANGHAI = ZoneInfo("Asia/Shanghai")
    out = _format_ts(datetime(2026, 1, 2, 10, 0, 0, tzinfo=SHANGHAI))  # = UTC 02:00
    assert out == "2026-01-02 02:00:00.000000"


def test_format_ts_string_passthrough():
    assert _format_ts("2026-01-01 00:00:00") == "2026-01-01 00:00:00"


# ── query 路径 fail-fast: 校验失败先于可用性/连接检查, 抛出且不查库 ──

def test_query_latest_rejects_bad_table_type(fake_conn):
    """非法 table_type → 抛 ValueError, 绝不查库 (fail-fast 先于可用性检查)。"""
    with pytest.raises(ValueError, match="非法 table_type"):
        TDengineWriter().query_latest(1, "wind")
    fake_conn.query.assert_not_called()


def test_query_latest_rejects_negative_device_id(fake_conn):
    with pytest.raises(ValueError, match="必须 >= 0"):
        TDengineWriter().query_latest(-1, "pv")
    fake_conn.query.assert_not_called()


def test_query_range_rejects_reversed_time(fake_conn):
    with pytest.raises(ValueError, match=r"start.* > .*end"):
        TDengineWriter().query_range(
            1, "pv", datetime(2026, 1, 2), datetime(2026, 1, 1))
    fake_conn.query.assert_not_called()


def test_query_range_rejects_bad_limit(fake_conn):
    with pytest.raises(ValueError, match="允许范围"):
        TDengineWriter().query_range(
            1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2), limit=0)
    fake_conn.query.assert_not_called()


def test_query_range_rejects_bad_table_type(fake_conn):
    with pytest.raises(ValueError):
        TDengineWriter().query_range(
            1, "wind", datetime(2026, 1, 1), datetime(2026, 1, 2))
    fake_conn.query.assert_not_called()


def test_query_station_stats_rejects_reversed_time(fake_conn):
    with pytest.raises(ValueError, match=r"start.* > .*end"):
        TDengineWriter().query_station_stats(
            1, "pv", datetime(2026, 1, 2), datetime(2026, 1, 1))
    fake_conn.query.assert_not_called()


def test_query_station_stats_rejects_bad_table_type(fake_conn):
    with pytest.raises(ValueError, match="非法 table_type"):
        TDengineWriter().query_station_stats(
            1, "water", datetime(2026, 1, 1), datetime(2026, 1, 2))
    fake_conn.query.assert_not_called()


# ========== 浮点/边界行为 lock-down (卡 45073f31 补遗) ==========
#
# 任务卡 45073f31 假设本模块"508 行零测试", 实际卡 a32fb821 已写完整 88 测试。
# 复核后发现唯一真实覆盖缺口: _validate_id / _validate_limit 对 **浮点数(非字符串)**
# 输入走 int() 截断而非拒绝 —— 这是潜在行为陷阱 (device_id=3.7 会被静默当 3 写入,
# -0.5 经 int() 截断成 0 绕过 <0 检查)。此处显式 lock-down 现有行为, 防未来误改。

def test_validate_id_truncates_float():
    # 浮点经 int() 截断 (非四舍五入), 3.7 -> 3
    assert _validate_id(3.7) == 3
    assert _validate_id(3.0) == 3


def test_validate_id_negative_float_truncates_to_zero():
    # -0.5 经 int() 截断为 0, 绕过 "< 0" 检查被接受 (语义边界, lock-down)
    assert _validate_id(-0.5) == 0


def test_validate_id_float_string_rejected():
    # 与上面浮点数对比: 字符串 "3.5" 无法 int() 转换 -> 拒绝 (防 f-string 注入)
    with pytest.raises(ValueError):
        _validate_id("3.5")


def test_validate_limit_truncates_float():
    # 浮点 limit 经 int() 截断, 100.9 -> 100 (在 [1,10000] 内 -> 通过)
    assert _validate_limit(100.9) == 100


def test_validate_limit_explicit_boundary_one_and_max():
    # 显式锁定 [1, 10000] 双闭区间端点 (任务卡要求)
    assert _validate_limit(1) == 1
    assert _validate_limit(10000) == 10000
