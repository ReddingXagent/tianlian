"""handle_notify 同步 ChargingOrder.payment_status 单测 (卡 1b5e3d1e)

被测: app/services/wx_pay/payment.py::handle_notify
修复点: IM-B回调成功后同步更新关联 ChargingOrder, 否则开票校验
(InvoiceRequestService 读 ChargingOrder.payment_status==PAID) 永远失败。

DB 策略: in-memory sqlite, 独立 engine, 同时建 PaymentOrder + ChargingOrder
(复用 test_wx_pay_payment.py 的脚手架模式)。client 用 MagicMock 控制 notify 返回。

口径: ChargingOrder.paid_amount 单位=元, PaymentOrder.amount_fen 单位=分,
同步时 amount_fen/100 换算 (对齐 invoice_request_service._amount_yuan_to_cents)。
"""
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


@pytest.fixture
def db():
    """独立 in-memory Session, 建被测所需表 (PaymentOrder + ChargingOrder)。"""
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
                   amount_fen=0):
    from app.services.wx_pay.client import NotifyResult
    return NotifyResult(
        out_trade_no=out_trade_no,
        wx_transaction_id=tx_id,
        trade_state=trade_state,
        amount_fen=amount_fen,
        paid_at=datetime.now(timezone.utc),
    )


def _seed(db, *, out_trade_no="TL_sync", order_no="ord_sync", amount_fen=3525,
          notify_processed=False, payment_status=PaymentStatus.UNPAID):
    """落一行 UNPAID PaymentOrder + 一行 UNPAID ChargingOrder, 返回 (po, co)。"""
    po = PaymentOrder(
        out_trade_no=out_trade_no,
        business_order_no=order_no,
        openid="openid_x",
        scene=PayScene.MINIPROGRAM,
        sub_mchid=pm.MOCK_DEFAULT_SUB_MCHID,
        amount_fen=amount_fen,
        prepay_id="prep_x",
        payment_status=payment_status,
        notify_processed=notify_processed,
    )
    db.add(po)
    co = ChargingOrder(
        order_no=order_no,
        station_id=1,
        device_id=10,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.COMPLETED,
        paid_amount=Decimal("0.00"),
    )
    db.add(co)
    db.commit()
    db.refresh(po)
    db.refresh(co)
    return po, co


class TestHandleNotifySyncsChargingOrder:
    def test_syncs_charging_order(self, db):
        """回调成功后 ChargingOrder.payment_status=PAID, paid_amount=amount_fen/100。"""
        po, co = _seed(db, amount_fen=3525)
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, trade_state="SUCCESS", tx_id="4200SYNC",
            amount_fen=3525,  # 与行 amount_fen 一致 (回调金额闸, 卡 6c8f930c)
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})

        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        db.refresh(co)
        # PaymentOrder 已 PAID
        assert po.payment_status == PaymentStatus.PAID
        # ChargingOrder 同步: 状态 + 金额(分→元); 支付时间落 PaymentOrder
        assert co.payment_status == OrderPaymentStatus.PAID
        assert co.paid_amount == Decimal("35.25")
        assert po.paid_at is not None

    def test_idempotent_charging_order(self, db):
        """重复回调 (notify_processed 已 True) 不重复更新 ChargingOrder。"""
        po, co = _seed(db, amount_fen=1000, notify_processed=True,
                       payment_status=PaymentStatus.PAID)
        # 预置已支付态: 金额已落定值; 支付时间定值落 PaymentOrder (真相源)
        co.payment_status = OrderPaymentStatus.PAID
        co.paid_amount = Decimal("10.00")
        fixed_paid_at = datetime(2026, 8, 9, 1, 2, 3, tzinfo=timezone.utc)
        po.paid_at = fixed_paid_at
        db.commit()
        db.refresh(co)
        db.refresh(po)

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, trade_state="SUCCESS", tx_id="4200DUP",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})

        assert resp["code"] == "SUCCESS"
        db.refresh(co)
        db.refresh(po)
        # 幂等: 原值不变 (金额/支付时间不被二次回调改写)
        assert co.paid_amount == Decimal("10.00")
        assert po.paid_at.replace(tzinfo=None) == fixed_paid_at.replace(tzinfo=None)
        # PaymentOrder 侧计数仍累加
        assert po.notify_count == 1

    def test_no_charging_order_does_not_raise(self, db):
        """PaymentOrder 存在但无关联 ChargingOrder (纯支付测试场景) -> 不报错。"""
        po = PaymentOrder(
            out_trade_no="TL_only",
            business_order_no="ord_orphan",
            openid="openid_y",
            scene=PayScene.MINIPROGRAM,
            sub_mchid=pm.MOCK_DEFAULT_SUB_MCHID,
            amount_fen=500,
            prepay_id="prep_y",
            payment_status=PaymentStatus.UNPAID,
        )
        db.add(po)
        db.commit()
        db.refresh(po)

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            po.out_trade_no, trade_state="SUCCESS", tx_id="4200ORPHAN",
            amount_fen=500,  # 与行 amount_fen 一致 (回调金额闸, 卡 6c8f930c)
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})

        # 不报错, PaymentOrder 仍正常落 PAID
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        # 无 ChargingOrder 行
        assert db.query(ChargingOrder).count() == 0
