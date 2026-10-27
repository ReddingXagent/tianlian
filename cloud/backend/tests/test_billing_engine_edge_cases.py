"""
billing_engine 边界缺陷修复测试 (5项)

覆盖:
1. daily_cap 按天累计(缺陷1)        — 多日停车封顶 = daily_cap * ceil(billable/1440)
2. _split_day_night 区间相交(缺陷2) — 跨午夜多天精确分摊, 与逐分钟等价
3. 未知 fee_type 抛异常(缺陷3)      — 不再静默返回 0
4. settle_order_fees 事务安全(缺陷4) — 不内部 commit; 异常 rollback 无半成品
5. 缺失 slot_price 抛异常(缺陷5)    — 不再默认 0 免费充电

设计: 纯函数直接断言; settle 用 test_db fixture 走真实 SQLite。
"""
import pytest
from decimal import Decimal
from datetime import datetime, time
from sqlalchemy.orm import sessionmaker

from app.services.billing_engine import (
    compute_tou_energy_fee,
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_order_fees,
    _split_day_night,
    settle_order_fees,
)
from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
from app.models.order_fee_item import OrderFeeItem, FeeType


def _base_parking_rule(**overrides):
    rule = {
        "free_minutes": 0,
        "hourly_rate": Decimal("5.00"),
        "daily_cap": None,
        "enable_night_rate": False,
        "night_rate": None,
        "night_start": None,
        "night_end": None,
    }
    rule.update(overrides)
    return rule


def _make_order(session, order_no="BE-EDGE-001"):
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


def _full_fees(**overrides):
    fees = {
        "energy_fee": Decimal("32.00"),
        "service_fee": Decimal("20.00"),
        "parking_fee": Decimal("10.00"),
        "occupancy_fee": Decimal("15.00"),
        "reservation_fee": Decimal("7.50"),
        "discount_amount": Decimal("0"),
        "coupon_amount": Decimal("0"),
        "points_amount": Decimal("0"),
    }
    fees.update(overrides)
    return fees


# ═══════════════════════════════════════════════════════════════
# 缺陷1: daily_cap 按天累计(非总额封顶)
# ═══════════════════════════════════════════════════════════════

class TestDailyCapPerDay:
    """daily_cap 是每日封顶, 多日停车封顶 = daily_cap * ceil(billable/1440)"""

    def test_three_days_cap_multiplied(self):
        """停车3天 daily_cap=50 → 封顶150, 非50"""
        rule = _base_parking_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("50.00"))
        # 4320min=3天, billable=4320, ceil(4320/1440)=3 → cap=150
        # subtotal=4320/60*10=720 > 150 → total=150
        result = compute_parking_fee_full(4320, rule)
        assert result["total"] == Decimal("150.00")
        assert result["capped"] is True
        assert result["subtotal"] == Decimal("720.00")

    def test_exactly_one_day_single_cap(self):
        """恰好1天(1440min) → ceil=1, 单倍封顶"""
        rule = _base_parking_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("50.00"))
        result = compute_parking_fee_full(1440, rule)
        assert result["total"] == Decimal("50.00")

    def test_just_over_one_day_doubles_cap(self):
        """1441min → ceil(1441/1440)=2, 封顶翻倍"""
        rule = _base_parking_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("50.00"))
        # subtotal=1441/60*10=240.17 > 100 → total=100
        result = compute_parking_fee_full(1441, rule)
        assert result["total"] == Decimal("100.00")
        assert result["capped"] is True

    def test_cap_uses_billable_after_free_and_exempt(self):
        """cap 按 billable(扣除免费+充电免除后)计天数"""
        # 停车 2880min(2天), free 1440(1天), exempt 0 → billable=1440 → ceil=1 → cap=50
        rule = _base_parking_rule(
            free_minutes=1440, hourly_rate=Decimal("10.00"), daily_cap=Decimal("50.00"),
        )
        result = compute_parking_fee_full(2880, rule)
        # billable=1440, subtotal=1440/60*10=240>50 → total=50(单倍)
        assert result["total"] == Decimal("50.00")

    def test_multi_day_subtotal_below_cap_not_capped(self):
        """多日但日费率极低, subtotal 未达多倍 cap → 不封顶"""
        rule = _base_parking_rule(hourly_rate=Decimal("0.10"), daily_cap=Decimal("50.00"))
        # 2880min=2天, billable=2880, ceil=2, cap=100
        # subtotal=2880/60*0.1=4.80 < 100 → total=4.80, 不封顶
        result = compute_parking_fee_full(2880, rule)
        assert result["total"] == Decimal("4.80")
        assert result["capped"] is False

    def test_cross_calendar_day_under_24h_single_cap(self):
        """跨日历日但 billable<1440min 仍按单块封顶。

        场景: 23:30 入场, 次日 02:00 离场(跨午夜), 停车 150min。daily_cap 按
        ceil(billable/1440)=1 个 24h 滚动计费块累计(非自然日历日), 不因跨午夜翻倍。
        """
        rule = _base_parking_rule(hourly_rate=Decimal("100.00"), daily_cap=Decimal("50.00"))
        result = compute_parking_fee_full(
            150, rule, start_time=datetime(2026, 7, 21, 23, 30),
        )
        # billable=150, ceil(150/1440)=1 → cap=50; subtotal=150/60*100=250 > 50 → total=50
        assert result["total"] == Decimal("50.00")
        assert result["capped"] is True
        assert result["subtotal"] == Decimal("250.00")

    def test_exactly_two_full_days_cap_doubled(self):
        """恰好2整天(2880min) → ceil=2, 双倍封顶且 subtotal 超封顶被正确应用"""
        rule = _base_parking_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("50.00"))
        # billable=2880, ceil(2880/1440)=2 → cap=100; subtotal=2880/60*10=480 > 100 → total=100
        result = compute_parking_fee_full(2880, rule)
        assert result["total"] == Decimal("100.00")
        assert result["capped"] is True
        assert result["subtotal"] == Decimal("480.00")


