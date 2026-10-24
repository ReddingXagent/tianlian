"""
billing_engine 顶层 None 入参异常加固 — BillingError (卡 bf84b6fb)。

与既有测试的分工:
- hardening 卡(e13e2c94) 已覆盖入参 sanitize(None/非法字符串经 Decimal 转换的崩溃);
- edge_cases/boundary 卡已固化"负数入参经 _nonneg/max(0,..) 归零"的契约;
- 本卡覆盖 **顶层公开函数 None 入参的崩溃缺口** 与 **统一 BillingError**:
  * compute_reservation_fee_full(None)         → 旧实现 .get on None → AttributeError;
  * compute_parking_fee_full(None, rule)       → int(None) → TypeError;
  * compute_occupancy_fee_full(None, rule)     → int(None) → TypeError;
  * compute_tou_energy_fee(None, ...)          → .tzinfo on None → AttributeError;

设计原则(纯加固, 与既有契约零冲突):
- 正常路径行为零变更;
- **负数**走既有 _nonneg/max(0,..) 归零守卫(edge_cases/boundary 已固化), 不在此抛错;
- **None 顶层入参**是调用方编程错误 → BillingError(既有测试未固化 None 容忍, 为真缺口);
- compute_reservation_fee_full 的字段级**负数**无 _nonneg 守卫(_q 直接量化保留负值,
  会产生负预约费套利), 且无既有测试固化, 故此处显式拒绝 → BillingError;
- 既有 ValueError(未知 fee_type / 缺 slot 价格 / 时段重叠)契约不变。
"""
import pytest
from decimal import Decimal
from datetime import datetime, time

from app.services.billing_engine import (
    BillingError,
    compute_tou_energy_fee,
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    compute_reservation_fee_full,
    compute_order_fees,
)


# ═══════════════════════════════════════════════════════════════
# 1. compute_reservation_fee_full — rule=None / 非 dict / 负数字段
# ═══════════════════════════════════════════════════════════════

class TestReservationHardening:
    def test_rule_none_raises_billing_error(self):
        """rule=None 顶层编程错误 → BillingError(旧实现 .get on None → AttributeError)。"""
        with pytest.raises(BillingError):
            compute_reservation_fee_full(None)

    def test_rule_not_dict_raises_billing_error(self):
        """rule 非 dict(如 list) → BillingError(.get 缺失)。"""
        with pytest.raises(BillingError):
            compute_reservation_fee_full([("fee_amount", 5)])

    def test_rule_int_raises_billing_error(self):
        with pytest.raises(BillingError):
            compute_reservation_fee_full(42)

    def test_negative_fee_amount_raises(self):
        """负 fee_amount 无 _nonneg 守卫(_q 量化保留负值→负预约费套利) → BillingError。"""
        with pytest.raises(BillingError):
            compute_reservation_fee_full({"fee_amount": Decimal("-5")})

    def test_negative_penalty_raises(self):
        with pytest.raises(BillingError):
            compute_reservation_fee_full({"fee_amount": "2", "no_show_penalty": "-5"})

    def test_normal_flat_unchanged(self):
        """正向路径不受加固影响。"""
        r = compute_reservation_fee_full(
            {"fee_amount": "2", "deposit_amount": "10", "no_show_penalty": "5"},
            no_show=True,
        )
        assert r["fee"] == Decimal("2.00")
        assert r["total"] == Decimal("7.00")

    def test_empty_rule_safe_zero(self):
        """合法但空的 dict(无配置项) → 全 0, 不报错。"""
        r = compute_reservation_fee_full({})
        assert r["fee"] == Decimal("0.00")
        assert r["total"] == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 2. compute_parking_fee_full — parking_minutes=None
# ═══════════════════════════════════════════════════════════════

