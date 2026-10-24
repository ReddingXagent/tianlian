"""
车队对账结算 API 测试 - Phase45

覆盖:
- 账单生成（按账期聚合 charging_orders）
- 账单列表/详情
- 账单确认 (pending → confirmed)
- 账单付款 (confirmed → paid)
- 账单明细列表
- 发票申请/列表
- 账单聚合单测（金额汇总正确性）
"""
import pytest
from decimal import Decimal
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_enterprise(name="测试运输公司", code="ENT_S001"):
    from app.models.enterprise import Enterprise
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        ent = Enterprise(name=name, code=code, balance=10000.00)
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.id
    finally:
        db.close()


def _create_vehicle(enterprise_id, plate_number="豫A99999"):
    from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        v = EnterpriseVehicle(
            enterprise_id=enterprise_id,
            plate_number=plate_number,
            vin=f"VIN{plate_number[-5:]}X",
            status=EnterpriseVehicleStatus.ACTIVE,
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        return v.id
    finally:
        db.close()


def _create_charging_orders(enterprise_id, plate_number, count=3, period="2025-07"):
    """创建若干充电订单用于聚合测试"""
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType
    )
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        orders = []
        for i in range(count):
            o = ChargingOrder(
                order_no=f"CO{period.replace('-', '')}{i:03d}",
                station_id=1,
                device_id=1,
                user_id=1,
                user_type=UserType.APP,
                vehicle_id=1,
                plate_number=plate_number,
                start_time=datetime.strptime(f"{period}-15 10:00:00", "%Y-%m-%d %H:%M:%S"),
                end_time=datetime.strptime(f"{period}-15 11:00:00", "%Y-%m-%d %H:%M:%S"),
                duration_minutes=60,
                charged_kwh=Decimal(f"{30 + i * 5}.00"),
                electricity_fee=Decimal(f"{20 + i * 3}.00"),
                service_fee=Decimal(f"{10 + i * 2}.00"),
                parking_fee=Decimal("5.00"),
                total_amount=Decimal(f"{35 + i * 5}.00"),
                discount_amount=Decimal("0.00"),
                coupon_amount=Decimal("0.00"),
                paid_amount=Decimal(f"{35 + i * 5}.00"),
                payment_method=PaymentMethod.ENTERPRISE,
                order_status=OrderStatus.COMPLETED,
                payment_status=OrderPaymentStatus.PAID,
            )
            db.add(o)
            orders.append(o)
        db.commit()
        for o in orders:
            db.refresh(o)
        return orders
    finally:
        db.close()


# ========== 账单生成 ==========

class TestBillGeneration:
    """账单生成相关测试"""

    def test_generate_bill_empty_period(self):
        """生成空账期账单（无订单）"""
        ent_id = _create_enterprise()
        resp = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-01"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bill_no"].startswith("FSB202501")
        assert data["enterprise_id"] == ent_id
        assert data["bill_period"] == "2025-01"
        assert data["total_orders"] == 0
        assert data["status"] == "pending"

    def test_generate_bill_with_orders(self):
        """生成含订单的账单 - 验证聚合正确性"""
        ent_id = _create_enterprise(code="ENT_S002")
        _create_vehicle(ent_id, "豫B88888")
        orders = _create_charging_orders(ent_id, "豫B88888", count=3, period="2025-07")

        resp = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_orders"] == 3
        # 验证聚合金额
        expected_energy = sum(o.charged_kwh for o in orders)
        expected_charge_fee = sum(o.electricity_fee for o in orders)
        expected_service_fee = sum(o.service_fee for o in orders)
        expected_total = sum(o.total_amount for o in orders)

        assert data["total_energy_kwh"] == float(expected_energy)
        assert data["total_charge_fee"] == float(expected_charge_fee)
        assert data["total_service_fee"] == float(expected_service_fee)
        assert data["total_amount"] == float(expected_total)

    def test_generate_duplicate_bill(self):
        """重复生成同一账期账单应返回400"""
        ent_id = _create_enterprise(code="ENT_S003")
        payload = {"enterprise_id": ent_id, "bill_period": "2025-03"}
        resp1 = client.post("/api/v1/fleet/settlement/bills/generate", json=payload, headers=_auth_headers())
        assert resp1.status_code == 200
        resp2 = client.post("/api/v1/fleet/settlement/bills/generate", json=payload, headers=_auth_headers())
        assert resp2.status_code == 400

    def test_generate_bill_nonexistent_enterprise(self):
        """不存在的企业"""
        resp = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": 99999, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


