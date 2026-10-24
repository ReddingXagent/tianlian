"""resolve_sub_mchid 复用路径商户状态闸测试 (卡 7f5b4d4f A2)

被测: app/services/wx_pay/payment.py::resolve_sub_mchid / prepay —
复用存量 PaymentOrder.sub_mchid 路径的 merchant_status 校验。

缺口背景 (A1 已知问题): 二次 prepay 复用已存在 PaymentOrder 的 sub_mchid
时直接返回, 跳过了 _assert_merchant_usable —— 商户被运营冻结 (FROZEN) 后,
用户对已有 UNPAID 支付行二次发起 prepay 仍能成功下单, 绕过禁收闸。

修复语义: 复用路径同样按 业务订单→station→team→Merchant 解析商户并校验状态;
解析不到商户 (mock 阶段常见) 保持现状放行 (与首单路径降级一致)。

DB 策略: in-memory sqlite (PaymentOrder + Merchant), lookup 链 patch 注入。
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.merchant import (
    Merchant,
    MerchantStatus,
    MerchantType,
    ApplymentState,
)
from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.services.wx_pay import payment as pm


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PaymentOrder.__table__.create(engine)
    Merchant.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _merchant(status, sub_mchid="2490000001"):
    return Merchant(
        business_code="APL_gate",
        merchant_type=MerchantType.MICRO_MERCHANT,
        merchant_name="被测商户",
        sub_mchid=sub_mchid,
        applyment_state=ApplymentState.FINISH,
        merchant_status=status,
    )


def _unpaid_po(business_order_no="ord_gate", sub_mchid="2490000001"):
    return PaymentOrder(
        out_trade_no="TL_gate_1",
        business_order_no=business_order_no,
        openid="openid_g",
        scene=PayScene.MINIPROGRAM,
        sub_mchid=sub_mchid,
        amount_fen=8200,
        prepay_id="prep_old",
        payment_status=PaymentStatus.UNPAID,
    )


# ═══════════════════════════════════════════════════════════════
# resolve_sub_mchid 复用路径状态闸
# ═══════════════════════════════════════════════════════════════
class TestReusePathMerchantGate:
    def test_reuse_frozen_merchant_rejected(self, db):
        """复用路径 + 商户 FROZEN → SubMerchantFrozen (不再静默放行)。"""
        db.add(_unpaid_po())
        db.commit()
        with patch.object(
            pm, "_lookup_merchant_by_order", return_value=_merchant(MerchantStatus.FROZEN)
        ):
            with pytest.raises(pm.SubMerchantFrozen):
                pm.resolve_sub_mchid(db, "ord_gate")

    def test_reuse_active_merchant_passes(self, db):
        """复用路径 + 商户 ACTIVE → 返回存量 sub_mchid (两用例之对照组)。"""
        db.add(_unpaid_po(sub_mchid="2490000001"))
        db.commit()
        with patch.object(
            pm, "_lookup_merchant_by_order", return_value=_merchant(MerchantStatus.ACTIVE)
        ):
            sub, m = pm.resolve_sub_mchid(db, "ord_gate")
        assert sub == "2490000001"
        assert m is not None

    def test_reuse_pending_merchant_rejected(self, db):
        """复用路径 + 商户 PENDING → SubMerchantNotReady。"""
        db.add(_unpaid_po())
        db.commit()
        with patch.object(
            pm, "_lookup_merchant_by_order", return_value=_merchant(MerchantStatus.PENDING)
        ):
            with pytest.raises(pm.SubMerchantNotReady):
                pm.resolve_sub_mchid(db, "ord_gate")

    def test_reuse_no_merchant_degrades(self, db):
        """复用路径 + 解析不到商户 (mock 阶段) → 保持降级放行 (现状兼容)。"""
        db.add(_unpaid_po())
        db.commit()
        with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
            sub, m = pm.resolve_sub_mchid(db, "ord_gate")
        assert sub == "2490000001"
        assert m is None


# ═══════════════════════════════════════════════════════════════
# prepay 集成链 (二次 prepay 全链拒/放行)
# ═══════════════════════════════════════════════════════════════
class TestPrepayReuseGateIntegration:
    def _mock_client(self):
        from unittest.mock import MagicMock
        from app.services.wx_pay.client import PrepayResult

        client = MagicMock()
        client.unified_order.return_value = PrepayResult(
            prepay_id="prep_new",
            time_stamp="1786047000",
            nonce_str="NONCE",
            package="prepay_id=prep_new",
            sign_type="RSA",
            pay_sign="SIGN",
        )
        return client

    def test_second_prepay_frozen_rejected(self, db):
        """FROZEN 二次 prepay → SubMerchantFrozen, 不调 unified_order。"""
        db.add(_unpaid_po(business_order_no="ord_i1"))
        db.commit()
        client = self._mock_client()
        with patch.object(
            pm, "_lookup_merchant_by_order", return_value=_merchant(MerchantStatus.FROZEN)
        ):
            with patch.object(pm, "get_wxpay_client", return_value=client):
                with pytest.raises(pm.SubMerchantFrozen):
                    pm.prepay(db, order_id="ord_i1", openid="o1", scene="miniprogram")
        client.unified_order.assert_not_called()
        # 存量 UNPAID 行未被新建污染 (仍一行)
        rows = db.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == "ord_i1"
        ).all()
        assert len(rows) == 1

    def test_second_prepay_active_succeeds(self, db):
        """ACTIVE 二次 prepay → 正常刷新 prepay_id (对照组)。"""
        db.add(_unpaid_po(business_order_no="ord_i2"))
        db.commit()
        client = self._mock_client()
        with patch.object(
            pm, "_lookup_merchant_by_order", return_value=_merchant(MerchantStatus.ACTIVE)
        ):
            with patch.object(pm, "get_wxpay_client", return_value=client):
                resp = pm.prepay(db, order_id="ord_i2", openid="o1", scene="miniprogram")
        assert resp["package"] == "prepay_id=prep_new"
        db.refresh(db.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == "ord_i2"
        ).first())
        client.unified_order.assert_called_once()
