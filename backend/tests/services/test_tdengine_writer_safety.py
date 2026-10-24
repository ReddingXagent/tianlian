"""TDengineWriter 写入路径 data-safety 加固测试 (卡 1b312e62)

被测模块: app/services/tdengine_writer.py
范围: write_pv / write_battery / write_charger 写入路径 (非查询路径)。

覆盖缺陷:
  - D1 (P1 数据安全): 毒记录隔离 — 单条坏记录 (缺 device_id 键 / device_id=None)
        不再拖垮整批; 健康记录照常写入; 返回值=真实成功条数 (非 len(batch))。
  - D3 (安全): 写入侧校验 — device_id / station_id 过 _validate_id, region_id
        拒单引号/分号/空格 (f-string TAGS 注入), 负值/注入片段的 id 被跳过。
  - D4 (时区族): aware datetime 显式 astimezone(UTC) 后再 strftime, 避免
        strftime 丢 tzinfo 依赖服务器时区解释导致 8h 漂移; 缺失 ts 默认 now(utc)。
  - D2 (财务, 锁定现状): query_station_stats 对累计计数器字段用 SUM 是全项目
        一致口径 (SQLAlchemy pre_aggregation + TDengine 连续聚合流同此), 且该方法
        当前无生产调用方; 本卡不改, 仅回归保护防无意改动, 待独立财务口径工单。

设计要点:
  - 全部外部依赖 mock, 绝不连真 TDengine, 测试可离线跑;
  - 毒记录用例断言 "跳过计数 + 健康记录 SQL 仍生成 + 返回真实条数" 三位一体。
"""
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.services import tdengine_writer as tdw_module
from app.services.tdengine_writer import TDengineWriter

SHANGHAI = ZoneInfo("Asia/Shanghai")


# ========== helpers (与 test_tdengine_writer.py 一致, 自包含) ==========

class _FakeField:
    def __init__(self, name):
        self.name = name


class FakeResult(list):
    def __init__(self, rows=(), fields=()):
        super().__init__(rows)
        self.fields = list(fields)


@pytest.fixture
def fake_conn(monkeypatch):
    monkeypatch.setattr(tdw_module, "TDENGINE_AVAILABLE", True)
    conn = MagicMock()
    conn.query = MagicMock(return_value=FakeResult())
    conn.execute = MagicMock()
    monkeypatch.setattr(tdw_module, "get_tdengine_conn", lambda: conn)
    return conn


def _capture_sql(conn):
    sqls = []
    conn.execute.side_effect = lambda sql: sqls.append(sql)
    return sqls


_WRITE_METHODS = ["write_pv", "write_battery", "write_charger"]


# ========== D1: 毒记录隔离 ==========

@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_poison_record_missing_device_id_isolated(fake_conn, method):
    """缺 device_id 键的毒记录跳过, 前后健康记录照写, 返回真实成功条数。

    旧码 ``table_name = f"d_{record['device_id']}"`` 下标取值 → KeyError 抛进
    整批 try → 整批静默丢弃返回 0; 修复后毒记录逐条隔离, 健康记录不受影响。
    """
    sqls = _capture_sql(fake_conn)
    records = [
        {"device_id": 1, "timestamp": datetime(2026, 1, 1)},   # 健康
        {"timestamp": datetime(2026, 1, 1)},                    # 毒: 缺 device_id
        {"device_id": 3, "timestamp": datetime(2026, 1, 1)},   # 健康
    ]
    n = getattr(TDengineWriter(), method)(records)
    assert n == 2                       # 仅 2 条健康记录成功, 毒记录不计入
    assert len(sqls) == 2               # 只为健康记录生成 SQL
    assert "d_1" in sqls[0]
    assert "d_3" in sqls[1]
    assert not any("d_None" in s for s in sqls)  # 绝不生成 d_None


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_poison_record_none_device_id_skipped(fake_conn, method):
    """device_id=None → _validate_id 拒绝, 跳过, 不崩, 不生成 d_None。

    旧码 ``record.get("device_id", 0)`` 取到 None (键存在, 默认值不生效) →
    table_name="d_None", TAGS(...None...); 修复后校验失败逐条跳过。
    """
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([{"device_id": None, "timestamp": datetime(2026, 1, 1)}])
    assert n == 0
    assert sqls == []


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_poison_record_at_batch_boundary(fake_conn, method):
    """毒记录混在 batch 边界 (首/中/尾) 全隔离, 跨多批仍只写健康记录。"""
    sqls = _capture_sql(fake_conn)
    w = TDengineWriter(batch_size=2)
    records = [
        {"device_id": None, "timestamp": datetime(2026, 1, 1)},           # 毒(批1首)
        {"device_id": 2, "timestamp": datetime(2026, 1, 1)},              # 健康(批1)
        {"timestamp": datetime(2026, 1, 1)},                              # 毒(批2首, 缺键)
        {"device_id": 4, "timestamp": datetime(2026, 1, 1)},              # 健康(批2)
        {"device_id": 5, "timestamp": datetime(2026, 1, 1)},              # 健康(批3)
    ]
    n = getattr(w, method)(records)
    assert n == 3
    assert len(sqls) == 3
    assert [s.split("d_")[1].split(" ")[0] for s in sqls] == ["2", "4", "5"]


