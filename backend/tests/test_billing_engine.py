"""
计费引擎增强测试 - Phase41 SPEC §2.1 费用模型管理

覆盖:
1. 充电费 — 尖峰平谷时段计费(按充电起止时间拆分电量, 支持跨午夜时段)
2. 服务费 — 多模式(fixed 元/次, percent 元/kWh)
3. 停车费 — 完整规则(免费时长/小时费率/日封顶/夜间费率/充电期间免除)
4. 占桩费 — 完整规则(宽限时长/费率/单次封顶)
5. 预约费 — 完整规则(预约费/冻结金额/爽约罚款)
6. 总费用 — 实收 = 总费用 - 优惠券 - 积分 - 折扣(三项分离)
7. 订单费用写入 — 5项费用字段 + order_fee_items 明细行

引擎为纯计算函数(接受规则 dict, 不耦合 ORM), 便于单测与复用。
"""
import pytest
from decimal import Decimal
from datetime import datetime, time, timezone, timedelta

from app.services.billing_engine import (
    compute_tou_energy_fee,
    compute_service_fee_multi,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    compute_reservation_fee_full,
    compute_order_fees,
    settle_order_fees,
)
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus,
)
from app.models.order_fee_item import OrderFeeItem, FeeType


# ═══════════════════════════════════════════════════════════════
# 1. TOU 时段充电费
# ═══════════════════════════════════════════════════════════════

