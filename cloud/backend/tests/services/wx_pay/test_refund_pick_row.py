"""process_refund 选行 PAID 优先测试 (工作卡 8f15802c)

同一订单多行 PaymentOrder (用户重复下单) 时, process_refund 取
out_trade_no 必须与 payment._pick_payment_row 对齐 (PAID > UNPAID > CLOSED,
同级最新), 不能盲取最新行 — 否则旧行 PAID + 新行 UNPAID 时会拿未支付行
发起渠道退款: 真实IM-B拒退, mock 退到幽灵交易。
"""
from decimal import Decimal

from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.services.wx_pay import MockWxPayClient, reset_wxpay_client_for_testing
from app.services.wx_pay.refund import process_refund


def _order_and_refund(session, order_no):
    order = ChargingOrder(
        order_no=order_no,
        station_id=1, device_id=1, user_id=1,
        charged_kwh=Decimal("10"),
        total_amount=Decimal("30"), paid_amount=Decimal("30"),
        payment_status=OrderPaymentStatus.REFUNDING,
        order_status=OrderStatus.COMPLETED,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    refund = RefundRecord(
        order_id=order.id,
        refund_amount=Decimal("30"),
        reason="选行测试",
        status=RefundStatus.APPROVED,
    )
    session.add(refund)
    session.commit()
    session.refresh(refund)
    return order, refund


def _payment_row(session, business_order_no, out_trade_no, status):
    """按调用顺序种支付行 (后 insert 的 id 更大 = 更"新")。"""
    row = PaymentOrder(
        out_trade_no=out_trade_no,
        business_order_no=business_order_no,
        openid="o-test",
        scene=PayScene.MINIPROGRAM,
        sub_mchid="1900000001",
        amount_fen=3000,
        payment_status=status,
    )
    session.add(row)
    session.commit()
    return row


class _CaptureClient(MockWxPayClient):
    """捕获 client.refund 收到的 out_trade_no (不改成功返回契约)。"""

    captured = None

    def refund(self, **kwargs):
        type(self).captured = kwargs.get("out_trade_no")
        return super().refund(**kwargs)


class TestRefundPicksPaidRow:
    """process_refund 选行 PAID 优先对齐 _pick_payment_row (卡 8f15802c)。"""

    def test_paid_old_row_preferred_over_unpaid_new_row(self, test_db):
        """旧行 PAID + 新行 UNPAID → 必须用 PAID 行的 out_trade_no (盲取最新会拿错)。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-PICK-001")
        _payment_row(session, order.order_no, "TL_OLD_PAID", PaymentStatus.PAID)
        _payment_row(session, order.order_no, "TL_NEW_UNPAID", PaymentStatus.UNPAID)

        _CaptureClient.captured = None
        reset_wxpay_client_for_testing(_CaptureClient())
        try:
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, str), "成功路径应返回 refund_id str"
        assert _CaptureClient.captured == "TL_OLD_PAID", \
            "退款必须用 PAID 行的 out_trade_no, 而非盲取最新 UNPAID 行"

    def test_single_paid_row_normal(self, test_db):
        """单行 PAID → 正常用该行 out_trade_no。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-PICK-002")
        _payment_row(session, order.order_no, "TL_ONLY_PAID", PaymentStatus.PAID)

        _CaptureClient.captured = None
        reset_wxpay_client_for_testing(_CaptureClient())
        try:
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, str)
        assert _CaptureClient.captured == "TL_ONLY_PAID"

    def test_no_payment_row_falls_back_to_local_no(self, test_db):
        """无支付行 → mock 降级 TL_LOCAL_ 前缀本地单号, 行为不变。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-PICK-003")

        _CaptureClient.captured = None
        reset_wxpay_client_for_testing(_CaptureClient())
        try:
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, str)
        assert _CaptureClient.captured == f"TL_LOCAL_{order.order_no}"

    def test_same_priority_picks_latest(self, test_db):
        """同为 PAID 时取最新行 (id 最大), 与 _pick_payment_row 语义一致。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-PICK-004")
        _payment_row(session, order.order_no, "TL_PAID_OLDER", PaymentStatus.PAID)
        _payment_row(session, order.order_no, "TL_PAID_NEWER", PaymentStatus.PAID)

        _CaptureClient.captured = None
        reset_wxpay_client_for_testing(_CaptureClient())
        try:
            process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert _CaptureClient.captured == "TL_PAID_NEWER"
