"""
billing_engine 边界与入参 sanitize 补充测试 (卡 b7057076)

背景: test_billing_engine.py(40) + test_billing_engine_edge_cases.py(32) 已覆盖
主干路径与已知缺陷族(共72测试全绿)。本文件聚焦其真实盲区 —— 入参 sanitize 与
边界防御, 不重复已有覆盖:

1. compute_occupancy_fee_full  — None规则/None费率/非法max_fee/部分字段缺失/grace边界
2. compute_reservation_fee_full — 空规则dict/部分字段缺失/None爽约罚款
3. 入参 sanitize 三件套(_safe_decimal/_q/_nonneg) — None/NaN/Inf/非法字符串/负数
4. compute_service_fee_multi   — None fee_value / None fee_type
5. compute_order_fees          — None/非法字符串费用项降级

设计: 纯函数直接断言, 不依赖 DB。
"""
import math
import pytest
from decimal import Decimal
from datetime import datetime, time

from app.services.billing_engine import (
    compute_occupancy_fee_full,
    compute_reservation_fee_full,
    compute_service_fee_multi,
    compute_order_fees,
    compute_parking_fee_full,
    _safe_decimal,
    _q,
    _nonneg,
    _to_amount,
)


# ═══════════════════════════════════════════════════════════════
# 1. 占桩费 — 边界与 sanitize(现有仅 4 个基础测试)
# ═══════════════════════════════════════════════════════════════

class TestOccupancyFeeBoundary:
    """占桩费: None 规则 / None 费率 / 非法封顶 / 部分字段缺失 / grace 边界"""

    def test_none_rule_returns_zero(self):
        """occ_rule=None(调用方未加载到规则) → 不崩, 降级 0 费"""
        assert compute_occupancy_fee_full(30, None) == Decimal("0.00")

    def test_non_dict_rule_returns_zero(self):
        """occ_rule 非 dict(如加载到字符串/列表) → 降级 0 费"""
        assert compute_occupancy_fee_full(30, "not a dict") == Decimal("0.00")
        assert compute_occupancy_fee_full(30, []) == Decimal("0.00")

    def test_none_rate_degrades_to_zero(self):
        """rate_per_minute=None(配置缺失) → 不崩, 费用 0"""
        rule = {"grace_minutes": 0, "rate_per_minute": None, "max_fee": None}
        assert compute_occupancy_fee_full(60, rule) == Decimal("0.00")

    def test_invalid_rate_string_degrades_to_zero(self):
        """rate_per_minute 非法字符串 → _safe_decimal 降级 0"""
        rule = {"grace_minutes": 0, "rate_per_minute": "abc", "max_fee": None}
        assert compute_occupancy_fee_full(60, rule) == Decimal("0.00")

    def test_invalid_max_fee_ignored_not_crushing(self):
        """max_fee=0 / 非法字符串 → cap<=0 视为无封顶, 不把 fee 压成 0"""
        # rate=0.5 × 200min = 100.00; max_fee="abc" → cap=0 → 不压制 → 100.00
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.50"), "max_fee": "abc"}
        assert compute_occupancy_fee_full(200, rule) == Decimal("100.00")
        # max_fee=0 同样不压制
        rule2 = {"grace_minutes": 0, "rate_per_minute": Decimal("0.50"), "max_fee": 0}
        assert compute_occupancy_fee_full(200, rule2) == Decimal("100.00")

    def test_grace_none_treated_as_zero(self):
        """grace_minutes=None → 0(全额计费)"""
        rule = {"grace_minutes": None, "rate_per_minute": Decimal("1.00"), "max_fee": None}
        assert compute_occupancy_fee_full(30, rule) == Decimal("30.00")

    def test_grace_exactly_equals_occupancy(self):
        """占桩时长 == 宽限期(临界) → billable=0, 费用 0"""
        rule = {"grace_minutes": 30, "rate_per_minute": Decimal("0.50"), "max_fee": None}
        assert compute_occupancy_fee_full(30, rule) == Decimal("0.00")

    def test_negative_occupancy_clamped(self):
        """负占桩时长(异常输入) → billable=0, 费用 0"""
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.50"), "max_fee": None}
        assert compute_occupancy_fee_full(-10, rule) == Decimal("0.00")

    def test_empty_rule_dict_no_crash(self):
        """空规则 dict(所有字段缺) → 全部 .get 返回 None → 降级 0"""
        assert compute_occupancy_fee_full(60, {}) == Decimal("0.00")

    def test_decimal_precision_two_places(self):
        """金额量化 2 位: 7min × 0.155 = 1.085 → 1.08(Decimal 默认 ROUND_HALF_EVEN 银行家舍入)"""
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.155"), "max_fee": None}
        # _q/quantize 未指定 rounding → 用 Decimal 上下文默认 ROUND_HALF_EVEN: 1.085 → 1.08
        assert compute_occupancy_fee_full(7, rule) == Decimal("1.08")

    def test_decimal_precision_two_places_half_up(self):
        """向上进位场景验证量化: 7min × 0.156 = 1.092 → 1.09"""
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.156"), "max_fee": None}
        assert compute_occupancy_fee_full(7, rule) == Decimal("1.09")