class TestTOUEnergyFee:
    """按充电起止时间拆分各时段电量, ∑(时段电量×时段电价)"""

    def test_single_period(self):
        """完全落在单一时段"""
        slots = [
            {"slot_id": 1, "period_type": "flat", "start_time": time(8, 0), "end_time": time(10, 0)},
            {"slot_id": 2, "period_type": "peak", "start_time": time(10, 0), "end_time": time(12, 0)},
        ]
        prices = {1: Decimal("0.6"), 2: Decimal("1.0")}
        # 8:00-10:00 全在 flat
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),
            end_time=datetime(2026, 7, 21, 10, 0),
            total_kwh=Decimal("20"),
            time_slots=slots,
            slot_prices=prices,
        )
        assert result["total_fee"] == Decimal("12.00")
        assert result["energy_by_period"]["flat"] == Decimal("20.00")

    def test_split_across_two_periods(self):
        """跨两个时段按时间比例分摊电量"""
        slots = [
            {"slot_id": 1, "period_type": "flat", "start_time": time(8, 0), "end_time": time(10, 0)},
            {"slot_id": 2, "period_type": "peak", "start_time": time(10, 0), "end_time": time(12, 0)},
        ]
        prices = {1: Decimal("0.6"), 2: Decimal("1.0")}
        # 8:00-12:00 = 4h, flat 8-10 占 2h, peak 10-12 占 2h
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),
            end_time=datetime(2026, 7, 21, 12, 0),
            total_kwh=Decimal("40"),
            time_slots=slots,
            slot_prices=prices,
        )
        # 平摊: flat=20kWh@0.6=12.00, peak=20kWh@1.0=20.00
        assert result["energy_by_period"]["flat"] == Decimal("20.00")
        assert result["energy_by_period"]["peak"] == Decimal("20.00")
        assert result["period_breakdown"]["flat"]["fee"] == Decimal("12.00")
        assert result["period_breakdown"]["peak"]["fee"] == Decimal("20.00")
        assert result["total_fee"] == Decimal("32.00")

    def test_energy_conservation(self):
        """各时段分摊电量之和等于总电量"""
        slots = [
            {"slot_id": 1, "period_type": "flat", "start_time": time(6, 0), "end_time": time(22, 0)},
            {"slot_id": 2, "period_type": "valley", "start_time": time(22, 0), "end_time": time(6, 0)},
        ]
        prices = {1: Decimal("0.6"), 2: Decimal("0.3")}
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 20, 0),
            end_time=datetime(2026, 7, 22, 0, 0),  # 20:00-24:00 = 4h
            total_kwh=Decimal("40"),
            time_slots=slots,
            slot_prices=prices,
        )
        total_split = sum(result["energy_by_period"].values(), Decimal("0"))
        assert total_split == Decimal("40.00")

    def test_cross_midnight_valley(self):
        """跨午夜谷段(22:00→次日06:00)在当天窗口正确重叠"""
        slots = [
            {"slot_id": 1, "period_type": "flat", "start_time": time(6, 0), "end_time": time(22, 0)},
            {"slot_id": 2, "period_type": "valley", "start_time": time(22, 0), "end_time": time(6, 0)},
        ]
        prices = {1: Decimal("0.6"), 2: Decimal("0.3")}
        # 20:00-00:00: flat 占 20-22=2h, valley 占 22-00=2h
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 20, 0),
            end_time=datetime(2026, 7, 22, 0, 0),
            total_kwh=Decimal("40"),
            time_slots=slots,
            slot_prices=prices,
        )
        assert result["energy_by_period"]["flat"] == Decimal("20.00")
        assert result["energy_by_period"]["valley"] == Decimal("20.00")
        # 20*0.6 + 20*0.3 = 12 + 6 = 18
        assert result["total_fee"] == Decimal("18.00")

    def test_no_matching_slot(self):
        """无匹配时段电价 → 电费为0"""
        slots = [{"slot_id": 1, "period_type": "peak", "start_time": time(10, 0), "end_time": time(12, 0)}]
        prices = {1: Decimal("1.0")}
        # 充电时段 14:00-16:00 不在任何定义时段内
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 14, 0),
            end_time=datetime(2026, 7, 21, 16, 0),
            total_kwh=Decimal("30"),
            time_slots=slots,
            slot_prices=prices,
        )
        assert result["total_fee"] == Decimal("0.00")

    def test_zero_duration(self):
        """零时长 → 电费0"""
        slots = [{"slot_id": 1, "period_type": "flat", "start_time": time(0, 0), "end_time": time(23, 59)}]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 10, 0),
            end_time=datetime(2026, 7, 21, 10, 0),
            total_kwh=Decimal("50"),
            time_slots=slots,
            slot_prices={1: Decimal("0.8")},
        )
        assert result["total_fee"] == Decimal("0.00")

    def test_zero_energy(self):
        """零电量 → 电费0"""
        slots = [{"slot_id": 1, "period_type": "flat", "start_time": time(0, 0), "end_time": time(23, 59)}]
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 10, 0),
            end_time=datetime(2026, 7, 21, 11, 0),
            total_kwh=Decimal("0"),
            time_slots=slots,
            slot_prices={1: Decimal("0.8")},
        )
        assert result["total_fee"] == Decimal("0.00")

    def test_aware_datetimes_stripped_no_typeerror(self):
        """aware datetime 入参被入口抹平 tzinfo, 不抛 TypeError。

        下游 _slot_window_on_date 用 datetime.combine 构造的时段窗口均为 naive,
        aware 入参与之比较/相减会抛 TypeError(can't compare offset-naive and
        offset-aware)。TOU 时段仅关心本地时钟(slot 的 time 无时区), 抹平 tzinfo
        不改变计费结果。
        """
        slots = [
            {"slot_id": 1, "period_type": "flat", "start_time": time(8, 0), "end_time": time(10, 0)},
        ]
        prices = {1: Decimal("0.6")}
        cst = timezone(timedelta(hours=8))
        # start/end 均 aware(CST): 8:00-10:00 全 flat, 20kWh@0.6=12.00
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0, tzinfo=cst),
            end_time=datetime(2026, 7, 21, 10, 0, tzinfo=cst),
            total_kwh=Decimal("20"),
            time_slots=slots,
            slot_prices=prices,
        )
        assert result["total_fee"] == Decimal("12.00")
        assert result["energy_by_period"]["flat"] == Decimal("20.00")

    def test_mixed_aware_naive_no_typeerror(self):
        """start naive + end aware 混合 → 入口统一 naive 化, 不抛 TypeError"""
        slots = [
            {"slot_id": 1, "period_type": "flat", "start_time": time(8, 0), "end_time": time(10, 0)},
        ]
        prices = {1: Decimal("0.6")}
        cst = timezone(timedelta(hours=8))
        result = compute_tou_energy_fee(
            start_time=datetime(2026, 7, 21, 8, 0),             # naive
            end_time=datetime(2026, 7, 21, 10, 0, tzinfo=cst),  # aware
            total_kwh=Decimal("20"),
            time_slots=slots,
            slot_prices=prices,
        )
        assert result["total_fee"] == Decimal("12.00")