# ========== D3: 写入侧校验 ==========

@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_rejects_region_with_quote(fake_conn, method):
    """region_id 含单引号 → TAGS 注入, 跳过该条, SQL 绝不含注入片段。"""
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([
        {"device_id": 1, "region_id": "east'; DROP TABLE telemetry_pv--", "timestamp": datetime(2026, 1, 1)},
    ])
    assert n == 0
    assert sqls == []
    # 即便 conn.execute 被调用过, 也不应出现注入残片
    for call in fake_conn.execute.call_args_list:
        assert "DROP" not in call[0][0]


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_rejects_region_with_semicolon(fake_conn, method):
    """region_id 含分号 → 拒绝。"""
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([
        {"device_id": 1, "region_id": "a;b", "timestamp": datetime(2026, 1, 1)},
    ])
    assert n == 0
    assert sqls == []


@pytest.mark.parametrize("bad_region", ["", "a b", "区", "x" * 33, "a'b", None])
def test_write_pv_region_whitelist(fake_conn, bad_region):
    """region_id 白名单: 空/空格/中文/超长/引号 拒绝; None 兜 default。"""
    rec = {"device_id": 1, "timestamp": datetime(2026, 1, 1)}
    if bad_region is not None:
        rec["region_id"] = bad_region
    sqls = _capture_sql(fake_conn)
    n = TDengineWriter().write_pv([rec])
    if bad_region is None:
        # None → "default" (合法)
        assert n == 1
        assert "'default'" in sqls[0]
    else:
        assert n == 0
        assert sqls == []


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_rejects_negative_device_id(fake_conn, method):
    """device_id 负值 → _validate_id 拒绝 → 跳过, 不生成 d_-1。"""
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([
        {"device_id": -1, "timestamp": datetime(2026, 1, 1)},
    ])
    assert n == 0
    assert sqls == []


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_rejects_negative_station_id(fake_conn, method):
    """station_id 负值 → _validate_id 拒绝 → 跳过。"""
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([
        {"device_id": 1, "station_id": -5, "timestamp": datetime(2026, 1, 1)},
    ])
    assert n == 0
    assert sqls == []


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_rejects_injection_device_id(fake_conn, method):
    """device_id 注入片段 → _validate_id 拒绝 → 跳过。"""
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([
        {"device_id": "1; DROP TABLE d", "timestamp": datetime(2026, 1, 1)},
    ])
    assert n == 0
    assert sqls == []


@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_healthy_records_with_validated_ids(fake_conn, method):
    """合法 device_id/station_id/region_id 三者都过校验 → 正常写入。"""
    sqls = _capture_sql(fake_conn)
    n = getattr(TDengineWriter(), method)([{
        "device_id": 7, "station_id": 9, "region_id": "east-zone_1",
        "timestamp": datetime(2026, 1, 1),
    }])
    assert n == 1
    assert "d_7" in sqls[0]
    assert "TAGS (7, 9, 'east-zone_1')" in sqls[0]


