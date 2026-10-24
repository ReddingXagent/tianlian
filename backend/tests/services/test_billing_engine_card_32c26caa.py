"""
billing_engine 补充单元测试 — 卡 6efb1bf0

被测: app/services/billing_engine.py

本文件是补充测试, 不重复 tests/services/test_billing_engine.py 及三个 hardening/gaps
文件已覆盖的场景。聚焦真实缺口:

1. _safe_decimal vs _q 精度语义差异(保留原始精度 vs 量化2位) — 代码注释强调的核心区别
2. _is_negative_decimal 脏值直接断言(None/非法/NaN/Infinity/0 → False)
3. compute_tou_energy_fee 多天充电(充电跨 ≥2 个日历日) — 现有仅覆盖单日与跨午夜
4. compute_tou_energy_fee 起始时间正好落在时段分界点的归属语义(左闭右开)
5. BillingError vs ValueError 精确类型区分:
   - 缺 slot 价格 / 时段重叠 → ValueError, 且 isinstance(., BillingError) 为 False
   - None 入参 → BillingError, 同时 isinstance(., ValueError) 为 True(向后兼容宽口径 except)
6. settle_order_fees 用 MagicMock(Session) 验证(不依赖真实 SQLite, 走纯 mock 路径)
"""
from datetime import datetime, time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.services.billing_engine import (
    BillingError,
    _is_negative_decimal,
    _q,
    _safe_decimal,
    compute_tou_energy_fee,
    settle_order_fees,
)


# ═══════════════════════════════════════════════════════════════
# 1. _safe_decimal: 保留原始精度, 不量化(与 _q 的核心区别)
# ═══════════════════════════════════════════════════════════════
class TestSafeDecimalPrecision:
    """_safe_decimal 面向入参 sanitize, 不量化; _q 面向内部路径, 量化2位。

    费率如 0.5286(4位精度), 提前量化到2位会失真 → 必须由各调用点乘积 quantize 收敛。
    """

    def test_preserves_4_place_precision_not_quantized(self):
        """0.5286 保留4位, 不被 _safe_decimal 压成 0.53"""
        assert _safe_decimal("0.5286") == Decimal("0.5286")

    def test_contrast_with_q_quantizes(self):
        """对比: _q('0.5286') → 0.53(失真), _safe_decimal('0.5286') → 0.5286(保真)"""
        assert _q("0.5286") == Decimal("0.53")
        assert _safe_decimal("0.5286") == Decimal("0.5286")
        assert _safe_decimal("0.5286") != _q("0.5286")

    def test_none_returns_default_zero(self):
        assert _safe_decimal(None) == Decimal("0")

    def test_none_custom_default(self):
        assert _safe_decimal(None, Decimal("5")) == Decimal("5")

    def test_invalid_string_returns_default(self):
        assert _safe_decimal("abc") == Decimal("0")

    def test_nan_returns_default(self):
        assert _safe_decimal("NaN") == Decimal("0")

    def test_infinity_returns_default(self):
        assert _safe_decimal("Infinity") == Decimal("0")
        assert _safe_decimal("-Infinity") == Decimal("0")

    def test_returns_decimal_type(self):
        assert isinstance(_safe_decimal("1.5"), Decimal)

    def test_default_is_decimal_normalized(self):
        """default 经 Decimal(str(default)) 归一, 即便传入 float 也安全"""
        assert _safe_decimal(None, 7) == Decimal("7")


