"""
Phase41 计费引擎测试 - 覆盖 billing 模块全部函数
"""
import pytest
from decimal import Decimal
from datetime import datetime, time

from app.services.billing import (
    calculate_electricity_fee,
    calculate_service_fee,
    calculate_parking_fee,
    calculate_idle_penalty,
    calculate_reservation_fee,
    calculate_total_order,
)


class TestElectricityFee:
    """电费计算测试"""

    def test_basic_electricity_fee(self):
        """基础电费计算"""
        fee = calculate_electricity_fee(Decimal("50"), Decimal("0.8"))
        assert fee == Decimal("40.00")

    def test_zero_consumption(self):
        """零充电量"""
        fee = calculate_electricity_fee(Decimal("0"), Decimal("0.8"))
        assert fee == Decimal("0.00")

    def test_high_precision_price(self):
        """高精度电价"""
        fee = calculate_electricity_fee(Decimal("33.33"), Decimal("0.5286"))
        assert fee == Decimal("17.62")  # 33.33 * 0.5286 = 17.618...

    def test_negative_charged_kwh(self):
        """负数充电量应报错"""
        with pytest.raises(ValueError, match="充电电量不能为负数"):
            calculate_electricity_fee(Decimal("-10"), Decimal("0.8"))

    def test_negative_price(self):
        """负电价应报错"""
        with pytest.raises(ValueError, match="电价不能为负数"):
            calculate_electricity_fee(Decimal("50"), Decimal("-0.1"))

    def test_large_amount(self):
        """大金额计算"""
        fee = calculate_electricity_fee(Decimal("1000"), Decimal("1.5"))
        assert fee == Decimal("1500.00")


class TestServiceFee:
    """服务费计算测试"""

    def test_basic_service_fee(self):
        """基础服务费"""
        fee = calculate_service_fee(Decimal("50"), Decimal("0.5"))
        assert fee == Decimal("25.00")

    def test_zero_rate(self):
        """费率为0"""
        fee = calculate_service_fee(Decimal("100"), Decimal("0"))
        assert fee == Decimal("0.00")

    def test_small_amount(self):
        """小电量计费"""
        fee = calculate_service_fee(Decimal("0.5"), Decimal("0.6"))
        assert fee == Decimal("0.30")

    def test_negative_charged_kwh(self):
        """负数充电量应报错"""
        with pytest.raises(ValueError, match="充电电量不能为负数"):
            calculate_service_fee(Decimal("-10"), Decimal("0.5"))

    def test_negative_rate(self):
        """负服务费率应报错"""
        with pytest.raises(ValueError, match="服务费率不能为负数"):
            calculate_service_fee(Decimal("50"), Decimal("-0.1"))


class TestParkingFee:
    """停车费计算测试"""

    def test_basic_parking_fee(self):
        """基础停车费"""
        fee = calculate_parking_fee(Decimal("2.5"), Decimal("5.0"))
        assert fee == Decimal("12.50")

    def test_free_parking(self):
        """免费停车"""
        fee = calculate_parking_fee(Decimal("2"), Decimal("0"))
        assert fee == Decimal("0.00")

    def test_zero_duration(self):
        """零时长"""
        fee = calculate_parking_fee(Decimal("0"), Decimal("5"))
        assert fee == Decimal("0.00")

    def test_negative_duration(self):
        """负数时长应报错"""
        with pytest.raises(ValueError, match="停车时长不能为负数"):
            calculate_parking_fee(Decimal("-1"), Decimal("5"))

    def test_negative_rate(self):
        """负费率应报错"""
        with pytest.raises(ValueError, match="停车费率不能为负数"):
            calculate_parking_fee(Decimal("1"), Decimal("-2"))

    def test_hourly_rounding(self):
        """四舍五入"""
        fee = calculate_parking_fee(Decimal("1.33"), Decimal("3"))
        assert fee == Decimal("3.99")


