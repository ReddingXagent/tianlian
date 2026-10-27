#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警规则服务 - 隔离单元测试 (MagicMock 隔离 DB)

被测: app/services/alarm_rule_service.py
设计: 纯逻辑方法直测; DB 依赖 (Session / SessionLocal / notification_dispatcher)
       全部用 MagicMock/patch 隔离, 不触碰真实数据库。
覆盖:
- _check_threshold          六种操作符 + 未知操作符 + TypeError 兜底
- get_level_info            四级策略 + 未知级别回落 INFO
- AlarmLevelInfo            should_create_workorder 规则覆盖语义 + get_workorder_level 映射
- _get_notify_channels / _get_response_time_for_level
- evaluate_single_rule      规则不存在
- _get_silenced_devices     无沉默期 / 有沉默期
- _get_target_device_ids    指定设备 / 类型+站点
- escalate_alarm_by_id      不存在 / 已最高级
- _escalate_single          超时升级 / 未超时
- evaluate_device           规则不存在 / 无遥测
- evaluate_all              空规则集
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.alarm import AlarmLevel
from app.services.alarm_rule_service import (
    AlarmLevelInfo,
    AlarmRuleEngine,
    LEVEL_CONFIG,
    engine,
    evaluate_all_rules,
    get_level_info,
    scan_and_escalate,
)


# ─────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────

def _self_query():
    """构造自链式 query mock: filter/group_by/order_by/join/limit/offset 都返回自身。

    limit/offset 自链是 evaluate_all 分批查询 (卡 138...) 必需: 缺则 .limit().offset()
    返回新 MagicMock, .all() 取到 truthy 默认值 -> while 分批循环永不 break (死循环)。
    """
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.join.return_value = q
    q.limit.return_value = q
    q.offset.return_value = q
    return q


def _rule(**kw):
    """构造 AlarmRule 替身。"""
    r = MagicMock()
    r.auto_create_workorder = kw.get("auto_create_workorder", None)
    return r


# ═══════════════════════════════════════════════════════════
# 1. _check_threshold 纯逻辑
# ═══════════════════════════════════════════════════════════

class TestCheckThreshold:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_greater_than(self):
        assert self.eng._check_threshold(10, ">", 5) is True
        assert self.eng._check_threshold(5, ">", 5) is False

    def test_greater_equal(self):
        assert self.eng._check_threshold(5, ">=", 5) is True
        assert self.eng._check_threshold(4, ">=", 5) is False

    def test_less_than(self):
        assert self.eng._check_threshold(3, "<", 5) is True
        assert self.eng._check_threshold(5, "<", 5) is False

    def test_less_equal(self):
        assert self.eng._check_threshold(5, "<=", 5) is True
        assert self.eng._check_threshold(6, "<=", 5) is False

    def test_equal_accepts_both_forms(self):
        assert self.eng._check_threshold(5, "==", 5) is True
        assert self.eng._check_threshold(5, "=", 5) is True
        assert self.eng._check_threshold(4, "==", 5) is False

    def test_not_equal_accepts_both_forms(self):
        assert self.eng._check_threshold(4, "!=", 5) is True
        assert self.eng._check_threshold(4, "<>", 5) is True
        assert self.eng._check_threshold(5, "!=", 5) is False

    def test_unknown_operator_returns_false(self):
        assert self.eng._check_threshold(10, "between", 5) is False
        assert self.eng._check_threshold(10, "approx", 5) is False

    def test_type_error_returns_false(self):
        # None 与数值比较在 py3 抛 TypeError -> 兜底 False
        assert self.eng._check_threshold(None, ">", 5) is False
        assert self.eng._check_threshold(5, "<", None) is False

    # ---- 缺陷1 (告警风暴): != / == 对混合类型不抛异常, 需 fail-closed 数值校验 ----

    def test_not_equal_with_string_metric_does_not_trigger(self):
        # 字符串遥测 status='offline' + != 规则: py3 不抛 TypeError, 'offline' != 80.0 静默 True
        # 修复后 fail-closed: value 非数值 -> 不触发
        assert self.eng._check_threshold("offline", "!=", 80.0) is False
        assert self.eng._check_threshold("offline", "==", 80.0) is False
        assert self.eng._check_threshold("offline", "<>", 80.0) is False

    def test_not_equal_with_none_threshold_does_not_trigger(self):
        # threshold 列为 NULL 时 value != None -> True, 任何遥测都触发告警风暴
        assert self.eng._check_threshold(80.0, "!=", None) is False
        assert self.eng._check_threshold(80.0, "==", None) is False

    def test_nan_does_not_trigger_any_operator(self):
        # NaN 与任何值的大小比较均 False, 但 != 例外返回 True; 两端 NaN 都须拦
        nan = float("nan")
        for op in (">", ">=", "<", "<=", "==", "=", "!=", "<>"):
            assert self.eng._check_threshold(nan, op, 80) is False
            assert self.eng._check_threshold(80, op, nan) is False

    def test_bool_values_not_treated_as_numbers(self):
        # bool 是 int 子类, 不应参与数值比较 (True > 0 会误触发告警)
        assert self.eng._check_threshold(True, ">", 0) is False
        assert self.eng._check_threshold(False, "<", 1) is False
        assert self.eng._check_threshold(1, "==", True) is False


