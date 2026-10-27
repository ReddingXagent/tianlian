"""
运营结算对账定时任务测试
"""
import pytest
from datetime import date, datetime
from decimal import Decimal

from app.tasks import settlement_tasks
from app.tasks.settlement_tasks import build_daily_settlement, reconcile_payments
from app.models.charging_order import ChargingOrder, OrderStatus, PaymentMethod
from app.models.ops_settlement.daily_settlement import DailySettlement, SettlementStatus
from app.models.ops_settlement.payment_reconciliation import PaymentReconciliation, ReconciliationStatus


def _make_order(kwh, electricity, service, end_dt, status=OrderStatus.COMPLETED,
                payment=PaymentMethod.WECHAT, paid=None, discount=0, coupon=0, points=0):
    total = Decimal(str(electricity)) + Decimal(str(service))
    if paid is None:
        paid = total - Decimal(str(discount)) - Decimal(str(coupon)) - Decimal(str(points))
    return ChargingOrder(
        order_no=f"SETTLE-{end_dt.strftime('%Y%m%d%H%M')}-{kwh}",
        station_id=1, device_id=1,
        charged_kwh=kwh, electricity_fee=electricity, service_fee=service,
        parking_fee=0, occupancy_fee=0, reservation_fee=0,
        total_amount=total, paid_amount=paid,
        discount_amount=discount, coupon_amount=coupon, points_amount=points,
        end_time=end_dt, order_status=status, payment_method=payment,
    )