# ═══════════════════════════════════════════════════════════════
# 缺陷2: _split_day_night 区间相交(替代逐分钟 O(n))
# ═══════════════════════════════════════════════════════════════

class TestSplitDayNightMath:
    """数学化日/夜分摊, 与逐分钟遍历结果等价"""

    def test_cross_midnight_single_night(self):
        """23:00起10h, 夜间22:00-06:00: 夜7h + 白3h"""
        day, night = _split_day_night(
            datetime(2026, 7, 21, 23, 0), 600, time(22, 0), time(6, 0),
        )
        assert day == 180
        assert night == 420

    def test_starts_before_night(self):
        """20:00起10h到次日06:00, 夜间22-06: 白2h + 夜8h"""
        day, night = _split_day_night(
            datetime(2026, 7, 21, 20, 0), 600, time(22, 0), time(6, 0),
        )
        assert day == 120
        assert night == 480

    def test_multi_day_span(self):
        """跨3天: 周期内逐分钟对照(参考实现)一致"""
        start = datetime(2026, 7, 21, 20, 0)
        billable = 3000  # 50h
        ns, ne = time(22, 0), time(6, 0)
        day, night = _split_day_night(start, billable, ns, ne)

        # 参考实现: 逐分钟(缺陷修复前等价行为)
        ref_day = ref_night = 0
        from datetime import timedelta
        for i in range(billable):
            cur = start + timedelta(minutes=i)
            t = cur.time()
            is_night = t >= ns or t < ne
            if is_night:
                ref_night += 1
            else:
                ref_day += 1
        assert (day, night) == (ref_day, ref_night)
        assert day + night == billable

    def test_non_crossing_night_window(self):
        """非跨午夜夜间窗(13:00-17:00): start 12:00 起6h"""
        day, night = _split_day_night(
            datetime(2026, 7, 21, 12, 0), 360, time(13, 0), time(17, 0),
        )
        # 12-13 白1h + 13-17 夜4h + 17-18 白1h
        assert day == 120
        assert night == 240


# ═══════════════════════════════════════════════════════════════
# 缺陷3: 未知 fee_type 抛 ValueError
# ═══════════════════════════════════════════════════════════════

