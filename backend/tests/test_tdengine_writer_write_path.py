"""TDengine 写路径测试 (卡 fd48fbb4)

被测模块: app/services/tdengine_writer.py
范围: _write_records / write_pv / write_battery / write_charger / _format_ts /
      _validate_region — 遥测数据落库主链路 (telemetry/helpers.py 调用)。

设计要点:
  - 与 test_tdengine_sql_safety.py 互补: 彼者覆盖 query 族与通用校验器,
    本文件只覆盖写路径 (query_latest/query_range 不在此重复);
  - 全部 mock TDENGINE_AVAILABLE 与 get_tdengine_conn, 不起真实 TDengine;
  - 毒记录隔离语义 (卡 1b312e62 D1): 逐条 try, 跳过+计数+warning,
    返回真实成功条数而非 len(records)。
"""
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services import tdengine_writer as tdw
from app.services.tdengine_writer import (
    TDengineWriter,
    _format_ts,
    _validate_region,
)


@pytest.fixture
def fake_conn(monkeypatch):
    """TDENGINE_AVAILABLE=True + MagicMock 连接, execute 可编程抛异常。"""
    monkeypatch.setattr(tdw, "TDENGINE_AVAILABLE", True)
    conn = MagicMock()
    conn.execute = MagicMock(return_value=1)
    monkeypatch.setattr(tdw, "get_tdengine_conn", lambda: conn)
    return conn


def rec(device_id=1, station_id=2, region_id="cn-east", timestamp=None, **extra):
    """构造一条基本合法的遥测记录。"""
    r = {"device_id": device_id, "station_id": station_id,
         "region_id": region_id, "timestamp": timestamp}
    r.update(extra)
    return r


# ========== _validate_region: TAG 注入防御 (sql_safety 测试未覆盖) ==========

class TestValidateRegion:
    def test_none_defaults(self):
        assert _validate_region(None) == "default"

    def test_valid_alnum(self):
        assert _validate_region("cn-east-1") == "cn-east-1"
        assert _validate_region("A_b-9") == "A_b-9"

    @pytest.mark.parametrize("bad", [
        "", "a b", "cn'east", "a;b", "a; DROP TABLE d", "区域", "a'b --",
        "x" * 33, "a.b", "a(b)",
    ])
    def test_rejected(self, bad):
        with pytest.raises(ValueError):
            _validate_region(bad)

    def test_max_len_32_accepted(self):
        assert _validate_region("x" * 32) == "x" * 32

    def test_region_injection_never_reaches_sql(self, fake_conn):
        # 集成: 单引号 region 被拒, conn.execute 零调用
        n = TDengineWriter().write_pv([rec(region_id="a'; DROP TABLE d_1; --")])
        assert n == 0
        fake_conn.execute.assert_not_called()


# ========== _format_ts ==========

class TestFormatTs:
    def test_naive_datetime_passthrough(self):
        s = _format_ts(datetime(2026, 8, 17, 10, 0, 0))
        assert s == "2026-08-17 10:00:00.000000"

    def test_aware_datetime_converted_to_utc(self):
        # 上海 aware 10:00 → UTC 02:00, 无 8h 漂移
        sh = timezone(timedelta(hours=8))
        s = _format_ts(datetime(2026, 8, 17, 10, 0, 0, tzinfo=sh))
        assert s == "2026-08-17 02:00:00.000000"

    def test_iso_string_passthrough(self):
        assert _format_ts("2026-08-17 10:00:00") == "2026-08-17 10:00:00"

    def test_int_ts_passthrough(self):
        # 非日期输入原样 str() 直通 (调用方职责)
        assert _format_ts(1755427200) == "1755427200"

    def test_float_ts_passthrough(self):
        assert _format_ts(1755427200.5) == "1755427200.5"

    def test_none_defaults_to_now_utc(self):
        before = datetime.now(timezone.utc)
        s = _format_ts(None)
        after = datetime.now(timezone.utc)
        parsed = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        assert before <= parsed <= after