# ═══════════════════════════════════════════════════════════════
# 2. 服务费多模式
# ═══════════════════════════════════════════════════════════════

class TestServiceFeeMulti:

    def test_fixed_per_session(self):
        """固定金额(元/次), 与电量无关"""
        fee = compute_service_fee_multi(Decimal("50"), "fixed", Decimal("5.00"))
        assert fee == Decimal("5.00")

    def test_fixed_zero_kwh_still_charged(self):
        """按次收费即使零电量也收"""
        fee = compute_service_fee_multi(Decimal("0"), "fixed", Decimal("3.00"))
        assert fee == Decimal("3.00")

    def test_percent_per_kwh(self):
        """按电量计费(元/kWh)"""
        fee = compute_service_fee_multi(Decimal("40"), "percent", Decimal("0.5"))
        assert fee == Decimal("20.00")

    def test_percent_zero_kwh(self):
        """按电量计费零电量为0"""
        fee = compute_service_fee_multi(Decimal("0"), "percent", Decimal("0.5"))
        assert fee == Decimal("0.00")

    def test_unknown_type_raises(self):
        """未知费用类型 → 抛 ValueError(不再静默返回 0, 见 test_billing_engine_edge_cases)"""
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("40"), "unknown", Decimal("1.0"))


# ═══════════════════════════════════════════════════════════════
# 3. 停车费完整规则
# ═══════════════════════════════════════════════════════════════