class TestIdlePenalty:
    """超时占用费计算测试"""

    def test_basic_idle_penalty(self):
        """基础占用费"""
        fee = calculate_idle_penalty(30, Decimal("0.5"))
        assert fee == Decimal("15.00")

    def test_no_idle(self):
        """零分钟"""
        fee = calculate_idle_penalty(0, Decimal("0.5"))
        assert fee == Decimal("0.00")

    def test_large_idle(self):
        """长时间占用"""
        fee = calculate_idle_penalty(120, Decimal("1.0"))
        assert fee == Decimal("120.00")

    def test_negative_minutes(self):
        """负数分钟应报错"""
        with pytest.raises(ValueError, match="超时分钟数不能为负数"):
            calculate_idle_penalty(-5, Decimal("0.5"))

    def test_negative_rate(self):
        """负费率应报错"""
        with pytest.raises(ValueError, match="占用费率不能为负数"):
            calculate_idle_penalty(10, Decimal("-0.1"))


class TestReservationFee:
    """预约费计算测试"""

    def test_basic_reservation_fee(self):
        """基础预约费（默认费率）"""
        fee = calculate_reservation_fee(30)
        assert fee == Decimal("30.00")

    def test_custom_rate(self):
        """自定义费率"""
        fee = calculate_reservation_fee(60, Decimal("0.5"))
        assert fee == Decimal("30.00")

    def test_zero_duration(self):
        """零时长"""
        fee = calculate_reservation_fee(0, Decimal("1"))
        assert fee == Decimal("0.00")

    def test_negative_duration(self):
        """负数时长应报错"""
        with pytest.raises(ValueError, match="预约时长不能为负数"):
            calculate_reservation_fee(-10, Decimal("1"))

    def test_negative_rate(self):
        """负费率应报错"""
        with pytest.raises(ValueError, match="基础费率不能为负数"):
            calculate_reservation_fee(10, Decimal("-1"))


