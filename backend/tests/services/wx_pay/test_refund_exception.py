"""process_refund 渠道异常保护测试 (工作卡 692b3df7)

验证 client.refund 抛异常时 process_refund:
1. 不裸抛 (调用方拿不到 500, 可决定降级策略)
2. 返回结构化错误 dict (含 status / error 字段)
3. 记录 logger.error (不吞日志)

注: 真实 RealWxPayClient.refund 经 httpx 调IM-B API, 网络/超时/解析异常约定
转 WxPayError (见 client.WxPayError docstring); mock 阶段不触发, 但 caller 侧
按本契约兜底, 真实接入切换时零行为漂移。
"""
import logging
from decimal import Decimal

import pytest

from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.services.wx_pay import MockWxPayClient, reset_wxpay_client_for_testing
from app.services.wx_pay.refund import process_refund


def _order_and_refund(session, order_no="RE-EXC-001"):
    """种子订单 + 一条 approved 退款记录 (process_refund 仅需 order/refund 入参)。"""
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
        reason="渠道异常测试",
        status=RefundStatus.APPROVED,
    )
    session.add(refund)
    session.commit()
    session.refresh(refund)
    return order, refund


class _ExplodingClient(MockWxPayClient):
    """refund 抛通用 Exception (模拟真实 httpx 网络异常未被转 WxPayError 的最坏情况)。"""

    def refund(self, **kwargs):
        raise Exception("模拟IM-B退款接口网络故障")


class _WxPayErrorClient(MockWxPayClient):
    """refund 抛 WxPayError (真实实现的契约异常)。"""

    def refund(self, **kwargs):
        from app.services.wx_pay.client import WxPayError
        raise WxPayError("IM-B退款失败: 商户证书过期")


class TestRefundExceptionProtection:
    """process_refund 渠道异常保护 (卡 692b3df7)。"""

    def test_generic_exception_not_bare_raised(self, test_db, caplog):
        """client.refund 抛通用 Exception → process_refund 不裸抛, 返回结构化错误。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-EXC-001")
        reset_wxpay_client_for_testing(_ExplodingClient())
        try:
            with caplog.at_level(logging.ERROR, logger="app.services.wx_pay.refund"):
                result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, dict), "渠道异常应返回结构化错误 dict 而非裸抛"
        assert result.get("status") == "error"
        assert "error" in result
        assert any(r.levelno == logging.ERROR for r in caplog.records), \
            "渠道异常应记 logger.error"

    def test_wxpayerror_not_bare_raised(self, test_db):
        """client.refund 抛 WxPayError → process_refund 同样兜底, 返回结构化错误。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-EXC-002")
        reset_wxpay_client_for_testing(_WxPayErrorClient())
        try:
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, dict)
        assert result.get("status") == "error"
        assert "error" in result

    def test_error_result_contains_out_refund_no(self, test_db):
        """错误结果含 out_refund_no (调用方据此幂等重试)。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-EXC-003")
        reset_wxpay_client_for_testing(_ExplodingClient())
        try:
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert "out_refund_no" in result
        assert result["out_refund_no"].startswith("TLR_")

    def test_success_path_returns_refund_id_str(self, test_db):
        """成功路径保持返回 str refund_id (不破坏既有调用契约 / test_refund_safety)。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-EXC-004")
        reset_wxpay_client_for_testing(MockWxPayClient())
        try:
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, str)
        assert result.startswith("4200")
