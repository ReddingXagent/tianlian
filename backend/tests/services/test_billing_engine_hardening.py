"""
billing_engine 防御性加固测试 — 入参 sanitize 不彻底导致的崩溃缺口 (卡 e13e2c94)。

billing_engine 主流程的事务保护/除零守卫/契约式 raise 已就位, 真实缺口集中在
入参的 None / 非法字符串 / 非 dict 经 ``Decimal(str(x))`` 转换时抛 InvalidOperation
或 AttributeError, 使整单计算崩溃。

设计原则(与 billing.py 加固 / 既有契约共存):
- None / 非法字符串 / None rule dict  → 安全降级(0 或空结构), 不崩, 不多收费;
- 契约式 ValueError(未知 fee_type / 缺 slot 价格 / 时段重叠) 保留 raise
  (test_billing_engine*.py 多处 pytest.raises 依赖, 不可改成静默吞);
- settle_order_fees DB 异常 → rollback + reraise, 不留脏数据。
"""
import pytest
from decimal import Decimal
from datetime import datetime, time

from app.services import billing_engine
from app.services.billing_engine import (
    _safe_decimal,
    compute_tou_energy_fee,
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    compute_order_fees,
    settle_order_fees,
)


# ═══════════════════════════════════════════════════════════════
# 0. _safe_decimal helper
# ═══════════════════════════════════════════════════════════════

class TestSafeDecimal:
    """None / 非法字符串 / 非数值类型 → default, 不抛 InvalidOperation。"""

    def test_none_returns_default_zero(self):
        assert _safe_decimal(None) == Decimal("0.00")

    def test_none_custom_default(self):
        assert _safe_decimal(None, Decimal("5")) == Decimal("5")

    def test_invalid_string_returns_zero(self):
        assert _safe_decimal("abc") == Decimal("0.00")

    def test_normal_decimal(self):
        assert _safe_decimal(Decimal("1.5")) == Decimal("1.50")

    def test_int(self):
        assert _safe_decimal(50) == Decimal("50.00")

    def test_float(self):
        assert _safe_decimal(0.8) == Decimal("0.80")

    def test_numeric_string(self):
        assert _safe_decimal("0.8") == Decimal("0.80")

    def test_nan_returns_default(self):
        assert _safe_decimal(Decimal("NaN")) == Decimal("0.00")

    def test_infinity_returns_default(self):
        assert _safe_decimal(Decimal("Infinity")) == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 1. compute_service_fee_multi — None 入参不崩
# ═══════════════════════════════════════════════════════════════

class TestServiceFeeNoneSafe:
    def test_fee_value_none_fixed(self):
        """fixed 模式 fee_value=None → 0, 不崩(配置缺失/解析失败)。"""
        assert compute_service_fee_multi(Decimal("10"), "fixed", None) == Decimal("0.00")

    def test_fee_value_none_percent(self):
        assert compute_service_fee_multi(Decimal("10"), "percent", None) == Decimal("0.00")

    def test_kwh_none_percent(self):
        """percent 模式 kwh=None → 按 0 电量 → 0。"""
        assert compute_service_fee_multi(None, "percent", Decimal("0.5")) == Decimal("0.00")

    def test_fee_value_invalid_string(self):
        assert compute_service_fee_multi(Decimal("10"), "fixed", "abc") == Decimal("0.00")

    def test_unknown_fee_type_still_raises(self):
        """契约保留: 未知 mode 仍 raise(配置错误需感知)。"""
        with pytest.raises(ValueError):
            compute_service_fee_multi(Decimal("10"), "mystery", Decimal("1"))

    def test_normal_fixed_unchanged(self):
        assert compute_service_fee_multi(Decimal("10"), "fixed", Decimal("3")) == Decimal("3.00")

    def test_normal_percent_unchanged(self):
        assert compute_service_fee_multi(Decimal("10"), "percent", Decimal("0.5")) == Decimal("5.00")


# ═══════════════════════════════════════════════════════════════
# 2. compute_tou_energy_fee — None / 脏值入参不崩
# ═══════════════════════════════════════════════════════════════