class TestParkingFeeFull:

    def _base_rule(self, **overrides):
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

    def test_free_within_free_minutes(self):
        """免费时长内 → 0"""
        rule = self._base_rule(free_minutes=60)
        result = compute_parking_fee_full(30, rule)
        assert result["total"] == Decimal("0.00")

    def test_basic_hourly(self):
        """基础小时计费"""
        rule = self._base_rule(free_minutes=0, hourly_rate=Decimal("5.00"))
        result = compute_parking_fee_full(120, rule)
        assert result["total"] == Decimal("10.00")

    def test_daily_cap(self):
        """日封顶"""
        rule = self._base_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("30.00"))
        result = compute_parking_fee_full(600, rule)  # 10h * 10 = 100 > 30
        assert result["total"] == Decimal("30.00")
        assert result["capped"] is True

    def test_below_cap_not_capped(self):
        """未达封顶"""
        rule = self._base_rule(hourly_rate=Decimal("5.00"), daily_cap=Decimal("50.00"))
        result = compute_parking_fee_full(120, rule)  # 10 < 50
        assert result["total"] == Decimal("10.00")
        assert result["capped"] is False

    def test_daily_cap_cross_calendar_day_single_block(self):
        """跨日历日但 billable<1440min → ceil(1)=1 块封顶, 不翻倍"""
        rule = self._base_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("30.00"))
        # billable=1200min (20h), 没到24h, 即使跨过午夜也只算1个封顶块
        result = compute_parking_fee_full(1200, rule)
        assert result["total"] == Decimal("30.00")
        assert result["capped"] is True

    def test_daily_cap_multi_day_two_blocks(self):
        """billable>1440min → ceil(2)=2 块封顶"""
        rule = self._base_rule(hourly_rate=Decimal("10.00"), daily_cap=Decimal("30.00"))
        # billable=1500min (25h), ceil(1500/1440)=2 → cap=60
        result = compute_parking_fee_full(1500, rule)
        assert result["total"] == Decimal("60.00")
        assert result["capped"] is True

    def test_charging_exempt(self):
        """充电期间免停车费"""
        # 停车 180min, 充电免除 60min, 免费 30min → 计费 90min = 1.5h
        rule = self._base_rule(free_minutes=30, hourly_rate=Decimal("5.00"))
        result = compute_parking_fee_full(180, rule, charging_exempt_minutes=60)
        assert result["total"] == Decimal("7.50")

    def test_night_rate(self):
        """夜间费率分摊"""
        # 夜间 23:00-07:00, 停车 22:00-02:00 = 4h
        # day 22-23 = 1h @5, night 23-02 = 3h @2 → 5 + 6 = 11
        rule = self._base_rule(
            hourly_rate=Decimal("5.00"),
            enable_night_rate=True,
            night_rate=Decimal("2.00"),
            night_start=time(23, 0),
            night_end=time(7, 0),
        )
        result = compute_parking_fee_full(
            240, rule, start_time=datetime(2026, 7, 21, 22, 0),
        )
        assert result["day_fee"] == Decimal("5.00")
        assert result["night_fee"] == Decimal("6.00")
        assert result["total"] == Decimal("11.00")

    def test_all_night(self):
        """全部落在夜间窗口"""
        # 00:00-04:00 = 4h 全夜间 @2 → 8.00
        rule = self._base_rule(
            hourly_rate=Decimal("5.00"),
            enable_night_rate=True,
            night_rate=Decimal("2.00"),
            night_start=time(23, 0),
            night_end=time(7, 0),
        )
        result = compute_parking_fee_full(
            240, rule, start_time=datetime(2026, 7, 21, 0, 0),
        )
        assert result["day_fee"] == Decimal("0.00")
        assert result["night_fee"] == Decimal("8.00")
        assert result["total"] == Decimal("8.00")

    def test_night_with_cap(self):
        """夜间计费仍受日封顶约束"""
        rule = self._base_rule(
            hourly_rate=Decimal("5.00"),
            enable_night_rate=True,
            night_rate=Decimal("4.00"),
            night_start=time(23, 0),
            night_end=time(7, 0),
            daily_cap=Decimal("20.00"),
        )
        # 00:00-08:00 = 8h: 0-07 夜间7h@4=28 + 07-08 白天1h@5=5 = 33 > 20
        result = compute_parking_fee_full(
            480, rule, start_time=datetime(2026, 7, 21, 0, 0),
        )
        assert result["total"] == Decimal("20.00")
        assert result["capped"] is True


# ═══════════════════════════════════════════════════════════════
# 4. 占桩费完整规则
# ═══════════════════════════════════════════════════════════════

class TestOccupancyFeeFull:

    def test_basic(self):
        """宽限后按分钟计费"""
        rule = {"grace_minutes": 15, "rate_per_minute": Decimal("0.50"), "max_fee": None}
        fee = compute_occupancy_fee_full(30, rule)
        assert fee == Decimal("7.50")  # (30-15)*0.5

    def test_within_grace(self):
        """宽限期内 → 0"""
        rule = {"grace_minutes": 30, "rate_per_minute": Decimal("0.50"), "max_fee": None}
        fee = compute_occupancy_fee_full(20, rule)
        assert fee == Decimal("0.00")

    def test_max_fee_cap(self):
        """单次封顶"""
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("1.00"), "max_fee": Decimal("50.00")}
        fee = compute_occupancy_fee_full(200, rule)  # 200 > 50
        assert fee == Decimal("50.00")

    def test_no_occupancy(self):
        """无占桩 → 0"""
        rule = {"grace_minutes": 15, "rate_per_minute": Decimal("0.50"), "max_fee": None}
        fee = compute_occupancy_fee_full(0, rule)
        assert fee == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 5. 预约费完整规则
# ═══════════════════════════════════════════════════════════════