# ═══════════════════════════════════════════════════════════
# 2. 级别策略 (AlarmLevelInfo / get_level_info)
# ═══════════════════════════════════════════════════════════

class TestLevelStrategy:
    def test_get_level_info_returns_all_known_levels(self):
        for level in (AlarmLevel.INFO, AlarmLevel.WARNING,
                      AlarmLevel.CRITICAL, AlarmLevel.FATAL):
            info = get_level_info(level)
            assert isinstance(info, AlarmLevelInfo)
            assert info.level == level
            assert LEVEL_CONFIG[level] is info

    def test_get_level_info_unknown_falls_back_to_info(self):
        info = get_level_info("not-a-level")  # type: ignore[arg-type]
        assert info is LEVEL_CONFIG[AlarmLevel.INFO]

    def test_should_create_workorder_rule_true_overrides_level(self):
        # INFO 默认 auto_workorder=False, 但规则显式开启应覆盖
        info = get_level_info(AlarmLevel.INFO)
        assert info.should_create_workorder(_rule(auto_create_workorder=True)) is True

    def test_should_create_workorder_rule_false_keeps_level_default(self):
        # CRITICAL 默认 auto_workorder=True; 规则 False 不应压过级别策略
        info = get_level_info(AlarmLevel.CRITICAL)
        assert info.should_create_workorder(_rule(auto_create_workorder=False)) is True

    def test_should_create_workorder_info_default_false(self):
        info = get_level_info(AlarmLevel.INFO)
        assert info.should_create_workorder(None) is False
        assert info.should_create_workorder(_rule(auto_create_workorder=None)) is False

    def test_get_workorder_level_mapping(self):
        assert get_level_info(AlarmLevel.CRITICAL).get_workorder_level().value == "critical"
        assert get_level_info(AlarmLevel.FATAL).get_workorder_level().value == "critical"
        assert get_level_info(AlarmLevel.WARNING).get_workorder_level().value == "warning"
        assert get_level_info(AlarmLevel.INFO).get_workorder_level().value == "info"

    def test_notify_channels_per_level(self):
        eng = AlarmRuleEngine()
        assert eng._get_notify_channels_for_level(AlarmLevel.INFO) == ["im"]
        # FATAL 渠道最多 (im + email + sms)
        assert eng._get_notify_channels_for_level(AlarmLevel.FATAL) == ["im", "email", "sms"]

    def test_response_time_per_level(self):
        eng = AlarmRuleEngine()
        assert eng._get_response_time_for_level(AlarmLevel.FATAL) == 15
        assert eng._get_response_time_for_level(AlarmLevel.INFO) == 120

    def test_should_auto_workorder_delegates_to_level_info(self):
        eng = AlarmRuleEngine()
        # CRITICAL + 规则关闭 -> 仍 True (级别默认)
        assert eng._should_auto_workorder(_rule(auto_create_workorder=False),
                                          AlarmLevel.CRITICAL) is True
        # INFO + 无规则 -> False
        assert eng._should_auto_workorder(_rule(), AlarmLevel.INFO) is False


# ═══════════════════════════════════════════════════════════
# 3. DB 隔离方法
# ═══════════════════════════════════════════════════════════