# ═══════════════════════════════════════════════════════════════
# 2. 预约费 — 空规则/部分缺失(现有仅 3 个基础测试)
# ═══════════════════════════════════════════════════════════════

class TestReservationFeeBoundary:

    def test_empty_rule_all_zero(self):
        """空规则 dict → fee/deposit/penalty/total 全 0"""
        result = compute_reservation_fee_full({})
        assert result["fee"] == Decimal("0.00")
        assert result["deposit"] == Decimal("0.00")
        assert result["no_show_penalty"] == Decimal("0.00")
        assert result["total"] == Decimal("0.00")

    def test_missing_penalty_field_no_show_ok(self):
        """no_show=True 但缺 no_show_penalty → total = fee(不崩)"""
        rule = {"fee_amount": Decimal("5.00"), "deposit_amount": Decimal("0")}
        result = compute_reservation_fee_full(rule, no_show=True)
        assert result["fee"] == Decimal("5.00")
        assert result["no_show_penalty"] == Decimal("0.00")
        assert result["total"] == Decimal("5.00")

    def test_missing_fee_field_only_deposit(self):
        """只配 deposit(可退还冻结) → fee=0, total=0(deposit 不计入实收)"""
        rule = {"deposit_amount": Decimal("50.00")}
        result = compute_reservation_fee_full(rule, no_show=False)
        assert result["fee"] == Decimal("0.00")
        assert result["deposit"] == Decimal("50.00")
        assert result["total"] == Decimal("0.00")

    def test_none_values_treated_as_zero(self):
        """fee_amount/deposit_amount/no_show_penalty 显式 None → 0"""
        rule = {
            "fee_amount": None,
            "deposit_amount": None,
            "no_show_penalty": None,
        }
        result = compute_reservation_fee_full(rule, no_show=True)
        assert result["fee"] == Decimal("0.00")
        assert result["total"] == Decimal("0.00")

    def test_string_amount_coerced(self):
        """字符串金额经 _q(Decimal(str())) 正确转换"""
        rule = {
            "fee_amount": "8.50",
            "deposit_amount": "100",
            "no_show_penalty": "15.25",
        }
        result = compute_reservation_fee_full(rule, no_show=True)
        assert result["fee"] == Decimal("8.50")
        assert result["deposit"] == Decimal("100.00")
        assert result["total"] == Decimal("23.75")  # 8.50 + 15.25


# ═══════════════════════════════════════════════════════════════
# 3. 入参 sanitize 三件套 — None/NaN/Inf/非法字符串/负数
# ═══════════════════════════════════════════════════════════════