class TestReservationFeeFull:

    def test_flat_policy(self):
        """固定预约费"""
        rule = {
            "reservation_policy": "flat",
            "fee_amount": Decimal("5.00"),
            "deposit_amount": Decimal("50.00"),
            "no_show_penalty": Decimal("20.00"),
        }
        result = compute_reservation_fee_full(rule, no_show=False)
        assert result["fee"] == Decimal("5.00")
        assert result["deposit"] == Decimal("50.00")
        assert result["total"] == Decimal("5.00")  # 不含爽约

    def test_no_show_penalty(self):
        """爽约加罚款"""
        rule = {
            "reservation_policy": "flat",
            "fee_amount": Decimal("5.00"),
            "deposit_amount": Decimal("50.00"),
            "no_show_penalty": Decimal("20.00"),
        }
        result = compute_reservation_fee_full(rule, no_show=True)
        assert result["total"] == Decimal("25.00")  # 5 + 20

    def test_slot_based_policy(self):
        """按时段策略(使用 fee_amount 作为基础预约费)"""
        rule = {
            "reservation_policy": "slot_based",
            "fee_amount": Decimal("8.00"),
            "deposit_amount": Decimal("30.00"),
            "no_show_penalty": Decimal("10.00"),
        }
        result = compute_reservation_fee_full(rule, no_show=False)
        assert result["fee"] == Decimal("8.00")
        assert result["total"] == Decimal("8.00")


# ═══════════════════════════════════════════════════════════════
# 6. 综合费用(优惠三项分离)
# ═══════════════════════════════════════════════════════════════

class TestComputeOrderFees:

    def test_three_discounts_separated(self):
        """三项优惠分离: 实收 = 总 - 券 - 积分 - 折扣"""
        result = compute_order_fees(
            energy_fee=Decimal("40"),
            service_fee=Decimal("20"),
            parking_fee=Decimal("10"),
            occupancy_fee=Decimal("15"),
            reservation_fee=Decimal("7.50"),
            discount_amount=Decimal("10"),
            coupon_amount=Decimal("5"),
            points_amount=Decimal("3"),
        )
        assert result["total_amount"] == Decimal("92.50")
        assert result["discount_amount"] == Decimal("10.00")
        assert result["coupon_amount"] == Decimal("5.00")
        assert result["points_amount"] == Decimal("3.00")
        assert result["paid_amount"] == Decimal("74.50")  # 92.5 - 10 - 5 - 3

    def test_no_discounts(self):
        """无优惠 → 实收 = 总"""
        result = compute_order_fees(
            energy_fee=Decimal("100"),
            service_fee=Decimal("0"),
            parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"),
            reservation_fee=Decimal("0"),
        )
        assert result["total_amount"] == Decimal("100.00")
        assert result["paid_amount"] == Decimal("100.00")

    def test_paid_floor_zero(self):
        """优惠超过总额 → 实收不低于0"""
        result = compute_order_fees(
            energy_fee=Decimal("10"),
            service_fee=Decimal("0"),
            parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"),
            reservation_fee=Decimal("0"),
            discount_amount=Decimal("100"),
        )
        assert result["paid_amount"] == Decimal("0.00")

    def test_negative_discount_ignored(self):
        """负数优惠按0处理"""
        result = compute_order_fees(
            energy_fee=Decimal("20"),
            service_fee=Decimal("0"),
            parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"),
            reservation_fee=Decimal("0"),
            discount_amount=Decimal("-5"),
        )
        assert result["discount_amount"] == Decimal("0.00")
        assert result["paid_amount"] == Decimal("20.00")


# ═══════════════════════════════════════════════════════════════
# 7. 订单费用写入 + 明细
# ═══════════════════════════════════════════════════════════════

