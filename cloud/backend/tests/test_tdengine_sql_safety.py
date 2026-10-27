"""TDengine 查询 SQL 输入校验加固测试 (卡 26e833c5)

被测模块: app/services/tdengine_writer.py
范围: query_latest / query_range / query_station_stats 的 f-string SQL
      defense-in-depth 输入校验 (白名单 / 类型强制 / 范围 / 时间区间)。

设计要点:
  - 所有校验先于 TDENGINE_AVAILABLE 与连接获取 (fail-fast)，非法输入异常
    向上抛出 ValueError，绝不被各方法底部的 except Exception 吞掉；
  - 故非法输入用例无需真实 TDengine，正向下沉到查询的用例用 MagicMock 连接
    验证 SQL 仍正确生成 (回归保护)。
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.services import tdengine_writer as tdw
from app.services.tdengine_writer import (
    TDengineWriter,
    _validate_id,
    _validate_table_type,
    _validate_limit,
    _validate_time_range,
)


# ========== 辅助校验函数: 直接测试 ==========

class TestValidateId:
    def test_int_passthrough(self):
        assert _validate_id(0) == 0
        assert _validate_id(42, "device_id") == 42

    def test_numeric_string_coerced(self):
        assert _validate_id("7") == 7

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            _validate_id(-1)
        with pytest.raises(ValueError):
            _validate_id(-1, "station_id")

    @pytest.mark.parametrize("bad", ["abc", None, "1; DROP TABLE d", [], object()])
    def test_non_coercible_rejected(self, bad):
        with pytest.raises(ValueError):
            _validate_id(bad)

    def test_float_string_rejected(self):
        # int("3.5") 抛 ValueError，绝不会以浮点/注入形态落到 SQL
        with pytest.raises(ValueError):
            _validate_id("3.5")


class TestValidateTableType:
    @pytest.mark.parametrize("t", ["pv", "battery", "charger"])
    def test_whitelisted(self, t):
        assert _validate_table_type(t) == t

    @pytest.mark.parametrize("t", ["wind", "legacy", "", "PV", "pv;", "battery--", None, 1])
    def test_rejected(self, t):
        with pytest.raises(ValueError):
            _validate_table_type(t)


class TestValidateLimit:
    def test_in_range(self):
        assert _validate_limit(1) == 1
        assert _validate_limit(1000) == 1000
        assert _validate_limit(10000) == 10000

    def test_zero_rejected(self):
        with pytest.raises(ValueError):
            _validate_limit(0)

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            _validate_limit(-5)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError):
            _validate_limit(10001)

    @pytest.mark.parametrize("bad", ["abc", None, "1; DROP", [], object()])
    def test_non_coercible_rejected(self, bad):
        with pytest.raises(ValueError):
            _validate_limit(bad)


class TestValidateTimeRange:
    def test_valid_range(self):
        _validate_time_range(datetime(2026, 1, 1), datetime(2026, 1, 2))

    def test_equal_start_end_allowed(self):
        t = datetime(2026, 1, 1)
        _validate_time_range(t, t)

    def test_start_after_end_rejected(self):
        with pytest.raises(ValueError):
            _validate_time_range(datetime(2026, 1, 2), datetime(2026, 1, 1))

    def test_non_datetime_rejected(self):
        with pytest.raises(ValueError):
            _validate_time_range("2026-01-01", datetime(2026, 1, 2))
        with pytest.raises(ValueError):
            _validate_time_range(datetime(2026, 1, 1), "2026-01-02")
        with pytest.raises(ValueError):
            _validate_time_range(None, datetime(2026, 1, 2))


# ========== 方法集成: 非法输入绝不抵达 conn.query ==========

@pytest.fixture
def fake_conn(monkeypatch):
    """TDENGINE_AVAILABLE=True + MagicMock 连接。

    校验先于连接获取，故非法输入在 conn.query 之前即抛 ValueError；
    正向用例可断言 query 被调用且 SQL 标识符来自已校验的值。
    """
    monkeypatch.setattr(tdw, "TDENGINE_AVAILABLE", True)
    conn = MagicMock()
    conn.query = MagicMock(return_value=[])
    conn.execute = MagicMock()
    monkeypatch.setattr(tdw, "get_tdengine_conn", lambda: conn)
    return conn


class TestQueryLatestSafety:
    def test_negative_device_id_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_latest(-1, "pv")
        fake_conn.query.assert_not_called()

    def test_bad_table_type_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_latest(1, "wind")
        fake_conn.query.assert_not_called()

    def test_injection_device_id_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_latest("1; DROP TABLE d", "pv")
        fake_conn.query.assert_not_called()

    def test_valid_input_proceeds_and_sql_safe(self, fake_conn):
        # 正向: 合法输入下沉到查询，标识符来自已 int() 校验的 device_id
        assert TDengineWriter().query_latest(7, "pv") is None  # 空结果 -> None
        fake_conn.query.assert_called_once()
        sql = fake_conn.query.call_args[0][0]
        assert "SELECT LAST(*) FROM d_7" in sql
        # 注入残片绝不出现
        assert "DROP" not in sql


class TestQueryRangeSafety:
    def test_negative_device_id_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(-1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
        fake_conn.query.assert_not_called()

    def test_bad_table_type_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(1, "legacy", datetime(2026, 1, 1), datetime(2026, 1, 2))
        fake_conn.query.assert_not_called()

    def test_zero_limit_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(
                1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2), limit=0
            )
        fake_conn.query.assert_not_called()

    def test_over_max_limit_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(
                1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2), limit=10 ** 9
            )
        fake_conn.query.assert_not_called()

    def test_injection_limit_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(
                1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2), limit="100; DROP"
            )
        fake_conn.query.assert_not_called()

    def test_start_after_end_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(1, "pv", datetime(2026, 1, 2), datetime(2026, 1, 1))
        fake_conn.query.assert_not_called()

    def test_non_datetime_time_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_range(1, "pv", "2026-01-01", datetime(2026, 1, 2))
        fake_conn.query.assert_not_called()

    def test_valid_input_proceeds_and_sql_safe(self, fake_conn):
        out = TDengineWriter().query_range(
            3, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2), limit=100
        )
        assert out == []
        sql = fake_conn.query.call_args[0][0]
        assert "FROM d_3" in sql
        assert "LIMIT 100" in sql
        assert "DROP" not in sql


class TestQueryStationStatsSafety:
    def test_negative_station_id_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_station_stats(-1, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
        fake_conn.query.assert_not_called()

    @pytest.mark.parametrize("t", ["wind", "legacy", "pv;", ""])
    def test_bad_table_type_rejected(self, fake_conn, t):
        with pytest.raises(ValueError):
            TDengineWriter().query_station_stats(1, t, datetime(2026, 1, 1), datetime(2026, 1, 2))
        fake_conn.query.assert_not_called()

    def test_injection_station_id_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_station_stats(
                "1 OR 1=1", "pv", datetime(2026, 1, 1), datetime(2026, 1, 2)
            )
        fake_conn.query.assert_not_called()

    def test_start_after_end_rejected(self, fake_conn):
        with pytest.raises(ValueError):
            TDengineWriter().query_station_stats(1, "pv", datetime(2026, 1, 2), datetime(2026, 1, 1))
        fake_conn.query.assert_not_called()

    def test_valid_pv_proceeds_and_sql_safe(self, fake_conn):
        assert TDengineWriter().query_station_stats(
            5, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2)
        ) is None
        sql = fake_conn.query.call_args[0][0]
        assert "FROM telemetry_pv" in sql
        assert "station_id = 5" in sql
        assert "DROP" not in sql