class TestSanitizers:

    def test_safe_decimal_none(self):
        assert _safe_decimal(None) == Decimal("0")

    def test_safe_decimal_invalid_string(self):
        assert _safe_decimal("abc") == Decimal("0")

    def test_safe_decimal_nan(self):
        """NaN 非有限 → 降级 default"""
        assert _safe_decimal(Decimal("NaN")) == Decimal("0")

    def test_safe_decimal_infinity(self):
        """Infinity 非有限 → 降级 default"""
        assert _safe_decimal(Decimal("Infinity")) == Decimal("0")
        assert _safe_decimal(Decimal("-Infinity")) == Decimal("0")

    def test_safe_decimal_float_nan(self):
        """float('nan') → 经 str() 成 'nan' → Decimal 非有限 → 0"""
        assert _safe_decimal(float("nan")) == Decimal("0")

    def test_safe_decimal_preserves_precision(self):
        """不量化: 4 位费率 0.5286 保留原样(提前量化会失真)"""
        assert _safe_decimal("0.5286") == Decimal("0.5286")

    def test_safe_decimal_custom_default(self):
        """指定 default 值生效"""
        assert _safe_decimal(None, default=Decimal("-1")) == Decimal("-1")

    def test_safe_decimal_valid_value(self):
        assert _safe_decimal("3.14") == Decimal("3.14")
        assert _safe_decimal(5) == Decimal("5")
        assert _safe_decimal(Decimal("2.5")) == Decimal("2.5")

    def test_q_quantizes_two_places(self):
        """_q 量化到 2 位"""
        assert _q("3.141") == Decimal("3.14")
        assert _q("2.5") == Decimal("2.50")
        assert _q(0) == Decimal("0.00")

    def test_q_none_or_zero_falsy(self):
        """_q(0 or None 经 `or`)→ Decimal('0.00')"""
        assert _q(None or 0) == Decimal("0.00")

    def test_nonneg_negative_to_zero(self):
        """负数归零"""
        assert _nonneg("-5") == Decimal("0.00")
        assert _nonneg(Decimal("-0.01")) == Decimal("0.00")

    def test_nonneg_zero_to_zero(self):
        assert _nonneg(0) == Decimal("0.00")
        assert _nonneg("0") == Decimal("0.00")

    def test_nonneg_positive_kept(self):
        assert _nonneg("5.678") == Decimal("5.68")
        assert _nonneg(Decimal("3")) == Decimal("3.00")

    def test_to_amount_serialization(self):
        """Decimal → 2 位 float; falsy → 0.0"""
        assert _to_amount(Decimal("3.141")) == 3.14
        assert _to_amount(Decimal("0")) == 0.0
        assert _to_amount(None) == 0.0
        # 长浮点尾兜底
        assert _to_amount(0.1 + 0.2) == 0.3


# ═══════════════════════════════════════════════════════════════
# 4. 服务费 — None 入参
# ═══════════════════════════════════════════════════════════════

class TestServiceFeeBoundary:

    def test_none_fee_value_fixed(self):
        """fixed 模式 fee_value=None → 0"""
        assert compute_service_fee_multi(Decimal("50"), "fixed", None) == Decimal("0.00")

    def test_none_fee_value_percent(self):
        """percent 模式 fee_value=None → 0"""
        assert compute_service_fee_multi(Decimal("50"), "percent", None) == Decimal("0.00")

    def test_none_charged_kwh_percent(self):
        """percent 模式 charged_kwh=None → 0(电量未采集)"""
        assert compute_service_fee_multi(None, "percent", Decimal("0.5")) == Decimal("0.00")

    def test_none_fee_type_raises(self):
        """fee_type=None → 进入未知分支抛 ValueError"""
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("40"), None, Decimal("1.0"))

    def test_invalid_fee_value_string(self):
        """fee_value 非法字符串 → _safe_decimal 降级 0"""
        assert compute_service_fee_multi(Decimal("40"), "percent", "abc") == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 5. 综合费用 — None/非法字符串费用项降级
# ═══════════════════════════════════════════════════════════════