class TestTotalOrder:
    """综合订单计费测试"""

    def test_full_order_with_all_fees(self):
        """完整订单：含所有费用项"""
        result = calculate_total_order(
            charged_kwh=Decimal("50"),
            electricity_price=Decimal("0.8"),
            service_fee_rate=Decimal("0.5"),
            duration_hours=Decimal("2"),
            parking_fee_per_hour=Decimal("5"),
            idle_minutes=30,
            idle_penalty_per_min=Decimal("0.5"),
            reservation_duration_minutes=15,
            reservation_fee_rate=Decimal("0.5"),
            discount_amount=Decimal("10"),
        )
        # 电费: 50*0.8 = 40
        # 服务费: 50*0.5 = 25
        # 停车费: 2*5 = 10
        # 占用费: 30*0.5 = 15
        # 预约费: 15*0.5 = 7.5
        # 总金额: 40+25+10+15+7.5 = 97.5
        # 折扣: 10 -> 实付: 87.5
        assert result["electricity_fee"] == Decimal("40.00")
        assert result["service_fee"] == Decimal("25.00")
        assert result["parking_fee"] == Decimal("10.00")
        assert result["idle_penalty"] == Decimal("15.00")
        assert result["reservation_fee"] == Decimal("7.50")
        assert result["total_amount"] == Decimal("97.50")
        assert result["discount_amount"] == Decimal("10.00")
        assert result["paid_amount"] == Decimal("87.50")

    def test_electricity_only(self):
        """仅充电费"""
        result = calculate_total_order(
            charged_kwh=Decimal("100"),
            electricity_price=Decimal("1.0"),
            service_fee_rate=Decimal("0"),
        )
        assert result["electricity_fee"] == Decimal("100.00")
        assert result["service_fee"] == Decimal("0.00")
        assert result["parking_fee"] == Decimal("0.00")
        assert result["idle_penalty"] == Decimal("0.00")
        assert result["reservation_fee"] == Decimal("0.00")
        assert result["total_amount"] == Decimal("100.00")
        assert result["paid_amount"] == Decimal("100.00")

    def test_zero_consumption(self):
        """零充电量"""
        result = calculate_total_order(
            charged_kwh=Decimal("0"),
            electricity_price=Decimal("0.8"),
            service_fee_rate=Decimal("0.5"),
        )
        assert result["electricity_fee"] == Decimal("0.00")
        assert result["service_fee"] == Decimal("0.00")
        assert result["total_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")

    def test_full_discount_covers_all(self):
        """折扣覆盖全部费用"""
        result = calculate_total_order(
            charged_kwh=Decimal("10"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0.5"),
            discount_amount=Decimal("100"),
        )
        # 总金额 = 10*1 + 10*0.5 = 15
        # 折扣后 = 15 - 100 不应低于0
        assert result["total_amount"] == Decimal("15.00")
        assert result["paid_amount"] == Decimal("0.00")

    def test_partial_discount(self):
        """部分折扣"""
        result = calculate_total_order(
            charged_kwh=Decimal("20"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0"),
            discount_amount=Decimal("5"),
        )
        assert result["total_amount"] == Decimal("20.00")
        assert result["paid_amount"] == Decimal("15.00")

    def test_decimal_precision(self):
        """Decimal精度测试"""
        result = calculate_total_order(
            charged_kwh=Decimal("0.01"),
            electricity_price=Decimal("0.1234"),
            service_fee_rate=Decimal("0.0567"),
        )
        # 电费: 0.01 * 0.1234 = 0.001234 -> 0.00
        # 服务费: 0.01 * 0.0567 = 0.000567 -> 0.00
        assert result["electricity_fee"] == Decimal("0.00")
        assert result["service_fee"] == Decimal("0.00")
        assert result["total_amount"] == Decimal("0.00")

    def test_negative_discount_raises(self):
        """负数折扣视为非法输入 raise (卡2230298e 缺口1)

        旧行为: 负折扣当加价, paid=total+|d|, 但 total_amount 与费用明细均不含加价
        → 明细合计 ≠ paid_amount, 财务对账不平。
        新契约: 与 5 个独立费用函数的负数契约一致, 直接 raise ValueError。
        """
        with pytest.raises(ValueError, match="折扣不能为负"):
            calculate_total_order(
                charged_kwh=Decimal("10"),
                electricity_price=Decimal("1"),
                service_fee_rate=Decimal("0"),
                discount_amount=Decimal(-5),
            )


# ==========================================
# 数据库模型集成测试
# ==========================================

class TestEnterpriseModels:
    """企业模型 CRUD 集成测试"""

    def test_create_enterprise(self, test_db):
        """创建企业记录"""
        from app.models.enterprise import Enterprise, EnterpriseStatus
        from app.core.database import SessionLocal

        session = test_db["session"]
        ent = Enterprise(
            name="测试物流",
            code="TEST001",
            contact="张三",
            phone="13800138000",
            balance=Decimal("10000.00"),
            credit_limit=Decimal("5000.00"),
        )
        session.add(ent)
        session.commit()
        session.refresh(ent)

        assert ent.id is not None
        assert ent.name == "测试物流"
        assert ent.code == "TEST001"
        assert ent.contact == "张三"
        assert str(ent.balance) == "10000.00"
        assert str(ent.credit_limit) == "5000.00"
        assert ent.status == EnterpriseStatus.ACTIVE

    def test_create_enterprise_vehicle(self, test_db):
        """创建企业车辆"""
        from app.models.enterprise import Enterprise
        from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus
        from app.core.database import SessionLocal

        session = test_db["session"]
        ent = Enterprise(name="车队", code="FLEET01", contact="李四", phone="13900139000")
        session.add(ent)
        session.commit()
        session.refresh(ent)

        ev = EnterpriseVehicle(
            enterprise_id=ent.id,
            plate_number="京A12345",
            vin="LSVAU2A37N2100001",
            driver_name="王五",
            driver_phone="13700137000",
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)

        assert ev.id is not None
        assert ev.plate_number == "京A12345"
        assert ev.vin == "LSVAU2A37N2100001"
        assert ev.status == EnterpriseVehicleStatus.ACTIVE
        assert ev.enterprise_id == ent.id

    def test_enterprise_transaction_flow(self, test_db):
        """企业交易流水：充值→消费→退款"""
        from app.models.enterprise import Enterprise
        from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
        from app.core.database import SessionLocal

        session = test_db["session"]
        ent = Enterprise(name="交易测试", code="TRX01", balance=Decimal("0.00"))
        session.add(ent)
        session.commit()
        session.refresh(ent)

        # 充值
        t1 = EnterpriseTransaction(
            enterprise_id=ent.id,
            type=TransactionType.RECHARGE,
            amount=Decimal("5000.00"),
            balance_after=Decimal("5000.00"),
            remark="充值5000元",
        )
        session.add(t1)
        # 消费
        t2 = EnterpriseTransaction(
            enterprise_id=ent.id,
            type=TransactionType.CONSUME,
            amount=Decimal("100.00"),
            balance_after=Decimal("4900.00"),
            remark="充电消费100元",
        )
        session.add(t2)
        # 退款
        t3 = EnterpriseTransaction(
            enterprise_id=ent.id,
            type=TransactionType.REFUND,
            amount=Decimal("50.00"),
            balance_after=Decimal("4950.00"),
            remark="退款50元",
        )
        session.add(t3)
        session.commit()

        for t in (t1, t2, t3):
            session.refresh(t)

        assert t1.id is not None
        assert t2.type == TransactionType.CONSUME
        assert str(t3.amount) == "50.00"

    def test_create_pricing_rule(self, test_db):
        """创建定价规则"""
        from app.models.pricing_rule import PricingRule, PeriodType
        from app.core.database import SessionLocal

        session = test_db["session"]
        pr = PricingRule(
            name="尖峰时段",
            period_type=PeriodType.PEAK,
            start_time=time(10, 0),
            end_time=time(12, 0),
            electricity_price=Decimal("1.2000"),
            service_fee_rate=Decimal("0.6000"),
            parking_fee_per_hour=Decimal("5.00"),
            idle_penalty_per_min=Decimal("0.50"),
            is_active=True,
        )
        session.add(pr)
        session.commit()
        session.refresh(pr)

        assert pr.id is not None
        assert pr.name == "尖峰时段"
        assert pr.period_type == PeriodType.PEAK
        assert str(pr.electricity_price) == "1.2000"

    def test_create_charging_order(self, test_db):
        """创建充电订单"""
        from app.models.charging_order import (
            ChargingOrder, OrderPaymentStatus, OrderStatus,
            PaymentMethod, UserType,
        )
        from app.core.database import SessionLocal

        session = test_db["session"]
        order = ChargingOrder(
            order_no="CHG20260624000001",
            station_id=1,
            device_id=1,
            user_id=1,
            user_type=UserType.APP,
            vehicle_id=1,
            plate_number="京B12345",
            start_time=datetime(2026, 6, 24, 10, 0),
            end_time=datetime(2026, 6, 24, 11, 0),
            duration_minutes=60,
            start_soc=Decimal("20.0"),
            end_soc=Decimal("80.0"),
            charged_kwh=Decimal("40.00"),
            electricity_fee=Decimal("32.00"),
            service_fee=Decimal("20.00"),
            parking_fee=Decimal("5.00"),
            idle_penalty=Decimal("0.00"),
            reservation_fee=Decimal("0.00"),
            total_amount=Decimal("57.00"),
            discount_amount=Decimal("5.00"),
            paid_amount=Decimal("52.00"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT,
            remark="测试订单",
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        assert order.id is not None
        assert order.order_no == "CHG20260624000001"
        assert str(order.total_amount) == "57.00"
        assert str(order.paid_amount) == "52.00"
        assert order.payment_status == OrderPaymentStatus.PAID
        assert order.order_status == OrderStatus.COMPLETED