"""wx_pay 金额真实化测试 (卡 6c8f930c A1)

被测: app/services/wx_pay/payment.py::compute_amount_fen / prepay 金额口径。

修复背景: prepay 旧实现 ``amount_fen = 0`` (mock 硬编码), 真实回调流会把
ChargingOrder.paid_amount 落成 0 元 —— 金额真实化是切换真实支付的前置。

口径 (对齐 billing_engine.calculate_order_fees 实收口径):
  应付(分) = round_half_up((total_amount − discount − coupon − points) × 100)
  - None 字段当 0
  - 负数钳 0 (全折扣覆盖时不向IM-B下负金额单)
  - 元→分用 Decimal ROUND_HALF_UP (0.005 进位), 不用 float (0.29×100 浮点尾差)

DB 策略: 独立 in-memory sqlite Session (PaymentOrder + ChargingOrder),
复用 test_wx_pay_payment.py 脚手架模式。client patch get_wxpay_client 注入
MagicMock, 断言 unified_order 收到的 amount_fen。
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.services.wx_pay import payment as pm
from app.services.wx_pay.client import PrepayResult


@pytest.fixture
def db():
    """独立 in-memory Session, 建 PaymentOrder + ChargingOrder 表。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PaymentOrder.__table__.create(engine)
    ChargingOrder.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _prepay_result(prepay_id="prep_amt"):
    return PrepayResult(
        prepay_id=prepay_id,
        time_stamp="1786047000",
        nonce_str="NONCE0123456789ABCDEF",
        package=f"prepay_id={prepay_id}",
        sign_type="RSA",
        pay_sign="SIGNATUREBASE64",
    )


def _co(order_no="ord_amt", *, total=None, discount=None, coupon=None, points=None):
    """构造带金额字段的 ChargingOrder (未 add, 由用例落库)。None 字段透传模拟未采集。"""
    return ChargingOrder(
        order_no=order_no, station_id=1, device_id=10,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.COMPLETED,
        total_amount=total, discount_amount=discount,
        coupon_amount=coupon, points_amount=points,
    )


# ═══════════════════════════════════════════════════════════════
# compute_amount_fen — 口径
# ═══════════════════════════════════════════════════════════════
class TestComputeAmountFen:
    def test_plain_amount_no_discount(self):
        """总额 99.00 元无优惠 → 9900 分。"""
        assert pm.compute_amount_fen(_co(total=Decimal("99.00"))) == 9900

    def test_all_discounts_subtracted(self):
        """四项全参与: 100 − 10(折扣) − 5(券) − 3(积分) = 82.00 元 → 8200 分。"""
        co = _co(
            total=Decimal("100.00"), discount=Decimal("10.00"),
            coupon=Decimal("5.00"), points=Decimal("3.00"),
        )
        assert pm.compute_amount_fen(co) == 8200

    def test_half_up_rounding_on_half_fen(self):
        """0.005 元 (半分) → ROUND_HALF_UP 进位到 1 分 (非银行家舍入的 0 分)。"""
        assert pm.compute_amount_fen(_co(total=Decimal("0.005"))) == 1

    def test_sub_fen_truncates_toward_rounding(self):
        """0.004 元 → 0 分 (半分以下舍去)。"""
        assert pm.compute_amount_fen(_co(total=Decimal("0.004"))) == 0

    def test_float_input_uses_decimal_not_binary_float(self):
        """float 35.25 (数据库 Numeric 读回可为 float) → 3525 分, 无 0.01 尾差。"""
        assert pm.compute_amount_fen(_co(total=35.25)) == 3525

    def test_two_decimal_scale_rounds_up(self):
        """0.125 元 → 13 分 (ROUND_HALF_UP, 二位小数场景的第三位 5 进位)。"""
        assert pm.compute_amount_fen(_co(total=Decimal("0.125"))) == 13

    # ── 边界: 全折扣 / 负数 / None ──
    def test_full_discount_clamps_to_zero(self):
        """优惠三合计 == 总额 (全免单) → 0 分, 不下负金额单。"""
        co = _co(
            total=Decimal("50.00"), discount=Decimal("20.00"),
            coupon=Decimal("20.00"), points=Decimal("10.00"),
        )
        assert pm.compute_amount_fen(co) == 0

    def test_negative_result_clamps_to_zero(self):
        """优惠合计 > 总额 (负应付) → 钳 0。"""
        co = _co(total=Decimal("10.00"), discount=Decimal("30.00"))
        assert pm.compute_amount_fen(co) == 0

    def test_none_total_treated_as_zero(self):
        """total_amount=None (未结算) → 0。"""
        assert pm.compute_amount_fen(_co(total=None)) == 0

    def test_none_discount_fields_treated_as_zero(self):
        """优惠三项 None → 只减 total, 不抛 TypeError。"""
        co = _co(total=Decimal("12.34"), discount=None, coupon=None, points=None)
        assert pm.compute_amount_fen(co) == 1234

    def test_all_none_is_zero(self):
        """全字段 None → 0 (构造 ChargingOrder 未填金额的默认状态)。"""
        assert pm.compute_amount_fen(_co(total=None, discount=None,
                                         coupon=None, points=None)) == 0

    def test_return_type_is_int(self):
        """返回必须是 int (PaymentOrder.amount_fen 列类型), 非 Decimal/float。"""
        r = pm.compute_amount_fen(_co(total=Decimal("1.00")))
        assert isinstance(r, int)


