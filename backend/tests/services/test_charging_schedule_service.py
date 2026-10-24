"""
智能充电调度服务(charging_schedule_service)测试 - 覆盖率补强 ≥70%

被测: app/services/charging_schedule_service.py (283 行)
设计: 用 test_db 真 SQLite 走调度生成/调整全链路(服务深度依赖 ORM:
      add/flush/add_all/commit/refresh + db.get/db.query, 真 db 让 plan.id
      真实生成、refresh 真实回读, 断言最可靠; 符合本仓 fleet_alert_service /
      charging_pricing 同类补覆盖率提交的成熟模式)。
覆盖:
- classify_period / window_period   峰/平/谷归类 + 全小时边界
- generate_schedule                 5 个错误路径 / SOC 优先级排序 /
                                    变压器容量贪心分配 / cap=min(车功率, 单车上限) /
                                    available=0 全 IDLE / SOC 达标不产条目 /
                                    rule_spec 自定义参数 / V2G 峰时放电+非峰待机 /
                                    V2G 阈值边界 / summary 口径 / 持久化
- adjust_schedule                   计划不存在 / 状态不可调 / 条目越界 / 功率为负 /
                                    PLANNED+ACTIVE 可调 / 按 priority 排序返回
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.charging_schedule_service import (
    classify_period,
    window_period,
    generate_schedule,
    adjust_schedule,
)
from app.models.charging_schedule import (
    ChargingSchedulePlan,
    ChargingScheduleEntry,
    ChargingSchedulePlanStatus,
    ChargingEntryMode,
    ChargingPeriodType,
)


ENT = 6001  # 任意企业 ID(SQLite FK 不强制, 无需真实 enterprise 行)

# 固定调度窗口, 小时可控以覆盖峰/平/谷
WIN_PEAK = (datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 1, 13, 0))   # 12 点 = 峰
WIN_FLAT = (datetime(2026, 1, 1, 8, 0), datetime(2026, 1, 1, 9, 0))     # 8 点 = 平
WIN_VALLEY = (datetime(2026, 1, 1, 2, 0), datetime(2026, 1, 1, 3, 0))   # 2 点 = 谷


def _vs(vid, soc, tgt=0.9, pwr=7.0):
    """构造一条车辆状态。"""
    return {"vehicle_id": vid, "current_soc": soc, "target_soc": tgt, "max_power_kw": pwr}


# ═══════════════════════════════════════════════════════════════
# 1. classify_period / window_period
# ═══════════════════════════════════════════════════════════════

class TestClassifyPeriod:
    def test_valley_hours(self):
        for h in [23, 0, 1, 2, 3, 4, 5, 6]:
            assert classify_period(h) == ChargingPeriodType.VALLEY, f"{h} 应为谷"

    def test_peak_hours(self):
        for h in [10, 11, 12, 13, 14, 18, 19, 20]:
            assert classify_period(h) == ChargingPeriodType.PEAK, f"{h} 应为峰"

    def test_flat_hours(self):
        for h in [7, 8, 9, 15, 16, 17, 21, 22]:
            assert classify_period(h) == ChargingPeriodType.FLAT, f"{h} 应为平"

    def test_boundary_transitions(self):
        """峰/平/谷交界小时归类正确。"""
        assert classify_period(6) == ChargingPeriodType.VALLEY   # 谷末
        assert classify_period(7) == ChargingPeriodType.FLAT     # 平始
        assert classify_period(9) == ChargingPeriodType.FLAT     # 平末
        assert classify_period(10) == ChargingPeriodType.PEAK    # 峰始
        assert classify_period(14) == ChargingPeriodType.PEAK    # 峰末
        assert classify_period(15) == ChargingPeriodType.FLAT    # 平始
        assert classify_period(17) == ChargingPeriodType.FLAT    # 平末
        assert classify_period(18) == ChargingPeriodType.PEAK    # 峰始
        assert classify_period(20) == ChargingPeriodType.PEAK    # 峰末
        assert classify_period(21) == ChargingPeriodType.FLAT    # 平始
        assert classify_period(22) == ChargingPeriodType.FLAT    # 平末
        assert classify_period(23) == ChargingPeriodType.VALLEY  # 谷始
        assert classify_period(0) == ChargingPeriodType.VALLEY   # 谷

    def test_window_period_uses_start_hour(self):
        """window_period 按窗口起始小时归类。"""
        assert window_period(datetime(2026, 1, 1, 12, 30)) == ChargingPeriodType.PEAK
        assert window_period(datetime(2026, 1, 1, 2, 15)) == ChargingPeriodType.VALLEY
        assert window_period(datetime(2026, 1, 1, 8, 45)) == ChargingPeriodType.FLAT


# ═══════════════════════════════════════════════════════════════
# 2. generate_schedule — 错误路径
# ═══════════════════════════════════════════════════════════════

class TestGenerateScheduleErrors:
    def test_negative_power_rejected(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], -1.0, *WIN_FLAT)
        assert res == {"error": "可用功率不能为负"}

    def test_empty_vehicle_states_rejected(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [], 10.0, *WIN_FLAT)
        assert res == {"error": "车辆状态列表为空"}

    def test_missing_vehicle_id_rejected(self, test_db):
        """vehicle_states 项缺 vehicle_id(或为 None)拒绝。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT,
            [{"current_soc": 0.2, "target_soc": 0.9, "max_power_kw": 7.0}],
            10.0, *WIN_FLAT,
        )
        assert res == {"error": "vehicle_states 缺少 vehicle_id"}

    def test_none_vehicle_id_rejected(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(None, 0.2)], 10.0, *WIN_FLAT)
        assert res == {"error": "vehicle_states 缺少 vehicle_id"}

    def test_error_path_writes_nothing(self, test_db):
        """错误路径不应持久化任何计划。"""
        db = test_db["session"]
        generate_schedule(db, ENT, [], 10.0, *WIN_FLAT)
        assert db.query(ChargingSchedulePlan).count() == 0