class TestTouNoneSafe:
    def _slots(self):
        return [{"slot_id": "s1", "period_type": "peak",
                 "start_time": time(0, 0), "end_time": time(23, 59)}]

    def test_total_kwh_none_returns_empty(self):
        """kwh=None 不崩, 返回空结构(不入计费)。"""
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            None, self._slots(), {"s1": Decimal("0.8")},
        )
        assert r["total_fee"] == Decimal("0.00")
        assert r["total_energy"] == Decimal("0.00")

    def test_slot_price_none_skipped(self):
        """slot 价格=None → 该 slot 电量降级排除, 不崩, 不免费充电(=排除)。"""
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("10"), self._slots(), {"s1": None},
        )
        # 价格缺失的 slot 被安全跳过 → total_fee/energy 为 0
        assert r["total_fee"] == Decimal("0.00")

    def test_slot_price_invalid_string_skipped(self):
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("10"), self._slots(), {"s1": "not-a-price"},
        )
        assert r["total_fee"] == Decimal("0.00")

    def test_total_minutes_zero_returns_empty(self):
        """除零守卫: start==end → total_minutes=0 → 空结构, 不 DivisionByZero。"""
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 10),
            Decimal("10"), self._slots(), {"s1": Decimal("0.8")},
        )
        assert r["total_fee"] == Decimal("0.00")
        assert r["coverage"] == 1.0

    def test_empty_slots_returns_empty(self):
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("10"), [], {"s1": Decimal("0.8")},
        )
        assert r["total_fee"] == Decimal("0.00")

    def test_negative_kwh_returns_empty(self):
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("-10"), self._slots(), {"s1": Decimal("0.8")},
        )
        assert r["total_fee"] == Decimal("0.00")

    def test_normal_unchanged(self):
        """正向计算不被加固影响。"""
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("10"), self._slots(), {"s1": Decimal("0.8")},
        )
        assert r["total_fee"] == Decimal("8.00")
        assert r["total_energy"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 3. compute_parking_fee_full — 脏 rule 不崩
# ═══════════════════════════════════════════════════════════════

class TestParkingDirtyRuleSafe:
    def test_hourly_rate_invalid_string(self):
        """hourly_rate 非数字 → 降级 0 费率, total=0, 不崩。"""
        r = compute_parking_fee_full(120, {"free_minutes": 0, "hourly_rate": "abc"})
        assert r["total"] == Decimal("0.00")

    def test_hourly_rate_none(self):
        r = compute_parking_fee_full(120, {"free_minutes": 0, "hourly_rate": None})
        assert r["total"] == Decimal("0.00")

    def test_missing_hourly_rate(self):
        r = compute_parking_fee_full(120, {"free_minutes": 0})
        assert r["total"] == Decimal("0.00")

    def test_rule_none(self):
        """rule=None 不崩(AttributeError 缺口), total=0。"""
        r = compute_parking_fee_full(120, None)
        assert r["total"] == Decimal("0.00")
        assert r["capped"] is False

    def test_daily_cap_invalid_string_ignored(self):
        """daily_cap 非数字 → 视为无封顶, 不崩。"""
        r = compute_parking_fee_full(
            2000, {"free_minutes": 0, "hourly_rate": "5", "daily_cap": "abc"}
        )
        # hourly_rate=5 * (2000/60) = 166.67, 无有效封顶
        assert r["total"] == Decimal("166.67")
        assert r["capped"] is False

    def test_normal_hourly_unchanged(self):
        r = compute_parking_fee_full(120, {"free_minutes": 0, "hourly_rate": "5"})
        assert r["total"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 4. compute_occupancy_fee_full — 脏 rule / None 不崩
# ═══════════════════════════════════════════════════════════════

class TestOccupancyDirtyRuleSafe:
    def test_rule_none(self):
        """occ_rule=None → AttributeError 缺口, 应返回 0。"""
        assert compute_occupancy_fee_full(60, None) == Decimal("0.00")

    def test_rate_invalid_string(self):
        assert compute_occupancy_fee_full(60, {"rate_per_minute": "abc"}) == Decimal("0.00")

    def test_max_fee_invalid_string_ignored(self):
        """max_fee 非数字 → 视为无封顶, 不崩。"""
        r = compute_occupancy_fee_full(
            120, {"grace_minutes": 0, "rate_per_minute": "0.5", "max_fee": "abc"}
        )
        assert r == Decimal("60.00")

    def test_normal_unchanged(self):
        r = compute_occupancy_fee_full(
            120, {"grace_minutes": 30, "rate_per_minute": "0.5", "max_fee": 10}
        )
        assert r == Decimal("10.00")  # (120-30)*0.5=45 → capped 10


# ═══════════════════════════════════════════════════════════════
# 5. compute_order_fees — None 子项不崩, 该项归 0
# ═══════════════════════════════════════════════════════════════

class TestOrderFeesNoneSafe:
    def test_all_none_fees(self):
        """任一 fee=None → 该项归 0, 不崩, 返回完整 dict。"""
        r = compute_order_fees(None, None, None, None, None)
        assert r["total_amount"] == Decimal("0.00")
        assert r["paid_amount"] == Decimal("0.00")

    def test_none_discount_safe(self):
        r = compute_order_fees(
            Decimal("10"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
            discount_amount=None,
        )
        assert r["discount_amount"] == Decimal("0.00")
        assert r["paid_amount"] == Decimal("10.00")

    def test_none_energy_others_present(self):
        """energy_fee=None 归 0, 其余正常计入。"""
        r = compute_order_fees(
            None, Decimal("5"), Decimal("0"), Decimal("0"), Decimal("0"),
        )
        assert r["total_amount"] == Decimal("5.00")

    def test_invalid_string_fee_safe(self):
        r = compute_order_fees("abc", Decimal("5"), None, None, None)
        assert r["total_amount"] == Decimal("5.00")

    def test_returns_complete_keys(self):
        r = compute_order_fees(None, None, None, None, None)
        assert set(r.keys()) == {
            "total_amount", "discount_amount", "coupon_amount",
            "points_amount", "paid_amount",
        }


# ═══════════════════════════════════════════════════════════════
# 6. settle_order_fees — DB 异常回滚不产生脏数据
# ═══════════════════════════════════════════════════════════════

class TestSettleDbExceptionRollback:
    @staticmethod
    def _make_order(session, order_no):
        from app.models.charging_order import ChargingOrder
        order = ChargingOrder(
            order_no=order_no, station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("20.00"),
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def test_flush_exception_no_dirty_fee_items(self, test_db):
        """写明细阶段 flush 异常 → rollback + reraise, 回滚后无脏 OrderFeeItem 残留。

        (test_billing_engine.py 已验证 rollback 被调用; 此处补充验证"不产生脏数据"
        这个更硬的契约 —— 即便 commit 由调用方控制, settle 内部异常也不留半成品明细。)
        """
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session, "t-hardening-rollback")

        original_flush = session.flush

        def _boom(*a, **kw):
            raise RuntimeError("simulated flush failure")

        session.flush = _boom
        try:
            fees = {"energy_fee": Decimal("10"), "service_fee": Decimal("2")}
            with pytest.raises(RuntimeError):
                settle_order_fees(order, fees, session)
        finally:
            session.flush = original_flush

        # 异常已回滚, 该订单无任何明细残留(不留半成品)
        remaining = (
            session.query(OrderFeeItem)
            .filter(OrderFeeItem.order_id == order.id)
            .count()
        )
        assert remaining == 0


# ═══════════════════════════════════════════════════════════════
# 7. TOU 规则异常 — 跨天时段 end<start 不崩(跨午夜合法) + 非法 time 字段
# ═══════════════════════════════════════════════════════════════

class TestTouMalformedSlots:
    def test_cross_midnight_slot_handled(self):
        """end<start(跨午夜)是合法配置, 不应崩, 正常按跨午夜窗口计费。"""
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 23), datetime(2026, 1, 2, 1),
            Decimal("10"),
            [{"slot_id": "s1", "period_type": "night",
              "start_time": time(22), "end_time": time(6)}],
            {"s1": Decimal("0.5")},
        )
        assert r["total_fee"] == Decimal("5.00")
        assert r["total_energy"] == Decimal("10.00")

    def test_slot_missing_period_type_does_not_crash(self):
        """slot 缺 period_type → 跳过该 slot, 不 KeyError 整单崩溃。"""
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("10"),
            [{"slot_id": "s1", "start_time": time(0), "end_time": time(23, 59)}],
            {"s1": Decimal("0.8")},
        )
        # 缺 period_type 的 slot 被安全跳过
        assert r["total_fee"] == Decimal("0.00")