class TestEngineDbIsolated:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_evaluate_single_rule_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = self.eng.evaluate_single_rule(999, db)
        assert result["triggered"] is False
        assert result["message"] == "规则不存在"

    def test_get_silenced_devices_no_silence_period(self):
        db = MagicMock()
        rule = MagicMock()
        rule.silence_minutes = 0
        assert self.eng._get_silenced_devices(rule, [1, 2, 3], db) == set()
        db.query.assert_not_called()

    def test_get_silenced_devices_with_recent_alarms(self):
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,), (3,)]
        db.query.return_value = q

        rule = MagicMock()
        rule.id = 7
        rule.silence_minutes = 5
        silenced = self.eng._get_silenced_devices(rule, [1, 2, 3], db)
        assert silenced == {1, 3}

    def test_get_target_device_ids_specific_devices(self):
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,), (2,)]
        db.query.return_value = q

        rule = MagicMock()
        rule.device_ids = [1, 2]
        rule.device_type = None
        rule.station_ids = None
        assert self.eng._get_target_device_ids(rule, db) == [1, 2]

    def test_get_target_device_ids_by_type_and_station(self):
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(10,), (20,)]
        db.query.return_value = q

        rule = MagicMock()
        rule.device_ids = None
        rule.device_type = "inverter"
        rule.station_ids = [100]
        assert self.eng._get_target_device_ids(rule, db) == [10, 20]

    def test_escalate_alarm_by_id_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = self.eng.escalate_alarm_by_id(123, db)
        assert result["success"] is False
        assert result["message"] == "告警不存在"

    def test_escalate_alarm_by_id_already_fatal(self):
        db = MagicMock()
        alarm = MagicMock()
        alarm.level = AlarmLevel.FATAL
        db.query.return_value.filter.return_value.first.return_value = alarm
        result = self.eng.escalate_alarm_by_id(123, db)
        assert result["success"] is False
        assert "最高级别" in result["message"]

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_escalate_single_warning_timeout_upgrades_to_critical(self, _disp):
        now = datetime(2026, 1, 1, 12, 0, 0)
        alarm = MagicMock()
        alarm.id = 1
        alarm.device_id = 10
        alarm.level = AlarmLevel.WARNING
        alarm.original_level = None
        alarm.content = "原始告警"
        alarm.rule_id = None  # 跳过规则查询
        alarm.created_at = now - timedelta(minutes=40)  # 超过默认 30 分钟

        db = MagicMock()
        result = self.eng._escalate_single(alarm, now, db)

        assert result is not None
        assert result["from_level"] == "warning"
        assert result["to_level"] == "critical"
        assert result["elapsed_minutes"] == 40
        assert alarm.level == AlarmLevel.CRITICAL
        assert alarm.original_level == "warning"
        db.commit.assert_called()

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_escalate_single_not_timed_out_returns_none(self, _disp):
        now = datetime(2026, 1, 1, 12, 0, 0)
        alarm = MagicMock()
        alarm.level = AlarmLevel.WARNING
        alarm.rule_id = None
        alarm.original_level = None
        alarm.created_at = now - timedelta(minutes=10)  # 未到 30 分钟
        db = MagicMock()
        assert self.eng._escalate_single(alarm, now, db) is None
        db.commit.assert_not_called()

    def test_escalate_single_no_created_at_returns_none(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        alarm = MagicMock()
        alarm.level = AlarmLevel.WARNING
        alarm.rule_id = None
        alarm.created_at = None
        db = MagicMock()
        assert self.eng._escalate_single(alarm, now, db) is None

    def test_evaluate_device_rule_not_found_or_disabled(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = self.eng.evaluate_device(1, 999, db)
        assert result["triggered"] is False
        assert result["message"] == "规则不存在或已禁用"

    def test_evaluate_device_no_telemetry(self):
        db = MagicMock()
        rule = MagicMock()
        rule.id = 1
        rule.enabled = True
        rule.metric = "battery_temperature"
        rule.operator = ">"
        rule.threshold = 50
        rule.level = AlarmLevel.WARNING
        # 第一条 query: AlarmRule; 第二条 query: Telemetry
        rule_q = _self_query()
        rule_q.first.return_value = rule
        telemetry_q = _self_query()
        telemetry_q.first.return_value = None
        db.query.side_effect = [rule_q, telemetry_q]

        result = self.eng.evaluate_device(1, 1, db)
        assert result["triggered"] is False
        assert result["message"] == "设备无遥测数据"

    @patch.object(AlarmRuleEngine, "_get_latest_telemetry_all", return_value={})
    def test_evaluate_all_empty_rules_returns_empty_list(self, _telem):
        db = MagicMock()
        rules_q = _self_query()
        rules_q.all.return_value = []  # 无启用规则 -> while 首轮即 break
        db.query.return_value = rules_q

        result = self.eng.evaluate_all(db)
        assert result == []

    def test_global_engine_instance_callable(self):
        # 确认模块级单例可调用且为 AlarmRuleEngine
        assert isinstance(engine, AlarmRuleEngine)
        assert callable(engine._check_threshold)


# ─────────────────────────────────────────────────────────
# 额外辅助 (DB 隔离测试用)
# ─────────────────────────────────────────────────────────

def _full_rule(**kw):
    """构造完整 AlarmRule 替身 (含 _create_alarm/_evaluate_rule 所需全部字段)。"""
    r = MagicMock()
    r.id = kw.get("id", 1)
    r.name = kw.get("name", "高温告警")
    r.metric = kw.get("metric", "battery_temperature")
    r.operator = kw.get("operator", ">")
    r.threshold = kw.get("threshold", 50)
    r.level = kw.get("level", AlarmLevel.INFO)
    r.alarm_template = kw.get("alarm_template", None)
    r.silence_minutes = kw.get("silence_minutes", 0)
    r.device_ids = kw.get("device_ids", None)
    r.device_type = kw.get("device_type", None)
    r.station_ids = kw.get("station_ids", None)
    r.auto_create_workorder = kw.get("auto_create_workorder", False)
    r.escalation_timeout_minutes = kw.get("escalation_timeout_minutes", None)
    return r


def _dev(**kw):
    """构造 Device 替身。"""
    d = MagicMock()
    d.id = kw.get("id", 1)
    d.station_id = kw.get("station_id", 5)
    d.name = kw.get("name", "逆变器#1")
    return d


def _tel(**kw):
    """构造遥测替身 (SimpleNamespace: 缺失属性 getattr 返回 None 而非 mock)。"""
    return SimpleNamespace(**kw)


def _no_merge_agg(new_alarm, db):
    """模拟 try_aggregate_alarm「不聚合」分支: 初始化聚合计数并返回 None。"""
    new_alarm.aggregation_count = 1
    return None


# ═══════════════════════════════════════════════════════════
# 4. _create_alarm (含聚合 / 模板渲染 / 工单 / 自愈)
# ═══════════════════════════════════════════════════════════

class TestCreateAlarm:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def _db_with_device(self):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = _dev()
        db.query.return_value = q
        return db

    def test_no_aggregation_renders_default_template(self):
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   side_effect=_no_merge_agg), \
             patch("app.services.healing_engine.healing_engine") as heal, \
             patch.object(self.eng, "_maybe_create_workorder") as wo:
            heal.evaluate_alarm.return_value = {"status": "ok"}
            rule = _full_rule(level=AlarmLevel.INFO)
            db = self._db_with_device()

            alarm = self.eng._create_alarm(rule, 1, 80, db)

            assert alarm is not None
            # 默认模板渲染了 metric / value
            assert "battery_temperature" in alarm.content
            assert "80" in alarm.content
            # Alarm + AlarmRuleLog 两次 add
            assert db.add.call_count == 2
            db.commit.assert_called()
            wo.assert_not_called()  # INFO 默认不建工单
            heal.evaluate_alarm.assert_called_once()

    def test_custom_template_rendered(self):
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   side_effect=_no_merge_agg), \
             patch("app.services.healing_engine.healing_engine") as heal:
            heal.evaluate_alarm.return_value = None
            rule = _full_rule(
                level=AlarmLevel.INFO,
                alarm_template="{rule_name}@{device_name}: {metric}{operator}{threshold}",
            )
            db = self._db_with_device()

            alarm = self.eng._create_alarm(rule, 1, 80, db)
            assert alarm.content == "高温告警@逆变器#1: battery_temperature>50"

    def test_aggregated_to_existing_deletes_new_alarm(self):
        aggregated = MagicMock()
        aggregated.id = 999
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   return_value=aggregated):
            rule = _full_rule(level=AlarmLevel.CRITICAL)
            db = self._db_with_device()

            result = self.eng._create_alarm(rule, 1, 80, db)

            assert result is aggregated
            db.delete.assert_called_once()  # 删除新创建的告警
            db.commit.assert_called()

    def test_critical_level_triggers_workorder(self):
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   side_effect=_no_merge_agg), \
             patch("app.services.healing_engine.healing_engine") as heal, \
             patch.object(self.eng, "_maybe_create_workorder") as wo:
            heal.evaluate_alarm.return_value = None
            rule = _full_rule(level=AlarmLevel.CRITICAL)
            db = self._db_with_device()

            self.eng._create_alarm(rule, 1, 80, db)
            wo.assert_called_once()

    def test_healing_exception_is_swallowed(self):
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   side_effect=_no_merge_agg), \
             patch("app.services.healing_engine.healing_engine") as heal:
            heal.evaluate_alarm.side_effect = RuntimeError("boom")
            rule = _full_rule(level=AlarmLevel.INFO)
            db = self._db_with_device()

            alarm = self.eng._create_alarm(rule, 1, 80, db)  # 不应抛出
            assert alarm is not None

    # ---- 缺陷2 (规则静默死): 坏模板回落默认, 规则继续评估 ----

    def test_bad_template_unknown_placeholder_falls_back(self):
        # 未知占位符 {device_id}/{foo} 抛 KeyError; 修复后回落默认模板, 告警仍创建
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   side_effect=_no_merge_agg), \
             patch("app.services.healing_engine.healing_engine") as heal:
            heal.evaluate_alarm.return_value = None
            rule = _full_rule(level=AlarmLevel.INFO,
                              alarm_template="设备{device_id}异常 {foo}")
            db = self._db_with_device()

            alarm = self.eng._create_alarm(rule, 1, 80, db)  # 不应抛出

            assert alarm is not None
            # 回落到默认模板 (含 metric/value, 不含未渲染占位符)
            assert "battery_temperature" in alarm.content
            assert "80" in alarm.content
            assert "{device_id}" not in alarm.content
            db.add.assert_called()  # 告警 + 日志仍落库

    def test_bad_template_literal_brace_falls_back(self):
        # 字面花括号 { 抛 ValueError -> 同样回落默认模板
        with patch("app.services.alarm_rule_service.try_aggregate_alarm",
                   side_effect=_no_merge_agg), \
             patch("app.services.healing_engine.healing_engine") as heal:
            heal.evaluate_alarm.return_value = None
            rule = _full_rule(level=AlarmLevel.INFO,
                              alarm_template="异常 {value} 未闭合 {")
            db = self._db_with_device()

            alarm = self.eng._create_alarm(rule, 1, 80, db)

            assert alarm is not None
            assert "battery_temperature" in alarm.content
            assert "80" in alarm.content


