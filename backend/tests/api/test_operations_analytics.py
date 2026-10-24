#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运营分析6大报表 API 聚合测试

造多类型订单 + 费用明细 + 券数据, 验证 6 个 analytics 端点聚合正确性
"""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import OrderFeeItem, FeeType, RefundRecord, RefundStatus
from app.models.coupon import Coupon, CouponUsage, CouponType, CouponStatus
from app.models.station import Station, StationStatus


def _seed_analytics_data(session):
    """创建测试数据: 2站点 + 多类型订单 + 费用明细 + 券"""
    now = datetime.now(timezone.utc)

    # 站点
    s1 = Station(name="分析站A", code="ANA001", address="北京", status=StationStatus.NORMAL)
    s2 = Station(name="分析站B", code="ANA002", address="上海", status=StationStatus.NORMAL)
    session.add_all([s1, s2])
    session.flush()

    # 订单 — APP用户
    o1 = ChargingOrder(
        order_no="ANA001", station_id=s1.id, device_id=1, user_id=101,
        user_type=UserType.APP, charged_kwh=Decimal("50.00"),
        electricity_fee=Decimal("30.00"), service_fee=Decimal("15.00"),
        parking_fee=Decimal("5.00"), occupancy_fee=Decimal("0.00"),
        reservation_fee=Decimal("0.00"), total_amount=Decimal("50.00"),
        paid_amount=Decimal("50.00"), coupon_amount=Decimal("5.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT, duration_minutes=60,
        peak_energy=Decimal("10.00"), flat_energy=Decimal("20.00"),
        valley_energy=Decimal("15.00"), trough_energy=Decimal("5.00"),
        created_at=now - timedelta(days=1),
    )
    # 订单 — 卡用户
    o2 = ChargingOrder(
        order_no="ANA002", station_id=s1.id, device_id=2, user_id=102,
        user_type=UserType.CARD, charged_kwh=Decimal("30.00"),
        electricity_fee=Decimal("18.00"), service_fee=Decimal("9.00"),
        parking_fee=Decimal("0.00"), occupancy_fee=Decimal("3.00"),
        reservation_fee=Decimal("0.00"), total_amount=Decimal("30.00"),
        paid_amount=Decimal("30.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.CARD, duration_minutes=45,
        peak_energy=Decimal("5.00"), flat_energy=Decimal("15.00"),
        valley_energy=Decimal("10.00"), trough_energy=Decimal("0.00"),
        created_at=now - timedelta(days=2),
    )
    # 订单 — APP用户, 站点B
    o3 = ChargingOrder(
        order_no="ANA003", station_id=s2.id, device_id=3, user_id=101,
        user_type=UserType.APP, charged_kwh=Decimal("80.00"),
        electricity_fee=Decimal("48.00"), service_fee=Decimal("24.00"),
        parking_fee=Decimal("0.00"), occupancy_fee=Decimal("0.00"),
        reservation_fee=Decimal("8.00"), total_amount=Decimal("80.00"),
        paid_amount=Decimal("75.00"), coupon_amount=Decimal("5.00"),
        payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.ALIPAY, duration_minutes=90,
        peak_energy=Decimal("20.00"), flat_energy=Decimal("40.00"),
        valley_energy=Decimal("15.00"), trough_energy=Decimal("5.00"),
        created_at=now - timedelta(hours=6),
    )
    session.add_all([o1, o2, o3])
    session.flush()

    # 费用明细
    fees = [
        OrderFeeItem(order_id=o1.id, fee_type=FeeType.ELECTRICITY, fee_name="充电费", amount=Decimal("30.00"), unit="元"),
        OrderFeeItem(order_id=o1.id, fee_type=FeeType.SERVICE, fee_name="服务费", amount=Decimal("15.00"), unit="元"),
        OrderFeeItem(order_id=o1.id, fee_type=FeeType.PARKING, fee_name="停车费", amount=Decimal("5.00"), unit="元"),
        OrderFeeItem(order_id=o2.id, fee_type=FeeType.ELECTRICITY, fee_name="充电费", amount=Decimal("18.00"), unit="元"),
        OrderFeeItem(order_id=o2.id, fee_type=FeeType.SERVICE, fee_name="服务费", amount=Decimal("9.00"), unit="元"),
        OrderFeeItem(order_id=o2.id, fee_type=FeeType.OCCUPANCY, fee_name="占桩费", amount=Decimal("3.00"), unit="元"),
        OrderFeeItem(order_id=o3.id, fee_type=FeeType.ELECTRICITY, fee_name="充电费", amount=Decimal("48.00"), unit="元"),
        OrderFeeItem(order_id=o3.id, fee_type=FeeType.SERVICE, fee_name="服务费", amount=Decimal("24.00"), unit="元"),
        OrderFeeItem(order_id=o3.id, fee_type=FeeType.RESERVATION, fee_name="预约费", amount=Decimal("8.00"), unit="元"),
    ]
    session.add_all(fees)

    # 券
    coupon = Coupon(
        name="分析测试券", coupon_type=CouponType.FIXED, face_value=Decimal("5.00"),
        min_order_amount=Decimal("20.00"), total_stock=100, remaining_stock=97,
        start_time=now - timedelta(days=30), end_time=now + timedelta(days=30),
        is_active=True,
    )
    session.add(coupon)
    session.flush()

    # 券使用记录 — 3张发出, 2张已用, 1张过期
    usages = [
        CouponUsage(
            coupon_id=coupon.id, user_id=101, user_type="app",
            coupon_code="CU001", order_id=o1.id, status=CouponStatus.USED,
            discount_amount=Decimal("5.00"), used_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
        ),
        CouponUsage(
            coupon_id=coupon.id, user_id=101, user_type="app",
            coupon_code="CU002", order_id=o3.id, status=CouponStatus.USED,
            discount_amount=Decimal("5.00"), used_at=now - timedelta(hours=6),
            expires_at=now + timedelta(days=30),
        ),
        CouponUsage(
            coupon_id=coupon.id, user_id=102, user_type="card",
            coupon_code="CU003", order_id=None, status=CouponStatus.EXPIRED,
            discount_amount=Decimal("0.00"), used_at=None,
            expires_at=now - timedelta(days=1),
        ),
    ]
    session.add_all(usages)
    session.commit()

    return {"stations": [s1, s2], "orders": [o1, o2, o3], "coupon": coupon}


class TestOperationsAnalytics:
    """运营分析6大报表测试"""

    def test_revenue_overview(self, client):
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/revenue?range=month")
        assert r.status_code == 200
        data = r.json()["data"]
        summary = data["summary"]
        # 3 orders, total paid = 50 + 30 + 75 = 155
        assert summary["total_orders"] == 3
        assert summary["total_revenue"] == 155.0
        # total kwh = 50 + 30 + 80 = 160
        assert summary["total_kwh"] == 160.0
        # avg_per_order = 155 / 3
        assert abs(summary["avg_per_order"] - round(155.0 / 3, 2)) < 0.01
        assert isinstance(data["trend"], list)
        assert len(data["trend"]) >= 1

    def test_fee_breakdown(self, client):
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/fee-breakdown?range=month")
        assert r.status_code == 200
        data = r.json()["data"]
        breakdown = data["breakdown"]
        assert len(breakdown) == 5
        # electricity = 30 + 18 + 48 = 96
        elec = next(b for b in breakdown if b["fee_type"] == "electricity")
        assert elec["amount"] == 96.0
        # service = 15 + 9 + 24 = 48
        svc = next(b for b in breakdown if b["fee_type"] == "service")
        assert svc["amount"] == 48.0
        # parking = 5
        park = next(b for b in breakdown if b["fee_type"] == "parking")
        assert park["amount"] == 5.0
        # occupancy = 3
        occ = next(b for b in breakdown if b["fee_type"] == "occupancy")
        assert occ["amount"] == 3.0
        # reservation = 8
        res = next(b for b in breakdown if b["fee_type"] == "reservation")
        assert res["amount"] == 8.0
        # total = 96 + 48 + 5 + 3 + 8 = 160
        assert data["total"] == 160.0
        assert isinstance(data["trend"], list)

    def test_user_revenue(self, client):
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/user-revenue?range=month")
        assert r.status_code == 200
        data = r.json()["data"]
        breakdown = data["breakdown"]
        assert len(breakdown) >= 2
        # APP: 2 orders, revenue = 50 + 75 = 125
        app_row = next(b for b in breakdown if b["user_type"] == "app")
        assert app_row["orders"] == 2
        assert app_row["revenue"] == 125.0
        assert app_row["kwh"] == 130.0
        # CARD: 1 order, revenue = 30
        card_row = next(b for b in breakdown if b["user_type"] == "card")
        assert card_row["orders"] == 1
        assert card_row["revenue"] == 30.0
        # 验证户均消费 > 0
        assert app_row["avg_per_user"] > 0

    def test_station_rank(self, client):
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/station-rank?range=month")
        assert r.status_code == 200
        data = r.json()["data"]
        ranking = data["ranking"]
        assert len(ranking) == 2
        # Station A (s1): 2 orders, revenue = 50 + 30 = 80
        # Station B (s2): 1 order, revenue = 75
        assert ranking[0]["revenue"] >= ranking[1]["revenue"]
        # 站名存在
        for item in ranking:
            assert item["station_name"]
            assert item["utilization_rate"] >= 0
            assert item["revenue_per_pile"] >= 0

    def test_time_slot(self, client):
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/time-slot?range=month")
        assert r.status_code == 200
        data = r.json()["data"]
        slots = data["slots"]
        assert len(slots) == 4
        # peak = 10 + 5 + 20 = 35
        peak = next(s for s in slots if s["slot_key"] == "peak")
        assert peak["kwh"] == 35.0
        # flat = 20 + 15 + 40 = 75
        flat = next(s for s in slots if s["slot_key"] == "flat")
        assert flat["kwh"] == 75.0
        # total_kwh = 160
        assert data["summary"]["total_kwh"] == 160.0
        assert data["summary"]["total_orders"] == 3

    def test_coupon_effect(self, client):
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/coupon-effect?range=month")
        assert r.status_code == 200
        data = r.json()["data"]
        summary = data["summary"]
        # 3 coupons issued, 2 used, 1 expired
        assert summary["total_coupons_issued"] == 3
        assert summary["used_coupons"] == 2
        assert summary["expired_coupons"] == 1
        # redemption_rate = 2/3 * 100 = 66.67
        assert abs(summary["redemption_rate"] - 66.67) < 0.1
        # discount cost: 5 + 5 (coupon_usage) + 5 + 5 (order coupon_amount) = 20
        assert summary["total_discount_cost"] == 20.0
        # roi > 0 (revenue > discount cost)
        assert summary["roi"] > 0
        assert len(data["by_type"]) >= 1

    def test_revenue_refund_deduction(self, client):
        """卡 a1e8299d: 有退款当日总营收不虚高 — summary 增 total_refund/net_revenue。

        口径: 退款按关联订单 created_at 窗口回溯(与营收窗口对齐);
        总营收毛口径含 PAID/PARTIAL/REFUNDING/REFUNDED(退款后订单离开 PAID 态),
        net = gross - refund 不重复扣。
        """
        s = client._sesh
        seeded = _seed_analytics_data(s)  # 155 毛(PAID-only 视角)
        now = datetime.now(timezone.utc)
        o1 = seeded["orders"][0]
        s.add(RefundRecord(order_id=o1.id, user_id=101, refund_amount=Decimal("20.00"),
                           reason="test", status=RefundStatus.REFUNDED,
                           refunded_at=now - timedelta(hours=1)))
        # 全额退款订单(o3, 75): 退款完成后订单离开 PAID 态 → 毛口径必须纳入才不双扣
        o3 = seeded["orders"][2]
        o3.payment_status = OrderPaymentStatus.REFUNDED
        s.add(RefundRecord(order_id=o3.id, user_id=101, refund_amount=Decimal("75.00"),
                           reason="test-full", status=RefundStatus.REFUNDED,
                           refunded_at=now - timedelta(hours=1)))
        # 在途退款不计入
        s.add(RefundRecord(order_id=seeded["orders"][1].id, user_id=102,
                           refund_amount=Decimal("5.00"), reason="pending",
                           status=RefundStatus.PENDING))
        s.commit()

        r = client.get("/api/v1/analytics/revenue?range=month")
        assert r.status_code == 200
        summary = r.json()["data"]["summary"]
        # gross = 50(o1) + 30(o2) + 75(o3 REFUNDED) = 155; refund = 20 + 75 = 95
        assert summary["total_revenue"] == 155.0
        assert summary["total_refund"] == 95.0
        assert summary["net_revenue"] == 60.0
        # trend 每期带 net_revenue, 各期 gross 求和 = 155
        assert abs(sum(t["revenue"] for t in r.json()["data"]["trend"]) - 155.0) < 0.01
        assert all("net_revenue" in t and "refund" in t for t in r.json()["data"]["trend"])

    def test_revenue_range_year(self, client):
        """验证 year 范围参数"""
        _seed_analytics_data(client._sesh)
        r = client.get("/api/v1/analytics/revenue?range=year")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "summary" in data
        assert "trend" in data
