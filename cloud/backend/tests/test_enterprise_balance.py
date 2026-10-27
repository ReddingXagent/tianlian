"""
预储值消耗闭环测试 - 扣费原子性 / 透支拦截 / 流水记录

覆盖:
1. 订单完成 → 自动扣减 Enterprise.balance
2. 订单完成 → 写入 EnterpriseTransaction (CONSUME)
3. 余额不足 + 超出 credit_limit → 拒绝扣费
4. 余额不足 + 在 credit_limit 内 → 允许透支
5. deduct_on_order_complete 服务层原子性
6. get_low_balance_enterprises 低余额清单
7. balance-warning API 端点
"""
from decimal import Decimal
import pytest

from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.services.enterprise_balance_service import (
    deduct_on_order_complete,
    check_balance_available,
    get_low_balance_enterprises,
    InsufficientBalanceError,
)


# ─── Helpers ───

def _make_enterprise(db, name="测试车队A", code="ENT001", balance=1000, credit_limit=500):
    ent = Enterprise(
        name=name, code=code, balance=Decimal(str(balance)),
        credit_limit=Decimal(str(credit_limit)), status=EnterpriseStatus.ACTIVE,
    )
    db.add(ent)
    db.flush()
    return ent


def _make_vehicle(db, enterprise_id, plate_number="京A12345", vin=None):
    import uuid
    v = EnterpriseVehicle(
        enterprise_id=enterprise_id,
        plate_number=plate_number,
        vin=vin or f"VIN{uuid.uuid4().hex[:12].upper()}",
        status="active",
    )
    db.add(v)
    db.flush()
    return v


def _make_order(db, paid_amount=100, vehicle_id=1, order_no="CO20260101-001",
                payment_method=PaymentMethod.ENTERPRISE):
    order = ChargingOrder(
        order_no=order_no,
        station_id=1,
        device_id=1,
        user_id=1,
        user_type=UserType.APP,
        vehicle_id=vehicle_id,
        plate_number="京A12345",
        charged_kwh=Decimal("50.00"),
        electricity_fee=Decimal("40.00"),
        service_fee=Decimal("60.00"),
        total_amount=Decimal(str(paid_amount)),
        paid_amount=Decimal(str(paid_amount)),
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.CHARGING,
        payment_method=payment_method,
    )
    db.add(order)
    db.flush()
    return order


# ─── Service Layer Tests ───

class TestDeductOnOrderComplete:
    """扣费原子性测试"""

    def test_deduct_success(self, test_db):
        """正常扣费: 余额充足 → 扣减成功 + 写流水 + 订单标 PAID"""
        db = test_db["session"]
        ent = _make_enterprise(db, balance=1000, credit_limit=0)
        veh = _make_vehicle(db, enterprise_id=ent.id)
        order = _make_order(db, paid_amount=100, vehicle_id=veh.id)

        tx = deduct_on_order_complete(db, order, ent)
        db.commit()

        assert tx is not None
        assert tx.type == TransactionType.CONSUME
        assert tx.amount == Decimal("100.00")
        assert tx.balance_after == Decimal("900.00")
        assert tx.enterprise_id == ent.id
        assert tx.order_id == order.order_no

        # 余额已扣减
        db.refresh(ent)
        assert ent.balance == Decimal("900.00")

        # 订单标记已支付
        db.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PAID

    def test_deduct_zero_amount_writes_zero_tx(self, test_db):
        """金额为 0 → 跳过扣减, 标记 PAID, 但写金额为0的 CONSUME 流水 (审计痕迹)"""
        db = test_db["session"]
        ent = _make_enterprise(db, balance=500, code="ENT_ZERO")
        veh = _make_vehicle(db, enterprise_id=ent.id)
        order = _make_order(db, paid_amount=0, vehicle_id=veh.id, order_no="CO-ZERO")

        tx = deduct_on_order_complete(db, order, ent)
        db.commit()

        # 返回零额流水
        assert tx is not None
        assert tx.amount == Decimal("0.00")
        db.refresh(ent)
        assert ent.balance == Decimal("500.00")
        db.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PAID

        # 零额流水已落库 (审计痕迹)
        txs = db.query(EnterpriseTransaction).filter(
            EnterpriseTransaction.enterprise_id == ent.id,
            EnterpriseTransaction.type == TransactionType.CONSUME,
        ).all()
        assert len(txs) == 1
        assert txs[0].amount == Decimal("0.00")
        assert txs[0].order_id == "CO-ZERO"

    def test_deduct_creates_transaction_record(self, test_db):
        """扣减后应有一条 CONSUME 流水"""
        db = test_db["session"]
        ent = _make_enterprise(db, balance=500, code="ENT_TX")
        veh = _make_vehicle(db, enterprise_id=ent.id)
        order = _make_order(db, paid_amount=80, vehicle_id=veh.id, order_no="CO-TX-01")

        deduct_on_order_complete(db, order, ent)
        db.commit()

        txs = db.query(EnterpriseTransaction).filter(
            EnterpriseTransaction.enterprise_id == ent.id,
            EnterpriseTransaction.type == TransactionType.CONSUME,
        ).all()
        assert len(txs) == 1
        assert txs[0].amount == Decimal("80.00")
        assert txs[0].balance_after == Decimal("420.00")
        assert txs[0].order_id == "CO-TX-01"