# ═══════════════════════════════════════════════════════════
# 5. _maybe_create_workorder (成功 / 异常回滚)
# ═══════════════════════════════════════════════════════════

class TestMaybeCreateWorkorder:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_success_adds_workorder_and_commits(self):
        from app.models.workorder import WorkOrder
        rule = _full_rule(level=AlarmLevel.CRITICAL)
        alarm = MagicMock()
        alarm.id = 1
        db = MagicMock()

        self.eng._maybe_create_workorder(alarm, rule, 1, 5, "过温", db)

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, WorkOrder)
        assert added.device_id == 1
        db.commit.assert_called_once()
        db.rollback.assert_not_called()

    def test_exception_rolls_back_and_swallows(self):
        rule = _full_rule(level=AlarmLevel.CRITICAL)
        alarm = MagicMock()
        alarm.id = 1
        db = MagicMock()
        db.commit.side_effect = RuntimeError("commit fail")

        self.eng._maybe_create_workorder(alarm, rule, 1, 5, "过温", db)  # 不抛
        db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════
# 6. _evaluate_rule (各分支)
# ═══════════════════════════════════════════════════════════

class TestEvaluateRule:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_no_target_devices_returns_not_triggered(self):
        rule = _full_rule()
        db = MagicMock()
        q = _self_query()
        q.all.return_value = []  # 无目标设备
        db.query.return_value = q

        result = self.eng._evaluate_rule(rule, db, {})
        assert result["triggered"] is False
        assert result["devices"] == []

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    @patch("app.services.healing_engine.healing_engine")
    @patch("app.services.alarm_rule_service.try_aggregate_alarm")
    def test_triggered_creates_alarm_and_dispatches(self, agg, heal, disp):
        agg.side_effect = _no_merge_agg
        rule = _full_rule(operator=">", threshold=50,
                          level=AlarmLevel.WARNING, silence_minutes=0)
        rule.device_ids = [1]
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,)]          # _get_target_device_ids
        q.first.return_value = _dev()        # _create_alarm 内 Device 查询
        db.query.return_value = q
        latest = {1: _tel(battery_temperature=80)}

        result = self.eng._evaluate_rule(rule, db, latest)

        assert result["triggered"] is True
        assert len(result["devices"]) == 1
        assert result["devices"][0]["value"] == 80
        assert result["devices"][0]["aggregated"] is False
        disp.dispatch_on_alarm.assert_called_once()

    def test_no_telemetry_for_device_continues(self):
        rule = _full_rule()
        rule.device_ids = [1]
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,)]
        db.query.return_value = q

        result = self.eng._evaluate_rule(rule, db, {})  # 无遥测
        assert result["triggered"] is False

    def test_metric_none_continues(self):
        rule = _full_rule(metric="battery_temperature")
        rule.device_ids = [1]
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,)]
        db.query.return_value = q
        latest = {1: _tel(other_metric=10)}  # 缺 battery_temperature

        result = self.eng._evaluate_rule(rule, db, latest)
        assert result["triggered"] is False

    def test_below_threshold_continues(self):
        rule = _full_rule(operator=">", threshold=50)
        rule.device_ids = [1]
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,)]
        db.query.return_value = q
        latest = {1: _tel(battery_temperature=30)}  # 未超阈值

        result = self.eng._evaluate_rule(rule, db, latest)
        assert result["triggered"] is False

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_silenced_device_continues(self, disp):
        rule = _full_rule(operator=">", threshold=50, silence_minutes=5)
        db = MagicMock()
        q = _self_query()
        # _get_target_device_ids 与 _get_silenced_devices 共用 .all() -> 设备1在沉默期
        q.all.return_value = [(1,)]
        db.query.return_value = q
        latest = {1: _tel(battery_temperature=80)}  # 本应触发

        result = self.eng._evaluate_rule(rule, db, latest)
        assert result["triggered"] is False
        disp.dispatch_on_alarm.assert_not_called()


