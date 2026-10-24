"""charging_queue_service 单元测试 — 优先级权重计算引擎

纯逻辑测试, DB 用 MagicMock 隔离。覆盖:
- _parse_criteria: 默认/JSON 字符串/非法 JSON/非 list/字段过滤/回退
- _get_field_value: 各字段提取 + None 兜底
- compute_sort_score: asc/desc 加权 + total_weight 防零
- sort_queue: 空队列/单条/稳定排序
- get_active_rule: station→enterprise→global 三级回退
- recalculate_priorities: WAITING 过滤 + estimated_wait_minutes 更新
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.charging_queue import ChargingQueue, ChargingQueueStatus
from app.models.device import Device
from app.services.charging_queue_service import (
    DEFAULT_PRIORITY_CRITERIA,
    _get_field_value,
    _parse_criteria,
    compute_sort_score,
    get_active_rule,
    recalculate_priorities,
    sort_queue,
)


# ═══════════════════════════════════════════
# _parse_criteria
# ═══════════════════════════════════════════

class TestParseCriteria:
    def test_none_returns_default(self):
        parsed = _parse_criteria(None)
        assert parsed == list(DEFAULT_PRIORITY_CRITERIA)

    def test_empty_list_returns_default(self):
        assert _parse_criteria([]) == list(DEFAULT_PRIORITY_CRITERIA)

    def test_valid_list_passed_through(self):
        raw = [
            {"field": "priority", "weight": 100, "direction": "asc"},
            {"field": "required_energy", "weight": 50, "direction": "desc"},
        ]
        parsed = _parse_criteria(raw)
        assert parsed == raw

    def test_valid_json_string_parsed(self):
        raw = json.dumps([{"field": "priority", "weight": 10, "direction": "asc"}])
        parsed = _parse_criteria(raw)
        assert parsed == [{"field": "priority", "weight": 10.0, "direction": "asc"}]

    def test_invalid_json_string_falls_back(self):
        assert _parse_criteria("{not json") == list(DEFAULT_PRIORITY_CRITERIA)

    def test_non_list_falls_back(self):
        assert _parse_criteria({"field": "priority"}) == list(DEFAULT_PRIORITY_CRITERIA)
        assert _parse_criteria(123) == list(DEFAULT_PRIORITY_CRITERIA)

    def test_filters_invalid_items(self):
        raw = [
            {"field": "priority", "weight": 10, "direction": "asc"},   # ok
            "not-a-dict",                                                # 跳过
            {"weight": 10, "direction": "asc"},                         # 缺 field → 跳过
            {"field": "x", "weight": -1, "direction": "asc"},           # weight<=0 → 跳过
            {"field": "y", "weight": 10, "direction": "sideways"},      # 非法 direction → 跳过
        ]
        parsed = _parse_criteria(raw)
        assert len(parsed) == 1
        assert parsed[0]["field"] == "priority"

    def test_all_invalid_items_falls_back_to_default(self):
        raw = [{"field": "x", "weight": -1, "direction": "asc"}]
        assert _parse_criteria(raw) == list(DEFAULT_PRIORITY_CRITERIA)

    def test_default_weight_and_direction_when_missing(self):
        raw = [{"field": "priority"}]
        parsed = _parse_criteria(raw)
        assert parsed[0]["weight"] == 1.0
        assert parsed[0]["direction"] == "asc"

    def test_non_numeric_weight_string_skipped(self):
        # weight='abc' → float() 抛 ValueError, 须跳过该非法项, 不 500
        raw = [
            {"field": "priority", "weight": "abc", "direction": "asc"},
            {"field": "arrival_time", "weight": 10, "direction": "asc"},
        ]
        parsed = _parse_criteria(raw)
        assert [c["field"] for c in parsed] == ["arrival_time"]

    def test_non_numeric_weight_dict_or_list_skipped(self):
        # weight=dict/list → float() 抛 TypeError, 须跳过
        raw = [
            {"field": "priority", "weight": {"x": 1}, "direction": "asc"},
            {"field": "arrival_time", "weight": [1, 2], "direction": "asc"},
        ]
        assert _parse_criteria(raw) == list(DEFAULT_PRIORITY_CRITERIA)

    def test_all_non_numeric_weight_falls_back_to_default(self):
        raw = [{"field": "priority", "weight": "abc", "direction": "asc"}]
        assert _parse_criteria(raw) == list(DEFAULT_PRIORITY_CRITERIA)

    def test_nan_weight_skipped(self):
        # NaN: weight>0 为 False, 但 NaN 会污染后续算分, 须显式按非法处理
        raw = [{"field": "priority", "weight": float("nan"), "direction": "asc"}]
        assert _parse_criteria(raw) == list(DEFAULT_PRIORITY_CRITERIA)

    def test_inf_weight_skipped(self):
        # inf: weight>0 为 True 会穿透, 权重爆炸, 须显式排除
        raw = [
            {"field": "priority", "weight": float("inf"), "direction": "asc"},
            {"field": "arrival_time", "weight": 10, "direction": "asc"},
        ]
        parsed = _parse_criteria(raw)
        assert [c["field"] for c in parsed] == ["arrival_time"]


# ═══════════════════════════════════════════
# _get_field_value
# ═══════════════════════════════════════════

class TestGetFieldValue:
    def _entry(self, **kw):
        e = ChargingQueue()
        for k, v in kw.items():
            setattr(e, k, v)
        return e

    def test_priority(self):
        assert _get_field_value(self._entry(priority=5), "priority") == 5.0

    def test_priority_defaults_to_100_when_none(self):
        assert _get_field_value(self._entry(priority=None), "priority") == 100.0

    def test_priority_zero_kept_as_explicit_highest(self):
        # 显式 priority=0 是最高优先级 (数字越小越优先), 不得因 falsy 被回退为 100
        assert _get_field_value(self._entry(priority=0), "priority") == 0.0

    def test_priority_zero_sorts_before_100(self):
        # 验收: priority=0 排序分数须比 priority=100 更低(更优先), 归一化不得破坏该语义
        crit = [{"field": "priority", "weight": 1, "direction": "asc"}]
        top = compute_sort_score(ChargingQueue(priority=0), crit, field_ranges={"priority": (0.0, 100.0)})
        bottom = compute_sort_score(ChargingQueue(priority=100), crit, field_ranges={"priority": (0.0, 100.0)})
        assert top < bottom
        assert top == pytest.approx(0.0)

    def test_current_soc_defaults_to_0(self):
        assert _get_field_value(self._entry(current_soc=None), "current_soc") == 0.0

    def test_arrival_time_datetime(self):
        dt = datetime(2026, 1, 1, 0, 0, 0)
        val = _get_field_value(self._entry(arrival_time=dt), "arrival_time")
        assert val == pytest.approx(dt.timestamp() / 60.0)

    def test_unknown_field_returns_zero(self):
        assert _get_field_value(self._entry(), "no_such_field") == 0.0


# ═══════════════════════════════════════════
# compute_sort_score
# ═══════════════════════════════════════════

class TestComputeScore:
    def test_asc_score_increases_with_value(self):
        crit = [{"field": "priority", "weight": 1, "direction": "asc"}]
        low = ChargingQueue(priority=1)
        high = ChargingQueue(priority=99)
        assert compute_sort_score(low, crit) < compute_sort_score(high, crit)

    def test_desc_score_decreases_with_value(self):
        crit = [{"field": "priority", "weight": 1, "direction": "desc"}]
        big = ChargingQueue(priority=99)
        small = ChargingQueue(priority=1)
        # desc: 大值 → 更低分 → 更优先
        assert compute_sort_score(big, crit) < compute_sort_score(small, crit)

    def test_weighted_sum_proportions(self):
        crit = [
            {"field": "priority", "weight": 3, "direction": "asc"},
            {"field": "required_energy", "weight": 1, "direction": "asc"},
        ]
        e = ChargingQueue(priority=10, required_energy_kwh=20)
        # total_weight=4; score = (10*3 + 20*1)/4 = 50/4 = 12.5
        assert compute_sort_score(e, crit) == pytest.approx(12.5)

    def test_empty_criteria_returns_zero(self):
        e = ChargingQueue(priority=10)
        # total_weight = 0 or 1.0 → 1.0, score 0
        assert compute_sort_score(e, []) == 0.0

    def test_negative_weight_clipped_not_invert(self):
        # 负权重 clip 为 0, total_weight 不为负, asc 语义保持。
        # 修复前: weight 5 + (-10) = -5 < 0, `or 1.0` 不触发(负数 truthy),
        # total_weight=-5 使正权重项贡献变号 → priority=99 反而比 priority=1
        # 分数低(更优先) → 排序反转。须用不同字段(priority vs current_soc)
        # 才暴露: 同字段同方向时 sum(weight)=total_weight 会约掉看不出反转。
        crit = [
            {"field": "priority", "weight": 5, "direction": "asc"},
            {"field": "current_soc", "weight": -10, "direction": "asc"},
        ]
        low = ChargingQueue(priority=1, current_soc=0.2)
        high = ChargingQueue(priority=99, current_soc=0.2)
        # priority asc: priority 小者分数低 → 更优先
        assert compute_sort_score(low, crit) < compute_sort_score(high, crit)


# ═══════════════════════════════════════════
# sort_queue
# ═══════════════════════════════════════════

class TestSortQueue:
    def test_empty_returns_empty(self):
        assert sort_queue([], None) == []

    def test_single_passthrough(self):
        e = ChargingQueue(id=1, priority=5)
        assert sort_queue([e], None) == [e]

    def test_priority_asc_ordering(self):
        crit = [{"field": "priority", "weight": 10, "direction": "asc"}]
        a = ChargingQueue(id=1, priority=10)
        b = ChargingQueue(id=2, priority=1)
        c = ChargingQueue(id=3, priority=5)
        out = sort_queue([a, b, c], crit)
        assert [e.id for e in out] == [2, 3, 1]

    def test_stable_sort_preserves_equal_score_order(self):
        crit = [{"field": "priority", "weight": 10, "direction": "asc"}]
        a = ChargingQueue(id=1, priority=5)
        b = ChargingQueue(id=2, priority=5)
        c = ChargingQueue(id=3, priority=5)
        out = sort_queue([a, b, c], crit)
        assert [e.id for e in out] == [1, 2, 3]

    def test_sort_queue_accepts_json_string_criteria(self):
        crit = json.dumps([{"field": "priority", "weight": 10, "direction": "asc"}])
        a = ChargingQueue(id=1, priority=99)
        b = ChargingQueue(id=2, priority=1)
        out = sort_queue([a, b], crit)
        assert [e.id for e in out] == [2, 1]


# ═══════════════════════════════════════════
# get_active_rule (三级回退)
# ═══════════════════════════════════════════

def _rule_mock_db(first_results):
    """构造 db: query→filter→first 链, first.side_effect = first_results (按调用顺序消费)。"""
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.side_effect = first_results
    return db, q


class TestGetActiveRule:
    def test_station_level_wins(self):
        station_rule = MagicMock(name="station_rule")
        db, q = _rule_mock_db([station_rule])
        got = get_active_rule(db, enterprise_id=1, station_id=7)
        assert got is station_rule
        assert q.first.call_count == 1  # 命中即返回, 不再回退

    def test_fallback_to_enterprise_when_no_station_rule(self):
        ent_rule = MagicMock(name="ent_rule")
        db, q = _rule_mock_db([None, ent_rule])
        got = get_active_rule(db, enterprise_id=1, station_id=7)
        assert got is ent_rule
        assert q.first.call_count == 2

    def test_fallback_to_global_when_no_station_nor_enterprise(self):
        global_rule = MagicMock(name="global_rule")
        db, q = _rule_mock_db([None, None, global_rule])
        got = get_active_rule(db, enterprise_id=1, station_id=7)
        assert got is global_rule
        assert q.first.call_count == 3

    def test_returns_none_when_nothing_matches(self):
        db, q = _rule_mock_db([None, None, None])
        assert get_active_rule(db, enterprise_id=1, station_id=7) is None
        assert q.first.call_count == 3

    def test_no_station_id_skips_station_query(self):
        # station_id=None → 直接走 enterprise(1) → global(2)
        ent_rule = MagicMock(name="ent_rule")
        db, q = _rule_mock_db([ent_rule])
        got = get_active_rule(db, enterprise_id=1, station_id=None)
        assert got is ent_rule
        assert q.first.call_count == 1

    def test_no_station_id_falls_to_global(self):
        global_rule = MagicMock(name="global_rule")
        db, q = _rule_mock_db([None, global_rule])
        got = get_active_rule(db, enterprise_id=1, station_id=None)
        assert got is global_rule
        assert q.first.call_count == 2


# ═══════════════════════════════════════════
# recalculate_priorities
# ═══════════════════════════════════════════

class TestRecalculate:
    def test_sorts_and_assigns_wait_minutes(self):
        entries = [ChargingQueue(id=1, priority=10), ChargingQueue(id=2, priority=1)]
        db = self._recalc_db(entries, pile_count=1)
        a, b = entries
        crit = [{"field": "priority", "weight": 10, "direction": "asc"}]
        out = recalculate_priorities(db, station_id=5, criteria=crit)
        # 排序后 b(优先)在前 → index 0 → wait 0; a → index 1 → wait 30
        assert [e.id for e in out] == [2, 1]
        assert b.estimated_wait_minutes == 0
        assert a.estimated_wait_minutes == 30
        db.flush.assert_called_once()

    def test_empty_waiting_returns_empty(self):
        db = self._recalc_db([], pile_count=1)
        out = recalculate_priorities(db, station_id=5, criteria=None)
        assert out == []
        db.flush.assert_called_once()

    def test_wait_minutes_use_30_min_increment(self):
        # priority 用 1..4 (避开 priority=0 的源码 falsy 回退 bug)
        entries = [ChargingQueue(id=i, priority=i + 1) for i in range(4)]
        db = self._recalc_db(entries, pile_count=1)
        recalculate_priorities(db, station_id=5, criteria=[{"field": "priority", "weight": 1, "direction": "asc"}])
        # 升序后仍是 id 顺序 [0,1,2,3] → wait [0,30,60,90]
        assert [e.estimated_wait_minutes for e in entries] == [0, 30, 60, 90]

    def _recalc_db(self, entries, pile_count, queue_q=None):
        """构造 db: query 首次(WAITING 队列)→all; 第二次(桩计数)→count 返回 pile_count。"""
        db = MagicMock()
        if queue_q is None:
            queue_q = MagicMock()
        pile_q = MagicMock()
        queue_q.filter.return_value = queue_q
        queue_q.all.return_value = entries
        pile_q.filter.return_value = pile_q
        pile_q.count.return_value = pile_count
        db.query.side_effect = [queue_q, pile_q]
        return db

    def test_multi_pile_wait_divided_by_pile_count(self):
        # 4 条等待 + 2 桩 → wait = (i//2)*30 = [0,0,30,30]
        entries = [ChargingQueue(id=i, priority=i + 1) for i in range(4)]
        db = self._recalc_db(entries, pile_count=2)
        recalculate_priorities(db, station_id=5, criteria=[{"field": "priority", "weight": 1, "direction": "asc"}])
        assert [e.estimated_wait_minutes for e in entries] == [0, 0, 30, 30]
        db.flush.assert_called_once()

    def test_single_pile_keeps_serial_behavior(self):
        entries = [ChargingQueue(id=i, priority=i + 1) for i in range(4)]
        db = self._recalc_db(entries, pile_count=1)
        recalculate_priorities(db, station_id=5, criteria=[{"field": "priority", "weight": 1, "direction": "asc"}])
        assert [e.estimated_wait_minutes for e in entries] == [0, 30, 60, 90]

    def test_zero_pile_degrades_to_serial(self):
        # pile_count=0 (无可用桩/查询失败兜底) → 退化为 i*30
        entries = [ChargingQueue(id=i, priority=i + 1) for i in range(3)]
        db = self._recalc_db(entries, pile_count=0)
        recalculate_priorities(db, station_id=5, criteria=[{"field": "priority", "weight": 1, "direction": "asc"}])
        assert [e.estimated_wait_minutes for e in entries] == [0, 30, 60]

    def test_pile_query_counts_online_chargers_of_station(self):
        # 桩计数查询条件: Device + ONLINE + 充电桩类型 + station_id
        entries = [ChargingQueue(id=1, priority=1)]
        db = self._recalc_db(entries, pile_count=3)
        recalculate_priorities(db, station_id=42, criteria=None)
        second_query_args = db.query.call_args_list[1].args
        assert second_query_args == (Device,)

    def test_filters_only_waiting_status(self):
        queue_q = MagicMock()
        queue_q.filter.return_value = queue_q
        queue_q.all.return_value = []
        db = self._recalc_db([], pile_count=1, queue_q=queue_q)
        recalculate_priorities(db, station_id=9, criteria=None)
        # 首次 query 即 WAITING 队列查询, 状态过滤在 filter 调用中
        assert db.query.call_args_list[0].args == (ChargingQueue,)
        queue_q.filter.assert_called_once()
        # 确认使用的是 WAITING 状态值
        assert ChargingQueueStatus.WAITING.value == "waiting"