class TestParkingHardening:
    def test_minutes_none_raises_billing_error(self):
        """parking_minutes=None → BillingError(旧实现 int(None) → TypeError)。"""
        with pytest.raises(BillingError):
            compute_parking_fee_full(None, {"free_minutes": 0, "hourly_rate": "5"})

    def test_negative_minutes_still_clamped(self):
        """负停车时长走既有 max(0,..) 守卫归零(boundary 契约), 不抛 BillingError。"""
        r = compute_parking_fee_full(-10, {"free_minutes": 0, "hourly_rate": "5"})
        assert r["total"] == Decimal("0.00")

    def test_normal_unchanged(self):
        r = compute_parking_fee_full(120, {"free_minutes": 0, "hourly_rate": "5"})
        assert r["total"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 3. compute_occupancy_fee_full — occupancy_minutes=None
# ═══════════════════════════════════════════════════════════════

class TestOccupancyHardening:
    def test_minutes_none_raises_billing_error(self):
        """occupancy_minutes=None → BillingError(旧实现 int(None) → TypeError)。"""
        with pytest.raises(BillingError):
            compute_occupancy_fee_full(None, {"rate_per_minute": "0.5"})

    def test_negative_minutes_still_clamped(self):
        """负占桩时长走既有 max(0,..) 守卫归零(boundary 契约), 不抛 BillingError。"""
        assert compute_occupancy_fee_full(-10, {"rate_per_minute": "0.5"}) == Decimal("0.00")

    def test_normal_unchanged(self):
        r = compute_occupancy_fee_full(
            120, {"grace_minutes": 30, "rate_per_minute": "0.5", "max_fee": 10}
        )
        assert r == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 4. compute_tou_energy_fee — start/end None
# ═══════════════════════════════════════════════════════════════

class TestTouHardening:
    def test_start_time_none_raises_billing_error(self):
        """start_time=None → BillingError(旧实现 .tzinfo on None → AttributeError)。"""
        with pytest.raises(BillingError):
            compute_tou_energy_fee(
                None, datetime(2026, 1, 1, 11), Decimal("10"), [], {}
            )

    def test_end_time_none_raises_billing_error(self):
        with pytest.raises(BillingError):
            compute_tou_energy_fee(
                datetime(2026, 1, 1, 10), None, Decimal("10"), [], {}
            )

    def test_both_none_raises_billing_error(self):
        with pytest.raises(BillingError):
            compute_tou_energy_fee(None, None, Decimal("10"), [], {})

    def test_normal_unchanged(self):
        r = compute_tou_energy_fee(
            datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11),
            Decimal("10"),
            [{"slot_id": "s1", "period_type": "peak",
              "start_time": time(0, 0), "end_time": time(23, 59)}],
            {"s1": Decimal("0.8")},
        )
        assert r["total_fee"] == Decimal("8.00")


# ═══════════════════════════════════════════════════════════════
# 5. compute_order_fees — None 降级 / 负数归零(既有契约) / 超大金额
# ═══════════════════════════════════════════════════════════════

class TestOrderFeesHardening:
    def test_none_still_degrades_to_zero(self):
        """None 走既有 _safe_decimal 降级(不变更), 非 BillingError。"""
        r = compute_order_fees(None, None, None, None, None)
        assert r["total_amount"] == Decimal("0.00")

    def test_negative_fee_clamped_to_zero(self):
        """负费用项走既有 _nonneg 归零(edge_cases 契约), 不抛 BillingError。"""
        r = compute_order_fees(
            Decimal("-10"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
        )
        assert r["total_amount"] == Decimal("0.00")
        assert r["paid_amount"] == Decimal("0.00")

    def test_huge_amount_handled(self):
        """超大金额(万级)正常计算, 不崩, 不精度丢失。"""
        r = compute_order_fees(
            Decimal("999999.99"), Decimal("999999.99"), Decimal("0"), Decimal("0"), Decimal("0"),
        )
        assert r["total_amount"] == Decimal("1999999.98")

    def test_normal_unchanged(self):
        r = compute_order_fees(
            Decimal("10"), Decimal("2"), Decimal("0"), Decimal("0"), Decimal("0"),
            discount_amount=Decimal("3"),
        )
        assert r["total_amount"] == Decimal("12.00")
        assert r["paid_amount"] == Decimal("9.00")


# ═══════════════════════════════════════════════════════════════
# 6. compute_service_fee_multi — None 降级 / 未知 fee_type 契约保留
# ═══════════════════════════════════════════════════════════════

class TestServiceFeeHardening:
    def test_none_still_degrades(self):
        """None 走既有降级(hardening 契约), 非 BillingError。"""
        assert compute_service_fee_multi(Decimal("10"), "fixed", None) == Decimal("0.00")

    def test_unknown_fee_type_still_value_error(self):
        """契约保留: 未知 mode 仍是 ValueError(非 BillingError)。"""
        with pytest.raises(ValueError):
            compute_service_fee_multi(Decimal("10"), "mystery", Decimal("1"))

    def test_normal_unchanged(self):
        assert compute_service_fee_multi(Decimal("10"), "percent", Decimal("0.5")) == Decimal("5.00")


# ═══════════════════════════════════════════════════════════════
# 7. BillingError 类型语义
# ═══════════════════════════════════════════════════════════════

class TestBillingErrorType:
    def test_billing_error_is_value_error_subclass(self):
        """BillingError 继承 ValueError, 兼容宽口径 except ValueError 兜底。"""
        assert issubclass(BillingError, ValueError)

    def test_billing_error_catchable_as_value_error(self):
        """调用方的 except ValueError 仍能捕获 BillingError(向后兼容)。"""
        with pytest.raises(ValueError):  # 不是 BillingError 限定
            compute_reservation_fee_full(None)
