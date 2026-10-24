#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警规则服务 - 补充测试 (卡 3ee097b9)

被测: app/services/alarm_rule_service.py
定位: tests/test_alarm_rule_service.py 已覆盖 14 个测试类 / 主路径齐备。
       本文件只补真实缺口 —— 既有文件未触达的分支:
- _is_real_number            int/float 接受; complex/str/None/bool/NaN/inf 拒绝
- _get_latest_telemetry_all  分批合并 (distinct device_id → chunk max(ts) → join)
- _evaluate_rule             多设备同时命中 (聚合标记 aggregated True)
- _create_alarm              device=None 退化路径 (station_id=None / 设备{N} / log 缺设备名)
- _create_alarm              聚合返回自身 (aggregated.id == alarm.id) 不删除
- _maybe_create_workorder    工单号格式 (WO-yyyyMMddHHmmss-4hex) + 字段映射
- _escalate_single           WARNING/CRITICAL 两个 try 块 commit 失败回滚返回 None
- evaluate_device            fail-closed: 字符串遥测值走 _check_threshold 不触发
- _check_threshold           浮点边界 (微超 / 等于阈值配合 >= / 负数比较)
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.alarm import AlarmLevel, AlarmStatus
from app.services.alarm_rule_service import (
    AlarmRuleEngine,
    _is_real_number,
)


# ─────────────────────────────────────────────────────────
# 共享辅助 (与既有文件风格一致)
# ─────────────────────────────────────────────────────────

def _self_query():
    """自链式 query mock: filter/distinct/group_by/order_by/join/limit/offset 都返回自身。"""
    q = MagicMock()
    q.filter.return_value = q
    q.distinct.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.join.return_value = q
    q.limit.return_value = q
    q.offset.return_value = q
    return q


def _full_rule(**kw):
    """构造完整 AlarmRule 替身。"""
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


def _tel(**kw):
    """遥测替身 (SimpleNamespace: 缺失属性 getattr 返回 None)。"""
    return SimpleNamespace(**kw)


def _no_merge_agg(new_alarm, db):
    """模拟 try_aggregate_alarm「不聚合」分支。"""
    new_alarm.aggregation_count = 1
    return None


# ═══════════════════════════════════════════════════════════
# 1. _is_real_number (fail-closed 数值守卫)
# ═══════════════════════════════════════════════════════════

class TestIsRealNumber:
    def test_int_and_float_accepted(self):
        assert _is_real_number(0) is True
        assert _is_real_number(42) is True
        assert _is_real_number(-7) is True
        assert _is_real_number(3.14) is True
        assert _is_real_number(0.0) is True

    def test_bool_rejected(self):
        # bool 是 int 子类, 不应作为阈值比较对象
        assert _is_real_number(True) is False
        assert _is_real_number(False) is False

    def test_string_rejected(self):
        assert _is_real_number("80") is False
        assert _is_real_number("offline") is False

    def test_none_rejected(self):
        assert _is_real_number(None) is False

    def test_nan_and_inf_rejected(self):
        assert _is_real_number(float("nan")) is False
        assert _is_real_number(float("inf")) is False
        assert _is_real_number(float("-inf")) is False

    def test_complex_rejected(self):
        # complex 不是 numbers.Real
        assert _is_real_number(complex(1, 2)) is False

    def test_large_finite_accepted(self):
        assert _is_real_number(1e308) is True  # 仍 finite
        assert _is_real_number(1e400) is False  # 溢出为 inf


# ═══════════════════════════════════════════════════════════
# 2. _check_threshold 浮点 / 负数 / 边界
# ═══════════════════════════════════════════════════════════

class TestCheckThresholdBoundary:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_micro_exceed_triggers(self):
        # 微超阈值仍应触发 (浮点比较)
        assert self.eng._check_threshold(50.0001, ">", 50) is True
        assert self.eng._check_threshold(49.9999, "<", 50) is True

    def test_exactly_equal_with_ge_le(self):
        assert self.eng._check_threshold(50.0, ">=", 50) is True
        assert self.eng._check_threshold(50.0, "<=", 50) is True

    def test_negative_values(self):
        assert self.eng._check_threshold(-60, "<", -50) is True
        assert self.eng._check_threshold(-40, ">", -50) is True
        assert self.eng._check_threshold(-50, "==", -50) is True

    def test_mixed_int_float_compared(self):
        # int vs float 应正常比较
        assert self.eng._check_threshold(80, ">", 50.0) is True
        assert self.eng._check_threshold(80.0, ">", 50) is True


# ═══════════════════════════════════════════════════════════
# 3. _get_latest_telemetry_all (分批合并逻辑)
# ═══════════════════════════════════════════════════════════