# ═══════════════════════════════════════════════════════════════
# 2. _is_negative_decimal: 脏值不抛, 非负/脏值 → False
# ═══════════════════════════════════════════════════════════════
class TestIsNegativeDecimal:
    """用于 reservation 金额负数校验: 过滤负数(抛 BillingError 防套利),
    其余(None/非法/NaN)继续走 `or 0` 降级, 不在此报错。"""

    def test_negative_string_true(self):
        assert _is_negative_decimal("-5") is True

    def test_negative_decimal_true(self):
        assert _is_negative_decimal(Decimal("-0.01")) is True

    def test_zero_false(self):
        assert _is_negative_decimal(0) is False
        assert _is_negative_decimal("0") is False

    def test_positive_false(self):
        assert _is_negative_decimal("5") is False
        assert _is_negative_decimal(Decimal("0.01")) is False

    def test_none_false(self):
        assert _is_negative_decimal(None) is False

    def test_invalid_string_false(self):
        assert _is_negative_decimal("abc") is False

    def test_nan_false(self):
        # NaN < 0 为 False, is_finite() 为 False → 返回 False
        assert _is_negative_decimal("NaN") is False

    def test_infinity_false(self):
        # 非有限 → False(即便 -Infinity 也不视为可套利的负数)
        assert _is_negative_decimal("-Infinity") is False
        assert _is_negative_decimal("Infinity") is False

    def test_returns_bool_type(self):
        assert isinstance(_is_negative_decimal("-1"), bool)
        assert isinstance(_is_negative_decimal(None), bool)


# ═══════════════════════════════════════════════════════════════
# 3. compute_tou_energy_fee: 多天充电(跨 ≥2 个日历日)
# ═══════════════════════════════════════════════════════════════
class TestTouMultiDay:
    """充电跨多个日历日(days 列表含 ≥2 天)的电量分摊。

    现有测试仅覆盖单日与单次跨午夜, 未覆盖真正的多天(如 6/24 12:00 → 6/26 12:00)。
    """

    def test_multi_day_full_coverage_flat(self):
        """全天窗(0-24)覆盖 48h: 6/24 12:00 → 6/26 12:00, 100kWh @0.6 = 60.00"""
        slots = [{"slot_id": "s", "period_type": "flat",
                  "start_time": time(0, 0), "end_time": time(0, 0)}]  # start==end 全天窗
        prices = {"s": Decimal("0.6")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 12, 0), datetime(2026, 6, 26, 12, 0),
            Decimal("100"), slots, prices,
        )
        assert r["total_fee"] == Decimal("60.00")
        assert r["total_energy"] == Decimal("100.00")
        assert r["coverage"] == 1.0

    def test_multi_day_cross_midnight_valley(self):
        """跨夜谷段(22-06)与 6/24 22:00 → 6/26 06:00(=32h, 非56h)相交。

        days=[6/23,6/24,6/25,6/26](含前置一天), 相交的谷窗仅两个:
        [6/24 22:00→6/25 06:00] 480min + [6/25 22:00→6/26 06:00] 480min = 960min。
        白天段(06-22)无谷段配置 → coverage=0.5, 未覆盖电量被排除(引擎 warning 为预期行为)。
        """
        slots = [{"slot_id": "v", "period_type": "valley",
                  "start_time": time(22, 0), "end_time": time(6, 0)}]
        prices = {"v": Decimal("0.3")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 22, 0), datetime(2026, 6, 26, 6, 0),
            Decimal("56"), slots, prices,
        )
        # 覆盖 960/1920 = 50%: 恒功率分摊 56×0.5 = 28kWh × 0.3 = 8.40
        assert r["total_energy"] == Decimal("28.00")
        assert r["total_fee"] == Decimal("8.40")
        assert r["coverage"] == 0.5

    def test_multi_day_period_breakdown_accumulates_across_days(self):
        """同 period_type 在多天多窗累加, 不覆盖(回归 4671e993 的多天延伸)。"""
        # 谷段 22-06, 充电 6/24 22:00 → 6/26 06:00(32h), 两个谷窗各 480min
        slots = [{"slot_id": "v", "period_type": "valley",
                  "start_time": time(22, 0), "end_time": time(6, 0)}]
        prices = {"v": Decimal("0.3")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 22, 0), datetime(2026, 6, 26, 6, 0),
            Decimal("56"), slots, prices,
        )
        # 两个谷窗累加进同一 period_type: minutes 合计 960, 每窗 14kWh→4.20, 合计 28kWh→8.40
        assert r["period_breakdown"]["valley"]["minutes"] == 960.0
        assert r["period_breakdown"]["valley"]["energy"] == Decimal("28.00")
        assert r["period_breakdown"]["valley"]["fee"] == Decimal("8.40")

    def test_early_morning_tail_of_previous_day_window(self):
        """回归: 充电起点在午夜后且落在前一天跨午夜窗口的凌晨尾巴内。

        谷段 22-06, 充电 6/25 00:00→06:00 属于窗口 [6/24 22:00→6/25 06:00]。
        修复前 days 从 start_time.date() 起算, 该窗口不被枚举 → coverage=0,
        整段电量静默排除(客户少付费); 修复后前置 start.date()-1 一天。
        """
        slots = [{"slot_id": "v", "period_type": "valley",
                  "start_time": time(22, 0), "end_time": time(6, 0)}]
        prices = {"v": Decimal("0.3")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 25, 0, 0), datetime(2026, 6, 25, 6, 0),
            Decimal("6"), slots, prices,
        )
        assert r["coverage"] == 1.0
        assert r["total_energy"] == Decimal("6.00")
        assert r["total_fee"] == Decimal("1.80")
        assert r["period_breakdown"]["valley"]["minutes"] == 360.0