class TestUnknownFeeTypeRaises:

    def test_unknown_type_raises(self):
        """未知 fee_type 不再静默返回 0, 抛 ValueError"""
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("40"), "unknown", Decimal("1.0"))

    def test_empty_type_raises(self):
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("40"), "", Decimal("1.0"))

    def test_fixed_still_works(self):
        assert compute_service_fee_multi(Decimal("50"), "fixed", Decimal("5.00")) == Decimal("5.00")

    def test_percent_still_works(self):
        assert compute_service_fee_multi(Decimal("40"), "percent", Decimal("0.5")) == Decimal("20.00")


# ═══════════════════════════════════════════════════════════════
# 缺陷5: 缺失 slot_price 抛 ValueError
# ═══════════════════════════════════════════════════════════════

class TestMissingSlotPriceRaises:

    def test_missing_price_for_covered_slot_raises(self):
        """slot 覆盖充电时段但 prices 缺该 slot → 抛 ValueError(不再免费)"""
        slots = [{"slot_id": 1, "period_type": "flat",
                  "start_time": time(8, 0), "end_time": time(12, 0)}]
        with pytest.raises(ValueError, match="Missing price for slot: 1"):
            compute_tou_energy_fee(
                start_time=datetime(2026, 7, 21, 8, 0),
                end_time=datetime(2026, 7, 21, 10, 0),
                total_kwh=Decimal("20"),
                time_slots=slots,
                slot_prices={},  # 缺 slot 1
            )

    def test_missing_price_for_uncovered_slot_ok(self):
        """slot 未覆盖充电时段(overlap=0 跳过), 缺价格不抛"""
        slots = [{"slot_id": 1, "period_type": "peak",
                  "start_time": time(10, 0), "end_time": time(12, 0)}]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 14, 0),
            end_time=datetime(2026, 7, 21, 16, 0),
            total_kwh=Decimal("10"),
            time_slots=slots,
            slot_prices={},  # 缺 slot 1 但不覆盖
        )
        assert result["total_fee"] == Decimal("0.00")

    def test_complete_prices_still_works(self):
        slots = [{"slot_id": 1, "period_type": "flat",
                  "start_time": time(8, 0), "end_time": time(10, 0)}]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),
            end_time=datetime(2026, 7, 21, 10, 0),
            total_kwh=Decimal("20"),
            time_slots=slots,
            slot_prices={1: Decimal("0.6")},
        )
        assert result["total_fee"] == Decimal("12.00")


# ═══════════════════════════════════════════════════════════════
# 缺陷4: settle_order_fees 事务安全
# ═══════════════════════════════════════════════════════════════

class TestSettleTransactionSafety:

    def test_settle_does_not_commit_internally(self, test_db):
        """settle 不自己 commit; 调用方未 commit 时另一 session 看不到明细"""
        session = test_db["session"]
        engine = test_db["engine"]
        order = _make_order(session, "BE-EDGE-NOCOMMIT")

        settle_order_fees(order, _full_fees(
            discount_amount=Decimal("10"), coupon_amount=Decimal("5"), points_amount=Decimal("3"),
        ), db=session)
        # 不 commit, 另开 session 查 → 看不到 OrderFeeItem
        other = sessionmaker(bind=engine)()
        try:
            count = other.query(OrderFeeItem).filter_by(order_id=order.id).count()
            assert count == 0
        finally:
            other.close()
        # 提交后另一 session 才可见(调用方控制事务)
        session.commit()
        other2 = sessionmaker(bind=engine)()
        try:
            count = other2.query(OrderFeeItem).filter_by(order_id=order.id).count()
            assert count == 8  # 5费用 + 3优惠
        finally:
            other2.close()

    def test_settle_rollback_on_error_no_partial(self, test_db, monkeypatch):
        """settle 中途异常 → rollback, 已删除的旧明细恢复(无半成品)"""
        session = test_db["session"]
        order = _make_order(session, "BE-EDGE-ROLLBACK")

        # 预置一条旧明细
        old_item = OrderFeeItem(
            order_id=order.id, fee_type=FeeType.SERVICE, fee_name="旧明细",
            quantity=Decimal("1"), unit_price=Decimal("1.00"),
            amount=Decimal("1.00"), unit="元",
        )
        session.add(old_item)
        session.commit()

        rollback_called = []
        _real_rollback = session.rollback

        def _spy_rollback():
            rollback_called.append(True)
            return _real_rollback()

        monkeypatch.setattr(session, "rollback", _spy_rollback)
        # 让 add_all 抛异常(模拟中途失败)
        def boom(items):
            raise RuntimeError("simulated mid-settle failure")
        monkeypatch.setattr(session, "add_all", boom)

        with pytest.raises(RuntimeError, match="simulated mid-settle failure"):
            settle_order_fees(order, _full_fees(), db=session)

        monkeypatch.undo()
        # rollback 被调用
        assert rollback_called == [True]
        # 旧明细恢复(delete 被回滚), 无新半成品
        session.expire_all()
        items = session.query(OrderFeeItem).filter_by(order_id=order.id).all()
        assert len(items) == 1
        assert items[0].fee_name == "旧明细"


