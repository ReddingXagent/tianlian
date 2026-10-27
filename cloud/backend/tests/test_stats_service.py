#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据看板服务 - 隔离单元测试 (MagicMock 隔离 DB)

被测: app/services/stats_service.py
设计: patch 模块级 _get_db 返回 MagicMock Session, 隔离真实数据库;
       @cached 装饰器有进程内 TTL 缓存, 每个测试前 clear_memory_cache 避免串扰。
       SQLAlchemy 查询链共享 MagicMock 节点 -> 用 db.query.side_effect 按调用顺序
       返回自链式 query mock (filter/group_by/order_by/join 返回自身)。
覆盖:
- get_dashboard_overview     结构 + 比率计算 + 空库默认值
- _calc_health_trend         上升/下降/持平/异常回落
- get_health_trend           命中健康记录 / 回落设备均值
- get_alarm_stats            级别+类型聚合 + 趋势 + 空数据
- get_workorder_stats        状态+类型聚合 + 平均时长 + 空数据
- get_engineer_performance   绩效计算 + 无工程师
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.cache import clear_memory_cache
from app.services import stats_service as stats_module
from app.services.stats_service import StatsService, stats_service


# ─────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────

def _self_query():
    """自链式 query mock: filter/group_by/order_by/join/with_entities 都返回自身。
    (卡 820cf187 团队过滤后 device/alarm/workorder 聚合走 query().with_entities(...))"""
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.join.return_value = q
    q.with_entities.return_value = q
    return q


def _row(**kw):
    """构造聚合查询结果行 (属性访问)。默认全部 None 表“空”。"""
    ns = SimpleNamespace()
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


@pytest.fixture(autouse=True)
def _reset_cache_and_db(monkeypatch):
    """每个测试前: 清内存缓存 + 隔离 _get_db (默认占位, 各测试再覆盖返回值)。"""
    clear_memory_cache()
    placeholder = MagicMock(name="placeholder_db")
    monkeypatch.setattr(stats_module, "_get_db", lambda: placeholder)
    yield
    clear_memory_cache()


def _patch_db(db):
    """把 _get_db 指向给定 mock db。"""
    return patch.object(stats_module, "_get_db", lambda: db)


# ═══════════════════════════════════════════════════════════
# 1. get_dashboard_overview
# ═══════════════════════════════════════════════════════════

class TestDashboardOverview:
    def test_structure_and_computed_rates(self):
        db = MagicMock()
        q = _self_query()
        # 四个 .first() 聚合查询共享同一行 (filter 返回自身)
        q.first.return_value = _row(
            total=10, normal=8,                       # station
            avg_health=95.0, online=7, offline=2, fault=1,  # device
            active=5, critical=1,                     # alarm
            pending=3, processing=2, today_completed=4,     # workorder
        )
        # _calc_health_trend 两条 scalar 查询 (filter 返回自身 -> 同一 scalar)
        q.scalar.return_value = 95.0
        db.query.return_value = q

        with _patch_db(db):
            result = stats_service.get_dashboard_overview()

        assert result["stations"] == {"total": 10, "normal": 8, "rate": 80.0}
        assert result["devices"] == {
            "total": 10, "online": 7, "offline": 2, "fault": 1, "online_rate": 70.0,
        }
        assert result["health"]["average"] == 95.0
        assert result["alarms"] == {"active": 5, "critical": 1}
        assert result["workorders"] == {
            "pending": 3, "processing": 2, "today_completed": 4,
        }
        assert isinstance(result["update_time"], str)

    def test_empty_db_returns_defaults(self):
        db = MagicMock()
        q = _self_query()
        # 所有聚合列为 None -> 走默认 (100 / 0)
        q.first.return_value = _row(
            total=None, normal=None, avg_health=None,
            online=None, offline=None, fault=None,
            active=None, critical=None,
            pending=None, processing=None, today_completed=None,
        )
        q.scalar.return_value = None
        db.query.return_value = q

        with _patch_db(db):
            result = stats_service.get_dashboard_overview()

        assert result["stations"]["total"] == 0
        assert result["stations"]["rate"] == 100  # total=0 -> 100
        assert result["devices"]["online_rate"] == 100
        assert result["health"]["average"] == 100  # avg_health None -> 100
        assert result["alarms"] == {"active": 0, "critical": 0}


