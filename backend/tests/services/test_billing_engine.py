"""
Phase41 计费引擎(billing_engine)测试 - 覆盖全部 11 个公开/内部函数

被测: app/services/billing_engine.py (纯计算函数 + settle_order_fees ORM 写入)
设计: 纯函数直接断言; settle_order_fees 用 test_db fixture 走真实 SQLite。
覆盖边界: 跨午夜时段/跨时段/单时段/零电量/负数/阶梯/封顶/夜间/实收不低于0/幂等。
"""
from datetime import datetime, date, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError

from app.services.billing_engine import (
    _q,
    _nonneg,
    _to_amount,
    _slot_window_on_date,
    _overlap_minutes,
    compute_tou_energy_fee,
    compute_service_fee_multi,
    _split_day_night,
    compute_parking_fee_full,
    compute_occupancy_fee_full,
    compute_reservation_fee_full,
    compute_order_fees,
    settle_order_fees,
)


# ═══════════════════════════════════════════════════════════════
# 1. 量化助手 _q / _nonneg
# ═══════════════════════════════════════════════════════════════
class TestQuantHelpers:
    """Decimal 量化助手"""

    def test_q_int(self):
        assert _q(0) == Decimal("0.00")
        assert _q(2) == Decimal("2.00")

    def test_q_str_quantize_two_places(self):
        # 3.14159 -> 2 位 = 3.14
        assert _q("3.14159") == Decimal("3.14")

    def test_q_float(self):
        assert _q(2.5) == Decimal("2.50")

    def test_q_decimal_passthrough(self):
        assert _q(Decimal("10")) == Decimal("10.00")

    def test_q_returns_decimal_type(self):
        assert isinstance(_q("1"), Decimal)

    def test_nonneg_positive(self):
        assert _nonneg("5.5") == Decimal("5.50")
        assert _nonneg(3) == Decimal("3.00")

    def test_nonneg_zero(self):
        # v > 0 为 False -> 归 0.00
        assert _nonneg(0) == Decimal("0.00")

    def test_nonneg_negative_to_zero(self):
        assert _nonneg(-5) == Decimal("0.00")
        assert _nonneg("-3.2") == Decimal("0.00")

    def test_nonneg_quantizes(self):
        assert _nonneg("1.234") == Decimal("1.23")


# ═══════════════════════════════════════════════════════════════
# 2. 时段窗口 + 重叠分钟
# ═══════════════════════════════════════════════════════════════
class TestSlotWindow:
    """_slot_window_on_date: 三种窗口形态"""

    d = date(2026, 6, 24)

    def test_normal_window_start_lt_end(self):
        s, e = _slot_window_on_date(self.d, time(10, 0), time(12, 0))
        assert s == datetime(2026, 6, 24, 10, 0)
        assert e == datetime(2026, 6, 24, 12, 0)

    def test_cross_midnight_start_gt_end(self):
        # 23:00 -> 次日 07:00
        s, e = _slot_window_on_date(self.d, time(23, 0), time(7, 0))
        assert s == datetime(2026, 6, 24, 23, 0)
        assert e == datetime(2026, 6, 25, 7, 0)

    def test_full_day_start_eq_end(self):
        # start == end 视为全天窗口 -> 次日 start
        s, e = _slot_window_on_date(self.d, time(12, 0), time(12, 0))
        assert s == datetime(2026, 6, 24, 12, 0)
        assert e == datetime(2026, 6, 25, 12, 0)


class TestOverlapMinutes:
    """_overlap_minutes: 重叠/边界/不重叠"""

    def test_full_overlap(self):
        a = datetime(2026, 6, 24, 10, 0)
        b = datetime(2026, 6, 24, 12, 0)
        assert _overlap_minutes(a, b, a, b) == 120.0

    def test_partial_overlap(self):
        # [10:00,12:00] vs [11:00,13:00] -> 60min
        assert _overlap_minutes(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
            datetime(2026, 6, 24, 11, 0), datetime(2026, 6, 24, 13, 0),
        ) == 60.0

    def test_touching_boundary_zero(self):
        # [10:00,12:00] vs [12:00,14:00] -> 端点相接, 重叠 0
        assert _overlap_minutes(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
            datetime(2026, 6, 24, 12, 0), datetime(2026, 6, 24, 14, 0),
        ) == 0.0

    def test_no_overlap(self):
        assert _overlap_minutes(
            datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 9, 0),
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
        ) == 0.0

    def test_cross_midnight_overlap(self):
        # 充电 [23:00, 次日02:00] vs 夜窗 [22:00, 次日06:00] -> 180min
        assert _overlap_minutes(
            datetime(2026, 6, 24, 23, 0), datetime(2026, 6, 25, 2, 0),
            datetime(2026, 6, 24, 22, 0), datetime(2026, 6, 25, 6, 0),
        ) == 180.0