# ========== D4: 时区 (aware datetime → UTC) ==========

@pytest.mark.parametrize("method", _WRITE_METHODS)
def test_write_aware_datetime_converted_to_utc(fake_conn, method):
    """aware datetime (上海 +08) 显式转 UTC 后写入, 不依赖服务器时区。

    旧码 strftime 对 aware datetime 保留表面值丢 tzinfo: 上海 10:00+08 →
    "2026-01-02 10:00:00", TDengine 服务器按 UTC 解释 → 实存 10:00 UTC
    (上海 18:00), 错位 8h。修复后 astimezone(UTC) → "2026-01-02 02:00:00"。
    """
    sqls = _capture_sql(fake_conn)
    ts_shanghai = datetime(2026, 1, 2, 10, 0, 0, tzinfo=SHANGHAI)  # = UTC 02:00
    getattr(TDengineWriter(), method)([{"device_id": 1, "timestamp": ts_shanghai}])
    assert "'2026-01-02 02:00:00.000000'" in sqls[0]
    assert "'2026-01-02 10:00:00" not in sqls[0]   # 丢 tz 的表面值绝不出现


def test_write_pv_naive_datetime_passthrough(fake_conn):
    """naive datetime 无 tzinfo, 按 UTC 表面值直通 (调用方职责)。"""
    sqls = _capture_sql(fake_conn)
    TDengineWriter().write_pv([{"device_id": 1, "timestamp": datetime(2026, 1, 2, 10, 0, 0)}])
    assert "'2026-01-02 10:00:00.000000'" in sqls[0]


def test_write_pv_missing_timestamp_defaults_utc(fake_conn):
    """缺失 timestamp → 默认 now(timezone.utc), 生成合法时间戳字面量。"""
    sqls = _capture_sql(fake_conn)
    n = TDengineWriter().write_pv([{"device_id": 1}])
    assert n == 1
    ts_part = sqls[0].partition("VALUES")[2].split("'")[1]   # VALUES 后首个引号内即 ts
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$", ts_part)


# ========== D2: 锁定 query_station_stats SUM 口径 (已知缺陷, 待独立工单) ==========

def test_query_station_stats_pv_sum_locked(fake_conn):
    """回归保护: query_station_stats 对 daily_generation 用 SUM。

    已知缺陷 (卡 1b312e62 D2, 范围外记录): daily_generation / daily_charge /
    daily_discharge / charger_kwh / total_* 是 modbus 寄存器直读的累计计数器
    (modbus_schema.py 描述 "日发电量/累计发电量/日充电量..."), 遥测每行重复
    携带累计快照值, SUM 会翻 N 倍。但全项目 (SQLAlchemy pre_aggregation.py
    + TDengine 连续聚合流 CREATE STREAM) 口径一致, 且本方法当前无生产调用方;
    单改一处制造口径分裂, 应立独立财务口径工单统一处理。本测试锁定现状防无意改动。
    """
    fake_conn.query.return_value = FakeResult([[5.0]], [_FakeField("pv_generation_kwh")])
    out = TDengineWriter().query_station_stats(5, "pv", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == {"pv_generation_kwh": 5.0}
    sql = fake_conn.query.call_args[0][0]
    assert "SUM(daily_generation) AS pv_generation_kwh" in sql


def test_query_station_stats_battery_sum_locked(fake_conn):
    fake_conn.query.return_value = FakeResult([[3.0]], [_FakeField("charge_kwh")])
    out = TDengineWriter().query_station_stats(2, "battery", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == {"charge_kwh": 3.0}
    sql = fake_conn.query.call_args[0][0]
    assert "SUM(daily_charge)" in sql
    assert "SUM(daily_discharge)" in sql


def test_query_station_stats_charger_sum_locked(fake_conn):
    fake_conn.query.return_value = FakeResult([[7.0]], [_FakeField("charger_kwh")])
    out = TDengineWriter().query_station_stats(8, "charger", datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert out == {"charger_kwh": 7.0}
    sql = fake_conn.query.call_args[0][0]
    assert "SUM(charger_kwh)" in sql
