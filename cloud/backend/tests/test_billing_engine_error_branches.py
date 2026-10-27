"""
billing_engine 错误分支行为锁测试 (卡 a6d3ddcd)

背景: 覆盖率 92%, 20 行未覆盖。本文件针对资金路径错误分支逐行锁行为:

- 122        _slot_window_on_date start==end → 全天窗口(次日同时刻)
- 165        compute_tou start/end None → BillingError(非 AttributeError)
- 215-216    缺必要字段的 slot → 跳过 + warning, 不崩
- 240-241    价格 None/非法(≤0)的 slot → 跳过 + warning, 不计费(不默认 0 计费)
- 249-252    同 period_type 多窗口累加(不覆盖) — 资金正确性关键分支
- 392        parking_minutes None → BillingError
- 486        occupancy_minutes None → BillingError
- 536        reservation_rule 非 dict/None → BillingError
- 543        预约费金额字段负数 → BillingError(防负预约费套利)
- 672-673    分时明细单条异常 → 跳过 + 不污染其余明细
- 731        settle 实收 < 0 → 钳 0(不出现负实收)

设计: 纯函数直接断言; settle 相关走 test_db fixture 真实 SQLite。
只加测试, 不改业务代码。
"""
import logging
import pytest
from decimal import Decimal
from datetime import datetime, date, time, timedelta

from app.services.billing_engine import (
    BillingError,
    compute_tou_energy_fee,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    compute_reservation_fee_full,
    settle_order_fees,
    _slot_window_on_date,
)
from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
from app.models.order_fee_item import OrderFeeItem, FeeType


# ═══════════════════════════════════════════════════════════════
# L122: _slot_window_on_date start==end → 全天窗口
# ═══════════════════════════════════════════════════════════════

class TestSlotWindowSameStartEnd:
    """start==end 视为全天窗: [d start, d+1 start], 而非零长度"""

    def test_same_start_end_returns_full_day_window(self):
        d = date(2026, 8, 18)
        s, e = _slot_window_on_date(d, time(10, 0), time(10, 0))
        assert s == datetime(2026, 8, 18, 10, 0)
        assert e == datetime(2026, 8, 19, 10, 0)  # 次日同时刻 = 24h
        assert (e - s) == timedelta(days=1)

    def test_slot_all_day_window_covers_whole_charging(self):
        """start==end 的 slot 覆盖整个充电区间 → coverage=1.0 全量计费"""
        res = compute_tou_energy_fee(
            datetime(2026, 8, 18, 8, 0), datetime(2026, 8, 18, 9, 0),
            Decimal("10"),
            [{"slot_id": 1, "period_type": "flat",
              "start_time": time(0, 0), "end_time": time(0, 0)}],
            {1: Decimal("1.00")},
        )
        assert res["total_energy"] == Decimal("10.00")
        assert res["total_fee"] == Decimal("10.00")
        assert res["coverage"] == 1.0


# ═══════════════════════════════════════════════════════════════
# L165: compute_tou start/end None → BillingError
# ═══════════════════════════════════════════════════════════════

class TestTouNoneTimes:

    def test_start_none_raises_billing_error(self):
        with pytest.raises(BillingError, match="start_time/end_time 不能为 None"):
            compute_tou_energy_fee(None, datetime(2026, 8, 18, 9, 0), Decimal("10"), [], {})

    def test_end_none_raises_billing_error(self):
        with pytest.raises(BillingError, match="start_time/end_time 不能为 None"):
            compute_tou_energy_fee(datetime(2026, 8, 18, 8, 0), None, Decimal("10"), [], {})

    def test_billing_error_is_value_error_subclass(self):
        """继承 ValueError: 兼容既有宽口径 except ValueError 兜底"""
        with pytest.raises(ValueError):
            compute_tou_energy_fee(None, None, Decimal("10"), [], {})


# ═══════════════════════════════════════════════════════════════
# L215-216: 缺必要字段的 slot 跳过
# ═══════════════════════════════════════════════════════════════

