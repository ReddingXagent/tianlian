"""handle_notify 资金安全校验测试 (卡 6c8f930c A1)

被测: app/services/wx_pay/payment.py::handle_notify SUCCESS 分支的
金额/身份校验 (上轮深读发现的资金安全缺口, 本卡必做)。

缺口背景: 旧实现 SUCCESS 回调只要验签通过就落 PAID, 不校验回调金额 vs
PaymentOrder.amount_fen。金额真实化后 (amount_fen 落真实应付), 回调金额
校验是防 "金额篡改/错单" 的最后一道闸:
- 回调金额 != PaymentOrder.amount_fen → 拒绝落 PAID + logger.error 告警
- notify 回传 appid/sub_mchid 时与订单行比对, 不符同样拒绝
- 校验失败不重试同类回调 (重试必然同值, 无意义), ACK SUCCESS + notify_count
  累加, 状态保持 UNPAID —— 与未知单 ACK 先例一致

DB 策略: 独立 in-memory sqlite (PaymentOrder + ChargingOrder), 复用现有脚手架。
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.services.wx_pay import payment as pm
from app.services.wx_pay.client import NotifyResult


@pytest.fixture
def db():
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


def _notify_result(out_trade_no="TL_x", trade_state="SUCCESS", tx_id="4200001234",
                   amount_fen=8200, paid_at=None, appid=None, sub_mchid=None):
    return NotifyResult(
        out_trade_no=out_trade_no,
        wx_transaction_id=tx_id,
        trade_state=trade_state,
        amount_fen=amount_fen,
        paid_at=paid_at if paid_at is not None else datetime.now(timezone.utc),
        appid=appid,
        sub_mchid=sub_mchid,
    )


def _po(out_trade_no="TL_guard", business_order_no="ord_guard", amount_fen=8200,
        sub_mchid=pm.MOCK_DEFAULT_SUB_MCHID):
    return PaymentOrder(
        out_trade_no=out_trade_no,
        business_order_no=business_order_no,
        openid="openid_g",
        scene=PayScene.MINIPROGRAM,
        sub_mchid=sub_mchid,
        amount_fen=amount_fen,
        prepay_id="prep_g",
        payment_status=PaymentStatus.UNPAID,
    )


class TestNotifyAmountGuard:
    def test_amount_match_marks_paid(self, db):
        """回调金额 == 下单金额 → 正常落 PAID (一致用例)。"""
        po = _po(amount_fen=8200)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=8200, tx_id="4200OK",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True

    def test_amount_mismatch_rejects_paid(self, db):
        """回调金额 1 分 vs 下单 8200 分 (金额篡改) → 拒绝落 PAID。"""
        po = _po(amount_fen=8200)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=1, tx_id="4200CHEAP",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"  # ACK 防重试风暴, 但状态不动
        db.refresh(po)
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.notify_processed is False
        assert po.wx_transaction_id is None
        assert po.paid_at is None
        assert po.notify_count == 1  # 计数照常累加 (审计线索)

    def test_amount_mismatch_logs_error(self, db, caplog):
        """金额不符 → logger.error 告警 (含双金额, 供风控对账)。"""
        po = _po(amount_fen=5000)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=100,
        )
        with caplog.at_level(logging.ERROR, logger="app.services.wx_pay.payment"):
            with patch.object(pm, "get_wxpay_client", return_value=client):
                pm.handle_notify(db, b"{}", {})
        msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("金额" in m and po.out_trade_no in m for m in msgs), msgs

    def test_amount_mismatch_charging_order_not_synced(self, db):
        """金额不符 → ChargingOrder 也不落 PAID (不被支付同步污染)。"""
        po = _po(out_trade_no="TL_g2", business_order_no="ord_g2", amount_fen=3000)
        co = ChargingOrder(
            order_no="ord_g2", station_id=1, device_id=10,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.COMPLETED, paid_amount=Decimal("0.00"),
        )
        db.add(po); db.add(co); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_g2", amount_fen=1,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.handle_notify(db, b"{}", {})
        db.refresh(po); db.refresh(co)
        assert po.payment_status == PaymentStatus.UNPAID
        assert co.payment_status == OrderPaymentStatus.UNPAID
        assert co.paid_amount == Decimal("0.00")

    def test_mismatch_then_correct_amount_marks_paid(self, db):
        """先篡改回调被拒, 后正确金额回调 → 正常落 PAID (拒绝不设终态标志)。"""
        po = _po(amount_fen=8200)
        db.add(po); db.commit()
        client = MagicMock()
        with patch.object(pm, "get_wxpay_client", return_value=client):
            client.verify_and_decrypt_notify.return_value = _notify_result(
                po.out_trade_no, amount_fen=1, tx_id="4200BAD",
            )
            pm.handle_notify(db, b"{}", {})
            client.verify_and_decrypt_notify.return_value = _notify_result(
                po.out_trade_no, amount_fen=8200, tx_id="4200GOOD",
            )
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.wx_transaction_id == "4200GOOD"
        assert po.notify_count == 2

    def test_zero_amount_row_accepts_matching_zero(self, db):
        """下单 0 分 (全免单/未结算) + 回调 0 分 → 通过 (0==0 不是不符)。"""
        po = _po(out_trade_no="TL_zero", business_order_no="ord_zero", amount_fen=0)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_zero", amount_fen=0, tx_id="4200ZERO",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID


class TestNotifyIdentityGuard:
    def test_sub_mchid_mismatch_rejects_paid(self, db):
        """回调 sub_mchid 与订单行不符 → 拒绝落 PAID (错单/跨商户错配)。"""
        po = _po(sub_mchid="2490000001")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=8200, sub_mchid="2490000999",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.notify_processed is False

    def test_sub_mchid_match_marks_paid(self, db):
        """回调 sub_mchid 与订单一致 + 金额一致 → 正常落 PAID。"""
        po = _po(sub_mchid="2490000001")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=8200, sub_mchid="2490000001",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID

    def test_identity_none_skips_that_dimension(self, db):
        """回调未携带 sub_mchid/appid (None) → 跳过该维度校验 (只校金额)。

        mock 明文 body 可不带身份字段; 旧数据/旧回调兼容, 不因缺字段误拒。
        """
        po = _po(amount_fen=8200)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=8200, sub_mchid=None, appid=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID

    def test_appid_guard_via_sub_mchid_pattern(self, db):
        """appid 校验同维度: 回传且不符 → 拒 (appid 无法与订单行直接比对 —
        PaymentOrder 不存 appid, 故 appid 不符仅在日志告警维度, 不阻断落库
        [PaymentOrder 无此字段, appid 校验由 A2 加列后启用])。

        本用例固化当前语义: appid 不符不阻断 (仅 sub_mchid/金额是硬闸)。
        """
        po = _po(amount_fen=8200)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=8200, appid="wxOTHERAPP",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID


class TestGuardDoesNotAffectOtherStates:
    def test_closed_notify_not_gated_by_amount(self, db):
        """CLOSED 回调不做金额校验 (关单无资金语义, 卡 4eab7cae 行为不变)。"""
        po = _po(amount_fen=8200)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, trade_state="CLOSED", amount_fen=0, paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.CLOSED

    def test_already_processed_repeat_not_gated(self, db):
        """notify_processed 已 True 的重复回调 → 幂等跳过, 不再校验金额
        (首次已校验过; IM-B重试报文一致, 二次校验无意义)。"""
        po = _po(amount_fen=8200)
        po.notify_processed = True
        po.payment_status = PaymentStatus.PAID
        po.wx_transaction_id = "4200ORIG"
        po.paid_at = datetime(2026, 8, 17, 2, 0, 0, tzinfo=timezone.utc)
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, amount_fen=1, tx_id="4200LATE",  # 金额甚至不同
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
        assert po.wx_transaction_id == "4200ORIG"


# ═══════════════════════════════════════════════════════════════
# mock_client 明文 body — 身份字段回传
# ═══════════════════════════════════════════════════════════════
class TestMockClientIdentityPassthrough:
    def test_mock_notify_passes_sub_mchid(self):
        """mock 明文 body 带 sp_appid/sub_mchid → NotifyResult 回传 (集成链路)。"""
        from app.services.wx_pay.mock_client import MockWxPayClient
        import json
        body = json.dumps({
            "out_trade_no": "TL_m", "transaction_id": "4200M",
            "trade_state": "SUCCESS", "amount": {"total": 100},
            "sp_appid": "wxMP00000000000000", "sub_mchid": "2490000001",
        }).encode()
        r = MockWxPayClient().verify_and_decrypt_notify(body, {})
        assert r is not None
        assert r.sub_mchid == "2490000001"
        assert r.appid == "wxMP00000000000000"

    def test_mock_notify_without_identity_none(self):
        """明文 body 不带身份字段 → NotifyResult.appid/sub_mchid 为 None。"""
        from app.services.wx_pay.mock_client import MockWxPayClient
        import json
        body = json.dumps({
            "out_trade_no": "TL_m2", "transaction_id": "4200M2",
            "trade_state": "SUCCESS",
        }).encode()
        r = MockWxPayClient().verify_and_decrypt_notify(body, {})
        assert r.sub_mchid is None
        assert r.appid is None
