"""
billing_engine 覆盖率补缺测试 (卡 eb184b4f)

现状: tests/services/test_billing_engine.py (1013行) + test_billing_engine_hardening.py (340行)
已覆盖 billing_engine.py 98% 语句(135 测试全绿)。本文件只补剩余 5 行真实缺口
(coverage 报告 Missing: 138, 140, 234, 369-373) + 任务卡点名的契约中现有测试未触及的分支:

缺口映射:
- L138/L140: compute_tou_energy_fee aware datetime 抹平 tzinfo (naive 化)
- L234:      时段重叠 → raise ValueError("Time slots overlap ...")
- L369-373:  停车费 night_start==night_end 误配置 → 降级白天费率

补充契约(任务卡点名, 现有测试仅测正面例):
- coverage < 1.0 (时段未完全覆盖) → 不抛错, total_energy < total_kwh, coverage 标记 < 1

注: 不重复已有 135 测试覆盖的逻辑, 仅锁死未覆盖分支, 推 statement coverage → 100%。
"""
import sys
sys.path.insert(0, ".")

from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.billing_engine import (
    compute_tou_energy_fee,
    compute_parking_fee_full,
)


# ═══════════════════════════════════════════════════════════════
# 缺口 L138/L140: aware datetime 抹平 tzinfo
# ═══════════════════════════════════════════════════════════════
class TestTouAwareDatetimeNaivized:
    """aware datetime 入参应被抹平为 naive 再做时段比较(否则 aware vs naive 抛 TypeError)。"""

    def test_aware_inputs_stripped_and_computed(self):
        tz = timezone(timedelta(hours=8))
        start = datetime(2026, 6, 24, 8, 0, tzinfo=tz)
        end = datetime(2026, 6, 24, 10, 0, tzinfo=tz)
        slots = [
            {"slot_id": "a", "period_type": "peak",
             "start_time": time(8, 0), "end_time": time(10, 0)},
        ]
        prices = {"a": Decimal("1.0")}
        # 若未抹平 tzinfo, _overlap_minutes 内 max/min 比较 aware/naive 会 TypeError
        r = compute_tou_energy_fee(start, end, Decimal("10"), slots, prices)
        assert r["total_energy"] == Decimal("10.00")
        assert r["total_fee"] == Decimal("10.00")

    def test_only_end_aware_stripped(self):
        """end aware / start naive 混合也应能计算 (L140 单独命中)。"""
        end = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        start = datetime(2026, 6, 24, 10, 0)  # naive
        slots = [
            {"slot_id": "a", "period_type": "p",
             "start_time": time(10, 0), "end_time": time(12, 0)},
        ]
        r = compute_tou_energy_fee(start, end, Decimal("4"), slots, {"a": Decimal("0.5")})
        assert r["total_fee"] == Decimal("2.00")


# ═══════════════════════════════════════════════════════════════
# 缺口 L234: 时段重叠 → raise ValueError
# ═══════════════════════════════════════════════════════════════
class TestTouOverlapRaises:
    """total_overlap > 充电总时长(时段配置重叠) → 显式 raise, 不静默多收费。"""

    def test_overlapping_slots_raise(self):
        # 充电 8-12 (240min); slot a=8-12(240min) + slot b=9-11(120min, 与 a 重叠)
        # total_overlap = 240 + 120 = 360 > 240 → raise
        slots = [
            {"slot_id": "a", "period_type": "peak",
             "start_time": time(8, 0), "end_time": time(12, 0)},
            {"slot_id": "b", "period_type": "flat",
             "start_time": time(9, 0), "end_time": time(11, 0)},
        ]
        prices = {"a": Decimal("1.0"), "b": Decimal("0.6")}
        with pytest.raises(ValueError, match="Time slots overlap"):
            compute_tou_energy_fee(
                datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 12, 0),
                Decimal("10"), slots, prices,
            )

    def test_boundary_equal_overlap_does_not_raise(self):
        """相邻时段端点相切(overlap 之和恰好 == 充电时长) 不应 raise(<=阈值合法)。"""
        slots = [
            {"slot_id": "a", "period_type": "peak",
             "start_time": time(8, 0), "end_time": time(10, 0)},
            {"slot_id": "b", "period_type": "flat",
             "start_time": time(10, 0), "end_time": time(12, 0)},
        ]
        prices = {"a": Decimal("1.0"), "b": Decimal("0.6")}
        r = compute_tou_energy_fee(
            datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 12, 0),
            Decimal("10"), slots, prices,
        )
        # 恰好全覆盖, 端点左闭右开不重叠, 不 raise
        assert r["coverage"] == 1.0
        assert r["total_energy"] == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════
