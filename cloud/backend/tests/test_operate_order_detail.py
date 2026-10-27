"""
运营-订单详情 API 测试 — SPEC §2.2 订单详情 "计费明细(5项费用拆解)"

覆盖 GET /api/v1/operate/orders/{order_id}:
- 订单基本信息(订单号/站点/用户/SOC/电表/电量/时长/停止原因/状态)
- 5项费用结构化拆解: 充电费/服务费/停车费/占桩费/预约费
- 优惠三项 + 总费用 + 实收金额
- fee_items 明细行

验收: 订单详情5项费用拆解 API 可用, 5项费用计算正确(total = 5项之和,
实收 = 总费用 - 优惠券 - 积分 - 折扣)。
"""
from decimal import Decimal

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import OrderFeeItem, FeeType


def _seed_full_fee_order(session):
    """seed 一笔 5 项费用全非零的已完成订单 + fee_items 明细。

    电费35.50 + 服务25.00 + 停车6.00 + 占桩30.00 + 预约15.00 = 111.50
    折扣20 + 券15 + 积分10 = 45 → 实收 66.50
    """
    order = ChargingOrder(
        order_no="DET001", station_id=1, device_id=1, user_id=101,
        user_type=UserType.APP, plate_number="京A00001",
        charged_kwh=Decimal("50.00"),
        start_soc=Decimal("20.0"), end_soc=Decimal("80.0"),
        start_meter=Decimal("1000.00"), end_meter=Decimal("1050.00"),
        duration_minutes=60, stop_reason="full",
        electricity_fee=Decimal("35.50"),
        service_fee=Decimal("25.00"),
        parking_fee=Decimal("6.00"),
        occupancy_fee=Decimal("30.00"),
        reservation_fee=Decimal("15.00"),
        discount_amount=Decimal("20.00"),
        coupon_amount=Decimal("15.00"),
        points_amount=Decimal("10.00"),
        total_amount=Decimal("111.50"),
        paid_amount=Decimal("66.50"),
        payment_status=OrderPaymentStatus.PAID,
        order_status=OrderStatus.COMPLETED,
        payment_method=PaymentMethod.WECHAT,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    session.add_all([
        OrderFeeItem(order_id=order.id, fee_type=FeeType.ELECTRICITY,
                     fee_name="尖峰电费", quantity=Decimal("50"), unit_price=Decimal("0.71"),
                     amount=Decimal("35.50"), unit="kWh"),
        OrderFeeItem(order_id=order.id, fee_type=FeeType.SERVICE, fee_name="服务费",
                     quantity=Decimal("50"), unit_price=Decimal("0.50"),
                     amount=Decimal("25.00"), unit="kWh"),
        OrderFeeItem(order_id=order.id, fee_type=FeeType.PARKING, fee_name="停车费",
                     quantity=Decimal("1.5"), unit_price=Decimal("4"),
                     amount=Decimal("6.00"), unit="小时"),
        OrderFeeItem(order_id=order.id, fee_type=FeeType.OCCUPANCY, fee_name="占桩费",
                     quantity=Decimal("60"), unit_price=Decimal("0.5"),
                     amount=Decimal("30.00"), unit="分钟"),
        OrderFeeItem(order_id=order.id, fee_type=FeeType.RESERVATION, fee_name="预约费",
                     quantity=Decimal("30"), unit_price=Decimal("0.5"),
                     amount=Decimal("15.00"), unit="分钟"),
        OrderFeeItem(order_id=order.id, fee_type=FeeType.DISCOUNT, fee_name="折扣优惠",
                     quantity=Decimal("1"), unit_price=Decimal("20"),
                     amount=Decimal("-20.00"), unit="元"),
    ])
    session.commit()
    return order


class TestOrderDetailFeeBreakdown:
    """GET /api/v1/operate/orders/{order_id} — 订单详情 5 项费用拆解"""

    def test_detail_returns_five_fee_breakdown(self, client):
        """5 项费用结构化拆解: 充电费/服务费/停车费/占桩费/预约费 各自独立返回。"""
        order = _seed_full_fee_order(client._sesh)

        r = client.get(f"/api/v1/operate/orders/{order.id}")
        assert r.status_code == 200, r.text
        data = r.json()["data"]

        fees = data["fees"]
        # 5 项费用逐项拆解(与订单落库值一致)
        assert fees["charge_fee"] == 35.5        # 充电费(电费)
        assert fees["service_fee"] == 25.0       # 服务费
        assert fees["parking_fee"] == 6.0        # 停车费
        assert fees["occupancy_fee"] == 30.0     # 占桩费
        assert fees["reservation_fee"] == 15.0   # 预约费

    def test_detail_total_equals_sum_of_five_fees(self, client):
        """5 项费用计算正确性: 总费用 = 充电费+服务费+停车费+占桩费+预约费。"""
        order = _seed_full_fee_order(client._sesh)

        data = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        fees = data["fees"]

        five_sum = (fees["charge_fee"] + fees["service_fee"] + fees["parking_fee"]
                    + fees["occupancy_fee"] + fees["reservation_fee"])
        assert five_sum == fees["total_amount"] == 111.5

    def test_detail_paid_equals_total_minus_discounts(self, client):
        """实收 = 总费用 - 折扣 - 优惠券 - 积分 (优惠三项联动)。"""
        order = _seed_full_fee_order(client._sesh)

        data = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        fees = data["fees"]

        assert fees["discount_amount"] == 20.0
        assert fees["coupon_amount"] == 15.0
        assert fees["points_amount"] == 10.0
        expected_paid = fees["total_amount"] - fees["discount_amount"] \
            - fees["coupon_amount"] - fees["points_amount"]
        assert fees["paid_amount"] == expected_paid == 66.5

    def test_detail_fee_items_returned(self, client):
        """订单详情返回 fee_items 明细行(含 5 项费用 + 优惠行)。"""
        order = _seed_full_fee_order(client._sesh)

        data = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        items = data["fee_items"]
        # 5 项费用 + 1 折扣行 = 6 行
        assert len(items) == 6
        types = {i["fee_type"] for i in items}
        assert types >= {"electricity", "service", "parking", "occupancy", "reservation"}
        # 每行结构完整
        for it in items:
            for key in ("fee_type", "fee_name", "quantity", "unit_price", "amount", "unit"):
                assert key in it

    def test_detail_order_basic_info(self, client):
        """订单基本信息字段齐全(§2.2 订单详情: SOC/电表/电量/停止原因)。"""
        order = _seed_full_fee_order(client._sesh)

        data = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        assert data["order_no"] == "DET001"
        assert data["station_id"] == 1
        assert data["user_type"] == "app"
        assert data["charged_kwh"] == 50.0
        assert data["start_soc"] == 20.0
        assert data["end_soc"] == 80.0
        assert data["start_meter"] == 1000.0
        assert data["end_meter"] == 1050.0
        assert data["stop_reason"] == "full"
        assert data["order_status"] == "completed"
        assert data["payment_status"] == "paid"
        assert data["payment_method"] == "im_b"

    def test_detail_not_found(self, client):
        """不存在的订单 → 404。"""
        r = client.get("/api/v1/operate/orders/999999")
        assert r.status_code == 404

    def test_detail_fee_fields_zero_when_unset(self, client):
        """边界 — 新订单未结算: 5 项费用均为 0, 实收 0, fee_items 空。"""
        session = client._sesh
        order = ChargingOrder(
            order_no="DET002", station_id=1, device_id=1,
            order_status=OrderStatus.PENDING,
            payment_status=OrderPaymentStatus.UNPAID,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        data = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        fees = data["fees"]
        assert fees["charge_fee"] == 0
        assert fees["service_fee"] == 0
        assert fees["total_amount"] == 0
        assert fees["paid_amount"] == 0
        assert data["fee_items"] == []