# ═══════════════════════════════════════════════════════════
# 2. _calc_health_trend
# ═══════════════════════════════════════════════════════════

class TestCalcHealthTrend:
    def test_up_trend(self):
        db = MagicMock()
        q_today = _self_query()
        q_today.scalar.return_value = 95.0
        q_yesterday = _self_query()
        q_yesterday.scalar.return_value = 90.0
        db.query.side_effect = [q_today, q_yesterday]
        assert StatsService()._calc_health_trend(db) == "+5.0"

    def test_down_trend(self):
        db = MagicMock()
        q_today = _self_query()
        q_today.scalar.return_value = 85.0
        q_yesterday = _self_query()
        q_yesterday.scalar.return_value = 95.0
        db.query.side_effect = [q_today, q_yesterday]
        assert StatsService()._calc_health_trend(db) == "-10.0"

    def test_stable_trend(self):
        db = MagicMock()
        q1 = _self_query()
        q1.scalar.return_value = 90.0
        q2 = _self_query()
        q2.scalar.return_value = 90.0
        db.query.side_effect = [q1, q2]
        assert StatsService()._calc_health_trend(db) == "+0.0"

    def test_exception_returns_zero(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert StatsService()._calc_health_trend(db) == "+0.0"


# ═══════════════════════════════════════════════════════════
# 3. get_health_trend
# ═══════════════════════════════════════════════════════════

class TestHealthTrend:
    def test_uses_health_record_when_present(self):
        db = MagicMock()
        record_q = _self_query()
        record_q.first.return_value = SimpleNamespace(total_score=92.0)
        db.query.return_value = record_q  # days=1, 命中后 continue

        with _patch_db(db):
            trend = stats_service.get_health_trend(days=1)

        assert len(trend) == 1
        assert trend[0]["score"] == 92.0
        assert "date" in trend[0]

    def test_falls_back_to_device_avg_when_no_record(self):
        db = MagicMock()
        record_q = _self_query()
        record_q.first.return_value = None  # 无健康记录
        avg_q = _self_query()
        avg_q.scalar.return_value = Decimal("88.0")
        db.query.side_effect = [record_q, avg_q]

        with _patch_db(db):
            trend = stats_service.get_health_trend(days=1)

        assert trend[0]["score"] == 88.0


# ═══════════════════════════════════════════════════════════
# 4. get_alarm_stats
# ═══════════════════════════════════════════════════════════

class TestAlarmStats:
    def test_aggregation_and_trend_up(self):
        db = MagicMock()
        level_q = _self_query()
        level_q.all.return_value = [("critical", 5), ("warning", 3)]
        type_q = _self_query()
        type_q.all.return_value = [("overcurrent", 5)]
        prev_q = _self_query()
        prev_q.scalar.return_value = 4  # 上一周期 4 条
        db.query.side_effect = [level_q, type_q, prev_q]

        with _patch_db(db):
            result = stats_service.get_alarm_stats(days=7)

        assert result["total"] == 8
        assert result["by_level"]["critical"] == 5
        assert result["by_level"]["warning"] == 3
        assert result["by_type"] == {"overcurrent": 5}
        # (8-4)/4 * 100 = 100.0 -> up
        assert result["trend"] == "up"
        assert result["trend_pct"] == 100.0

    def test_empty_data_stable(self):
        db = MagicMock()
        level_q = _self_query()
        level_q.all.return_value = []
        type_q = _self_query()
        type_q.all.return_value = []
        prev_q = _self_query()
        prev_q.scalar.return_value = 0
        db.query.side_effect = [level_q, type_q, prev_q]

        with _patch_db(db):
            result = stats_service.get_alarm_stats(days=7)

        assert result["total"] == 0
        assert result["by_level"] == {"info": 0, "warning": 0, "critical": 0, "fatal": 0}
        assert result["trend"] == "stable"
        assert result["trend_pct"] == 0


# ═══════════════════════════════════════════════════════════
# 5. get_workorder_stats
# ═══════════════════════════════════════════════════════════

class TestWorkorderStats:
    def test_aggregation_and_avg_hours(self):
        db = MagicMock()
        status_q = _self_query()
        status_q.all.return_value = [("pending", 5), ("completed", 3)]
        type_q = _self_query()
        type_q.all.return_value = [("repair", 8)]
        resp_q = _self_query()
        resp_q.scalar.return_value = 2.5
        comp_q = _self_query()
        comp_q.scalar.return_value = 1.0
        db.query.side_effect = [status_q, type_q, resp_q, comp_q]

        with _patch_db(db):
            result = stats_service.get_workorder_stats(days=7)

        assert result["total"] == 8
        assert result["by_status"] == {"pending": 5, "completed": 3}
        assert result["by_type"] == {"repair": 8}
        assert result["avg_response_hours"] == 2.5
        assert result["avg_completion_hours"] == 1.0

    def test_empty_data_zero_avgs(self):
        db = MagicMock()
        status_q = _self_query()
        status_q.all.return_value = []
        type_q = _self_query()
        type_q.all.return_value = []
        resp_q = _self_query()
        resp_q.scalar.return_value = None
        comp_q = _self_query()
        comp_q.scalar.return_value = None
        db.query.side_effect = [status_q, type_q, resp_q, comp_q]

        with _patch_db(db):
            result = stats_service.get_workorder_stats(days=7)

        assert result["total"] == 0
        assert result["avg_response_hours"] == 0
        assert result["avg_completion_hours"] == 0


# ═══════════════════════════════════════════════════════════
# 6. get_engineer_performance
# ═══════════════════════════════════════════════════════════

class TestEngineerPerformance:
    def test_performance_ranking(self):
        db = MagicMock()
        eng = MagicMock()
        eng.id = 1
        eng.real_name = "Alice"
        eng.username = "alice"
        eng.level = MagicMock()
        eng.level.value = "senior"
        eng_q = _self_query()
        eng_q.all.return_value = [eng]
        total_q = _self_query()
        total_q.all.return_value = [(1, 10)]
        completed_q = _self_query()
        completed_q.all.return_value = [(1, 8)]
        hours_q = _self_query()
        hours_q.all.return_value = [(1, 24.0)]
        db.query.side_effect = [eng_q, total_q, completed_q, hours_q]

        with _patch_db(db):
            result = stats_service.get_engineer_performance()

        assert len(result) == 1
        row = result[0]
        assert row["id"] == 1
        assert row["name"] == "Alice"
        assert row["level"] == "senior"
        assert row["total_orders"] == 10
        assert row["completed_orders"] == 8
        assert row["completion_rate"] == 80.0
        assert row["avg_hours"] == 3.0  # 24.0 / 8

    def test_no_engineers_returns_empty(self):
        db = MagicMock()
        eng_q = _self_query()
        eng_q.all.return_value = []
        db.query.side_effect = [eng_q]

        with _patch_db(db):
            assert stats_service.get_engineer_performance() == []


# ═══════════════════════════════════════════════════════════
# 7. 单例
# ═══════════════════════════════════════════════════════════

def test_singleton_is_stats_service_instance():
    assert isinstance(stats_service, StatsService)


# ═══════════════════════════════════════════════════════════
# 8. 边界缺陷加固 (RED -> GREEN)
# ═══════════════════════════════════════════════════════════

class TestBoundaryFalsyZero:
    """缺陷1: 真实零值不被 or/真值判定吞成默认值。"""

    def test_avg_health_zero_is_real_not_masked(self):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = _row(
            total=5, normal=5,
            avg_health=0.0, online=5, offline=0, fault=0,
            active=0, critical=0,
            pending=0, processing=0, today_completed=0,
        )
        q.scalar.return_value = 0.0  # _calc_health_trend 两条 scalar 查询
        db.query.return_value = q

        with _patch_db(db):
            result = stats_service.get_dashboard_overview()

        # 真实平均分 0.0, 旧代码 `or 100` / `if avg_health else 100` 会吞成 100
        assert result["health"]["average"] == 0.0


class TestBoundaryNoDataNoFabrication:
    """缺陷2: 无数据日返回 None, 禁止编造 85+(i%3)*2。"""

    def test_no_data_day_score_is_none(self):
        db = MagicMock()
        record_q = _self_query()
        record_q.first.return_value = None      # 无健康记录
        avg_q = _self_query()
        avg_q.scalar.return_value = None        # 当日无设备更新
        db.query.side_effect = [record_q, avg_q]

        with _patch_db(db):
            trend = stats_service.get_health_trend(days=1)

        assert trend[0]["score"] is None        # 旧代码得 85+(0%3)*2 = 85
        assert "date" in trend[0]


class TestBoundaryAlarmZeroToN:
    """缺陷5: 0→N 告警是激增(up), pct 不可比记 None。"""

    def test_zero_prev_and_now_positive_is_up(self):
        db = MagicMock()
        level_q = _self_query()
        level_q.all.return_value = [("warning", 3)]
        type_q = _self_query()
        type_q.all.return_value = [("overcurrent", 3)]
        prev_q = _self_query()
        prev_q.scalar.return_value = 0          # 上一周期 0 条
        db.query.side_effect = [level_q, type_q, prev_q]

        with _patch_db(db):
            result = stats_service.get_alarm_stats(days=7)

        assert result["total"] == 3
        assert result["trend"] == "up"          # 旧代码 stable
        assert result["trend_pct"] is None      # 旧代码 0


class TestBoundaryScoreClamp:
    """缺陷6: score 钳制到 [0,100], avg_hours 偏大不出现负分。"""

    def test_score_clamped_when_avg_hours_huge(self):
        db = MagicMock()
        eng = MagicMock()
        eng.id = 1
        eng.real_name = "Bob"
        eng.username = "bob"
        eng.level = MagicMock()
        eng.level.value = "senior"
        eng_q = _self_query()
        eng_q.all.return_value = [eng]
        total_q = _self_query()
        total_q.all.return_value = [(1, 1)]     # 1 单
        completed_q = _self_query()
        completed_q.all.return_value = [(1, 1)]  # 完成 1
        hours_q = _self_query()
        # 1 单耗 100h -> avg_hours=100 -> (100-500)*0.3=-120 -> raw=70-120=-50 负分
        hours_q.all.return_value = [(1, 100.0)]
        db.query.side_effect = [eng_q, total_q, completed_q, hours_q]

        with _patch_db(db):
            result = stats_service.get_engineer_performance()

        score = result[0]["score"]
        assert 0 <= score <= 100                 # 旧代码 -50.0
        assert score == 0.0                      # 负分钳到下界


class TestHoursBetweenDialect:
    """缺陷7: 小时差 SQL 表达式按方言分支 (sqlite julianday / postgres EXTRACT EPOCH)。"""

    def test_postgres_uses_extract_epoch_not_julianday(self):
        from sqlalchemy.dialects import postgresql
        from app.models.workorder import WorkOrder
        from app.services.stats_service import _hours_between
        expr = _hours_between("postgresql", WorkOrder.create_time, WorkOrder.accept_time)
        sql = str(expr.compile(dialect=postgresql.dialect(),
                               compile_kwargs={"literal_binds": True}))
        assert "extract" in sql.lower()
        assert "epoch" in sql.lower()
        assert "julianday" not in sql.lower()

    def test_sqlite_uses_julianday(self):
        from sqlalchemy.dialects import sqlite
        from app.models.workorder import WorkOrder
        from app.services.stats_service import _hours_between
        expr = _hours_between("sqlite", WorkOrder.create_time, WorkOrder.accept_time)
        sql = str(expr.compile(dialect=sqlite.dialect(),
                               compile_kwargs={"literal_binds": True}))
        assert "julianday" in sql.lower()