# ========== _write_records: 可用性与连接短路 ==========

class TestWriteRecordsAvailability:
    def test_unavailable_returns_0_and_skips(self, monkeypatch):
        monkeypatch.setattr(tdw, "TDENGINE_AVAILABLE", False)
        get_conn = MagicMock()
        monkeypatch.setattr(tdw, "get_tdengine_conn", get_conn)
        n = TDengineWriter().write_pv([rec()])
        assert n == 0
        get_conn.assert_not_called()

    def test_none_conn_returns_0(self, monkeypatch):
        monkeypatch.setattr(tdw, "TDENGINE_AVAILABLE", True)
        monkeypatch.setattr(tdw, "get_tdengine_conn", lambda: None)
        assert TDengineWriter().write_pv([rec()]) == 0

    def test_empty_records_returns_0_no_execute(self, fake_conn):
        assert TDengineWriter().write_pv([]) == 0
        fake_conn.execute.assert_not_called()


# ========== _write_records: 毒记录隔离 (D1) ==========

class TestWriteRecordsPoisonIsolation:
    def test_missing_device_id_key_skipped(self, fake_conn, caplog):
        bad = rec(device_id=None)  # get("device_id") -> None -> 校验失败
        del bad["device_id"]
        good = rec(device_id=5)
        n = TDengineWriter().write_pv([bad, good])
        assert n == 1
        assert fake_conn.execute.call_count == 1
        assert "d_5" in fake_conn.execute.call_args[0][0]
        assert any("跳过" in r.message for r in caplog.records)

    def test_none_record_skipped(self, fake_conn):
        n = TDengineWriter().write_pv([None, rec(device_id=7)])
        assert n == 1
        assert fake_conn.execute.call_count == 1

    def test_negative_device_id_skipped_not_written(self, fake_conn):
        n = TDengineWriter().write_pv([rec(device_id=-1), rec(device_id=3)])
        assert n == 1
        sqls = [c[0][0] for c in fake_conn.execute.call_args_list]
        assert all("d_3" in s for s in sqls)
        assert not any("d_-1" in s for s in sqls)

    def test_negative_station_id_skipped(self, fake_conn):
        assert TDengineWriter().write_pv([rec(station_id=-2)]) == 0
        fake_conn.execute.assert_not_called()

    def test_execute_exception_isolated(self, fake_conn, caplog):
        # 第 2 条 execute 抛异常: 只跳过该条, 第 3 条照常写入
        def execute(sql):
            if "d_2" in sql:
                raise RuntimeError("connection reset")
            return 1
        fake_conn.execute.side_effect = execute
        records = [rec(device_id=1), rec(device_id=2), rec(device_id=3)]
        n = TDengineWriter().write_pv(records)
        assert n == 2
        assert fake_conn.execute.call_count == 3
        assert any("connection reset" in r.message for r in caplog.records)

    def test_all_poison_returns_0_with_warning(self, fake_conn, caplog):
        n = TDengineWriter().write_pv([rec(device_id=-1), rec(device_id=-2)])
        assert n == 0
        assert any(re.search(r"跳过 2/2", r.message) for r in caplog.records)


# ========== _write_records: 计数与切批 ==========

class TestWriteRecordsCountingAndBatching:
    def test_returns_real_success_count_not_len(self, fake_conn):
        records = [rec(device_id=i) for i in range(3)] + [rec(device_id=-9)]
        assert TDengineWriter().write_pv(records) == 3

    def test_batch_size_splitting(self, fake_conn):
        # batch_size=2, 5 条健康记录: 切 3 批遍历, 逐条 execute 共 5 次
        w = TDengineWriter(batch_size=2)
        records = [rec(device_id=i) for i in range(5)]
        assert w.write_pv(records) == 5
        assert fake_conn.execute.call_count == 5

    def test_poison_across_batches_isolated(self, fake_conn):
        # 毒记录分布在不同批, 均被隔离且不影响其他批
        w = TDengineWriter(batch_size=2)
        records = [rec(device_id=1), rec(device_id=-1),
                   rec(device_id=2), rec(device_id=-2), rec(device_id=3)]
        assert w.write_pv(records) == 3