# ═══════════════════════════════════════════════════════════════
# 3. generate_schedule — 充电分配逻辑
# ═══════════════════════════════════════════════════════════════

class TestGenerateScheduleCharging:
    def test_single_vehicle_full_alloc(self, test_db):
        """单车功率充足时按 cap 分配。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        e = res["entries"][0]
        assert e["assigned_power_kw"] == 7.0          # cap=min(7, 7.0)=7
        assert e["charge_mode"] == ChargingEntryMode.CHARGE.value
        assert e["priority"] == 1
        assert e["soc_start"] == 0.2 and e["soc_target"] == 0.9

    def test_soc_priority_ordering(self, test_db):
        """低 SOC 优先(priority 数字越小越优先)。"""
        db = test_db["session"]
        # 乱序给入, 应按 soc 升序排
        states = [_vs(1, 0.5), _vs(2, 0.1), _vs(3, 0.3)]
        res = generate_schedule(db, ENT, states, 100.0, *WIN_FLAT)
        prio = {e["vehicle_id"]: e["priority"] for e in res["entries"]}
        assert prio == {2: 1, 3: 2, 1: 3}   # soc 0.1<0.3<0.5

    def test_transformer_capacity_greedy(self, test_db):
        """功率不足时按优先级贪心, 排后者 IDLE。"""
        db = test_db["session"]
        # soc 升序: 车2(0.1)→车1(0.3)→车3(0.5), 每车 cap=7, 总可用=10
        states = [_vs(1, 0.3), _vs(2, 0.1), _vs(3, 0.5)]
        res = generate_schedule(db, ENT, states, 10.0, *WIN_FLAT)
        by_vid = {e["vehicle_id"]: e for e in res["entries"]}
        assert by_vid[2]["assigned_power_kw"] == 7.0                          # 最优先吃满
        assert by_vid[2]["charge_mode"] == ChargingEntryMode.CHARGE.value
        assert by_vid[1]["assigned_power_kw"] == 3.0                          # 剩 3
        assert by_vid[1]["charge_mode"] == ChargingEntryMode.CHARGE.value
        assert by_vid[3]["assigned_power_kw"] == 0.0                          # 没了 → IDLE
        assert by_vid[3]["charge_mode"] == ChargingEntryMode.IDLE.value
        summ = res["summary"]
        assert summ["allocated_power_kw"] == 10.0
        assert summ["remaining_power_kw"] == 0.0
        assert summ["charging_vehicles"] == 2
        assert summ["idle_vehicles"] == 1

    def test_zero_available_all_idle(self, test_db):
        """available_power=0(非负, 合法)→ 全 IDLE。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2), _vs(2, 0.3)], 0.0, *WIN_FLAT)
        assert all(e["charge_mode"] == ChargingEntryMode.IDLE.value for e in res["entries"])
        assert all(e["assigned_power_kw"] == 0.0 for e in res["entries"])
        assert res["summary"]["allocated_power_kw"] == 0.0
        assert res["summary"]["remaining_power_kw"] == 0.0

    def test_vehicle_power_capped_by_per_vehicle_limit(self, test_db):
        """车 max_power_kw > 单车上限 → cap 取单车上限。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2, pwr=100.0)], 100.0, *WIN_FLAT)
        assert res["entries"][0]["assigned_power_kw"] == 7.0   # 默认 max_power_per_vehicle

    def test_vehicle_power_below_limit_uses_vehicle_power(self, test_db):
        """车 max_power_kw < 单车上限 → cap 取车功率。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2, pwr=3.5)], 100.0, *WIN_FLAT)
        assert res["entries"][0]["assigned_power_kw"] == 3.5

    def test_custom_max_power_per_vehicle(self, test_db):
        """rule_spec.max_power_per_vehicle 覆盖默认。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.2, pwr=100.0)], 100.0, *WIN_FLAT,
            rule_spec={"max_power_per_vehicle": 5.0},
        )
        assert res["entries"][0]["assigned_power_kw"] == 5.0

    def test_soc_already_at_target_no_entry(self, test_db):
        """SOC 已达标且 v2g 关闭 → 不产生条目。"""
        db = test_db["session"]
        # cur=0.95 >= tgt=0.9, v2g 关闭 → 既不充电也不放电
        res = generate_schedule(db, ENT, [_vs(1, 0.95, tgt=0.9)], 10.0, *WIN_FLAT)
        assert res["entries"] == []
        assert res["summary"]["charging_vehicles"] == 0

    def test_default_soc_when_missing(self, test_db):
        """current_soc 缺失默认 0.0, target_soc 缺失默认 rule_spec.target_soc(默认 0.9)。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [{"vehicle_id": 1}], 10.0, *WIN_FLAT)
        e = res["entries"][0]
        assert e["soc_start"] == 0.0
        assert e["soc_target"] == 0.9
        assert e["charge_mode"] == ChargingEntryMode.CHARGE.value

    def test_custom_target_soc_default(self, test_db):
        """rule_spec.target_soc 作为缺省目标 SOC。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [{"vehicle_id": 1}], 10.0, *WIN_FLAT,
            rule_spec={"target_soc": 0.8},
        )
        assert res["entries"][0]["soc_target"] == 0.8


# ═══════════════════════════════════════════════════════════════
# 4. generate_schedule — 时段 & summary 口径
# ═══════════════════════════════════════════════════════════════

class TestGenerateSchedulePeriod:
    def test_valley_preferred_true(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_VALLEY)
        assert res["period_type"] == ChargingPeriodType.VALLEY.value
        assert res["valley_preferred"] is True

    def test_valley_preferred_false_for_peak(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_PEAK)
        assert res["period_type"] == ChargingPeriodType.PEAK.value
        assert res["valley_preferred"] is False

    def test_flat_period(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        assert res["period_type"] == ChargingPeriodType.FLAT.value
        assert res["valley_preferred"] is False

    def test_charging_entry_marks_period_type(self, test_db):
        """充电条目 period_type 标注当前时段。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_VALLEY)
        assert res["entries"][0]["period_type"] == ChargingPeriodType.VALLEY.value


