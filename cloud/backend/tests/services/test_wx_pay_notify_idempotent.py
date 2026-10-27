"""回调幂等加固测试 (卡 071194e4 A3)

被测: app/services/wx_pay/payment.py::handle_notify — IM-B重试 PAID 回调的
幂等行为锁。

摸底结论: 状态机已有 notify_processed 幂等 (首次 SUCCESS 落 PAID + 设标志,
重复回调跳过业务只累加 notify_count), test_wx_pay_payment.py:477 已测
"预置 PAID 行收到重复回调"。本卡按工作卡口径补**行为链锁测试**:
从 UNPAID 起连续两次相同 PAID 回调 → 全链幂等 (状态/交易号/paid_at/
ChargingOrder 同步/响应 全一致), 不是预置终态的快照测试。

三域断言:
1. 订单状态: 两次回调后仍 PAID, 不产生第二行, notify_count 恰为 2
2. 账务同步: ChargingOrder.paid_amount / payment_status 只被写一次的等值
   (重复回调后仍为首次金额, 不叠加/不复写)
3. 响应: 两次回调均 {"code": "SUCCESS"} (IM-B侧停止重试)

附带: 交错序 (先 CLOSED 后 SUCCESS) 与重复不同 tx_id 回调的幂等不变量。
"""
import json
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


def _seed(db, out_trade_no="TL_idem3", business_order_no="ord_idem3",
          amount_fen=8200):
    """UNPAID 支付行 + 关联业务订单 (模拟真实充电完成待支付场景)。"""
    po = PaymentOrder(
        out_trade_no=out_trade_no,
        business_order_no=business_order_no,
        openid="openid_i",
        scene=PayScene.MINIPROGRAM,
        sub_mchid="2490000001",
        amount_fen=amount_fen,
        prepay_id="prep_i",
        payment_status=PaymentStatus.UNPAID,
        notify_count=0,
    )
    co = ChargingOrder(
        order_no=business_order_no, station_id=1, device_id=10,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.COMPLETED, paid_amount=Decimal("0.00"),
    )
    db.add(po); db.add(co); db.commit()
    return po, co


def _client_notify(out_trade_no, tx_id="4200IDEM", amount_fen=8200,
                   trade_state="SUCCESS"):
    """MagicMock client 固定返回同构 PAID 回调 (IM-B重试报文一致)。"""
    client = MagicMock()
    client.verify_and_decrypt_notify.return_value = NotifyResult(
        out_trade_no=out_trade_no,
        wx_transaction_id=tx_id,
        trade_state=trade_state,
        amount_fen=amount_fen,
        paid_at=datetime(2026, 8, 17, 4, 0, 0, tzinfo=timezone.utc),
        appid=None,
        sub_mchid="2490000001",
    )
    return client


# ═══════════════════════════════════════════════════════════════
# 1. 同订单两次相同 PAID 回调 → 全链幂等
# ═══════════════════════════════════════════════════════════════
class TestDuplicatePaidNotifyIdempotent:
    def test_two_identical_paid_notify_full_chain(self, db):
        """UNPAID 起 → 两次相同 PAID 回调: 状态/交易号/paid_at/同步/响应一致。"""
        po, co = _seed(db)
        client = _client_notify(po.out_trade_no)
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp1 = pm.handle_notify(db, b"{}", {})
            resp2 = pm.handle_notify(db, b"{}", {})
        db.refresh(po); db.refresh(co)
        # 响应: 两次都 SUCCESS (IM-B停止重试)
        assert resp1 == {"code": "SUCCESS", "message": "成功"}
        assert resp2 == resp1
        # 状态: PAID 恰好一次落库, 不产生第二行
        assert po.payment_status == PaymentStatus.PAID
        assert db.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == po.business_order_no
        ).count() == 1
        # 交易号/时间: 首次值保持 (不被第二次覆盖)
        assert po.wx_transaction_id == "4200IDEM"
        assert po.paid_at is not None
        assert po.notify_processed is True
        # 计数: 恰为 2 (每次回调都留痕)
        assert po.notify_count == 2
        # 账务同步: ChargingOrder 只反映一次支付 (paid_amount = 82.00 元, 不叠加)
        assert co.payment_status == OrderPaymentStatus.PAID
        assert co.paid_amount == Decimal("82.00")

    def test_paid_at_not_reset_by_duplicate(self, db):
        """重复回调不重设 paid_at (首次回调时刻保持, 记账时点不漂移)。"""
        po, _ = _seed(db)
        first_paid_at = datetime(2026, 8, 17, 4, 0, 0, tzinfo=timezone.utc)
        client = _client_notify(po.out_trade_no)
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        # sqlite DateTime 不存 tzinfo → 读回 naive, 比 wall-clock 部分
        assert po.paid_at.replace(tzinfo=None) == first_paid_at.replace(tzinfo=None)
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert po.paid_at.replace(tzinfo=None) == first_paid_at.replace(tzinfo=None)

    def test_duplicate_with_different_tx_id_keeps_first(self, db):
        """IM-B重试报文 tx_id 异常不同 (理论不应发生) → 保持首次值不变。"""
        po, _ = _seed(db)
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, tx_id="4200FIRST",
        )):
            pm.handle_notify(db, b"{}", {})
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, tx_id="4200SECOND",
        )):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.wx_transaction_id == "4200FIRST"

    def test_third_notify_still_idempotent(self, db):
        """三次回调 (IM-B退避最长可重试多轮) → 仍幂等, count==3。"""
        po, co = _seed(db)
        client = _client_notify(po.out_trade_no)
        with patch.object(pm, "get_wxpay_client", return_value=client):
            for _ in range(3):
                resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po); db.refresh(co)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_count == 3
        assert co.paid_amount == Decimal("82.00")  # 金额不叠加


# ═══════════════════════════════════════════════════════════════
# 2. 交错序不变量
# ═══════════════════════════════════════════════════════════════
class TestInterleavedOrderings:
    def test_closed_then_success_still_marks_paid(self, db):
        """先 CLOSED 后 SUCCESS (IM-B交错投递): SUCCESS 仍可落 PAID (先关后付补偿)。"""
        po, _ = _seed(db)
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, trade_state="CLOSED",
        )):
            pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert po.payment_status == PaymentStatus.CLOSED
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, trade_state="SUCCESS",
        )):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID

    def test_success_then_closed_not_downgraded(self, db):
        """先 SUCCESS 后 CLOSED: PAID 行绝不降级 (资金状态单向)。"""
        po, _ = _seed(db)
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, trade_state="SUCCESS",
        )):
            pm.handle_notify(db, b"{}", {})
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, trade_state="CLOSED",
        )):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
        assert po.wx_transaction_id == "4200IDEM"

    def test_success_repeat_after_closed_then_success(self, db):
        """CLOSED→SUCCESS→SUCCESS 三连: 末次重复不扰动已落 PAID。"""
        po, co = _seed(db)
        with patch.object(pm, "get_wxpay_client", return_value=_client_notify(
            po.out_trade_no, trade_state="CLOSED",
        )):
            pm.handle_notify(db, b"{}", {})
        succ = _client_notify(po.out_trade_no, trade_state="SUCCESS")
        with patch.object(pm, "get_wxpay_client", return_value=succ):
            pm.handle_notify(db, b"{}", {})
            resp2 = pm.handle_notify(db, b"{}", {})
        db.refresh(po); db.refresh(co)
        assert resp2["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_count == 3
        assert co.paid_amount == Decimal("82.00")