# ═══════════════════════════════════════════════════════════════
# 3. 尖峰平谷时段计费(核心)
# ═══════════════════════════════════════════════════════════════
class TestTouEnergyFee:
    """compute_tou_energy_fee: 单时段/跨时段/跨午夜/防御"""

    # 两个相邻时段: 尖峰 10-12 @1.0, 平段 12-14 @0.6
    SLOTS = [
        {"slot_id": "s_peak", "period_type": "peak", "start_time": time(10, 0), "end_time": time(12, 0)},
        {"slot_id": "s_flat", "period_type": "flat", "start_time": time(12, 0), "end_time": time(14, 0)},
    ]
    PRICES = {"s_peak": Decimal("1.0"), "s_flat": Decimal("0.6")}

    def test_single_period(self):
        """单时段: 充电 10:00-11:00, 10kWh -> 全落在尖峰"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 11, 0),
            Decimal("10"), self.SLOTS, self.PRICES,
        )
        assert r["total_fee"] == Decimal("10.00")
        assert r["total_energy"] == Decimal("10.00")
        assert set(r["period_breakdown"].keys()) == {"peak"}
        assert r["period_breakdown"]["peak"]["fee"] == Decimal("10.00")
        assert r["period_breakdown"]["peak"]["minutes"] == 60.0
        assert r["energy_by_period"]["peak"] == Decimal("10.00")

    def test_cross_period(self):
        """跨时段: 充电 10:00-14:00, 20kWh -> 各占一半"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 14, 0),
            Decimal("20"), self.SLOTS, self.PRICES,
        )
        # 尖峰: 10kWh * 1.0 = 10.00 ; 平段: 10kWh * 0.6 = 6.00
        assert r["period_breakdown"]["peak"]["fee"] == Decimal("10.00")
        assert r["period_breakdown"]["flat"]["fee"] == Decimal("6.00")
        assert r["total_fee"] == Decimal("16.00")
        assert r["total_energy"] == Decimal("20.00")

    def test_cross_midnight_period(self):
        """跨午夜时段(slot 本身跨午夜): 22:00-06:00 夜段, 充电 23:00-次日02:00"""
        slots = [{"slot_id": "s_valley", "period_type": "valley",
                  "start_time": time(22, 0), "end_time": time(6, 0)}]
        prices = {"s_valley": Decimal("0.4")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 23, 0), datetime(2026, 6, 25, 2, 0),
            Decimal("6"), slots, prices,
        )
        # 180min 全在夜段, 6kWh * 0.4 = 2.40
        assert r["total_fee"] == Decimal("2.40")
        assert r["total_energy"] == Decimal("6.00")
        assert r["period_breakdown"]["valley"]["minutes"] == 180.0

    def test_slot_outside_charge_window_skipped(self):
        """时段与充电区间无重叠 -> 该 period 不出现"""
        slots = [{"slot_id": "s_night", "period_type": "night",
                  "start_time": time(22, 0), "end_time": time(6, 0)}]
        prices = {"s_night": Decimal("0.3")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 12, 0), datetime(2026, 6, 24, 14, 0),
            Decimal("10"), slots, prices,
        )
        assert r["period_breakdown"] == {}
        assert r["total_fee"] == Decimal("0.00")

    def test_zero_kwh(self):
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
            Decimal("0"), self.SLOTS, self.PRICES,
        )
        assert r["total_fee"] == Decimal("0.00")
        assert r["total_energy"] == Decimal("0.00")
        assert r["period_breakdown"] == {}

    def test_negative_kwh(self):
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
            Decimal("-5"), self.SLOTS, self.PRICES,
        )
        assert r["total_fee"] == Decimal("0.00")

    def test_empty_slots(self):
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 12, 0),
            Decimal("10"), [], self.PRICES,
        )
        assert r["total_fee"] == Decimal("0.00")
        assert r["period_breakdown"] == {}

    def test_zero_duration(self):
        """起止相同 -> total_minutes<=0 -> 全零"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 10, 0),
            Decimal("10"), self.SLOTS, self.PRICES,
        )
        assert r["total_fee"] == Decimal("0.00")

    def test_reversed_time(self):
        """end < start -> total_minutes<0 -> 全零"""
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 12, 0), datetime(2026, 6, 24, 10, 0),
            Decimal("10"), self.SLOTS, self.PRICES,
        )
        assert r["total_fee"] == Decimal("0.00")

    def test_missing_price_raises(self):
        """slot 覆盖充电区间却缺价格 -> 配置错误, 抛 ValueError(不再默认 0 免费充电)

        旧实现静默返 0 会让该时段免费充电(漏收), d17a43287 改为显式报错;
        调用方 _load_tou_energy 有 try/except 兜底走默认电价。
        """
        with pytest.raises(ValueError, match="Missing price for slot"):
            compute_tou_energy_fee(
                datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 11, 0),
                Decimal("10"), self.SLOTS, {},  # peak slot 覆盖 10-11 却缺价格
            )

    def test_double_same_period_window_merges(self):
        """同 period_type 双时段窗(双峰 08-12 + 18-21)累加, 不覆盖。

        回归 4671e993: 旧实现 period_breakdown[period_type]= 覆盖写, 同类型多窗只剩
        最后一窗, energy_by_period/明细金额之和 < total_energy/total_fee,
        发票明细与 electricity_fee 不符。配三时段(双峰夹平段)使覆盖完整 → total_energy==total_kwh。
        """
        slots = [
            {"slot_id": "s_pk1", "period_type": "peak", "start_time": time(8, 0), "end_time": time(12, 0)},
            {"slot_id": "s_flat", "period_type": "flat", "start_time": time(12, 0), "end_time": time(18, 0)},
            {"slot_id": "s_pk2", "period_type": "peak", "start_time": time(18, 0), "end_time": time(21, 0)},
        ]
        prices = {"s_pk1": Decimal("1.0"), "s_flat": Decimal("0.6"), "s_pk2": Decimal("1.0")}
        # 充电 08:00-21:00 共 780min; peak1=240, flat=360, peak2=180, 全覆盖(coverage=1)
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 21, 0),
            Decimal("130"), slots, prices,
        )
        # 双峰合并为一行 peak + 一行 flat(覆盖 bug 下 peak 仅剩第二窗, energy 丢失)
        assert set(r["period_breakdown"].keys()) == {"peak", "flat"}
        # energy_by_period["peak"] == 两窗之和: 130*240/780=40 + 130*180/780=30 = 70
        assert r["energy_by_period"]["peak"] == Decimal("70.00")
        assert r["energy_by_period"]["flat"] == Decimal("60.00")
        # minutes 累加: peak 240+180=420; flat 360
        assert r["period_breakdown"]["peak"]["minutes"] == 420.0
        assert r["period_breakdown"]["flat"]["minutes"] == 360.0
        # 全覆盖 → total_energy == total_kwh(电量守恒)
        assert r["total_energy"] == Decimal("130.00")
        # 明细 fee 之和 == total_fee(修复后; 旧覆盖 bug 下 peak.fee=30, 明细和=66<106)
        # peak 40*1.0+30*1.0=70 ; flat 60*0.6=36 ; 合计 106
        bd_fee_sum = sum((v["fee"] for v in r["period_breakdown"].values()), Decimal("0"))
        assert bd_fee_sum == r["total_fee"] == Decimal("106.00")
        assert r["period_breakdown"]["peak"]["fee"] == Decimal("70.00")

    def test_double_same_period_window_weighted_price(self):
        """同 period_type 双窗不同价: fee 累加, price 取加权平均(总fee/总energy, 量化6位)。"""
        slots = [
            {"slot_id": "s_pk1", "period_type": "peak", "start_time": time(8, 0), "end_time": time(12, 0)},
            {"slot_id": "s_pk2", "period_type": "peak", "start_time": time(18, 0), "end_time": time(21, 0)},
        ]
        prices = {"s_pk1": Decimal("1.0"), "s_pk2": Decimal("2.0")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 21, 0),
            Decimal("130"), slots, prices,
        )
        peak = r["period_breakdown"]["peak"]
        # energy 40+30=70; fee 40*1.0 + 30*2.0 = 100.00
        assert peak["energy"] == Decimal("70.00")
        assert peak["fee"] == Decimal("100.00")
        assert r["total_fee"] == Decimal("100.00")
        # 加权单价 = 100/70 ≈ 1.428571, 严格介于两窗单价之间
        assert Decimal("1.0") < peak["price"] < Decimal("2.0")


# ═══════════════════════════════════════════════════════════════
# 4. 服务费多模式
# ═══════════════════════════════════════════════════════════════
class TestServiceFeeMulti:
    def test_fixed(self):
        # fixed 元/次, 与电量无关
        assert compute_service_fee_multi(Decimal("50"), "fixed", Decimal("2.5")) == Decimal("2.50")
        assert compute_service_fee_multi(Decimal("0"), "fixed", Decimal("2.5")) == Decimal("2.50")

    def test_percent(self):
        # percent 元/kWh
        assert compute_service_fee_multi(Decimal("50"), "percent", Decimal("0.5")) == Decimal("25.00")

    def test_percent_fractional(self):
        assert compute_service_fee_multi(Decimal("33.33"), "percent", Decimal("0.5286")) == Decimal("17.62")

    def test_percent_zero_rate(self):
        assert compute_service_fee_multi(Decimal("100"), "percent", Decimal("0")) == Decimal("0.00")

    def test_unknown_fee_type(self):
        # 未知 fee_type(配置错误) -> 抛 ValueError, 不再静默返 0(d17a43287)
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("50"), "other", Decimal("1"))

    def test_empty_fee_type(self):
        # 空 fee_type 同理抛 ValueError
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("50"), "", Decimal("1"))


# ═══════════════════════════════════════════════════════════════
# 5. 夜间判断 + 日夜拆分
# ═══════════════════════════════════════════════════════════════
class TestNightHelpers:
    def test_split_all_day(self):
        """12:00 起 120min 全白天"""
        day, night = _split_day_night(datetime(2026, 6, 24, 12, 0), 120, time(22, 0), time(6, 0))
        assert day == 120
        assert night == 0

    def test_split_all_night(self):
        """23:00 起 120min 全夜间(跨午夜)"""
        day, night = _split_day_night(datetime(2026, 6, 24, 23, 0), 120, time(22, 0), time(6, 0))
        assert day == 0
        assert night == 120

    def test_split_mixed(self):
        """21:00 起 180min: 21:00-22:00 白天(60), 22:00-00:00 夜间(120)"""
        day, night = _split_day_night(datetime(2026, 6, 24, 21, 0), 180, time(22, 0), time(6, 0))
        assert day == 60
        assert night == 120

    def test_split_zero(self):
        day, night = _split_day_night(datetime(2026, 6, 24, 12, 0), 0, time(22, 0), time(6, 0))
        assert day == 0
        assert night == 0


# ═══════════════════════════════════════════════════════════════
# 6. 停车费完整规则
# ═══════════════════════════════════════════════════════════════
class TestParkingFeeFull:
    def test_within_free_minutes(self):
        """免费时长内 -> 全零"""
        rule = {"free_minutes": 60, "hourly_rate": Decimal("5.0")}
        r = compute_parking_fee_full(30, rule)
        assert r["total"] == Decimal("0.00")
        assert r["capped"] is False
        assert r["day_minutes"] == 0

    def test_basic_hourly(self):
        """基础小时计费: 120min, 5元/h, 无免费 -> 10.00"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0")}
        r = compute_parking_fee_full(120, rule)
        assert r["day_fee"] == Decimal("10.00")
        assert r["total"] == Decimal("10.00")
        assert r["day_minutes"] == 120
        assert r["night_minutes"] == 0

    def test_daily_cap(self):
        """单日封顶: 120min 5元/h=10 > cap 8 -> 8.00, capped"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0"), "daily_cap": Decimal("8.00")}
        r = compute_parking_fee_full(120, rule)
        assert r["subtotal"] == Decimal("10.00")
        assert r["total"] == Decimal("8.00")
        assert r["capped"] is True

    def test_below_cap_not_capped(self):
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0"), "daily_cap": Decimal("20.00")}
        r = compute_parking_fee_full(120, rule)
        assert r["total"] == Decimal("10.00")
        assert r["capped"] is False

    def test_night_rate_all_night(self):
        """夜间费率: 23:00 起 120min 全夜间, 夜费 2元/h -> 4.00"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0"),
                "enable_night_rate": True, "night_rate": Decimal("2.0"),
                "night_start": time(22, 0), "night_end": time(6, 0)}
        r = compute_parking_fee_full(120, rule, start_time=datetime(2026, 6, 24, 23, 0))
        assert r["night_minutes"] == 120
        assert r["day_minutes"] == 0
        assert r["night_fee"] == Decimal("4.00")
        assert r["day_fee"] == Decimal("0.00")
        assert r["total"] == Decimal("4.00")

    def test_night_rate_mixed(self):
        """日夜混合: 21:00 起 180min, 日 60min@5 + 夜 120min@2 = 5+4=9.00"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0"),
                "enable_night_rate": True, "night_rate": Decimal("2.0"),
                "night_start": time(22, 0), "night_end": time(6, 0)}
        r = compute_parking_fee_full(180, rule, start_time=datetime(2026, 6, 24, 21, 0))
        assert r["day_minutes"] == 60
        assert r["night_minutes"] == 120
        assert r["day_fee"] == Decimal("5.00")
        assert r["night_fee"] == Decimal("4.00")
        assert r["subtotal"] == Decimal("9.00")

    def test_charging_exempt(self):
        """充电期间免除: 停 180min, 免除 120min, 计费 60min@5 = 5.00"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0")}
        r = compute_parking_fee_full(180, rule, charging_exempt_minutes=120)
        assert r["day_minutes"] == 60
        assert r["total"] == Decimal("5.00")

    def test_enable_night_without_start_time(self):
        """开了夜间但没给 start_time -> 走 else 全算白天"""
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0"),
                "enable_night_rate": True, "night_rate": Decimal("2.0"),
                "night_start": time(22, 0), "night_end": time(6, 0)}
        r = compute_parking_fee_full(120, rule)  # 无 start_time
        assert r["day_minutes"] == 120
        assert r["night_minutes"] == 0
        assert r["total"] == Decimal("10.00")

    def test_free_plus_exempt_exceeds_duration(self):
        """免费+免除超过总时长 -> billable=0 全零"""
        rule = {"free_minutes": 60, "hourly_rate": Decimal("5.0")}
        r = compute_parking_fee_full(100, rule, charging_exempt_minutes=60)
        assert r["total"] == Decimal("0.00")

    def test_zero_parking_minutes(self):
        rule = {"free_minutes": 0, "hourly_rate": Decimal("5.0")}
        r = compute_parking_fee_full(0, rule)
        assert r["total"] == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 7. 占桩费