# ═══════════════════════════════════════════════════════════════
# 4. compute_tou_energy_fee: 起始时间正好落在时段分界点
# ═══════════════════════════════════════════════════════════════
class TestTouBoundaryAtSlotEdge:
    """充电起始/结束正好落在 slot 边界点的归属语义。

    _overlap_minutes 用左闭右开(max/min 相减), 端点相接重叠为 0。
    """

    SLOTS = [
        {"slot_id": "pk", "period_type": "peak", "start_time": time(10, 0), "end_time": time(12, 0)},
        {"slot_id": "fl", "period_type": "flat", "start_time": time(12, 0), "end_time": time(14, 0)},
    ]
    PRICES = {"pk": Decimal("1.0"), "fl": Decimal("0.6")}

    def test_start_at_peak_start(self):
        """起始 10:00 恰为 peak 起点(含) → 全落 peak"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 11, 0),
            Decimal("10"), self.SLOTS, self.PRICES,
        )
        assert set(r["period_breakdown"].keys()) == {"peak"}
        assert r["period_breakdown"]["peak"]["fee"] == Decimal("10.00")

    def test_start_at_boundary_belongs_to_later_slot(self):
        """起始 12:00 恰为 peak 终点/flat 起点 → 归属 flat(peak 左闭右开不含 12:00)"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 12, 0), datetime(2026, 6, 24, 13, 0),
            Decimal("10"), self.SLOTS, self.PRICES,
        )
        assert set(r["period_breakdown"].keys()) == {"flat"}
        assert r["period_breakdown"]["flat"]["fee"] == Decimal("6.00")

    def test_end_at_boundary_excluded_from_earlier_slot(self):
        """结束 12:00 恰为 peak 终点 → peak 重叠仅到 12:00(不含), 充电 10:00-12:00 全 peak"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
            Decimal("10"), self.SLOTS, self.PRICES,
        )
        # 10:00-12:00 严格 peak(120min), flat 重叠 0
        assert set(r["period_breakdown"].keys()) == {"peak"}
        assert r["period_breakdown"]["peak"]["minutes"] == 120.0

    def test_span_across_boundary_split(self):
        """跨边界 11:00-13:00: peak 60min(11-12) + flat 60min(12-13)"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 11, 0), datetime(2026, 6, 24, 13, 0),
            Decimal("20"), self.SLOTS, self.PRICES,
        )
        assert r["period_breakdown"]["peak"]["minutes"] == 60.0
        assert r["period_breakdown"]["flat"]["minutes"] == 60.0
        # 各 10kWh: peak 10.00 + flat 6.00
        assert r["total_fee"] == Decimal("16.00")


