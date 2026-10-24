"""
运营-财务管理 API 测试

覆盖 /api/v1/operate/financial:
- GET /financial/charges       充电费记录(已支付)
- GET /financial/parking       停车费(parking_fee>0)
- GET /financial/occupancy     占桩费(idle_penalty>0)
- GET /financial/reservations  预约费(reservation_fee>0)
- GET /financial/refunds       退款(REFUNDING/REFUNDED/PARTIAL)
"""
from decimal import Decimal

from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)


def _seed_financial(session):
    """3 笔订单, 分别命中不同费用/退款端点"""
    orders = [
        # o1: 已支付 + 有停车费
        ChargingOrder(
            order_no="FIN001", station_id=1, device_id=1, user_id=101,
            user_type=UserType.APP, plate_number="京A11111",
            parking_fee=Decimal("5.00"), idle_penalty=Decimal("0.00"),
            reservation_fee=Decimal("0.00"), total_amount=Decimal("100.00"),
            paid_amount=Decimal("100.00"),
            payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
        ),
        # o2: 已支付 + 占桩费 + 预约费
        ChargingOrder(
            order_no="FIN002", station_id=1, device_id=2, user_id=102,
            user_type=UserType.CARD, plate_number="京B22222",
            parking_fee=Decimal("0.00"), idle_penalty=Decimal("3.00"),
            reservation_fee=Decimal("2.00"), total_amount=Decimal("50.00"),
            paid_amount=Decimal("50.00"),
            payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.CARD,
        ),
        # o3: 已退款
        ChargingOrder(
            order_no="FIN003", station_id=1, device_id=3, user_id=103,
            user_type=UserType.APP, plate_number="京C33333",
            total_amount=Decimal("20.00"), paid_amount=Decimal("20.00"),
            payment_status=OrderPaymentStatus.REFUNDED, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.ALIPAY,
        ),
    ]
    session.add_all(orders)
    session.commit()
    return orders


class TestOperateFinancial:
    """五类财务记录列表"""

    def test_financial_charges(self, client):
        """充电费记录: 仅已支付订单(o1, o2)"""
        _seed_financial(client._sesh)
        data = client.get("/api/v1/operate/financial/charges").json()["data"]
        assert data["total"] == 2
        order_nos = {item["order_no"] for item in data["items"]}
        assert order_nos == {"FIN001", "FIN002"}

    def test_financial_parking_occupancy_reservations(self, client):
        """停车/占桩/预约 各自按费用>0过滤"""
        _seed_financial(client._sesh)

        parking = client.get("/api/v1/operate/financial/parking").json()["data"]
        assert parking["total"] == 1
        assert parking["items"][0]["order_no"] == "FIN001"
        assert parking["items"][0]["parking_fee"] == 5.0

        occupancy = client.get("/api/v1/operate/financial/occupancy").json()["data"]
        assert occupancy["total"] == 1
        assert occupancy["items"][0]["order_no"] == "FIN002"
        assert occupancy["items"][0]["idle_penalty"] == 3.0

        reservations = client.get("/api/v1/operate/financial/reservations").json()["data"]
        assert reservations["total"] == 1
        assert reservations["items"][0]["order_no"] == "FIN002"
        assert reservations["items"][0]["reservation_fee"] == 2.0

    def test_financial_refunds(self, client):
        """退款记录: 仅 REFUNDED 状态订单(o3)"""
        _seed_financial(client._sesh)
        data = client.get("/api/v1/operate/financial/refunds").json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "FIN003"
        assert data["items"][0]["payment_status"] == "refunded"

    def test_financial_charges_empty(self, client):
        """空库: 返回空列表"""
        data = client.get("/api/v1/operate/financial/charges").json()["data"]
        assert data["total"] == 0
        assert data["items"] == []
