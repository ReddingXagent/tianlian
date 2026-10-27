"""
运营日报聚合定时任务测试

覆盖:
- build_revenue_daily / build_station_daily_metrics 聚合正确性、幂等、退款归属、日期过滤
- _iter_target_dates 区间补算解析
- revenue_stats API 预聚合表优先读取 + 手动触发补算端点
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.tasks.analytics_tasks import (
    build_revenue_daily,
    build_station_daily_metrics,
    _iter_target_dates,
)
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.charging_queue import ChargingQueue
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.models.spec_tables import RevenueDaily, StationDailyMetric


# ═══════════════════════════════════════════════════════════════════
# 辅助构造
# ═══════════════════════════════════════════════════════════════════

def _order(station_id, user_type, end_dt, kwh=0, elec=0, service=0, parking=0,
           occupancy=0, reservation=0, total=None, paid=None, duration=0,
           user_id=None, status=OrderStatus.COMPLETED, order_no=None):
    if total is None:
        total = Decimal(str(elec)) + Decimal(str(service)) + Decimal(str(parking)) \
            + Decimal(str(occupancy)) + Decimal(str(reservation))
    if paid is None:
        paid = total
    return ChargingOrder(
        order_no=order_no or f"AGG-{station_id}-{end_dt.strftime('%Y%m%d%H%M')}-{user_type}",
        station_id=station_id, device_id=station_id * 100, user_id=user_id, user_type=user_type,
        charged_kwh=Decimal(str(kwh)), electricity_fee=Decimal(str(elec)),
        service_fee=Decimal(str(service)), parking_fee=Decimal(str(parking)),
        occupancy_fee=Decimal(str(occupancy)), reservation_fee=Decimal(str(reservation)),
        total_amount=Decimal(str(total)), paid_amount=Decimal(str(paid)),
        duration_minutes=duration, end_time=end_dt, order_status=status,
        payment_status=OrderPaymentStatus.PAID, payment_method=PaymentMethod.WECHAT,
    )


# ═══════════════════════════════════════════════════════════════════
# build_revenue_daily
# ═══════════════════════════════════════════════════════════════════

class TestBuildRevenueDaily:

    def test_aggregates_by_station_and_user_type(self, test_db):
        db = test_db["session"]
        d = datetime(2026, 7, 15, 10, 0)
        db.add_all([
            _order(1, UserType.APP, d, kwh=50, elec=40, service=10, parking=5,
                   occupancy=3, reservation=2, total=60, paid=55, user_id=101),
            _order(1, UserType.CARD, datetime(2026, 7, 15, 12, 0), kwh=20, elec=16,
                   service=4, total=20, paid=20, user_id=102),
            _order(2, UserType.APP, datetime(2026, 7, 15, 14, 0), kwh=10, elec=8,
                   service=2, total=10, paid=10, user_id=103),
        ])
        db.flush()

        result = build_revenue_daily(db, "2026-07-15")

        assert result["status"] == "completed"
        assert result["groups"] == 3
        assert result["orders"] == 3

        rows = db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).all()
        assert len(rows) == 3

        s1_app = next(r for r in rows if r.station_id == 1 and r.user_type == "app")
        assert s1_app.orders_count == 1
        assert float(s1_app.energy_kwh) == 50.0
        assert float(s1_app.charge_fee) == 40.0
        assert float(s1_app.service_fee) == 10.0
        assert float(s1_app.parking_fee) == 5.0
        assert float(s1_app.occupancy_fee) == 3.0
        assert float(s1_app.reservation_fee) == 2.0
        assert float(s1_app.total_revenue) == 60.0
        assert float(s1_app.paid_revenue) == 55.0

    def test_refund_attributed_via_order_join(self, test_db):
        """退款按 refund_records.refunded_at 当日, 经订单回溯 station/user_type 归属。"""
        db = test_db["session"]
        app_order = _order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=55)
        db.add_all([
            app_order,
            _order(1, UserType.CARD, datetime(2026, 7, 15, 12, 0), total=20, paid=20),
        ])
        db.flush()
        db.add(RefundRecord(
            order_id=app_order.id, user_id=101, refund_amount=Decimal("5.00"),
            reason="测试退款", status=RefundStatus.REFUNDED,
            # 16:00 UTC = 上海次日 00:00 → 旧窗口错归次日; 改 14:00 (上海 22:00 同业务日, 卡 f7422bbc)
            refunded_at=datetime(2026, 7, 15, 14, 0),
        ))
        db.flush()

        build_revenue_daily(db, "2026-07-15")

        s1_app = db.query(RevenueDaily).filter(
            RevenueDaily.station_id == 1, RevenueDaily.user_type == "app",
            RevenueDaily.record_date == datetime(2026, 7, 15),
        ).one()
        s1_card = db.query(RevenueDaily).filter(
            RevenueDaily.station_id == 1, RevenueDaily.user_type == "card",
            RevenueDaily.record_date == datetime(2026, 7, 15),
        ).one()
        assert float(s1_app.refund_amount) == 5.0
        assert float(s1_card.refund_amount) == 0.0

    def test_refund_excluded_when_refunded_other_day(self, test_db):
        db = test_db["session"]
        app_order = _order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=55)
        db.add(app_order)
        db.flush()
        db.add(RefundRecord(
            order_id=app_order.id, refund_amount=Decimal("5.00"), reason="x",
            status=RefundStatus.REFUNDED, refunded_at=datetime(2026, 7, 16, 10, 0),
        ))
        db.flush()

        build_revenue_daily(db, "2026-07-15")
        s1_app = db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).one()
        assert float(s1_app.refund_amount) == 0.0

    def test_idempotent_rerun(self, test_db):
        db = test_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=55))
        db.flush()

        build_revenue_daily(db, "2026-07-15")
        build_revenue_daily(db, "2026-07-15")

        rows = db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).all()
        assert len(rows) == 1
        assert rows[0].orders_count == 1

    def test_rerun_after_change_overwrites(self, test_db):
        """补算覆盖: 数据变化后重跑, 数值更新而非累加。"""
        db = test_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=55))
        db.flush()
        build_revenue_daily(db, "2026-07-15")

        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 11, 0), total=40, paid=40))
        db.flush()
        build_revenue_daily(db, "2026-07-15")

        rows = db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).all()
        assert len(rows) == 1
        assert rows[0].orders_count == 2
        assert float(rows[0].total_revenue) == 100.0

    def test_excludes_other_dates(self, test_db):
        db = test_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 14, 10, 0), total=60, paid=55))
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=40, paid=40))
        db.flush()

        result = build_revenue_daily(db, "2026-07-15")
        assert result["orders"] == 1
        row = db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).one()
        assert float(row.total_revenue) == 40.0

    def test_excludes_non_completed(self, test_db):
        db = test_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=55,
                      status=OrderStatus.CHARGING))
        db.flush()
        result = build_revenue_daily(db, "2026-07-15")
        assert result["orders"] == 0
        assert db.query(RevenueDaily).count() == 0

    def test_no_orders_cleans_stale_rows(self, test_db):
        """当日无订单时清理可能的历史残留行, 保证幂等。"""
        db = test_db["session"]
        db.add(RevenueDaily(record_date=datetime(2026, 7, 15), station_id=1,
                            user_type="app", orders_count=5))
        db.flush()
        result = build_revenue_daily(db, "2026-07-15")
        assert result["orders"] == 0
        assert db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).count() == 0

    def test_null_user_type_groups_to_none(self, test_db):
        db = test_db["session"]
        db.add(_order(1, None, datetime(2026, 7, 15, 10, 0), total=30, paid=30))
        db.flush()
        build_revenue_daily(db, "2026-07-15")
        row = db.query(RevenueDaily).filter(
            RevenueDaily.record_date == datetime(2026, 7, 15)
        ).one()
        assert row.user_type is None
        assert row.orders_count == 1

    def test_bad_date_returns_error(self, test_db):
        db = test_db["session"]
        result = build_revenue_daily(db, "not-a-date")
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════════
# build_station_daily_metrics
# ═══════════════════════════════════════════════════════════════════

def _charger(device_id, station_id, status, guns=1):
    return Device(
        id=device_id, sn=f"SN-AGG-{device_id}", name=f"桩#{device_id}",
        code=f"CHG{device_id}", type=DeviceType.CHARGER_DC, status=status,
        station_id=station_id, gun_count=guns,
    )


class TestBuildStationDailyMetrics:

    def _seed_station1(self, db):
        """站1: 2 枪(1在线+1充电中)；2 单(用户101复充/102新)；历史单使101非新增。"""
        db.add_all([
            _charger(1001, 1, DeviceStatus.ONLINE, guns=1),
            _charger(1002, 1, DeviceStatus.CHARGING, guns=1),
        ])
        db.add_all([
            _order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=50, paid=50,
                   kwh=30, duration=144, user_id=101, order_no="S1-A"),
            _order(1, UserType.APP, datetime(2026, 7, 15, 12, 0), total=100, paid=100,
                   kwh=60, duration=288, user_id=102, order_no="S1-B"),
            # 历史单: 用户101 在 07-10 已在该站充电 → 07-15 非新增
            _order(1, UserType.APP, datetime(2026, 7, 10, 10, 0), total=20, paid=20,
                   kwh=10, duration=60, user_id=101, order_no="S1-PRIOR"),
        ])
        db.add_all([
            ChargingQueue(station_id=1, vehicle_id=1, arrival_time=datetime(2026, 7, 15, 9, 0),
                          estimated_wait_minutes=10, status="completed"),
            ChargingQueue(station_id=1, vehicle_id=2, arrival_time=datetime(2026, 7, 15, 9, 30),
                          estimated_wait_minutes=20, status="completed"),
        ])
        db.flush()

    def test_core_metrics(self, test_db):
        db = test_db["session"]
        self._seed_station1(db)

        result = build_station_daily_metrics(db, "2026-07-15")
        assert result["status"] == "completed"
        assert result["stations"] == 1

        m = db.query(StationDailyMetric).filter(
            StationDailyMetric.station_id == 1,
            StationDailyMetric.record_date == datetime(2026, 7, 15),
        ).one()
        assert m.orders_count == 2
        assert float(m.energy_kwh) == 90.0
        assert float(m.revenue) == 150.0
        assert m.active_users == 2
        assert m.new_users == 1              # 102 新增; 101 有历史单
        assert m.avg_charge_duration == 216  # (144+288)/2
        assert m.online_devices == 2         # ONLINE + CHARGING
        assert m.avg_wait_time == 15         # (10+20)/2
        assert float(m.utilization_rate) == 15.0   # 432min / (2*1440) *100
        assert float(m.idle_ratio) == 85.0

    def test_offline_device_not_counted_online(self, test_db):
        db = test_db["session"]
        db.add_all([
            _charger(2001, 2, DeviceStatus.ONLINE, guns=1),
            _charger(2002, 2, DeviceStatus.OFFLINE, guns=1),
        ])
        db.add(_order(2, UserType.APP, datetime(2026, 7, 15, 10, 0), total=10, paid=10,
                      kwh=5, duration=60, user_id=201, order_no="S2-A"))
        db.flush()
        build_station_daily_metrics(db, "2026-07-15")
        m = db.query(StationDailyMetric).filter(StationDailyMetric.station_id == 2).one()
        assert m.online_devices == 1          # OFFLINE 不计
        # 2 枪, 仅 60 min → 60/(2*1440)*100 ≈ 2.08
        assert float(m.utilization_rate) == pytest.approx(2.08, abs=0.01)

    def test_zero_guns_utilization_zero(self, test_db):
        db = test_db["session"]
        # 站3无充电桩设备记录
        db.add(_order(3, UserType.APP, datetime(2026, 7, 15, 10, 0), total=10, paid=10,
                      kwh=5, duration=120, user_id=301, order_no="S3-A"))
        db.flush()
        build_station_daily_metrics(db, "2026-07-15")
        m = db.query(StationDailyMetric).filter(StationDailyMetric.station_id == 3).one()
        assert float(m.utilization_rate) == 0.0
        assert float(m.idle_ratio) == 100.0
        assert m.online_devices == 0

    def test_idempotent_rerun(self, test_db):
        db = test_db["session"]
        self._seed_station1(db)
        build_station_daily_metrics(db, "2026-07-15")
        build_station_daily_metrics(db, "2026-07-15")
        rows = db.query(StationDailyMetric).filter(
            StationDailyMetric.station_id == 1,
            StationDailyMetric.record_date == datetime(2026, 7, 15),
        ).all()
        assert len(rows) == 1

    def test_excludes_other_dates(self, test_db):
        db = test_db["session"]
        db.add(_order(1, UserType.APP, datetime(2026, 7, 14, 10, 0), total=10, paid=10,
                      kwh=5, duration=60, user_id=401, order_no="OTHER"))
        db.flush()
        result = build_station_daily_metrics(db, "2026-07-15")
        assert result["stations"] == 0


# ═══════════════════════════════════════════════════════════════════
# _iter_target_dates 区间补算
# ═══════════════════════════════════════════════════════════════════

class TestIterTargetDates:

    def test_single_date(self):
        assert _iter_target_dates("2026-07-15", None) == ["2026-07-15"]

    def test_range_inclusive(self):
        assert _iter_target_dates("2026-07-15", "2026-07-17") == [
            "2026-07-15", "2026-07-16", "2026-07-17",
        ]

    def test_default_yesterday_when_none(self):
        out = _iter_target_dates(None, None)
        assert len(out) == 1
        assert out[0] == (date.today() - timedelta(days=1)).isoformat()

    def test_bad_date_empty(self):
        assert _iter_target_dates("bad", None) == []

    def test_end_before_start_clamps(self):
        assert _iter_target_dates("2026-07-17", "2026-07-15") == ["2026-07-17"]


# ═══════════════════════════════════════════════════════════════════
# revenue_stats API: 预聚合优先 + 手动触发
# ═══════════════════════════════════════════════════════════════════

def _seed_revenue_daily(session):
    """2 行预聚合: 站1-app / 站1-card, 日期 2026-07-15。"""
    session.add_all([
        RevenueDaily(record_date=datetime(2026, 7, 15), station_id=1, user_type="app",
                     orders_count=2, energy_kwh=Decimal("100"), charge_fee=Decimal("80"),
                     service_fee=Decimal("20"), parking_fee=Decimal("5"),
                     occupancy_fee=Decimal("3"), reservation_fee=Decimal("2"),
                     total_revenue=Decimal("110"), paid_revenue=Decimal("105"),
                     refund_amount=Decimal("5")),
        RevenueDaily(record_date=datetime(2026, 7, 15), station_id=1, user_type="card",
                     orders_count=1, energy_kwh=Decimal("30"), charge_fee=Decimal("24"),
                     service_fee=Decimal("6"), total_revenue=Decimal("30"),
                     paid_revenue=Decimal("30")),
    ])
    session.commit()


class TestRevenueStatsPreAggregated:
    """revenue_stats 优先读 revenue_daily 预聚合表, 无覆盖时回退实时聚合。"""

    def test_summary_prefers_pre_aggregated(self, client):
        _seed_revenue_daily(client._sesh)
        data = client.get(
            "/api/v1/operate/revenue/summary?start_date=2026-07-15&end_date=2026-07-15"
        ).json()["data"]
        assert data["source"] == "pre_aggregated"
        assert data["total_orders"] == 3            # 2 + 1
        assert data["total_revenue"] == 135.0       # paid 105 + 30
        assert data["total_kwh"] == 130.0
        assert data["total_electricity_fee"] == 104.0   # 80 + 24
        assert data["total_service_fee"] == 26.0        # 20 + 6
        assert data["total_parking_fee"] == 5.0
        assert data["total_reservation_fee"] == 2.0

    def test_summary_fallback_when_no_pre_aggregated(self, client):
        """无预聚合数据 → 回退实时聚合, 不带 source=pre_aggregated。"""
        from tests.test_operate_revenue_stats import _seed_revenue
        _seed_revenue(client._sesh)   # 仅订单, 无 revenue_daily
        data = client.get("/api/v1/operate/revenue/summary").json()["data"]
        assert data.get("source") != "pre_aggregated"
        assert data["total_orders"] == 2

    def test_daily_trend_reads_pre_aggregated(self, client):
        """预聚合路径: 日趋势直接读 revenue_daily, 规避 cast(Date) 在 SQLite 的 bug。

        造数日期用 UTC 锚点动态生成(卡 7b7a7444): 端点以 datetime.now(timezone.utc)-days
        为窗口下界, 硬编码日期会随时间滑出窗口而腐烂; today-1/today 两个整天恒在窗口内。
        """
        s = client._sesh
        today_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        d1, d2 = today_utc - timedelta(days=1), today_utc
        s.add_all([
            RevenueDaily(record_date=d1, station_id=1, user_type="app",
                         orders_count=1, paid_revenue=Decimal("40"), energy_kwh=Decimal("20")),
            RevenueDaily(record_date=d2, station_id=1, user_type="app",
                         orders_count=2, paid_revenue=Decimal("100"), energy_kwh=Decimal("50")),
        ])
        s.commit()
        r = client.get("/api/v1/operate/revenue/daily-trend?days=30")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2
        assert data[0]["date"] == d1.strftime("%Y-%m-%d")
        assert data[0]["revenue"] == 40.0
        assert data[1]["date"] == d2.strftime("%Y-%m-%d")
        assert data[1]["revenue"] == 100.0
        assert data[1]["orders"] == 2


class TestManualTriggerAggregate:
    """手动触发补算端点 (支持指定日期)。"""

    def test_trigger_revenue_aggregate(self, client):
        s = client._sesh
        s.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=55,
                     kwh=30, user_id=101, order_no="MT-1"))
        s.commit()

        r = client.post("/api/v1/operate/revenue/aggregate?target_date=2026-07-15")
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["status"] == "completed"
        assert body["orders"] == 1

        # 触发后 summary 走预聚合路径
        data = client.get(
            "/api/v1/operate/revenue/summary?start_date=2026-07-15&end_date=2026-07-15"
        ).json()["data"]
        assert data["source"] == "pre_aggregated"
        assert data["total_revenue"] == 55.0

    def test_trigger_station_metrics_aggregate(self, client):
        s = client._sesh
        s.add(_charger(9501, 5, DeviceStatus.ONLINE, guns=2))
        s.add(_order(5, UserType.APP, datetime(2026, 7, 15, 10, 0), total=50, paid=50,
                     kwh=25, duration=120, user_id=501, order_no="MT-2"))
        s.commit()

        r = client.post("/api/v1/operate/station-metrics/aggregate?target_date=2026-07-15")
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["status"] == "completed"
        assert body["stations"] == 1

        m = s.query(StationDailyMetric).filter(StationDailyMetric.station_id == 5).one()
        assert m.orders_count == 1
        assert m.online_devices == 1

    def test_trigger_range_backfill(self, client):
        """target_date..end_date 区间补算。"""
        s = client._sesh
        s.add(_order(1, UserType.APP, datetime(2026, 7, 14, 10, 0), total=40, paid=40,
                     user_id=1, order_no="RB-1"))
        s.add(_order(1, UserType.APP, datetime(2026, 7, 15, 10, 0), total=60, paid=60,
                     user_id=2, order_no="RB-2"))
        s.commit()

        r = client.post(
            "/api/v1/operate/revenue/aggregate?target_date=2026-07-14&end_date=2026-07-15"
        )
        assert r.status_code == 200
        days = r.json()["data"]["results"]
        assert len(days) == 2
        # 两日均生成预聚合行
        assert s.query(RevenueDaily).filter(
            RevenueDaily.record_date.in_([datetime(2026, 7, 14), datetime(2026, 7, 15)])
        ).count() == 2