# ═══════════════════════════════════════════════════════════════
# 缺陷6: 重叠时段双倍计费 — sum(overlap) > 充电时长 → ValueError
# ═══════════════════════════════════════════════════════════════

class TestOverlappingSlotsRaises:
    """time_slots 重叠时, 各 slot overlap 分钟之和超过充电总时长 → 配置错误, 抛 ValueError

    否则恒功率分摊会使 total_energy > total_kwh, 客户被多收费。
    """

    def test_overlapping_slots_raises(self):
        """两 slot(8-14 / 10-16)重叠 4h, 充电 10-12(120min): overlap 之和 240 > 120 → 抛错"""
        slots = [
            {"slot_id": 1, "period_type": "peak",
             "start_time": time(8, 0), "end_time": time(14, 0)},
            {"slot_id": 2, "period_type": "flat",
             "start_time": time(10, 0), "end_time": time(16, 0)},
        ]
        with pytest.raises(ValueError, match="Time slots overlap"):
            compute_tou_energy_fee(
                start_time=datetime(2026, 7, 21, 10, 0),
                end_time=datetime(2026, 7, 21, 12, 0),
                total_kwh=Decimal("10"),
                time_slots=slots,
                slot_prices={1: Decimal("0.6"), 2: Decimal("0.5")},
            )

    def test_adjacent_non_overlapping_ok(self):
        """相邻不重叠 slot(8-10 / 10-12), 充电 8-12: overlap 之和 == 充电时长, 不抛"""
        slots = [
            {"slot_id": 1, "period_type": "peak",
             "start_time": time(8, 0), "end_time": time(10, 0)},
            {"slot_id": 2, "period_type": "flat",
             "start_time": time(10, 0), "end_time": time(12, 0)},
        ]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),
            end_time=datetime(2026, 7, 21, 12, 0),
            total_kwh=Decimal("20"),
            time_slots=slots,
            slot_prices={1: Decimal("0.6"), 2: Decimal("0.5")},
        )
        # overlap 之和 240 == 充电时长 240, 不抛; 电量不被放大
        assert result["total_energy"] == Decimal("20.00")

    def test_single_slot_full_coverage_ok(self):
        """单一 slot 全覆盖, overlap == 充电时长, 不抛"""
        slots = [{"slot_id": 1, "period_type": "flat",
                  "start_time": time(8, 0), "end_time": time(12, 0)}]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),
            end_time=datetime(2026, 7, 21, 12, 0),
            total_kwh=Decimal("15"),
            time_slots=slots,
            slot_prices={1: Decimal("0.6")},
        )
        assert result["total_energy"] == Decimal("15.00")


# ═══════════════════════════════════════════════════════════════
# 缺陷7: 负数基础费用未守卫 → total_amount 为负
# ═══════════════════════════════════════════════════════════════