# ========== 账单列表/详情 ==========

class TestBillListAndDetail:
    """账单列表和详情测试"""

    def test_list_bills_empty(self):
        """空账单列表"""
        resp = client.get("/api/v1/fleet/settlement/bills", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []

    def test_list_bills_with_filter(self):
        """按企业筛选账单列表"""
        ent1 = _create_enterprise(code="ENT_L001")
        ent2 = _create_enterprise(name="第二公司", code="ENT_L002")
        client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent1, "bill_period": "2025-04"},
            headers=_auth_headers(),
        )
        client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent2, "bill_period": "2025-04"},
            headers=_auth_headers(),
        )

        resp = client.get(
            f"/api/v1/fleet/settlement/bills?enterprise_id={ent1}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["enterprise_id"] == ent1

    def test_get_bill_detail(self):
        """获取单条账单详情"""
        ent_id = _create_enterprise(code="ENT_D001")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-05"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp = client.get(f"/api/v1/fleet/settlement/bills/{bill_id}", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == bill_id
        assert data["bill_period"] == "2025-05"

    def test_get_bill_not_found(self):
        """获取不存在的账单"""
        resp = client.get("/api/v1/fleet/settlement/bills/99999", headers=_auth_headers())
        assert resp.status_code == 404


# ========== 账单确认/付款 ==========

class TestBillConfirmAndPay:
    """账单确认和付款状态流转测试"""

    def test_confirm_bill(self):
        """确认账单 pending → confirmed"""
        ent_id = _create_enterprise(code="ENT_C001")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-06"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/confirm",
            json={"remark": "已核对"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "confirmed"
        assert data["confirmed_at"] is not None
        assert data["remark"] == "已核对"

    def test_pay_bill_before_confirm(self):
        """未确认的账单不能付款"""
        ent_id = _create_enterprise(code="ENT_C002")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-06"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": 100.00},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_confirm_bill_twice(self):
        """重复确认应返回400"""
        ent_id = _create_enterprise(code="ENT_C003")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-06"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp1 = client.post(f"/api/v1/fleet/settlement/bills/{bill_id}/confirm", json={}, headers=_auth_headers())
        assert resp1.status_code == 200
        resp2 = client.post(f"/api/v1/fleet/settlement/bills/{bill_id}/confirm", json={}, headers=_auth_headers())
        assert resp2.status_code == 400

    def test_pay_bill_full(self):
        """全额付款 confirmed → paid"""
        ent_id = _create_enterprise(code="ENT_C004")
        _create_vehicle(ent_id, "豫C12345")
        _create_charging_orders(ent_id, "豫C12345", count=2, period="2025-07")

        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]
        total = gen.json()["data"]["total_amount"]

        # 确认
        client.post(f"/api/v1/fleet/settlement/bills/{bill_id}/confirm", json={}, headers=_auth_headers())
        # 付款
        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": total},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "paid"
        assert data["paid_at"] is not None
        assert data["paid_amount"] == total
        assert data["balance_amount"] == 0

    def test_pay_bill_partial(self):
        """部分付款 - 余额大于0"""
        ent_id = _create_enterprise(code="ENT_C005")
        _create_vehicle(ent_id, "豫D56789")
        _create_charging_orders(ent_id, "豫D56789", count=2, period="2025-07")

        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]
        total = gen.json()["data"]["total_amount"]

        client.post(f"/api/v1/fleet/settlement/bills/{bill_id}/confirm", json={}, headers=_auth_headers())
        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/pay",
            json={"paid_amount": total / 2},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "paid"
        assert data["balance_amount"] > 0


# ========== 账单明细 ==========