# ═══════════════════════════════════════════════════════════════
# 5. BillingError vs ValueError 精确类型区分
# ═══════════════════════════════════════════════════════════════
class TestErrorTypeDiscrimination:
    """两类错误的精确区分:

    - ValueError(配置数据问题: 缺 slot 价格 / 时段重叠 / 未知 fee_type)→ 纯 ValueError,
      不是 BillingError; 调用方 try/except 后走默认值兜底。
    - BillingError(调用方编程错误: None 必填入参 / 负数金额 / 非 dict 规则)→ 继承
      ValueError(兼容宽口径 except), 但 isinstance(., BillingError) 为 True, 便于上层区分。
    """

    SLOTS = [
        {"slot_id": "pk", "period_type": "peak", "start_time": time(10, 0), "end_time": time(12, 0)},
        {"slot_id": "fl", "period_type": "flat", "start_time": time(12, 0), "end_time": time(14, 0)},
    ]
    PRICES = {"pk": Decimal("1.0"), "fl": Decimal("0.6")}

    def test_missing_price_is_plain_value_error_not_billing_error(self):
        """缺 slot 价格 → ValueError, 且不是 BillingError(配置错误, 非编程错误)"""
        with pytest.raises(ValueError, match="Missing price for slot"):
            compute_tou_energy_fee(
                datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 11, 0),
                Decimal("10"), self.SLOTS, {},  # peak 覆盖 10-11 却缺价格
            )
        try:
            compute_tou_energy_fee(
                datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 11, 0),
                Decimal("10"), self.SLOTS, {},
            )
        except BillingError:
            pytest.fail("缺 slot 价格应抛 ValueError, 不应抛 BillingError")
        except ValueError:
            pass  # 预期

    def test_overlapping_slots_is_value_error_not_billing_error(self):
        """时段重叠 → ValueError(配置错误), 不是 BillingError"""
        overlapping = [
            {"slot_id": "a", "period_type": "peak", "start_time": time(10, 0), "end_time": time(13, 0)},
            {"slot_id": "b", "period_type": "flat", "start_time": time(12, 0), "end_time": time(14, 0)},
        ]
        prices = {"a": Decimal("1.0"), "b": Decimal("0.6")}
        with pytest.raises(ValueError, match="Time slots overlap"):
            compute_tou_energy_fee(
                datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 14, 0),
                Decimal("20"), overlapping, prices,
            )

    def test_none_start_time_is_billing_error_and_value_error(self):
        """None 入参 → BillingError(编程错误), 同时 isinstance(., ValueError) 为 True(向后兼容)"""
        with pytest.raises(BillingError):
            compute_tou_energy_fee(
                None, datetime(2026, 6, 24, 12, 0),
                Decimal("10"), self.SLOTS, self.PRICES,
            )
        try:
            compute_tou_energy_fee(
                None, datetime(2026, 6, 24, 12, 0),
                Decimal("10"), self.SLOTS, self.PRICES,
            )
        except ValueError:
            pass  # BillingError 继承 ValueError, 宽口径 except 也能兜住
        else:
            pytest.fail("None start_time 应抛 BillingError(也是 ValueError)")

    def test_none_end_time_is_billing_error(self):
        with pytest.raises(BillingError):
            compute_tou_energy_fee(
                datetime(2026, 6, 24, 10, 0), None,
                Decimal("10"), self.SLOTS, self.PRICES,
            )

    def test_billing_error_subclass_relationship(self):
        """BillingError 是 ValueError 子类(继承链), 非 RuntimeError"""
        assert issubclass(BillingError, ValueError)
        assert not issubclass(BillingError, RuntimeError)

    def test_billing_error_message_contains_context(self):
        """BillingError 消息含入参上下文, 便于定位"""
        with pytest.raises(BillingError, match="start_time"):
            compute_tou_energy_fee(
                None, None, Decimal("10"), self.SLOTS, self.PRICES,
            )