# ═══════════════════════════════════════════════════════════════
# prepay — 集成: 金额从业务订单取
# ═══════════════════════════════════════════════════════════════
class TestPrepayAmountIntegration:
    def test_prepay_passes_order_amount_to_client_and_row(self, db):
        """prepay → unified_order 收到应付分值 + PaymentOrder.amount_fen 落同值。"""
        db.add(_co(
            "ord_amt1", total=Decimal("100.00"), discount=Decimal("10.00"),
            coupon=Decimal("5.00"), points=Decimal("3.00"),
        ))
        db.commit()
        client = MagicMock()
        client.unified_order.return_value = _prepay_result()
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.prepay(db, order_id="ord_amt1", openid="o1", scene="miniprogram")
        # client 收到的金额 = 应付 8200 分
        assert client.unified_order.call_args.kwargs["amount_fen"] == 8200
        # 落库行同值
        po = db.query(PaymentOrder).filter_by(business_order_no="ord_amt1").one()
        assert po.amount_fen == 8200

    def test_prepay_without_charging_order_amount_zero(self, db):
        """无业务订单行 (纯支付测试场景) → amount_fen=0, 不抛 (容错与 mock 阶段一致)。"""
        client = MagicMock()
        client.unified_order.return_value = _prepay_result()
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.prepay(db, order_id="ord_absent", openid="o1", scene="miniprogram")
        assert client.unified_order.call_args.kwargs["amount_fen"] == 0
        po = db.query(PaymentOrder).filter_by(business_order_no="ord_absent").one()
        assert po.amount_fen == 0

    def test_prepay_reuse_row_amount_refreshed_from_order(self, db):
        """二次 prepay (复用 UNPAID 行): 金额按订单当前值刷新 (结算金额可能已修正)。"""
        db.add(_co("ord_reamt", total=Decimal("50.00")))
        db.commit()
        db.add(PaymentOrder(
            out_trade_no="TL_reamt", business_order_no="ord_reamt",
            openid="o_old", scene=PayScene.MINIPROGRAM,
            sub_mchid=pm.MOCK_DEFAULT_SUB_MCHID, amount_fen=0,
            prepay_id="prep_old", payment_status=PaymentStatus.UNPAID,
        ))
        db.commit()
        client = MagicMock()
        client.unified_order.return_value = _prepay_result("prep_new")
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.prepay(db, order_id="ord_reamt", openid="o_new", scene="miniprogram")
        po = db.query(PaymentOrder).filter_by(business_order_no="ord_reamt").one()
        assert po.amount_fen == 5000
        assert po.prepay_id == "prep_new"


# ═══════════════════════════════════════════════════════════════
# mock 回调金额一致性 — prepay 下单金额与回调金额链路对齐
# ═══════════════════════════════════════════════════════════════
class TestMockNotifyAmountConsistency:
    def test_mock_notify_amount_echoes_prepay_fen(self):
        """mock_client: 回调 body amount.total 原样回显下单金额 → 下单 8200 分,
        回调报 8200 分, handle_notify 金额校验通过 (链路一致性锚点)。"""
        from app.services.wx_pay.mock_client import MockWxPayClient
        import json
        body = json.dumps({
            "out_trade_no": "TL_cons", "transaction_id": "4200CONS",
            "trade_state": "SUCCESS", "amount": {"total": 8200},
        }).encode()
        r = MockWxPayClient().verify_and_decrypt_notify(body, {})
        assert r is not None
        assert r.amount_fen == 8200
