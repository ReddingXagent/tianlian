"""
告警聚合服务测试 - 覆盖率补强 ≥70%

被测: app/services/alarm_aggregation.py
设计: test_db 真 SQLite + Alarm model; 模块级 _storm_counters 用 autouse fixture
      隔离避免用例间状态污染。

时区注意: alarm_aggregation 统一用 datetime.now(timezone.utc) (UTC) 算窗口, 故 Alarm.created_at
          也用 utcnow() 对齐, 否则被 5 分钟聚合窗口过滤。

覆盖:
- _clean_storm_counters       清理过期 key / 保留窗口内 key
- check_anti_storm            前3次允许 / 第4次抑制 / 不同 key 独立计数
- find_aggregatable_alarm     命中 / 状态非ACTIVE / 超窗口 / 已升级 / rule 不匹配
- update_aggregated_alarm     count 累加 / last_at None→now / last_at 已有→更新 / trigger_value 更新
- try_aggregate_alarm         风暴抑制分支 / 找到 existing / 无 existing 返回 None
- get_aggregation_stats       多 rule 聚合统计 / agg_count<=1 不计入 / first/last_at 序列化
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import alarm_aggregation as aa
from app.services.alarm_aggregation import (
    check_anti_storm,
    find_aggregatable_alarm,
    update_aggregated_alarm,
    try_aggregate_alarm,
    get_aggregation_stats,
    AGGREGATION_WINDOW_MINUTES,
    ANTI_STORM_MAX_TRIGGERS,
)
from app.models.alarm import Alarm, AlarmStatus, AlarmLevel


# ═══════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _isolate_storm_counters():
    """每个用例前后清空模块级防风暴计数器, 避免跨用例污染。"""
    aa._storm_counters.clear()
    yield
    aa._storm_counters.clear()


def make_alarm(db, device_id=1, rule_id=10, status=AlarmStatus.ACTIVE,
               created_at=None, agg_count=None, agg_first=None, agg_last=None,
               escalated_from=None, trigger_value=42.0):
    """alarm_aggregation 用 now()(本地) 算窗口, created_at 默认 now()。"""
    a = Alarm(
        device_id=device_id, rule_id=rule_id, status=status,
        created_at=created_at or datetime.now(timezone.utc),
        aggregation_count=agg_count,
        aggregation_first_at=agg_first,
        aggregation_last_at=agg_last,
        escalated_from=escalated_from,
        trigger_value=trigger_value,
        level=AlarmLevel.WARNING, content="c", alarm_type="t",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ═══════════════════════════════════════════════════════════════
# 1. _clean_storm_counters
# ═══════════════════════════════════════════════════════════════

class TestCleanStormCounters:

    def test_removes_fully_expired_key(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=100)  # 远超 30s 窗口
        aa._storm_counters[(1, 1)] = [old]
        aa._clean_storm_counters()
        assert (1, 1) not in aa._storm_counters

    def test_keeps_key_with_recent_timestamp(self):
        recent = datetime.now(timezone.utc) - timedelta(seconds=5)
        aa._storm_counters[(2, 2)] = [recent]
        aa._clean_storm_counters()
        assert (2, 2) in aa._storm_counters


# ═══════════════════════════════════════════════════════════════
# 2. check_anti_storm
# ═══════════════════════════════════════════════════════════════

class TestCheckAntiStorm:

    def test_allows_up_to_max_then_suppresses(self):
        # ANTI_STORM_MAX_TRIGGERS=3: 前 3 次 True, 第 4 次 False
        for _ in range(ANTI_STORM_MAX_TRIGGERS):
            assert check_anti_storm(10, 100) is True
        assert check_anti_storm(10, 100) is False  # 第 4 次抑制

    def test_different_keys_count_independently(self):
        # (10,100) 已打满, (10,200) 仍允许
        for _ in range(ANTI_STORM_MAX_TRIGGERS):
            check_anti_storm(10, 100)
        assert check_anti_storm(10, 200) is True
        assert check_anti_storm(10, 100) is False

    def test_counter_grows_within_window(self):
        assert check_anti_storm(30, 300) is True
        assert len(aa._storm_counters[(30, 300)]) == 1
        assert check_anti_storm(30, 300) is True
        assert len(aa._storm_counters[(30, 300)]) == 2


# ═══════════════════════════════════════════════════════════════
# 3. find_aggregatable_alarm
# ═══════════════════════════════════════════════════════════════

class TestFindAggregatable:

    def test_finds_active_recent_alarm(self, test_db):
        db = test_db["session"]
        a = make_alarm(db, device_id=1, rule_id=10, agg_count=1)
        found = find_aggregatable_alarm(1, 10, db)
        assert found is not None
        assert found.id == a.id

    def test_skips_non_active_status(self, test_db):
        db = test_db["session"]
        make_alarm(db, device_id=2, rule_id=10, status=AlarmStatus.RESOLVED)
        assert find_aggregatable_alarm(2, 10, db) is None

    def test_skips_alarm_outside_window(self, test_db):
        db = test_db["session"]
        old = datetime.now(timezone.utc) - timedelta(minutes=AGGREGATION_WINDOW_MINUTES + 2)
        make_alarm(db, device_id=3, rule_id=10, created_at=old)
        assert find_aggregatable_alarm(3, 10, db) is None

    def test_skips_escalated_alarm(self, test_db):
        db = test_db["session"]
        make_alarm(db, device_id=4, rule_id=10, escalated_from="warning")
        assert find_aggregatable_alarm(4, 10, db) is None

    def test_rule_mismatch_returns_none(self, test_db):
        db = test_db["session"]
        make_alarm(db, device_id=5, rule_id=10)
        assert find_aggregatable_alarm(5, 999, db) is None

    def test_returns_most_recent_when_multiple(self, test_db):
        db = test_db["session"]
        older = make_alarm(db, device_id=6, rule_id=10,
                           created_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        newer = make_alarm(db, device_id=6, rule_id=10,
                           created_at=datetime.now(timezone.utc))
        found = find_aggregatable_alarm(6, 10, db)
        assert found.id == newer.id  # order_by created_at desc


# ═══════════════════════════════════════════════════════════════
# 4. update_aggregated_alarm
# ═══════════════════════════════════════════════════════════════

class TestUpdateAggregatedAlarm:

    def test_increments_count_and_updates_trigger(self, test_db):
        db = test_db["session"]
        now = datetime.now(timezone.utc)
        a = make_alarm(db, device_id=1, rule_id=10, agg_count=5,
                       agg_first=now, agg_last=now, trigger_value=10.0)
        updated = update_aggregated_alarm(a, current_value=99.5, db=db)
        assert updated.aggregation_count == 6
        assert updated.trigger_value == 99.5
        assert updated.aggregation_last_at is not None

    def test_sets_last_at_when_none(self, test_db):
        # 覆盖 line 103-104 last_at is None 分支
        db = test_db["session"]
        a = make_alarm(db, device_id=2, rule_id=10, agg_count=1,
                       agg_first=None, agg_last=None)
        updated = update_aggregated_alarm(a, current_value=1.0, db=db)
        assert updated.aggregation_last_at is not None
        assert updated.aggregation_count == 2  # (1 or 1) + 1


# ═══════════════════════════════════════════════════════════════
# 5. try_aggregate_alarm
# ═══════════════════════════════════════════════════════════════

class TestTryAggregateAlarm:

    def test_storm_suppressed_returns_sentinel_and_deletes(self, test_db):
        # 路径1 (卡 2779d516 新契约): 防风暴打满 → 删除新告警行并返回 SUPPRESSED 哨兵。
        # 旧契约返回 new_alarm 自身会让 _create_alarm 误判「未聚合」走完整副作用路径。
        db = test_db["session"]
        for _ in range(ANTI_STORM_MAX_TRIGGERS):
            check_anti_storm(1, 10)
        new_alarm = make_alarm(db, device_id=1, rule_id=10, agg_count=None)
        result = try_aggregate_alarm(new_alarm, db)
        assert result is aa.SUPPRESSED
        # 新告警行已被删除, 不残留
        from app.models.alarm import Alarm
        assert db.query(Alarm).filter(Alarm.id == new_alarm.id).count() == 0

    def test_aggregates_into_existing(self, test_db):
        # 路径2: 找到可聚合 existing → 更新并返回 existing
        # new_alarm 用 detached 对象(未落库), 否则其 created_at 最新会被
        # find_aggregatable_alarm 的 order_by(created_at desc) 查到自身。
        db = test_db["session"]
        existing = make_alarm(db, device_id=2, rule_id=20, agg_count=1,
                              trigger_value=5.0)
        new_alarm = Alarm(device_id=2, rule_id=20, status=AlarmStatus.ACTIVE,
                          trigger_value=8.0, level=AlarmLevel.WARNING,
                          content="c", alarm_type="t")
        result = try_aggregate_alarm(new_alarm, db)
        assert result is existing
        assert result.aggregation_count == 2
        assert result.trigger_value == 8.0  # 保留最新值

    def test_no_existing_returns_none_and_inits(self, test_db):
        # 路径3: 无可聚合 → 初始化 new 字段, 返回 None
        # new_alarm detached (未落库), 避免被 find 查到自身走路径2。
        db = test_db["session"]
        new_alarm = Alarm(device_id=3, rule_id=30, status=AlarmStatus.ACTIVE,
                          level=AlarmLevel.WARNING, content="c", alarm_type="t")
        result = try_aggregate_alarm(new_alarm, db)
        assert result is None
        assert new_alarm.aggregation_count == 1
        assert new_alarm.aggregation_first_at is not None
        assert new_alarm.aggregation_last_at is not None


# ═══════════════════════════════════════════════════════════════
# 6. get_aggregation_stats
# ═══════════════════════════════════════════════════════════════

class TestGetAggregationStats:

    def test_groups_by_rule_and_sums_counts(self, test_db):
        db = test_db["session"]
        now = datetime.now(timezone.utc)
        # rule 10: 2 条 (agg_count 3, 2)
        make_alarm(db, device_id=7, rule_id=10, agg_count=3,
                   agg_first=now, agg_last=now)
        make_alarm(db, device_id=7, rule_id=10, agg_count=2,
                   agg_first=now, agg_last=now)
        # rule 11: 1 条 (agg_count 4)
        make_alarm(db, device_id=7, rule_id=11, agg_count=4,
                   agg_first=now, agg_last=now)
        # agg_count=1 不计入 (>1 过滤)
        make_alarm(db, device_id=7, rule_id=12, agg_count=1,
                   agg_first=now, agg_last=now)

        stats = get_aggregation_stats(7, db)
        by_rule = {s["rule_id"]: s for s in stats}
        assert 10 in by_rule and 11 in by_rule
        assert 12 not in by_rule  # agg_count=1 被过滤
        assert by_rule[10]["total_alarms"] == 2
        assert by_rule[10]["total_aggregated"] == 5  # 3 + 2
        assert by_rule[11]["total_alarms"] == 1
        assert by_rule[11]["total_aggregated"] == 4
        # first/last_at 序列化为 isoformat 字符串
        assert isinstance(by_rule[10]["first_at"], str)
        assert isinstance(by_rule[10]["last_at"], str)

    def test_other_device_excluded(self, test_db):
        db = test_db["session"]
        now = datetime.now(timezone.utc)
        make_alarm(db, device_id=8, rule_id=10, agg_count=5,
                   agg_first=now, agg_last=now)
        make_alarm(db, device_id=9, rule_id=10, agg_count=5,
                   agg_first=now, agg_last=now)
        stats = get_aggregation_stats(8, db)
        assert all(s["rule_id"] == 10 for s in stats)
        assert stats[0]["total_alarms"] == 1  # 仅 device 8

    def test_empty_when_no_aggregated(self, test_db):
        db = test_db["session"]
        assert get_aggregation_stats(999, db) == []