class TestOverdraftProtection:
    """透支保护测试"""

    def test_overdraft_allowed_within_credit_limit(self, test_db):
        """余额不足但在 credit_limit 内 → 允许透支"""
        db = test_db["session"]
        ent = _make_enterprise(db, balance=50, credit_limit=200, code="ENT_OD1")
        veh = _make_vehicle(db, enterprise_id=ent.id)
        order = _make_order(db, paid_amount=150, vehicle_id=veh.id, order_no="CO-OD-01")

        # balance=50, amount=150, credit_limit=200 → 50-150=-100 >= -200 ✓
        tx = deduct_on_order_complete(db, order, ent)
        db.commit()

        assert tx is not None
        db.refresh(ent)
        assert ent.balance == Decimal("-100.00")

    def test_overdraft_blocked_beyond_credit_limit(self, test_db):
        """余额不足且超出 credit_limit → 拒绝扣费"""
        db = test_db["session"]
        ent = _make_enterprise(db, balance=50, credit_limit=100, code="ENT_OD2")
        veh = _make_vehicle(db, enterprise_id=ent.id)
        order = _make_order(db, paid_amount=200, vehicle_id=veh.id, order_no="CO-OD-02")
        db.commit()  # Commit setup so rollback won't undo creation

        # balance=50, amount=200, credit_limit=100 → 50-200=-150 < -100 ✗
        with pytest.raises(InsufficientBalanceError) as exc_info:
            deduct_on_order_complete(db, order, ent)

        # 余额不变
        db.rollback()
        # Re-query since rollback detaches instances
        ent_fresh = db.query(Enterprise).filter(Enterprise.id == ent.id).first()
        assert ent_fresh is not None
        assert ent_fresh.balance == Decimal("50.00")
        # 无流水
        txs = db.query(EnterpriseTransaction).filter(
            EnterpriseTransaction.enterprise_id == ent.id
        ).all()
        assert len(txs) == 0

    def test_check_balance_available(self, test_db):
        """单元测试: check_balance_available"""
        db = test_db["session"]
        ent = _make_enterprise(db, balance=100, credit_limit=50, code="ENT_CHK")

        assert check_balance_available(ent, Decimal("80")) is True   # 100-80=20 >= -50
        assert check_balance_available(ent, Decimal("100")) is True  # 100-100=0 >= -50
        assert check_balance_available(ent, Decimal("150")) is True  # 100-150=-50 >= -50
        assert check_balance_available(ent, Decimal("151")) is False # 100-151=-51 < -50