class TestNegativeFeeInputGuarded:
    """compute_order_fees 5 项基础费用经 _nonneg() 守卫, 负值归零(基础费用不允许为负)"""

    def test_negative_fee_input_guarded(self):
        """负数 energy_fee → 守卫为 0, total_amount 不为负"""
        result = compute_order_fees(
            energy_fee=Decimal("-50"),
            service_fee=Decimal("0"),
            parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"),
            reservation_fee=Decimal("0"),
        )
        assert result["total_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")

    def test_negative_partially_offset_by_positive(self):
        """energy_fee=-30 + service_fee=50: 负项归零后 total=50(非 20), 证明是逐项守卫而非末尾裁剪"""
        result = compute_order_fees(
            energy_fee=Decimal("-30"),
            service_fee=Decimal("50"),
            parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"),
            reservation_fee=Decimal("0"),
        )
        assert result["total_amount"] == Decimal("50.00")

    def test_all_negative_fees_guarded(self):
        """5 项基础费用全负 → total/paid 均为 0"""
        result = compute_order_fees(
            energy_fee=Decimal("-10"),
            service_fee=Decimal("-5"),
            parking_fee=Decimal("-3"),
            occupancy_fee=Decimal("-2"),
            reservation_fee=Decimal("-1"),
        )
        assert result["total_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 缺陷8: TOU 时段覆盖缺口 → 静默少收费(coverage 校验)
# ═══════════════════════════════════════════════════════════════
class TestTouCoverageGap:
    """time_slots 未完全覆盖充电区间时, 未覆盖分钟电量被静默排除(total_energy<total_kwh),
    客户少付费且无任何警告/日志。

    修复: 计算 coverage=total_overlap/total_minutes, <1.0 时 _logger.warning 并在返回 dict
    加 coverage 标记, 不再静默; 不抛错(配置缺口由调用方默认电价兜底, 抛错反而整体走默认更糟)。
    """

    def test_partial_coverage_marks_and_warns(self, caplog):
        """只定义尖峰段(8-12), 充电 8-16(480min): 仅覆盖 240min → coverage=0.5 + warning"""
        slots = [{"slot_id": 1, "period_type": "peak",
                  "start_time": time(8, 0), "end_time": time(12, 0)}]
        with caplog.at_level("WARNING", logger="app.services.billing_engine"):
            result = compute_tou_energy_fee(
                start_time=datetime(2026, 7, 21, 8, 0),
                end_time=datetime(2026, 7, 21, 16, 0),
                total_kwh=Decimal("20"),
                time_slots=slots,
                slot_prices={1: Decimal("1.0")},
            )
        assert result["coverage"] == pytest.approx(0.5)
        assert any("覆盖" in r.message or "coverage" in r.message.lower()
                   for r in caplog.records)

    def test_partial_coverage_undercounts_energy(self):
        """缺口场景文档化: 仅 50% 分钟被覆盖 → total_energy=10(非 20), 客户少付费"""
        slots = [{"slot_id": 1, "period_type": "peak",
                  "start_time": time(8, 0), "end_time": time(12, 0)}]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),
            end_time=datetime(2026, 7, 21, 16, 0),
            total_kwh=Decimal("20"),
            time_slots=slots,
            slot_prices={1: Decimal("1.0")},
        )
        assert result["total_energy"] == Decimal("10.00")
        assert result["coverage"] == pytest.approx(0.5)

    def test_full_coverage_no_warning(self, caplog):
        """全覆盖: coverage=1.0, 无 warning"""
        slots = [{"slot_id": 1, "period_type": "flat",
                  "start_time": time(8, 0), "end_time": time(16, 0)}]
        with caplog.at_level("WARNING", logger="app.services.billing_engine"):
            result = compute_tou_energy_fee(
                start_time=datetime(2026, 7, 21, 8, 0),
                end_time=datetime(2026, 7, 21, 16, 0),
                total_kwh=Decimal("20"),
                time_slots=slots,
                slot_prices={1: Decimal("0.6")},
            )
        assert result["coverage"] == pytest.approx(1.0)
        assert not any("覆盖" in r.message or "coverage" in r.message.lower()
                       for r in caplog.records)

    def test_zero_coverage_no_matching_slot_marked(self, caplog):
        """完全无匹配(overlap=0): coverage=0.0 + warning(total_fee 仍 0)"""
        slots = [{"slot_id": 1, "period_type": "peak",
                  "start_time": time(10, 0), "end_time": time(12, 0)}]
        with caplog.at_level("WARNING", logger="app.services.billing_engine"):
            result = compute_tou_energy_fee(
                start_time=datetime(2026, 7, 21, 14, 0),
                end_time=datetime(2026, 7, 21, 16, 0),
                total_kwh=Decimal("30"),
                time_slots=slots,
                slot_prices={1: Decimal("1.0")},
            )
        assert result["coverage"] == pytest.approx(0.0)
        assert result["total_fee"] == Decimal("0.00")
        assert any("覆盖" in r.message or "coverage" in r.message.lower()
                   for r in caplog.records)


