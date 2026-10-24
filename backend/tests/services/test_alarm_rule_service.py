#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""告警规则服务深度测试

覆盖范围：级别策略、阈值匹配、设备定位、沉默期、规则评估主循环、
告警创建/聚合/工单、即时评估、告警升级、模块级入口函数与异常处理。

DB 隔离：使用 conftest.test_db（已 override app.core.database.SessionLocal）。
对 `evaluate_all()` / `scan_and_escalate()` 的无参分支，额外 monkeypatch
本服务模块顶层绑定的 SessionLocal（import binding 坑，见
[[service-sessionlocal-import-binding-test-pitfall]]），否则会连生产库。
外部副作用（通知分发 / 自愈评估）patch 隔离；防风暴计数器每个测试清空。
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services import alarm_rule_service as ars
from app.services.alarm_rule_service import (
    AlarmRuleEngine,
    AlarmLevelInfo,
    get_level_info,
    LEVEL_CONFIG,
    evaluate_all_rules,
    scan_and_escalate as module_scan_and_escalate,
)
from app.models.alarm import (
    Alarm,
    AlarmRule,
    AlarmRuleLog,
    AlarmLevel,
    AlarmStatus,
)
from app.models.telemetry import Telemetry
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus, WorkOrderLevel
from app.services import alarm_aggregation


# ===================== helpers =====================

def _station(db, **kw):
    defaults = dict(name="测试站A", code="S001", address="addr", status=StationStatus.NORMAL)
    defaults.update(kw)
    st = Station(**defaults)
    db.add(st); db.commit(); db.refresh(st)
    return st


def _device(db, station, **kw):
    defaults = dict(
        sn="SN-1", name="设备1", code="DEV1",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=station.id, rated_power=10.0,
    )
    defaults.update(kw)
    d = Device(**defaults)
    db.add(d); db.commit(); db.refresh(d)
    return d


def _telemetry(db, device, **kw):
    defaults = dict(device_id=device.id, timestamp=datetime.now(timezone.utc))
    defaults.update(kw)
    t = Telemetry(**defaults)
    db.add(t); db.commit(); db.refresh(t)
    return t


def _rule(db, **kw):
    defaults = dict(
        name="rule-1", description="d",
        metric="battery_temperature", operator=">", threshold=50.0,
        level=AlarmLevel.WARNING, enabled=True, silence_minutes=0,
        auto_create_workorder=False, escalation_timeout_minutes=30,
    )
    defaults.update(kw)
    r = AlarmRule(**defaults)
    db.add(r); db.commit(); db.refresh(r)
    return r


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """清空跨测试残留的防风暴计数器 + 隔离通知/自愈外部副作用。"""
    alarm_aggregation._storm_counters.clear()
    monkeypatch.setattr(
        "app.services.alarm_rule_service.notification_dispatcher.dispatch_on_alarm",
        MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.healing_engine.healing_engine.evaluate_alarm",
        MagicMock(return_value=None),
    )
    yield
    alarm_aggregation._storm_counters.clear()


# ===================== 级别策略 =====================

class TestAlarmLevelInfo:
    def test_level_config_has_four_levels(self):
        for lv in (AlarmLevel.INFO, AlarmLevel.WARNING, AlarmLevel.CRITICAL, AlarmLevel.FATAL):
            assert lv in LEVEL_CONFIG
            assert isinstance(LEVEL_CONFIG[lv], AlarmLevelInfo)

    def test_get_level_info_known(self):
        info = get_level_info(AlarmLevel.CRITICAL)
        assert info.level == AlarmLevel.CRITICAL
        assert info.priority == 3
        assert info.auto_workorder is True

    def test_get_level_info_unknown_falls_back_to_info(self):
        info = get_level_info("unknown_level")
        assert info.level == AlarmLevel.INFO

    @pytest.mark.parametrize("level,expected", [
        (AlarmLevel.CRITICAL, WorkOrderLevel.CRITICAL),
        (AlarmLevel.FATAL, WorkOrderLevel.CRITICAL),
        (AlarmLevel.WARNING, WorkOrderLevel.WARNING),
        (AlarmLevel.INFO, WorkOrderLevel.INFO),
    ])
    def test_get_workorder_level(self, level, expected):
        info = AlarmLevelInfo(
            level=level, label="x", priority=1, response_minutes=10,
            notify_channels=[], auto_workorder=False, color="black",
        )
        assert info.get_workorder_level() == expected

    def test_should_create_workorder_rule_true_overrides(self):
        info = LEVEL_CONFIG[AlarmLevel.INFO]  # auto_workorder=False
        rule = MagicMock(auto_create_workorder=True)
        assert info.should_create_workorder(rule) is True

    def test_should_create_workorder_rule_false_falls_back(self):
        info = LEVEL_CONFIG[AlarmLevel.CRITICAL]  # auto_workorder=True
        rule = MagicMock(auto_create_workorder=False)
        assert info.should_create_workorder(rule) is True  # 回落到级别默认

    def test_should_create_workorder_rule_none_falls_back(self):
        info = LEVEL_CONFIG[AlarmLevel.CRITICAL]
        rule = MagicMock(auto_create_workorder=None)
        assert info.should_create_workorder(rule) is True

    def test_should_create_workorder_no_rule_uses_level(self):
        info = LEVEL_CONFIG[AlarmLevel.INFO]
        assert info.should_create_workorder(None) is False
        info2 = LEVEL_CONFIG[AlarmLevel.FATAL]
        assert info2.should_create_workorder(None) is True


