"""
analytics_tasks.py 覆盖率补充测试 (54% → ≥70%)

覆盖此前未测的代码块:
- calculate_health_score_task (设备缺失 / 有遥测 / 无遥测 / 空 soc-temp / 严重告警)
- analyze_efficiency_task (device_ids+station_id 过滤 / 日期区间 / 无设备 / 无遥测)
- batch_health_report_task (空设备正常返回 / 非空批量计算健康度)
- aggregate_revenue_daily_task / aggregate_station_daily_metrics_task
  (单日 / 区间 / 非法日期空列表 / 异常重试路径)

调用约定:
  celery shared_task(bind=True) 的 `.__wrapped__` 是已绑定 self 的 bound method,
  须取 `.__wrapped__.__func__` 拿到裸函数 `(self, ...)` 再注入 _FakeTaskSelf
  (提供 request.id + retry), 完全绕过 broker。统一走 _run_task helper。

模块级 SessionLocal 绑定坑:
  analytics_tasks 模块级 `from app.core.database import SessionLocal` 绑定到导入时
  的对象, 绕过 conftest 对 db_module.SessionLocal 的覆盖 → monkeypatch 模块属性。

源码 bug 修复覆盖 (卡片 199a84d0):
  Bug1: batch_health_report_task 内 `__wrapped__(<task proxy>, device.id, days=7)`
        给已绑定 method 多传首参 → TypeError(multiple values for 'days')。修复后
        非空分支正常返回健康度列表 (见 test_with_devices_returns_health_scores)。
  Bug2: 任务引用幻影列 t.temperature / t.active_power → AttributeError。已改用
        真实列 ambient_temperature (温度评分) / charger_power (能耗聚合), 正向
        断言见该二用例。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.tasks import analytics_tasks as tasks_mod
from app.tasks.analytics_tasks import (
    build_revenue_daily,
    build_station_daily_metrics,
    calculate_health_score_task,
    analyze_efficiency_task,
    batch_health_report_task,
    aggregate_revenue_daily_task,
    aggregate_station_daily_metrics_task,
)
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.telemetry import Telemetry
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.analytics import AnalyticsResult
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.spec_tables import RevenueDaily, StationDailyMetric

# 复用兄弟测试的订单/充电桩构造器, 保证字段口径一致
from tests.test_analytics_aggregation import _order, _charger


# ═══════════════════════════════════════════════════════════════════
# 辅助: 模拟 celery bind=True 任务的 self + 裸函数调用
# ═══════════════════════════════════════════════════════════════════

class _FakeTaskSelf:
    """提供 request.id 供任务返回体引用; retry() 记录调用并重抛异常便于断言。"""

    def __init__(self, task_id="test-task-id-001"):
        self.request = type("_Req", (), {"id": task_id})()
        self.retried = []

    def retry(self, exc=None, **kwargs):
        self.retried.append(exc)
        raise exc


def _run_task(task, fake_self, *args, **kwargs):
    """调用 celery bind=True 任务的裸函数, 注入 FakeSelf 作 self。

    `task.__wrapped__` 是已绑定 self 的 method, 直接传 FakeSelf 会被当作首个
    业务参数; 取 `.__func__` 才能重绑 self。
    """
    return task.__wrapped__.__func__(fake_self, *args, **kwargs)


@pytest.fixture
def patched_db(test_db, monkeypatch):
    """注入测试库到 analytics_tasks 模块 + 开 WAL 防嵌套写锁。"""
    # 1) 模块级 SessionLocal 绑定坑: 显式 patch 模块属性
    monkeypatch.setattr(tasks_mod, "SessionLocal", test_db["SessionLocal"])
    # 2) batch 非空时 S1 读事务未提交期间内层任务写 S2 → 开 WAL 规避 "database is locked"
    with test_db["engine"].connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    return test_db


# 种子构造器
def _dev(db, did, station_id=1, status=DeviceStatus.ONLINE, dtype=DeviceType.CHARGER_DC):
    d = Device(
        id=did, sn=f"SN-AT-{did}", name=f"设备{did}", code=f"AT{did}",
        type=dtype, status=status, station_id=station_id,
    )
    db.add(d)
    return d


def _tele(db, did, ts, soc=None, temp=None, power=None, kwh=None, grid=None):
    t = Telemetry(
        device_id=did, timestamp=ts, battery_soc=soc,
        ambient_temperature=temp, charger_power=power,
        charger_kwh=kwh, grid_power_total=grid,
    )
    db.add(t)
    return t


def _alarm(db, did, level=AlarmLevel.WARNING, created_at=None):
    a = Alarm(
        device_id=did, alarm_type="test", level=level, content="x",
        status=AlarmStatus.ACTIVE, created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(a)
    return a


def _fresh_read(test_db):
    """新开 session 读任务提交的写入 (避开测试 session 的快照)。"""
    return test_db["SessionLocal"]()


# ═══════════════════════════════════════════════════════════════════
# calculate_health_score_task
# ═══════════════════════════════════════════════════════════════════

class TestCalculateHealthScore:

    def test_device_not_found_raises(self, patched_db):
        patched_db["session"].commit()
        with pytest.raises(ValueError, match="不存在"):
            _run_task(calculate_health_score_task, _FakeTaskSelf(), 9999, days=7)

    def test_with_telemetry_and_alarms(self, patched_db):
        db = patched_db["session"]
        _dev(db, 5001)
        now = datetime.now(timezone.utc)
        _tele(db, 5001, now - timedelta(hours=2), soc=80, temp=25, power=5)
        _tele(db, 5001, now - timedelta(hours=1), soc=60, temp=35, power=3)
        _alarm(db, 5001, level=AlarmLevel.WARNING, created_at=now - timedelta(hours=3))
        _alarm(db, 5001, level=AlarmLevel.CRITICAL, created_at=now - timedelta(hours=2))
        db.commit()

        result = _run_task(calculate_health_score_task, _FakeTaskSelf("hs-001"), 5001, days=7)

        assert result["status"] == "completed"
        assert result["device_id"] == 5001
        assert result["task_id"] == "hs-001"
        # soc avg=70 → min(100, 70*1.2)=84 ; temp avg=30 → 100-|5|*3=85
        # alarm: 2 条含 1 critical → 100-10-15=75 ; 总均 (84+85+75)/3 ≈ 81.3 → low
        assert result["overall_score"] == 81.3
        assert result["risk_level"] == "low"

        s = _fresh_read(patched_db)
        try:
            ar = s.query(AnalyticsResult).filter_by(
                device_id=5001, analysis_type="health_score").one()
            assert ar.confidence == 0.85
            assert ar.result_json["risk_level"] == "low"
            assert ar.result_json["alarm_count"] == 2
            assert ar.result_json["data_points"] == 2
        finally:
            s.close()

    def test_no_telemetry_low_confidence(self, patched_db):
        db = patched_db["session"]
        _dev(db, 5002)
        db.commit()

        result = _run_task(calculate_health_score_task, _FakeTaskSelf(), 5002, days=7)
        # battery=50, temperature=50 (无遥测 else 分支), alarm=100 → 均 66.7 → medium
        assert result["overall_score"] == 66.7
        assert result["risk_level"] == "medium"

        s = _fresh_read(patched_db)
        try:
            ar = s.query(AnalyticsResult).filter_by(device_id=5002).one()
            assert ar.confidence == 0.3
            assert ar.result_json["data_points"] == 0
        finally:
            s.close()

    def test_telemetry_null_soc_and_temp(self, patched_db):
        db = patched_db["session"]
        _dev(db, 5003)
        _tele(db, 5003, datetime.now(timezone.utc) - timedelta(hours=1), soc=None, temp=None, power=None)
        db.commit()

        result = _run_task(calculate_health_score_task, _FakeTaskSelf(), 5003, days=7)
        # soc_values 空 → battery=70 ; temps 空 → temperature=70 ; alarm=100 → 80.0 → low
        assert result["overall_score"] == 80.0
        assert result["risk_level"] == "low"

    def test_many_critical_alarms_critical_risk(self, patched_db):
        db = patched_db["session"]
        _dev(db, 5004)
        now = datetime.now(timezone.utc)
        _tele(db, 5004, now - timedelta(hours=1), soc=30, temp=80)  # 偏离 25℃ 较远
        for _ in range(5):
            _alarm(db, 5004, level=AlarmLevel.CRITICAL, created_at=now - timedelta(hours=1))
        db.commit()

        result = _run_task(calculate_health_score_task, _FakeTaskSelf(), 5004, days=7)
        # battery=min(100,36)=36 ; temp=max(0,100-55*3)=0 ; alarm=max(0,100-25-75)=0
        # → 12.0 → critical; 覆盖 max(0,..) 钳位与 critical 分支
        assert result["risk_level"] == "critical"
        assert result["overall_score"] < 40


# ═══════════════════════════════════════════════════════════════════
# analyze_efficiency_task
# ═══════════════════════════════════════════════════════════════════

class TestAnalyzeEfficiency:

    def test_basic_with_telemetry(self, patched_db):
        """能耗=charger_kwh 差值累计; 充电桩效率=avg(charger_power)/avg(grid_power_total)。"""
        db = patched_db["session"]
        _dev(db, 6001)
        _dev(db, 6002)
        now = datetime.now(timezone.utc)
        # 6001: kwh 10→40 (energy=30) ; power/grid 8/10 → eff 80.0
        _tele(db, 6001, now - timedelta(hours=2), power=8, kwh=10, grid=10)
        _tele(db, 6001, now - timedelta(hours=1), power=8, kwh=40, grid=10)
        # 6002: kwh 3→5 (energy=2) ; power/grid 5/5 → eff 100.0
        _tele(db, 6002, now - timedelta(hours=2), power=5, kwh=3, grid=5)
        _tele(db, 6002, now - timedelta(hours=1), power=5, kwh=5, grid=5)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf("eff-1"),
                           device_ids=[6001, 6002])

        assert result["status"] == "completed"
        assert result["total_devices"] == 2
        assert result["task_id"] == "eff-1"
        assert result["total_energy_kwh"] == 32.0   # 30 + 2

        bd = {b["device_id"]: b for b in result["breakdown"]}
        assert bd[6001]["energy_kwh"] == 30.0
        assert bd[6001]["efficiency"] == 80.0       # avg(8)/avg(10)*100
        assert bd[6002]["energy_kwh"] == 2.0
        assert bd[6002]["efficiency"] == 100.0
        assert result["avg_efficiency"] == 90.0     # (80+100)/2

        s = _fresh_read(patched_db)
        try:
            rows = s.query(AnalyticsResult).filter_by(analysis_type="efficiency").all()
            assert len(rows) == 2
            assert all(r.confidence == 0.8 for r in rows)
        finally:
            s.close()

    def test_station_filter_and_date_range(self, patched_db):
        db = patched_db["session"]
        _dev(db, 6101, station_id=7)
        _dev(db, 6102, station_id=8)
        start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        _tele(db, 6101, datetime.now(timezone.utc) - timedelta(hours=1), power=8, kwh=0, grid=10)
        _tele(db, 6101, datetime.now(timezone.utc), power=8, kwh=8, grid=10)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(),
                           station_id=7, start_date=start, end_date=end)

        assert result["total_devices"] == 1
        assert result["breakdown"][0]["device_id"] == 6101
        assert result["breakdown"][0]["energy_kwh"] == 8.0

    def test_no_matching_devices_raises(self, patched_db):
        db = patched_db["session"]
        _dev(db, 6201, station_id=99)
        db.commit()
        with pytest.raises(ValueError, match="未找到匹配的设备"):
            _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[9999])

    def test_no_telemetry_low_confidence(self, patched_db):
        db = patched_db["session"]
        _dev(db, 6301)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[6301])
        assert result["total_energy_kwh"] == 0.0
        # 无遥测: 同步端点口径, 充电桩缺功率对 → 默认效率 88.0 (不再是假值 75.0)
        assert result["breakdown"][0]["efficiency"] == 88.0

        s = _fresh_read(patched_db)
        try:
            ar = s.query(AnalyticsResult).filter_by(
                device_id=6301, analysis_type="efficiency").one()
            assert ar.confidence == 0.2
            assert ar.result_json["data_points"] == 0
        finally:
            s.close()

    def test_energy_prefers_charger_kwh_cumulative(self, patched_db):
        """能耗读累计列 charger_kwh (末值-首值), 不再把瞬时 charger_power 当 kWh 累加。"""
        db = patched_db["session"]
        _dev(db, 6401)
        now = datetime.now(timezone.utc)
        _tele(db, 6401, now - timedelta(hours=1), power=15, kwh=100)
        _tele(db, 6401, now, power=5, kwh=120)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[6401])
        assert result["breakdown"][0]["energy_kwh"] == 20.0   # 120 - 100
        # 效率 = avg(15,5)/avg(grid None 不参与) — grid 全空 → 默认 88.0
        assert result["breakdown"][0]["efficiency"] == 88.0

    def test_energy_fallback_grid_power_total_without_kwh(self, patched_db):
        """无 charger_kwh 时回退 grid_power_total 折算 (同步端点 avg_power×hours 口径)。"""
        db = patched_db["session"]
        _dev(db, 6451)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=2)
        _tele(db, 6451, start, grid=10)
        _tele(db, 6451, now, grid=10)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(),
                           device_ids=[6451], start_date=start.isoformat(),
                           end_date=now.isoformat())
        # avg(10 kW) × 2h = 20 kWh
        assert result["breakdown"][0]["energy_kwh"] == 20.0

    def test_inverter_efficiency_dispatch(self, patched_db):
        """逆变器: eff = avg(inv_power_a)/avg(grid_power_total)×100。"""
        db = patched_db["session"]
        _dev(db, 6461, dtype=DeviceType.PV_INVERTER)
        now = datetime.now(timezone.utc)
        for i in range(3):
            t = Telemetry(device_id=6461, timestamp=now - timedelta(hours=3 - i),
                          grid_power_total=10, inv_power_a=9)
            db.add(t)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[6461])
        assert result["breakdown"][0]["efficiency"] == 90.0

    def test_battery_efficiency_dispatch(self, patched_db):
        """电池: SOC 变化稳定 → 高分; 依据 SOC 序列标准差。"""
        db = patched_db["session"]
        _dev(db, 6471, dtype=DeviceType.BATTERY)
        now = datetime.now(timezone.utc)
        for i, soc in enumerate([50.0, 50.2, 50.4, 50.6]):
            _tele(db, 6471, now - timedelta(hours=4 - i), soc=soc)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[6471])
        # soc 变化均 0.2(>0.1 阈值), std=0 → 100.0
        assert result["breakdown"][0]["efficiency"] == 100.0

    def test_general_efficiency_dispatch(self, patched_db):
        """未知/其它类型走通用算法: 功率因数+温度。"""
        db = patched_db["session"]
        _dev(db, 6481, dtype=DeviceType.METER)
        now = datetime.now(timezone.utc)
        for i in range(3):
            t = Telemetry(device_id=6481, timestamp=now - timedelta(hours=3 - i),
                          grid_power_factor=0.9, battery_temperature=25.0)
            db.add(t)
        db.commit()

        result = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[6481])
        # pf_score=90 (0.9*100), temp_std=0 → temp_score=100 → 0.6*90+0.4*100=94.0
        assert result["breakdown"][0]["efficiency"] == 94.0


# ═══════════════════════════════════════════════════════════════════
# batch_health_report_task
# ═══════════════════════════════════════════════════════════════════

class TestBatchHealthReport:

    def test_empty_devices_returns_clean(self, patched_db):
        patched_db["session"].commit()
        result = _run_task(batch_health_report_task, _FakeTaskSelf())
        assert result["status"] == "completed"
        assert result["total_devices"] == 0
        assert result["results"] == []

    def test_with_devices_returns_health_scores(self, patched_db):
        """非空设备时, batch 对每设备复用健康度计算并聚合返回。
        联动覆盖 Bug1 + Bug2 修复: 内层 __wrapped__(device.id, days=7) 不再 TypeError;
        health score 温度分读真实列 ambient_temperature 正常产出。"""
        db = patched_db["session"]
        _dev(db, 7001)
        _tele(db, 7001, datetime.now(timezone.utc) - timedelta(hours=1), soc=90, temp=25)
        db.commit()

        result = _run_task(batch_health_report_task, _FakeTaskSelf("batch-1"))

        assert result["status"] == "completed"
        assert result["total_devices"] == 1
        assert len(result["results"]) == 1
        # soc=90 → min(100, 90*1.2)=100; ambient_temperature=25 → 100-|0|*3=100;
        # 0 告警 → 100; 均 100.0 → low
        score = result["results"][0]
        assert score["device_id"] == 7001
        assert score["overall_score"] == 100.0
        assert score["risk_level"] == "low"

    def test_station_filter_yields_empty(self, patched_db):
        """传 station_id 过滤但无匹配设备 → devices 空 → 干净返回 (覆盖 station_id 过滤分支)。"""
        db = patched_db["session"]
        _dev(db, 7002, station_id=1)   # 站 1
        db.commit()
        result = _run_task(batch_health_report_task, _FakeTaskSelf(), station_id=999)
        assert result["status"] == "completed"
        assert result["total_devices"] == 0
        assert result["results"] == []


# ═══════════════════════════════════════════════════════════════════
# build_station_daily_metrics 非法日期 error 分支 (line 442)
# ═══════════════════════════════════════════════════════════════════

class TestBuildStationDailyMetricsBadDate:

    def test_bad_date_returns_error(self, patched_db):
        from app.tasks.analytics_tasks import build_station_daily_metrics
        patched_db["session"].commit()
        result = build_station_daily_metrics(patched_db["session"], "not-a-date")
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════════
# aggregate_revenue_daily_task
# ═══════════════════════════════════════════════════════════════════

class TestAggregateRevenueDaily:

    def test_single_date(self, patched_db):
        db = patched_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0),
                      total=60, paid=55, user_id=101))
        db.commit()

        result = _run_task(aggregate_revenue_daily_task, _FakeTaskSelf("agg-rev-1"),
                           target_date="2026-07-15")

        assert isinstance(result, list) and len(result) == 1
        assert result[0]["status"] == "completed"
        assert result[0]["orders"] == 1

        s = _fresh_read(patched_db)
        try:
            assert s.query(RevenueDaily).filter_by(
                record_date=datetime(2026, 7, 15)).count() == 1
        finally:
            s.close()

    def test_range_backfill(self, patched_db):
        db = patched_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 14, 10, 0),
                      total=40, paid=40, user_id=1))
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0),
                      total=60, paid=60, user_id=2))
        db.commit()

        result = _run_task(aggregate_revenue_daily_task, _FakeTaskSelf(),
                           target_date="2026-07-14", end_date="2026-07-15")

        assert len(result) == 2
        s = _fresh_read(patched_db)
        try:
            assert s.query(RevenueDaily).count() == 2
        finally:
            s.close()

    def test_bad_date_returns_empty(self, patched_db):
        patched_db["session"].commit()
        result = _run_task(aggregate_revenue_daily_task, _FakeTaskSelf(),
                           target_date="bad")
        assert result == []

    def test_retry_on_error(self, patched_db, monkeypatch):
        def _boom(db, d):
            raise RuntimeError("db down")
        monkeypatch.setattr(tasks_mod, "build_revenue_daily", _boom)

        fake = _FakeTaskSelf()
        with pytest.raises(RuntimeError, match="db down"):
            _run_task(aggregate_revenue_daily_task, fake, target_date="2026-07-15")
        assert fake.retried and isinstance(fake.retried[0], RuntimeError)


# ═══════════════════════════════════════════════════════════════════
# aggregate_station_daily_metrics_task
# ═══════════════════════════════════════════════════════════════════

class TestAggregateStationDailyMetrics:

    def test_single_date(self, patched_db):
        db = patched_db["session"]
        db.add(_charger(8001, 1, DeviceStatus.ONLINE, guns=1))
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0),
                      total=50, paid=50, kwh=25, duration=120, user_id=801, order_no="AS-1"))
        db.commit()

        result = _run_task(aggregate_station_daily_metrics_task, _FakeTaskSelf(),
                           target_date="2026-07-15")

        assert len(result) == 1
        assert result[0]["stations"] == 1

        s = _fresh_read(patched_db)
        try:
            m = s.query(StationDailyMetric).filter_by(station_id=1).one()
            assert m.orders_count == 1
            assert m.online_devices == 1
        finally:
            s.close()

    def test_bad_date_returns_empty(self, patched_db):
        patched_db["session"].commit()
        result = _run_task(aggregate_station_daily_metrics_task, _FakeTaskSelf(),
                           target_date="bad")
        assert result == []

    def test_retry_on_error(self, patched_db, monkeypatch):
        def _boom(db, d):
            raise RuntimeError("station build down")
        monkeypatch.setattr(tasks_mod, "build_station_daily_metrics", _boom)

        fake = _FakeTaskSelf()
        with pytest.raises(RuntimeError, match="station build down"):
            _run_task(aggregate_station_daily_metrics_task, fake, target_date="2026-07-15")
        assert fake.retried and isinstance(fake.retried[0], RuntimeError)


# ═══════════════════════════════════════════════════════════════════
# 业务时区 wiring (卡 c42ac99a)
# ═══════════════════════════════════════════════════════════════════

class TestBizTzDefaults:
    """_iter_target_dates 默认取业务时区昨日; analyze_efficiency naive 输入不崩。

    - _iter_target_dates 无参 → 起始=业务时区昨日 (旧 date.today()-1d 在 UTC 容器错算前天)
    - analyze_efficiency_task: 仅传 start_date (naive) 不再与 aware 默认 end 比较抛 TypeError
    时区逻辑本身见 test_tasks_tz_utils.py。
    """

    def test_iter_default_start_is_biz_yesterday(self, monkeypatch):
        from datetime import date as _date
        from app.tasks.analytics_tasks import _iter_target_dates

        monkeypatch.setattr(tasks_mod, "yesterday_in_biz_tz", lambda: _date(2026, 8, 6))
        assert _iter_target_dates(None, None) == ["2026-08-06"]

    def test_iter_explicit_target_not_overridden(self, monkeypatch):
        from app.tasks.analytics_tasks import _iter_target_dates

        monkeypatch.setattr(tasks_mod, "yesterday_in_biz_tz", lambda: _date(2026, 8, 6))
        # 显式 target_date/end_date 走入参解析, 不触默认
        assert _iter_target_dates("2026-01-15", "2026-01-16") == ["2026-01-15", "2026-01-16"]

    def test_aggregate_revenue_daily_default_uses_helper(self, patched_db, monkeypatch):
        """无参 aggregate_revenue_daily_task → 走业务时区昨日 (复用 _order 种子)。"""
        from datetime import date as _date

        db = patched_db["session"]
        monkeypatch.setattr(tasks_mod, "yesterday_in_biz_tz", lambda: _date(2026, 8, 6))
        db.add(_order(1, UserType.APP, datetime(2026, 8, 6, 10, 0),
                      total=60, paid=60, user_id=901, order_no="TZ-1"))
        db.commit()

        result = _run_task(aggregate_revenue_daily_task, _FakeTaskSelf())

        assert len(result) == 1
        assert result[0]["date"] == "2026-08-06"
        assert result[0]["orders"] == 1

    def test_efficiency_naive_start_date_no_crash(self, patched_db):
        """仅传 naive start_date (无 end_date) 不再抛 naive/aware TypeError。

        旧实现: start=datetime.fromisoformat(串) (naive) vs end=datetime.now(utc) (aware)
        → start<=timestamp<=end 直接 TypeError 崩任务。修复后 naive 按业务时区解释成 aware。
        """
        db = patched_db["session"]
        _dev(db, 6501)
        now = datetime.now(timezone.utc)
        _tele(db, 6501, now - timedelta(hours=1), grid=12)
        db.commit()

        # 仅传 naive start_date, end_date 缺省走 aware now —— 旧实现此处崩
        result = _run_task(
            analyze_efficiency_task, _FakeTaskSelf(),
            device_ids=[6501],
            start_date=(now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        assert result["status"] == "completed"
        # grid 回退口径: avg(12kW)×时长(>0) > 0, 具体数值随时长变; 只锚定口径有效
        assert result["breakdown"][0]["energy_kwh"] > 0

    def test_efficiency_naive_start_and_end_comparable(self, patched_db):
        """naive start+end 都传 → 均按业务时区解释成 aware, 互相可比不崩。"""
        db = patched_db["session"]
        _dev(db, 6601)
        now = datetime.now(timezone.utc)
        _tele(db, 6601, now - timedelta(hours=1), grid=9)
        db.commit()

        result = _run_task(
            analyze_efficiency_task, _FakeTaskSelf(),
            device_ids=[6601],
            start_date=(now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            end_date=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        assert result["status"] == "completed"
        # grid 回退口径: avg(9kW)×48h ≈ 432, 锚定口径而非旧 power 累加假值
        assert result["breakdown"][0]["energy_kwh"] == pytest.approx(432.0, abs=1.0)


# ═══════════════════════════════════════════════════════════════════
# 卡 77184280: analytics_results 唯一约束 + 任务写入幂等
# ═══════════════════════════════════════════════════════════════════
# calculate_health_score_task / analyze_efficiency_task 每次运行/重试
# 直接 INSERT 新行 → 重试即表膨胀。修复: (device_id, analysis_type)
# 唯一约束 uq_ar_device_type + 写入改 check-then-upsert (撞约束 rollback
# 后重跑转纯覆盖), 对齐 settlement/_fetch_existing 范式 (卡 97c83af9)。

from sqlalchemy.exc import IntegrityError


def _table_unique_indexes(engine, table):
    """SQLite 表级 UniqueConstraint 生成匿名 autoindex, 用 PRAGMA 取唯一索引列集。"""
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA index_list({table})").fetchall()
        out = []
        for r in rows:
            if r[2]:
                cols = {c[2] for c in conn.exec_driver_sql(
                    f"PRAGMA index_info({r[1]})").fetchall()}
                out.append(cols)
        return out


class TestUniqueConstraintCard77184280:

    def test_analytics_results_unique_index_exists(self, test_db):
        uniques = _table_unique_indexes(test_db["engine"], "analytics_results")
        assert {"device_id", "analysis_type"} in uniques

    def test_duplicate_insert_rejected(self, test_db):
        db = test_db["session"]
        db.add(AnalyticsResult(device_id=1, analysis_type="health_score"))
        db.commit()
        db.add(AnalyticsResult(device_id=1, analysis_type="health_score"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        # 同设备不同 analysis_type 可共存
        db.add(AnalyticsResult(device_id=1, analysis_type="efficiency"))
        db.commit()
        assert db.query(AnalyticsResult).filter_by(device_id=1).count() == 2


class TestHealthScoreIdempotencyCard77184280:

    def test_rerun_updates_single_row(self, patched_db):
        """同设备同 type 二次运行不新增行, 字段/generated_at 被覆盖更新。"""
        db = patched_db["session"]
        _dev(db, 5101)
        now = datetime.now(timezone.utc)
        _tele(db, 5101, now - timedelta(hours=1), soc=80, temp=25)
        db.commit()

        r1 = _run_task(calculate_health_score_task, _FakeTaskSelf(), 5101, days=7)
        # battery=min(100,96)=96, temp=100, alarm=100 → 98.7
        assert r1["overall_score"] == 98.7

        # 固定旧 generated_at, 便于断言更新路径刷新了它
        s0 = _fresh_read(patched_db)
        s0.query(AnalyticsResult).filter_by(
            device_id=5101, analysis_type="health_score"
        ).update({"generated_at": datetime(2020, 1, 1)})
        s0.commit()
        s0.close()

        # 二次运行 (重试/重投递): 新增 1 条 critical 告警改变评分
        _alarm(db, 5101, level=AlarmLevel.CRITICAL, created_at=now)
        db.commit()
        r2 = _run_task(calculate_health_score_task, _FakeTaskSelf(), 5101, days=7)
        # alarm=100-5-15=80 → (96+100+80)/3=92.0
        assert r2["overall_score"] == 92.0

        s = _fresh_read(patched_db)
        try:
            rows = s.query(AnalyticsResult).filter_by(
                device_id=5101, analysis_type="health_score").all()
            assert len(rows) == 1
            assert rows[0].result_json["alarm_count"] == 1
            assert rows[0].confidence == 0.85
            gen = rows[0].generated_at
            gen = gen if gen.tzinfo else gen.replace(tzinfo=timezone.utc)
            assert gen > datetime(2020, 1, 1, tzinfo=timezone.utc)
        finally:
            s.close()

    def test_race_integrity_fallback_overwrites(self, patched_db, monkeypatch):
        """check-then-act 竞态: 首查 miss → INSERT 撞约束 → rollback 回查转覆盖。"""
        db = patched_db["session"]
        _dev(db, 5102)
        # 并发对手已落同键行 (含陈旧值)
        db.add(AnalyticsResult(device_id=5102, analysis_type="health_score",
                               result_json={"stale": True}, confidence=0.1))
        db.commit()

        real_fetch = tasks_mod._fetch_existing_analytics
        calls = {"n": 0}

        def _miss_first(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return real_fetch(*args, **kwargs)

        monkeypatch.setattr(tasks_mod, "_fetch_existing_analytics", _miss_first)

        result = _run_task(calculate_health_score_task, _FakeTaskSelf(), 5102, days=7)
        assert result["status"] == "completed"
        assert calls["n"] >= 2

        s = _fresh_read(patched_db)
        try:
            rows = s.query(AnalyticsResult).filter_by(device_id=5102).all()
            assert len(rows) == 1
            assert rows[0].result_json.get("stale") is None
            # 无遥测 → confidence 0.3, 覆盖了竞态行的 0.1
            assert rows[0].confidence == 0.3
        finally:
            s.close()


class TestEfficiencyIdempotencyCard77184280:

    def test_rerun_updates_single_row(self, patched_db):
        db = patched_db["session"]
        _dev(db, 5201)
        now = datetime.now(timezone.utc)
        _tele(db, 5201, now - timedelta(hours=2), power=8, kwh=10, grid=10)
        _tele(db, 5201, now - timedelta(hours=1), power=8, kwh=30, grid=10)
        db.commit()

        r1 = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[5201])
        assert r1["breakdown"][0]["energy_kwh"] == 20.0

        # 二次运行: 累计表推进 kwh 30→50 (时间戳全在过去, 不落默认窗口外)
        _tele(db, 5201, now - timedelta(minutes=30), power=8, kwh=50, grid=10)
        db.commit()
        r2 = _run_task(analyze_efficiency_task, _FakeTaskSelf(), device_ids=[5201])
        assert r2["breakdown"][0]["energy_kwh"] == 40.0

        s = _fresh_read(patched_db)
        try:
            rows = s.query(AnalyticsResult).filter_by(
                device_id=5201, analysis_type="efficiency").all()
            assert len(rows) == 1
            assert rows[0].result_json["energy_kwh"] == 40.0
        finally:
            s.close()


# ═══════════════════════════════════════════════════════════════════
# 卡 9863018d: revenue_daily / station_daily_metrics 唯一约束 + 幂等兜底
# ═══════════════════════════════════════════════════════════════════
class TestUniqueConstraintsCard9863018d:
    """约束存在性 + 重复插入拒绝 + NULL 哨兵映射。"""

    def _unique_indexes(self, engine, table):
        """SQLite 表级 UniqueConstraint 生成匿名 sqlite_autoindex, 不进
        inspector.get_indexes; 用 PRAGMA index_list 取 origin='u' 的唯一索引。"""
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(f"PRAGMA index_list({table})").fetchall()
            out = []
            for r in rows:
                # (seq, name, unique, origin, partial)
                if r[2]:
                    cols = {c[2] for c in conn.exec_driver_sql(
                        f"PRAGMA index_info({r[1]})").fetchall()}
                    out.append(cols)
            return out

    def test_revenue_unique_index_exists(self, test_db):
        uniques = self._unique_indexes(test_db["engine"], "revenue_daily")
        assert {"record_date", "station_id", "user_type_key"} in uniques

    def test_station_metric_unique_index_exists(self, test_db):
        uniques = self._unique_indexes(test_db["engine"], "station_daily_metrics")
        assert {"station_id", "record_date"} in uniques

    def test_revenue_duplicate_insert_rejected(self, test_db):
        db = test_db["session"]
        marker = datetime(2026, 7, 15)
        db.add(RevenueDaily(record_date=marker, station_id=1, user_type="app"))
        db.commit()
        db.add(RevenueDaily(record_date=marker, station_id=1, user_type="app"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_station_metric_duplicate_insert_rejected(self, test_db):
        db = test_db["session"]
        marker = datetime(2026, 7, 15)
        db.add(StationDailyMetric(station_id=1, record_date=marker))
        db.commit()
        db.add(StationDailyMetric(station_id=1, record_date=marker))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_null_user_type_sentinel_mapping(self, test_db):
        """user_type NULL → user_type_key='' (before_insert 同步); 两条 NULL 行同键撞约束。"""
        db = test_db["session"]
        marker = datetime(2026, 7, 15)
        db.add(RevenueDaily(record_date=marker, station_id=2, user_type=None))
        db.commit()
        row = db.query(RevenueDaily).filter(RevenueDaily.station_id == 2).one()
        assert row.user_type is None and row.user_type_key == ""
        # 第二条同键 NULL 行被拒 → 历史/无类型订单不会重复
        db.add(RevenueDaily(record_date=marker, station_id=2, user_type=None))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        # 非 NULL 与 NULL 可共存 (不同哨兵键)
        db.add(RevenueDaily(record_date=marker, station_id=2, user_type="app"))
        db.commit()
        assert db.query(RevenueDaily).filter(RevenueDaily.station_id == 2).count() == 2


class TestBuildIdempotencyCard9863018d:
    """重跑/竞态兜底: 无重复行, 覆盖语义保持。"""

    def test_revenue_rerun_no_duplicates(self, test_db):
        db = test_db["session"]
        db.add(_order(11, UserType.APP, datetime(2026, 7, 15, 10), kwh=10, elec=5))
        db.commit()
        build_revenue_daily(db, "2026-07-15")
        db.commit()
        # 模拟并发重投递: 手动塞入一条竞态行后重跑 (若 add 撞约束走回退覆盖)
        build_revenue_daily(db, "2026-07-15")
        db.commit()
        rows = db.query(RevenueDaily).all()
        assert len(rows) == 1
        assert rows[0].orders_count == 1

    def test_revenue_integrity_fallback_overwrites(self, test_db):
        """预插竞态行 → build 撞约束回退覆盖语义, 不重插不重复。"""
        db = test_db["session"]
        db.add(_order(12, None, datetime(2026, 7, 15, 11), kwh=7, elec=3))
        db.commit()
        # 竞态对手已落同键行 (含 NULL user_type 哨兵键)
        db.add(RevenueDaily(record_date=datetime(2026, 7, 15), station_id=12,
                            user_type=None, paid_revenue=Decimal("999")))
        db.commit()

        result = build_revenue_daily(db, "2026-07-15")
        db.commit()
        assert result["status"] == "completed"
        rows = db.query(RevenueDaily).filter(RevenueDaily.station_id == 12).all()
        assert len(rows) == 1
        assert rows[0].paid_revenue == Decimal("3")

    def test_station_metric_rerun_no_duplicates(self, test_db):
        db = test_db["session"]
        db.add(_charger(1301, 13, DeviceStatus.ONLINE))
        db.add(_order(13, UserType.APP, datetime(2026, 7, 15, 12), kwh=5, elec=2))
        db.commit()
        build_station_daily_metrics(db, "2026-07-15")
        db.commit()
        build_station_daily_metrics(db, "2026-07-15")
        db.commit()
        rows = db.query(StationDailyMetric).all()
        assert len(rows) == 1
        assert rows[0].orders_count == 1