# ═══════════════════════════════════════════════════════════════
# 缺陷9: night_start == night_end 误配置(全天夜间窗)
# ═══════════════════════════════════════════════════════════════
class TestParkingNightWindowEqualStartEnd:
    """night_start == night_end 被 _slot_window_on_date 视为全天窗, 误配置会让全部分钟
    按夜间费率计费(夜间费率通常更低 → 客户少付停车费)。

    修复: compute_parking_fee_full 入口检测相等 → warning + 降级为不启用夜间分摊(全白天)。
    """

    def test_equal_night_window_warns_and_degrades_to_day(self, caplog):
        """night_start==night_end==02:00 → 无效夜间窗, 全按白天费率(非全夜间)"""
        rule = _base_parking_rule(
            hourly_rate=Decimal("5.00"),
            enable_night_rate=True,
            night_rate=Decimal("2.00"),
            night_start=time(2, 0),
            night_end=time(2, 0),  # 相等 = 误配置
        )
        with caplog.at_level("WARNING", logger="app.services.billing_engine"):
            result = compute_parking_fee_full(
                120, rule, start_time=datetime(2026, 7, 21, 10, 0),
            )
        # 降级为白天: 120min=2h × 5.0 = 10.00(非全夜间 2h × 2.0 = 4.00)
        assert result["day_minutes"] == 120
        assert result["night_minutes"] == 0
        assert result["total"] == Decimal("10.00")
        assert any("夜间" in r.message for r in caplog.records)

    def test_normal_cross_midnight_night_window_unaffected(self):
        """正常跨午夜夜间窗(22-06)不受相等校验影响"""
        rule = _base_parking_rule(
            hourly_rate=Decimal("5.00"),
            enable_night_rate=True,
            night_rate=Decimal("2.00"),
            night_start=time(22, 0),
            night_end=time(6, 0),
        )
        # 23:00 起 60min 全夜间
        result = compute_parking_fee_full(
            60, rule, start_time=datetime(2026, 7, 21, 23, 0),
        )
        assert result["night_minutes"] == 60
        assert result["day_minutes"] == 0
        assert result["total"] == Decimal("2.00")


# ═══════════════════════════════════════════════════════════════
# 缺陷10: energy_by_period 之和 != total_energy(精度不一致)
# ═══════════════════════════════════════════════════════════════
class TestTouEnergyPrecisionConsistency:
    """period_breakdown["energy"] 量化 2 位展示, total_energy 却按 4 位累加后再量化 2 位 →
    非整除时 energy_by_period(2 位)之和 ≠ total_energy, 展示自相矛盾。

    修复: total_energy 改为按 2 位分项累加, 与 energy_by_period 同源, 两者恒等。
    """

    def test_three_way_split_sum_equals_total(self):
        """3 时段均分 10kWh(非整除): 各 3.33, 和 9.99 == total_energy(修复前 9.99 != 10.00)"""
        slots = [
            {"slot_id": 1, "period_type": "peak",
             "start_time": time(0, 0), "end_time": time(8, 0)},
            {"slot_id": 2, "period_type": "flat",
             "start_time": time(8, 0), "end_time": time(16, 0)},
            {"slot_id": 3, "period_type": "valley",
             "start_time": time(16, 0), "end_time": time(0, 0)},  # 跨午夜到次日 00:00
        ]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 0, 0),
            end_time=datetime(2026, 7, 22, 0, 0),  # 24h = 1440min
            total_kwh=Decimal("10"),
            time_slots=slots,
            slot_prices={1: Decimal("1.0"), 2: Decimal("0.6"), 3: Decimal("0.3")},
        )
        energy_sum = sum(result["energy_by_period"].values(), Decimal("0"))
        assert energy_sum == result["total_energy"]  # 修复前 9.99 != 10.00
        assert result["total_energy"] == Decimal("9.99")
