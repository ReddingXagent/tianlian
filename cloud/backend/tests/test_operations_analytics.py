"""
运营分析 6 大报表聚合 API 测试

覆盖 GET /api/v1/analytics/* (operations_analytics.py):
- /analytics/revenue        营收总览(总营收/充电量/订单数/客单价 + 趋势)
- /analytics/fee-breakdown  5项费用占比 + 趋势
- /analytics/user-revenue   按用户类型营收贡献/户均消费/复充率
- /analytics/station-rank   站点营收/充电量/利用率/收益每桩 排行
- /analytics/time-slot      尖峰平谷时段电量/电价/服务费占比
- /analytics/coupon-effect  券核销率/增量订单/优惠成本vs营收增长/ROI

每端点至少 1 正常用例 + 1 边界用例(空库/无参数)。
参考模式: tests/test_operate_revenue_stats.py。
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.models.station import Station, StationStatus
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import OrderFeeItem, FeeType
from app.models.coupon import Coupon, CouponUsage, CouponStatus, CouponType


BASE = "/api/v1/analytics"


# ─── 公共种子工厂 ───

def _paid_order(order_no, *, station_id=1, device_id=1, user_id=101,
                user_type=UserType.APP, paid_amount=Decimal("100"),
                charged_kwh=Decimal("50"), **extra):
    """构造一笔已支付已完成订单(创建于当前时刻, 命中默认 day 时间窗)。"""
    base = dict(
        order_no=order_no, station_id=station_id, device_id=device_id, user_id=user_id,
        user_type=user_type, charged_kwh=charged_kwh, paid_amount=paid_amount,
        electricity_fee=Decimal("0.00"), service_fee=Decimal("0.00"),
        total_amount=paid_amount, payment_status=OrderPaymentStatus.PAID,
        order_status=OrderStatus.COMPLETED, payment_method=PaymentMethod.WECHAT,
        created_at=datetime.now(timezone.utc),
    )
    base.update(extra)
    return ChargingOrder(**base)


# ─── 1. 营收总览 ───

def _seed_revenue_orders(session):
    """2 笔已支付订单: 100元50kWh + 60元30kWh"""
    session.add(_paid_order("OA-REV-1", user_id=101, paid_amount=Decimal("100"), charged_kwh=Decimal("50")))
    session.add(_paid_order("OA-REV-2", user_id=102, paid_amount=Decimal("60"), charged_kwh=Decimal("30")))
    session.commit()


class TestAnalyticsRevenue:
    """1. 营收总览"""

    def test_revenue_aggregates(self, client):
        """正常: 总营收160/总电量80/订单2/客单价80"""
        _seed_revenue_orders(client._sesh)
        data = client.get(f"{BASE}/revenue").json()["data"]
        summary = data["summary"]
        assert summary["total_revenue"] == 160.0
        assert summary["total_kwh"] == 80.0
        assert summary["total_orders"] == 2
        assert summary["avg_per_order"] == 80.0
        # 趋势序列聚合应等于总额
        trend = data["trend"]
        assert isinstance(trend, list) and len(trend) >= 1
        assert sum(r["revenue"] for r in trend) == 160.0
        assert sum(r["orders"] for r in trend) == 2

    def test_revenue_empty(self, client):
        """空库无参数: 全零, trend 为空"""
        data = client.get(f"{BASE}/revenue").json()["data"]
        assert data["summary"]["total_orders"] == 0
        assert data["summary"]["total_revenue"] == 0
        assert data["summary"]["avg_per_order"] == 0.0
        assert data["trend"] == []

    def test_revenue_invalid_range_rejected(self, client):
        """边界: 非法 range 值触发 422(pattern 校验)"""
        r = client.get(f"{BASE}/revenue?range=hour")
        assert r.status_code == 422

    def test_revenue_range_month_ok(self, client):
        """range=month 分支可用, 结构完整"""
        _seed_revenue_orders(client._sesh)
        data = client.get(f"{BASE}/revenue?range=month").json()["data"]
        assert {"summary", "trend"} <= set(data)
        assert data["summary"]["total_orders"] == 2


# ─── 2. 费用占比分析 ───

def _seed_fee_breakdown(session):
    """1 笔已支付订单 + 5 类费用项(电60/服40/停5/占3/预2, 合计110)

    注意: 端点 join OrderFeeItem.order_id == ChargingOrder.id 且要求订单 PAID,
    故必须用真实订单 id 关联费用项(不能凭空写 order_id)。
    """
    order = _paid_order("OA-FEE-1", paid_amount=Decimal("110"), charged_kwh=Decimal("50"))
    session.add(order)
    session.flush()
    now = datetime.now(timezone.utc)
    rows = [
        (FeeType.ELECTRICITY, "充电费", Decimal("60.00")),
        (FeeType.SERVICE, "服务费", Decimal("40.00")),
        (FeeType.PARKING, "停车费", Decimal("5.00")),
        (FeeType.OCCUPANCY, "占桩费", Decimal("3.00")),
        (FeeType.RESERVATION, "预约费", Decimal("2.00")),
    ]
    for ft, name, amt in rows:
        session.add(OrderFeeItem(
            order_id=order.id, fee_type=ft, fee_name=name,
            amount=amt, quantity=Decimal("1"), unit="元", created_at=now,
        ))
    session.commit()


class TestAnalyticsFeeBreakdown:
    """2. 费用占比分析"""

    def test_fee_breakdown_aggregates(self, client):
        """正常: 5 类合计110, 充电费占比≈54.55, 趋势1行"""
        _seed_fee_breakdown(client._sesh)
        data = client.get(f"{BASE}/fee-breakdown").json()["data"]
        assert data["total"] == 110.0
        by_type = {row["fee_type"]: row for row in data["breakdown"]}
        assert {"electricity", "service", "parking", "occupancy", "reservation"} <= set(by_type)
        assert by_type["electricity"]["amount"] == 60.0
        assert by_type["service"]["amount"] == 40.0
        assert by_type["reservation"]["amount"] == 2.0
        # 占比合计 ≈ 100
        assert abs(sum(r["percentage"] for r in data["breakdown"]) - 100.0) < 0.1
        # 充电费占比 60/110 ≈ 54.55
        assert abs(by_type["electricity"]["percentage"] - 54.55) < 0.01
        # 趋势一行, 各费用项金额正确
        assert len(data["trend"]) == 1
        t = data["trend"][0]
        assert t["electricity"] == 60.0
        assert t["service"] == 40.0
        assert t["reservation"] == 2.0

    def test_fee_breakdown_empty(self, client):
        """空库: total=0, breakdown 仍含 5 项(全0), trend 空"""
        data = client.get(f"{BASE}/fee-breakdown").json()["data"]
        assert data["total"] == 0.0
        assert len(data["breakdown"]) == 5
        assert all(r["amount"] == 0.0 and r["percentage"] == 0.0 for r in data["breakdown"])
        assert data["trend"] == []


# ─── 3. 用户收入分析 ───

def _seed_user_type_orders(session):
    """APP: 2 用户/3 单(100+50+50)/复充; CARD: 1 用户/1 单(60)"""
    session.add(_paid_order("OA-UT-1", user_id=101, user_type=UserType.APP,
                            paid_amount=Decimal("100"), charged_kwh=Decimal("50")))
    session.add(_paid_order("OA-UT-2", user_id=102, user_type=UserType.APP,
                            paid_amount=Decimal("50"), charged_kwh=Decimal("25")))
    session.add(_paid_order("OA-UT-3", user_id=102, user_type=UserType.APP,
                            paid_amount=Decimal("50"), charged_kwh=Decimal("25")))
    session.add(_paid_order("OA-UT-4", user_id=201, user_type=UserType.CARD,
                            paid_amount=Decimal("60"), charged_kwh=Decimal("30")))
    session.commit()


class TestAnalyticsUserRevenue:
    """3. 用户收入分析"""

    def test_user_revenue_breakdown(self, client):
        """正常: APP 营收200/3单/2用户/户均100; CARD 营收60/1单/1用户"""
        _seed_user_type_orders(client._sesh)
        data = client.get(f"{BASE}/user-revenue").json()["data"]
        by = {row["user_type"]: row for row in data["breakdown"]}
        assert "app" in by and "card" in by

        assert by["app"]["revenue"] == 200.0
        assert by["app"]["orders"] == 3
        assert by["app"]["unique_users"] == 2
        assert by["app"]["avg_per_user"] == 100.0
        assert by["app"]["orders_per_user"] == 1.5
        # 复充率: min(orders/users, 1.0)*100 = min(1.5,1.0)*100 = 100.0
        assert by["app"]["recharge_rate"] == 100.0

        assert by["card"]["revenue"] == 60.0
        assert by["card"]["orders"] == 1
        assert by["card"]["unique_users"] == 1
        assert by["card"]["recharge_rate"] == 100.0

    def test_user_revenue_empty(self, client):
        """空库: breakdown 为空列表"""
        data = client.get(f"{BASE}/user-revenue").json()["data"]
        assert data["breakdown"] == []

    def test_user_revenue_range_day_with_data(self, client):
        """回归 [35aad373]: 显式 range=day + 有数据 → 200, breakdown 列表含 app/card。

        case() 内 user_type 与 vin/interconnect/enterprise 字面量比较曾在 PG 抛 enum 500
        (SQLite 容忍故既有用例不暴露); cast(String) 后此端点须结构正确不抛异常。
        """
        _seed_user_type_orders(client._sesh)
        r = client.get(f"{BASE}/user-revenue?range=day")
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data["breakdown"], list)
        by = {row["user_type"]: row for row in data["breakdown"]}
        assert "app" in by and "card" in by

    def test_user_revenue_range_day_empty(self, client):
        """回归 [35aad373]: 显式 range=day + 空库 → 200, breakdown 空列表(不 500)。"""
        r = client.get(f"{BASE}/user-revenue?range=day")
        assert r.status_code == 200
        assert r.json()["data"]["breakdown"] == []


# ─── 4. 站点收益排行 ───

def _seed_station_rank(session):
    """2 站点各 1 单: 站A 营收100, 站B 营收60(应按营收降序)"""
    s1 = Station(name="分析站A", code="OA-ST-001", address="北京", status=StationStatus.NORMAL)
    s2 = Station(name="分析站B", code="OA-ST-002", address="上海", status=StationStatus.NORMAL)
    session.add_all([s1, s2])
    session.flush()
    session.add(_paid_order("OA-SR-1", station_id=s1.id, user_id=301,
                            paid_amount=Decimal("100"), charged_kwh=Decimal("50"),
                            duration_minutes=60))
    session.add(_paid_order("OA-SR-2", station_id=s2.id, user_id=302,
                            paid_amount=Decimal("60"), charged_kwh=Decimal("30"),
                            duration_minutes=30))
    session.commit()
    return s1, s2


class TestAnalyticsStationRank:
    """4. 站点收益排行"""

    def test_station_rank_ordering(self, client):
        """正常: 按营收降序, 站A(100)在前; 含站名/每单均价"""
        s1, s2 = _seed_station_rank(client._sesh)
        data = client.get(f"{BASE}/station-rank").json()["data"]
        ranking = data["ranking"]
        assert len(ranking) == 2
        assert ranking[0]["station_name"] == "分析站A"
        assert ranking[0]["revenue"] == 100.0
        assert ranking[0]["orders"] == 1
        assert ranking[0]["avg_revenue_per_order"] == 100.0
        assert ranking[1]["station_name"] == "分析站B"
        assert ranking[1]["revenue"] == 60.0
        # 利用率落在合法区间
        assert 0 <= ranking[0]["utilization_rate"] <= 100

    def test_station_rank_limit(self, client):
        """边界: limit=1 只返回 1 行"""
        _seed_station_rank(client._sesh)
        data = client.get(f"{BASE}/station-rank?limit=1").json()["data"]
        assert len(data["ranking"]) == 1
        assert data["ranking"][0]["revenue"] == 100.0  # 最高营收者

    def test_station_rank_limit_invalid(self, client):
        """边界: limit 超界(0 / 101)触发 422"""
        assert client.get(f"{BASE}/station-rank?limit=0").status_code == 422
        assert client.get(f"{BASE}/station-rank?limit=101").status_code == 422

    def test_station_rank_empty(self, client):
        """空库: ranking 为空列表"""
        data = client.get(f"{BASE}/station-rank").json()["data"]
        assert data["ranking"] == []


# ─── 5. 时段收益分析 ───

def _seed_time_slot(session):
    """1 单: 尖20/平20/谷10/深谷0; 电费60 服务费40 总电量50"""
    session.add(_paid_order(
        "OA-TS-1", user_id=401, paid_amount=Decimal("100"), charged_kwh=Decimal("50"),
        peak_energy=Decimal("20.00"), flat_energy=Decimal("20.00"),
        valley_energy=Decimal("10.00"), trough_energy=Decimal("0.00"),
        electricity_fee=Decimal("60.00"), service_fee=Decimal("40.00"),
    ))
    session.commit()


class TestAnalyticsTimeSlot:
    """5. 时段收益分析"""

    def test_time_slot_breakdown(self, client):
        """正常: 尖40%/平40%/谷20%/深谷0%; 服务费占比40%"""
        _seed_time_slot(client._sesh)
        data = client.get(f"{BASE}/time-slot").json()["data"]
        slots = {s["slot_key"]: s for s in data["slots"]}
        assert slots["peak"]["kwh"] == 20.0
        assert slots["flat"]["kwh"] == 20.0
        assert slots["valley"]["kwh"] == 10.0
        assert slots["trough"]["kwh"] == 0.0
        assert abs(slots["peak"]["kwh_percentage"] - 40.0) < 0.01
        assert abs(slots["valley"]["kwh_percentage"] - 20.0) < 0.01
        assert slots["trough"]["kwh_percentage"] == 0

        summary = data["summary"]
        assert summary["total_kwh"] == 50.0
        assert summary["total_electricity_fee"] == 60.0
        assert summary["total_service_fee"] == 40.0
        assert abs(summary["electricity_fee_ratio"] - 60.0) < 0.01
        assert abs(summary["service_fee_ratio"] - 40.0) < 0.01
        assert summary["total_orders"] == 1

    def test_time_slot_empty(self, client):
        """空库: 总电量0, 各时段占比0"""
        data = client.get(f"{BASE}/time-slot").json()["data"]
        assert data["summary"]["total_kwh"] == 0.0
        assert data["summary"]["total_orders"] == 0
        assert all(s["kwh_percentage"] == 0 for s in data["slots"])


# ─── 6. 优惠效果分析 ───

def _seed_coupons(session):
    """1 张固定券(面额5): 已用4(各抵5, 各绑1单coupon_amount=5/paid=50)/过期2/活跃4"""
    now = datetime.now(timezone.utc)
    coupon = Coupon(
        name="分析测试券", coupon_type=CouponType.FIXED, face_value=Decimal("5.00"),
        total_stock=10, remaining_stock=4, valid_days=30,
        start_time=now, end_time=now, is_active=True,
    )
    session.add(coupon)
    session.flush()

    # 4 张已用券, 各关联 1 笔已支付订单
    for i in range(4):
        order = _paid_order(f"OA-CP-{i}", user_id=500 + i,
                            paid_amount=Decimal("50.00"), charged_kwh=Decimal("10"))
        order.coupon_amount = Decimal("5.00")
        session.add(order)
        session.flush()
        session.add(CouponUsage(
            coupon_id=coupon.id, user_id=500 + i, coupon_code=f"OAU{i}",
            order_id=order.id, status=CouponStatus.USED,
            discount_amount=Decimal("5.00"), used_at=now,
            expires_at=now, received_at=now, created_at=now,
        ))
    # 2 张过期
    for i in range(2):
        session.add(CouponUsage(
            coupon_id=coupon.id, user_id=510 + i, coupon_code=f"OAE{i}",
            status=CouponStatus.EXPIRED, expires_at=now,
            received_at=now, created_at=now,
        ))
    # 4 张活跃未用
    for i in range(4):
        session.add(CouponUsage(
            coupon_id=coupon.id, user_id=520 + i, coupon_code=f"OAC{i}",
            status=CouponStatus.ACTIVE, expires_at=now,
            received_at=now, created_at=now,
        ))
    session.commit()
    return coupon.id


class TestAnalyticsCouponEffect:
    """6. 优惠效果分析"""

    def test_coupon_effect_summary(self, client):
        """正常: 发10/用4/过期2, 核销率40%, 优惠成本40, 营收200, ROI=4.0"""
        _seed_coupons(client._sesh)
        data = client.get(f"{BASE}/coupon-effect").json()["data"]
        s = data["summary"]
        assert s["total_coupons_issued"] == 10
        assert s["used_coupons"] == 4
        assert s["expired_coupons"] == 2
        assert s["redemption_rate"] == 40.0          # 4/10
        assert s["coupon_orders"] == 4               # 4 个不同订单
        assert s["total_discount_cost"] == 40.0      # 券抵扣20 + 订单coupon_amount20
        assert s["total_revenue"] == 200.0           # 4 * 50
        assert s["total_orders"] == 4
        assert s["roi"] == 4.0                        # (200-40)/40

    def test_coupon_effect_by_type(self, client):
        """正常: by_type 仅含 fixed 一类, 已用4, 成本20(仅券抵扣)"""
        _seed_coupons(client._sesh)
        data = client.get(f"{BASE}/coupon-effect").json()["data"]
        assert len(data["by_type"]) == 1
        row = data["by_type"][0]
        assert row["coupon_type"] == "fixed"
        assert row["type_name"] == "固定金额券"
        assert row["used_count"] == 4
        assert row["total_cost"] == 20.0

    def test_coupon_effect_empty(self, client):
        """空库: 全零, 核销率0, ROI0, by_type 空"""
        data = client.get(f"{BASE}/coupon-effect").json()["data"]
        s = data["summary"]
        assert s["total_coupons_issued"] == 0
        assert s["used_coupons"] == 0
        assert s["redemption_rate"] == 0.0
        assert s["total_discount_cost"] == 0.0
        assert s["roi"] == 0.0
        assert data["by_type"] == []