# 任务卡点名补缺: coverage < 1.0 (未完全覆盖) → 不抛错, 记 warning, total_energy < total_kwh
# ═══════════════════════════════════════════════════════════════
class TestTouCoverageGap:
    """时段配置未完全覆盖充电区间(配置缺口) → 不抛错, 未覆盖部分电量被排除。"""

    def test_partial_coverage_no_raise(self, caplog):
        # 充电 8-14 (360min); 仅配置 8-12 时段(240min), 12-14 无配置 → coverage=2/3
        slots = [
            {"slot_id": "a", "period_type": "peak",
             "start_time": time(8, 0), "end_time": time(12, 0)},
        ]
        prices = {"a": Decimal("1.0")}
        import logging
        with caplog.at_level(logging.WARNING, logger="app.services.billing_engine"):
            r = compute_tou_energy_fee(
                datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 14, 0),
                Decimal("30"), slots, prices,
            )
        # 不抛错
        assert "coverage" in r
        # coverage = 240/360 ≈ 0.667
        assert r["coverage"] < 1.0
        assert abs(r["coverage"] - (240 / 360)) < 1e-9
        # 未覆盖部分电量被排除: total_energy = 30 * 240/360 = 20 < 30
        assert r["total_energy"] == Decimal("20.00")
        assert r["total_energy"] < Decimal("30.00")
        # 记 warning (运维补全配置的信号)
        assert any("覆盖缺口" in rec.getMessage() for rec in caplog.records)

    def test_full_coverage_no_warning(self, caplog):
        """完整覆盖时不记 coverage 缺口 warning。"""
        slots = [
            {"slot_id": "a", "period_type": "p",
             "start_time": time(8, 0), "end_time": time(12, 0)},
        ]
        prices = {"a": Decimal("1.0")}
        import logging
        with caplog.at_level(logging.WARNING, logger="app.services.billing_engine"):
            r = compute_tou_energy_fee(
                datetime(2026, 6, 24, 8, 0), datetime(2026, 6, 24, 12, 0),
                Decimal("10"), slots, prices,
            )
        assert r["coverage"] == 1.0
        assert not any("覆盖缺口" in rec.getMessage() for rec in caplog.records)


# ═══════════════════════════════════════════════════════════════
# 缺口 L369-373: night_start==night_end 误配置 → 降级白天费率
# ═══════════════════════════════════════════════════════════════
class TestParkingNightStartEqualsEndDegrade:
    """night_start==night_end 被 _slot_window_on_date 视为全天夜间窗(必为误配置),
    应降级为白天费率计费, 而非用低夜间费率压低停车费。"""

    def test_equal_night_window_degrades_to_day(self, caplog):
        rule = {
            "free_minutes": 0,
            "hourly_rate": Decimal("6"),
            "enable_night_rate": True,
            "night_rate": Decimal("1"),      # 远低于白天, 若误判全天夜间会少收
            "night_start": time(22, 0),
            "night_end": time(22, 0),         # == start → 误配置
        }
        import logging
        with caplog.at_level(logging.WARNING, logger="app.services.billing_engine"):
            r = compute_parking_fee_full(
                120, rule, start_time=datetime(2026, 6, 24, 23, 0),
            )
        # 全部按白天费率: 120min * 6/60 = 12.00; 若误判夜间则 = 120*1/60 = 2.00
        assert r["day_minutes"] == 120
        assert r["night_minutes"] == 0
        assert r["day_fee"] == Decimal("12.00")
        assert r["night_fee"] == Decimal("0.00")
        assert r["total"] == Decimal("12.00")
        # 记 warning 提示运维修正配置
        assert any("night_start==night_end" in rec.getMessage() for rec in caplog.records)

    def test_distinct_night_window_not_degraded(self):
        """正常夜间窗(start != end)走分摊, 不降级。"""
        rule = {
            "free_minutes": 0,
            "hourly_rate": Decimal("6"),
            "enable_night_rate": True,
            "night_rate": Decimal("3"),
            "night_start": time(22, 0),
            "night_end": time(6, 0),   # 跨午夜正常窗
        }
        # 23:00 起 120min → 全程在 22-06 夜间窗
        r = compute_parking_fee_full(
            120, rule, start_time=datetime(2026, 6, 24, 23, 0),
        )
        assert r["night_minutes"] == 120
        assert r["day_minutes"] == 0
        assert r["night_fee"] == Decimal("6.00")  # 120 * 3/60
        assert r["day_fee"] == Decimal("0.00")