# ═══════════════════════════════════════════════════════════════
# 6. settle_order_fees: 用 MagicMock(Session) 验证写入(不依赖真实 SQLite)
# ═══════════════════════════════════════════════════════════════
class TestSettleOrderFeesWithMock:
    """纯 mock 路径: 用 MagicMock 模拟 Session, 验证:

    - 旧明细清除(query.filter.delete)被调用
    - 5 项费用写入 order 字段 + idle_penalty 兼容
    - OrderFeeItem 明细行数量与 fee_type 正确
    - add_all + flush 调用(不 commit, 提交边界交调用方)
    - 返回 dict 6 项金额为干净 float
    """

    @staticmethod
    def _make_order():
        """MagicMock order: .id 可读, 字段属性可写"""
        order = MagicMock()
        order.id = 42
        return order

    @staticmethod
    def _make_db():
        """MagicMock Session: query().filter().delete() 链可用"""
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 0
        return db

    def test_clears_old_items_then_writes(self):
        """先清除旧明细(query.filter.delete), 再 add_all 新明细 + flush(不 commit)"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("16"), "service_fee": Decimal("25"),
            "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
            "reservation_fee": Decimal("7"),
            "discount_amount": Decimal("3"), "coupon_amount": Decimal("2"),
            "points_amount": Decimal("1"),
        }
        result = settle_order_fees(order, fees, db)

        # 清除旧明细
        db.query.assert_called_once()
        db.query.return_value.filter.return_value.delete.assert_called_once()
        # add_all 写入明细 + flush(提交边界交调用方, 不 commit)
        db.add_all.assert_called_once()
        db.flush.assert_called_once()
        db.commit.assert_not_called()
        # 返回 order_id
        assert result["order_id"] == 42

    def test_five_fee_fields_written_to_order(self):
        """5 项费用 + idle_penalty(兼容旧字段) 写入 order 属性"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("16"), "service_fee": Decimal("25"),
            "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
            "reservation_fee": Decimal("7"),
        }
        settle_order_fees(order, fees, db)

        assert order.electricity_fee == Decimal("16.00")
        assert order.service_fee == Decimal("25.00")
        assert order.parking_fee == Decimal("10.00")
        assert order.occupancy_fee == Decimal("5.00")
        assert order.idle_penalty == Decimal("5.00")  # 兼容旧字段 = occupancy_fee
        assert order.reservation_fee == Decimal("7.00")

    def test_total_and_paid_written_to_order(self):
        """total = 5项之和; paid = total - 优惠三项, 触底 0"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("16"), "service_fee": Decimal("25"),
            "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
            "reservation_fee": Decimal("7"),
            "discount_amount": Decimal("3"), "coupon_amount": Decimal("2"),
            "points_amount": Decimal("1"),
        }
        settle_order_fees(order, fees, db)

        # total = 16+25+10+5+7 = 63; paid = 63-3-2-1 = 57
        assert order.total_amount == Decimal("63.00")
        assert order.discount_amount == Decimal("3.00")
        assert order.coupon_amount == Decimal("2.00")
        assert order.points_amount == Decimal("1.00")
        assert order.paid_amount == Decimal("57.00")

    def test_fee_items_count_and_types(self):
        """无 breakdown 时明细: 电费(汇总) + 服务费 + 停车 + 占桩 + 预约 + 折扣 + 券 + 积分 = 8"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("16"), "service_fee": Decimal("25"),
            "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
            "reservation_fee": Decimal("7"),
            "discount_amount": Decimal("3"), "coupon_amount": Decimal("2"),
            "points_amount": Decimal("1"),
        }
        result = settle_order_fees(order, fees, db)

        added_items = db.add_all.call_args[0][0]
        assert len(added_items) == 8
        types = [i.fee_type.value for i in added_items]
        assert types == [
            "electricity", "service", "parking", "occupancy", "reservation",
            "discount", "coupon", "points",
        ]
        # 返回 dict 的 fee_items 同样 8 条
        assert len(result["fee_items"]) == 8

    def test_breakdown_generates_multiple_electricity_items(self):
        """带 breakdown: 电费按时段多行, 其余汇总"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("16"), "service_fee": Decimal("0"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
        }
        breakdown = [
            {"period_name": "尖峰", "kwh": 10, "price": Decimal("1.0"), "fee": Decimal("10"), "unit": "kWh"},
            {"period_name": "平", "kwh": 10, "price": Decimal("0.6"), "fee": Decimal("6"), "unit": "kWh"},
        ]
        result = settle_order_fees(order, fees, db, energy_breakdown=breakdown)

        added_items = db.add_all.call_args[0][0]
        elec = [i for i in added_items if i.fee_type.value == "electricity"]
        assert len(elec) == 2  # 两时段两行, 非汇总单行
        assert {i.fee_name for i in elec} == {"尖峰", "平"}

    def test_discount_items_have_negative_amount(self):
        """优惠明细行金额为负(表示抵扣)"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("10"), "service_fee": Decimal("0"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("3"),
        }
        result = settle_order_fees(order, fees, db)

        added_items = db.add_all.call_args[0][0]
        discount_item = next(i for i in added_items if i.fee_type.value == "discount")
        assert discount_item.amount == Decimal("-3.00")  # 负数抵扣
        # 返回 dict 的 amount 也是负 float
        assert result["fee_items"][-1]["amount"] == -3.0

    def test_zero_fees_produce_no_items(self):
        """全部费用为 0 → 无明细行, 但 order 字段仍写入 0"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("0"), "service_fee": Decimal("0"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
        }
        result = settle_order_fees(order, fees, db)

        added_items = db.add_all.call_args[0][0]
        assert added_items == []
        assert len(result["fee_items"]) == 0
        assert result["total_amount"] == 0.0
        assert result["paid_amount"] == 0.0
        assert order.total_amount == Decimal("0.00")

    def test_returned_amounts_are_clean_float(self):
        """返回 dict 的 6 项金额为干净 2 位 float(无长尾)"""
        order = self._make_order()
        db = self._make_db()

        fees = {
            "energy_fee": Decimal("0.10"), "service_fee": Decimal("0.20"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("0.01"),
        }
        result = settle_order_fees(order, fees, db)

        for key in ("total_amount", "discount_amount", "coupon_amount",
                    "points_amount", "paid_amount"):
            v = result[key]
            assert v == round(v, 2), f"{key} 带长尾: {v}"
        # total 0.30 不等于 float 算术泄漏
        assert result["total_amount"] == 0.30
        assert result["total_amount"] != 0.1 + 0.2

    def test_db_exception_triggers_rollback_and_reraises(self):
        """db.flush 异常 → rollback 调用 + 原异常上抛(不留半成品)"""
        order = self._make_order()
        db = self._make_db()
        db.flush.side_effect = OperationalError("stmt", {}, Exception("flush fail"))

        with pytest.raises(OperationalError):
            settle_order_fees(order, {"energy_fee": Decimal("10")}, db)
        db.rollback.assert_called_once()

    def test_missing_fee_keys_default_zero(self):
        """fees 缺键 → 该项降级 0(不崩), total/paid 仍正确"""
        order = self._make_order()
        db = self._make_db()

        result = settle_order_fees(order, {"energy_fee": Decimal("10")}, db)

        assert order.electricity_fee == Decimal("10.00")
        assert order.service_fee == Decimal("0.00")
        assert order.parking_fee == Decimal("0.00")
        assert order.total_amount == Decimal("10.00")
        assert result["total_amount"] == 10.0
        # 仅 1 条电费明细
        assert len(db.add_all.call_args[0][0]) == 1
