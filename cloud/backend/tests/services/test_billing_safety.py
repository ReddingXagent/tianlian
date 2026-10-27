"""
billing.py 安全加固测试 — 计费核心不得因异常导致用户账单错误。

覆盖三类「脏输入」(任务卡 b6adf748):
1. None 入参        — 不得 TypeError 崩溃, 返回 Decimal("0.00")
2. 非法类型(str/dict/list) — 不得崩溃, 返回 Decimal("0.00")
3. 超大数(>=10^18)   — 视为非法, 返回 0, 不崩不耗尽内存

设计原则(与 test_billing.py 既有契约共存):
- 独立费用函数: 负数仍 raise ValueError (契约, test_billing.py 多处 pytest.raises 依赖);
  None / 非法类型 / 超大数 / 运算意外 → 返回 0 (安全默认, 不多收费)。
- calculate_total_order: 任意单项异常 (含子函数 raise ValueError) → 该项归 0,
  订单不崩, 始终返回完整 dict (宁可少收一项, 不可整个订单崩溃致用户无法结账)。
"""
import pytest
from decimal import Decimal

from app.services import billing as billing_module
from app.services.billing import (
    calculate_electricity_fee,
    calculate_service_fee,
    calculate_parking_fee,
    calculate_idle_penalty,
    calculate_reservation_fee,
    calculate_total_order,
)
from app.services.billing import _is_sane_decimal, _quantize_or_zero


# ═══════════════════════════════════════════════════════════════
# 1. None 入参 — 安全默认 0, 不崩
# ═══════════════════════════════════════════════════════════════

class TestNoneInputsSafe:
    def test_electricity_none_kwh(self):
        assert calculate_electricity_fee(None, Decimal("0.8")) == Decimal("0.00")

    def test_electricity_none_price(self):
        assert calculate_electricity_fee(Decimal("50"), None) == Decimal("0.00")

    def test_electricity_both_none(self):
        assert calculate_electricity_fee(None, None) == Decimal("0.00")

    def test_service_none(self):
        assert calculate_service_fee(None, None) == Decimal("0.00")

    def test_parking_none(self):
        assert calculate_parking_fee(None, None) == Decimal("0.00")

    def test_idle_none_minutes(self):
        assert calculate_idle_penalty(None, Decimal("0.5")) == Decimal("0.00")

    def test_idle_none_rate(self):
        assert calculate_idle_penalty(30, None) == Decimal("0.00")

    def test_reservation_none_duration(self):
        assert calculate_reservation_fee(None, Decimal("1")) == Decimal("0.00")

    def test_reservation_none_rate(self):
        assert calculate_reservation_fee(30, None) == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 2. 非法类型 — 安全默认 0, 不崩
# ═══════════════════════════════════════════════════════════════

class TestInvalidTypeSafe:
    def test_electricity_invalid_str(self):
        assert calculate_electricity_fee("abc", Decimal("0.8")) == Decimal("0.00")

    def test_electricity_dict_input(self):
        assert calculate_electricity_fee({"x": 1}, Decimal("0.8")) == Decimal("0.00")

    def test_electricity_list_input(self):
        assert calculate_electricity_fee([1, 2], Decimal("0.8")) == Decimal("0.00")

    def test_parking_invalid_str(self):
        assert calculate_parking_fee("not-a-number", Decimal("5")) == Decimal("0.00")

    def test_service_object_input(self):
        assert calculate_service_fee(object(), Decimal("0.5")) == Decimal("0.00")

    def test_reservation_invalid_str_rate(self):
        assert calculate_reservation_fee(30, "free") == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 3. 超大数 — 视为非法, 返回 0, 不崩
# ═══════════════════════════════════════════════════════════════