# ═══════════════════════════════════════════════════════════
# 7. evaluate_single_rule (规则命中路径)
# ═══════════════════════════════════════════════════════════

class TestEvaluateSingleRule:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_rule_found_runs_evaluate(self):
        rule = _full_rule(operator=">", threshold=50)
        rule.device_ids = [1]
        rule_q = _self_query()
        rule_q.first.return_value = rule
        subq_q = _self_query()
        subq_q.subquery.return_value = MagicMock()
        join_q = _self_query()
        join_q.all.return_value = []          # 无最新遥测
        target_q = _self_query()
        target_q.all.return_value = [(1,)]    # _get_target_device_ids

        db = MagicMock()
        db.query.side_effect = [rule_q, subq_q, join_q, target_q]

        result = self.eng.evaluate_single_rule(1, db)
        assert result["rule_id"] == 1
        assert result["triggered"] is False   # 无遥测 -> 未触发


# ═══════════════════════════════════════════════════════════
# 8. evaluate_all (SessionLocal/异常/结果聚合)
# ═══════════════════════════════════════════════════════════

class TestEvaluateAll:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch.object(AlarmRuleEngine, "_get_latest_telemetry_all", return_value={})
    @patch("app.services.alarm_rule_service.SessionLocal")
    def test_no_db_opens_and_closes_session(self, sl, _telem):
        sess = MagicMock()
        sl.return_value = sess
        rules_q = _self_query()
        rules_q.all.return_value = []  # 无规则 -> while 首轮 break
        sess.query.return_value = rules_q

        result = self.eng.evaluate_all(None)

        sl.assert_called_once()
        sess.close.assert_called_once()
        assert result == []

    @patch.object(AlarmRuleEngine, "_get_latest_telemetry_all", return_value={})
    @patch.object(AlarmRuleEngine, "_evaluate_rule")
    def test_rule_results_appended(self, eval_rule, _telem):
        eval_rule.return_value = {"rule_id": 1, "triggered": True}
        rule = _full_rule()
        db = MagicMock()
        rules_q = _self_query()
        rules_q.all.side_effect = [[rule], []]
        db.query.return_value = rules_q

        result = self.eng.evaluate_all(db)
        assert len(result) == 1
        assert result[0]["triggered"] is True

    @patch.object(AlarmRuleEngine, "_get_latest_telemetry_all", return_value={})
    @patch.object(AlarmRuleEngine, "_evaluate_rule", side_effect=RuntimeError("boom"))
    def test_rule_exception_appends_error_result(self, eval_rule, _telem):
        rule = _full_rule(id=7, name="坏规则")
        db = MagicMock()
        rules_q = _self_query()
        rules_q.all.side_effect = [[rule], []]
        db.query.return_value = rules_q

        result = self.eng.evaluate_all(db)
        assert result[0]["triggered"] is False
        assert result[0]["error"]            # 含异常信息
        assert result[0]["rule_id"] == 7


