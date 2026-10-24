"""
卡 010f4894 回归: analyze_efficiency_task 遥测查询必须 ORDER BY timestamp ASC。

背景: 能耗 = kwh_values[-1] - kwh_values[0]「累计表末-首」依赖时间序。
修复前查询无 ORDER BY, 行序由存储引擎决定 (PG 下无保证) — 行序错乱时
差值为负被 max(0.0, ...) 静默钳 0, 或取到错误端点值。

覆盖:
- 乱序插入 charger_kwh → energy = 时间序末-首 (非插入序/非 0)
- 无 charger_kwh → grid_power_total 均值×时长回退口径不回归
- 空遥测不崩溃 (energy=0, confidence=0.2)
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import analytics_tasks as tasks_mod
from app.tasks.analytics_tasks import analyze_efficiency_task
from app.models.device import DeviceStatus

# 复用兄弟测试的任务调用/种子构造器, 保证口径一致
from tests.test_analytics_tasks_coverage import (
    _FakeTaskSelf, _run_task, _dev, _tele,
)


@pytest.fixture
def patched_db(test_db, monkeypatch):
    """同 test_analytics_tasks_coverage.patched_db: patch 模块级 SessionLocal。"""
    monkeypatch.setattr(tasks_mod, "SessionLocal", test_db["SessionLocal"])
    return test_db


class TestEfficiencyTelemetryOrdering:

    def test_out_of_order_kwh_uses_time_order_not_insert_order(self, patched_db):
        """乱序插入: energy 必须按时间序末-首 (30.0), 而非列表序末-首 (-30 被钳 0)。"""
        db = patched_db["session"]
        _dev(db, 7101)
        now = datetime.now(timezone.utc)
        # 插入序故意与时间序相反: kwh 40(新) → 10(旧)
        _tele(db, 7101, now, power=8, kwh=40, grid=10)
        _tele(db, 7101, now - timedelta(hours=2), power=8, kwh=10, grid=10)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(),
                           device_ids=[7101])
        assert result["breakdown"][0]["energy_kwh"] == 30.0  # 40-10 时间序

    def test_multi_point_shuffle_middle_extremes(self, patched_db):
        """多点乱序 (首末夹在中间): 端点取时间序 min/max, 非首/末行。"""
        db = patched_db["session"]
        _dev(db, 7102)
        now = datetime.now(timezone.utc)
        # 时间序 kwh: 10(h-3) 100(h-2) 50(h-1) 40(now) → energy=30
        # 插入序: 100, 40, 10, 50 — 若按插入序首末会得 50-100 → 钳 0
        _tele(db, 7102, now - timedelta(hours=2), kwh=100)
        _tele(db, 7102, now, kwh=40)
        _tele(db, 7102, now - timedelta(hours=3), kwh=10)
        _tele(db, 7102, now - timedelta(hours=1), kwh=50)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(),
                           device_ids=[7102])
        assert result["breakdown"][0]["energy_kwh"] == 30.0  # 40-10

    def test_fallback_grid_power_avg_unaffected(self, patched_db):
        """无 charger_kwh → grid 均值×时长回退口径不回归 (乱序插入下均值本就序无关)。"""
        db = patched_db["session"]
        _dev(db, 7103)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=2)
        _tele(db, 7103, now, grid=10)
        _tele(db, 7103, start, grid=10)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(),
                           device_ids=[7103], start_date=start.isoformat(),
                           end_date=now.isoformat())
        assert result["breakdown"][0]["energy_kwh"] == 20.0  # avg(10)×2h

    def test_sql_contains_order_by(self, patched_db):
        """结构断言: 查询必须显式 ORDER BY timestamp ASC。

        SQLite 测试库命中 (device_id, timestamp) 索引时无 ORDER BY 也按时间序
        返回 — 行为断言抓不住 PG 行序无保证的回归, 须直接断言 SQL 形态。
        """
        from unittest.mock import patch
        from sqlalchemy.orm import Query as _Query
        from app.models.telemetry import Telemetry as _Telemetry

        captured = []
        real_all = _Query.all

        def spy_all(self):
            if self.column_descriptions and self.column_descriptions[0]["entity"] is _Telemetry:
                captured.append(self)
            return real_all(self)

        db = patched_db["session"]
        _dev(db, 7105)
        now = datetime.now(timezone.utc)
        _tele(db, 7105, now, kwh=1)
        _tele(db, 7105, now - timedelta(hours=1), kwh=0)
        db.commit()

        with patch.object(_Query, "all", spy_all):
            _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[7105])

        tele_queries = [q for q in captured
                        if q.column_descriptions[0]["entity"] is _Telemetry]
        assert tele_queries, "未捕获到 Telemetry 查询"
        sql = str(tele_queries[-1])
        assert "ORDER BY" in sql
        assert "telemetry.timestamp ASC" in sql

    def test_empty_telemetry_no_crash(self, patched_db):
        """空遥测: energy=0, 不崩溃。"""
        db = patched_db["session"]
        _dev(db, 7104, status=DeviceStatus.OFFLINE)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(),
                           device_ids=[7104])
        assert result["status"] == "completed"
        assert result["total_energy_kwh"] == 0.0
        assert result["breakdown"][0]["energy_kwh"] == 0.0
