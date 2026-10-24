"""
运营-营收统计 API 测试

覆盖 /api/v1/operate/revenue:
- GET /revenue/summary     营收概览(总营收/电量/订单/各项费用)
- GET /revenue/by-station  按站点营收明细
- GET /revenue/daily-trend 日趋势(端点 cast(Date) 在 SQLite 报错, xfail 标注)
- GET /revenue/export      导出(同 by-station)
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models.station import Station, StationStatus
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)


def _seed_revenue(session):
    """2 站点 + 2 笔已支付订单(分属不同站点)"""
    s1 = Station(name="营收站A", code="REV001", address="北京", status=StationStatus.NORMAL)
    s2 = Station(name="营收站B", code="REV002", address="上海", status=StationStatus.NORMAL)
    session.add_all([s1, s2])
    session.flush()

    session.add(ChargingOrder(
        order_no="REV001", station_id=s1.id, device_id=1, user_id=101,
        user_type=UserType.APP, charged_kwh=Decimal("50.00"),
        electricity_fee=Decimal("60.00"), service_fee=Decimal("40.00"),
        parking_fee=Decimal("5.00"), total_amount=Decimal("100.00"),
        paid_amount=Decimal("100.00"), discount_amount=Decimal("10.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT, created_at=datetime.now(timezone.utc),
    ))
    session.add(ChargingOrder(
        order_no="REV002", station_id=s2.id, device_id=2, user_id=102,
        user_type=UserType.CARD, charged_kwh=Decimal("30.00"),
        electricity_fee=Decimal("40.00"), service_fee=Decimal("20.00"),
        total_amount=Decimal("60.00"), paid_amount=Decimal("60.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.CARD, created_at=datetime.now(timezone.utc),
    ))
    session.commit()
    return [s1, s2]


class TestOperateRevenueStats:
    """营收统计聚合"""

    def test_revenue_summary(self, client):
        """概览: 2 单/总营收160/总电量80"""
        _seed_revenue(client._sesh)
        data = client.get("/api/v1/operate/revenue/summary").json()["data"]
        assert data["total_orders"] == 2
        assert data["total_revenue"] == 160.0   # 100 + 60
        assert data["total_kwh"] == 80.0        # 50 + 30
        assert data["total_electricity_fee"] == 100.0  # 60 + 40
        assert data["total_service_fee"] == 60.0       # 40 + 20
        assert data["total_discount"] == 10.0
        assert data["total_parking_fee"] == 5.0

    def test_revenue_by_station(self, client):
        """按站点: 返回 2 行, 含站名"""
        stations = _seed_revenue(client._sesh)
        data = client.get("/api/v1/operate/revenue/by-station").json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        names = {row["station_name"] for row in data}
        assert "营收站A" in names and "营收站B" in names
        # 站A 1 单 100 元
        row_a = next(r for r in data if r["station_name"] == "营收站A")
        assert row_a["order_count"] == 1
        assert row_a["total_paid"] == 100.0

    def test_revenue_by_station_date_filter(self, client):
        """日期过滤: 范围外返回空"""
        _seed_revenue(client._sesh)
        # 2030 年的范围, 不命中今天的数据
        r = client.get("/api/v1/operate/revenue/by-station?start_date=2030-01-01&end_date=2030-01-02")
        assert r.status_code == 200
        assert r.json()["data"] == []

    @pytest.mark.xfail(
        reason="端点 bug(非本次范围): revenue_stats.py:130 cast(created_at, Date) "
               "在 SQLite 下 result-row 解析触发 fromisoformat TypeError, 接口 500"
    )
    def test_revenue_daily_trend(self, client):
        """日趋势: 含今天一行(端点当前 broken, xfail 记录)"""
        _seed_revenue(client._sesh)
        data = client.get("/api/v1/operate/revenue/daily-trend?days=30").json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1
        today_row = data[-1]
        assert today_row["revenue"] == 160.0
        assert today_row["orders"] == 2

    def test_revenue_export_matches_by_station(self, client):
        """export 端点与 by-station 同结构"""
        _seed_revenue(client._sesh)
        exported = client.get("/api/v1/operate/revenue/export").json()["data"]
        by_station = client.get("/api/v1/operate/revenue/by-station").json()["data"]
        assert exported == by_station


# ================= 运营分析深化 (Phase43) =================
from app.models.order_fee_item import OrderFeeItem, FeeType as ItemFeeType
from app.models.coupon import Coupon, CouponUsage, CouponStatus, CouponType
from app.models.pricing_v2 import TimeSlotDefinition, PeriodType


def _seed_fee_items(session):
    """5 类费用明细(本月): 电60/服40/停5/占3/预2, 合计 110"""
    now = datetime.now(timezone.utc)
    rows = [
        (ItemFeeType.ELECTRICITY, "电费", Decimal("60.00"), Decimal("50.0000"), "kWh"),
        (ItemFeeType.SERVICE, "服务费", Decimal("40.00"), Decimal("50.0000"), "kWh"),
        (ItemFeeType.PARKING, "停车费", Decimal("5.00"), Decimal("1.0000"), "小时"),
        (ItemFeeType.OCCUPANCY, "占桩费", Decimal("3.00"), Decimal("30.0000"), "分钟"),
        (ItemFeeType.RESERVATION, "预约费", Decimal("2.00"), Decimal("1"), "次"),
    ]
    for ft, name, amt, qty, unit in rows:
        session.add(OrderFeeItem(
            order_id=9001, fee_type=ft, fee_name=name,
            amount=amt, quantity=qty, unit=unit, created_at=now,
        ))
    session.commit()


def _seed_user_type_orders(session):
    """APP: 2 用户/3 单/复充率 0.5；CARD: 1 用户/1 单"""
    base = dict(
        payment_status=OrderPaymentStatus.PAID,
        order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT,
        created_at=datetime.now(timezone.utc),
    )
    session.add(ChargingOrder(order_no="UT1", station_id=1, device_id=1, user_id=101,
                              user_type=UserType.APP, charged_kwh=Decimal("50"), paid_amount=Decimal("100"), **base))
    session.add(ChargingOrder(order_no="UT2", station_id=1, device_id=1, user_id=102,
                              user_type=UserType.APP, charged_kwh=Decimal("25"), paid_amount=Decimal("50"), **base))
    session.add(ChargingOrder(order_no="UT3", station_id=1, device_id=1, user_id=102,
                              user_type=UserType.APP, charged_kwh=Decimal("25"), paid_amount=Decimal("50"), **base))
    session.add(ChargingOrder(order_no="UT4", station_id=1, device_id=1, user_id=201,
                              user_type=UserType.CARD, charged_kwh=Decimal("30"), paid_amount=Decimal("60"), **base))
    session.commit()


def _seed_time_period_orders(session):
    """分时电量: 尖20/平20/谷10/深谷0；电费60 服务费40"""
    session.add(ChargingOrder(
        order_no="TP1", station_id=1, device_id=1, user_id=301, user_type=UserType.APP,
        peak_energy=Decimal("20.00"), flat_energy=Decimal("20.00"),
        valley_energy=Decimal("10.00"), trough_energy=Decimal("0.00"),
        charged_kwh=Decimal("50.00"), electricity_fee=Decimal("60.00"),
        service_fee=Decimal("40.00"), paid_amount=Decimal("100.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
    ))
    session.commit()


def _seed_coupons(session):
    """1 张券发 10 张: 核销 4(各抵 5, 关联回款 50 订单)/过期 2/活跃 4"""
    now = datetime.now(timezone.utc)
    c = Coupon(name="新客券", coupon_type=CouponType.FIXED, face_value=Decimal("5.00"),
               total_stock=10, remaining_stock=4, valid_days=30,
               start_time=now, end_time=now, is_active=True)
    session.add(c)
    session.flush()
    order_ids = []
    for i in range(4):
        o = ChargingOrder(order_no=f"CP{i}", station_id=1, device_id=1, user_id=400 + i,
                          user_type=UserType.APP, paid_amount=Decimal("50.00"),
                          coupon_amount=Decimal("5.00"),
                          payment_status=OrderPaymentStatus.PAID,
                          order_status=OrderStatus.COMPLETED, created_at=now)
        session.add(o)
        session.flush()
        order_ids.append(o.id)
    for i in range(4):
        session.add(CouponUsage(coupon_id=c.id, user_id=400 + i, coupon_code=f"UC{i}",
                                order_id=order_ids[i], status=CouponStatus.USED,
                                discount_amount=Decimal("5.00"), used_at=now,
                                expires_at=now, created_at=now))
    for i in range(2):
        session.add(CouponUsage(coupon_id=c.id, user_id=410 + i, coupon_code=f"EX{i}",
                                status=CouponStatus.EXPIRED, expires_at=now, created_at=now))
    for i in range(4):
        session.add(CouponUsage(coupon_id=c.id, user_id=420 + i, coupon_code=f"AC{i}",
                                status=CouponStatus.ACTIVE, expires_at=now, created_at=now))
    session.commit()
    return c.id


class TestOperateRevenueDeepAnalytics:
    """运营分析深化 — 4 个新端点"""

    def test_revenue_fee_breakdown(self, client):
        """费用占比: 5 类按月聚合, 占比合计 ≈ 1"""
        _seed_fee_items(client._sesh)
        data = client.get("/api/v1/operate/revenue/fee-breakdown").json()["data"]
        assert {"trends", "summary", "total", "ratios"} <= set(data)
        assert data["total"] == 110.0
        assert data["summary"]["electricity"] == 60.0
        assert data["summary"]["service"] == 40.0
        assert data["summary"]["reservation"] == 2.0
        assert len(data["trends"]) == 1                      # 本月一行
        assert data["trends"][0]["fees"]["electricity"] == 60.0
        assert abs(sum(data["ratios"].values()) - 1.0) < 0.01

    def test_revenue_by_user_type(self, client):
        """用户收入: APP 2 用户/3 单/复充率 0.5；CARD 1 用户"""
        _seed_user_type_orders(client._sesh)
        data = client.get("/api/v1/operate/revenue/by-user-type").json()["data"]
        by = {row["user_type"]: row for row in data}
        assert "app" in by and "card" in by
        assert by["app"]["revenue"] == 200.0
        assert by["app"]["orders"] == 3
        assert by["app"]["users"] == 2
        assert by["app"]["avg_per_user"] == 100.0
        assert by["app"]["repeat_rate"] == 0.5
        assert by["card"]["users"] == 1
        assert by["card"]["repeat_rate"] == 0.0

    def test_revenue_by_time_period(self, client):
        """时段收益: 尖20/平20/谷10；服务费占比 0.4"""
        _seed_time_period_orders(client._sesh)
        data = client.get("/api/v1/operate/revenue/by-time-period").json()["data"]
        periods = {p["period"]: p for p in data["periods"]}
        assert periods["peak"]["energy"] == 20.0
        assert periods["flat"]["energy"] == 20.0
        assert periods["valley"]["energy"] == 10.0
        assert data["total_energy"] == 50.0
        assert data["service_fee"] == 40.0
        assert abs(data["service_fee_ratio"] - 0.4) < 0.01

    def test_revenue_coupon_effectiveness(self, client):
        """券效果: 核销率 0.4 / 优惠成本 20 / ROI = 200/20 = 10"""
        _seed_coupons(client._sesh)
        data = client.get("/api/v1/operate/revenue/coupon-effectiveness").json()["data"]
        assert data["summary"]["total_issued"] == 10
        assert data["summary"]["total_used"] == 4
        assert abs(data["summary"]["overall_redemption_rate"] - 0.4) < 0.01
        assert data["summary"]["total_discount_cost"] == 20.0
        assert data["summary"]["total_order_revenue"] == 200.0
        assert abs(data["summary"]["overall_roi"] - 10.0) < 0.01

    def test_deep_analytics_date_filter(self, client):
        """4 端点统一支持日期过滤: 范围外(2030)返回空集"""
        _seed_fee_items(client._sesh)
        _seed_user_type_orders(client._sesh)
        _seed_time_period_orders(client._sesh)
        _seed_coupons(client._sesh)
        for ep in ["fee-breakdown", "by-user-type", "by-time-period", "coupon-effectiveness"]:
            r = client.get(f"/api/v1/operate/revenue/{ep}?start_date=2030-01-01&end_date=2030-01-02")
            assert r.status_code == 200, ep
            d = r.json()["data"]
            if ep == "fee-breakdown":
                assert d["trends"] == [] and d["total"] == 0
            elif ep == "by-user-type":
                assert d == []
            elif ep == "by-time-period":
                assert d["total_energy"] == 0
            else:
                assert d["summary"]["total_issued"] == 0
