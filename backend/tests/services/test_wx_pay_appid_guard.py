"""PaymentOrder.appid 列 + 回调 appid 硬闸测试 (卡 7f5b4d4f A2)

被测:
- app/models/payment_order.py — 新增 appid 列 (nullable, 兼容存量)
- app/services/wx_pay/payment.py::prepay — 下单时写入 appid (按 scene 从
  settings 取, IM-B回调配对基准)
- app/services/wx_pay/payment.py::handle_notify — 回调 appid 与订单 appid
  比对: 不一致拒绝落 PAID + 告警; 订单 appid 为 null (存量行) 跳过比对 +
  日志记录 (兼容期)。

资金安全语义 (契约 §2.2 回调): 回调 sp_appid 不属于本订单下单 appid,
说明回调被跨应用嫁接/伪造后过了平台验签 (如另一 appid 下的订单号碰撞),
不能落 PAID。

测试三用例 (篡改拒/一致放行/null 跳过) + prepay 写入用例。
"""
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.services.wx_pay import payment as pm
from app.services.wx_pay.client import NotifyResult, PrepayResult


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PaymentOrder.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _po(out_trade_no="TL_appid", business_order_no="ord_appid", appid=None,
        amount_fen=8200):
    return PaymentOrder(
        out_trade_no=out_trade_no,
        business_order_no=business_order_no,
        openid="openid_a",
        scene=PayScene.MINIPROGRAM,
        sub_mchid="2490000001",
        amount_fen=amount_fen,
        prepay_id="prep_a",
        payment_status=PaymentStatus.UNPAID,
        appid=appid,
    )


def _notify(out_trade_no="TL_appid", amount_fen=8200, appid=None, tx_id="4200A"):
    return NotifyResult(
        out_trade_no=out_trade_no,
        wx_transaction_id=tx_id,
        trade_state="SUCCESS",
        amount_fen=amount_fen,
        paid_at=datetime.now(timezone.utc),
        appid=appid,
        sub_mchid="2490000001",
    )


def _mock_client(notify):
    client = MagicMock()
    client.verify_and_decrypt_notify.return_value = notify
    return client


# ═══════════════════════════════════════════════════════════════
# 模型列
# ═══════════════════════════════════════════════════════════════
class TestAppidColumn:
    def test_column_exists_nullable(self):
        """PaymentOrder 有 appid 列且 nullable (存量行不破坏)。"""
        assert hasattr(PaymentOrder, "appid")
        col = PaymentOrder.__table__.columns["appid"]
        assert col.nullable is True

    def test_legacy_row_without_appid_persists(self, db):
        """不设 appid 落行 → 正常 (存量兼容)。"""
        db.add(_po(appid=None))
        db.commit()
        row = db.query(PaymentOrder).first()
        assert row.appid is None


# ═══════════════════════════════════════════════════════════════
# prepay 写入 appid
# ═══════════════════════════════════════════════════════════════
class TestPrepayWritesAppid:
    def _settings(self, mini="wxMINI000000000000", appid_app="wxAPP000000000000"):
        from types import SimpleNamespace
        return SimpleNamespace(
            WX_PAY_APPID_MINIPROGRAM=mini,
            WX_PAY_APPID_APP=appid_app,
        )

    def _mock_client(self):
        client = MagicMock()
        client.unified_order.return_value = PrepayResult(
            prepay_id="prep_x",
            time_stamp="1786047000",
            nonce_str="NONCE",
            package="prepay_id=prep_x",
            sign_type="RSA",
            pay_sign="SIGN",
        )
        return client

    def test_new_order_writes_miniprogram_appid(self, db):
        """新支付行 → appid 按 scene=miniprogram 从 settings 取。"""
        with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
            with patch.object(pm, "get_wxpay_client", return_value=self._mock_client()):
                pm.prepay(
                    db, order_id="ord_new", openid="o1", scene="miniprogram",
                    _settings_override=self._settings(mini="wxMINI000000000000"),
                )
        row = db.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == "ord_new"
        ).first()
        assert row.appid == "wxMINI000000000000"

    def test_new_order_scene_app_writes_app_appid(self, db):
        """scene=app → appid 用 WX_PAY_APPID_APP。"""
        with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
            with patch.object(pm, "get_wxpay_client", return_value=self._mock_client()):
                pm.prepay(
                    db, order_id="ord_app2", openid="o1", scene="app",
                    _settings_override=self._settings(appid_app="wxAPP000000000000"),
                )
        row = db.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == "ord_app2"
        ).first()
        assert row.appid == "wxAPP000000000000"


# ═══════════════════════════════════════════════════════════════
# 回调 appid 硬闸 (三用例)
# ═══════════════════════════════════════════════════════════════
class TestNotifyAppidGuard:
    def test_appid_mismatch_rejects_paid(self, db):
        """篡改: 回调 appid (wxOTHER) != 订单 appid (wxMINE) → 拒绝落 PAID。"""
        po = _po(appid="wxMINE000000000000")
        db.add(po); db.commit()
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client(
            _notify(po.out_trade_no, appid="wxOTHER0000000000"),
        )):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"  # ACK 防重试风暴, 状态不动
        db.refresh(po)
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.notify_processed is False
        assert po.wx_transaction_id is None

    def test_appid_mismatch_logs_error(self, db, caplog):
        """appid 不符 → logger.error 告警 (含双 appid + 单号)。"""
        po = _po(appid="wxMINE000000000000")
        db.add(po); db.commit()
        with caplog.at_level(logging.ERROR, logger="app.services.wx_pay.payment"):
            with patch.object(pm, "get_wxpay_client", return_value=_mock_client(
                _notify(po.out_trade_no, appid="wxOTHER0000000000"),
            )):
                pm.handle_notify(db, b"{}", {})
        msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("appid" in m and po.out_trade_no in m for m in msgs), msgs

    def test_appid_match_marks_paid(self, db):
        """一致: 回调 appid == 订单 appid → 正常落 PAID (对照组)。"""
        po = _po(appid="wxMINE000000000000")
        db.add(po); db.commit()
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client(
            _notify(po.out_trade_no, appid="wxMINE000000000000"),
        )):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True

    def test_order_appid_null_skips_compare_and_logs(self, db, caplog):
        """null 跳过: 存量行 appid 为 None → 不比对, 照常落 PAID + 日志记录兼容。"""
        po = _po(appid=None)
        db.add(po); db.commit()
        with caplog.at_level(logging.WARNING, logger="app.services.wx_pay.payment"):
            with patch.object(pm, "get_wxpay_client", return_value=_mock_client(
                _notify(po.out_trade_no, appid="wxANYTHING000000"),
            )):
                resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
        # 兼容期留痕: 明确记下跳过了 appid 比对 (风控对账可查)
        warns = [r.getMessage() for r in caplog.records
                 if r.levelno >= logging.WARNING]
        assert any("appid" in m for m in warns), warns

    def test_notify_appid_none_order_has_appid_skips(self, db):
        """回调未携带 appid (None) + 订单有 appid → 跳过该维度 (mock 明文兼容)。"""
        po = _po(appid="wxMINE000000000000")
        db.add(po); db.commit()
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client(
            _notify(po.out_trade_no, appid=None),
        )):
            resp = pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert resp["code"] == "SUCCESS"
        assert po.payment_status == PaymentStatus.PAID