class TestHugeNumberSafe:
    def test_electricity_huge_kwh(self):
        # 1e20 远超任何合理充电量(kWh), 归 0
        assert calculate_electricity_fee(Decimal("1e20"), Decimal("0.8")) == Decimal("0.00")

    def test_electricity_huge_price(self):
        assert calculate_electricity_fee(Decimal("50"), Decimal("1e20")) == Decimal("0.00")

    def test_electricity_huge_negative(self):
        # 负超大数同样挡(adjusted 取绝对值数量级)
        assert calculate_electricity_fee(Decimal("-1e20"), Decimal("0.8")) == Decimal("0.00")

    def test_total_huge_not_crash(self):
        """超大数入 total_order 不崩, 返回完整 dict, 各项安全归 0。"""
        result = calculate_total_order(
            charged_kwh=Decimal("1e30"),
            electricity_price=Decimal("1e30"),
            service_fee_rate=Decimal("0"),
        )
        assert result["electricity_fee"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 4. 负数契约保留 — 独立函数仍 raise ValueError (不破坏 test_billing.py)
# ═══════════════════════════════════════════════════════════════

class TestNegativeContractPreserved:
    def test_electricity_negative_kwh_raises(self):
        with pytest.raises(ValueError, match="充电电量不能为负数"):
            calculate_electricity_fee(Decimal("-10"), Decimal("0.8"))

    def test_electricity_negative_price_raises(self):
        with pytest.raises(ValueError, match="电价不能为负数"):
            calculate_electricity_fee(Decimal("50"), Decimal("-0.1"))

    def test_service_negative_kwh_raises(self):
        with pytest.raises(ValueError):
            calculate_service_fee(Decimal("-10"), Decimal("0.5"))

    def test_parking_negative_duration_raises(self):
        with pytest.raises(ValueError):
            calculate_parking_fee(Decimal("-1"), Decimal("5"))


# ═══════════════════════════════════════════════════════════════
# 5. calculate_total_order 韧性 — 子项异常归 0, 订单不崩
# ═══════════════════════════════════════════════════════════════

class TestTotalOrderResilience:
    def test_none_kwh_in_total_safe(self):
        """None 电量 → 电费/服务费归 0, 不崩。"""
        result = calculate_total_order(
            charged_kwh=None,
            electricity_price=Decimal("0.8"),
            service_fee_rate=Decimal("0.5"),
        )
        assert result["electricity_fee"] == Decimal("0.00")
        assert result["service_fee"] == Decimal("0.00")
        assert result["total_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")

    def test_negative_kwh_in_total_does_not_crash(self):
        """负数电量: 子函数 raise ValueError, total_order 捕获该项归 0, 订单不崩。"""
        result = calculate_total_order(
            charged_kwh=Decimal("-10"),
            electricity_price=Decimal("0.8"),
            service_fee_rate=Decimal("0.5"),
        )
        assert result["electricity_fee"] == Decimal("0.00")
        assert result["service_fee"] == Decimal("0.00")
        assert result["total_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")

    def test_none_discount_in_total_safe(self):
        """None 折扣 → 视为 0, 正常计费。"""
        result = calculate_total_order(
            charged_kwh=Decimal("10"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0"),
            discount_amount=None,
        )
        assert result["discount_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("10.00")

    def test_bad_input_returns_complete_dict(self):
        """脏输入仍返回完整 8 键 dict, 结构契约不变。"""
        result = calculate_total_order(
            charged_kwh=None,
            electricity_price=None,
            service_fee_rate=None,
        )
        expected_keys = {
            "electricity_fee", "service_fee", "parking_fee", "idle_penalty",
            "reservation_fee", "total_amount", "discount_amount", "paid_amount",
        }
        assert set(result.keys()) == expected_keys
        # 所有值均为 Decimal
        for v in result.values():
            assert isinstance(v, Decimal)

    def test_invalid_type_discount_safe(self):
        result = calculate_total_order(
            charged_kwh=Decimal("10"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0"),
            discount_amount="not-a-number",
        )
        assert result["discount_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 6. 增强 — int/float 入参不再 TypeError
# ═══════════════════════════════════════════════════════════════

class TestNumericCoercion:
    def test_int_input_accepted(self):
        """原实现 50 < Decimal('0') 会 TypeError, 加固后接受 int。"""
        assert calculate_electricity_fee(50, Decimal("0.8")) == Decimal("40.00")

    def test_float_input_accepted(self):
        assert calculate_electricity_fee(Decimal("50"), 0.8) == Decimal("40.00")

    def test_numeric_string_accepted(self):
        assert calculate_electricity_fee("50", "0.8") == Decimal("40.00")

    def test_bool_treated_as_zero(self):
        """bool 无业务意义, 归 0(而非 True=1 致 1*kwh 误计)。"""
        assert calculate_electricity_fee(True, Decimal("0.8")) == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 7. 私有 helper 与各 calc 函数 catch-all 兜底分支
# ═══════════════════════════════════════════════════════════════

class TestInternalHelpers:
    def test_is_sane_decimal_rejects_non_decimal(self):
        """非 Decimal 类型 → False (防御性, 内部调用方恒传 Decimal)。"""
        assert _is_sane_decimal("100") is False
        assert _is_sane_decimal(100) is False
        assert _is_sane_decimal(None) is False

    def test_is_sane_decimal_rejects_non_finite(self):
        """NaN / Infinity → is_finite() False → False。"""
        assert _is_sane_decimal(Decimal("NaN")) is False
        assert _is_sane_decimal(Decimal("Infinity")) is False
        assert _is_sane_decimal(Decimal("-Infinity")) is False

    def test_is_sane_decimal_accepts_finite_normal(self):
        assert _is_sane_decimal(Decimal("100")) is True
        assert _is_sane_decimal(Decimal("0")) is True

    def test_quantize_or_zero_handles_precision_overflow(self):
        """quantize 精度溢出 (结果有效位数超 context 精度) 抛 InvalidOperation → 兜底 0。

        白盒直测防御分支: 正常 sane 流程 (adjusted<18) 永不溢出,
        此处用 1E+30 强制触发 quantize 精度溢出。"""
        assert _quantize_or_zero(Decimal("1E+30")) == Decimal("0")


class TestCalcFuncCatchAll:
    """5 个独立费用函数的 (InvalidOperation, ArithmeticError, TypeError) catch-all:
    强制 _to_decimal 抛 TypeError → 兜底返回 Decimal("0.00"), 不崩。"""

    @pytest.mark.parametrize("func,args", [
        (calculate_electricity_fee, (Decimal("10"), Decimal("1"))),
        (calculate_service_fee, (Decimal("10"), Decimal("0.5"))),
        (calculate_parking_fee, (Decimal("1"), Decimal("5"))),
        (calculate_idle_penalty, (10, Decimal("0.5"))),
        (calculate_reservation_fee, (10, Decimal("1"))),
    ])
    def test_catches_unexpected_typeerror(self, monkeypatch, func, args):
        def _boom(_v):
            raise TypeError("boom")
        monkeypatch.setattr(billing_module, "_to_decimal", _boom)
        assert func(*args) == Decimal("0.00")


class TestHugeNumberPerFunction:
    """各独立函数直接收超大数 → sanity 守卫归 0 (补 total_order 之外的直测)。"""

    def test_parking_huge_returns_zero(self):
        assert calculate_parking_fee(Decimal("1e20"), Decimal("5")) == Decimal("0.00")

    def test_idle_huge_returns_zero(self):
        assert calculate_idle_penalty(Decimal("1e20"), Decimal("0.5")) == Decimal("0.00")

    def test_reservation_huge_returns_zero(self):
        assert calculate_reservation_fee(Decimal("1e20"), Decimal("1")) == Decimal("0.00")

    def test_total_order_huge_discount_sanitized_to_zero(self):
        """total_order: 折扣超大数 → sanity 失败归 0 (不加价不崩溃)。"""
        result = calculate_total_order(
            charged_kwh=Decimal("10"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0"),
            discount_amount=Decimal("1e20"),
        )
        assert result["discount_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 8. 负折扣契约 — calculate_total_order 对 discount<0 raise (卡2230298e 缺口1)
# ═══════════════════════════════════════════════════════════════

class TestNegativeDiscountContract:
    """负折扣财务边界: 费用明细合计必须 = paid_amount。

    旧行为(加价语义)使 paid_amount = total + |discount|, 而 total_amount / 费用明细
    不含加价 → 明细合计 ≠ paid_amount, 财务对账不平。修复: discount<0 raise,
    与独立费用函数负数契约一致(负值是非法输入, 调用方需感知, 而非静默吞掉)。
    """

    def test_negative_discount_raises(self):
        with pytest.raises(ValueError, match="折扣不能为负"):
            calculate_total_order(
                charged_kwh=Decimal("10"),
                electricity_price=Decimal("1"),
                service_fee_rate=Decimal("0"),
                discount_amount=Decimal("-5"),
            )

    def test_zero_discount_ok(self):
        """discount=0 不触发 raise, 正常计费 (边界值)。"""
        result = calculate_total_order(
            charged_kwh=Decimal("10"),
            electricity_price=Decimal("1"),
            service_fee_rate=Decimal("0"),
            discount_amount=Decimal("0"),
        )
        assert result["discount_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("10.00")
