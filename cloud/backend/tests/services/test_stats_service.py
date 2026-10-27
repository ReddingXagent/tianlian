#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计服务测试

覆盖 StatsService 全部公开方法 + _calc_health_trend 私有方法：
- get_dashboard_overview: 空库 / 聚合准确性 / 今日完工 / 均健康 / 比例计算
- _calc_health_trend: 正向 / 负向 / 缺数据兜底
- get_health_trend: DeviceHealthRecord 命中 / 空库 fallback / 天数长度
- get_alarm_stats: by_level / by_type / trend(up/down/stable) / 时间范围
- get_workorder_stats: by_status / by_type / avg_response / avg_completion / 空库 / 时间范围
- get_engineer_performance: 空列表 / 绩效计算 / 排序
- @cached: 命中 / 失效
- 数据库异常: finally close 兜底

注意: stats_service 是模块级单例 + @cached 进程内内存缓存,
      cache key 仅含函数名+参数(不含 DB 状态), 跨测试会串味,
      故本文件 autouse fixture 每个测试前后清空内存缓存。
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services import stats_service as stats_mod
from app.services.stats_service import StatsService, stats_service
from app.core.cache import clear_memory_cache
from app.models.station import Station, StationStatus
from app.models.device import Device, DeviceType, DeviceStatus, DeviceHealthRecord
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus
from app.models.user import User, UserRole, EngineerLevel


# ─── 每个测试前后清空进程内缓存, 避免跨测试串味 ───
@pytest.fixture(autouse=True)
def _reset_memory_cache():
    clear_memory_cache()
    yield
    clear_memory_cache()


# ─── seed helpers (独立于 conftest 的 seed_* fixtures) ───
def _station(s, code, status=StationStatus.NORMAL, name=None):
    st = Station(name=name or f"站点{code}", code=code, status=status)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


def _device(s, station_id, sn, status=DeviceStatus.ONLINE, health=100.0,
            updated_at=None, name=None, dtype=DeviceType.PV_INVERTER):
    d = Device(
        sn=sn, name=name or sn, type=dtype, station_id=station_id,
        status=status, health_score=health, updated_at=updated_at,
    )
    s.add(d)
    s.commit()
    s.refresh(d)
    return d


def _alarm(s, device_id, level=AlarmLevel.WARNING, status=AlarmStatus.ACTIVE,
           alarm_type="t", created_at=None):
    a = Alarm(
        device_id=device_id, level=level, status=status,
        alarm_type=alarm_type, created_at=created_at,
    )
    s.add(a)
    s.commit()
    s.refresh(a)
    return a


def _workorder(s, wid, status=WorkOrderStatus.PENDING, wtype=WorkOrderType.REPAIR,
               assignee_id=None, create_time=None, accept_time=None, finish_time=None):
    w = WorkOrder(
        id=wid, status=status, type=wtype, assignee_id=assignee_id,
        create_time=create_time, accept_time=accept_time, finish_time=finish_time,
    )
    s.add(w)
    s.commit()
    s.refresh(w)
    return w