# ═══════════════════════════════════════════════════════════════
class TestOccupancyFeeFull:
    def test_within_grace(self):
        """宽限期内 -> 0"""
        rule = {"grace_minutes": 30, "rate_per_minute": Decimal("0.5")}
        assert compute_occupancy_fee_full(20, rule) == Decimal("0.00")

    def test_basic_after_grace(self):
        """宽限 30, 占桩 90 -> 计费 60min@0.5 = 30.00"""
        rule = {"grace_minutes": 30, "rate_per_minute": Decimal("0.5")}
        assert compute_occupancy_fee_full(90, rule) == Decimal("30.00")

    def test_capped(self):
        """单次封顶: 200min@0.5=100 > cap 50 -> 50.00"""
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.5"), "max_fee": Decimal("50")}
        assert compute_occupancy_fee_full(200, rule) == Decimal("50.00")

    def test_no_max_fee(self):
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.5")}
        assert compute_occupancy_fee_full(60, rule) == Decimal("30.00")

    def test_zero_minutes(self):
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.5")}
        assert compute_occupancy_fee_full(0, rule) == Decimal("0.00")

    def test_below_cap(self):
        rule = {"grace_minutes": 0, "rate_per_minute": Decimal("0.5"), "max_fee": Decimal("100")}
        assert compute_occupancy_fee_full(60, rule) == Decimal("30.00")

    def test_missing_keys_default_zero(self):
        """空规则 -> 全 0"""
        assert compute_occupancy_fee_full(120, {}) == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 8. 预约费