# ═══════════════════════════════════════════════════════════════
# 5. generate_schedule — V2G 反向放电
# ═══════════════════════════════════════════════════════════════

class TestGenerateScheduleV2G:
    def test_v2g_discharge_in_peak(self, test_db):
        """峰时段 + SOC 达阈值 + 无需再充 → 反向放电。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.9, tgt=0.9)], 10.0, *WIN_PEAK,
            rule_spec={"v2g_enabled": True},
        )
        e = res["entries"][0]
        assert e["charge_mode"] == ChargingEntryMode.DISCHARGE.value
        assert e["assigned_power_kw"] == 5.0   # 默认 v2g_discharge_kw
        # priority = 100 + int((1-0.9)*100); 浮点 (1-0.9)*100 = 9.999... → int 截断为 9
        assert e["priority"] == 109
        assert res["summary"]["v2g_discharge_vehicles"] == 1

    def test_v2g_idle_outside_peak(self, test_db):
        """谷时段(非峰)即使满足 V2G 条件也待机。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.9, tgt=0.9)], 10.0, *WIN_VALLEY,
            rule_spec={"v2g_enabled": True},
        )
        e = res["entries"][0]
        assert e["charge_mode"] == ChargingEntryMode.IDLE.value
        assert e["assigned_power_kw"] == 0.0
        assert e["priority"] == 200
        assert res["summary"]["v2g_discharge_vehicles"] == 0

    def test_v2g_threshold_boundary_inclusive(self, test_db):
        """SOC == 阈值(默认 0.80)边界: 含等号 → 可放电。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.80, tgt=0.80)], 10.0, *WIN_PEAK,
            rule_spec={"v2g_enabled": True},
        )
        e = res["entries"][0]
        assert e["charge_mode"] == ChargingEntryMode.DISCHARGE.value
        # priority = 100 + int((1-0.8)*100); 浮点 (1-0.8)*100 = 19.999... → int 截断为 19
        assert e["priority"] == 119

    def test_v2g_below_threshold_falls_to_charge(self, test_db):
        """SOC < 阈值 且 < target → 进入充电候选而非 V2G。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.79, tgt=0.90)], 10.0, *WIN_PEAK,
            rule_spec={"v2g_enabled": True},
        )
        e = res["entries"][0]
        assert e["charge_mode"] == ChargingEntryMode.CHARGE.value
        assert e["priority"] == 1   # 充电优先级从 1 起

    def test_custom_v2g_params(self, test_db):
        """rule_spec 自定义 V2G 阈值/放电功率。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.70, tgt=0.70)], 10.0, *WIN_PEAK,
            rule_spec={
                "v2g_enabled": True,
                "v2g_discharge_threshold": 0.65,
                "v2g_discharge_kw": 4.0,
            },
        )
        e = res["entries"][0]
        assert e["charge_mode"] == ChargingEntryMode.DISCHARGE.value
        assert e["assigned_power_kw"] == 4.0

    def test_v2g_disabled_treats_high_soc_as_noop(self, test_db):
        """v2g 关闭时高 SOC 且达标的车不放电也不充电(不产条目)。"""
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.95, tgt=0.9)], 10.0, *WIN_PEAK,
            rule_spec={"v2g_enabled": False},
        )
        assert res["entries"] == []

    def test_mixed_fleet_charge_and_discharge(self, test_db):
        """混合车队: 低 SOC 充电 + 高 SOC 峰时放电, entries 顺序=充电在前放电在后。"""
        db = test_db["session"]
        states = [
            _vs(10, 0.9, tgt=0.9),   # V2G 候选(峰时放电)
            _vs(20, 0.2, tgt=0.9),   # 充电候选
        ]
        res = generate_schedule(db, ENT, states, 10.0, *WIN_PEAK, rule_spec={"v2g_enabled": True})
        modes = [e["charge_mode"] for e in res["entries"]]
        # 充电候选先(charge_candidates + v2g_candidates 拼接)
        assert modes[0] == ChargingEntryMode.CHARGE.value
        assert modes[1] == ChargingEntryMode.DISCHARGE.value
        summ = res["summary"]
        assert summ["charging_vehicles"] == 1
        assert summ["v2g_discharge_vehicles"] == 1


# ═══════════════════════════════════════════════════════════════
# 6. generate_schedule — 持久化
# ═══════════════════════════════════════════════════════════════

class TestGenerateSchedulePersistence:
    def test_plan_and_entries_persisted(self, test_db):
        """计划与条目真实落库, 可被查询回读。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2), _vs(2, 0.4)], 14.0, *WIN_VALLEY)
        plan_id = res["plan_id"]
        plan = db.query(ChargingSchedulePlan).get(plan_id)
        assert plan is not None
        assert plan.enterprise_id == ENT
        assert plan.status == ChargingSchedulePlanStatus.PLANNED
        assert plan.total_available_power_kw == 14.0
        assert plan.rule_json["period_type"] == ChargingPeriodType.VALLEY.value
        assert plan.rule_json["v2g_enabled"] is False

        entries = (db.query(ChargingScheduleEntry)
                   .filter(ChargingScheduleEntry.plan_id == plan_id)
                   .all())
        assert len(entries) == 2
        assert {e.vehicle_id for e in entries} == {1, 2}
        # entry id 真实生成(非 None)
        assert all(e.id is not None for e in entries)

    def test_returned_entries_carry_real_ids(self, test_db):
        """refresh 后 entries 的 id 是真实主键。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        assert all(isinstance(e["id"], int) for e in res["entries"])

    def test_rule_json_records_max_power(self, test_db):
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.2)], 10.0, *WIN_PEAK,
            rule_spec={"max_power_per_vehicle": 6.5, "v2g_enabled": True, "v2g_discharge_threshold": 0.85},
        )
        plan = db.query(ChargingSchedulePlan).get(res["plan_id"])
        assert plan.rule_json["max_power_per_vehicle"] == 6.5
        assert plan.rule_json["v2g_discharge_threshold"] == 0.85
        assert plan.rule_json["v2g_enabled"] is True

    def test_idle_entry_period_type_null(self, test_db):
        """待机条目 period_type 为 None(充电/放电才标时段)。"""
        db = test_db["session"]
        # available=0 → 充电候选变 IDLE, 其 period_type 应为 None
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 0.0, *WIN_VALLEY)
        assert res["entries"][0]["charge_mode"] == ChargingEntryMode.IDLE.value
        assert res["entries"][0]["period_type"] is None


# ═══════════════════════════════════════════════════════════════
# 7. adjust_schedule
# ═══════════════════════════════════════════════════════════════

class TestAdjustSchedule:
    def test_plan_not_found(self, test_db):
        db = test_db["session"]
        res = adjust_schedule(db, 999999, [{"entry_id": 1, "new_power_kw": 5.0}])
        assert res == {"error": "调度计划 999999 不存在"}

    def test_status_not_adjustable(self, test_db):
        """COMPLETED/CANCELLED 状态不可调。"""
        db = test_db["session"]
        plan = ChargingSchedulePlan(
            enterprise_id=ENT, plan_date=datetime.now(timezone.utc),
            time_window_start=WIN_FLAT[0], time_window_end=WIN_FLAT[1],
            total_available_power_kw=10.0, status=ChargingSchedulePlanStatus.COMPLETED,
            rule_json={},
        )
        db.add(plan)
        db.commit()
        res = adjust_schedule(db, plan.id, [])
        assert res == {"error": f"计划状态 {ChargingSchedulePlanStatus.COMPLETED.value} 不可调整"}

    def test_entry_not_in_plan(self, test_db):
        """条目不属于该计划 → 拒绝。"""
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        res = adjust_schedule(db, gen["plan_id"], [{"entry_id": 888888, "new_power_kw": 5.0}])
        assert res == {"error": f"条目 888888 不属于计划 {gen['plan_id']}"}

    def test_negative_power_rejected(self, test_db):
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        entry_id = gen["entries"][0]["id"]
        res = adjust_schedule(db, gen["plan_id"], [{"entry_id": entry_id, "new_power_kw": -0.1}])
        assert res == {"error": "功率不能为负"}

    def test_adjust_planned_status_ok(self, test_db):
        """PLANNED 状态可调, 功率落库 + round。"""
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        entry_id = gen["entries"][0]["id"]
        res = adjust_schedule(db, gen["plan_id"], [{"entry_id": entry_id, "new_power_kw": 3.456}])
        assert res["plan_id"] == gen["plan_id"]
        assert res["status"] == ChargingSchedulePlanStatus.PLANNED.value
        assert res["entries"][0]["assigned_power_kw"] == 3.46   # round(3.456, 2)
        # 落库验证
        ent = db.query(ChargingScheduleEntry).get(entry_id)
        assert ent.assigned_power_kw == 3.46

    def test_adjust_active_status_ok(self, test_db):
        """ACTIVE 状态也可调。"""
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        plan = db.query(ChargingSchedulePlan).get(gen["plan_id"])
        plan.status = ChargingSchedulePlanStatus.ACTIVE
        db.commit()
        entry_id = gen["entries"][0]["id"]
        res = adjust_schedule(db, gen["plan_id"], [{"entry_id": entry_id, "new_power_kw": 6.0}])
        assert res["status"] == ChargingSchedulePlanStatus.ACTIVE.value
        assert res["entries"][0]["assigned_power_kw"] == 6.0

    def test_result_ordered_by_priority(self, test_db):
        """返回条目按 priority 升序。"""
        db = test_db["session"]
        # soc 升序 → priority 1,2,3
        gen = generate_schedule(db, ENT, [_vs(1, 0.5), _vs(2, 0.1), _vs(3, 0.3)], 100.0, *WIN_FLAT)
        ids = [e["id"] for e in gen["entries"]]
        res = adjust_schedule(
            db, gen["plan_id"],
            [{"entry_id": i, "new_power_kw": 2.0} for i in ids],
        )
        priorities = [e["priority"] for e in res["entries"]]
        assert priorities == sorted(priorities)
        # priority 1 的车是 soc 最低的车 2
        assert res["entries"][0]["vehicle_id"] == 2


# ═══════════════════════════════════════════════════════════════
# 8. 输入校验边界 (card:6bd0daa9)
#    SOC 范围 / 时间窗口 / max_power_per_vehicle / adjust 总功率
# ═══════════════════════════════════════════════════════════════

class TestInputValidation:
    """generate/adjust 输入校验边界: 非法输入返回 {"error": ...} 且不落库。"""

    # ── SOC 范围: current_soc / target_soc 拒绝负值或 >1 ──
    @pytest.mark.parametrize("soc", [-0.1, 1.5])
    def test_current_soc_out_of_range_rejected(self, test_db, soc):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, soc, tgt=0.9)], 10.0, *WIN_FLAT)
        assert res == {"error": "SOC必须在0-1范围"}

    @pytest.mark.parametrize("soc", [-0.1, 1.5])
    def test_target_soc_out_of_range_rejected(self, test_db, soc):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2, tgt=soc)], 10.0, *WIN_FLAT)
        assert res == {"error": "SOC必须在0-1范围"}

    def test_soc_boundary_zero_and_one_accepted(self, test_db):
        """边界(含等号): SOC=0 与 SOC=1 均合法, 不被 SOC 校验拒绝。"""
        db = test_db["session"]
        res0 = generate_schedule(db, ENT, [_vs(1, 0.0, tgt=0.9)], 10.0, *WIN_FLAT)
        assert "error" not in res0
        res1 = generate_schedule(db, ENT, [_vs(1, 1.0, tgt=1.0)], 10.0, *WIN_FLAT)
        assert "error" not in res1

    # ── 时间窗口: end <= start 拒绝 ──
    def test_time_window_end_before_start_rejected(self, test_db):
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, WIN_FLAT[1], WIN_FLAT[0])
        assert res == {"error": "结束时间必须晚于开始时间"}

    def test_time_window_equal_rejected(self, test_db):
        """end == start 也拒绝(<=)。"""
        db = test_db["session"]
        res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, WIN_FLAT[0], WIN_FLAT[0])
        assert res == {"error": "结束时间必须晚于开始时间"}

    # ── max_power_per_vehicle: <= 0 拒绝 ──
    @pytest.mark.parametrize("mpv", [0, -1])
    def test_max_power_per_vehicle_non_positive_rejected(self, test_db, mpv):
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT,
            rule_spec={"max_power_per_vehicle": mpv},
        )
        assert res == {"error": "单车最大功率必须大于0"}

    def test_validation_error_writes_nothing(self, test_db):
        """校验失败不应持久化任何计划。"""
        db = test_db["session"]
        generate_schedule(db, ENT, [_vs(1, 1.5)], 10.0, *WIN_FLAT)
        assert db.query(ChargingSchedulePlan).count() == 0

    # ── adjust 总功率: 调整后超过 plan.total_available_power_kw 拒绝 ──
    def test_adjust_total_power_exceeds_available_rejected(self, test_db):
        db = test_db["session"]
        # available 10.0, 单车 cap 7.0 → 1 条目 7.0; 调到 15.0 超总量
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        entry_id = gen["entries"][0]["id"]
        res = adjust_schedule(db, gen["plan_id"], [{"entry_id": entry_id, "new_power_kw": 15.0}])
        assert "error" in res

    def test_adjust_total_power_at_limit_accepted(self, test_db):
        """总功率恰等于上限(边界)应放行 — 用严格 >, 不用 >=。"""
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        entry_id = gen["entries"][0]["id"]
        res = adjust_schedule(db, gen["plan_id"], [{"entry_id": entry_id, "new_power_kw": 10.0}])
        assert "error" not in res


# ═══════════════════════════════════════════════════════════════
# 9. DB 异常处理 (card:5d4cca66)
#    flush/commit 抛异常 → rollback + logger.exception + 降级 error
# ═══════════════════════════════════════════════════════════════

class TestExceptionHandling:
    """DB 异常被兜底: 不向上抛, rollback 并返回 {"error": "调度服务暂时不可用"}。"""

    def test_generate_flush_exception_returns_error(self, test_db):
        db = test_db["session"]
        with patch.object(db, "flush", side_effect=RuntimeError("DB connection lost")), \
             patch.object(db, "rollback", wraps=db.rollback) as rollback_spy, \
             patch("app.services.charging_schedule_service.logger.exception") as log_exc:
            res = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        assert res == {"error": "调度服务暂时不可用"}
        rollback_spy.assert_called_once()
        log_exc.assert_called_once()
        # rollback 撤销 add(plan) → 无计划落库
        assert db.query(ChargingSchedulePlan).count() == 0

    def test_adjust_commit_exception_returns_error(self, test_db):
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        entry_id = gen["entries"][0]["id"]
        with patch.object(db, "commit", side_effect=RuntimeError("DB write failed")), \
             patch.object(db, "rollback", wraps=db.rollback) as rollback_spy, \
             patch("app.services.charging_schedule_service.logger.exception") as log_exc:
            res = adjust_schedule(db, gen["plan_id"], [{"entry_id": entry_id, "new_power_kw": 5.0}])
        assert res == {"error": "调度服务暂时不可用"}
        rollback_spy.assert_called_once()
        log_exc.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# 10. 防御性加固 (卡3f02df33)
#    classify_period/window_period 输入边界 + 计算阶段脏数据隔离
#    参考 billing_engine(68d4bea22) 加固模式: 异常不冒泡, 降级 + 记日志
# ═══════════════════════════════════════════════════════════════

class TestDefensiveHardening:
    """防御性加固: 输入边界校验 + 计算/转换异常隔离。

    核心不变量: 非法输入(hour 越界/None、脏数据字符串)不向上抛 500,
    要么返回安全降级值(纯函数), 要么返回 {"error": ...} 并 rollback 记日志(写函数)。
    """

    # ── 1. classify_period 输入边界 ──
    def test_classify_period_none_raises_value_error(self):
        """None 不是合法小时 → 显式 ValueError, 不抛 AttributeError。

        纯函数对非法输入应给明确异常类型(便于调用方捕获), 而非 AttributeError 这种实现细节。
        """
        with pytest.raises(ValueError):
            classify_period(None)

    @pytest.mark.parametrize("bad_hour", [-1, 24, 25, 100])
    def test_classify_period_out_of_range_raises(self, bad_hour):
        """小时越界(< 0 或 > 23)→ ValueError, 不静默归 FLAT。"""
        with pytest.raises(ValueError):
            classify_period(bad_hour)

    @pytest.mark.parametrize("bad_hour", [-1.5, "abc", 12.5, [3]])
    def test_classify_period_non_int_raises(self, bad_hour):
        """非 int(字符串/列表/小数)→ ValueError。"""
        with pytest.raises(ValueError):
            classify_period(bad_hour)

    @pytest.mark.parametrize("hour", [0, 6, 23])
    def test_classify_period_legal_hour_still_works(self, hour):
        """合法边界小时(0/6/23)加固后行为不变, 仍归 VALLEY。"""
        assert classify_period(hour) == ChargingPeriodType.VALLEY

    # ── 2. window_period None/非法 datetime 防护 ──
    def test_window_period_none_raises_value_error(self):
        """time_window_start=None → ValueError(非 AttributeError)。"""
        with pytest.raises(ValueError):
            window_period(None)

    def test_window_period_legal_datetime_unchanged(self):
        """合法 datetime 加固后归类不变。"""
        assert window_period(datetime(2026, 1, 1, 12, 0)) == ChargingPeriodType.PEAK

    # ── 3. generate_schedule 计算阶段脏数据隔离 ──
    def test_generate_schedule_soc_non_numeric_isolated(self, test_db):
        """current_soc 为不可转 float 的字符串 → 不崩 500, 降级 error + rollback + 记日志。

        此前 float('abc') 在计算循环抛 ValueError, 绕过持久化 try/except(位于其后),
        直接冒泡成未捕获异常。加固后计算阶段异常也应被兜底。
        """
        db = test_db["session"]
        states = [{"vehicle_id": 1, "current_soc": "abc", "target_soc": 0.9, "max_power_kw": 7.0}]
        with patch("app.services.charging_schedule_service.logger.exception") as log_exc:
            res = generate_schedule(db, ENT, states, 10.0, *WIN_FLAT)
        assert "error" in res
        log_exc.assert_called_once()
        # 脏数据不应落库任何计划
        assert db.query(ChargingSchedulePlan).count() == 0

    def test_generate_schedule_max_power_non_numeric_isolated(self, test_db):
        """max_power_kw 为不可转 float 的脏值(对象)→ 计算阶段异常被兜底, 降级 error, 不冒泡。

        注: float('NaN') 会被 Python 接受(返回 nan), 故用 object() 触发真实转换异常。
        """
        db = test_db["session"]
        states = [{"vehicle_id": 1, "current_soc": 0.2, "target_soc": 0.9, "max_power_kw": object()}]
        with patch("app.services.charging_schedule_service.logger.exception") as log_exc:
            res = generate_schedule(db, ENT, states, 10.0, *WIN_FLAT)
        assert "error" in res
        log_exc.assert_called_once()

    def test_generate_schedule_calc_exception_rolls_back(self, test_db):
        """计算阶段异常也触发 rollback, 不留半成品(无 plan 落库)。"""
        db = test_db["session"]
        states = [{"vehicle_id": 1, "current_soc": object(), "target_soc": 0.9, "max_power_kw": 7.0}]
        with patch.object(db, "rollback", wraps=db.rollback) as rollback_spy:
            res = generate_schedule(db, ENT, states, 10.0, *WIN_FLAT)
        assert "error" in res
        rollback_spy.assert_called_once()
        assert db.query(ChargingSchedulePlan).count() == 0

    # ── 4. generate_schedule rule_spec 脏参数隔离 ──
    def test_generate_schedule_dirty_rule_spec_isolated(self, test_db):
        """rule_spec.max_power_per_vehicle 非数字 → 不崩, 降级 error。

        float('xyz') 此前在参数解析阶段(line 92)抛 ValueError, 无任何防护。
        """
        db = test_db["session"]
        res = generate_schedule(
            db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT,
            rule_spec={"max_power_per_vehicle": "not-a-number"},
        )
        assert "error" in res
        assert db.query(ChargingSchedulePlan).count() == 0

    # ── 5. adjust_schedule 转换/查询异常防护 ──
    def test_adjust_negative_power_string_isolated(self, test_db):
        """new_power_kw 为脏字符串 → 不崩, 降级 error + rollback + 记日志。"""
        db = test_db["session"]
        gen = generate_schedule(db, ENT, [_vs(1, 0.2)], 10.0, *WIN_FLAT)
        entry_id = gen["entries"][0]["id"]
        with patch.object(db, "rollback", wraps=db.rollback) as rollback_spy, \
             patch("app.services.charging_schedule_service.logger.exception") as log_exc:
            res = adjust_schedule(db, gen["plan_id"],
                                  [{"entry_id": entry_id, "new_power_kw": "oops"}])
        assert res == {"error": "调度服务暂时不可用"}
        rollback_spy.assert_called_once()
        log_exc.assert_called_once()

    def test_adjust_get_plan_exception_isolated(self, test_db):
        """db.get(plan) 查询抛异常 → 兜底降级 error, 不冒泡成 500。"""
        db = test_db["session"]
        with patch.object(db, "get", side_effect=RuntimeError("connection lost")), \
             patch("app.services.charging_schedule_service.logger.exception") as log_exc:
            res = adjust_schedule(db, 999, [])
        assert res == {"error": "调度服务暂时不可用"}
        log_exc.assert_called_once()