class TestBillDetails:
    """账单明细测试"""

    def test_list_details_with_orders(self):
        """获取含订单的账单明细"""
        ent_id = _create_enterprise(code="ENT_DT001")
        _create_vehicle(ent_id, "豫E11111")
        _create_charging_orders(ent_id, "豫E11111", count=3, period="2025-07")

        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp = client.get(
            f"/api/v1/fleet/settlement/bills/{bill_id}/details",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 3
        # 验证明细字段
        item = data["items"][0]
        assert "order_no" in item
        assert "energy_kwh" in item
        assert "charge_fee" in item
        assert "service_fee" in item

    def test_list_details_empty(self):
        """空账单的明细列表"""
        ent_id = _create_enterprise(code="ENT_DT002")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-08"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp = client.get(
            f"/api/v1/fleet/settlement/bills/{bill_id}/details",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []


# ========== 发票申请 ==========

class TestInvoiceRequest:
    """发票申请测试"""

    def test_request_invoice(self):
        """提交发票申请"""
        ent_id = _create_enterprise(code="ENT_I001")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-09"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/invoice",
            json={
                "title": "测试运输有限公司",
                "tax_no": "91110000123456789X",
                "invoice_type": "general",
                "email": "finance@test.com",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "测试运输有限公司"
        assert data["tax_no"] == "91110000123456789X"
        assert data["status"] == "pending"
        assert data["bill_id"] == bill_id

    def test_list_invoices(self):
        """获取发票申请列表"""
        ent_id = _create_enterprise(code="ENT_I002")
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-10"},
            headers=_auth_headers(),
        )
        bill_id = gen.json()["data"]["id"]

        client.post(
            f"/api/v1/fleet/settlement/bills/{bill_id}/invoice",
            json={"title": "公司A", "invoice_type": "general"},
            headers=_auth_headers(),
        )

        resp = client.get("/api/v1/fleet/settlement/invoices", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1

    def test_list_invoices_by_enterprise(self):
        """按企业筛选发票列表"""
        ent1 = _create_enterprise(code="ENT_I003")
        ent2 = _create_enterprise(name="公司B", code="ENT_I004")

        for eid, period in [(ent1, "2025-11"), (ent2, "2025-11")]:
            gen = client.post(
                "/api/v1/fleet/settlement/bills/generate",
                json={"enterprise_id": eid, "bill_period": period},
                headers=_auth_headers(),
            )
            bid = gen.json()["data"]["id"]
            client.post(
                f"/api/v1/fleet/settlement/bills/{bid}/invoice",
                json={"title": f"公司{eid}"},
                headers=_auth_headers(),
            )

        resp = client.get(
            f"/api/v1/fleet/settlement/invoices?enterprise_id={ent1}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert all(i["enterprise_id"] == ent1 for i in data["items"])


# ========== 账单聚合单测 ==========

class TestBillAggregation:
    """账单聚合逻辑单元测试 - 验证从 charging_orders 到 bill 的金额汇总正确性"""

    def test_aggregation_totals_match_sum_of_orders(self):
        """账单总金额 = 所有订单金额之和"""
        from app.models.settlement import FleetSettlementBill, FleetSettlementDetail
        from app.models.charging_order import ChargingOrder
        from app.core.database import SessionLocal

        ent_id = _create_enterprise(code="ENT_A001")
        _create_vehicle(ent_id, "豫F22222")
        orders = _create_charging_orders(ent_id, "豫F22222", count=5, period="2025-07")

        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        assert gen.status_code == 200
        bill_data = gen.json()["data"]

        # 直接从数据库验证
        db = SessionLocal()
        try:
            bill = db.query(FleetSettlementBill).filter_by(id=bill_data["id"]).first()
            details = db.query(FleetSettlementDetail).filter_by(bill_id=bill.id).all()

            # 明细数 = 订单数
            assert len(details) == 5

            # 汇总: sum(detail.field) == bill.field
            for field_name, detail_field in [
                ("total_energy_kwh", "energy_kwh"),
                ("total_charge_fee", "charge_fee"),
                ("total_service_fee", "service_fee"),
                ("total_parking_fee", "parking_fee"),
                ("total_amount", "total_amount"),
            ]:
                detail_sum = sum(getattr(d, detail_field) for d in details)
                bill_val = getattr(bill, field_name)
                assert bill_val == detail_sum, f"{field_name}: bill={bill_val} != sum(details)={detail_sum}"

            # 验证明细与原始订单对应
            order_map = {o.id: o for o in orders}
            for d in details:
                src = order_map[d.order_id]
                assert d.energy_kwh == src.charged_kwh
                assert d.charge_fee == src.electricity_fee
                assert d.service_fee == src.service_fee
                assert d.total_amount == src.total_amount
        finally:
            db.close()

    def test_cross_enterprise_isolation(self):
        """卡 3a8d4dc5: 企业A生成账单不得吞并企业B的企业支付订单"""
        ent_a = _create_enterprise(name="企业A", code="ENT_X001")
        ent_b = _create_enterprise(name="企业B", code="ENT_X002")
        vid_a = _create_vehicle(ent_a, "豫H11111")
        vid_b = _create_vehicle(ent_b, "豫H22222")
        _create_vehicle(ent_b, "豫H33333")

        # 企业B的订单: 1笔按vehicle_id归属, 1笔按车牌归属, 1笔无车牌无vehicle_id但enterprise支付
        from app.models.charging_order import (
            ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType
        )
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            base = dict(
                station_id=1, device_id=1, user_id=1, user_type=UserType.APP,
                start_time=datetime.strptime("2025-07-15 10:00:00", "%Y-%m-%d %H:%M:%S"),
                end_time=datetime.strptime("2025-07-15 11:00:00", "%Y-%m-%d %H:%M:%S"),
                duration_minutes=60, charged_kwh=Decimal("30.00"),
                electricity_fee=Decimal("20.00"), service_fee=Decimal("10.00"),
                parking_fee=Decimal("0.00"), total_amount=Decimal("30.00"),
                discount_amount=Decimal("0.00"), coupon_amount=Decimal("0.00"),
                paid_amount=Decimal("30.00"),
                payment_method=PaymentMethod.ENTERPRISE,
                order_status=OrderStatus.COMPLETED,
                payment_status=OrderPaymentStatus.PAID,
            )
            db.add(ChargingOrder(order_no="COB0001", vehicle_id=vid_b, plate_number=None, **base))
            db.add(ChargingOrder(order_no="COB0002", vehicle_id=None, plate_number="豫H33333", **base))
            db.add(ChargingOrder(order_no="COB0003", vehicle_id=None, plate_number=None, **base))
            db.commit()
        finally:
            db.close()

        # 企业A生成账单: 不得并入企业B的任何订单
        gen_a = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_a, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        assert gen_a.status_code == 200
        data_a = gen_a.json()["data"]
        assert data_a["total_orders"] == 0
        assert data_a["total_amount"] == 0

        # 企业B生成账单: 只并入能确权归属B的订单(vehicle_id或车牌反查到B)
        gen_b = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_b, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        assert gen_b.status_code == 200
        data_b = gen_b.json()["data"]
        assert data_b["total_orders"] == 2
        assert data_b["total_amount"] == 60.0

    def test_aggregation_cross_period_exclusion(self):
        """账单不包含其他账期的订单"""
        ent_id = _create_enterprise(code="ENT_A002")
        _create_vehicle(ent_id, "豫G33333")
        # 创建7月和8月的订单
        _create_charging_orders(ent_id, "豫G33333", count=2, period="2025-07")
        _create_charging_orders(ent_id, "豫G33333", count=3, period="2025-08")

        # 只生成7月账单
        gen = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-07"},
            headers=_auth_headers(),
        )
        assert gen.status_code == 200
        assert gen.json()["data"]["total_orders"] == 2

        # 再生成8月账单
        gen2 = client.post(
            "/api/v1/fleet/settlement/bills/generate",
            json={"enterprise_id": ent_id, "bill_period": "2025-08"},
            headers=_auth_headers(),
        )
        assert gen2.status_code == 200
        assert gen2.json()["data"]["total_orders"] == 3