# ═══════════════════════════════════════════════════════════════
class TestReservationFeeFull:
    def test_normal(self):
        rule = {"fee_amount": Decimal("10"), "deposit_amount": Decimal("100"), "no_show_penalty": Decimal("5")}
        r = compute_reservation_fee_full(rule, no_show=False)
        assert r["fee"] == Decimal("10.00")
        assert r["deposit"] == Decimal("100.00")
        assert r["no_show_penalty"] == Decimal("5.00")
        assert r["total"] == Decimal("10.00")  # 不含 deposit, 不含罚款

    def test_no_show(self):
        """爽约: total = fee + penalty"""
        rule = {"fee_amount": Decimal("10"), "deposit_amount": Decimal("100"), "no_show_penalty": Decimal("5")}
        r = compute_reservation_fee_full(rule, no_show=True)
        assert r["total"] == Decimal("15.00")

    def test_empty_rule(self):
        r = compute_reservation_fee_full({}, no_show=True)
        assert r["fee"] == Decimal("0.00")
        assert r["deposit"] == Decimal("0.00")
        assert r["no_show_penalty"] == Decimal("0.00")
        assert r["total"] == Decimal("0.00")

    def test_deposit_not_in_total(self):
        """deposit 始终不计入实收(可退还)"""
        rule = {"fee_amount": Decimal("0"), "deposit_amount": Decimal("200"), "no_show_penalty": Decimal("0")}
        r = compute_reservation_fee_full(rule, no_show=False)
        assert r["total"] == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════