class TestGetLatestTelemetryAll:
    """_get_latest_telemetry_all 三次 db.query 同一对象:
    1) db.query(Telemetry.device_id).distinct().all()        -> distinct device_id 列表
    2) db.query(device_id, max(ts))...subquery()             -> max 子查询 (无 .all())
    3) db.query(Telemetry).join(subq,...)...all()            -> 最新遥测行
    故 q.all 用 side_effect 按 distinct/join 顺序区分两次 .all()。
    """
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_empty_returns_empty_dict(self):
        db = MagicMock()
        q = _self_query()
        q.all.return_value = []  # distinct device_id 为空 -> 不进循环
        db.query.return_value = q
        assert self.eng._get_latest_telemetry_all(db) == {}

    def test_single_device_mapped_by_id(self):
        tel = _tel(device_id=7, battery_temperature=80)
        db = MagicMock()
        q = _self_query()
        # distinct 第一次 .all() 返回 device_id; join 第二次 .all() 返回遥测行
        q.all.side_effect = [[(7,)], [tel]]
        db.query.return_value = q

        result = self.eng._get_latest_telemetry_all(db)
        assert result == {7: tel}

    def test_multiple_devices_batched_and_merged(self):
        t1 = _tel(device_id=1, battery_temperature=80)
        t2 = _tel(device_id=2, battery_temperature=70)
        db = MagicMock()
        q = _self_query()
        q.all.side_effect = [[(1,), (2,)], [t1, t2]]
        db.query.return_value = q

        result = self.eng._get_latest_telemetry_all(db)
        assert set(result.keys()) == {1, 2}
        assert result[1] is t1
        assert result[2] is t2


# ═══════════════════════════════════════════════════════════
# 4. _evaluate_rule 多设备同时命中
# ═══════════════════════════════════════════════════════════

class TestEvaluateRuleMultiDevice:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    @patch("app.services.healing_engine.healing_engine")
    @patch("app.services.alarm_rule_service.try_aggregate_alarm")
    def test_multiple_devices_all_triggered(self, agg, heal, disp):
        agg.side_effect = _no_merge_agg
        heal.evaluate_alarm.return_value = None
        rule = _full_rule(operator=">", threshold=50,
                          level=AlarmLevel.WARNING, silence_minutes=0)
        rule.device_ids = [1, 2]
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,), (2,)]   # _get_target_device_ids
        q.first.return_value = MagicMock(station_id=5, name="逆变器")  # _create_alarm Device
        db.query.return_value = q
        latest = {
            1: _tel(battery_temperature=80),
            2: _tel(battery_temperature=90),
        }

        result = self.eng._evaluate_rule(rule, db, latest)

        assert result["triggered"] is True
        assert len(result["devices"]) == 2
        values = sorted(d["value"] for d in result["devices"])
        assert values == [80, 90]
        # 每个设备都派发通知
        assert disp.dispatch_on_alarm.call_count == 2

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    @patch("app.services.healing_engine.healing_engine")
    @patch("app.services.alarm_rule_service.try_aggregate_alarm")
    def test_partial_devices_triggered(self, agg, heal, disp):
        agg.side_effect = _no_merge_agg
        heal.evaluate_alarm.return_value = None
        rule = _full_rule(operator=">", threshold=50, silence_minutes=0)
        rule.device_ids = [1, 2, 3]
        db = MagicMock()
        q = _self_query()
        q.all.return_value = [(1,), (2,), (3,)]
        q.first.return_value = MagicMock(station_id=5, name="d")
        db.query.return_value = q
        latest = {
            1: _tel(battery_temperature=80),   # 触发
            2: _tel(battery_temperature=30),   # 未超阈值
            3: _tel(other_metric=99),          # 缺指标
        }

        result = self.eng._evaluate_rule(rule, db, latest)
        assert result["triggered"] is True
        assert len(result["devices"]) == 1
        assert result["devices"][0]["device_id"] == 1


# ═══════════════════════════════════════════════════════════
# 5. _create_alarm 退化路径 (device=None / 聚合返回自身)
# ═══════════════════════════════════════════════════════════

