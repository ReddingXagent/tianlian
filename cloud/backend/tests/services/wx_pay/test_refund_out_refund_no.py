"""卡 69fe6381 — 退款渠道幂等键 out_refund_no 持久化测试。

缺陷: process_refund 每次随机生成 out_refund_no 且不落库 → 渠道已受理但
响应丢失时, 重试会发起新单号的第二笔退款 → 重复打款 (P1 资金安全)。

修复后契约 (HTTP 契约/路由/响应结构不变):
- process_refund 优先复用 refund.out_refund_no, 否则生成新号;
- 成功/失败路径都把 out_refund_no 写进传入的 refund 对象 (随 commit 落库);
- complete_refund 渠道失败抛 502 前保证 refund.out_refund_no 已落库,
  重试复用同号 → 渠道侧幂等去重。
"""
import logging
from decimal import Decimal

import pytest

from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
from app.models.order_fee_item import RefundRecord, RefundStatus
from app.services.wx_pay import MockWxPayClient, reset_wxpay_client_for_testing
from app.services.wx_pay.refund import process_refund


def _order_and_refund(session, order_no="RE-IDEM-001"):
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
        reason="幂等键测试",
        status=RefundStatus.APPROVED,
    )
    session.add(refund)
    session.commit()
    session.refresh(refund)
    return order, refund


class _RecordingClient(MockWxPayClient):
    """记录每次 refund 调用的 out_refund_no, 供断言复用/换号。"""

    def __init__(self):
        super().__init__()
        self.seen_out_refund_no = []

    def refund(self, **kwargs):
        self.seen_out_refund_no.append(kwargs["out_refund_no"])
        return super().refund(**kwargs)


class _FlakyClient(_RecordingClient):
    """第一次抛渠道异常 (模拟已受理但响应丢失), 第二次成功。"""

    def refund(self, **kwargs):
        self.seen_out_refund_no.append(kwargs["out_refund_no"])
        if len(self.seen_out_refund_no) == 1:
            from app.services.wx_pay.client import WxPayError
            raise WxPayError("IM-B退款接口超时(响应丢失)")
        return MockWxPayClient.refund(self, **kwargs)


class _ExplodingClient(_RecordingClient):
    """refund 恒抛异常 (失败路径断言 out_refund_no 附到 refund 对象)。"""

    def refund(self, **kwargs):
        self.seen_out_refund_no.append(kwargs["out_refund_no"])
        from app.services.wx_pay.client import WxPayError
        raise WxPayError("渠道持续故障")





class TestOutRefundNoIdempotency:
    """process_refund / complete_refund 的 out_refund_no 幂等 (卡 69fe6381)。"""

    def test_reuses_persisted_out_refund_no(self, test_db, monkeypatch):
        """(a) refund.out_refund_no 已存在 → 复用, 不再生成新号。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-IDEM-001")
        refund.out_refund_no = "TLR_EXISTING_0001"
        session.commit()

        client = _RecordingClient()
        reset_wxpay_client_for_testing(client)
        try:
            monkeypatch.setattr(
                "app.services.wx_pay.refund.generate_out_refund_no",
                lambda: "TLR_SHOULD_NOT_APPEAR",
            )
            result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert not isinstance(result, dict)
        assert client.seen_out_refund_no == ["TLR_EXISTING_0001"], "已持久化号必须复用"
        assert refund.out_refund_no == "TLR_EXISTING_0001"

    def test_generates_and_attaches_new_out_refund_no(self, test_db, monkeypatch):
        """无持久化号 → 生成新号并写进 refund 对象 (可随 commit 落库)。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-IDEM-002")
        assert refund.out_refund_no is None

        client = _RecordingClient()
        reset_wxpay_client_for_testing(client)
        try:
            monkeypatch.setattr(
                "app.services.wx_pay.refund.generate_out_refund_no",
                lambda: "TLR_NEW_0002",
            )
            process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert client.seen_out_refund_no == ["TLR_NEW_0002"]
        assert refund.out_refund_no == "TLR_NEW_0002"
        session.commit()
        session.refresh(refund)
        assert refund.out_refund_no == "TLR_NEW_0002"

    def test_failure_path_attaches_out_refund_no(self, test_db, caplog):
        """(c) 渠道异常路径 out_refund_no 也写进 refund 对象 (可随 commit 落库)。"""
        session = test_db["session"]
        order, refund = _order_and_refund(session, "RE-IDEM-003")

        client = _ExplodingClient()
        reset_wxpay_client_for_testing(client)
        try:
            with caplog.at_level(logging.ERROR, logger="app.services.wx_pay.refund"):
                result = process_refund(session, order=order, refund=refund)
        finally:
            reset_wxpay_client_for_testing(None)

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert refund.out_refund_no == result["out_refund_no"]
        assert refund.out_refund_no in client.seen_out_refund_no
        # 随 commit 落库
        session.commit()
        session.refresh(refund)
        assert refund.out_refund_no == result["out_refund_no"]

    def test_complete_refund_retry_reuses_same_out_refund_no(self, test_db):
        """(b) 渠道失败后重试 complete, 两次 out_refund_no 一致 (否则重复打款)。"""
        from app.api.v1.order_fees import (
            create_refund, approve_refund, complete_refund,
            RefundRequest, RefundReview,
        )
        session = test_db["session"]
        from tests.test_order_fees import _ADMIN
        order = ChargingOrder(
            order_no="RE-IDEM-004",
            station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("50"),
            total_amount=Decimal("100"), paid_amount=Decimal("100"),
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        req = RefundRequest(refund_amount=100, reason="幂等重试测试")
        resp = create_refund(order.id, req, db=session, user=_ADMIN)
        refund_id = resp["data"]["id"]
        approve_refund(order.id, refund_id, RefundReview(reviewer_id=1), db=session, user=_ADMIN)

        client = _FlakyClient()
        reset_wxpay_client_for_testing(client)
        try:
            # 第一次: 渠道异常 → 502, 退款保持 APPROVED
            with pytest.raises(Exception) as exc_info:
                complete_refund(order.id, refund_id, db=session, user=_ADMIN)
            from fastapi import HTTPException
            assert isinstance(exc_info.value, HTTPException)
            assert exc_info.value.status_code == 502

            # 失败后 out_refund_no 已随 commit 落库
            session.expire_all()
            refund = session.query(RefundRecord).filter(RefundRecord.id == refund_id).first()
            first_no = refund.out_refund_no
            assert first_no == client.seen_out_refund_no[0]
            assert refund.status == RefundStatus.APPROVED, "失败后仍 APPROVED 可重试"

            # 第二次: 成功, 必须复用同一 out_refund_no
            resp2 = complete_refund(order.id, refund_id, db=session, user=_ADMIN)
            assert resp2["data"]["status"] == "refunded"
        finally:
            reset_wxpay_client_for_testing(None)

        assert len(client.seen_out_refund_no) == 2
        assert client.seen_out_refund_no[0] == client.seen_out_refund_no[1], \
            "重试必须复用同一 out_refund_no, 否则渠道重复打款"
        session.expire_all()
        refund = session.query(RefundRecord).filter(RefundRecord.id == refund_id).first()
        assert refund.out_refund_no == first_no