class TestLowBalanceEnterprises:
    """低余额清单测试"""

    def test_get_low_balance_with_fixed_threshold(self, test_db):
        """固定阈值: 返回余额 < threshold 的企业"""
        db = test_db["session"]
        _make_enterprise(db, name="富车队", code="RICH", balance=10000, credit_limit=0)
        _make_enterprise(db, name="穷车队", code="POOR", balance=50, credit_limit=0)
        _make_enterprise(db, name="中车队", code="MID", balance=500, credit_limit=0)

        result = get_low_balance_enterprises(db, threshold=Decimal("600"))
        codes = [r["code"] for r in result]
        assert "POOR" in codes
        assert "MID" in codes
        assert "RICH" not in codes

    def test_get_low_balance_default_credit_line(self, test_db):
        """默认: 余额 < credit_limit 视为低余额"""
        db = test_db["session"]
        _make_enterprise(db, name="透支队", code="OVF", balance=100, credit_limit=500)
        _make_enterprise(db, name="健康队", code="HLT", balance=2000, credit_limit=500)

        result = get_low_balance_enterprises(db, threshold=None)
        codes = [r["code"] for r in result]
        assert "OVF" in codes
        assert "HLT" not in codes

    def test_get_low_balance_pure_prepaid_fallback(self, test_db):
        """缺陷1(纯预付车队预警盲区): credit_limit=0 时绝对阈值兜底, 不能永久沉默。

        buggy 行为: coalesce(balance,0) < coalesce(credit_limit,0) → balance<0,
        而透支保护保证 balance 不会低于 0, 故 credit_limit=0 的纯预付车队
        (balance==0 即余额耗尽) 永远不会进入低余额清单 → 监控失效。
        修复: credit_limit=0 时用绝对预警线兜底 (balance <= 兜底线)。
        """
        db = test_db["session"]
        # 纯预付车队, 余额已耗尽 (balance==0, credit_limit==0)
        _make_enterprise(db, name="预付耗尽队", code="PREPAID_ZERO", balance=0, credit_limit=0)
        # 纯预付车队, 仍有余额
        _make_enterprise(db, name="预付充裕队", code="PREPAID_OK", balance=500, credit_limit=0)

        result = get_low_balance_enterprises(db, threshold=None)
        codes = [r["code"] for r in result]
        # 余额耗尽的纯预付车队必须能被预警 (兜底生效)
        assert "PREPAID_ZERO" in codes
        # 仍有余额的纯预付车队不预警
        assert "PREPAID_OK" not in codes

    def test_low_balance_sorted_by_balance_asc(self, test_db):
        """结果按余额升序"""
        db = test_db["session"]
        _make_enterprise(db, name="A", code="A1", balance=300, credit_limit=0)
        _make_enterprise(db, name="B", code="B1", balance=100, credit_limit=0)

        result = get_low_balance_enterprises(db, threshold=Decimal("500"))
        assert result[0]["balance"] <= result[1]["balance"]


# ─── API Integration Tests ───