# 9. 综合费用
# ═══════════════════════════════════════════════════════════════
class TestOrderFees:
    def test_full_order_with_discounts(self):
        """总=97.50, 折扣10+券5+积分2.5 -> 实收 80.00"""
        r = compute_order_fees(
            energy_fee=Decimal("40"), service_fee=Decimal("25"), parking_fee=Decimal("10"),
            occupancy_fee=Decimal("15"), reservation_fee=Decimal("7.5"),
            discount_amount=Decimal("10"), coupon_amount=Decimal("5"), points_amount=Decimal("2.5"),
        )
        assert r["total_amount"] == Decimal("97.50")
        assert r["discount_amount"] == Decimal("10.00")
        assert r["coupon_amount"] == Decimal("5.00")
        assert r["points_amount"] == Decimal("2.50")
        assert r["paid_amount"] == Decimal("80.00")

    def test_negative_discounts_normalized_to_zero(self):
        """负优惠归零(不允许为负)"""
        r = compute_order_fees(
            energy_fee=Decimal("10"), service_fee=Decimal("0"), parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"), reservation_fee=Decimal("0"),
            discount_amount=Decimal("-5"), coupon_amount=Decimal("-3"), points_amount=Decimal("-2"),
        )
        assert r["total_amount"] == Decimal("10.00")
        assert r["discount_amount"] == Decimal("0.00")
        assert r["paid_amount"] == Decimal("10.00")

    def test_paid_floored_at_zero(self):
        """优惠超过总额 -> 实收不低于 0"""
        r = compute_order_fees(
            energy_fee=Decimal("10"), service_fee=Decimal("5"), parking_fee=Decimal("0"),
            occupancy_fee=Decimal("0"), reservation_fee=Decimal("0"),
            discount_amount=Decimal("100"),
        )
        assert r["total_amount"] == Decimal("15.00")
        assert r["paid_amount"] == Decimal("0.00")

    def test_all_zero(self):
        r = compute_order_fees(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
        )
        assert r["total_amount"] == Decimal("0.00")
        assert r["paid_amount"] == Decimal("0.00")

    def test_discount_coupon_points_order_independent(self):
        """三项扣减顺序无关, 总额一致"""
        base = dict(energy_fee=Decimal("100"), service_fee=Decimal("0"),
                    parking_fee=Decimal("0"), occupancy_fee=Decimal("0"), reservation_fee=Decimal("0"))
        r = compute_order_fees(**base, discount_amount=Decimal("10"), coupon_amount=Decimal("20"), points_amount=Decimal("5"))
        assert r["paid_amount"] == Decimal("65.00")

    def test_decimal_precision(self):
        """金额量化 2 位"""
        r = compute_order_fees(
            Decimal("1.005"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
        )
        # Decimal(str("1.005")) 量化 ROUND_HALF_EVEN -> 1.00
        assert r["total_amount"] == Decimal("1.00")


# ═══════════════════════════════════════════════════════════════
# 10. settle_order_fees (ORM 写入)
# ═══════════════════════════════════════════════════════════════
class TestSettleOrderFees:
    """settle_order_fees: 写 ChargingOrder 字段 + OrderFeeItem 明细"""

    @staticmethod
    def _make_order(session, order_no="TEST_BILLING_1"):
        from app.models.charging_order import ChargingOrder
        order = ChargingOrder(
            order_no=order_no, station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("20.00"),
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    def test_settle_with_breakdown(self, test_db):
        """带分时明细: 电费多行 + 其余费用 + 优惠三项"""
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session)

        fees = {
            "energy_fee": Decimal("16"), "service_fee": Decimal("25"),
            "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
            "reservation_fee": Decimal("7"),
            "discount_amount": Decimal("3"), "coupon_amount": Decimal("2"), "points_amount": Decimal("1"),
        }
        breakdown = [
            {"period_name": "尖峰", "kwh": 10, "price": Decimal("1.0"), "fee": Decimal("10"), "unit": "kWh"},
            {"period_name": "平", "kwh": 10, "price": Decimal("0.6"), "fee": Decimal("6"), "unit": "kWh"},
        ]
        result = settle_order_fees(order, fees, session, energy_breakdown=breakdown)

        # total = 16+25+10+5+7 = 63; paid = 63-3-2-1 = 57
        assert result["total_amount"] == 63.0
        assert result["paid_amount"] == 57.0
        assert result["order_id"] == order.id
        # 明细: 尖峰电费 + 平电费 + 服务费 + 停车费 + 占桩费 + 预约费 + 折扣 + 券 + 积分 = 9
        assert len(result["fee_items"]) == 9
        assert result["fee_items"][0]["fee_type"] == "electricity"
        assert result["fee_items"][0]["fee_name"] == "尖峰"

        # 订单字段写入
        assert order.electricity_fee == Decimal("16.00")
        assert order.service_fee == Decimal("25.00")
        assert order.parking_fee == Decimal("10.00")
        assert order.occupancy_fee == Decimal("5.00")
        assert order.idle_penalty == Decimal("5.00")  # 兼容旧字段
        assert order.reservation_fee == Decimal("7.00")
        assert order.total_amount == Decimal("63.00")
        assert order.discount_amount == Decimal("3.00")
        assert order.coupon_amount == Decimal("2.00")
        assert order.points_amount == Decimal("1.00")
        assert order.paid_amount == Decimal("57.00")

        # 数据库实际落库
        rows = session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        assert len(rows) == 9

    def test_settle_without_breakdown(self, test_db):
        """无 breakdown: 电费汇总单行(quantity=1, unit=元)"""
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session, "TEST_BILLING_2")

        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("0"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}
        result = settle_order_fees(order, fees, session)

        # 仅 1 条电费汇总行
        assert len(result["fee_items"]) == 1
        assert result["fee_items"][0]["fee_name"] == "电费"
        assert result["total_amount"] == 16.0
        assert result["paid_amount"] == 16.0
        rows = session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).all()
        assert len(rows) == 1
        assert rows[0].quantity == Decimal("1")
        assert rows[0].unit == "元"

    def test_settle_idempotent(self, test_db):
        """重复结算: 旧明细先清除再重写, 行数不变"""
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session, "TEST_BILLING_3")

        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("25"),
                "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
                "reservation_fee": Decimal("7")}
        breakdown = [
            {"period_name": "尖峰", "kwh": 10, "price": Decimal("1.0"), "fee": Decimal("10"), "unit": "kWh"},
            {"period_name": "平", "kwh": 10, "price": Decimal("0.6"), "fee": Decimal("6"), "unit": "kWh"},
        ]
        settle_order_fees(order, fees, session, energy_breakdown=breakdown)
        # 灌入一些"旧明细"模拟历史脏数据
        session.add_all([
            OrderFeeItem(order_id=order.id, fee_type=OrderFeeItem.__table__.c.fee_type.type.enum_class.ELECTRICITY,
                         fee_name="脏数据", quantity=Decimal("1"), unit_price=Decimal("999"), amount=Decimal("999"), unit="元"),
        ])
        session.commit()
        assert session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).count() == 7  # 6 + 1 脏

        # 再次结算 -> 清除全部旧明细(含脏数据), 重写 6 行
        result = settle_order_fees(order, fees, session, energy_breakdown=breakdown)
        assert len(result["fee_items"]) == 6
        assert session.query(OrderFeeItem).filter(OrderFeeItem.order_id == order.id).count() == 6

    def test_settle_zero_energy_no_electricity_item(self, test_db):
        """energy_fee=0 且无 breakdown -> 不生成电费明细行"""
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session, "TEST_BILLING_4")

        fees = {"energy_fee": Decimal("0"), "service_fee": Decimal("5"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}
        result = settle_order_fees(order, fees, session)
        # 仅服务费 1 行, 无电费行
        assert len(result["fee_items"]) == 1
        assert result["fee_items"][0]["fee_type"] == "service"
        assert order.electricity_fee == Decimal("0.00")
        assert order.service_fee == Decimal("5.00")

    def test_settle_paid_floored_at_zero(self, test_db):
        """优惠超过总额 -> 实收触底 0(覆盖 paid<0 分支)"""
        session = test_db["session"]
        order = self._make_order(session, "TEST_BILLING_6")

        fees = {"energy_fee": Decimal("10"), "service_fee": Decimal("0"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0"), "discount_amount": Decimal("100")}
        result = settle_order_fees(order, fees, session)
        assert result["total_amount"] == 10.0
        assert result["paid_amount"] == 0.0
        assert order.paid_amount == Decimal("0.00")

    def test_settle_zero_fee_segment_skipped(self, test_db):
        """breakdown 中 fee=0 的时段被跳过"""
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session, "TEST_BILLING_5")

        fees = {"energy_fee": Decimal("10"), "service_fee": Decimal("0"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}
        breakdown = [
            {"period_name": "尖峰", "kwh": 10, "price": Decimal("1.0"), "fee": Decimal("10"), "unit": "kWh"},
            {"period_name": "深谷", "kwh": 0, "price": Decimal("0.2"), "fee": Decimal("0"), "unit": "kWh"},  # 0 跳过
        ]
        result = settle_order_fees(order, fees, session, energy_breakdown=breakdown)
        # 仅 1 行电费(尖峰), 深谷被跳过
        elec = [i for i in result["fee_items"] if i["fee_type"] == "electricity"]
        assert len(elec) == 1
        assert elec[0]["fee_name"] == "尖峰"

    def test_settle_amounts_no_float_precision_tail(self, test_db):
        """[卡0595f21d] 序列化边界精度不变量: 返回的 6 项金额 float 不得带长尾。

        settle_order_fees 返回 dict 时把 Decimal 转 float(序列化边界)。本测试锁定不变量:
        每个金额 v 必须满足 v == round(v, 2)。fees 取 float 算术下会塌成长尾的组合
        (0.10+0.20 → 0.30000000000000004), 以最大化回归保护——一旦上游 _q/_nonneg 量化
        或序列化层的 round 兜底被移除/旁路, 此处即 RED。
        """
        session = test_db["session"]
        order = self._make_order(session, "TEST_BILLING_PREC")

        fees = {
            "energy_fee": Decimal("0.10"), "service_fee": Decimal("0.20"),
            "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
            "reservation_fee": Decimal("0"),
            "discount_amount": Decimal("0.01"), "coupon_amount": Decimal("0.01"),
            "points_amount": Decimal("0.01"),
        }
        result = settle_order_fees(order, fees, session)

        def _no_tail(v):
            return v == round(v, 2)

        # total 0.30 / paid 0.27 / 优惠各 0.01 + 每条 fee_item amount: 均无长浮点尾
        assert _no_tail(result["total_amount"])
        assert _no_tail(result["discount_amount"])
        assert _no_tail(result["coupon_amount"])
        assert _no_tail(result["points_amount"])
        assert _no_tail(result["paid_amount"])
        for item in result["fee_items"]:
            assert _no_tail(item["amount"]), item

        # 精确到 2 位的值, 且不等于 float 算术泄漏形式
        assert result["total_amount"] == 0.30
        assert result["paid_amount"] == 0.27
        assert result["total_amount"] != 0.1 + 0.2  # 0.30000000000000004 != 0.30


# ═══════════════════════════════════════════════════════════════
# 11. settle_order_fees 异常安全(卡 ba5c1f64)
# ═══════════════════════════════════════════════════════════════
class TestSettleExceptionSafety:
    """settle_order_fees / 助手函数异常路径加固。

    核心不变量: 单条坏明细不传播、不污染 total/paid; db 写异常 rollback+reraise;
    助手函数边界(falsy/负数/超大数/非法输入)行为可预期。
    """

    @staticmethod
    def _make_order(session, order_no="TEST_BILLING_EXC"):
        from app.models.charging_order import ChargingOrder
        order = ChargingOrder(
            order_no=order_no, station_id=1, device_id=1, user_id=1,
            charged_kwh=Decimal("20.00"),
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    @staticmethod
    def _good_seg(period_name="尖峰", fee=Decimal("10")):
        return {"period_name": period_name, "kwh": 10,
                "price": Decimal("1.0"), "fee": fee, "unit": "kWh"}

    class _PoisonedSeg:
        """自定义毒明细: 控制 .get() 抛出指定异常类型, 可靠覆盖 4 类隔离路径。

        真实坏 dict 数据多触发 decimal.InvalidOperation(非 TypeError/ValueError),
        难以稳定枚举异常类型; 用自定义 .get 精确抛出目标异常是隔离容错测试的标准手法。
        """

        def __init__(self, exc_factory):
            self._exc_factory = exc_factory

        def get(self, key, default=None):
            raise self._exc_factory()

    # ---- 1. breakdown 单条毒记录隔离(4 类异常) ----
    @pytest.mark.parametrize("exc_cls", [TypeError, ValueError, KeyError, AttributeError])
    def test_breakdown_single_poison_record_isolated(self, test_db, exc_cls):
        """坏明细(4 类异常之一)被跳过, 不影响前后正常明细处理。"""
        from app.models.order_fee_item import OrderFeeItem
        session = test_db["session"]
        order = self._make_order(session)

        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("0"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}
        breakdown = [
            self._good_seg("尖峰", Decimal("10")),
            self._PoisonedSeg(exc_cls),  # 毒明细 → 跳过
            self._good_seg("平", Decimal("6")),
        ]
        # 不抛异常
        result = settle_order_fees(order, fees, session, energy_breakdown=breakdown)

        elec = [i for i in result["fee_items"] if i["fee_type"] == "electricity"]
        assert len(elec) == 2  # 毒被隔离, 仅 2 条好明细
        assert {i["fee_name"] for i in elec} == {"尖峰", "平"}

    def test_breakdown_all_poison_records_fallback(self, test_db):
        """全部 breakdown 毒记录: 不抛, 电费明细为空(但不影响 order.electricity_fee 字段)。

        energy_fee 由独立 fees["energy_fee"] 字段写入 order, 不依赖逐条 seg 累加,
        故即使明细全坏, 订单电费字段与 total 仍正确。
        """
        session = test_db["session"]
        order = self._make_order(session)

        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("25"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}
        breakdown = [self._PoisonedSeg(TypeError), self._PoisonedSeg(ValueError)]
        result = settle_order_fees(order, fees, session, energy_breakdown=breakdown)

        elec = [i for i in result["fee_items"] if i["fee_type"] == "electricity"]
        assert elec == []  # 电费明细全被隔离
        # 但 order 字段与 total 由 energy_fee 独立汇总, 不受明细影响
        assert order.electricity_fee == Decimal("16.00")
        assert result["total_amount"] == 41.0  # 16+25

    def test_poison_breakdown_does_not_pollute_total(self, test_db):
        """毒明细不污染 total/paid: total 始终 = 五项费用之和。"""
        session = test_db["session"]
        order = self._make_order(session)

        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("25"),
                "parking_fee": Decimal("10"), "occupancy_fee": Decimal("5"),
                "reservation_fee": Decimal("7"),
                "discount_amount": Decimal("3")}
        breakdown = [self._good_seg("尖峰", Decimal("10")), self._PoisonedSeg(KeyError)]
        result = settle_order_fees(order, fees, session, energy_breakdown=breakdown)

        # total=16+25+10+5+7=63; paid=63-3=60, 与明细条数无关
        assert result["total_amount"] == 63.0
        assert result["paid_amount"] == 60.0
        assert order.total_amount == Decimal("63.00")
        assert order.paid_amount == Decimal("60.00")

    # ---- 2. db 写异常 rollback + reraise ----
    def test_db_flush_exception_rolls_back_and_reraises(self, test_db):
        """db.flush 抛异常 → rollback 被调用 + 原异常上抛(不留半成品)。"""
        session = test_db["session"]
        order = self._make_order(session)
        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("25"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}

        original_flush = session.flush

        def _boom(*a, **kw):
            raise OperationalError("statement", {}, Exception("flush fail"))

        session.flush = _boom
        rollback_called = {"v": False}
        original_rollback = session.rollback

        def _spy_rollback(*a, **kw):
            rollback_called["v"] = True

        session.rollback = _spy_rollback
        try:
            with pytest.raises(OperationalError):
                settle_order_fees(order, fees, session)
            assert rollback_called["v"] is True
        finally:
            session.flush = original_flush
            session.rollback = original_rollback

    def test_db_query_exception_rolls_back_and_reraises(self, test_db):
        """清除旧明细的 db.query(...).delete() 抛异常 → rollback + reraise。

        query 失败发生在 try 体内最前部, 必须先 rollback 再传播, 不静默吞。
        """
        session = test_db["session"]
        order = self._make_order(session)
        fees = {"energy_fee": Decimal("16"), "service_fee": Decimal("0"),
                "parking_fee": Decimal("0"), "occupancy_fee": Decimal("0"),
                "reservation_fee": Decimal("0")}

        original_query = session.query
        rollback_called = {"v": False}
        original_rollback = session.rollback

        def _spy_rollback(*a, **kw):
            rollback_called["v"] = True

        class _BoomQuery:
            def filter(self, *a, **kw):
                return self

            def delete(self, *a, **kw):
                raise OperationalError("statement", {}, Exception("query fail"))

        def _boom_query(*a, **kw):
            return _BoomQuery()

        session.query = _boom_query
        session.rollback = _spy_rollback
        try:
            with pytest.raises(OperationalError):
                settle_order_fees(order, fees, session)
            assert rollback_called["v"] is True
        finally:
            session.query = original_query
            session.rollback = original_rollback

    # ---- 3. _to_amount 边界 ----
    def test_to_amount_none_returns_zero(self):
        assert _to_amount(None) == 0.0

    def test_to_amount_empty_string_returns_zero(self):
        assert _to_amount("") == 0.0

    def test_to_amount_negative_preserved(self):
        # 负数金额(优惠抵扣行)是 truthy, round 后保留负值, 序列化边界不抹零
        assert _to_amount(Decimal("-3.5")) == -3.5

    def test_to_amount_huge_number(self):
        assert _to_amount(Decimal("999999999999.99")) == 999999999999.99

    # ---- 4. _q 边界 ----
    def test_q_none_raises(self):
        # None 不可转 Decimal: Decimal(str(None))="None" → InvalidOperation
        with pytest.raises(Exception):
            _q(None)

    def test_q_scientific_notation_string(self):
        # "1e2" → Decimal("1E+2") → 量化 2 位 = 100.00
        assert _q("1e2") == Decimal("100.00")

    # ---- 5. _nonneg 边界 ----
    def test_nonneg_zero_is_zero(self):
        assert _nonneg(0) == Decimal("0.00")

    def test_nonneg_negative_is_zero(self):
        assert _nonneg(Decimal("-99.9")) == Decimal("0.00")

    def test_nonneg_positive_preserved(self):
        assert _nonneg(Decimal("12.34")) == Decimal("12.34")

    # ---- 6. compute_tou_energy_fee 零时长返回空结构 ----
    def test_tou_zero_duration_returns_empty_structure(self):
        """total_minutes=0(起止相同)→ 返回空 period_breakdown + 零费用(任务卡 #9)。"""
        slots = [{"slot_id": "s", "period_type": "peak",
                  "start_time": time(10, 0), "end_time": time(12, 0)}]
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 10, 0), datetime(2026, 6, 24, 10, 0),
            Decimal("10"), slots, {"s": Decimal("1.0")},
        )
        assert r["period_breakdown"] == {}
        assert r["energy_by_period"] == {}
        assert r["total_fee"] == Decimal("0.00")
        assert r["total_energy"] == Decimal("0.00")

    # ---- 7. compute_service_fee_multi 非法 fee_type ----
    def test_service_fee_invalid_type_raises(self):
        """fee_type 非法值(配置错误)→ 抛 ValueError, 不静默返 0(任务卡 #10)。"""
        with pytest.raises(ValueError, match="Unknown fee_type"):
            compute_service_fee_multi(Decimal("50"), "invalid_mode", Decimal("1"))