# ═══════════════════════════════════════════════════════════
# 9. scan_and_escalate (SessionLocal/升级/异常)
# ═══════════════════════════════════════════════════════════

class TestScanAndEscalate:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch("app.services.alarm_rule_service.SessionLocal")
    def test_no_db_opens_and_closes_session(self, sl):
        sess = MagicMock()
        sl.return_value = sess
        q = _self_query()
        q.all.return_value = []
        sess.query.return_value = q

        result = self.eng.scan_and_escalate(None)

        sl.assert_called_once()
        sess.close.assert_called_once()
        assert result == []

    @patch.object(AlarmRuleEngine, "_escalate_single")
    def test_escalates_pending_alarms(self, esc):
        alarm = MagicMock()
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [alarm]
        db.query.return_value = q
        esc.return_value = {"alarm_id": 1, "to_level": "critical"}

        result = self.eng.scan_and_escalate(db)
        assert len(result) == 1
        esc.assert_called_once()

    def test_exception_returns_empty_list(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert self.eng.scan_and_escalate(db) == []

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_scan_escalates_already_escalated_critical_to_fatal(self, disp):
        # 缺陷3 方案A: 已升级到 CRITICAL(escalated_from 非空)在扫描路径仍可达, 继续升 FATAL
        # 原 filter escalated_from.is_(None) 会排除此类告警 -> CRITICAL→FATAL 是死代码
        now = datetime(2026, 1, 1, 12, 0, 0)
        alarm = SimpleNamespace(
            id=7, device_id=10, level=AlarmLevel.CRITICAL, rule_id=None,
            original_level="warning", escalated_from="warning→critical",
            created_at=now - timedelta(minutes=120),
            escalated_at=now - timedelta(minutes=20),  # CRITICAL 停留 20min >= 15
            content="原始",
        )
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [alarm]
        db.query.return_value = q

        result = self.eng.scan_and_escalate(db)
        assert len(result) == 1
        assert result[0]["to_level"] == "fatal"
        assert alarm.level == AlarmLevel.FATAL


# ═══════════════════════════════════════════════════════════
# 10. _escalate_single (规则超时 / CRITICAL→FATAL)
# ═══════════════════════════════════════════════════════════

class TestEscalateSingleExtra:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_warning_uses_rule_escalation_timeout(self, disp):
        now = datetime(2026, 1, 1, 12, 0, 0)
        rule = MagicMock()
        rule.escalation_timeout_minutes = 10
        rule_q = _self_query()
        rule_q.first.return_value = rule
        db = MagicMock()
        db.query.return_value = rule_q

        alarm = MagicMock()
        alarm.id = 1
        alarm.device_id = 10
        alarm.level = AlarmLevel.WARNING
        alarm.rule_id = 5                    # 触发规则查询
        alarm.original_level = None
        alarm.created_at = now - timedelta(minutes=20)  # > 10 分钟

        result = self.eng._escalate_single(alarm, now, db)
        assert result is not None
        assert result["to_level"] == "critical"
        assert result["elapsed_minutes"] == 20
        db.query.assert_called()             # 命中规则查询 (line 517)

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_critical_escalates_to_fatal(self, disp):
        now = datetime(2026, 1, 1, 12, 0, 0)
        alarm = MagicMock()
        alarm.id = 2
        alarm.device_id = 20
        alarm.level = AlarmLevel.CRITICAL
        alarm.rule_id = None
        alarm.original_level = None
        alarm.created_at = now - timedelta(minutes=20)  # >= max(15, 30//2)
        db = MagicMock()

        result = self.eng._escalate_single(alarm, now, db)
        assert result is not None
        assert result["to_level"] == "fatal"
        assert alarm.level == AlarmLevel.FATAL
        disp.dispatch_on_alarm.assert_called_once()

    # ---- 缺陷3 (升级链两级, 方案A): 第二级 CRITICAL→FATAL 用 escalated_at 基准 ----

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_critical_escalation_uses_escalated_at_baseline(self, disp):
        # created_at 很久(120min) 但 escalated_at 刚 10min: 用 escalated_at 基准 → 未达 15min 不升级
        # 现状用 created_at 基准 → elapsed=120>=15 会误升级 (RED)
        now = datetime(2026, 1, 1, 12, 0, 0)
        alarm = SimpleNamespace(
            id=2, device_id=20, level=AlarmLevel.CRITICAL, rule_id=None,
            original_level="warning", escalated_from="warning→critical",
            created_at=now - timedelta(minutes=120),
            escalated_at=now - timedelta(minutes=10),
            content="原始",
        )
        db = MagicMock()
        assert self.eng._escalate_single(alarm, now, db) is None

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_two_level_escalation_chain(self, disp):
        # 端到端两级链: WARN→CRITICAL(created_at 基准) → CRITICAL→FATAL(escalated_at 基准)
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        alarm = SimpleNamespace(
            id=7, device_id=10, level=AlarmLevel.WARNING, rule_id=None,
            original_level=None, escalated_from=None,
            created_at=t0 - timedelta(minutes=40),  # 第一级 elapsed=40>=30
            escalated_at=None, content="原始",
        )
        db = MagicMock()

        # 第一级: WARNING 超时 → CRITICAL, 记录 escalated_at
        r1 = self.eng._escalate_single(alarm, t0, db)
        assert r1 is not None and r1["to_level"] == "critical"
        assert alarm.level == AlarmLevel.CRITICAL
        assert alarm.escalated_at == t0

        # 第二级: 推进 20 分钟, CRITICAL 超时(escalated_at 基准 elapsed=20>=15) → FATAL
        t1 = t0 + timedelta(minutes=20)
        r2 = self.eng._escalate_single(alarm, t1, db)
        assert r2 is not None and r2["to_level"] == "fatal"
        assert alarm.level == AlarmLevel.FATAL

    # ---- 缺陷4 (falsy-zero): 显式0=立即升级, 仅 None 回落 30 ----

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_explicit_zero_timeout_escalates_immediately(self, disp):
        # escalation_timeout_minutes=0 → 超时0分钟即满足, 立即升级
        # 现状 `if rule and rule.escalation_timeout_minutes` 把 0 吞成 30 -> 0<30 不升级 (RED)
        now = datetime(2026, 1, 1, 12, 0, 0)
        rule = MagicMock()
        rule.escalation_timeout_minutes = 0
        rule_q = _self_query()
        rule_q.first.return_value = rule
        db = MagicMock()
        db.query.return_value = rule_q

        alarm = SimpleNamespace(
            id=1, device_id=10, level=AlarmLevel.WARNING, rule_id=5,
            original_level=None, escalated_from=None,
            created_at=now,  # 刚创建, elapsed=0
            escalated_at=None, content="x",
        )
        result = self.eng._escalate_single(alarm, now, db)
        assert result is not None
        assert result["to_level"] == "critical"

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_none_timeout_falls_back_to_30(self, disp):
        # escalation_timeout_minutes=None → 回落默认 30 分钟 (与显式0 区分)
        now = datetime(2026, 1, 1, 12, 0, 0)
        rule = MagicMock()
        rule.escalation_timeout_minutes = None
        rule_q = _self_query()
        rule_q.first.return_value = rule
        db = MagicMock()
        db.query.return_value = rule_q

        alarm = SimpleNamespace(
            id=1, device_id=10, level=AlarmLevel.WARNING, rule_id=5,
            original_level=None, escalated_from=None,
            created_at=now - timedelta(minutes=25),  # 25 < 30
            escalated_at=None, content="x",
        )
        assert self.eng._escalate_single(alarm, now, db) is None


# ═══════════════════════════════════════════════════════════
# 11. escalate_alarm_by_id (成功 / 未达条件)
# ═══════════════════════════════════════════════════════════

class TestEscalateById:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch.object(AlarmRuleEngine, "_escalate_single")
    def test_success_returns_data(self, esc):
        alarm = MagicMock()
        alarm.level = AlarmLevel.WARNING
        db = MagicMock()
        q = _self_query()
        q.first.return_value = alarm
        db.query.return_value = q
        esc.return_value = {"alarm_id": 1, "to_level": "critical"}

        result = self.eng.escalate_alarm_by_id(1, db)
        assert result["success"] is True
        assert result["data"]["to_level"] == "critical"

    @patch.object(AlarmRuleEngine, "_escalate_single", return_value=None)
    def test_not_met_returns_failure(self, esc):
        alarm = MagicMock()
        alarm.level = AlarmLevel.WARNING
        db = MagicMock()
        q = _self_query()
        q.first.return_value = alarm
        db.query.return_value = q

        result = self.eng.escalate_alarm_by_id(1, db)
        assert result["success"] is False
        assert result["message"] == "未达到升级条件"


# ═══════════════════════════════════════════════════════════
# 12. _is_silenced (单设备沉默期)
# ═══════════════════════════════════════════════════════════

class TestIsSilenced:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_no_silence_period_returns_false(self):
        db = MagicMock()
        rule = MagicMock()
        rule.silence_minutes = 0
        assert self.eng._is_silenced(rule, 1, db) is False
        db.query.assert_not_called()

    def test_recent_alarm_returns_true(self):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = MagicMock()  # 近期有告警
        db.query.return_value = q
        rule = MagicMock()
        rule.id = 1
        rule.silence_minutes = 5
        assert self.eng._is_silenced(rule, 1, db) is True

    def test_no_recent_alarm_returns_false(self):
        db = MagicMock()
        q = _self_query()
        q.first.return_value = None
        db.query.return_value = q
        rule = MagicMock()
        rule.id = 1
        rule.silence_minutes = 5
        assert self.eng._is_silenced(rule, 1, db) is False


# ═══════════════════════════════════════════════════════════
# 13. evaluate_device (metric 缺失 / 未触发 / 触发)
# ═══════════════════════════════════════════════════════════

class TestEvaluateDeviceExtra:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_metric_missing_returns_message(self):
        rule = _full_rule(metric="battery_temperature")
        rule_q = _self_query()
        rule_q.first.return_value = rule
        tel_q = _self_query()
        tel_q.first.return_value = _tel(other=10)  # 缺目标指标
        db = MagicMock()
        db.query.side_effect = [rule_q, tel_q]

        result = self.eng.evaluate_device(1, 1, db)
        assert result["triggered"] is False
        assert "找不到指标" in result["message"]

    def test_below_threshold_returns_message(self):
        rule = _full_rule(operator=">", threshold=50)
        rule_q = _self_query()
        rule_q.first.return_value = rule
        tel_q = _self_query()
        tel_q.first.return_value = _tel(battery_temperature=30)
        db = MagicMock()
        db.query.side_effect = [rule_q, tel_q]

        result = self.eng.evaluate_device(1, 1, db)
        assert result["triggered"] is False
        assert "未触发" in result["message"]
        assert result["current_value"] == 30

    @patch("app.services.healing_engine.healing_engine")
    @patch("app.services.alarm_rule_service.try_aggregate_alarm")
    def test_triggered_creates_alarm(self, agg, heal):
        agg.side_effect = _no_merge_agg
        rule = _full_rule(operator=">", threshold=50, level=AlarmLevel.WARNING)
        rule_q = _self_query()
        rule_q.first.return_value = rule
        tel_q = _self_query()
        tel_q.first.return_value = _tel(battery_temperature=80)
        dev_q = _self_query()
        dev_q.first.return_value = _dev()
        db = MagicMock()
        db.query.side_effect = [rule_q, tel_q, dev_q]

        result = self.eng.evaluate_device(1, 1, db)
        assert result["triggered"] is True
        assert result["current_value"] == 80
        assert result["level"] == "warning"
        assert "battery_temperature" in result["content"]
        db.add.assert_called()  # 告警已创建 (未持久化故 id 为 None, 用 add 验证)


# ═══════════════════════════════════════════════════════════
# 14. 模块级入口 (evaluate_all_rules / scan_and_escalate)
# ═══════════════════════════════════════════════════════════

class TestModuleEntryPoints:
    def test_evaluate_all_rules_normal(self):
        with patch.object(engine, "evaluate_all",
                          return_value=[{"triggered": True}]) as ea:
            assert evaluate_all_rules() == [{"triggered": True}]
            ea.assert_called_once()

    def test_evaluate_all_rules_exception_returns_empty(self):
        with patch.object(engine, "evaluate_all", side_effect=RuntimeError("x")):
            assert evaluate_all_rules() == []

    def test_scan_and_escalate_entry_normal(self):
        with patch.object(engine, "scan_and_escalate",
                          return_value=[{"alarm_id": 1}]) as se:
            assert len(scan_and_escalate()) == 1
            se.assert_called_once()

    def test_scan_and_escalate_entry_exception_returns_empty(self):
        with patch.object(engine, "scan_and_escalate", side_effect=RuntimeError("x")):
            assert scan_and_escalate() == []
