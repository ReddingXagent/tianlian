"""
fleet_settlement pay_bill 资金边界守卫测试 (卡2323582c)

覆盖:
- 负数实付金额 → 422 (Field ge=0)
- 超总额实付 → 400 (业务校验)
- 合法部分付款 → 通过, balance = total - paid
- 零元实付 → 允许 (ge=0 含边界)
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


def _auth_headers():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _confirmed_bill(code):
    """创建一个已确认的账单，返回 (bill_id, total_amount)"""
    from app.models.enterprise import Enterprise
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        db.add(Enterprise(name=f"守卫测试{code}", code=code, balance=10000.00))
        db.commit()
    finally:
        db.close()
    ent = db.query(Enterprise).filter(Enterprise.code == code).first()
    ent_id = ent.id

    from datetime import datetime
    from decimal import Decimal
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType
    )
    db = SessionLocal()
    try:
        db.add(ChargingOrder(
            order_no=f"GUARD{code}001",
            station_id=1, device_id=1, user_id=1,
            user_type=UserType.APP, vehicle_id=1, plate_number="豫G00001",
            start_time=datetime.strptime("2025-08-15 10:00:00", "%Y-%m-%d %H:%M:%S"),
            end_time=datetime.strptime("2025-08-15 11:00:00", "%Y-%m-%d %H:%M:%S"),
            duration_minutes=60,
            charged_kwh=Decimal("30.00"),
            electricity_fee=Decimal("20.00"),
            service_fee=Decimal("10.00"),
            parking_fee=Decimal("5.00"),
            total_amount=Decimal("35.00"),
            discount_amount=Decimal("0.00"),
            coupon_amount=Decimal("0.00"),
            paid_amount=Decimal("35.00"),
            payment_method=PaymentMethod.ENTERPRISE,
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
        ))
        db.commit()
    finally:
        db.close()

    gen = client.post(
        "/api/v1/fleet/settlement/bills/generate",
        json={"enterprise_id": ent_id, "bill_period": "2025-08"},
        headers=_auth_headers(),
    )
    assert gen.status_code == 200
    bill_id = gen.json()["data"]["id"]
    total = gen.json()["data"]["total_amount"]
    resp = client.post(f"/api/v1/fleet/settlement/bills/{bill_id}/confirm", json={}, headers=_auth_headers())
    assert resp.status_code == 200
    return bill_id, total


class TestPayBillGuard:
    def test_negative_paid_amount_rejected(self):
        """负数实付 → 422"""
        bill_id, _ = _confirmed_bill("ENT_GUARD1")
        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": -0.01},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_exceed_total_rejected(self):
        """超总额实付 → 400"""
        bill_id, total = _confirmed_bill("ENT_GUARD2")
        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": round(total + 0.01, 2)},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "不能超过账单总额" in resp.json()["message"]

    def test_partial_payment_allowed(self):
        """合法部分付款 → 通过, balance = total - paid"""
        bill_id, total = _confirmed_bill("ENT_GUARD3")
        paid = round(total / 2, 2)
        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": paid},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "paid"
        assert data["paid_amount"] == paid
        assert data["balance_amount"] == round(total - paid, 2)

    def test_zero_paid_allowed(self):
        """零元实付 → 允许 (ge=0 含边界)"""
        bill_id, total = _confirmed_bill("ENT_GUARD4")
        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": 0},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["paid_amount"] == 0
        assert data["balance_amount"] == total