def _engineer(s, username, level=EngineerLevel.JUNIOR, real_name=None):
    u = User(
        username=username, password_hash="x", role=UserRole.ENGINEER,
        level=level, real_name=real_name or username, status="active",
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


class TestStatsService:
    def test_service_initialization(self):
        svc = StatsService()
        assert svc is not None

    def test_singleton_exists(self):
        assert stats_service is not None
        assert isinstance(stats_service, StatsService)

    def test_service_methods_present(self):
        methods = [
            "get_dashboard_overview",
            "get_health_trend",
            "get_alarm_stats",
            "get_workorder_stats",
            "get_engineer_performance",
        ]
        for m in methods:
            assert hasattr(stats_service, m), f"Missing method: {m}"

    # ────────────── get_dashboard_overview ──────────────
    def test_overview_empty_db(self, test_db):
        """空库: 全部计数为 0, 比例/均健康走兜底 100。"""
        result = stats_service.get_dashboard_overview()
        assert result["stations"] == {"total": 0, "normal": 0, "rate": 100}
        assert result["devices"] == {
            "total": 0, "online": 0, "offline": 0, "fault": 0, "online_rate": 100,
        }
        assert result["health"]["average"] == 100
        assert result["alarms"] == {"active": 0, "critical": 0}
        assert result["workorders"] == {"pending": 0, "processing": 0, "today_completed": 0}
        assert "update_time" in result

    def test_overview_aggregation_accuracy(self, test_db):
        """有数据: 聚合计数与比例准确。"""
        s = test_db["session"]
        st = _station(s, "C1", status=StationStatus.NORMAL)
        _station(s, "C2", status=StationStatus.MAINTENANCE)  # 非正常
        _device(s, st.id, "SN1", status=DeviceStatus.ONLINE, health=80.0)
        _device(s, st.id, "SN2", status=DeviceStatus.ONLINE, health=90.0)
        _device(s, st.id, "SN3", status=DeviceStatus.OFFLINE, health=50.0)
        _device(s, st.id, "SN4", status=DeviceStatus.FAULT, health=30.0)
        # 2 条 active(1 critical + 1 warning) + 1 resolved
        _alarm(s, 1, level=AlarmLevel.CRITICAL, status=AlarmStatus.ACTIVE)
        _alarm(s, 1, level=AlarmLevel.WARNING, status=AlarmStatus.ACTIVE)
        _alarm(s, 1, level=AlarmLevel.CRITICAL, status=AlarmStatus.RESOLVED)
        # 工单: 1 pending + 1 processing + 1 今日完工
        # (卡 70202e7b: finish_time 锚当前 UTC-naive 时刻, 业务日区间口径下
        # 任意时区/任意时刻均落"业务今天"窗)
        _workorder(s, "WO-1", status=WorkOrderStatus.PENDING)
        _workorder(s, "WO-2", status=WorkOrderStatus.PROCESSING)
        _workorder(s, "WO-3", status=WorkOrderStatus.COMPLETED,
                   finish_time=datetime.now(timezone.utc).replace(tzinfo=None))

        result = stats_service.get_dashboard_overview()
        assert result["stations"] == {"total": 2, "normal": 1, "rate": 50.0}
        assert result["devices"]["total"] == 4
        assert result["devices"]["online"] == 2
        assert result["devices"]["offline"] == 1
        assert result["devices"]["fault"] == 1
        assert result["devices"]["online_rate"] == 50.0
        # avg(80,90,50,30)=62.5
        assert result["health"]["average"] == 62.5
        assert result["alarms"] == {"active": 2, "critical": 1}
        assert result["workorders"] == {"pending": 1, "processing": 1, "today_completed": 1}

    def test_overview_today_completed_excludes_other_days(self, test_db):
        """昨日完工不计入 today_completed。(卡 70202e7b: 锚当前 UTC-naive 时刻)"""
        s = test_db["session"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        _workorder(s, "WO-Y", status=WorkOrderStatus.COMPLETED, finish_time=now - timedelta(days=1))
        _workorder(s, "WO-T", status=WorkOrderStatus.COMPLETED, finish_time=now)
        result = stats_service.get_dashboard_overview()
        assert result["workorders"]["today_completed"] == 1

    def test_overview_values_are_positive(self, test_db):
        result = stats_service.get_dashboard_overview()
        assert result["stations"]["total"] >= 0
        assert result["devices"]["total"] >= 0
        assert result["alarms"]["active"] >= 0
        assert result["workorders"]["pending"] >= 0

    # ────────────── _calc_health_trend ──────────────
    def test_calc_health_trend_positive(self, test_db):
        """今日均健康高于昨日 → '+diff'。"""
        s = test_db["session"]
        # 卡 70202e7b: 健康趋势按业务日 UTC-naive 区间过滤 (ba16a9ff 后日期基准为
        # 业务今天), seed 锚"当前时刻 / 24h 前"保证任意时区/任意时刻落对窗
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        st = _station(s, "C1")
        _device(s, st.id, "SN1", health=80.0, updated_at=now)
        _device(s, st.id, "SN2", health=70.0, updated_at=now - timedelta(days=1))
        svc = StatsService()
        assert svc._calc_health_trend(s) == "+10.0"

    def test_calc_health_trend_negative(self, test_db):
        """今日均健康低于昨日 → '-diff'。"""
        s = test_db["session"]
        # 同 test_calc_health_trend_positive: 锚当前时刻/24h前 (卡 70202e7b)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        st = _station(s, "C1")
        _device(s, st.id, "SN1", health=60.0, updated_at=now)
        _device(s, st.id, "SN2", health=75.0, updated_at=now - timedelta(days=1))
        svc = StatsService()
        assert svc._calc_health_trend(s) == "-15.0"

    def test_calc_health_trend_missing_data_defaults_zero(self, test_db):
        """缺今日或昨日数据 → '+0.0'。"""
        s = test_db["session"]
        st = _station(s, "C1")
        _device(s, st.id, "SN1", health=80.0,
                updated_at=datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time()))
        svc = StatsService()
        # 只有今日, 无昨日 → 走兜底
        assert svc._calc_health_trend(s) == "+0.0"

    def test_calc_health_trend_empty_db(self, test_db):
        svc = StatsService()
        assert svc._calc_health_trend(test_db["session"]) == "+0.0"

    def test_calc_health_trend_swallows_db_error(self, test_db):
        """db.query 抛异常时 except 兜底返回 '+0.0'。"""
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        svc = StatsService()
        assert svc._calc_health_trend(mock_db) == "+0.0"

    # ────────────── get_health_trend ──────────────
    def test_get_health_trend_returns_list(self, test_db):
        result = stats_service.get_health_trend(days=7)
        assert isinstance(result, list)

    def test_get_health_trend_length_matches_days(self, test_db):
        assert len(stats_service.get_health_trend(days=7)) == 7
        assert len(stats_service.get_health_trend(days=30)) == 30

    def test_get_health_trend_with_health_record(self, test_db):
        """存在 DeviceHealthRecord 时优先使用其 total_score。"""
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        rec = DeviceHealthRecord(device_id=dev.id, total_score=91.5)
        s.add(rec)
        s.commit()
        trend = stats_service.get_health_trend(days=1)
        assert len(trend) == 1
        assert trend[0]["score"] == 91.5
        assert "date" in trend[0]

    def test_get_health_trend_empty_db_returns_none(self, test_db):
        """空库: 无 record 无 device → 各日 score=None, 禁止编造 85+(i%3)*2。"""
        trend = stats_service.get_health_trend(days=3)
        assert [t["score"] for t in trend] == [None, None, None]

    # ────────────── get_alarm_stats ──────────────
    def test_get_alarm_stats_structure(self, test_db):
        result = stats_service.get_alarm_stats(days=7)
        assert isinstance(result, dict)
        assert "total" in result
        assert "by_level" in result

    def test_get_alarm_stats_by_level(self, test_db):
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        _alarm(s, dev.id, level=AlarmLevel.CRITICAL, alarm_type="a")
        _alarm(s, dev.id, level=AlarmLevel.CRITICAL, alarm_type="a")
        _alarm(s, dev.id, level=AlarmLevel.WARNING, alarm_type="b")
        _alarm(s, dev.id, level=AlarmLevel.INFO, alarm_type="c")
        r = stats_service.get_alarm_stats(days=7)
        assert r["by_level"]["critical"] == 2
        assert r["by_level"]["warning"] == 1
        assert r["by_level"]["info"] == 1
        assert r["by_level"]["fatal"] == 0
        assert r["total"] == 4

    def test_get_alarm_stats_by_type(self, test_db):
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        _alarm(s, dev.id, alarm_type="over_temp")
        _alarm(s, dev.id, alarm_type="over_temp")
        _alarm(s, dev.id, alarm_type="comm_fault")
        r = stats_service.get_alarm_stats(days=7)
        assert r["by_type"]["over_temp"] == 2
        assert r["by_type"]["comm_fault"] == 1

    def test_get_alarm_stats_trend_up(self, test_db):
        """当前期告警多于前期 → 'up'。"""
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        now = datetime.now(timezone.utc)
        # 当前期(now-7d ~ now): 4 条
        for i in range(4):
            _alarm(s, dev.id, created_at=now - timedelta(days=1))
        # 前期(now-14d ~ now-7d): 1 条
        _alarm(s, dev.id, created_at=now - timedelta(days=10))
        r = stats_service.get_alarm_stats(days=7)
        assert r["trend"] == "up"
        assert r["trend_pct"] == 300.0

    def test_get_alarm_stats_trend_down(self, test_db):
        """当前期告警少于前期 → 'down'。"""
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        now = datetime.now(timezone.utc)
        _alarm(s, dev.id, created_at=now - timedelta(days=1))  # 当前期 1 条
        for _ in range(5):
            _alarm(s, dev.id, created_at=now - timedelta(days=10))  # 前期 5 条
        r = stats_service.get_alarm_stats(days=7)
        assert r["trend"] == "down"
        assert r["trend_pct"] == -80.0

    def test_get_alarm_stats_trend_zero_to_n_is_up(self, test_db):
        """前期0告警、当前期N>0 → 激增(up); pct 分母为0不可比记 None。"""
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        _alarm(s, dev.id)  # 仅当前期 1 条, 前期 0 条
        r = stats_service.get_alarm_stats(days=7)
        assert r["trend"] == "up"
        assert r["trend_pct"] is None

    def test_get_alarm_stats_time_range_excludes_old(self, test_db):
        """超出 days 的告警不计入 total。"""
        s = test_db["session"]
        st = _station(s, "C1")
        dev = _device(s, st.id, "SN1")
        _alarm(s, dev.id)  # 今日
        _alarm(s, dev.id, created_at=datetime.now(timezone.utc) - timedelta(days=30))  # 30 天前
        r = stats_service.get_alarm_stats(days=7)
        assert r["total"] == 1

    # ────────────── get_workorder_stats ──────────────
    def test_get_workorder_stats_structure(self, test_db):
        result = stats_service.get_workorder_stats(days=7)
        assert isinstance(result, dict)
        assert "total" in result
        assert "by_status" in result
        assert "by_type" in result

    def test_get_workorder_stats_empty_db(self, test_db):
        r = stats_service.get_workorder_stats(days=7)
        assert r["total"] == 0
        assert r["by_status"] == {}
        assert r["by_type"] == {}
        assert r["avg_response_hours"] == 0
        assert r["avg_completion_hours"] == 0

    def test_get_workorder_stats_by_status(self, test_db):
        s = test_db["session"]
        _workorder(s, "WO-1", status=WorkOrderStatus.PENDING)
        _workorder(s, "WO-2", status=WorkOrderStatus.PENDING)
        _workorder(s, "WO-3", status=WorkOrderStatus.PROCESSING)
        _workorder(s, "WO-4", status=WorkOrderStatus.COMPLETED)
        r = stats_service.get_workorder_stats(days=7)
        assert r["by_status"]["pending"] == 2
        assert r["by_status"]["processing"] == 1
        assert r["by_status"]["completed"] == 1
        assert r["total"] == 4

    def test_get_workorder_stats_by_type(self, test_db):
        s = test_db["session"]
        _workorder(s, "WO-1", wtype=WorkOrderType.REPAIR)
        _workorder(s, "WO-2", wtype=WorkOrderType.REPAIR)
        _workorder(s, "WO-3", wtype=WorkOrderType.MAINTENANCE)
        r = stats_service.get_workorder_stats(days=7)
        assert r["by_type"]["repair"] == 2
        assert r["by_type"]["maintenance"] == 1

    def test_get_workorder_stats_avg_response_and_completion(self, test_db):
        """avg_response = mean(accept-create)*24, avg_completion = mean(finish-accept)*24。

        注: SQLite julianday 存在 ~1e-9 浮点误差, 业务 round(x, 1) 在 .5 边界会抖动,
        故用整数小时组合让 avg 落在干净 3.0 (round 不受微扰影响)。
        """
        s = test_db["session"]
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        # 工单1: create 10:00 → accept 12:00 (响应 2h), finish 16:00 (完工 4h)
        _workorder(
            s, "WO-1", status=WorkOrderStatus.COMPLETED,
            create_time=base.replace(hour=10), accept_time=base.replace(hour=12),
            finish_time=base.replace(hour=16),
        )
        # 工单2: create 10:00 → accept 14:00 (响应 4h), finish 16:00 (完工 2h)
        _workorder(
            s, "WO-2", status=WorkOrderStatus.COMPLETED,
            create_time=base.replace(hour=10), accept_time=base.replace(hour=14),
            finish_time=base.replace(hour=16),
        )
        r = stats_service.get_workorder_stats(days=7)
        assert r["avg_response_hours"] == 3.0    # (2 + 4) / 2
        assert r["avg_completion_hours"] == 3.0  # (4 + 2) / 2

    def test_get_workorder_stats_time_range_excludes_old(self, test_db):
        """超出 days 的工单不计入。"""
        s = test_db["session"]
        _workorder(s, "WO-1")  # 今日 (server_default now)
        _workorder(s, "WO-2", create_time=datetime.now(timezone.utc) - timedelta(days=30))
        r = stats_service.get_workorder_stats(days=7)
        assert r["total"] == 1

    # ────────────── get_engineer_performance ─────────────
    def test_get_engineer_performance_empty(self, test_db):
        """无工程师 → 空列表。"""
        assert stats_service.get_engineer_performance() == []

    def test_get_engineer_performance_returns_list(self, test_db):
        result = stats_service.get_engineer_performance()
        assert isinstance(result, list)

    def test_get_engineer_performance_calc_and_sort(self, test_db):
        """绩效计算准确且按 score 降序。"""
        s = test_db["session"]
        eng1 = _engineer(s, "eng1", level=EngineerLevel.MIDDLE, real_name="张三")
        eng2 = _engineer(s, "eng2", level=EngineerLevel.SENIOR, real_name="李四")

        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        # eng1: 4 工单, 2 完工(各耗时 2h/4h → avg 3h), 完工率 50%
        _workorder(s, "WO-1", assignee_id=eng1.id)
        _workorder(s, "WO-2", assignee_id=eng1.id)
        _workorder(s, "WO-3", status=WorkOrderStatus.COMPLETED, assignee_id=eng1.id,
                   accept_time=base.replace(hour=10), finish_time=base.replace(hour=12))
        _workorder(s, "WO-4", status=WorkOrderStatus.COMPLETED, assignee_id=eng1.id,
                   accept_time=base.replace(hour=10), finish_time=base.replace(hour=14))
        # eng2: 2 工单, 2 完工(各耗时 1h/1h → avg 1h), 完工率 100%
        _workorder(s, "WO-5", status=WorkOrderStatus.COMPLETED, assignee_id=eng2.id,
                   accept_time=base.replace(hour=10), finish_time=base.replace(hour=11))
        _workorder(s, "WO-6", status=WorkOrderStatus.COMPLETED, assignee_id=eng2.id,
                   accept_time=base.replace(hour=10), finish_time=base.replace(hour=11))

        result = stats_service.get_engineer_performance()
        assert len(result) == 2
        # 排序: eng2(完工率100%) 在 eng1(50%) 前
        assert result[0]["id"] == eng2.id
        assert result[1]["id"] == eng1.id
        # eng1 字段
        eng1_row = next(r for r in result if r["id"] == eng1.id)
        assert eng1_row["name"] == "张三"
        assert eng1_row["level"] == "middle"
        assert eng1_row["total_orders"] == 4
        assert eng1_row["completed_orders"] == 2
        assert eng1_row["completion_rate"] == 50.0
        assert eng1_row["avg_hours"] == 3.0
        # score = 50*0.7 + (100 - 3*5)*0.3 = 35 + 25.5 = 60.5
        assert eng1_row["score"] == 60.5
        # eng2 score = 100*0.7 + (100 - 1*5)*0.3 = 70 + 28.5 = 98.5
        eng2_row = next(r for r in result if r["id"] == eng2.id)
        assert eng2_row["score"] == 98.5
        assert eng2_row["completion_rate"] == 100.0

    def test_get_engineer_performance_zero_completed(self, test_db):
        """工程师无完工工单: completion_rate=0, avg_hours=0。"""
        s = test_db["session"]
        eng = _engineer(s, "eng1", level=EngineerLevel.JUNIOR, real_name="新人")
        _workorder(s, "WO-1", assignee_id=eng.id)
        _workorder(s, "WO-2", status=WorkOrderStatus.PROCESSING, assignee_id=eng.id)
        result = stats_service.get_engineer_performance()
        assert len(result) == 1
        row = result[0]
        assert row["total_orders"] == 2
        assert row["completed_orders"] == 0
        assert row["completion_rate"] == 0
        assert row["avg_hours"] == 0
        # level 走 eng.level.value
        assert row["level"] == "junior"

    # ────────────── @cached 命中 / 失效 ──────────────
    def test_cache_hit_skips_db(self, test_db, monkeypatch):
        """第二次调用命中内存缓存, 不再查库。"""
        orig_get_db = stats_mod._get_db
        calls = []

        def counting_get_db():
            calls.append(1)
            return orig_get_db()

        monkeypatch.setattr(stats_mod, "_get_db", counting_get_db)
        stats_service.get_dashboard_overview()
        stats_service.get_dashboard_overview()
        assert len(calls) == 1  # 第二次命中缓存

    def test_cache_invalidate_after_clear(self, test_db, monkeypatch):
        """清缓存后重新查库。"""
        orig_get_db = stats_mod._get_db
        calls = []

        def counting_get_db():
            calls.append(1)
            return orig_get_db()

        monkeypatch.setattr(stats_mod, "_get_db", counting_get_db)
        stats_service.get_dashboard_overview()
        assert len(calls) == 1
        clear_memory_cache()
        stats_service.get_dashboard_overview()
        assert len(calls) == 2

    # ────────────── 数据库异常 → finally close 兜底 ──────────────
    def test_dashboard_db_exception_closes_and_reraises(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(stats_mod, "_get_db", lambda: mock_db)
        with pytest.raises(RuntimeError):
            stats_service.get_dashboard_overview()
        mock_db.close.assert_called_once()

    def test_alarm_stats_db_exception_closes_and_reraises(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(stats_mod, "_get_db", lambda: mock_db)
        with pytest.raises(RuntimeError):
            stats_service.get_alarm_stats()
        mock_db.close.assert_called_once()

    def test_workorder_stats_db_exception_closes_and_reraises(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(stats_mod, "_get_db", lambda: mock_db)
        with pytest.raises(RuntimeError):
            stats_service.get_workorder_stats()
        mock_db.close.assert_called_once()

    def test_engineer_performance_db_exception_closes_and_reraises(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(stats_mod, "_get_db", lambda: mock_db)
        with pytest.raises(RuntimeError):
            stats_service.get_engineer_performance()
        mock_db.close.assert_called_once()

    def test_health_trend_db_exception_closes_and_reraises(self, monkeypatch):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(stats_mod, "_get_db", lambda: mock_db)
        with pytest.raises(RuntimeError):
            stats_service.get_health_trend(days=7)
        mock_db.close.assert_called_once()