class TestCreateAlarmDegraded:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch("app.services.healing_engine.healing_engine")
    @patch("app.services.alarm_rule_service.try_aggregate_alarm")
    def test_device_not_found_uses_fallback_name_and_null_station(self, agg, heal):
        """设备查询返回 None: station_id=None, 模板 {device_name} 回落 '设备{N}'。"""
        agg.side_effect = _no_merge_agg
        heal.evaluate_alarm.return_value = None
        rule = _full_rule(level=AlarmLevel.INFO,
                          alarm_template="{rule_name}-{device_name}: {value}")
        db = MagicMock()
        q = _self_query()
        q.first.return_value = None  # 设备不存在
        db.query.return_value = q

        alarm = self.eng._create_alarm(rule, 42, 80, db)

        assert alarm is not None
        assert alarm.station_id is None  # 设备不存在 -> station 置空
        # device_name 占位回落 f'设备{device_id}'
        assert alarm.content == "高温告警-设备42: 80"

    @patch("app.services.healing_engine.healing_engine")
    @patch("app.services.alarm_rule_service.try_aggregate_alarm")
    def test_aggregated_returns_self_keeps_alarm(self, agg, heal):
        """聚合函数返回同一个 alarm 对象 (id 相同) → 不删除, 走完整落库+日志+自愈。"""
        agg.side_effect = _no_merge_agg  # 返回 None
        heal.evaluate_alarm.return_value = None
        rule = _full_rule(level=AlarmLevel.INFO)
        db = MagicMock()
        q = _self_query()
        q.first.return_value = MagicMock(station_id=5, name="d")
        db.query.return_value = q

        alarm = self.eng._create_alarm(rule, 1, 80, db)
        assert alarm is not None
        # 未聚合到既有告警 → 不调用 delete
        db.delete.assert_not_called()
        # Alarm + AlarmRuleLog 两次 add
        assert db.add.call_count == 2


# ═══════════════════════════════════════════════════════════
# 6. _maybe_create_workorder 工单号格式与字段
# ═══════════════════════════════════════════════════════════

class TestMaybeCreateWorkorderFormat:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_workorder_id_format_and_fields(self):
        import re
        from app.models.workorder import WorkOrder, WorkOrderStatus, WorkOrderType
        rule = _full_rule(level=AlarmLevel.CRITICAL)
        alarm = MagicMock()
        alarm.id = 1
        db = MagicMock()

        self.eng._maybe_create_workorder(alarm, rule, 7, 9, "过温", db)

        added = db.add.call_args[0][0]
        assert isinstance(added, WorkOrder)
        # WO-yyyyMMddHHmmss-4hex
        assert re.match(r"^WO-\d{14}-[0-9a-f]{4}$", added.id), added.id
        assert added.device_id == 7
        assert added.station_id == 9
        assert "[告警自动创建]" in added.fault_desc
        assert added.status == WorkOrderStatus.PENDING
        assert added.type == WorkOrderType.REPAIR
        assert added.creator_id is None  # 系统自动创建无创建人


# ═══════════════════════════════════════════════════════════
# 7. _escalate_single commit 失败回滚
# ═══════════════════════════════════════════════════════════

class TestEscalateSingleCommitFailure:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_warning_commit_failure_returns_none_and_rolls_back(self, disp):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        alarm = MagicMock()
        alarm.level = AlarmLevel.WARNING
        alarm.rule_id = None
        alarm.original_level = None
        alarm.created_at = now - timedelta(minutes=40)  # 超时
        db = MagicMock()
        db.commit.side_effect = RuntimeError("write fail")

        result = self.eng._escalate_single(alarm, now, db)

        assert result is None
        db.rollback.assert_called_once()
        # 写库失败不应派发通知
        disp.dispatch_on_alarm.assert_not_called()

    @patch("app.services.alarm_rule_service.notification_dispatcher")
    def test_critical_commit_failure_returns_none_and_rolls_back(self, disp):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        alarm = MagicMock()
        alarm.level = AlarmLevel.CRITICAL
        alarm.rule_id = None
        alarm.original_level = "warning"
        alarm.escalated_from = "warning→critical"
        alarm.escalated_at = now - timedelta(minutes=20)  # 用 escalated_at 基准超时
        alarm.created_at = now - timedelta(minutes=120)
        db = MagicMock()
        db.commit.side_effect = RuntimeError("write fail")

        result = self.eng._escalate_single(alarm, now, db)

        assert result is None
        db.rollback.assert_called_once()
        disp.dispatch_on_alarm.assert_not_called()


# ═══════════════════════════════════════════════════════════
# 8. evaluate_device fail-closed (字符串遥测值)
# ═══════════════════════════════════════════════════════════

class TestEvaluateDeviceFailClosed:
    def setup_method(self):
        self.eng = AlarmRuleEngine()

    def test_string_metric_does_not_trigger(self):
        """遥测值为字符串 (如 status='offline') + != 规则: fail-closed 不触发。

        非 None 故不命中 metric_value is None 早退; 须由 _check_threshold 守卫拦下。
        """
        rule = _full_rule(metric="status", operator="!=", threshold=80)
        rule_q = _self_query()
        rule_q.first.return_value = rule
        tel_q = _self_query()
        tel_q.first.return_value = _tel(status="offline")
        db = MagicMock()
        db.query.side_effect = [rule_q, tel_q]

        result = self.eng.evaluate_device(1, 1, db)
        assert result["triggered"] is False
        assert "未触发" in result["message"]
        # 不应尝试创建告警
        db.add.assert_not_called()