class TestDailySettlement:

    def test_aggregates_completed_orders(self, test_db):
        db = test_db["session"]
        dt = datetime(2026, 7, 15, 12, 0)
        db.add_all([
            _make_order(50, 40, 10, dt),
            # 18:00 UTC = 上海次日 02:00 → 归次日业务日 (卡 f7422bbc naive-UTC 口径), 改 09:00
            _make_order(80, 64, 16, datetime(2026, 7, 15, 9, 0)),
        ])
        db.flush()

        result = build_daily_settlement(db, "2026-07-15")

        assert result["status"] == "completed"
        assert result["orders"] == 2
        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert s.total_orders == 2
        assert float(s.total_energy_kwh) == 130.0
        assert float(s.total_charge_fee) == 104.0
        assert float(s.total_service_fee) == 26.0
        assert float(s.total_amount) == 130.0

    def test_auto_confirm_when_balanced(self, test_db):
        db = test_db["session"]
        db.add(_make_order(100, 80, 20, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert s.status == SettlementStatus.CONFIRMED
        assert s.confirmed_by == "system_auto"

    def test_idempotent_rerun(self, test_db):
        db = test_db["session"]
        db.add(_make_order(100, 80, 20, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")
        build_daily_settlement(db, "2026-07-15")

        rows = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).all()
        assert len(rows) == 1

    def test_no_orders_skips(self, test_db):
        db = test_db["session"]
        result = build_daily_settlement(db, "2026-07-15")
        assert result["orders"] == 0
        assert db.query(DailySettlement).count() == 0

    def test_excludes_other_dates(self, test_db):
        db = test_db["session"]
        db.add(_make_order(100, 80, 20, datetime(2026, 7, 14, 10, 0)))
        db.add(_make_order(50, 40, 10, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        result = build_daily_settlement(db, "2026-07-15")
        assert result["orders"] == 1


def _make_refund(order_id, amount, status, refunded_at):
    from app.models.order_fee_item import RefundRecord
    return RefundRecord(
        order_id=order_id, refund_amount=amount, reason="测试退款",
        status=status, refunded_at=refunded_at,
    )


class TestDailySettlementRefund:
    """total_refund 接入 RefundRecord 真实聚合 (卡 8e2be954)。
    口径: status=REFUNDED 且 refunded_at 落在 [day_start, day_end) 当日窗口。"""

    def test_refunded_included_in_total_and_expected(self, test_db):
        from app.models.order_fee_item import RefundStatus
        db = test_db["session"]
        # 生产口径: paid_amount=100 毛实付(complete_refund 不核减), total_amount=95(用户实得部分),
        # 当日 REFUNDED 退款5 → 净额 expected=(100-5)+0=95 == total → 自动确认
        order = _make_order(100, Decimal("95"), Decimal("0"), datetime(2026, 7, 15, 10, 0),
                            paid=Decimal("100"))
        db.add(order)
        db.flush()
        db.add(_make_refund(order.id, Decimal("5.00"), RefundStatus.REFUNDED,
                            datetime(2026, 7, 15, 14, 0)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 5.0
        # 净额口径: 毛实付-退款+优惠 == total_amount → 自动确认
        assert s.status == SettlementStatus.CONFIRMED

    def test_no_refund_zero_regression(self, test_db):
        db = test_db["session"]
        db.add(_make_order(100, 80, 20, datetime(2026, 7, 15, 10, 0)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 0.0

    def test_non_refunded_statuses_excluded(self, test_db):
        from app.models.order_fee_item import RefundStatus
        db = test_db["session"]
        order = _make_order(100, 80, 20, datetime(2026, 7, 15, 10, 0))
        db.add(order)
        db.flush()
        dt = datetime(2026, 7, 15, 14, 0)
        db.add_all([
            _make_refund(order.id, Decimal("1.00"), RefundStatus.PENDING, None),
            _make_refund(order.id, Decimal("2.00"), RefundStatus.APPROVED, dt),
            _make_refund(order.id, Decimal("3.00"), RefundStatus.REJECTED, dt),
        ])
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 0.0

    def test_refunded_with_null_refunded_at_excluded(self, test_db):
        from app.models.order_fee_item import RefundStatus
        db = test_db["session"]
        order = _make_order(100, 80, 20, datetime(2026, 7, 15, 10, 0))
        db.add(order)
        db.flush()
        db.add(_make_refund(order.id, Decimal("7.00"), RefundStatus.REFUNDED, None))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 0.0

    def test_next_day_midnight_boundary_excluded(self, test_db):
        from app.models.order_fee_item import RefundStatus
        db = test_db["session"]
        order = _make_order(100, 80, 20, datetime(2026, 7, 15, 10, 0))
        db.add(order)
        db.flush()
        db.add(_make_refund(order.id, Decimal("9.00"), RefundStatus.REFUNDED,
                            datetime(2026, 7, 16, 0, 0)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 0.0


class TestReconcilePayments:

    def test_reconciles_by_channel(self, test_db):
        db = test_db["session"]
        dt = datetime(2026, 7, 15, 12, 0)
        db.add_all([
            _make_order(50, 40, 10, dt, payment=PaymentMethod.WECHAT),
            _make_order(80, 64, 16, dt, payment=PaymentMethod.ALIPAY),
        ])
        db.flush()

        result = reconcile_payments(db, "2026-07-15")

        assert result["status"] == "completed"
        assert result["channels_reconciled"] == 2
        recons = db.query(PaymentReconciliation).filter(
            PaymentReconciliation.settlement_date == date(2026, 7, 15)
        ).all()
        assert len(recons) == 2
        for r in recons:
            assert r.status == ReconciliationStatus.RECONCILED
            assert r.difference_count == 0

    def test_idempotent(self, test_db):
        db = test_db["session"]
        db.add(_make_order(50, 40, 10, datetime(2026, 7, 15, 12, 0)))
        db.flush()

        reconcile_payments(db, "2026-07-15")
        reconcile_payments(db, "2026-07-15")

        rows = db.query(PaymentReconciliation).filter(
            PaymentReconciliation.settlement_date == date(2026, 7, 15)
        ).all()
        assert len(rows) == 1


# ═══════════════════════════════════════════════════════════════════
# 默认 target_date 业务时区昨日 wiring (卡 c42ac99a)
# ═══════════════════════════════════════════════════════════════════

class TestDefaultTargetBizTz:
    """settlement_daily / settlement_reconcile 无参调用 → 默认 target 取业务时区昨日。

    beat 按上海凌晨触发; 旧实现 date.today()-1d 在 UTC 容器错算"上海前天"。
    此处 patch yesterday_in_biz_tz 为边界固定值, 捕获下游 build/reconcile 收到的日期,
    证明默认分支确实消费 helper (时区逻辑本身见 test_tasks_tz_utils.py)。
    """

    @pytest.fixture
    def captured(self, monkeypatch):
        """patch helper 为边界值 (上海 08-07 01:00 = UTC 08-06 17:00 的业务昨日 08-06),
        SessionLocal 为假对象, 捕获下游收到的 target_date。"""
        box = {}
        monkeypatch.setattr(settlement_tasks, "yesterday_in_biz_tz", lambda: date(2026, 8, 6))

        class _FakeDB:
            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(settlement_tasks, "SessionLocal", lambda: _FakeDB())
        return box

    def test_daily_default_target_is_biz_yesterday(self, captured, monkeypatch):
        def _capture(db, td):
            captured["target_date"] = td
            return {"status": "completed"}

        monkeypatch.setattr(settlement_tasks, "build_daily_settlement", _capture)
        result = settlement_tasks.settlement_daily.__wrapped__()
        assert result["status"] == "completed"
        assert captured["target_date"] == "2026-08-06"

    def test_reconcile_default_target_is_biz_yesterday(self, captured, monkeypatch):
        def _capture(db, td):
            captured["target_date"] = td
            return {"status": "completed"}

        monkeypatch.setattr(settlement_tasks, "reconcile_payments", _capture)
        settlement_tasks.settlement_reconcile.__wrapped__()
        assert captured["target_date"] == "2026-08-06"

    def test_explicit_target_not_overridden(self, captured, monkeypatch):
        """显式传 target_date 时不走默认分支 (手动补算场景)。"""
        def _capture(db, td):
            captured["target_date"] = td
            return {"status": "completed"}

        monkeypatch.setattr(settlement_tasks, "build_daily_settlement", _capture)
        settlement_tasks.settlement_daily.__wrapped__("2026-01-15")
        assert captured["target_date"] == "2026-01-15"


# ═══════════════════════════════════════════════════════════════════
# 业务日边界换算 UTC-naive 窗口 (卡 f7422bbc, 时区缺陷族第7弹)
# ═══════════════════════════════════════════════════════════════════

class TestBizDayBoundaryUtcWindow:
    """end_time/refunded_at 统一 naive-UTC 落库后, 业务日窗口 = 上海日边界换算的
    UTC-naive [start, end)。上海 23:30 / 00:30 (墙钟) 结束的订单与到账退款
    必须归属正确的业务日 daily_settlement — 旧裸 naive 窗口会把上海 00:00-08:00
    的数据整体错归前一日 (auto_confirm 失衡)。种子全部按 naive-UTC 口径构造
    (上海墙钟 - 8h), 与生产落库一致。"""

    def test_shanghai_2330_belongs_to_same_biz_day(self, test_db):
        """上海 7/15 23:30 结束 = UTC 7/15 15:30 → 归 7/15 业务日 (而非被裸 UTC 日窗口归 7/15 侥幸/错日)。"""
        db = test_db["session"]
        db.add(_make_order(50, 40, 10, datetime(2026, 7, 15, 15, 30)))
        db.flush()

        result = build_daily_settlement(db, "2026-07-15")
        assert result["orders"] == 1

    def test_shanghai_0030_belongs_to_same_biz_day_next_utc_date(self, test_db):
        """上海 7/15 00:30 结束 = UTC 7/14 16:30 → 归 7/15 业务日。
        旧裸 naive 窗口 [7/15 00:00, 7/16 00:00) 会漏掉它 (归错 7/14)。"""
        db = test_db["session"]
        db.add(_make_order(50, 40, 10, datetime(2026, 7, 14, 16, 30)))
        db.flush()

        result = build_daily_settlement(db, "2026-07-15")
        assert result["orders"] == 1
        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_amount) == 50.0

    def test_shanghai_0030_not_in_prior_biz_day(self, test_db):
        """同一单 (UTC 7/14 16:30 = 上海 7/15 00:30) 不得归入 7/14 业务日。"""
        db = test_db["session"]
        db.add(_make_order(50, 40, 10, datetime(2026, 7, 14, 16, 30)))
        db.flush()

        result = build_daily_settlement(db, "2026-07-14")
        assert result["orders"] == 0

    def test_refund_shanghai_0030_attributed_to_biz_day(self, test_db):
        """上海 7/15 00:30 到账退款 (UTC 7/14 16:30) 必须计入 7/15 日结 total_refund。"""
        from app.models.order_fee_item import RefundStatus
        db = test_db["session"]
        order = _make_order(100, Decimal("95"), Decimal("0"),
                            datetime(2026, 7, 14, 16, 30), paid=Decimal("100"))
        db.add(order)
        db.flush()
        db.add(_make_refund(order.id, Decimal("5.00"), RefundStatus.REFUNDED,
                            datetime(2026, 7, 14, 16, 45)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 5.0
        # 毛实付100 - 退款5 + 0 == total 95 → 自动确认
        assert s.status == SettlementStatus.CONFIRMED

    def test_refund_shanghai_2330_attributed_to_biz_day(self, test_db):
        """上海 7/15 23:30 到账退款 (UTC 7/15 15:30) 计入 7/15 而非 7/16。"""
        from app.models.order_fee_item import RefundStatus
        db = test_db["session"]
        order = _make_order(100, Decimal("95"), Decimal("0"),
                            datetime(2026, 7, 15, 2, 0), paid=Decimal("100"))
        db.add(order)
        db.flush()
        db.add(_make_refund(order.id, Decimal("3.00"), RefundStatus.REFUNDED,
                            datetime(2026, 7, 15, 15, 30)))
        db.flush()

        build_daily_settlement(db, "2026-07-15")

        s = db.query(DailySettlement).filter(DailySettlement.settlement_date == date(2026, 7, 15)).one()
        assert float(s.total_refund) == 3.0

    def test_window_exactly_biz_midnight_utc_edge(self, test_db):
        """窗口边界: 上海 7/16 00:00 = UTC 7/15 16:00 恰为 7/15 业务日上界(半开) → 归 7/16。"""
        db = test_db["session"]
        db.add(_make_order(50, 40, 10, datetime(2026, 7, 15, 16, 0)))
        db.flush()

        assert build_daily_settlement(db, "2026-07-15")["orders"] == 0
        assert build_daily_settlement(db, "2026-07-16")["orders"] == 1