class TestComputeOrderFeesBoundary:

    def test_none_fee_items_degrade_to_zero(self):
        """单项 None(上游未采集) → 该项降级 0, 整单汇总不崩"""
        result = compute_order_fees(
            energy_fee=None,
            service_fee=None,
            parking_fee=None,
            occupancy_fee=None,
            reservation_fee=None,
        )
        assert result["total_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")

    def test_invalid_string_fee_degrades(self):
        """非法字符串费用项 → _safe_decimal 降级 0"""
        result = compute_order_fees(
            energy_fee="abc",
            service_fee="20",
            parking_fee=None,
            occupancy_fee=None,
            reservation_fee=None,
        )
        assert result["total_amount"] == Decimal("20.00")

    def test_discounts_all_none(self):
        """优惠三项 None → 均 0, paid = total"""
        result = compute_order_fees(
            energy_fee=Decimal("100"),
            service_fee=Decimal("0"),
            parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"),
            reservation_fee=Decimal("0"),
            discount_amount=None,
            coupon_amount=None,
            points_amount=None,
        )
        assert result["discount_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("100.00")

    def test_mixed_none_and_valid(self):
        """混合 None 与有效值: None 降级, 有效值正常累加"""
        result = compute_order_fees(
            energy_fee=Decimal("40"),
            service_fee=None,        # 降级 0
            parking_fee=Decimal("10"),
            occupancy_fee=None,      # 降级 0
            reservation_fee=Decimal("5"),
        )
        assert result["total_amount"] == Decimal("55.00")  # 40+0+10+0+5


# ═══════════════════════════════════════════════════════════════
# 6. 停车费 — None/非法 sanitize(主干已有夜间/封顶, 这里补 None)
# ═══════════════════════════════════════════════════════════════

class TestParkingFeeBoundary:

    def test_none_rule_returns_zero(self):
        """parking_rule=None → 降级 0 费"""
        result = compute_parking_fee_full(120, None)
        assert result["total"] == Decimal("0.00")
        assert result["capped"] is False

    def test_non_dict_rule_returns_zero(self):
        result = compute_parking_fee_full(120, "invalid")
        assert result["total"] == Decimal("0.00")

    def test_none_hourly_rate_degrades_to_zero(self):
        """hourly_rate=None → 降级 0, 不崩"""
        rule = {"free_minutes": 0, "hourly_rate": None, "daily_cap": None}
        result = compute_parking_fee_full(120, rule)
        assert result["total"] == Decimal("0.00")

    def test_invalid_daily_cap_ignored(self):
        """daily_cap 非法字符串 → cap<=0 视为无封顶, 不压制"""
        rule = {
            "free_minutes": 0,
            "hourly_rate": Decimal("10.00"),
            "daily_cap": "abc",
        }
        result = compute_parking_fee_full(120, rule)
        # 2h × 10 = 20.00, 不被压
        assert result["total"] == Decimal("20.00")
        assert result["capped"] is False

    def test_empty_rule_dict_no_crash(self):
        """空规则 dict → hourly_rate=None 降级 0"""
        result = compute_parking_fee_full(120, {})
        assert result["total"] == Decimal("0.00")

    def test_negative_parking_minutes_clamped(self):
        """负停车时长 → billable=0"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.00"), "daily_cap": None}
        result = compute_parking_fee_full(-60, rule)
        assert result["total"] == Decimal("0.00")

    def test_negative_charging_exempt_raises(self):
        """charging_exempt_minutes 为负 → billable 被放大 → 用户多收费, 必须拒绝"""
        from app.services.billing_engine import BillingError
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.00"), "daily_cap": None}
        with pytest.raises(BillingError):
            compute_parking_fee_full(120, rule, charging_exempt_minutes=-30)

    def test_dirty_night_rate_degrades(self):
        """night_rate 非法字符串 → 走 _safe_decimal 降级 0, 不崩 InvalidOperation"""
        rule = {
            "free_minutes": 0,
            "hourly_rate": Decimal("10.00"),
            "daily_cap": None,
            "enable_night_rate": True,
            "night_rate": "abc",
            "night_start": time(22, 0),
            "night_end": time(6, 0),
        }
        start = datetime(2026, 1, 1, 23, 0)  # 全落夜间窗
        result = compute_parking_fee_full(120, rule, start_time=start)
        assert result["night_fee"] == Decimal("0.00")
        assert result["day_fee"] == Decimal("0.00")
