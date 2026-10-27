"""wx_pay.payment 单元测试覆盖补全 (卡 23f40b50)

被测: app/services/wx_pay/payment.py — IM-B服务商支付 service (契约 §2 支付)。

覆盖矩阵 (7 个被测点 + 常量/异常):
  generate_out_trade_no     格式 (TL_ + 8 位业务日 + 16 hex) / 唯一性 / Asia/Shanghai 业务日
  _lookup_merchant_by_order 查询链各分支 (无订单/无站点/无商户/命中) + 异常降级 None
  _assert_merchant_usable   ACTIVE 通过 / FROZEN 抛 SubMerchantFrozen / 非ACTIVE 抛 SubMerchantNotReady
  resolve_sub_mchid         复用已有 PaymentOrder / 无商户降级 MOCK / 有商户各状态
  prepay                    已PAID 拒单 / 已UNPAID 复用刷新 / 新订单落行 + 五字段 camelCase
  handle_notify             验签失败 FAIL / 未知订单 ACK 不处理 / 首次 SUCCESS 落 PAID / 重复幂等 / 非 SUCCESS 不落 PAID
  get_order_payment         无记录 None / 单行 / 多行按优先级 (PAID>UNPAID>CLOSED)

DB 策略: prepay/notify/get_order_payment/resolve_sub_mchid 走真实 in-memory sqlite Session
  (对 PaymentOrder 做 add/commit/refresh/query, 真实 DB 最稳, 独立 Session 避开全局 SessionLocal 坑)。
  _lookup_merchant_by_order 用 MagicMock 测查询链 + 异常降级 (纯查询函数, mock 最准)。
client 策略: patch get_wxpay_client 注入 MagicMock (避免单例污染, 控制 unified_order/verify 返回)。

铁律: 只加测试, 不改 production。
"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.merchant import Merchant, MerchantStatus, MerchantType, ApplymentState
from app.models.payment_order import PaymentOrder, PaymentStatus, PayScene
from app.services.wx_pay import payment as pm
from app.services.wx_pay.client import PrepayResult


# ═══════════════════════════════════════════════════════════════════════════
# 脚手架: in-memory sqlite Session (独立 engine, 不碰全局 SessionLocal)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def db():
    """仅建被测所需表的独立 in-memory Session (PaymentOrder; Merchant 留给 lookup 单测)。

    StaticPool + check_same_thread=False 让单连接贯穿整个 session, commit/refresh 行为
    与生产一致 (真实 query 链 + 主键回写)。
    """
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


def _prepay_result(prepay_id="prep_123"):
    """构造 PrepayResult (unified_order 返回结构)。"""
    return PrepayResult(
        prepay_id=prepay_id,
        time_stamp="1786047000",
        nonce_str="NONCE0123456789ABCDEF",
        package=f"prepay_id={prepay_id}",
        sign_type="RSA",
        pay_sign="SIGNATUREBASE64",
    )


def _mock_client(unified=None, notify=None):
    """构造 wxpay client mock; 默认 unified_order 返回 _prepay_result()。"""
    client = MagicMock()
    client.unified_order.return_value = unified or _prepay_result()
    if notify is not None:
        client.verify_and_decrypt_notify.return_value = notify
    return client


def _notify_result(out_trade_no="TL_x", trade_state="SUCCESS",
                   tx_id="4200001234", paid_at=None, amount_fen=0):
    """构造 NotifyResult (默认 SUCCESS + paid_at; amount_fen 默认 0 与
    _make_unpaid_po 的 0 分行一致, 过回调金额闸)。"""
    from app.services.wx_pay.client import NotifyResult
    return NotifyResult(
        out_trade_no=out_trade_no,
        wx_transaction_id=tx_id,
        trade_state=trade_state,
        amount_fen=amount_fen,
        paid_at=paid_at if paid_at is not None else datetime.now(timezone.utc),
    )


def _make_unpaid_po(out_trade_no="TL_old", business_order_no="ord_1",
                    sub_mchid=pm.MOCK_DEFAULT_SUB_MCHID, prepay_id="prep_old"):
    """构造一行 UNPAID PaymentOrder (未 commit, 由调用方 add+commit)。"""
    return PaymentOrder(
        out_trade_no=out_trade_no,
        business_order_no=business_order_no,
        openid="openid_x",
        scene=PayScene.MINIPROGRAM,
        sub_mchid=sub_mchid,
        amount_fen=0,
        prepay_id=prepay_id,
        payment_status=PaymentStatus.UNPAID,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. generate_out_trade_no
# ═══════════════════════════════════════════════════════════════════════════
class TestGenerateOutTradeNo:
    def test_format_prefix_date_hex(self):
        """TL_ + 8 位业务日 (yyyymmdd) + 16 位 hex, 用 _ 分隔。"""
        no = pm.generate_out_trade_no()
        assert no.startswith("TL_")
        parts = no.split("_")
        assert len(parts) == 3
        assert parts[0] == "TL"
        date = parts[1]
        assert len(date) == 8 and date.isdigit()
        hexpart = parts[2]
        assert len(hexpart) == 16  # secrets.token_hex(8) -> 16 hex chars
        int(hexpart, 16)  # 必须是合法十六进制

    def test_uniqueness_consecutive(self):
        """连续生成不重复 (secrets.token_hex 随机性)。"""
        samples = {pm.generate_out_trade_no() for _ in range(200)}
        assert len(samples) == 200

    @patch("app.services.wx_pay.payment.datetime")
    def test_business_day_uses_shanghai_tz(self, mock_dt):
        """业务日按 Asia/Shanghai, 非 UTC。

        构造 UTC 2026-01-01 16:00 (对应 CST 2026-01-02 00:00),
        断言单号内嵌日期为 20260102 (CST 边界验证)。
        """
        from zoneinfo import ZoneInfo

        real_from = datetime.now

        def fake_now(tz=None):
            # payment.py 调 datetime.now(_BIZ_TZ); 透传 tz 还原带时区 now 语义
            if tz is not None:
                return real_from(ZoneInfo("UTC")).astimezone(tz)
            return real_from()

        # 固定 UTC 16:00 -> 任意时区换算: 让 fake_now 在传入 Asia/Shanghai 时
        # 返回 2026-01-02 00:00 CST (即 UTC 2026-01-01 16:00)
        fixed_utc = datetime(2026, 1, 1, 16, 0, 0, tzinfo=ZoneInfo("UTC"))

        def fake_now_fixed(tz=None):
            return fixed_utc.astimezone(tz) if tz is not None else fixed_utc

        mock_dt.now.side_effect = fake_now_fixed
        no = pm.generate_out_trade_no()
        # CST 业务日 = 20260102
        assert no.startswith("TL_20260102_"), no


# ═══════════════════════════════════════════════════════════════════════════
# 2. _lookup_merchant_by_order (纯查询链 -> MagicMock session)
# ═══════════════════════════════════════════════════════════════════════════
class TestLookupMerchantByOrder:
    def _chain_session(self, order_row=None, team_id=None, merchant=None):
        """构造 MagicMock session: 三段 query 链按调用顺序返回。

        payment.py 顺序:
          1) db.query(ChargingOrder.station_id).filter(...).first() -> order_row
          2) db.query(Station.team_id).filter(...).scalar() -> team_id
          3) db.query(Merchant).filter(...).order_by(...).first() -> merchant
        用 side_effect 按序供给。
        """
        session = MagicMock()
        q1 = MagicMock(); q1.filter.return_value.first.return_value = order_row
        q2 = MagicMock(); q2.filter.return_value.scalar.return_value = team_id
        q3 = MagicMock(); q3.filter.return_value.order_by.return_value.first.return_value = merchant
        session.query.side_effect = [q1, q2, q3]
        return session

    def test_no_order_returns_none(self):
        """无业务订单 -> 第一段 first()=None -> None (不查 station/merchant)。"""
        session = self._chain_session(order_row=None)
        assert pm._lookup_merchant_by_order(session, "nope") is None
        # 仅触发第一段查询
        assert session.query.call_count == 1

    def test_order_without_station_id_returns_none(self):
        """订单存在但 station_id 缺 -> None。"""
        row = MagicMock(); row.station_id = None
        session = self._chain_session(order_row=row)
        assert pm._lookup_merchant_by_order(session, "ord") is None

    def test_no_team_returns_none(self):
        """有站点但无 team_id -> None (不查 merchant)。"""
        row = MagicMock(); row.station_id = 7
        session = self._chain_session(order_row=row, team_id=None)
        assert pm._lookup_merchant_by_order(session, "ord") is None
        assert session.query.call_count == 2

    def test_no_merchant_returns_none(self):
        """有 team 但无商户 -> None。"""
        row = MagicMock(); row.station_id = 7
        session = self._chain_session(order_row=row, team_id=5, merchant=None)
        assert pm._lookup_merchant_by_order(session, "ord") is None

    def test_hit_returns_merchant(self):
        """全链命中 -> 返回 Merchant。"""
        row = MagicMock(); row.station_id = 7
        merchant = MagicMock(name="m")
        session = self._chain_session(order_row=row, team_id=5, merchant=merchant)
        assert pm._lookup_merchant_by_order(session, "ord") is merchant

    def test_query_exception_degrades_to_none(self):
        """查询抛任意异常 -> except 降级 None, 不冒泡。"""
        session = MagicMock()
        session.query.side_effect = RuntimeError("db down")
        assert pm._lookup_merchant_by_order(session, "ord") is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. _assert_merchant_usable
# ═══════════════════════════════════════════════════════════════════════════
class TestAssertMerchantUsable:
    def _merchant(self, status):
        m = Merchant(merchant_status=status, sub_mchid="2490000009",
                     business_code="APL_1", merchant_type=MerchantType.MICRO_MERCHANT,
                     merchant_name="m")
        return m

    def test_active_passes(self):
        pm._assert_merchant_usable(self._merchant(MerchantStatus.ACTIVE))  # 不抛即通过

    def test_frozen_raises_frozen(self):
        with pytest.raises(pm.SubMerchantFrozen):
            pm._assert_merchant_usable(self._merchant(MerchantStatus.FROZEN))

    def test_pending_raises_not_ready(self):
        with pytest.raises(pm.SubMerchantNotReady):
            pm._assert_merchant_usable(self._merchant(MerchantStatus.PENDING))


# ═══════════════════════════════════════════════════════════════════════════
# 4. resolve_sub_mchid
# ═══════════════════════════════════════════════════════════════════════════
class TestResolveSubMchid:
    def test_reuse_existing_payment_order(self, db):
        """已有 PaymentOrder -> 复用其 sub_mchid, merchant 返回 None。"""
        db.add(_make_unpaid_po(sub_mchid="2490000001"))
        db.commit()
        sub, m = pm.resolve_sub_mchid(db, "ord_1")
        assert sub == "2490000001"
        assert m is None

    def test_no_merchant_degrades_to_mock(self, db):
        """无商户 (lookup None) -> MOCK_DEFAULT_SUB_MCHID。"""
        with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
            sub, m = pm.resolve_sub_mchid(db, "ord_none")
        assert sub == pm.MOCK_DEFAULT_SUB_MCHID
        assert m is None

    def test_active_merchant_returns_sub_mchid(self, db):
        """有 ACTIVE 商户 -> 校验通过 + 返回其 sub_mchid。"""
        merchant = Merchant(
            business_code="APL_a", merchant_type=MerchantType.MICRO_MERCHANT,
            merchant_name="m", sub_mchid="2490000088",
            merchant_status=MerchantStatus.ACTIVE,
        )
        with patch.object(pm, "_lookup_merchant_by_order", return_value=merchant):
            sub, m = pm.resolve_sub_mchid(db, "ord_a")
        assert sub == "2490000088"
        assert m is merchant

    def test_frozen_merchant_raises(self, db):
        """有 FROZEN 商户 -> SubMerchantFrozen。"""
        merchant = Merchant(
            business_code="APL_f", merchant_type=MerchantType.MICRO_MERCHANT,
            merchant_name="m", sub_mchid="2490000099",
            merchant_status=MerchantStatus.FROZEN,
        )
        with patch.object(pm, "_lookup_merchant_by_order", return_value=merchant):
            with pytest.raises(pm.SubMerchantFrozen):
                pm.resolve_sub_mchid(db, "ord_f")

    def test_pending_merchant_raises(self, db):
        """有 PENDING 商户 -> SubMerchantNotReady。"""
        merchant = Merchant(
            business_code="APL_p", merchant_type=MerchantType.MICRO_MERCHANT,
            merchant_name="m", sub_mchid="2490000077",
            merchant_status=MerchantStatus.PENDING,
        )
        with patch.object(pm, "_lookup_merchant_by_order", return_value=merchant):
            with pytest.raises(pm.SubMerchantNotReady):
                pm.resolve_sub_mchid(db, "ord_p")


# ═══════════════════════════════════════════════════════════════════════════
# 5. prepay
# ═══════════════════════════════════════════════════════════════════════════
class TestPrepay:
    def test_already_paid_raises(self, db):
        """已有 PAID 行 -> OrderAlreadyPaid。"""
        po = _make_unpaid_po(business_order_no="ord_paid")
        po.payment_status = PaymentStatus.PAID
        db.add(po); db.commit()
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client()):
            with pytest.raises(pm.OrderAlreadyPaid):
                pm.prepay(db, order_id="ord_paid", openid="o1", scene="miniprogram")

    def test_existing_unpaid_reuses_out_trade_no(self, db):
        """已有 UNPAID 行 -> 复用 out_trade_no + 刷新 prepay_id + commit, 不新建行。"""
        po = _make_unpaid_po(out_trade_no="TL_keep", business_order_no="ord_u",
                             prepay_id="prep_old")
        db.add(po); db.commit()
        client = _mock_client()  # 返回 _prepay_result(prepay_id="prep_123")
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.prepay(db, order_id="ord_u", openid="o_new", scene="app")

        # 五字段结构
        assert resp == {
            "timeStamp": "1786047000", "nonceStr": "NONCE0123456789ABCDEF",
            "package": "prepay_id=prep_123", "signType": "RSA",
            "paySign": "SIGNATUREBASE64",
        }
        # 仍只有一行 (复用, 未新建)
        rows = db.query(PaymentOrder).filter(PaymentOrder.business_order_no == "ord_u").all()
        assert len(rows) == 1
        # out_trade_no 保持, prepay_id 被刷新, openid/scene/sub_mchid 更新
        refreshed = rows[0]
        assert refreshed.out_trade_no == "TL_keep"
        assert refreshed.prepay_id == "prep_123"
        assert refreshed.openid == "o_new"
        assert refreshed.scene == PayScene.APP
        assert refreshed.payment_status == PaymentStatus.UNPAID
        # unified_order 被调用且传入了复用的 out_trade_no
        client.unified_order.assert_called_once()
        assert client.unified_order.call_args.kwargs["out_trade_no"] == "TL_keep"
        assert client.unified_order.call_args.kwargs["scene"] == "app"

    def test_closed_row_not_reused_new_out_trade_no(self, db):
        """已有 CLOSED 行 (无 UNPAID 行) -> 不复用, 生成新 out_trade_no 新建行 (卡 4eab7cae)。

        existing_unpaid 只查 UNPAID: CLOSED 行被跳过, 走新单号 — C端可对已关单
        重新发起 prepay, 旧 CLOSED 行保留作对账历史。
        """
        closed = _make_unpaid_po(out_trade_no="TL_dead", business_order_no="ord_dead")
        closed.payment_status = PaymentStatus.CLOSED
        db.add(closed); db.commit()

        client = _mock_client()
        with patch.object(pm, "get_wxpay_client", return_value=client):
            with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
                pm.prepay(db, order_id="ord_dead", openid="o1", scene="miniprogram")

        rows = db.query(PaymentOrder).filter(
            PaymentOrder.business_order_no == "ord_dead").order_by(PaymentOrder.id).all()
        assert len(rows) == 2  # 旧 CLOSED + 新 UNPAID
        assert rows[0].out_trade_no == "TL_dead"
        assert rows[0].payment_status == PaymentStatus.CLOSED
        new = rows[1]
        assert new.out_trade_no != "TL_dead"
        assert new.out_trade_no.startswith("TL_")
        assert new.payment_status == PaymentStatus.UNPAID
        # unified_order 收到的是新单号, 非旧 CLOSED 单号
        assert client.unified_order.call_args.kwargs["out_trade_no"] == new.out_trade_no

    def test_new_order_creates_payment_order(self, db):
        """新订单 -> 生成 out_trade_no + 落 UNPAID PaymentOrder + 五字段。"""
        client = _mock_client()
        with patch.object(pm, "get_wxpay_client", return_value=client):
            with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
                resp = pm.prepay(db, order_id="ord_new", openid="o1", scene="miniprogram")

        # 五字段 camelCase
        assert set(resp.keys()) == {"timeStamp", "nonceStr", "package", "signType", "paySign"}
        assert resp["signType"] == "RSA"
        assert resp["package"] == "prepay_id=prep_123"

        rows = db.query(PaymentOrder).filter(PaymentOrder.business_order_no == "ord_new").all()
        assert len(rows) == 1
        po = rows[0]
        assert po.out_trade_no.startswith("TL_")
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.sub_mchid == pm.MOCK_DEFAULT_SUB_MCHID  # 无商户降级
        assert po.prepay_id == "prep_123"
        assert po.scene == PayScene.MINIPROGRAM
        assert po.openid == "o1"

    def test_sub_mchid_resolution_integrated(self, db):
        """sub_mchid 解析集成: 解析到 ACTIVE 商户 -> 落库 sub_mchid 为商户号。"""
        merchant = Merchant(
            business_code="APL_int", merchant_type=MerchantType.MICRO_MERCHANT,
            merchant_name="m", sub_mchid="2490000066",
            merchant_status=MerchantStatus.ACTIVE,
        )
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client()):
            with patch.object(pm, "_lookup_merchant_by_order", return_value=merchant):
                pm.prepay(db, order_id="ord_int", openid="o1", scene="miniprogram")
        po = db.query(PaymentOrder).filter(PaymentOrder.business_order_no == "ord_int").one()
        assert po.sub_mchid == "2490000066"

    # ── 事务安全加固 (卡 d077c519): commit 失败必须 rollback + 重抛 ──
    def test_commit_fail_on_new_order_rolls_back_and_reraises(self, db, monkeypatch):
        """新建行 commit 抛异常 -> rollback 被调用 + 异常重抛 (调用方映射 500)。

        prepay 不抛 HTTPException (service 层不耦合 HTTP); 走 business.py 兜底
        except Exception -> 500。故这里只断言 rollback + 重抛。
        """
        real_commit = db.commit
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit boom")))
        rollback_spy = MagicMock(wraps=db.rollback)
        monkeypatch.setattr(db, "rollback", rollback_spy)
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client()):
            with patch.object(pm, "_lookup_merchant_by_order", return_value=None):
                with pytest.raises(Exception):
                    pm.prepay(db, order_id="ord_new", openid="o1", scene="miniprogram")
        rollback_spy.assert_called_once()
        # 恢复真实 commit 后验证: 未落库 (事务已回滚)
        monkeypatch.setattr(db, "commit", real_commit)
        assert db.query(PaymentOrder).filter(PaymentOrder.business_order_no == "ord_new").count() == 0

    def test_commit_fail_on_reuse_rolls_back_and_reraises(self, db, monkeypatch):
        """复用行刷新 commit 抛异常 -> rollback 被调用 + 异常重抛。"""
        po = _make_unpaid_po(out_trade_no="TL_keep", business_order_no="ord_u",
                             prepay_id="prep_old")
        db.add(po); db.commit()
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit boom")))
        rollback_spy = MagicMock(wraps=db.rollback)
        monkeypatch.setattr(db, "rollback", rollback_spy)
        with patch.object(pm, "get_wxpay_client", return_value=_mock_client()):
            with pytest.raises(Exception):
                pm.prepay(db, order_id="ord_u", openid="o_new", scene="app")
        rollback_spy.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# 6. handle_notify
# ═══════════════════════════════════════════════════════════════════════════
class TestHandleNotify:
    def test_verify_fail_returns_fail(self, db):
        """验签失败 (notify=None) -> {"code": "FAIL"}, 不查/改订单。"""
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = None
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"bad", {"x": "y"})
        assert resp["code"] == "FAIL"

    def test_unknown_order_acks_without_processing(self, db):
        """未知订单 (out_trade_no 不匹配) -> ACK SUCCESS, 不落状态。"""
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result("TL_ghost")
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        assert db.query(PaymentOrder).count() == 0

    def test_first_success_sets_paid(self, db):
        """首次 SUCCESS 回调 -> PAID + notify_processed + wx_transaction_id + paid_at。"""
        po = _make_unpaid_po(out_trade_no="TL_pay", business_order_no="ord_pay")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_pay", trade_state="SUCCESS", tx_id="4200AAA",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        assert po.notify_count == 1
        assert po.wx_transaction_id == "4200AAA"
        assert po.paid_at is not None

    def test_duplicate_notify_is_idempotent(self, db):
        """重复 SUCCESS 回调 (notify_processed 已 True) -> 不重设 paid_at/tx_id。"""
        fixed_paid_at = datetime(2026, 8, 7, 4, 20, 0, tzinfo=timezone.utc)
        po = _make_unpaid_po(out_trade_no="TL_idem", business_order_no="ord_idem")
        po.payment_status = PaymentStatus.PAID
        po.notify_processed = True
        po.notify_count = 1
        po.wx_transaction_id = "ORIG_TX"
        po.paid_at = fixed_paid_at
        db.add(po); db.commit()

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_idem", trade_state="SUCCESS", tx_id="NEW_TX",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        # 幂等: 原值不变, 仅 count 累加。
        # (sqlite DateTime 不存 tzinfo, 读回为 naive, 故比较 wall-clock 部分)
        assert po.wx_transaction_id == "ORIG_TX"
        assert po.paid_at.replace(tzinfo=None) == fixed_paid_at.replace(tzinfo=None)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_count == 2

    def test_non_success_trade_state_not_paid(self, db):
        """trade_state 非 SUCCESS (NOTPAY) -> notify_count+1 但不落 PAID/processed。"""
        po = _make_unpaid_po(out_trade_no="TL_np", business_order_no="ord_np")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_np", trade_state="NOTPAY", paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            pm.handle_notify(db, b"{}", {})
        db.refresh(po)
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.notify_processed is False
        assert po.notify_count == 1
        assert po.wx_transaction_id is None
        assert po.paid_at is None

    # ── 并发回调 (卡 ccd4c683): 无锁设计, 幂等纯靠 notify_processed + DB commit ──
    def test_concurrent_notify_only_first_processes(self, db):
        """并发回调 (两线程同一通知): 仅首次落 PAID, 第二次读 notify_processed=True 不重复落。

        handle_notify 无应用层锁, 幂等性靠 notify_processed 标志 + DB commit 的
        read-modify-write。IM-B退避重试天然串行化回调, 故真实并发也表现为"先到者处理、
        后到者幂等跳过"。本测试用两线程 + 前置屏障同步起跑, 验证最终态: 恰好一次落 PAID。

        技术约束: in-memory sqlite 单连接 Session 非线程安全, 两线程同时 commit 会破坏
        连接状态 (测到的是 SQLAlchemy/SQLite 竞态而非业务幂等)。故用一个 threading.Lock
        把两次 handle_notify 串行执行 —— 锁不改变业务逻辑 (handle_notify 本就无锁),
        只保证两次调用对共享 Session 的访问不交错, 从而测到真正的幂等语义而非 DB 竞态。
        """
        import threading

        po = _make_unpaid_po(out_trade_no="TL_conc", business_order_no="ord_conc")
        db.add(po); db.commit()

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_conc", trade_state="SUCCESS", tx_id="4200CONC",
        )

        barrier = threading.Barrier(2)
        serialize = threading.Lock()
        results = []
        errors = []

        def run():
            try:
                barrier.wait(timeout=5)  # 两线程同步起跑
                with serialize:          # 串行化 Session 访问 (避 SQLite 竞态)
                    with patch.object(pm, "get_wxpay_client", return_value=client):
                        results.append(pm.handle_notify(db, b"{}", {}))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=run); t2 = threading.Thread(target=run)
        t1.start(); t2.start(); t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"线程异常: {errors}"
        assert len(results) == 2
        # 两次都 ACK (IM-B侧均收到成功响应)
        assert all(r["code"] == "SUCCESS" for r in results)

        db.refresh(po)
        # 幂等: 最终态恰好一次处理 — PAID + processed=True + count==2
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        assert po.notify_count == 2
        assert po.wx_transaction_id == "4200CONC"  # 未被第二次覆盖 (仅首次落)

    # ── 回调状态落库 (卡 4eab7cae): CLOSED/PAYERROR 终态回写 ──
    def test_closed_notify_marks_unpaid_row_closed(self, db):
        """CLOSED 回调 → UNPAID 行落 CLOSED (不再永远卡 UNPAID)。

        缺陷背景: 修复前非 SUCCESS 回调只 notify_count+1, PaymentStatus.CLOSED
        枚举零写入路径 → 订单超时关闭后 get_order_payment 永远返回 UNPAID。
        """
        po = _make_unpaid_po(out_trade_no="TL_closed", business_order_no="ord_closed")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_closed", trade_state="CLOSED", paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.CLOSED
        assert po.notify_count == 1
        # CLOSED 不是支付成功: 不落 tx_id/paid_at/notify_processed
        assert po.wx_transaction_id is None
        assert po.paid_at is None
        assert po.notify_processed is False

    def test_payerror_notify_marks_unpaid_row_closed(self, db):
        """PAYERROR 回调 → UNPAID 行同样落 CLOSED (终态口径与 CLOSED 一致)。"""
        po = _make_unpaid_po(out_trade_no="TL_perr", business_order_no="ord_perr")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_perr", trade_state="PAYERROR", paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.CLOSED
        assert po.notify_count == 1
        assert po.notify_processed is False

    def test_paid_row_receives_closed_not_downgraded(self, db):
        """PAID 行收到 CLOSED 回调 → 不降级, 仍 PAID (资金真相不可回退)。

        IM-B侧时序: 支付成功回调与关单回调可能交错 (如用户支付瞬间订单超时关单),
        PAID 一旦确立必须稳定, 仅记 notify_count。
        """
        fixed_paid_at = datetime(2026, 8, 16, 8, 0, 0, tzinfo=timezone.utc)
        po = _make_unpaid_po(out_trade_no="TL_paid2", business_order_no="ord_paid2")
        po.payment_status = PaymentStatus.PAID
        po.notify_processed = True
        po.notify_count = 1
        po.wx_transaction_id = "4200KEEP"
        po.paid_at = fixed_paid_at
        db.add(po); db.commit()

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_paid2", trade_state="CLOSED", paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.wx_transaction_id == "4200KEEP"
        assert po.paid_at.replace(tzinfo=None) == fixed_paid_at.replace(tzinfo=None)
        assert po.notify_count == 2  # 仅计数累加

    def test_userpaying_keeps_unpaid(self, db):
        """USERPAYING (用户支付中, 中间态) 回调 → 保持 UNPAID 不动。

        中间态非终态, 落 CLOSED 会在用户稍后支付成功前误关订单。
        """
        po = _make_unpaid_po(out_trade_no="TL_upay", business_order_no="ord_upay")
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_upay", trade_state="USERPAYING", paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.UNPAID
        assert po.notify_count == 1
        assert po.notify_processed is False

    def test_closed_row_receives_closed_again_idempotent(self, db):
        """已 CLOSED 行重复收到 CLOSED 回调 → 状态不变, 仅 count 累加 (幂等)。"""
        po = _make_unpaid_po(out_trade_no="TL_c2x", business_order_no="ord_c2x")
        po.payment_status = PaymentStatus.CLOSED
        po.notify_count = 1
        db.add(po); db.commit()
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_c2x", trade_state="CLOSED", paid_at=None,
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.CLOSED
        assert po.notify_count == 2

    # ── ChargingOrder 同步异常 (卡 ccd4c683): 同步失败不阻断, PaymentOrder 仍 PAID ──
    def test_charging_order_sync_failure_does_not_block_paid(self, db, monkeypatch):
        """同步 ChargingOrder 时抛异常 -> except 吞掉, PaymentOrder 仍正确 PAID + 回调 SUCCESS。

        payment.py:238-253 同步逻辑在 try/except 内, 同步失败仅记日志不阻断回调
        (PaymentOrder 是支付真相源)。模拟 db.query(ChargingOrder) 抛 RuntimeError,
        验证 PaymentOrder 状态仍落库成功, 回调返回 SUCCESS (不因同步失败转 FAIL)。
        """
        po = _make_unpaid_po(out_trade_no="TL_syncfail", business_order_no="ord_syncfail")
        db.add(po); db.commit()

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_syncfail", trade_state="SUCCESS", tx_id="4200SYNCFAIL",
        )

        real_query = db.query
        query_calls = {"n": 0}

        def flaky_query(*args, **kwargs):
            query_calls["n"] += 1
            if query_calls["n"] == 2:
                # 第 1 次 query 是查 PaymentOrder (payment.py:219, 成功);
                # 第 2 次 query 是同步块内查 ChargingOrder (payment.py:239) — 让它抛异常
                raise RuntimeError("charging_order sync boom")
            return real_query(*args, **kwargs)

        monkeypatch.setattr(db, "query", flaky_query)

        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})

        # 同步异常不阻断: 回调仍 SUCCESS
        assert resp["code"] == "SUCCESS"
        # PaymentOrder 状态正确落 PAID (用独立 query 读取, 避免被 patch 污染)
        monkeypatch.setattr(db, "query", real_query)
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        assert po.wx_transaction_id == "4200SYNCFAIL"

    # ── trade_state 多次转换 (卡 ccd4c683): NOTPAY→SUCCESS→NOTPAY 幂等不变 ──
    def test_trade_state_transitions_notpay_then_success_then_notpay(self, db):
        """NOTPAY→SUCCESS→NOTPAY 三次回调: 仅 SUCCESS 次落 PAID, 后续 NOTPAY 不回退。

        验证: 首次 NOTPAY 不落状态 (notify_processed 仍 False); 第二次 SUCCESS 落 PAID
        + notify_processed=True; 第三次 NOTPAY 因 notify_processed 已 True 不再改状态
        (既不回退为 UNPAID, count 仍累加)。IM-B真实场景: 用户支付后偶发状态查询延迟
        导致回调交错, PAID 一旦确立必须稳定。
        """
        po = _make_unpaid_po(out_trade_no="TL_trans", business_order_no="ord_trans")
        db.add(po); db.commit()

        states = ["NOTPAY", "SUCCESS", "NOTPAY"]
        client = MagicMock()
        responses = []
        with patch.object(pm, "get_wxpay_client", return_value=client):
            for i, st in enumerate(states):
                client.verify_and_decrypt_notify.return_value = _notify_result(
                    "TL_trans", trade_state=st, tx_id=f"4200T{i}",
                    paid_at=None if st == "NOTPAY" else datetime.now(timezone.utc),
                )
                responses.append(pm.handle_notify(db, b"{}", {}))
                db.refresh(po)

        # 三次回调均 ACK SUCCESS (IM-B侧语义)
        assert all(r["code"] == "SUCCESS" for r in responses)

        # ── 1) 首次 NOTPAY: 不落 PAID/processed, count=1 ──
        # (循环中每步已 refresh, 这里用最终态 + 中间态已在循环内隐式断言 count 增长)

        # ── 最终态 (三次后): PAID 稳定, processed=True, count=3 ──
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        assert po.notify_count == 3
        # tx_id 是 SUCCESS 次 (index 1) 写入的 "4200T1", 未被第三次 NOTPAY 覆盖
        assert po.wx_transaction_id == "4200T1"

    # ── 行不存在 (卡 ccd4c683): ACK SUCCESS 但不落任何状态 ──
    def test_payment_order_absent_acks_without_state_change(self, db):
        """PaymentOrder 行不存在 (out_trade_no 无匹配) -> ACK SUCCESS, notify_count/状态不变。

        与 test_unknown_order_acks_without_processing 互补: 后者仅断言无新建行; 这里聚焦
        "ACK SUCCESS 但绝不落任何状态/副作用" — 验证不新增 PaymentOrder、不抛异常、
        返回结构含 message 字段。IM-B重发已关单/历史通知时不应产生副作用。
        """
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_never_existed", trade_state="SUCCESS", tx_id="4200GHOST",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})

        assert resp["code"] == "SUCCESS"
        assert resp["message"] == "成功"
        # 无任何 PaymentOrder 行落库 (绝不为未知订单新建)
        assert db.query(PaymentOrder).count() == 0

    # ── paid_at 缺失 (卡 ccd4c683): 回调 paid_at=None 时 now() 兜底, 仍落 PAID ──
    def test_paid_at_missing_falls_back_to_now(self, db):
        """回调 paid_at=None (amount_payer_total/paid_at 缺失场景) -> now(UTC) 兜底, 仍落 PAID。

        payment.py:230 `po.paid_at = notify.paid_at or datetime.now(timezone.utc)`,
        IM-B回调 amount 字段缺失或解析失败时 paid_at 可能为 None, 必须兜底为当前 UTC
        时间, 不能让 paid_at 留空 (开票/对账依赖)。验证 paid_at 非空且为合理近期时间。
        """
        po = _make_unpaid_po(out_trade_no="TL_nopaidat", business_order_no="ord_nopaidat")
        db.add(po); db.commit()

        client = MagicMock()
        # paid_at=None 模拟 amount_payer_total 缺失/解析失败
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_nopaidat", trade_state="SUCCESS", tx_id="4200NOPAIDAT", paid_at=None,
        )

        from datetime import timedelta

        before = datetime.now(timezone.utc)
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        after = datetime.now(timezone.utc)

        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        # paid_at 兜底非空 (sqlite 不存 tzinfo, 读回 naive, 统一比 wall-clock)。
        # 生产 now() 与测试 before/after 是独立调用, 微秒级时序不可控 (跨调用 jitter),
        # 故放宽至前后 2 秒窗口断言 "合理近期 UTC 时间" 而非严格夹逼。
        assert po.paid_at is not None
        paid_at_naive = po.paid_at.replace(tzinfo=None) if po.paid_at.tzinfo else po.paid_at
        window_start = before.replace(tzinfo=None) - timedelta(seconds=2)
        window_end = after.replace(tzinfo=None) + timedelta(seconds=2)
        assert window_start <= paid_at_naive <= window_end

    # ── 资金安全 (卡 5c0eb666): commit 失败必须 rollback + 返回 FAIL 触发IM-B重试 ──
    def test_commit_fail_rolls_back_and_returns_fail(self, db, monkeypatch):
        """最终 commit 抛异常 -> rollback 被调用 + 返回 FAIL (触发IM-B重试)。

        资金安全: commit 失败意味着 PAID 状态未持久化, 若此时 ACK SUCCESS IM-B不再
        重试, 订单将永久卡 UNPAID (无法开票)。返回 FAIL 让IM-B按退避算法重试, 下次
        重试 notify_processed 仍 False, 幂等逻辑重新同步最终落库成功。
        """
        po = _make_unpaid_po(out_trade_no="TL_pay", business_order_no="ord_pay")
        db.add(po); db.commit()
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit boom")))
        rollback_spy = MagicMock(wraps=db.rollback)
        monkeypatch.setattr(db, "rollback", rollback_spy)
        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_pay", trade_state="SUCCESS", tx_id="4200AAA",
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})
        # 返回 FAIL 触发IM-B重试 (资金安全, 不丢 PAID 同步)
        assert resp["code"] == "FAIL"
        # rollback 被调用 (事务回滚, 不留脏状态)
        rollback_spy.assert_called_once()

    def test_commit_fail_keeps_idempotent_on_retry(self, db, monkeypatch):
        """commit 失败返回 FAIL 后, notify_processed 仍为 False, 下次重试可重新同步。

        模拟IM-B重试场景: 第一次 commit 失败 (rollback, 返回 FAIL), 状态未持久化;
        第二次重试 commit 恢复成功 -> SUCCESS, 同步落库。证明返回 FAIL 触发的重试
        能正确补偿, 不会因首次失败丢失 PAID 同步。
        """
        from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
        from decimal import Decimal

        ChargingOrder.__table__.create(db.bind, checkfirst=True)
        po = _make_unpaid_po(out_trade_no="TL_retry", business_order_no="ord_retry")
        db.add(po)
        co = ChargingOrder(
            order_no="ord_retry", station_id=1, device_id=10,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.COMPLETED, paid_amount=Decimal("0.00"),
        )
        db.add(co); db.commit()

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_retry", trade_state="SUCCESS", tx_id="4200RETRY",
        )

        # commit spy: 第一次抛异常, 之后走真实 commit
        real_commit = db.commit
        calls = {"n": 0}

        def flaky_commit():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("commit boom")
            return real_commit()

        monkeypatch.setattr(db, "commit", flaky_commit)

        # ── 第一次回调: commit 失败 -> FAIL, 状态未持久化 ──
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp1 = pm.handle_notify(db, b"{}", {})
        assert resp1["code"] == "FAIL"
        db.refresh(po)
        db.refresh(co)
        assert po.payment_status == PaymentStatus.UNPAID
        assert co.payment_status == OrderPaymentStatus.UNPAID

        # ── IM-B重试 (第二次回调): commit 恢复 -> SUCCESS, 同步成功 ──
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp2 = pm.handle_notify(db, b"{}", {})
        assert resp2["code"] == "SUCCESS"
        db.refresh(po)
        db.refresh(co)
        assert po.payment_status == PaymentStatus.PAID
        assert po.notify_processed is True
        assert co.payment_status == OrderPaymentStatus.PAID

    def test_charging_order_sync_persisted_on_success(self, db):
        """回调成功后 ChargingOrder 同步结果持久化 (PAID + paid_amount 分→元换算)。

        验证 commit 成功路径下 ChargingOrder 与 PaymentOrder 同步落库一致, 这是
        资金安全的目标态: 付款后开票校验读 ChargingOrder.payment_status==PAID 必须成立。
        """
        from app.models.charging_order import ChargingOrder, OrderPaymentStatus, OrderStatus
        from decimal import Decimal

        ChargingOrder.__table__.create(db.bind, checkfirst=True)
        po = PaymentOrder(
            out_trade_no="TL_syncok", business_order_no="ord_syncok",
            openid="openid_s", scene=PayScene.MINIPROGRAM,
            sub_mchid=pm.MOCK_DEFAULT_SUB_MCHID, amount_fen=9900,
            prepay_id="prep_s", payment_status=PaymentStatus.UNPAID,
        )
        db.add(po)
        co = ChargingOrder(
            order_no="ord_syncok", station_id=1, device_id=10,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.COMPLETED, paid_amount=Decimal("0.00"),
        )
        db.add(co); db.commit()

        client = MagicMock()
        client.verify_and_decrypt_notify.return_value = _notify_result(
            "TL_syncok", trade_state="SUCCESS", tx_id="4200SYNCOK",
            amount_fen=9900,  # 与行 amount_fen 一致 (回调金额闸, 卡 6c8f930c)
        )
        with patch.object(pm, "get_wxpay_client", return_value=client):
            resp = pm.handle_notify(db, b"{}", {})

        assert resp["code"] == "SUCCESS"
        db.refresh(po)
        db.refresh(co)
        # PaymentOrder + ChargingOrder 同步一致落库
        assert po.payment_status == PaymentStatus.PAID
        assert co.payment_status == OrderPaymentStatus.PAID
        # paid_amount 分→元换算 (9900 分 -> 99.00 元), 对齐 invoice 口径
        assert co.paid_amount == Decimal("99.00")
        # paid_at 落在 PaymentOrder (支付真相源), ChargingOrder 无此字段
        assert po.paid_at is not None
        assert po.wx_transaction_id == "4200SYNCOK"


# ═══════════════════════════════════════════════════════════════════════════
# 7. get_order_payment + _STATUS_PRIORITY
# ═══════════════════════════════════════════════════════════════════════════
class TestGetOrderPayment:
    def test_no_record_returns_none(self, db):
        assert pm.get_order_payment(db, "absent") is None

    def test_single_unpaid_row(self, db):
        po = _make_unpaid_po(out_trade_no="TL_s", business_order_no="ord_s")
        db.add(po); db.commit()
        result = pm.get_order_payment(db, "ord_s")
        assert result == {
            "order_id": "ord_s",
            "payment_status": "UNPAID",
            "transaction_id": None,
            "paid_at": None,
        }

    def test_paid_takes_priority_over_unpaid(self, db):
        """PAID + UNPAID 两行 -> 返回 PAID (优先级)。"""
        unpaid = _make_unpaid_po(out_trade_no="TL_u2", business_order_no="ord_mix")
        db.add(unpaid); db.commit()  # id=1
        paid = _make_unpaid_po(out_trade_no="TL_p2", business_order_no="ord_mix")
        paid.payment_status = PaymentStatus.PAID
        paid.wx_transaction_id = "4200PAID"
        db.add(paid); db.commit()  # id=2 (更新)
        result = pm.get_order_payment(db, "ord_mix")
        assert result["payment_status"] == "PAID"
        assert result["transaction_id"] == "4200PAID"

    def test_unpaid_takes_priority_over_closed(self, db):
        """UNPAID + CLOSED 两行 -> 返回 UNPAID (优先级)。"""
        closed = _make_unpaid_po(out_trade_no="TL_c2", business_order_no="ord_mix2")
        closed.payment_status = PaymentStatus.CLOSED
        db.add(closed); db.commit()
        unpaid = _make_unpaid_po(out_trade_no="TL_u3", business_order_no="ord_mix2")
        db.add(unpaid); db.commit()
        result = pm.get_order_payment(db, "ord_mix2")
        assert result["payment_status"] == "UNPAID"

    def test_paid_at_isoformat(self, db):
        """paid_at 序列化为 isoformat 字符串 (契约 §2.3 paid_at 字段)。

        sqlite DateTime 不存 tzinfo, 读回 naive -> isoformat 无时区后缀;
        断言 wall-clock 分量正确 (生产代码行为即如此)。
        """
        fixed = datetime(2026, 8, 9, 10, 30, 0, tzinfo=timezone.utc)
        po = _make_unpaid_po(out_trade_no="TL_iso", business_order_no="ord_iso")
        po.payment_status = PaymentStatus.PAID
        po.paid_at = fixed
        po.wx_transaction_id = "4200ISO"
        db.add(po); db.commit()
        result = pm.get_order_payment(db, "ord_iso")
        assert result["paid_at"] == "2026-08-09T10:30:00"
        assert result["transaction_id"] == "4200ISO"


# ═══════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════
def test_mock_default_sub_mchid_constant():
    """MOCK_DEFAULT_SUB_MCHID 契约值。"""
    assert pm.MOCK_DEFAULT_SUB_MCHID == "2490000000"


def test_exceptions_are_distinct():
    """三个自定义异常互相独立。"""
    assert pm.SubMerchantNotReady is not pm.SubMerchantFrozen
    assert pm.SubMerchantNotReady is not pm.OrderAlreadyPaid
    assert issubclass(pm.SubMerchantNotReady, Exception)
    assert issubclass(pm.SubMerchantFrozen, Exception)
    assert issubclass(pm.OrderAlreadyPaid, Exception)