class TestSettleOrderFees:
    """结算引擎写入 ChargingOrder + 生成 OrderFeeItem 明细"""

    def _create_order(self, session, order_no="BE-SET-001"):
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

    def test_settle_writes_five_fee_fields(self, test_db):
        """结算写入订单 5 项费用字段 + 总额/实收"""
        session = test_db["session"]
        order = self._create_order(session, "BE-SET-002")

        fees = {
            "energy_fee": Decimal("32.00"),
            "service_fee": Decimal("20.00"),
            "parking_fee": Decimal("10.00"),
            "occupancy_fee": Decimal("15.00"),
            "reservation_fee": Decimal("7.50"),
            "discount_amount": Decimal("10.00"),
            "coupon_amount": Decimal("5.00"),
            "points_amount": Decimal("3.00"),
        }
        result = settle_order_fees(order, fees, db=session)

        session.refresh(order)
        assert order.electricity_fee == Decimal("32.00")
        assert order.service_fee == Decimal("20.00")
        assert order.parking_fee == Decimal("10.00")
        assert order.occupancy_fee == Decimal("15.00")
        assert order.reservation_fee == Decimal("7.50")
        assert order.idle_penalty == Decimal("15.00")  # 兼容旧字段
        assert order.total_amount == Decimal("84.50")  # 32+20+10+15+7.5
        assert order.paid_amount == Decimal("66.50")   # 84.5 - 10 - 5 - 3
        assert order.coupon_amount == Decimal("5.00")
        assert order.points_amount == Decimal("3.00")
        assert order.discount_amount == Decimal("10.00")

    def test_settle_generates_fee_items(self, test_db):
        """结算生成 5 项费用明细 + 3 项优惠明细 = 8 行"""
        session = test_db["session"]
        order = self._create_order(session, "BE-SET-003")

        fees = {
            "energy_fee": Decimal("32.00"),
            "service_fee": Decimal("20.00"),
            "parking_fee": Decimal("10.00"),
            "occupancy_fee": Decimal("15.00"),
            "reservation_fee": Decimal("7.50"),
            "discount_amount": Decimal("10.00"),
            "coupon_amount": Decimal("5.00"),
            "points_amount": Decimal("3.00"),
        }
        result = settle_order_fees(order, fees, db=session)

        items = session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        # 5 项费用 + 3 项优惠
        assert len(items) == 8
        types = {i.fee_type for i in items}
        assert FeeType.ELECTRICITY in types
        assert FeeType.SERVICE in types
        assert FeeType.PARKING in types
        assert FeeType.OCCUPANCY in types
        assert FeeType.RESERVATION in types
        assert FeeType.DISCOUNT in types
        assert FeeType.COUPON in types
        assert FeeType.POINTS in types

    def test_settle_with_energy_breakdown(self, test_db):
        """带分时电量明细: 电费拆成多条时段明细"""
        session = test_db["session"]
        order = self._create_order(session, "BE-SET-004")

        fees = {
            "energy_fee": Decimal("18.00"),
            "service_fee": Decimal("5.00"),
            "parking_fee": Decimal("0"),
            "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("0"),
            "coupon_amount": Decimal("0"),
            "points_amount": Decimal("0"),
        }
        energy_breakdown = [
            {"period_name": "平段电费", "kwh": Decimal("20"), "price": Decimal("0.6"), "fee": Decimal("12.00"), "unit": "kWh"},
            {"period_name": "谷段电费", "kwh": Decimal("20"), "price": Decimal("0.3"), "fee": Decimal("6.00"), "unit": "kWh"},
        ]
        settle_order_fees(order, fees, db=session, energy_breakdown=energy_breakdown)

        items = session.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == order.id,
            OrderFeeItem.fee_type == FeeType.ELECTRICITY,
        ).all()
        assert len(items) == 2
        names = {i.fee_name for i in items}
        assert "平段电费" in names
        assert "谷段电费" in names

    def test_settle_idempotent(self, test_db):
        """重复结算覆盖旧明细"""
        session = test_db["session"]
        order = self._create_order(session, "BE-SET-005")

        fees_v1 = {
            "energy_fee": Decimal("32.00"), "service_fee": Decimal("20.00"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("0"), "coupon_amount": Decimal("0"),
            "points_amount": Decimal("0"),
        }
        settle_order_fees(order, fees_v1, db=session)

        fees_v2 = {
            "energy_fee": Decimal("18.00"), "service_fee": Decimal("5.00"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("0"), "coupon_amount": Decimal("0"),
            "points_amount": Decimal("0"),
        }
        settle_order_fees(order, fees_v2, db=session)

        items = session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        # v2: 电费 + 服务费 = 2 行(v1 被清除)
        assert len(items) == 2
        session.refresh(order)
        assert order.electricity_fee == Decimal("18.00")