class TestMalformedSlotSkipped:

    @pytest.mark.parametrize("bad_slot", [
        {"period_type": "flat", "start_time": time(0), "end_time": time(23)},  # 缺 slot_id
        {"slot_id": 1, "start_time": time(0), "end_time": time(23)},           # 缺 period_type
        {"slot_id": 1, "period_type": "flat", "end_time": time(23)},           # 缺 start_time
        {"slot_id": 1, "period_type": "flat", "start_time": time(0)},          # 缺 end_time
        {"slot_id": None, "period_type": "flat",
         "start_time": time(0), "end_time": time(23)},                         # slot_id=None
    ])
    def test_bad_slot_skipped_good_slot_still_billed(self, bad_slot, caplog):
        """坏 slot 跳过不崩; 好 slot 正常计费(不被坏数据拖垮)"""
        good = {"slot_id": 9, "period_type": "peak",
                "start_time": time(0), "end_time": time(23)}
        with caplog.at_level(logging.WARNING, logger="app.services.billing_engine"):
            res = compute_tou_energy_fee(
                datetime(2026, 8, 18, 8, 0), datetime(2026, 8, 18, 9, 0),
                Decimal("10"), [bad_slot, good], {9: Decimal("1.00")},
            )
        assert res["total_fee"] == Decimal("10.00")
        assert list(res["energy_by_period"]) == ["peak"]
        assert any("跳过格式错误" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════
# L240-241: 价格非法(None/0/负/脏字符串)的 slot 跳过
# ═══════════════════════════════════════════════════════════════

class TestInvalidSlotPriceSkipped:

    @pytest.mark.parametrize("price", [None, Decimal("0"), Decimal("-1.00"), "not-a-number"])
    def test_invalid_price_slot_skipped_with_warning(self, price, caplog):
        """key 存在但 value 非法 → 跳过该时段电量(不按 0 计费也不崩)"""
        with caplog.at_level(logging.WARNING, logger="app.services.billing_engine"):
            res = compute_tou_energy_fee(
                datetime(2026, 8, 18, 8, 0), datetime(2026, 8, 18, 9, 0),
                Decimal("10"),
                [{"slot_id": 1, "period_type": "flat",
                  "start_time": time(0), "end_time": time(23)}],
                {1: price},
            )
        assert res["total_fee"] == Decimal("0.00")
        assert res["period_breakdown"] == {}
        # overlap 仍计入分母校验 → coverage 完整, 但电量被安全排除
        assert res["coverage"] == 1.0
        assert any("跳过价格非法" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════
# L249-252: 同 period_type 多窗口累加
# ═══════════════════════════════════════════════════════════════

class TestSamePeriodMultiWindowMerge:
    """同 period_type 双窗口: energy/fee/minutes 累加, price=加权平均(卡4671e993 行为锁)"""

    def test_two_windows_same_period_merged(self):
        # 10:00-10:30 @1.0 + 10:30-11:00 @3.0, 同 period_type=flat, 10kWh 均分 5+5
        res = compute_tou_energy_fee(
            datetime(2026, 8, 18, 10, 0), datetime(2026, 8, 18, 11, 0),
            Decimal("10"),
            [
                {"slot_id": 1, "period_type": "flat",
                 "start_time": time(10, 0), "end_time": time(10, 30)},
                {"slot_id": 2, "period_type": "flat",
                 "start_time": time(10, 30), "end_time": time(11, 0)},
            ],
            {1: Decimal("1.00"), 2: Decimal("3.00")},
        )
        assert len(res["period_breakdown"]) == 1  # 不覆盖, 只一行
        flat = res["period_breakdown"]["flat"]
        assert flat["fee"] == Decimal("5.00") + Decimal("15.00")  # 累加非覆盖
        assert flat["energy"] == Decimal("10.00")
        assert flat["minutes"] == 60.0
        assert flat["price"] == Decimal("2.000000")  # 20/10 加权平均
        assert res["total_fee"] == Decimal("20.00")
        assert res["total_energy"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# L392/486/536/543: 顶层入参编程错误 → BillingError
# ═══════════════════════════════════════════════════════════════

class TestTopLevelBillingErrors:

    def test_parking_minutes_none_raises(self):
        with pytest.raises(BillingError, match="parking_minutes 不能为 None"):
            compute_parking_fee_full(None, {"hourly_rate": Decimal("5")})

    def test_occupancy_minutes_none_raises(self):
        with pytest.raises(BillingError, match="occupancy_minutes 不能为 None"):
            compute_occupancy_fee_full(None, {"rate_per_minute": Decimal("0.1")})

    @pytest.mark.parametrize("bad_rule", [None, [], "flat", 42])
    def test_reservation_rule_not_dict_raises(self, bad_rule):
        with pytest.raises(BillingError, match="reservation_rule 必须为 dict"):
            compute_reservation_fee_full(bad_rule)

    @pytest.mark.parametrize("field", ["fee_amount", "deposit_amount", "no_show_penalty"])
    def test_reservation_negative_amount_raises(self, field):
        """负金额字段 → BillingError, 防负预约费/负罚款套利"""
        rule = {"fee_amount": Decimal("1.00"),
                "deposit_amount": Decimal("2.00"),
                "no_show_penalty": Decimal("3.00")}
        rule[field] = Decimal("-0.01")
        with pytest.raises(BillingError, match=f"{field} 不能为负数"):
            compute_reservation_fee_full(rule)


# ═══════════════════════════════════════════════════════════════
# L672-673: 分时明细单条异常跳过
# ═══════════════════════════════════════════════════════════════

class TestSettleBreakdownPerItemTolerance:

    def _create_order(self, session, order_no):
        order = ChargingOrder(
            order_no=order_no,
            station_id=1, device_id=1, user_id=1,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.CHARGING,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    @pytest.mark.parametrize("poison", [
        "not-a-dict",                       # seg.get AttributeError
        None,
        {"fee": Decimal("1"), "price": "abc", "kwh": 1},  # price InvalidOperation
    ])
    def test_poison_segment_skipped_good_segments_kept(self, poison, test_db):
        """单条坏明细跳过+日志; 好明细保留; total 由 energy_fee 字段汇总不受污染"""
        session = test_db["session"]
        order = self._create_order(session, "BE-ERR-POISON")
        fees = {
            "energy_fee": Decimal("12.00"),
            "service_fee": Decimal("0"), "parking_fee": Decimal("0"),
            "occupancy_fee": Decimal("0"), "reservation_fee": Decimal("0"),
        }
        good = {"period_name": "peak", "fee": Decimal("12.00"),
                "kwh": Decimal("10"), "price": Decimal("1.20"), "unit": "kWh"}
        settle_order_fees(order, fees, db=session, energy_breakdown=[poison, good])

        items = session.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == order.id,
            OrderFeeItem.fee_type == FeeType.ELECTRICITY,
        ).all()
        assert len(items) == 1  # 只有 good, poison 被跳过
        assert items[0].fee_name == "peak"
        assert items[0].amount == Decimal("12.00")
        assert order.total_amount == Decimal("12.00")  # 汇总不因 poison 缩水


# ═══════════════════════════════════════════════════════════════
# L731: settle 实收 < 0 → 钳 0
# ═══════════════════════════════════════════════════════════════

class TestSettlePaidFloor:

    def test_discount_exceeds_total_paid_clamped_zero(self, test_db):
        """优惠三项之和 > 总费用 → paid_amount=0, 不出现负实收"""
        session = test_db["session"]
        order = ChargingOrder(
            order_no="BE-ERR-NEGPAID",
            station_id=1, device_id=1, user_id=1,
            payment_status=OrderPaymentStatus.UNPAID,
            order_status=OrderStatus.CHARGING,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        fees = {
            "energy_fee": Decimal("10.00"),
            "service_fee": Decimal("0"), "parking_fee": Decimal("0"),
            "occupancy_fee": Decimal("0"), "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("8.00"),
            "coupon_amount": Decimal("5.00"),
            "points_amount": Decimal("2.00"),
        }
        result = settle_order_fees(order, fees, db=session)

        session.refresh(order)
        # 10 - 8 - 5 - 2 = -5 → 钳 0
        assert result["paid_amount"] == 0.0
        assert order.paid_amount == Decimal("0.00")
        assert order.total_amount == Decimal("10.00")