class TestLevelStrategyHelpers:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_get_notify_channels_for_level(self):
        assert self.engine._get_notify_channels_for_level(AlarmLevel.INFO) == ['im']
        assert self.engine._get_notify_channels_for_level(AlarmLevel.FATAL) == ['im', 'email', 'sms']

    def test_get_response_time_for_level(self):
        assert self.engine._get_response_time_for_level(AlarmLevel.INFO) == 120
        assert self.engine._get_response_time_for_level(AlarmLevel.FATAL) == 15

    def test_should_auto_workorder(self):
        rule = MagicMock(auto_create_workorder=True)
        assert self.engine._should_auto_workorder(rule, AlarmLevel.INFO) is True
        rule2 = MagicMock(auto_create_workorder=False)
        assert self.engine._should_auto_workorder(rule2, AlarmLevel.INFO) is False


# ===================== 阈值匹配 =====================

class TestCheckThreshold:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    @pytest.mark.parametrize("op,value,threshold,expected", [
        (">", 60, 50, True), (">", 50, 50, False),
        (">=", 50, 50, True), (">=", 49, 50, False),
        ("<", 40, 50, True), ("<", 50, 50, False),
        ("<=", 50, 50, True), ("<=", 51, 50, False),
        ("==", 50, 50, True), ("==", 51, 50, False),
        ("=", 50, 50, True),
        ("!=", 51, 50, True), ("!=", 50, 50, False),
        ("<>", 51, 50, True),
    ])
    def test_operators(self, op, value, threshold, expected):
        assert self.engine._check_threshold(value, op, threshold) is expected

    def test_invalid_operator_returns_false(self):
        assert self.engine._check_threshold(100, "~", 50) is False
        assert self.engine._check_threshold(100, "between", 50) is False

    def test_type_error_returns_false(self):
        # None 与数字比较抛 TypeError -> 兜底 False
        assert self.engine._check_threshold(None, ">", 50) is False


# ===================== 设备定位 =====================

class TestGetTargetDeviceIds:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def _seed_devices(self, db):
        st = _station(db)
        d1 = _device(db, st, sn="SN-1", code="DEV1")
        d2 = _device(db, st, sn="SN-2", code="DEV2", type=DeviceType.CHARGER_DC)
        d3 = _device(db, st, sn="SN-3", code="DEV3", type=DeviceType.BATTERY_INVERTER)
        return st, d1, d2, d3

    def test_by_device_ids(self, test_db):
        db = test_db["session"]
        st, d1, d2, d3 = self._seed_devices(db)
        rule = _rule(db, device_ids=[d2.id, d3.id], device_type=None, station_ids=None)
        ids = set(self.engine._get_target_device_ids(rule, db))
        assert ids == {d2.id, d3.id}

    def test_by_device_type(self, test_db):
        db = test_db["session"]
        st, d1, d2, d3 = self._seed_devices(db)
        rule = _rule(db, device_ids=None, device_type="charger_dc", station_ids=None)
        ids = set(self.engine._get_target_device_ids(rule, db))
        assert ids == {d2.id}

    def test_by_station_ids(self, test_db):
        db = test_db["session"]
        st, d1, d2, d3 = self._seed_devices(db)
        rule = _rule(db, device_ids=None, device_type=None, station_ids=[st.id])
        ids = set(self.engine._get_target_device_ids(rule, db))
        assert ids == {d1.id, d2.id, d3.id}

    def test_all_when_no_filter(self, test_db):
        db = test_db["session"]
        st, d1, d2, d3 = self._seed_devices(db)
        rule = _rule(db, device_ids=None, device_type=None, station_ids=None)
        ids = set(self.engine._get_target_device_ids(rule, db))
        assert ids == {d1.id, d2.id, d3.id}


# ===================== 沉默期 =====================

