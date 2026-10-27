"""
订单五项费用模型 + fee_items 明细 + 退款流程测试

覆盖:
- 费用计算: 总费用=充电费+服务费+停车费+占桩费+预约费; 实收=总费用-券-积分-折扣
- 结算生成 fee_items 明细行
- 退款全流程: 申请→审批→到账; 申请→拒绝
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.models.charging_order import (
    ChargingOrder, OrderPaymentStatus, OrderStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import (
    OrderFeeItem, RefundRecord, FeeType, RefundStatus,
)
from app.services.billing import calculate_total_order
from app.models.user import User, UserRole

# team scoping（任务卡 1c19b59a）后 router 函数首行调 assert_order_team_access，
# 直接调用须传合法 admin user；否则 user 取默认值 Depends(get_current_user) 未被
# FastAPI 解析，is_platform_admin 在 Depends 对象上取 .role 会抛 AttributeError。
_ADMIN = User(id=1, username="admin", role=UserRole.ADMIN, status="active")


# ==========================================
# 费用计算单测
# ==========================================

class TestFeeCalculation:
    """五项费用计算逻辑"""

    def test_total_equals_five_fees(self):
        """总费用 = 充电费 + 服务费 + 停车费 + 占桩费 + 预约费"""
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
        )
        # 电费: 50*0.8=40, 服务费: 50*0.5=25, 停车费: 2*5=10, 占桩费: 30*0.5=15, 预约费: 15*0.5=7.5
        assert result["electricity_fee"] == Decimal("40.00")
        assert result["service_fee"] == Decimal("25.00")
        assert result["parking_fee"] == Decimal("10.00")
        assert result["idle_penalty"] == Decimal("15.00")
        assert result["reservation_fee"] == Decimal("7.50")
        # 总费用 = 40+25+10+15+7.5 = 97.50
        assert result["total_amount"] == Decimal("97.50")

    def test_paid_equals_total_minus_discount(self):
        """实收 = 总费用 - 折扣"""
        result = calculate_total_order(
            charged_kwh=Decimal("50"),
            electricity_price=Decimal("0.8"),
            service_fee_rate=Decimal("0.5"),
            discount_amount=Decimal("10"),
        )
        # 总费用 = 40 + 25 = 65, 实收 = 65 - 10 = 55
        assert result["total_amount"] == Decimal("65.00")
        assert result["paid_amount"] == Decimal("55.00")

    def test_paid_with_coupon_and_points(self):
        """实收 = 总费用 - 折扣 - 优惠券 - 积分（通过结算API验证）"""
        # 这里先验证 billing 基础: 折扣在 billing 模块中已处理
        result = calculate_total_order(
            charged_kwh=Decimal("100"),
            electricity_price=Decimal("1.0"),
            service_fee_rate=Decimal("0.5"),
            discount_amount=Decimal("30"),
        )
        # 总 = 100 + 50 = 150, 实收 = 150 - 30 = 120
        assert result["total_amount"] == Decimal("150.00")
        assert result["paid_amount"] == Decimal("120.00")

    def test_paid_floor_zero(self):
        """实收不低于0"""
        result = calculate_total_order(
            charged_kwh=Decimal("10"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0"),
            discount_amount=Decimal("100"),
        )
        assert result["paid_amount"] == Decimal("0.00")

    def test_electricity_only(self):
        """仅充电费"""
        result = calculate_total_order(
            charged_kwh=Decimal("30"),
            electricity_price=Decimal("1.2"),
            service_fee_rate=Decimal("0"),
        )
        assert result["electricity_fee"] == Decimal("36.00")
        assert result["total_amount"] == Decimal("36.00")
        assert result["paid_amount"] == Decimal("36.00")


# ==========================================
# 模型字段扩展测试
# ==========================================

class TestChargingOrderExtendedFields:
    """ChargingOrder 新增字段验证"""

    def test_create_order_with_extended_fields(self, test_db):
        """创建带扩展字段的订单"""
        session = test_db["session"]
        order = ChargingOrder(
            order_no="EXT001",
            station_id=1,
            device_id=1,
            user_id=1,
            charged_kwh=Decimal("50"),
            electricity_fee=Decimal("40"),
            service_fee=Decimal("25"),
            parking_fee=Decimal("10"),
            occupancy_fee=Decimal("15"),
            reservation_fee=Decimal("7.5"),
            peak_energy=Decimal("20"),
            flat_energy=Decimal("15"),
            valley_energy=Decimal("10"),
            trough_energy=Decimal("5"),
            total_amount=Decimal("97.5"),
            discount_amount=Decimal("5"),
            coupon_amount=Decimal("3"),
            points_amount=Decimal("2"),
            paid_amount=Decimal("87.5"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        assert order.id is not None
        assert str(order.occupancy_fee) == "15.00"
        assert str(order.peak_energy) == "20.00"
        assert str(order.flat_energy) == "15.00"
        assert str(order.valley_energy) == "10.00"
        assert str(order.trough_energy) == "5.00"
        assert str(order.coupon_amount) == "3.00"
        assert str(order.points_amount) == "2.00"


# ==========================================
# OrderFeeItem 模型测试
# ==========================================

class TestOrderFeeItemModel:
    """费用明细行模型"""

    def test_create_fee_items(self, test_db):
        """为订单创建多条费用明细"""
        session = test_db["session"]
        order = ChargingOrder(
            order_no="FI001",
            station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("50"),
            total_amount=Decimal("97.5"),
            paid_amount=Decimal("97.5"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        items = [
            OrderFeeItem(order_id=order.id, fee_type=FeeType.ELECTRICITY, fee_name="电费",
                         quantity=Decimal("50"), unit_price=Decimal("0.8"), amount=Decimal("40"), unit="kWh"),
            OrderFeeItem(order_id=order.id, fee_type=FeeType.SERVICE, fee_name="服务费",
                         quantity=Decimal("50"), unit_price=Decimal("0.5"), amount=Decimal("25"), unit="kWh"),
            OrderFeeItem(order_id=order.id, fee_type=FeeType.PARKING, fee_name="停车费",
                         quantity=Decimal("2"), unit_price=Decimal("5"), amount=Decimal("10"), unit="小时"),
            OrderFeeItem(order_id=order.id, fee_type=FeeType.OCCUPANCY, fee_name="占桩费",
                         quantity=Decimal("30"), unit_price=Decimal("0.5"), amount=Decimal("15"), unit="分钟"),
            OrderFeeItem(order_id=order.id, fee_type=FeeType.RESERVATION, fee_name="预约费",
                         quantity=Decimal("15"), unit_price=Decimal("0.5"), amount=Decimal("7.5"), unit="分钟"),
        ]
        session.add_all(items)
        session.commit()

        db_items = session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        assert len(db_items) == 5
        types = {i.fee_type for i in db_items}
        assert FeeType.ELECTRICITY in types
        assert FeeType.OCCUPANCY in types
        assert FeeType.RESERVATION in types


# ==========================================
# 退款记录模型测试
# ==========================================

class TestRefundRecordModel:
    """退款记录模型"""

    def test_refund_flow_pending_to_approved(self, test_db):
        """退款: pending → approved → refunded"""
        session = test_db["session"]
        order = ChargingOrder(
            order_no="RF001",
            station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("50"),
            total_amount=Decimal("97.5"),
            paid_amount=Decimal("97.5"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        # pending
        refund = RefundRecord(
            order_id=order.id, user_id=1,
            refund_amount=Decimal("50"),
            reason="充电故障退款",
            status=RefundStatus.PENDING,
        )
        session.add(refund)
        session.commit()
        session.refresh(refund)
        assert refund.status == RefundStatus.PENDING

        # approved
        refund.status = RefundStatus.APPROVED
        refund.reviewer_id = 99
        refund.reviewed_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(refund)
        assert refund.status == RefundStatus.APPROVED

        # refunded
        refund.status = RefundStatus.REFUNDED
        refund.refunded_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(refund)
        assert refund.status == RefundStatus.REFUNDED

    def test_refund_rejected(self, test_db):
        """退款被拒绝"""
        session = test_db["session"]
        order = ChargingOrder(
            order_no="RF002",
            station_id=1, device_id=1, user_id=1,
            total_amount=Decimal("50"),
            paid_amount=Decimal("50"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        refund = RefundRecord(
            order_id=order.id, user_id=1,
            refund_amount=Decimal("50"),
            reason="测试拒绝",
            status=RefundStatus.PENDING,
        )
        session.add(refund)
        session.commit()
        session.refresh(refund)

        refund.status = RefundStatus.REJECTED
        refund.reviewer_id = 99
        refund.reject_reason="不符合退款条件"
        session.commit()
        session.refresh(refund)
        assert refund.status == RefundStatus.REJECTED
        assert refund.reject_reason == "不符合退款条件"


# ==========================================
# 结算API集成测试
# ==========================================

class TestSettleApi:
    """结算API — 生成 fee_items"""

    def test_settle_generates_fee_items(self, test_db):
        """结算后生成正确的费用明细行"""
        from app.api.v1.order_fees import settle_order, SettleRequest

        session = test_db["session"]
        order = ChargingOrder(
            order_no="SET001",
            station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("0"),
            electricity_fee=Decimal("0"),
            service_fee=Decimal("0"),
            total_amount=Decimal("0"),
            paid_amount=Decimal("0"),
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.PENDING,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        req = SettleRequest(
            peak_energy=20, flat_energy=15, valley_energy=10, trough_energy=5,
            peak_price=1.0, flat_price=0.7, valley_price=0.4, trough_price=0.2,
            service_fee_rate=0.5,
            parking_hours=2, parking_rate=5,
            occupancy_minutes=30, occupancy_rate=0.5,
            reservation_minutes=15, reservation_rate=0.5,
            discount_amount=10, coupon_amount=5, points_amount=3,
        )
        resp = settle_order(order.id, req, db=session, user=_ADMIN)
        data = resp["data"]

        # 验证 fee_items 数量: 4(分时电费) + 1(服务费) + 1(停车) + 1(占桩) + 1(预约) + 3(优惠) = 11
        assert len(data["fee_items"]) == 11

        # 总电费 = 20*1 + 15*0.7 + 10*0.4 + 5*0.2 = 20+10.5+4+1 = 35.5
        assert data["total_amount"] == pytest.approx(35.5 + 25 + 10 + 15 + 7.5)  # 93.0

        # 实收 = 93 - 10 - 5 - 3 = 75
        assert data["paid_amount"] == pytest.approx(75.0)

    def test_settle_idempotent(self, test_db):
        """重复结算覆盖旧明细"""
        from app.api.v1.order_fees import settle_order, SettleRequest

        session = test_db["session"]
        order = ChargingOrder(
            order_no="SET002",
            station_id=1, device_id=1, user_id=1,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.PENDING,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        req = SettleRequest(
            flat_energy=50, flat_price=0.8,
            service_fee_rate=0.5,
        )
        settle_order(order.id, req, db=session, user=_ADMIN)
        # 第二次结算
        req2 = SettleRequest(
            flat_energy=100, flat_price=0.6,
            service_fee_rate=0.4,
        )
        resp = settle_order(order.id, req2, db=session, user=_ADMIN)

        items = session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        # 只有2条 (电费+服务费), 旧的被清除
        assert len(items) == 2
        # 验证新值
        order = session.query(ChargingOrder).filter(ChargingOrder.id == order.id).first()
        assert str(order.charged_kwh) == "100.00"


# ==========================================
# 退款API集成测试
# ==========================================

class TestRefundApi:
    """退款流程 API"""

    def _create_paid_order(self, session, order_no="RF-API-001", paid=Decimal("100")):
        order = ChargingOrder(
            order_no=order_no,
            station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("50"),
            total_amount=paid, paid_amount=paid,
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def test_full_refund_flow(self, test_db):
        """完整退款流程: 申请→审批→到账"""
        from app.api.v1.order_fees import (
            create_refund, approve_refund, complete_refund,
            RefundRequest, RefundReview,
        )
        session = test_db["session"]
        order = self._create_paid_order(session)

        # 1. 申请退款 (全额 100, complete 后累计==实付 → REFUNDED)
        req = RefundRequest(refund_amount=100, reason="多收费用")
        resp = create_refund(order.id, req, db=session, user=_ADMIN)
        assert resp["data"]["status"] == "pending"
        refund_id = resp["data"]["id"]

        # 订单状态变为退款中
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDING

        # 2. 审批通过 (缺陷3: reviewer_id 取 token, body.reviewer_id 废弃)
        review = RefundReview(reviewer_id=999)
        resp = approve_refund(order.id, refund_id, review, db=session, user=_ADMIN)
        assert resp["data"]["status"] == "approved"
        # body.reviewer_id=999 被忽略, 落 user.id (_ADMIN.id)
        assert resp["data"]["reviewer_id"] == _ADMIN.id

        # 3. 完成退款
        resp = complete_refund(order.id, refund_id, db=session, user=_ADMIN)
        assert resp["data"]["status"] == "refunded"

        # 订单状态变为已退款
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.REFUNDED

    def test_reject_refund_flow(self, test_db):
        """退款拒绝流程"""
        from app.api.v1.order_fees import (
            create_refund, reject_refund,
            RefundRequest, RefundReview,
        )
        session = test_db["session"]
        order = self._create_paid_order(session, "RF-API-002")

        # 申请退款
        req = RefundRequest(refund_amount=30, reason="测试拒绝")
        resp = create_refund(order.id, req, db=session, user=_ADMIN)
        refund_id = resp["data"]["id"]

        # 拒绝
        review = RefundReview(reviewer_id=88, reject_reason="不符合条件")
        resp = reject_refund(order.id, refund_id, review, db=session, user=_ADMIN)
        assert resp["data"]["status"] == "rejected"
        assert resp["data"]["reject_reason"] == "不符合条件"

        # 订单恢复为已支付
        session.refresh(order)
        assert order.payment_status == OrderPaymentStatus.PAID

    def test_refund_exceeds_paid(self, test_db):
        """退款金额超过实付 (卡 75134a82: 单笔超实付天然落入剩余可退校验)"""
        from app.api.v1.order_fees import create_refund, RefundRequest
        session = test_db["session"]
        order = self._create_paid_order(session, "RF-API-003", paid=Decimal("50"))

        with pytest.raises(Exception) as exc_info:
            create_refund(
                order.id,
                RefundRequest(refund_amount=100, reason="超额退款"),
                db=session,
                user=_ADMIN,
            )
        # 卡 75134a82: 文案改报剩余可退 (50), 不再是旧"不能超过实付金额"
        assert "超过" in str(exc_info.value.detail)
        assert "50.00" in str(exc_info.value.detail)

    def test_refund_unpaid_order(self, test_db):
        """未支付订单不能退款"""
        from app.api.v1.order_fees import create_refund, RefundRequest
        session = test_db["session"]
        order = ChargingOrder(
            order_no="RF-API-004",
            station_id=1, device_id=1,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.PENDING,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        with pytest.raises(Exception) as exc_info:
            create_refund(
                order.id,
                RefundRequest(refund_amount=10, reason="未支付退款"),
                db=session,
                user=_ADMIN,
            )
        assert "未支付" in str(exc_info.value.detail)

    def test_complete_without_approve(self, test_db):
        """未审批不能直接完成"""
        from app.api.v1.order_fees import (
            create_refund, complete_refund,
            RefundRequest,
        )
        session = test_db["session"]
        order = self._create_paid_order(session, "RF-API-005")

        resp = create_refund(order.id, RefundRequest(refund_amount=10, reason="测试"), db=session, user=_ADMIN)
        refund_id = resp["data"]["id"]

        with pytest.raises(Exception) as exc_info:
            complete_refund(order.id, refund_id, db=session, user=_ADMIN)
        assert "approved" in str(exc_info.value.detail)


# ==========================================
# 折扣入口校验 (卡2230298e 缺口2) — SettleRequest.discount_amount 约束
# Pydantic ValidationError 是 FastAPI 422 的来源: body 校验失败 → 422。
# ==========================================

class TestSettleDiscountValidation:
    """discount_amount 必须 >=0 且 <=100000 (百元级单位下足够宽松)。"""

    def test_negative_discount_rejected(self):
        """负折扣 → 422 (ValidationError)。"""
        from pydantic import ValidationError
        from app.api.v1.order_fees import SettleRequest
        with pytest.raises(ValidationError):
            SettleRequest(discount_amount=-1.0)

    def test_oversized_discount_rejected(self):
        """超大折扣 (>100000) → 422。"""
        from pydantic import ValidationError
        from app.api.v1.order_fees import SettleRequest
        with pytest.raises(ValidationError):
            SettleRequest(discount_amount=100001.0)

    def test_upper_bound_accepted(self):
        """上限边界 100000 合法 (闭区间)。"""
        from app.api.v1.order_fees import SettleRequest
        req = SettleRequest(discount_amount=100000.0)
        assert req.discount_amount == 100000.0

    def test_normal_discount_accepted(self):
        """正常折扣不回归。"""
        from app.api.v1.order_fees import SettleRequest
        req = SettleRequest(discount_amount=10.0)
        assert req.discount_amount == 10.0