def _auth(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json().get("data", {}).get("token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


class TestBalanceWarningAPI:

    def test_balance_warning_endpoint(self, client, seed_users):
        """GET /api/v1/fleet/balance-warning 返回低余额清单"""
        db = client._sesh
        _make_enterprise(db, name="低余额队", code="LOW01", balance=50, credit_limit=200)
        _make_enterprise(db, name="高余额队", code="HIGH01", balance=5000, credit_limit=100)

        headers = _auth(client)
        resp = client.get("/api/v1/fleet/balance-warning", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        codes = [item["code"] for item in body["items"]]
        assert "LOW01" in codes
        assert "HIGH01" not in codes

    def test_balance_warning_with_threshold(self, client, seed_users):
        """传入 threshold 参数过滤"""
        db = client._sesh
        _make_enterprise(db, name="中余额队", code="MID02", balance=800, credit_limit=0)

        headers = _auth(client)
        resp = client.get("/api/v1/fleet/balance-warning?threshold=1000", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["threshold"] == 1000.0
        # 至少包含余额 800 的
        codes = [item["code"] for item in body["items"]]
        assert "MID02" in codes


class TestOrderCompleteDeduction:
    """订单完成 → 自动扣费端到端测试"""

    def test_order_complete_deducts_balance(self, client, seed_users, seed_stations):
        """PUT /charging-orders/{id}/status → completed 时自动扣费"""
        db = client._sesh
        headers = _auth(client)

        # 创建企业 + 车辆
        ent = Enterprise(
            name="扣费测试车队", code="DEDUCT01",
            balance=Decimal("1000"), credit_limit=Decimal("0"),
            status=EnterpriseStatus.ACTIVE,
        )
        db.add(ent)
        db.flush()
        veh = EnterpriseVehicle(
            enterprise_id=ent.id, plate_number="京B99999",
            vin="VINB99999TEST",
            status="active",
        )
        db.add(veh)
        db.flush()

        # 创建充电订单（企业支付）
        order = ChargingOrder(
            order_no="CO-DEDUCT-001",
            station_id=seed_stations["station_a"].id,
            device_id=1,
            vehicle_id=veh.id,
            plate_number="京B99999",
            charged_kwh=Decimal("30"),
            electricity_fee=Decimal("40"),
            service_fee=Decimal("60"),
            total_amount=Decimal("100"),
            paid_amount=Decimal("100"),
            order_status=OrderStatus.CHARGING,
            payment_status=OrderPaymentStatus.UNPAID,
            payment_method=PaymentMethod.ENTERPRISE,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # 完成订单
        resp = client.put(
            f"/api/v1/charging-orders/{order.id}/status",
            json={"status": "completed"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        # 验证余额已扣减
        db.refresh(ent)
        assert ent.balance == Decimal("900.00")

        # 验证流水已写入
        tx = db.query(EnterpriseTransaction).filter(
            EnterpriseTransaction.order_id == "CO-DEDUCT-001"
        ).first()
        assert tx is not None
        assert tx.type == TransactionType.CONSUME
        assert tx.amount == Decimal("100.00")
        assert tx.balance_after == Decimal("900.00")

    def test_order_complete_overdraft_blocked(self, client, seed_users, seed_stations):
        """余额不足且超出透支额度 → 订单完成但保持 unpaid (1d0d8d942 卡8772b963 后不再 402)"""
        db = client._sesh
        headers = _auth(client)

        ent = Enterprise(
            name="透支拦截车队", code="BLOCK01",
            balance=Decimal("50"), credit_limit=Decimal("100"),
            status=EnterpriseStatus.ACTIVE,
        )
        db.add(ent)
        db.flush()
        veh = EnterpriseVehicle(
            enterprise_id=ent.id, plate_number="京C88888",
            vin="VINC88888TEST",
            status="active",
        )
        db.add(veh)
        db.flush()

        order = ChargingOrder(
            order_no="CO-BLOCK-001",
            station_id=seed_stations["station_a"].id,
            device_id=1,
            vehicle_id=veh.id,
            plate_number="京C88888",
            charged_kwh=Decimal("100"),
            electricity_fee=Decimal("100"),
            service_fee=Decimal("100"),
            total_amount=Decimal("200"),
            paid_amount=Decimal("200"),
            order_status=OrderStatus.CHARGING,
            payment_status=OrderPaymentStatus.UNPAID,
            payment_method=PaymentMethod.ENTERPRISE,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # 尝试完成订单 → 1d0d8d942: 余额不足对齐 business_orders 语义,
        # rollback 扣款 + 订单完成保持 unpaid 待人工跟进, 不再 402 拦截
        resp = client.put(
            f"/api/v1/charging-orders/{order.id}/status",
            json={"status": "completed"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert "余额不足待人工跟进" in resp.json()["message"]
        assert resp.json()["data"]["order_status"] == "completed"
        assert resp.json()["data"]["payment_status"] == "unpaid"

        # 余额不变 (扣款已 rollback)
        db.refresh(ent)
        assert ent.balance == Decimal("50.00")

    def test_order_complete_non_enterprise_no_deduction(self, client, seed_users, seed_stations):
        """非企业支付方式 → 正常完成，不扣费"""
        db = client._sesh
        headers = _auth(client)

        order = ChargingOrder(
            order_no="CO-WECHAT-001",
            station_id=seed_stations["station_a"].id,
            device_id=1,
            plate_number="京D77777",
            charged_kwh=Decimal("30"),
            electricity_fee=Decimal("40"),
            service_fee=Decimal("60"),
            total_amount=Decimal("100"),
            paid_amount=Decimal("100"),
            order_status=OrderStatus.CHARGING,
            payment_status=OrderPaymentStatus.UNPAID,
            payment_method=PaymentMethod.WECHAT,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        resp = client.put(
            f"/api/v1/charging-orders/{order.id}/status",
            json={"status": "completed"},
            headers=headers,
        )
        assert resp.status_code == 200