class TestSilencePeriod:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_get_silenced_devices_disabled(self, test_db):
        db = test_db["session"]
        rule = _rule(db, silence_minutes=0)
        assert self.engine._get_silenced_devices(rule, [1, 2], db) == set()

    def test_get_silenced_devices_in_window(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, silence_minutes=10)
        # 一条近期告警 -> 应被沉默
        db.add(Alarm(
            device_id=d.id, station_id=st.id, rule_id=rule.id,
            alarm_type="t", level=AlarmLevel.WARNING, content="c",
            status=AlarmStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        silenced = self.engine._get_silenced_devices(rule, [d.id, 999], db)
        assert d.id in silenced
        assert 999 not in silenced

    def test_is_silenced_disabled(self, test_db):
        db = test_db["session"]
        rule = _rule(db, silence_minutes=0)
        assert self.engine._is_silenced(rule, 1, db) is False

    def test_is_silenced_recent_alarm(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, silence_minutes=10)
        db.add(Alarm(
            device_id=d.id, station_id=st.id, rule_id=rule.id,
            alarm_type="t", level=AlarmLevel.WARNING, content="c",
            status=AlarmStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        assert self.engine._is_silenced(rule, d.id, db) is True
        assert self.engine._is_silenced(rule, 88888, db) is False


# ===================== 最新遥测聚合 =====================

class TestLatestTelemetry:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_get_latest_telemetry_all_picks_max_timestamp(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        old = _telemetry(db, d, battery_temperature=10.0, timestamp=datetime.now(timezone.utc) - timedelta(hours=1))
        new = _telemetry(db, d, battery_temperature=90.0, timestamp=datetime.now(timezone.utc))
        result = self.engine._get_latest_telemetry_all(db)
        assert d.id in result
        assert result[d.id].id == new.id
        assert result[d.id].battery_temperature == 90.0


# ===================== 规则评估主循环 =====================

class TestEvaluateRule:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_no_target_devices(self, test_db):
        db = test_db["session"]
        rule = _rule(db, device_ids=None, device_type=None, station_ids=None)
        res = self.engine._evaluate_rule(rule, db, {})
        assert res["triggered"] is False
        assert res["devices"] == []

    def test_device_without_telemetry_skipped(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db)
        res = self.engine._evaluate_rule(rule, db, {})  # 最新遥测里没有 d
        assert res["triggered"] is False

    def test_metric_none_skipped(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=None)
        latest = self.engine._get_latest_telemetry_all(db)
        rule = _rule(db)
        res = self.engine._evaluate_rule(rule, db, latest)
        assert res["triggered"] is False

    def test_below_threshold_not_triggered(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=30.0)  # 30 <= 50
        latest = self.engine._get_latest_telemetry_all(db)
        rule = _rule(db, threshold=50.0)
        res = self.engine._evaluate_rule(rule, db, latest)
        assert res["triggered"] is False

    def test_triggered_creates_alarm(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        latest = self.engine._get_latest_telemetry_all(db)
        rule = _rule(db, threshold=50.0, level=AlarmLevel.WARNING)
        res = self.engine._evaluate_rule(rule, db, latest)
        assert res["triggered"] is True
        assert len(res["devices"]) == 1
        dev = res["devices"][0]
        assert dev["device_id"] == d.id
        assert dev["value"] == 80.0
        # Alarm + Log 落库
        assert db.query(Alarm).filter(Alarm.rule_id == rule.id).count() == 1
        assert db.query(AlarmRuleLog).filter(AlarmRuleLog.rule_id == rule.id).count() == 1

    def test_silenced_device_skipped(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, threshold=50.0, silence_minutes=10)
        # 预置一条近期告警 -> 沉默
        db.add(Alarm(
            device_id=d.id, station_id=st.id, rule_id=rule.id,
            alarm_type="t", level=AlarmLevel.WARNING, content="c",
            status=AlarmStatus.ACTIVE, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        _telemetry(db, d, battery_temperature=80.0)
        latest = self.engine._get_latest_telemetry_all(db)
        res = self.engine._evaluate_rule(rule, db, latest)
        assert res["triggered"] is False  # 被沉默


class TestEvaluateAll:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_with_explicit_db(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        rule = _rule(db, threshold=50.0)
        results = self.engine.evaluate_all(db)
        assert len(results) == 1
        assert results[0]["triggered"] is True

    def test_disabled_rule_skipped(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        _rule(db, threshold=50.0, enabled=False)
        results = self.engine.evaluate_all(db)
        assert results == []

    def test_db_none_uses_sessionlocal(self, test_db, monkeypatch):
        """无参分支：monkeypatch 本模块顶层 SessionLocal 指向测试库。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        _rule(db, threshold=50.0)
        monkeypatch.setattr(ars, "SessionLocal", test_db["SessionLocal"])
        results = self.engine.evaluate_all()
        assert len(results) == 1
        assert results[0]["triggered"] is True

    def test_rule_exception_captured(self, test_db, monkeypatch):
        """单规则评估抛异常 -> 捕获并写入 error 字段，不影响整体。"""
        db = test_db["session"]
        rule = _rule(db, threshold=50.0)

        def boom(rule, db, latest):
            raise RuntimeError("boom")
        monkeypatch.setattr(self.engine, "_evaluate_rule", boom)
        results = self.engine.evaluate_all(db)
        assert len(results) == 1
        assert results[0]["triggered"] is False
        assert "boom" not in results[0]["error"]


# ===================== 批量加载策略 (卡 0a5b31db, 防 OOM) =====================

class TestBatchLoading:
    """分批查询防 OOM:
    - _get_latest_telemetry_all 按 device_id 分批合并 dict (替代一次 .all() 全量遥测)
    - evaluate_all 分批查规则, 不丢规则
    只改加载策略, 不改业务语义。
    """

    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_latest_telemetry_default_batch_size(self):
        """默认大批量(>=500), 小数据集一次取完, 兼容现有行为。"""
        import inspect
        sig = inspect.signature(AlarmRuleEngine._get_latest_telemetry_all)
        assert sig.parameters["batch_size"].default >= 500

    def test_latest_telemetry_batched_merge(self, test_db):
        """3 设备 batch_size=2 -> 分 2 批查, 合并后仍含全部 3 设备最新遥测。"""
        db = test_db["session"]
        st = _station(db)
        d1 = _device(db, st, sn="SN-T1", code="T1")
        d2 = _device(db, st, sn="SN-T2", code="T2")
        d3 = _device(db, st, sn="SN-T3", code="T3")
        _telemetry(db, d1, battery_temperature=10.0)
        _telemetry(db, d2, battery_temperature=20.0)
        _telemetry(db, d3, battery_temperature=30.0)
        result = self.engine._get_latest_telemetry_all(db, batch_size=2)
        assert len(result) == 3
        temps = {result[d.id].battery_temperature for d in (d1, d2, d3)}
        assert temps == {10.0, 20.0, 30.0}

    def test_latest_telemetry_picks_max_across_batches(self, test_db):
        """同设备多条遥测, 分批合并后仍取 max timestamp 那条。"""
        db = test_db["session"]
        st = _station(db)
        d1 = _device(db, st, sn="SN-M1", code="M1")
        d2 = _device(db, st, sn="SN-M2", code="M2")
        _telemetry(db, d1, battery_temperature=10.0,
                   timestamp=datetime.now(timezone.utc) - timedelta(hours=1))
        _telemetry(db, d1, battery_temperature=90.0, timestamp=datetime.now(timezone.utc))
        _telemetry(db, d2, battery_temperature=20.0)
        result = self.engine._get_latest_telemetry_all(db, batch_size=1)
        assert result[d1.id].battery_temperature == 90.0
        assert result[d2.id].battery_temperature == 20.0

    def test_evaluate_all_default_batch_size(self):
        import inspect
        sig = inspect.signature(AlarmRuleEngine.evaluate_all)
        assert sig.parameters["batch_size"].default >= 100

    def test_evaluate_all_batches_rules_without_loss(self, test_db):
        """5 条 enabled 规则 batch_size=2 -> 全部评估, 不丢规则。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        names = [f"batch-r{i}" for i in range(5)]
        for n in names:
            _rule(db, name=n, threshold=50.0)
        results = self.engine.evaluate_all(db, batch_size=2)
        assert len(results) == 5
        assert {r["rule_name"] for r in results} == set(names)

    def test_evaluate_all_disabled_rule_not_in_any_batch(self, test_db):
        """分批查仍只取 enabled 规则(兼容现有 test_disabled_rule_skipped)。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        _rule(db, name="on", threshold=50.0, enabled=True)
        _rule(db, name="off", threshold=50.0, enabled=False)
        results = self.engine.evaluate_all(db, batch_size=1)
        assert len(results) == 1
        assert results[0]["rule_name"] == "on"


class TestEvaluateSingleRule:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_rule_not_found(self, test_db):
        db = test_db["session"]
        res = self.engine.evaluate_single_rule(99999, db)
        assert res["triggered"] is False
        assert res["message"] == "规则不存在"

    def test_rule_evaluated(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        rule = _rule(db, threshold=50.0)
        res = self.engine.evaluate_single_rule(rule.id, db)
        assert res["triggered"] is True


# ===================== 告警创建 / 聚合 / 工单 =====================

class TestCreateAlarm:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_create_alarm_writes_alarm_and_log(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, alarm_template="{metric}={value}")
        alarm = self.engine._create_alarm(rule, d.id, 80.0, db)
        assert alarm.id is not None
        assert alarm.content == "battery_temperature=80.0"
        assert alarm.level == AlarmLevel.WARNING
        assert alarm.trigger_value == 80.0
        assert db.query(AlarmRuleLog).count() == 1

    def test_create_alarm_default_template(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, alarm_template=None)
        alarm = self.engine._create_alarm(rule, d.id, 80.0, db)
        assert "80.0" in alarm.content
        assert "battery_temperature" in alarm.content

    def test_create_alarm_auto_workorder_by_level(self, test_db):
        """CRITICAL 级别 auto_workorder=True -> 自动建单。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, level=AlarmLevel.CRITICAL, auto_create_workorder=False)
        alarm = self.engine._create_alarm(rule, d.id, 80.0, db)
        wos = db.query(WorkOrder).filter(WorkOrder.device_id == d.id).all()
        assert len(wos) == 1
        assert wos[0].level == WorkOrderLevel.CRITICAL
        assert wos[0].status == WorkOrderStatus.PENDING

    def test_create_alarm_no_workorder_for_warning(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, level=AlarmLevel.WARNING, auto_create_workorder=False)
        self.engine._create_alarm(rule, d.id, 80.0, db)
        assert db.query(WorkOrder).count() == 0

    def test_create_alarm_rule_override_workorder(self, test_db):
        """INFO 级别默认不建单，但 rule.auto_create_workorder=True 覆盖。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, level=AlarmLevel.INFO, auto_create_workorder=True)
        self.engine._create_alarm(rule, d.id, 80.0, db)
        assert db.query(WorkOrder).count() == 1

    def test_create_alarm_healing_success_logs(self, test_db, monkeypatch):
        """healing_engine 返回有效结果 -> 记录自愈日志（覆盖 truthy 分支）。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db)
        monkeypatch.setattr(
            "app.services.healing_engine.healing_engine.evaluate_alarm",
            MagicMock(return_value={"status": "healed"}),
        )
        alarm = self.engine._create_alarm(rule, d.id, 80.0, db)
        assert alarm.id is not None

    def test_create_alarm_healing_exception_swallowed(self, test_db, monkeypatch):
        """healing_engine 抛异常 -> 被吞掉，不影响告警创建（覆盖 except 分支）。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db)
        monkeypatch.setattr(
            "app.services.healing_engine.healing_engine.evaluate_alarm",
            MagicMock(side_effect=RuntimeError("healing boom")),
        )
        alarm = self.engine._create_alarm(rule, d.id, 80.0, db)
        assert alarm.id is not None

    def test_create_alarm_aggregates_into_existing(self, test_db):
        """窗口内已有 ACTIVE 告警 -> 聚合到旧告警，删除新告警。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, level=AlarmLevel.WARNING)
        first = self.engine._create_alarm(rule, d.id, 80.0, db)
        # 对齐时区：SQLite server_default func.now() 存 UTC，聚合窗口也用 UTC 判定,
        # 故显式覆盖 created_at 为 utcnow() 使 5 分钟窗口生效。
        first.created_at = datetime.now(timezone.utc)
        db.commit()
        # 清空防风暴计数器，避免被风暴抑制
        alarm_aggregation._storm_counters.clear()
        second = self.engine._create_alarm(rule, d.id, 85.0, db)
        # 聚合返回的是同一条告警
        assert second.id == first.id
        assert second.aggregation_count == 2
        assert second.trigger_value == 85.0
        # 只剩一条告警记录
        assert db.query(Alarm).filter(Alarm.rule_id == rule.id).count() == 1


class TestMaybeCreateWorkorder:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_exception_triggers_rollback(self, test_db, monkeypatch):
        """工单创建异常 -> rollback + 不抛出。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, level=AlarmLevel.CRITICAL)
        alarm = Alarm(
            device_id=d.id, station_id=st.id, rule_id=rule.id,
            alarm_type="t", level=AlarmLevel.CRITICAL, content="c",
            status=AlarmStatus.ACTIVE,
        )
        db.add(alarm); db.commit(); db.refresh(alarm)

        # WorkOrder 构造抛异常（构造阶段）触发 rollback 分支
        import app.models.workorder as wo_mod
        monkeypatch.setattr(wo_mod, "WorkOrder", MagicMock(side_effect=RuntimeError("wo boom")))
        # 不抛异常
        self.engine._maybe_create_workorder(alarm, rule, d.id, st.id, "c", db)
        assert db.query(WorkOrder).count() == 0


# ===================== 即时评估 =====================

class TestEvaluateDevice:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_rule_not_found_or_disabled(self, test_db):
        db = test_db["session"]
        res = self.engine.evaluate_device(1, 99999, db)
        assert res["triggered"] is False

    def test_no_telemetry(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db)
        res = self.engine.evaluate_device(d.id, rule.id, db)
        assert res["triggered"] is False
        assert res["message"] == "设备无遥测数据"

    def test_metric_none(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=None)
        rule = _rule(db)
        res = self.engine.evaluate_device(d.id, rule.id, db)
        assert res["triggered"] is False
        assert "battery_temperature" in res["message"]

    def test_below_threshold(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=30.0)
        rule = _rule(db, threshold=50.0)
        res = self.engine.evaluate_device(d.id, rule.id, db)
        assert res["triggered"] is False
        assert res["current_value"] == 30.0

    def test_triggered(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        rule = _rule(db, threshold=50.0)
        res = self.engine.evaluate_device(d.id, rule.id, db)
        assert res["triggered"] is True
        assert res["current_value"] == 80.0
        assert res["alarm_id"] is not None


# ===================== 告警升级 =====================

class TestEscalateSingle:
    def setup_method(self):
        self.engine = AlarmRuleEngine()
        self.now = datetime.now(timezone.utc)

    def _alarm(self, db, level, age_minutes, rule=None, station=None, device=None):
        st = station or _station(db)
        d = device or _device(db, st, sn=f"SN-{level.value}-{age_minutes}", code=f"C-{level.value}-{age_minutes}")
        a = Alarm(
            device_id=d.id, station_id=st.id,
            rule_id=rule.id if rule else None,
            alarm_type="t", level=level, content="c",
            status=AlarmStatus.ACTIVE,
            created_at=self.now - timedelta(minutes=age_minutes),
        )
        db.add(a); db.commit(); db.refresh(a)
        return a, st, d

    def test_warn_escalates_to_critical(self, test_db):
        db = test_db["session"]
        rule = _rule(db, escalation_timeout_minutes=30)
        a, st, d = self._alarm(db, AlarmLevel.WARNING, age_minutes=40, rule=rule)
        res = self.engine._escalate_single(a, self.now, db)
        assert res is not None
        assert res["from_level"] == "warning"
        assert res["to_level"] == "critical"
        assert a.level == AlarmLevel.CRITICAL
        assert a.escalated_from == "warning→critical"
        assert a.original_level == "warning"

    def test_warn_not_yet_timeout(self, test_db):
        db = test_db["session"]
        rule = _rule(db, escalation_timeout_minutes=30)
        a, _, _ = self._alarm(db, AlarmLevel.WARNING, age_minutes=10, rule=rule)
        assert self.engine._escalate_single(a, self.now, db) is None

    def test_critical_escalates_to_fatal(self, test_db):
        db = test_db["session"]
        rule = _rule(db, escalation_timeout_minutes=30)
        a, _, _ = self._alarm(db, AlarmLevel.CRITICAL, age_minutes=20, rule=rule)
        res = self.engine._escalate_single(a, self.now, db)
        assert res is not None
        assert res["to_level"] == "fatal"
        assert a.level == AlarmLevel.FATAL

    def test_critical_not_yet_timeout(self, test_db):
        db = test_db["session"]
        rule = _rule(db, escalation_timeout_minutes=30)
        a, _, _ = self._alarm(db, AlarmLevel.CRITICAL, age_minutes=5, rule=rule)
        assert self.engine._escalate_single(a, self.now, db) is None

    def test_default_timeout_without_rule(self, test_db):
        """无 rule -> 默认 30 分钟超时。"""
        db = test_db["session"]
        a, _, _ = self._alarm(db, AlarmLevel.WARNING, age_minutes=35, rule=None)
        res = self.engine._escalate_single(a, self.now, db)
        assert res is not None
        assert res["to_level"] == "critical"

    def test_rule_timeout_override(self, test_db):
        db = test_db["session"]
        rule = _rule(db, escalation_timeout_minutes=60)
        a, _, _ = self._alarm(db, AlarmLevel.WARNING, age_minutes=40, rule=rule)
        # 40 < 60 -> 不升级
        assert self.engine._escalate_single(a, self.now, db) is None

    def test_created_at_none_returns_none(self, test_db):
        from sqlalchemy import update
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        a = Alarm(
            device_id=d.id, station_id=st.id, alarm_type="t",
            level=AlarmLevel.WARNING, content="c", status=AlarmStatus.ACTIVE,
        )
        db.add(a); db.commit()
        # server_default=func.now() 在 commit 时已填充 created_at，
        # 显式 UPDATE 置 NULL 并过期，覆盖 created_at is None 的提前返回分支。
        db.execute(update(Alarm).where(Alarm.id == a.id).values(created_at=None))
        db.commit()
        db.expire(a)
        assert self.engine._escalate_single(a, self.now, db) is None


class TestScanAndEscalate:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_warn_escalation_in_scan(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        rule = _rule(db, escalation_timeout_minutes=30)
        db.add(Alarm(
            device_id=d.id, station_id=st.id, rule_id=rule.id,
            alarm_type="t", level=AlarmLevel.WARNING, content="c",
            status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=40),
        ))
        db.commit()
        res = self.engine.scan_and_escalate(db)
        assert len(res) == 1
        assert res[0]["to_level"] == "critical"

    def test_skips_already_escalated(self, test_db):
        # 缺陷3 方案A: 不再用 escalated_from.is_(None) 排除已升级者。
        # 已升到 FATAL(最高级)的告警由 level.in_([WARNING, CRITICAL]) 自然排除 -> 返回 []。
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        db.add(Alarm(
            device_id=d.id, station_id=st.id,
            alarm_type="t", level=AlarmLevel.FATAL, content="c",
            status=AlarmStatus.ACTIVE,
            escalated_from="critical→fatal",  # 已升到最高级
            created_at=datetime.now(timezone.utc) - timedelta(minutes=120),
        ))
        db.commit()
        assert self.engine.scan_and_escalate(db) == []

    def test_scan_escalates_critical_via_escalated_at_baseline(self, test_db):
        # 缺陷3 方案A 正向: 已升到 CRITICAL(escalated_from 非空)在扫描路径仍可达,
        # 以 escalated_at 为基准超时后继续升 FATAL (原 escalated_from.is_(None) filter 使此分支死代码)。
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        now = datetime.now(timezone.utc)
        db.add(Alarm(
            device_id=d.id, station_id=st.id,
            alarm_type="t", level=AlarmLevel.CRITICAL, content="c",
            status=AlarmStatus.ACTIVE,
            escalated_from="warning→critical",
            original_level="warning",
            created_at=now - timedelta(minutes=120),
            escalated_at=now - timedelta(minutes=20),  # CRITICAL 停留 20min >= 15
        ))
        db.commit()
        res = self.engine.scan_and_escalate(db)
        assert len(res) == 1
        assert res[0]["to_level"] == "fatal"

    def test_db_none_uses_sessionlocal(self, test_db, monkeypatch):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        db.add(Alarm(
            device_id=d.id, station_id=st.id,
            alarm_type="t", level=AlarmLevel.WARNING, content="c",
            status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=40),
        ))
        db.commit()
        monkeypatch.setattr(ars, "SessionLocal", test_db["SessionLocal"])
        res = self.engine.scan_and_escalate()
        assert len(res) == 1

    def test_exception_captured(self, test_db, monkeypatch):
        db = test_db["session"]
        monkeypatch.setattr(self.engine, "_escalate_single", MagicMock(side_effect=RuntimeError("esc boom")))
        # 有一条待扫描告警才会进入 _escalate_single
        st = _station(db); d = _device(db, st)
        db.add(Alarm(
            device_id=d.id, station_id=st.id, alarm_type="t",
            level=AlarmLevel.WARNING, content="c", status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=40),
        ))
        db.commit()
        # 不抛异常，返回 []
        assert self.engine.scan_and_escalate(db) == []


class TestEscalateAlarmById:
    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_alarm_not_found(self, test_db):
        db = test_db["session"]
        res = self.engine.escalate_alarm_by_id(99999, db)
        assert res["success"] is False

    def test_already_fatal(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        a = Alarm(
            device_id=d.id, station_id=st.id, alarm_type="t",
            level=AlarmLevel.FATAL, content="c", status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=60),
        )
        db.add(a); db.commit(); db.refresh(a)
        res = self.engine.escalate_alarm_by_id(a.id, db)
        assert res["success"] is False
        assert "最高级别" in res["message"]

    def test_not_yet_met_condition(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        a = Alarm(
            device_id=d.id, station_id=st.id, alarm_type="t",
            level=AlarmLevel.WARNING, content="c", status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(a); db.commit(); db.refresh(a)
        res = self.engine.escalate_alarm_by_id(a.id, db)
        assert res["success"] is False
        assert "未达到" in res["message"]

    def test_manual_escalate_success(self, test_db):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        a = Alarm(
            device_id=d.id, station_id=st.id, alarm_type="t",
            level=AlarmLevel.WARNING, content="c", status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=40),
        )
        db.add(a); db.commit(); db.refresh(a)
        res = self.engine.escalate_alarm_by_id(a.id, db)
        assert res["success"] is True
        assert res["data"]["to_level"] == "critical"


# ===================== 模块级入口函数 =====================

class TestModuleEntryFunctions:
    def test_evaluate_all_rules_ok(self, test_db, monkeypatch):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        _rule(db, threshold=50.0)
        monkeypatch.setattr(ars, "SessionLocal", test_db["SessionLocal"])
        monkeypatch.setattr(ars, "engine", ars.AlarmRuleEngine())
        results = evaluate_all_rules()
        assert any(r.get("triggered") for r in results)

    def test_evaluate_all_rules_swallows_exception(self, monkeypatch):
        monkeypatch.setattr(ars, "engine", MagicMock(**{"evaluate_all": MagicMock(side_effect=RuntimeError("x"))}))
        assert evaluate_all_rules() == []

    def test_module_scan_and_escalate_ok(self, test_db, monkeypatch):
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        db.add(Alarm(
            device_id=d.id, station_id=st.id, alarm_type="t",
            level=AlarmLevel.WARNING, content="c", status=AlarmStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=40),
        ))
        db.commit()
        monkeypatch.setattr(ars, "SessionLocal", test_db["SessionLocal"])
        monkeypatch.setattr(ars, "engine", ars.AlarmRuleEngine())
        res = module_scan_and_escalate()
        assert len(res) == 1

    def test_module_scan_and_escalate_swallows_exception(self, monkeypatch):
        fake_engine = MagicMock(**{"scan_and_escalate": MagicMock(side_effect=RuntimeError("x"))})
        monkeypatch.setattr(ars, "engine", fake_engine)
        assert module_scan_and_escalate() == []


# ===================== 向后兼容：基础初始化测试 =====================

class TestEngineBasics:
    def test_engine_initialization(self):
        engine = AlarmRuleEngine()
        assert engine is not None

    def test_engine_has_methods(self):
        engine = AlarmRuleEngine()
        assert callable(engine.evaluate_all)
        assert callable(engine.evaluate_single_rule)
        assert callable(engine.scan_and_escalate)


# ===================== 防风暴抑制 / 聚合窗口派发语义 (卡 2779d516) =====================

class TestStormSuppressionNoSideEffects:
    """防风暴抑制的触发不得产生任何副作用:
    - 不新建 Alarm 行 (被抑制的触发只更新已有告警计数, 不产生独立记录)
    - 不写 AlarmRuleLog
    - 不创建工单 (CRITICAL 也不建)
    - 不派发通知
    """

    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_suppressed_trigger_no_alarm_no_log_no_dispatch(self, test_db):
        """同设备+规则第 4 次触发起被防风暴抑制: 不新增告警/日志/通知。"""
        from app.services import alarm_rule_service
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        rule = _rule(db, threshold=50.0, level=AlarmLevel.INFO)
        latest = self.engine._get_latest_telemetry_all(db)

        for _ in range(3):
            self.engine._evaluate_rule(rule, db, latest)

        alarms_before = db.query(Alarm).filter(Alarm.rule_id == rule.id).count()
        logs_before = db.query(AlarmRuleLog).filter(AlarmRuleLog.rule_id == rule.id).count()
        dispatch = alarm_rule_service.notification_dispatcher.dispatch_on_alarm
        dispatch.reset_mock()

        # 第 4 次: 30s 窗口内已被防风暴抑制
        res = self.engine._evaluate_rule(rule, db, latest)

        assert res["triggered"] is True  # 阈值确实命中, 结果如实上报
        assert db.query(Alarm).filter(Alarm.rule_id == rule.id).count() == alarms_before
        assert db.query(AlarmRuleLog).filter(AlarmRuleLog.rule_id == rule.id).count() == logs_before
        dispatch.assert_not_called()

    def test_suppressed_critical_no_workorder(self, test_db):
        """CRITICAL 规则被抑制的触发不建工单 (防风暴前 3 次各建一张)。"""
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        rule = _rule(db, threshold=50.0, level=AlarmLevel.CRITICAL)
        latest = self.engine._get_latest_telemetry_all(db)

        for _ in range(3):
            self.engine._evaluate_rule(rule, db, latest)
        wo_before = db.query(WorkOrder).count()

        self.engine._evaluate_rule(rule, db, latest)  # 第 4 次, 被抑制

        assert db.query(WorkOrder).count() == wo_before


class TestAggregationWindowSingleDispatch:
    """聚合窗口 (5min) 内仅首次触发派发通知 (docstring 『5分钟内只发1条』)。"""

    def setup_method(self):
        self.engine = AlarmRuleEngine()

    def test_second_trigger_in_window_no_dispatch(self, test_db):
        """窗口内第二次触发: 告警计数聚合 +1, 但不再派发通知。"""
        from app.services import alarm_rule_service
        db = test_db["session"]
        st = _station(db); d = _device(db, st)
        _telemetry(db, d, battery_temperature=80.0)
        rule = _rule(db, threshold=50.0, level=AlarmLevel.WARNING, silence_minutes=0)
        latest = self.engine._get_latest_telemetry_all(db)
        dispatch = alarm_rule_service.notification_dispatcher.dispatch_on_alarm

        # 第一次触发 (独立告警): 派发 1 次
        res1 = self.engine._evaluate_rule(rule, db, latest)
        assert res1["triggered"] is True
        assert dispatch.call_count == 1

        # 第二次触发 (30s 防风暴窗口外: 清计数器模拟) → 落入 5min 聚合窗口
        from app.services import alarm_aggregation
        alarm_aggregation._storm_counters.clear()
        res2 = self.engine._evaluate_rule(rule, db, latest)

        assert res2["triggered"] is True
        # 聚合到已有告警: 不新增告警行, 计数 +1
        alarms = db.query(Alarm).filter(Alarm.rule_id == rule.id).all()
        assert len(alarms) == 1
        assert alarms[0].aggregation_count == 2
        # 窗口内后续触发不再派发
        assert dispatch.call_count == 1
