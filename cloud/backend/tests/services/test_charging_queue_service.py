# -*- coding: utf-8 -*-
"""
充电队列排序服务测试 - 覆盖率 ≥70%

被测: app/services/charging_queue_service.py
  (纯计算函数 _parse_criteria / _get_field_value / compute_sort_score / sort_queue
   + DB 注入函数 get_active_rule / recalculate_priorities)

设计: 纯函数直接断言 (含边界/非法输入); DB 函数走 test_db 真实 SQLite。
本 service 全部接受 db 参数注入, 无模块级 SessionLocal 按值绑定坑。

覆盖:
- _parse_criteria     None/空/JSON字符串(合法+非法)/非list/项验证(缺字段+weight<=0+
                      非法direction+非dict跳过+默认weight/direction)/全非法回退默认
- _get_field_value    priority/arrival_time(datetime/None/数字)/required_energy(双名)/
                      target_soc/current_soc/未知字段
- compute_sort_score  asc/desc/混合加权/空criteria兜底(不除零)
- sort_queue          空列表/单元素/多字段排序/优先级压倒/稳定性/自定义desc
- get_active_rule     station级优先/enterprise级/global级/全无None/disable过滤/无station_id
- recalculate_priorities  排序+estimated_wait_minutes递增/空队列/仅WAITING状态
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.charging_queue_service import (
    _parse_criteria,
    _get_field_value,
    compute_sort_score,
    sort_queue,
    get_active_rule,
    recalculate_priorities,
    DEFAULT_PRIORITY_CRITERIA,
)
from app.models.charging_queue import (
    ChargingQueue,
    ChargingQueueRule,
    ChargingQueueStatus,
)


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def _entry(**kw):
    """构造 ChargingQueue-like (MagicMock spec) 用于纯函数排序计算。"""
    e = MagicMock(spec=ChargingQueue)
    e.priority = kw.get("priority", 100)
    e.arrival_time = kw.get("arrival_time", datetime(2026, 8, 2, 10, 0))
    e.required_energy_kwh = kw.get("required_energy_kwh", 0.0)
    e.target_soc = kw.get("target_soc", 0.8)
    e.current_soc = kw.get("current_soc", 0.0)
    return e


def _cq(db, **kw):
    """构造并 add 一个真实 ChargingQueue 行 (默认 waiting)。"""
    q = ChargingQueue(
        station_id=kw.get("station_id", 1),
        vehicle_id=kw.get("vehicle_id", 100),
        enterprise_id=kw.get("enterprise_id", 0),
        priority=kw.get("priority", 100),
        arrival_time=kw.get("arrival_time", datetime(2026, 8, 2, 10, 0)),
        required_energy_kwh=kw.get("required_energy_kwh", 10.0),
        target_soc=kw.get("target_soc", 0.8),
        current_soc=kw.get("current_soc", 0.2),
        status=kw.get("status", ChargingQueueStatus.WAITING.value),
    )
    db.add(q)
    return q


def _rule(db, **kw):
    rule = ChargingQueueRule(
        enterprise_id=kw.get("enterprise_id", 0),
        station_id=kw.get("station_id", None),
        rule_name=kw.get("rule_name", "R"),
        priority_criteria=kw.get("priority_criteria", []),
        enable=kw.get("enable", True),
    )
    db.add(rule)
    return rule


# ═══════════════════════════════════════════════════════════════
# _parse_criteria
# ═══════════════════════════════════════════════════════════════

class TestParseCriteria:

    def test_none_returns_default(self):
        assert _parse_criteria(None) == DEFAULT_PRIORITY_CRITERIA

    def test_empty_list_returns_default(self):
        assert _parse_criteria([]) == DEFAULT_PRIORITY_CRITERIA

    def test_empty_string_returns_default(self):
        assert _parse_criteria("") == DEFAULT_PRIORITY_CRITERIA

    def test_invalid_json_string_returns_default(self):
        assert _parse_criteria("{not json") == DEFAULT_PRIORITY_CRITERIA

    def test_non_list_returns_default(self):
        assert _parse_criteria({"field": "priority"}) == DEFAULT_PRIORITY_CRITERIA
        assert _parse_criteria(42) == DEFAULT_PRIORITY_CRITERIA

    def test_valid_json_string_parsed(self):
        raw = '[{"field": "priority", "weight": 10, "direction": "asc"}]'
        assert _parse_criteria(raw) == [
            {"field": "priority", "weight": 10.0, "direction": "asc"}
        ]

    def test_dict_items_kept(self):
        result = _parse_criteria([{"field": "priority", "weight": 5, "direction": "desc"}])
        assert result == [{"field": "priority", "weight": 5.0, "direction": "desc"}]

    def test_non_dict_item_skipped(self):
        result = _parse_criteria([{"field": "priority", "weight": 5}, "junk", 3])
        assert result == [{"field": "priority", "weight": 5.0, "direction": "asc"}]

    def test_missing_field_skipped(self):
        # field 缺省 "" -> if field 为 False -> 跳过 -> 全空回退默认
        assert _parse_criteria([{"weight": 5}]) == DEFAULT_PRIORITY_CRITERIA

    def test_weight_le_zero_skipped(self):
        assert _parse_criteria([{"field": "priority", "weight": 0}]) == DEFAULT_PRIORITY_CRITERIA

    def test_invalid_direction_skipped(self):
        result = _parse_criteria(
            [{"field": "priority", "weight": 5, "direction": "sideways"}]
        )
        assert result == DEFAULT_PRIORITY_CRITERIA

    def test_defaults_weight_and_direction(self):
        # 缺 weight -> 1.0; 缺 direction -> asc
        assert _parse_criteria([{"field": "priority"}]) == [
            {"field": "priority", "weight": 1.0, "direction": "asc"}
        ]

    def test_weight_string_coerced_to_float(self):
        result = _parse_criteria([{"field": "priority", "weight": "8"}])
        assert result[0]["weight"] == 8.0

    def test_returns_copy_not_reference(self):
        # 返回 list(...) 副本, 不会污染模块常量
        r1 = _parse_criteria(None)
        r1.append({"field": "x", "weight": 1, "direction": "asc"})
        assert _parse_criteria(None) == DEFAULT_PRIORITY_CRITERIA

    def test_invalid_weight_string_should_fallback_safely(self):
        # 已修复: weight 非数字字符串不再抛 ValueError, 回退默认
        assert _parse_criteria([{"field": "priority", "weight": "abc"}]) == DEFAULT_PRIORITY_CRITERIA


# ═══════════════════════════════════════════════════════════════
# _get_field_value
# ═══════════════════════════════════════════════════════════════

class TestGetFieldValue:

    def test_priority_with_value(self):
        assert _get_field_value(_entry(priority=5), "priority") == 5.0

    def test_priority_none_defaults_100(self):
        assert _get_field_value(_entry(priority=None), "priority") == 100.0

    def test_arrival_time_datetime(self):
        dt = datetime(2026, 8, 2, 10, 0)
        assert _get_field_value(_entry(arrival_time=dt), "arrival_time") == dt.timestamp() / 60.0

    def test_arrival_time_none_defaults_now(self):
        # None -> datetime.now(timezone.utc) epoch 分钟, 必为正
        assert _get_field_value(_entry(arrival_time=None), "arrival_time") > 0

    def test_arrival_time_numeric(self):
        # 非 datetime 的数字 -> float / 60
        assert _get_field_value(_entry(arrival_time=1200), "arrival_time") == 20.0

    def test_required_energy(self):
        assert _get_field_value(_entry(required_energy_kwh=50), "required_energy") == 50.0

    def test_required_energy_kwh_alias(self):
        assert _get_field_value(_entry(required_energy_kwh=50), "required_energy_kwh") == 50.0

    def test_required_energy_none(self):
        assert _get_field_value(_entry(required_energy_kwh=None), "required_energy") == 0.0

    def test_target_soc_with_value(self):
        assert _get_field_value(_entry(target_soc=0.5), "target_soc") == 0.5

    def test_target_soc_none_defaults_08(self):
        assert _get_field_value(_entry(target_soc=None), "target_soc") == 0.8

    def test_current_soc_with_value(self):
        assert _get_field_value(_entry(current_soc=0.3), "current_soc") == 0.3

    def test_current_soc_none_defaults_zero(self):
        assert _get_field_value(_entry(current_soc=None), "current_soc") == 0.0

    def test_unknown_field_returns_zero(self):
        assert _get_field_value(_entry(), "nope") == 0.0


# ═══════════════════════════════════════════════════════════════
# compute_sort_score
# ═══════════════════════════════════════════════════════════════

class TestComputeSortScore:

    def test_single_asc(self):
        criteria = [{"field": "priority", "weight": 100, "direction": "asc"}]
        assert compute_sort_score(_entry(priority=10), criteria) == 10.0

    def test_single_desc(self):
        criteria = [{"field": "priority", "weight": 100, "direction": "desc"}]
        # desc: -10 * 100 / 100 = -10
        assert compute_sort_score(_entry(priority=10), criteria) == -10.0

    def test_weighted_average(self):
        # 两个 criterion 同 priority=10, weight 100+50 -> 归一化后仍 10
        criteria = [
            {"field": "priority", "weight": 100, "direction": "asc"},
            {"field": "priority", "weight": 50, "direction": "asc"},
        ]
        assert compute_sort_score(_entry(priority=10), criteria) == 10.0

    def test_empty_criteria_no_div_by_zero(self):
        # 直调传空 list: total_weight=0 -> or 1.0; 循环不执行 -> 0.0
        assert compute_sort_score(_entry(priority=10), []) == 0.0

    def test_negative_weight_does_not_invert_sort_semantics(self):
        # 负权重 clip 为 0, total_weight 不为负, asc 语义保持。
        # 修复前: 5 + (-10) = -5 < 0, `or 1.0` 不触发(负数 truthy), total_weight=-5
        # 使正权重项贡献变号 → priority=99 反而比 priority=1 优先 → 排序反转。
        # 须用不同字段(priority vs current_soc): 同字段同方向 sum(weight)=total_weight 约掉。
        crit = [
            {"field": "priority", "weight": 5, "direction": "asc"},
            {"field": "current_soc", "weight": -10, "direction": "asc"},
        ]
        low = _entry(priority=1, current_soc=0.2)
        high = _entry(priority=99, current_soc=0.2)
        assert compute_sort_score(low, crit) < compute_sort_score(high, crit)


# ═══════════════════════════════════════════════════════════════
# sort_queue
# ═══════════════════════════════════════════════════════════════

class TestSortQueue:

    def test_empty(self):
        assert sort_queue([], None) == []

    def test_single(self):
        e = _entry(priority=5)
        assert sort_queue([e], None) == [e]

    def test_sort_by_priority_asc(self):
        # 默认 criteria: priority asc + arrival_time asc
        t = datetime(2026, 8, 2, 10, 0)
        e_low = _entry(priority=1, arrival_time=t)
        e_high = _entry(priority=99, arrival_time=t)
        result = sort_queue([e_high, e_low], None)
        assert result[0] is e_low
        assert result[1] is e_high

    def test_priority_dominates_arrival(self):
        # priority 权重 100 > arrival_time 权重 50; 低 priority 即使晚到也排前
        early_hi = _entry(priority=1, arrival_time=datetime(2026, 8, 2, 8, 0))
        late_lo = _entry(priority=99, arrival_time=datetime(2026, 8, 2, 12, 0))
        assert sort_queue([late_lo, early_hi], None)[0] is early_hi

    def test_stable_for_equal_score(self):
        # 同 priority 同 arrival -> score 相同 -> 保持输入顺序
        t = datetime(2026, 8, 2, 10, 0)
        a = _entry(priority=5, arrival_time=t)
        b = _entry(priority=5, arrival_time=t)
        c = _entry(priority=5, arrival_time=t)
        assert sort_queue([a, b, c], None) == [a, b, c]

    def test_custom_criteria_desc(self):
        # required_energy desc: 大能量优先 (desc 负值, 大值得低分)
        criteria = [{"field": "required_energy", "weight": 100, "direction": "desc"}]
        big = _entry(required_energy_kwh=100)
        small = _entry(required_energy_kwh=10)
        assert sort_queue([small, big], criteria)[0] is big


# ═══════════════════════════════════════════════════════════════
# 跨量纲权重归一化 (卡: priority 不被 arrival_time epoch 分钟碾压)
# ═══════════════════════════════════════════════════════════════

class TestCrossScaleNormalization:

    def test_priority_not_drowned_by_arrival_time(self):
        # 默认规则 priority:100 + arrival_time:50; 修复前 arrival_time epoch
        # 分钟 (~2.97e7) 贡献 ~9.9e6, 碾压 priority 贡献 (~66) 约 15 万倍,
        # 排序退化为纯 FIFO。修复后 priority=1 晚到仍排在 priority=99 早到之前。
        early_lo = _entry(priority=99, arrival_time=datetime(2026, 8, 2, 8, 0))
        late_hi = _entry(priority=1, arrival_time=datetime(2026, 8, 2, 12, 0))
        assert sort_queue([early_lo, late_hi], None)[0] is late_hi

    def test_weight_ratio_reflected_after_normalization(self):
        # 100:50 权重下 priority 主导: priority 差满量程 (0.98) > arrival_time
        # 归一化差 (0.5) × (50/150)
        crit = [
            {"field": "priority", "weight": 100, "direction": "asc"},
            {"field": "arrival_time", "weight": 50, "direction": "asc"},
        ]
        # A: priority 满, arrival 早; B: priority 零, arrival 晚
        A = _entry(priority=99, arrival_time=datetime(2026, 8, 2, 8, 0))
        B = _entry(priority=1, arrival_time=datetime(2026, 8, 2, 12, 0))
        # 再加两条拉出满量程, 使 priority 归一化 [1,99]→[0,1]
        C = _entry(priority=50, arrival_time=datetime(2026, 8, 2, 10, 0))
        out = sort_queue([A, B, C], crit)
        # B 的 priority 归一化=0, arrival_time 归一化=1:
        #   score_B = 0*(100/150) + 1*(50/150) = 0.333
        # A 的 priority=1, arrival=0: score_A = 0.667 → B 优先
        assert out[0] is B

    def test_arrival_time_tiebreak_when_priority_equal(self):
        # 同 priority 时 arrival_time asc 仍生效 (早到优先), 归一化不破坏 FIFO 语义
        t1 = datetime(2026, 8, 2, 8, 0)
        t2 = datetime(2026, 8, 2, 12, 0)
        early = _entry(priority=50, arrival_time=t1)
        late = _entry(priority=50, arrival_time=t2)
        assert sort_queue([late, early], None)[0] is early

    def test_constant_field_range_no_div_by_zero(self):
        # 全部条目字段取值相同 (hi==lo) → 常数映射 0.5, 不除零, 稳定排序保持输入序
        t = datetime(2026, 8, 2, 10, 0)
        a = _entry(priority=5, arrival_time=t)
        b = _entry(priority=5, arrival_time=t)
        assert sort_queue([a, b], None) == [a, b]

    def test_compute_sort_score_direct_call_no_ranges_keeps_raw(self):
        # 公开函数直调 (无 field_ranges): 保持原值加权语义, 兼容既有调用方
        criteria = [{"field": "priority", "weight": 100, "direction": "asc"}]
        assert compute_sort_score(_entry(priority=10), criteria) == 10.0


# ═══════════════════════════════════════════════════════════════
# get_active_rule (DB)
# ═══════════════════════════════════════════════════════════════

class TestGetActiveRule:

    def test_station_level_first(self, test_db):
        db = test_db["session"]
        _rule(db, enterprise_id=10, station_id=5, rule_name="station")
        _rule(db, enterprise_id=10, station_id=None, rule_name="enterprise")
        _rule(db, enterprise_id=0, station_id=None, rule_name="global")
        db.commit()

        assert get_active_rule(db, enterprise_id=10, station_id=5).rule_name == "station"

    def test_enterprise_level_when_no_station_rule(self, test_db):
        db = test_db["session"]
        _rule(db, enterprise_id=10, station_id=None, rule_name="enterprise")
        _rule(db, enterprise_id=0, station_id=None, rule_name="global")
        db.commit()

        assert get_active_rule(db, enterprise_id=10, station_id=5).rule_name == "enterprise"

    def test_global_level_when_no_enterprise_rule(self, test_db):
        db = test_db["session"]
        _rule(db, enterprise_id=0, station_id=None, rule_name="global")
        db.commit()

        assert get_active_rule(db, enterprise_id=10, station_id=5).rule_name == "global"

    def test_none_when_no_rule(self, test_db):
        db = test_db["session"]
        db.commit()
        assert get_active_rule(db, enterprise_id=10, station_id=5) is None

    def test_disabled_rule_skipped(self, test_db):
        db = test_db["session"]
        _rule(db, enterprise_id=10, station_id=5, rule_name="disabled", enable=False)
        _rule(db, enterprise_id=0, station_id=None, rule_name="global")
        db.commit()

        assert get_active_rule(db, enterprise_id=10, station_id=5).rule_name == "global"

    def test_no_station_id_skips_station_level(self, test_db):
        db = test_db["session"]
        _rule(db, enterprise_id=10, station_id=5, rule_name="station")
        _rule(db, enterprise_id=10, station_id=None, rule_name="enterprise")
        db.commit()

        # station_id=None -> 跳过 station 级, 直接查 enterprise 级
        assert get_active_rule(db, enterprise_id=10, station_id=None).rule_name == "enterprise"


# ═══════════════════════════════════════════════════════════════
# recalculate_priorities (DB)
# ═══════════════════════════════════════════════════════════════

class TestRecalculatePriorities:

    def test_sorted_and_wait_minutes_updated(self, test_db):
        db = test_db["session"]
        t = datetime(2026, 8, 2, 10, 0)
        # 乱序插入: 高 priority 值(低优先)在前, 验证按 score 重排
        _cq(db, vehicle_id=1, priority=99, arrival_time=t)
        _cq(db, vehicle_id=2, priority=1, arrival_time=t)
        _cq(db, vehicle_id=3, priority=50, arrival_time=t)
        db.commit()

        criteria = [{"field": "priority", "weight": 100, "direction": "asc"}]
        result = recalculate_priorities(db, station_id=1, criteria=criteria)

        # priority asc: 1 -> 50 -> 99
        assert [r.vehicle_id for r in result] == [2, 3, 1]
        # estimated_wait_minutes 按 30 分钟递增
        assert [r.estimated_wait_minutes for r in result] == [0, 30, 60]

    def test_empty_queue(self, test_db):
        db = test_db["session"]
        db.commit()
        assert recalculate_priorities(db, station_id=1, criteria=None) == []

    def test_only_waiting_processed(self, test_db):
        db = test_db["session"]
        t = datetime(2026, 8, 2, 10, 0)
        _cq(db, vehicle_id=1, priority=1, arrival_time=t, status=ChargingQueueStatus.CHARGING.value)
        _cq(db, vehicle_id=2, priority=5, arrival_time=t, status=ChargingQueueStatus.WAITING.value)
        db.commit()

        result = recalculate_priorities(db, station_id=1, criteria=None)
        assert len(result) == 1
        assert result[0].vehicle_id == 2
        assert result[0].estimated_wait_minutes == 0
