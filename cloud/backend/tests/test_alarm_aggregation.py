"""alarm_aggregation 单元测试 — 告警聚合 + 防风暴

纯逻辑测试, DB 用 MagicMock 隔离。覆盖:
- check_anti_storm: 30s 窗口内同 (device, rule) 最多 3 次, 第 4 次起抑制
- _clean_storm_counters: 清理全过期 key, 保留含新时间戳的 key
- find_aggregatable_alarm: 查询可聚合告警 (含 escalated_from.is_(None) 过滤)
- update_aggregated_alarm: 计数自增 + 时间戳更新 + trigger_value 更新
- try_aggregate_alarm: 防风暴优先 → 聚合已有 → 初始化新告警 三分支
- get_aggregation_stats: 分组统计与 None 兜底
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.alarm import Alarm, AlarmStatus
from app.services import alarm_aggregation as aa


@pytest.fixture(autouse=True)
def _reset_storm_counters():
    """每个用例前清空模块级防风暴计数器, 避免相互污染。"""
    aa._storm_counters.clear()
    yield
    aa._storm_counters.clear()


# ═══════════════════════════════════════════
# check_anti_storm / _clean_storm_counters
# ═══════════════════════════════════════════

class TestAntiStorm:
    def test_first_three_calls_allowed(self):
        for i in range(3):
            assert aa.check_anti_storm(device_id=1, rule_id=10) is True

    def test_fourth_call_suppressed(self):
        for _ in range(3):
            aa.check_anti_storm(device_id=1, rule_id=10)
        assert aa.check_anti_storm(device_id=1, rule_id=10) is False

    def test_suppression_does_not_grow_counter(self):
        for _ in range(3):
            aa.check_anti_storm(device_id=1, rule_id=10)
        # 被抑制后计数器保持 3, 不再追加
        aa.check_anti_storm(device_id=1, rule_id=10)
        assert len(aa._storm_counters[(1, 10)]) == 3

    def test_different_keys_independent(self):
        for _ in range(3):
            aa.check_anti_storm(device_id=1, rule_id=10)
        # 不同 rule 视为新 key, 允许触发
        assert aa.check_anti_storm(device_id=1, rule_id=20) is True

    def test_clean_removes_fully_expired_key(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=120)
        aa._storm_counters[(5, 5)] = [old, old]
        aa._clean_storm_counters()
        assert (5, 5) not in aa._storm_counters

    def test_clean_keeps_key_with_recent_timestamp(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=120)
        recent = datetime.now(timezone.utc)
        aa._storm_counters[(5, 5)] = [old, recent]
        aa._clean_storm_counters()
        assert (5, 5) in aa._storm_counters

    def test_check_filters_out_expired_then_allows(self):
        # 注入一个过期时间戳, 触发时会被清理, 计数从 0 开始 → 允许
        old = datetime.now(timezone.utc) - timedelta(seconds=120)
        aa._storm_counters[(7, 7)] = [old, old, old]
        assert aa.check_anti_storm(device_id=7, rule_id=7) is True
        # 过期时间戳被过滤掉, 仅保留本次追加
        assert all(ts > old for ts in aa._storm_counters[(7, 7)])


# ═══════════════════════════════════════════
# find_aggregatable_alarm
# ═══════════════════════════════════════════

class TestFindAggregatable:
    def test_returns_matched_alarm(self):
        db = MagicMock()
        target = Alarm(id=99)
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = target
        got = aa.find_aggregatable_alarm(device_id=1, rule_id=2, db=db)
        assert got is target
        db.query.return_value.filter.assert_called_once()

    def test_returns_none_when_no_match(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        assert aa.find_aggregatable_alarm(device_id=1, rule_id=2, db=db) is None


# ═══════════════════════════════════════════
# update_aggregated_alarm
# ═══════════════════════════════════════════

class TestUpdateAggregated:
    def test_increments_count_and_updates_trigger_value(self):
        db = MagicMock()
        alarm = Alarm(id=1, aggregation_count=2, trigger_value=30.0)
        result = aa.update_aggregated_alarm(alarm, current_value=42.0, db=db)
        assert result.aggregation_count == 3
        assert result.trigger_value == 42.0
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(alarm)

    def test_count_defaults_to_one_when_none(self):
        db = MagicMock()
        alarm = Alarm(id=1, aggregation_count=None)
        result = aa.update_aggregated_alarm(alarm, current_value=1.0, db=db)
        # (None or 1) + 1 == 2
        assert result.aggregation_count == 2

    def test_last_at_always_set(self):
        # NOTE 源码可维护性问题 (非功能 bug): update_aggregated_alarm 中
        #   if alarm.aggregation_last_at is None: ...=now()  else: ...=now()
        # 两分支完全相同 (dead branch), 无论原值是否为 None 都会被覆盖为 now()。
        # 此处验证行为: 传入已存在的 last_at 也会被刷新。
        db = MagicMock()
        before = datetime.now(timezone.utc) - timedelta(hours=1)
        alarm = Alarm(id=1, aggregation_count=1, aggregation_last_at=before)
        result = aa.update_aggregated_alarm(alarm, current_value=1.0, db=db)
        assert result.aggregation_last_at is not None
        assert result.aggregation_last_at > before


# ═══════════════════════════════════════════
# try_aggregate_alarm
# ═══════════════════════════════════════════

class TestTryAggregate:
    def _new_alarm(self):
        return Alarm(id=1, device_id=1, rule_id=10, trigger_value=50.0)

    def test_aggregates_into_existing(self):
        db = MagicMock()
        existing = Alarm(id=2, device_id=1, rule_id=10, aggregation_count=1)
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing
        new_alarm = self._new_alarm()
        result = aa.try_aggregate_alarm(new_alarm, db)
        # 命中已有告警 → 返回的是 existing (已 update)
        assert result is existing
        assert existing.aggregation_count == 2
        assert existing.trigger_value == 50.0

    def test_no_existing_returns_none_and_inits_new(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        new_alarm = self._new_alarm()
        result = aa.try_aggregate_alarm(new_alarm, db)
        assert result is None
        assert new_alarm.aggregation_count == 1
        assert new_alarm.aggregation_first_at is not None
        assert new_alarm.aggregation_last_at is not None
        db.commit.assert_called_once()

    def test_storm_suppressed_deletes_new_alarm_and_returns_sentinel(self):
        # 卡 2779d516: 抑制分支返回 SUPPRESSED 哨兵并删除新建告警行,
        # 调用方 (_create_alarm) 据此走零副作用路径 (不建行/日志/工单/通知)。
        # 旧契约「返回 new_alarm 自身」会让调用方误判为未聚合走完整路径,
        # 被抑制的触发反而产生最重副作用, 防风暴完全失效。
        for _ in range(3):
            aa.check_anti_storm(device_id=1, rule_id=10)
        db = MagicMock()
        new_alarm = self._new_alarm()
        result = aa.try_aggregate_alarm(new_alarm, db)
        assert result is aa.SUPPRESSED
        db.delete.assert_called_once_with(new_alarm)
        db.commit.assert_called()
        # 抑制时不应再查可聚合告警 (find_aggregatable_alarm 不被调用 → query 未发生)
        db.query.assert_not_called()


# ═══════════════════════════════════════════
# get_aggregation_stats
# ═══════════════════════════════════════════

class TestAggregationStats:
    def test_stats_structure(self):
        db = MagicMock()
        first_at = datetime(2026, 1, 1, 10, 0, 0)
        last_at = datetime(2026, 1, 1, 10, 5, 0)
        rows = [(1, 5, 12, first_at, last_at)]
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows
        stats = aa.get_aggregation_stats(device_id=1, db=db)
        assert len(stats) == 1
        assert stats[0] == {
            "rule_id": 1,
            "total_alarms": 5,
            "total_aggregated": 12,
            "first_at": first_at.isoformat(),
            "last_at": last_at.isoformat(),
        }

    def test_stats_total_aggregated_falls_back_to_count_when_none(self):
        # r[2] (total_aggregated) 为 None 时回退用 r[1] (total_alarms)
        db = MagicMock()
        first_at = datetime(2026, 1, 1, 10, 0, 0)
        last_at = datetime(2026, 1, 1, 10, 5, 0)
        rows = [(2, 7, None, first_at, last_at)]
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows
        stats = aa.get_aggregation_stats(device_id=1, db=db)
        assert stats[0]["total_aggregated"] == 7

    def test_stats_handles_none_timestamps(self):
        db = MagicMock()
        rows = [(3, 1, 1, None, None)]
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows
        stats = aa.get_aggregation_stats(device_id=1, db=db)
        assert stats[0]["first_at"] is None
        assert stats[0]["last_at"] is None

    def test_stats_empty(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        assert aa.get_aggregation_stats(device_id=1, db=db) == []


# ═══════════════════════════════════════════
# 异常分支 — 各 except 兜底 (告警域宁可多发不漏发)
# ═══════════════════════════════════════════

def _raise_runtime(*args, **kwargs):
    raise RuntimeError("forced failure")


class TestExceptionBranches:
    def test_clean_storm_counters_swallows_items_error(self, monkeypatch):
        """_clean_storm_counters: items() 抛 → except 吞掉, 不外泄。"""
        class _BoomItems(dict):
            def items(self):
                raise RuntimeError("items boom")
        monkeypatch.setattr(aa, "_storm_counters", _BoomItems())
        aa._clean_storm_counters()  # 不应抛

    def test_check_anti_storm_swallows_setitem_error_and_returns_true(self, monkeypatch):
        """check_anti_storm: __setitem__ 抛 → except → 放行 True (宁可多发不漏发)。"""
        class _BoomSet(dict):
            def __setitem__(self, k, v):
                raise RuntimeError("setitem boom")
        monkeypatch.setattr(aa, "_storm_counters", _BoomSet())
        assert aa.check_anti_storm(device_id=1, rule_id=1) is True

    def test_find_aggregatable_swallows_db_error(self):
        """find_aggregatable_alarm: db.query 抛 → except → None。"""
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert aa.find_aggregatable_alarm(device_id=1, rule_id=2, db=db) is None

    def test_update_aggregated_swallows_commit_error_and_rolls_back(self):
        """update_aggregated_alarm: commit 抛 → except → rollback + 返回原 alarm。"""
        db = MagicMock()
        db.commit.side_effect = RuntimeError("commit failed")
        alarm = Alarm(id=1, aggregation_count=1, trigger_value=1.0)
        result = aa.update_aggregated_alarm(alarm, current_value=2.0, db=db)
        assert result is alarm
        db.rollback.assert_called_once()

    def test_update_aggregated_swallows_rollback_failure(self):
        """update_aggregated_alarm: commit 抛 + rollback 也抛 → 仍返回原 alarm。"""
        db = MagicMock()
        db.commit.side_effect = RuntimeError("commit failed")
        db.rollback.side_effect = RuntimeError("rollback also failed")
        alarm = Alarm(id=1, aggregation_count=1, trigger_value=1.0)
        result = aa.update_aggregated_alarm(alarm, current_value=2.0, db=db)
        assert result is alarm

    def test_try_aggregate_fallback_init_on_check_exception(self, monkeypatch):
        """try_aggregate_alarm: check_anti_storm 抛 → 外层 except → 兜底初始化 + commit。"""
        monkeypatch.setattr(aa, "check_anti_storm", _raise_runtime)
        db = MagicMock()
        new_alarm = Alarm(id=1, device_id=1, rule_id=10, trigger_value=50.0)
        result = aa.try_aggregate_alarm(new_alarm, db)
        assert result is None
        assert new_alarm.aggregation_count == 1
        assert new_alarm.aggregation_first_at is not None
        assert new_alarm.aggregation_last_at is not None
        db.commit.assert_called_once()

    def test_try_aggregate_fallback_rollback_on_commit_failure(self, monkeypatch):
        """try_aggregate_alarm: 兜底阶段 commit 再抛 → 内层 except → rollback。"""
        monkeypatch.setattr(aa, "check_anti_storm", _raise_runtime)
        db = MagicMock()
        db.commit.side_effect = RuntimeError("commit failed")
        new_alarm = Alarm(id=1, device_id=1, rule_id=10, trigger_value=50.0)
        result = aa.try_aggregate_alarm(new_alarm, db)
        assert result is None
        db.rollback.assert_called_once()

    def test_get_aggregation_stats_swallows_db_error(self):
        """get_aggregation_stats: db.query 抛 → except → 返回空列表。"""
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert aa.get_aggregation_stats(device_id=1, db=db) == []


# ═══════════════════════════════════════════
# SUPPRESSED 哨兵契约 (卡 2779d516)
# ═══════════════════════════════════════════

def test_suppressed_sentinel_is_unique_object():
    """SUPPRESSED 是模块级唯一哨兵, 不可与任何 Alarm 混淆 (id 判定安全)。"""
    assert isinstance(aa.SUPPRESSED, object)
    assert not isinstance(aa.SUPPRESSED, Alarm)
    assert aa.SUPPRESSED is not Alarm(id=123)