# ========== write_pv / write_battery / write_charger: SQL 结构 ==========

class TestWriteSqlStructure:
    def _write_one(self, conn, method, record):
        w = TDengineWriter()
        getattr(w, method)([record])
        assert conn.execute.call_count == 1
        return conn.execute.call_args[0][0]

    def test_write_pv_sql(self, fake_conn):
        sql = self._write_one(fake_conn, "write_pv",
                              rec(device_id=11, station_id=22, region_id="cn-east",
                                  pv_power_total=1234.5, run_mode=1))
        assert sql.startswith("INSERT INTO d_11 USING telemetry_pv ")
        assert "TAGS (11, 22, 'cn-east')" in sql
        assert re.search(r"VALUES \('\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}'", sql)
        # 数值列按 _PV_FIELDS 顺序展开, 缺失列填 NULL
        assert "1234.5" in sql
        assert "NULL" in sql
        assert "telemetry_battery" not in sql
        assert "DROP" not in sql

    def test_write_battery_sql(self, fake_conn):
        sql = self._write_one(fake_conn, "write_battery",
                              rec(device_id=31, station_id=32, region_id="sh",
                                  battery_soc=88, battery_voltage=512.0))
        assert sql.startswith("INSERT INTO d_31 USING telemetry_battery ")
        assert "TAGS (31, 32, 'sh')" in sql
        assert "88" in sql and "512.0" in sql

    def test_write_charger_sql(self, fake_conn):
        sql = self._write_one(fake_conn, "write_charger",
                              rec(device_id=41, station_id=42, region_id="bj",
                                  charger_voltage=220, gun_status=2))
        assert sql.startswith("INSERT INTO d_41 USING telemetry_charger ")
        assert "TAGS (41, 42, 'bj')" in sql
        assert "220" in sql and "2" in sql

    def test_region_default_when_missing(self, fake_conn):
        r = rec(device_id=1)
        del r["region_id"]
        sql = self._write_one(fake_conn, "write_pv", r)
        assert "'default'" in sql

    def test_aware_timestamp_in_sql_utc(self, fake_conn):
        sh = timezone(timedelta(hours=8))
        sql = self._write_one(fake_conn, "write_pv",
                              rec(device_id=1, timestamp=datetime(2026, 8, 17, 10, 0, 0, tzinfo=sh)))
        assert "'2026-08-17 02:00:00.000000'" in sql

    def test_string_ts_passthrough_in_sql(self, fake_conn):
        sql = self._write_one(fake_conn, "write_pv",
                              rec(device_id=1, timestamp="2026-08-17 10:00:00"))
        assert "'2026-08-17 10:00:00'" in sql

    def test_pv_field_order_matches_constant(self, fake_conn):
        # VALUES 列数 = len(_PV_FIELDS) + 1 (ts), 顺序与模块常量一致
        r = rec(device_id=1)
        for i, f in enumerate(tdw._PV_FIELDS):
            r[f] = i
        sql = self._write_one(fake_conn, "write_pv", r)
        values = sql.split("VALUES (")[1].rstrip(")")
        parts = [p.strip() for p in values.split(",")]
        assert len(parts) == len(tdw._PV_FIELDS) + 1
        assert parts[1:] == [str(i) for i in range(len(tdw._PV_FIELDS))]

    def test_three_tables_return_real_counts(self, fake_conn):
        w = TDengineWriter()
        assert w.write_pv([rec(device_id=1), rec(device_id=-1)]) == 1
        assert w.write_battery([rec(device_id=2), rec(device_id=3)]) == 2
        assert w.write_charger([rec(device_id=4)]) == 1
        assert fake_conn.execute.call_count == 4
