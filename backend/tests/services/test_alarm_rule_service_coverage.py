#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alarm_rule_service.py 覆盖率补强测试（服务层直调）

聚焦 API 测试难以覆盖的内部方法 / 分支：
- AlarmLevelInfo             get_workorder_level / should_create_workorder
- get_level_info             未知级别兜底
- _get_notify_channels_for_level / _get_response_time_for_level / _should_auto_workorder
- _check_threshold           8 种操作符 + 未知操作符 + TypeError 兜底
- _get_target_device_ids     device_ids / device_type / station_ids / 无过滤
- _get_silenced_devices      沉默期开关 + 命中
- _is_silenced               开关 / 命中 / 未命中
- _create_alarm              基础创建 / 自定义模板 / 设备缺失 / 聚合合并 / 工单 / 自愈成功与异常
- _maybe_create_workorder    成功 + 异常
- _evaluate_rule             无设备 / 无遥测 / 无指标 / 未触发 / 沉默跳过 / 触发 / 聚合标记
- evaluate_all               显式 db / db=None 自建自关 / 单规则异常捕获
- evaluate_single_rule       规则不存在 / 存在
- evaluate_device            规则缺失 / 无遥测 / 无指标 / 未触发 / 触发
- scan_and_escalate          显式 db / db=None / 异常捕获
- _escalate_single           created_at 缺失 / 默认超时 / 自定义超时 / 未超时 / CRITICAL 升级
- escalate_alarm_by_id       不存在 / 已 FATAL / 成功 / 未达条件
- evaluate_all_rules / scan_and_escalate 模块入口  正常 + 异常
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services import alarm_rule_service
from app.services.alarm_rule_service import (
    AlarmRuleEngine,
    AlarmLevelInfo,
    LEVEL_CONFIG,
    get_level_info,
)
from app.models.alarm import (
    Alarm, AlarmRule, AlarmRuleLog, AlarmLevel, AlarmStatus,
)
from app.models.telemetry import Telemetry
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.workorder import WorkOrderLevel


# ========== 通用 fixtures ==========

@pytest.fixture
def engine():
    """独立引擎实例。"""
    return AlarmRuleEngine()


@pytest.fixture
def db(test_db):
    return test_db["session"]


@pytest.fixture(autouse=True)
def _stub_external(monkeypatch):
    """屏蔽外部副作用，保证确定性与速度：
    - notification_dispatcher.dispatch_on_alarm：网络 / 异步IM / 邮件
    - healing_engine.evaluate_alarm：重依赖，默认返回成功结果（覆盖成功分支）
    - try_aggregate_alarm：默认返回 None（新告警路径）；聚合合并用例单独覆写
    """
    healing = MagicMock()
    healing.evaluate_alarm.return_value = {"status": "success"}
    monkeypatch.setattr("app.services.healing_engine.healing_engine", healing)
    monkeypatch.setattr(
        alarm_rule_service.notification_dispatcher, "dispatch_on_alarm", MagicMock()
    )
    monkeypatch.setattr(alarm_rule_service, "try_aggregate_alarm", lambda *a, **k: None)


# ========== helpers ==========

def make_station(db, code="AR-ST"):
    st = Station(name=f"告警站-{code}", code=code, status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def make_device(db, station, *, sn="AR-DEV", name="告警设备",
                dtype=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE):
    dev = Device(sn=sn, name=name, code=sn, type=dtype, status=status,
                 station_id=station.id)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def make_telemetry(db, device, *, ts=None, **metrics):
    t = Telemetry(device_id=device.id, timestamp=ts or datetime.now(timezone.utc), **metrics)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def make_rule(db, **kw):
    rule = AlarmRule(
        name=kw.get("name", "测试告警规则"),
        metric=kw.get("metric", "battery_temperature"),
        operator=kw.get("operator", ">"),
        threshold=kw.get("threshold", 55.0),
        level=kw.get("level", AlarmLevel.WARNING),
        enabled=kw.get("enabled", True),
        device_type=kw.get("device_type"),
        device_ids=kw.get("device_ids"),
        station_ids=kw.get("station_ids"),
        alarm_template=kw.get("alarm_template"),
        auto_create_workorder=kw.get("auto_create_workorder"),
        silence_minutes=kw.get("silence_minutes", 0),
        escalation_timeout_minutes=kw.get("escalation_timeout_minutes"),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def make_alarm(db, *, device=None, station=None, device_id=None,
               level=AlarmLevel.WARNING, status=AlarmStatus.ACTIVE,
               rule_id=None, content="测试告警", aggregation_count=1,
               escalated_from=None, created_at=None):
    al = Alarm(
        device_id=device_id if device_id is not None else (device.id if device else 99999),
        station_id=station.id if station else None,
        rule_id=rule_id,
        alarm_type="rule_test",
        level=level,
        content=content,
        status=status,
        aggregation_count=aggregation_count,
        escalated_from=escalated_from,
    )
    if created_at is not None:
        al.created_at = created_at
    db.add(al)
    db.commit()
    db.refresh(al)
    return al


# ========== 级别配置 / 策略辅助方法 ==========

class TestLevelConfig:
    """覆盖 AlarmLevelInfo 与级别策略辅助方法（48-60, 106, 116-122, 126-127）。"""

    @pytest.mark.parametrize("level,expected", [
        (AlarmLevel.CRITICAL, WorkOrderLevel.CRITICAL),
        (AlarmLevel.FATAL, WorkOrderLevel.CRITICAL),
        (AlarmLevel.WARNING, WorkOrderLevel.WARNING),
        (AlarmLevel.INFO, WorkOrderLevel.INFO),
    ])
    def test_get_workorder_level_mapping(self, level, expected):
        info = LEVEL_CONFIG[level]
        assert info.get_workorder_level() == expected

    def test_should_create_workorder_rule_override(self):
        """rule.auto_create_workorder 非 None 时覆盖级别默认值（59）。"""
        info = LEVEL_CONFIG[AlarmLevel.INFO]  # 默认 auto_workorder=False
        rule = AlarmRule(auto_create_workorder=True)
        assert info.should_create_workorder(rule) is True

    def test_should_create_workorder_default_when_rule_none(self):
        """rule=None → 返回级别默认（60）。"""
        info = LEVEL_CONFIG[AlarmLevel.CRITICAL]  # 默认 True
        assert info.should_create_workorder(None) is True

    def test_should_create_workorder_default_when_attr_none(self):
        """rule.auto_create_workorder 为 None → 返回级别默认（60）。"""
        info = LEVEL_CONFIG[AlarmLevel.INFO]
        rule = AlarmRule(auto_create_workorder=None)
        assert info.should_create_workorder(rule) is False

    def test_should_create_workorder_rule_false_falls_back_to_level(self):
        """rule.auto_create_workorder=False（持久化默认值）→ 不覆盖级别策略，
        回落到级别默认。Bug2 修复点：旧逻辑 `is not None` 恒真致
        CRITICAL/FATAL 默认 auto_workorder=True 对 DB 规则失效。"""
        # CRITICAL 默认 auto_workorder=True：规则 False 不应压过级别策略
        critical = LEVEL_CONFIG[AlarmLevel.CRITICAL]
        assert critical.should_create_workorder(
            AlarmRule(auto_create_workorder=False)) is True
        # INFO 默认 auto_workorder=False：规则 False 回落到 False（平凡方向）
        info = LEVEL_CONFIG[AlarmLevel.INFO]
        assert info.should_create_workorder(
            AlarmRule(auto_create_workorder=False)) is False

    def test_get_level_info_unknown_falls_back_to_info(self):
        """未知级别 → 兜底 INFO 配置（106）。"""
        info = get_level_info("not-a-level")
        assert info is LEVEL_CONFIG[AlarmLevel.INFO]

    def test_get_notify_channels_for_level(self, engine):
        assert engine._get_notify_channels_for_level(AlarmLevel.FATAL) == \
            ["im", "email", "sms"]
        assert engine._get_notify_channels_for_level(AlarmLevel.INFO) == ["im"]

    def test_get_response_time_for_level(self, engine):
        assert engine._get_response_time_for_level(AlarmLevel.CRITICAL) == 30
        assert engine._get_response_time_for_level(AlarmLevel.INFO) == 120

    def test_should_auto_workorder_delegates(self, engine):
        rule = AlarmRule(auto_create_workorder=True)
        assert engine._should_auto_workorder(rule, AlarmLevel.INFO) is True
        assert engine._should_auto_workorder(None, AlarmLevel.CRITICAL) is True


# ========== _check_threshold ==========

class TestCheckThreshold:
    """覆盖 8 种操作符 + 未知操作符 + 异常兜底（283-298）。"""

    @pytest.mark.parametrize("value,op,threshold,expected", [
        (60, ">", 55, True),
        (55, ">", 55, False),
        (55, ">=", 55, True),
        (54, ">=", 55, False),
        (50, "<", 55, True),
        (55, "<=", 55, True),
        (56, "<=", 55, False),
        (55, "==", 55, True),
        (55, "=", 55, True),
        (56, "!=", 55, True),
        (55, "<>", 55, False),
    ])
    def test_operators(self, engine, value, op, threshold, expected):
        assert engine._check_threshold(value, op, threshold) is expected

    def test_unknown_operator_returns_false(self, engine):
        assert engine._check_threshold(100, "approx", 50) is False

    def test_typeerror_returns_false(self, engine):
        """不可比较类型 → TypeError → 返回 False（297）。"""
        assert engine._check_threshold({}, ">", 5) is False


# ========== _get_target_device_ids ==========

class TestGetTargetDeviceIds:
    """覆盖 device_ids / device_type / station_ids / 无过滤（268-269, 273, 277）。"""

    def test_filter_by_device_ids(self, engine, db):
        st = make_station(db, "T1")
        d1 = make_device(db, st, sn="T1-D1")
        d2 = make_device(db, st, sn="T1-D2")
        rule = make_rule(db, device_ids=[d2.id])
        assert engine._get_target_device_ids(rule, db) == [d2.id]

    def test_filter_by_device_type(self, engine, db):
        st = make_station(db, "T2")
        make_device(db, st, sn="T2-INV", dtype=DeviceType.PV_INVERTER)
        charger = make_device(db, st, sn="T2-CHG", dtype=DeviceType.CHARGER_DC)
        rule = make_rule(db, device_type=DeviceType.CHARGER_DC.value)
        assert engine._get_target_device_ids(rule, db) == [charger.id]

    def test_filter_by_station_ids(self, engine, db):
        st_a = make_station(db, "T3A")
        st_b = make_station(db, "T3B")
        a_dev = make_device(db, st_a, sn="T3-A")
        b_dev = make_device(db, st_b, sn="T3-B")
        rule = make_rule(db, station_ids=[st_b.id])
        assert set(engine._get_target_device_ids(rule, db)) == {b_dev.id}

    def test_all_devices_when_no_filter(self, engine, db):
        st = make_station(db, "T4")
        make_device(db, st, sn="T4-D1")
        make_device(db, st, sn="T4-D2")
        rule = make_rule(db)
        assert len(engine._get_target_device_ids(rule, db)) == 2


# ========== _get_silenced_devices ==========

class TestGetSilencedDevices:
    """覆盖沉默期开关与命中（251-260）。"""

    def test_no_silence_returns_empty(self, engine, db):
        rule = make_rule(db, silence_minutes=0)
        assert engine._get_silenced_devices(rule, [1, 2], db) == set()

    def test_silenced_devices_found(self, engine, db):
        st = make_station(db, "S1")
        dev = make_device(db, st, sn="S1-D")
        rule = make_rule(db, silence_minutes=30)
        # 预置一条近期告警（同 rule + device）→ 命中沉默
        # 显式 created_at=utcnow()，与代码 UTC cutoff 对齐(避免 server_default 与查询时区错位)
        make_alarm(db, device=dev, station=st, rule_id=rule.id, created_at=datetime.now(timezone.utc))
        silenced = engine._get_silenced_devices(rule, [dev.id], db)
        assert dev.id in silenced


# ========== _is_silenced ==========

class TestIsSilenced:
    """覆盖 _is_silenced 三分支（302-311）。"""

    def test_no_silence_returns_false(self, engine, db):
        rule = make_rule(db, silence_minutes=0)
        assert engine._is_silenced(rule, 1, db) is False

    def test_recent_alarm_silenced(self, engine, db):
        st = make_station(db, "IS1")
        dev = make_device(db, st, sn="IS1-D")
        rule = make_rule(db, silence_minutes=30)
        make_alarm(db, device=dev, station=st, rule_id=rule.id, created_at=datetime.now(timezone.utc))
        assert engine._is_silenced(rule, dev.id, db) is True

    def test_no_recent_not_silenced(self, engine, db):
        rule = make_rule(db, silence_minutes=30)
        # 该设备无近期告警
        assert engine._is_silenced(rule, 99999, db) is False


# ========== _create_alarm ==========

class TestCreateAlarm:
    """覆盖 _create_alarm 全路径（317-396）。"""

    def test_create_alarm_basic(self, engine, db):
        """INFO 级别：建告警 + 日志，无工单，自愈成功（stub 返回 dict）。"""
        st = make_station(db, "C1")
        dev = make_device(db, st, sn="C1-D", name="逆变器A")
        rule = make_rule(db, level=AlarmLevel.INFO, alarm_template=None)
        alarm = engine._create_alarm(rule, dev.id, 80.0, db)

        assert alarm.id is not None
        assert alarm.device_id == dev.id
        assert alarm.station_id == st.id
        assert alarm.rule_id == rule.id
        assert alarm.level == AlarmLevel.INFO
        assert alarm.status == AlarmStatus.ACTIVE
        assert alarm.trigger_value == 80.0
        assert alarm.trigger_threshold == 55.0
        # 默认模板渲染
        assert "battery_temperature" in alarm.content
        assert "80" in alarm.content
        # 触发日志已写
        log = db.query(AlarmRuleLog).filter(AlarmRuleLog.alarm_id == alarm.id).first()
        assert log is not None
        assert log.triggered is True
        assert log.device_name == "逆变器A"

    def test_create_alarm_custom_template(self, engine, db):
        """自定义模板覆盖默认（321 分支）。"""
        st = make_station(db, "C2")
        dev = make_device(db, st, sn="C2-D")
        rule = make_rule(
            db, level=AlarmLevel.INFO,
            alarm_template="{rule_name}:{device_name} 的 {metric}={value} (限值{threshold})",
        )
        alarm = engine._create_alarm(rule, dev.id, 90.0, db)
        assert alarm.content == "测试告警规则:告警设备 的 battery_temperature=90.0 (限值55.0)"

    def test_create_alarm_device_not_found(self, engine, db):
        """设备不存在 → device None，station_id None，模板用兜底设备名（318, 327）。
        默认模板不含 {device_name}，故用自定义模板验证兜底设备名渲染。"""
        rule = make_rule(
            db, level=AlarmLevel.INFO,
            alarm_template="{device_name} 触发 {metric}={value}",
        )
        alarm = engine._create_alarm(rule, 99999, 70.0, db)
        assert alarm.station_id is None
        assert alarm.content == "设备99999 触发 battery_temperature=70.0"

    def test_create_alarm_aggregation_merge(self, engine, db, monkeypatch):
        """try_aggregate 返回已有告警（不同 id）→ 删除新建告警，返回聚合告警（350-358）。"""
        st = make_station(db, "C3")
        dev = make_device(db, st, sn="C3-D")
        rule = make_rule(db, level=AlarmLevel.INFO)
        existing = make_alarm(
            db, device=dev, station=st, rule_id=rule.id,
            aggregation_count=5, content="已有告警",
        )
        # 覆写 autouse 的 stub：返回已存在的聚合告警
        monkeypatch.setattr(alarm_rule_service, "try_aggregate_alarm",
                            lambda *a, **k: existing)
        result = engine._create_alarm(rule, dev.id, 80.0, db)
        assert result.id == existing.id
        # 新建的临时告警应被删除 → 库中仅 existing 一条该规则的告警
        alarms = db.query(Alarm).filter(Alarm.rule_id == rule.id).all()
        assert [a.id for a in alarms] == [existing.id]

    def test_create_alarm_critical_creates_workorder(self, engine, db):
        """CRITICAL + 显式 auto_create_workorder=True → should_create_workorder True
        → _maybe_create_workorder 成功落库工单（383-385 调用 + 402-418）。

        源码 3 个叠加 bug 已修复：
        1) WorkOrder.id 自生成 WO-{yyyyMMddHHmmss}-{4位hex}，commit 不再抛 IntegrityError；
        2) should_create_workorder 仅 rule.auto_create_workorder is True 才覆盖级别策略，
           False/None 回落到级别默认（CRITICAL/FATAL 默认 True 亦生效）；
        3) except 块已 rollback，会话不残留 inactive。
        """
        st = make_station(db, "C4")
        dev = make_device(db, st, sn="C4-D")
        rule = make_rule(db, level=AlarmLevel.CRITICAL, auto_create_workorder=True)
        engine._create_alarm(rule, dev.id, 90.0, db)
        # 会话状态正常（Bug3 修复后 commit 成功路径无 rollback 需求），可直接查询
        from app.models.alarm import Alarm as _Alarm
        from app.models.workorder import (
            WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus,
        )
        # 告警 + 工单均正常落库
        assert db.query(_Alarm).filter(_Alarm.device_id == dev.id).first() is not None
        wo = db.query(WorkOrder).filter(WorkOrder.device_id == dev.id).first()
        assert wo is not None  # Bug1 修复：id 自生成，工单成功持久化
        assert wo.id.startswith("WO-")
        assert wo.type == WorkOrderType.REPAIR
        assert wo.level == WorkOrderLevel.CRITICAL
        assert wo.status == WorkOrderStatus.PENDING
        assert wo.creator_id is None  # 系统自动创建: 无真实创建人 (卡片 1236b769)

    def test_create_alarm_healing_exception_swallowed(self, engine, db, monkeypatch):
        """healing_engine 抛异常 → 被吞掉，告警仍正常返回（393-394）。"""
        st = make_station(db, "C6")
        dev = make_device(db, st, sn="C6-D")
        rule = make_rule(db, level=AlarmLevel.INFO)

        def _raise(alarm, db):
            raise RuntimeError("healing-boom")
        monkeypatch.setattr(
            "app.services.healing_engine.healing_engine.evaluate_alarm", _raise)
        alarm = engine._create_alarm(rule, dev.id, 80.0, db)
        assert alarm.id is not None


# ========== _maybe_create_workorder 异常分支 ==========

class TestMaybeCreateWorkorder:
    """覆盖 _maybe_create_workorder（402-420）。

    成功路径：源码已自生成 WO-{yyyyMMddHHmmss}-{4位hex} id（Bug1 修复），
    无需注入；异常路径：except 吞异常并 rollback（Bug3 修复）。
    """

    def test_success_path(self, engine, db):
        """源码自生成 id → 工单成功持久化（402-418，含 418 成功日志）。"""
        from app.models.workorder import (
            WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus,
        )
        st = make_station(db, "W1")
        dev = make_device(db, st, sn="W1-D")
        rule = make_rule(db, level=AlarmLevel.CRITICAL)
        alarm = make_alarm(db, device=dev, station=st, rule_id=rule.id)

        ret = engine._maybe_create_workorder(alarm, rule, dev.id, st.id, "过温90度", db)
        assert ret is None  # 方法本身无返回值
        wo = db.query(WorkOrder).filter(WorkOrder.device_id == dev.id).first()
        assert wo is not None
        assert wo.id.startswith("WO-")  # Bug1 修复：自生成工单号
        assert wo.type == WorkOrderType.REPAIR
        assert wo.level == WorkOrderLevel.CRITICAL  # CRITICAL/FATAL → CRITICAL
        assert wo.status == WorkOrderStatus.PENDING
        assert wo.creator_id is None  # 系统自动创建: 无真实创建人 (卡片 1236b769)
        assert "[告警自动创建] 过温90度" in wo.fault_desc

    def test_exception_swallowed(self, engine, db, monkeypatch):
        """构造抛异常 → except 吞掉，返回 None（419-420）。"""
        st = make_station(db, "W2")
        dev = make_device(db, st, sn="W2-D")
        rule = make_rule(db, level=AlarmLevel.CRITICAL)
        alarm = make_alarm(db, device=dev, station=st, rule_id=rule.id)

        class _Boom:
            def __init__(self, *a, **k):
                raise RuntimeError("wo-crash")
        import app.models.workorder as wo_mod
        monkeypatch.setattr(wo_mod, "WorkOrder", _Boom)
        assert engine._maybe_create_workorder(alarm, rule, dev.id, st.id, "x", db) is None


# ========== _evaluate_rule ==========

class TestEvaluateRule:
    """覆盖 _evaluate_rule 设备循环各分支（204-241）。"""

    def test_no_target_devices_returns_not_triggered(self, engine, db):
        st = make_station(db, "E1")
        rule = make_rule(db, device_ids=[99999])  # 无匹配设备
        result = engine._evaluate_rule(rule, db, {})
        assert result["triggered"] is False
        assert result["devices"] == []

    def test_skip_device_without_telemetry(self, engine, db):
        st = make_station(db, "E2")
        dev = make_device(db, st, sn="E2-D")
        rule = make_rule(db, device_ids=[dev.id])
        result = engine._evaluate_rule(rule, db, {})  # 无遥测
        assert result["triggered"] is False
        assert result["devices"] == []

    def test_skip_when_metric_missing(self, engine, db):
        st = make_station(db, "E3")
        dev = make_device(db, st, sn="E3-D")
        make_telemetry(db, dev, grid_voltage_a=220.0)  # 无 battery_temperature
        rule = make_rule(db, device_ids=[dev.id], metric="battery_temperature")
        result = engine._evaluate_rule(rule, db, engine._get_latest_telemetry_all(db))
        assert result["triggered"] is False

    def test_skip_when_not_triggered(self, engine, db):
        st = make_station(db, "E4")
        dev = make_device(db, st, sn="E4-D")
        make_telemetry(db, dev, battery_temperature=30.0)  # 低于阈值 55
        rule = make_rule(db, device_ids=[dev.id])
        result = engine._evaluate_rule(rule, db, engine._get_latest_telemetry_all(db))
        assert result["triggered"] is False

    def test_skip_silenced_device(self, engine, db):
        st = make_station(db, "E5")
        dev = make_device(db, st, sn="E5-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        rule = make_rule(db, device_ids=[dev.id], silence_minutes=30)
        # 预置近期告警 → 沉默跳过（显式 created_at=utcnow() 对齐 UTC 沉默窗口）
        make_alarm(db, device=dev, station=st, rule_id=rule.id, created_at=datetime.now(timezone.utc))
        result = engine._evaluate_rule(rule, db, engine._get_latest_telemetry_all(db))
        assert result["triggered"] is False  # 被沉默，未产生新触发

    def test_triggered_creates_alarm_and_notifies(self, engine, db):
        st = make_station(db, "E6")
        dev = make_device(db, st, sn="E6-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        rule = make_rule(db, device_ids=[dev.id], level=AlarmLevel.WARNING)
        result = engine._evaluate_rule(rule, db, engine._get_latest_telemetry_all(db))

        assert result["triggered"] is True
        assert len(result["devices"]) == 1
        d = result["devices"][0]
        assert d["device_id"] == dev.id
        assert d["value"] == 90.0
        assert d["alarm_id"] is not None
        assert d["level"] == "warning"
        assert d["aggregated"] is False
        # 通知已分发（stub）
        alarm_rule_service.notification_dispatcher.dispatch_on_alarm.assert_called()

    def test_triggered_aggregated_marked(self, engine, db, monkeypatch):
        """_create_alarm 返回聚合告警（count>1）→ devices 中 aggregated=True（238）。"""
        st = make_station(db, "E7")
        dev = make_device(db, st, sn="E7-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        rule = make_rule(db, device_ids=[dev.id], level=AlarmLevel.WARNING)

        existing = make_alarm(db, device=dev, station=st, rule_id=rule.id,
                              aggregation_count=5)
        monkeypatch.setattr(alarm_rule_service, "try_aggregate_alarm",
                            lambda *a, **k: existing)
        result = engine._evaluate_rule(rule, db, engine._get_latest_telemetry_all(db))
        assert result["triggered"] is True
        assert result["devices"][0]["aggregated"] is True


# ========== evaluate_all ==========

class TestEvaluateAll:
    """覆盖 evaluate_all（133-158）。"""

    def test_with_explicit_db(self, engine, db):
        st = make_station(db, "A1")
        dev = make_device(db, st, sn="A1-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        rule = make_rule(db, level=AlarmLevel.INFO)
        results = engine.evaluate_all(db)
        assert len(results) == 1
        assert results[0]["triggered"] is True

    def test_db_none_creates_and_closes_session(self, engine, db, test_db, monkeypatch):
        """db=None → 内部 SessionLocal 自建并在 finally 关闭（134-137, 156-157）。"""
        st = make_station(db, "A2")
        dev = make_device(db, st, sn="A2-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        make_rule(db, level=AlarmLevel.INFO)
        # 服务模块的 SessionLocal 是导入时绑定，需直接 patch 指向测试库
        monkeypatch.setattr(alarm_rule_service, "SessionLocal", test_db["SessionLocal"])
        results = engine.evaluate_all()
        assert len(results) == 1
        assert results[0]["triggered"] is True

    def test_rule_exception_caught(self, engine, db, monkeypatch):
        """单规则评估抛异常 → 捕获并返回 error 结果（147-154）。"""
        rule = make_rule(db, level=AlarmLevel.INFO)

        def _raise(*a, **k):
            raise RuntimeError("eval-boom")
        monkeypatch.setattr(engine, "_evaluate_rule", _raise)
        results = engine.evaluate_all(db)
        assert results[0]["rule_id"] == rule.id
        assert results[0]["triggered"] is False
        assert "eval-boom" not in results[0]["error"]


# ========== evaluate_single_rule ==========

class TestEvaluateSingleRule:
    """覆盖 evaluate_single_rule（160-167）。"""

    def test_rule_not_found(self, engine, db):
        result = engine.evaluate_single_rule(99999, db)
        assert result == {"triggered": False, "message": "规则不存在"}

    def test_existing_rule_evaluated(self, engine, db):
        st = make_station(db, "ES1")
        dev = make_device(db, st, sn="ES1-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        rule = make_rule(db, level=AlarmLevel.INFO)
        result = engine.evaluate_single_rule(rule.id, db)
        assert result["rule_id"] == rule.id
        assert result["triggered"] is True


# ========== evaluate_device ==========

class TestEvaluateDevice:
    """覆盖 evaluate_device 即时评估（424-450）。"""

    def test_rule_not_found_or_disabled(self, engine, db):
        assert engine.evaluate_device(1, 99999, db)["message"] == "规则不存在或已禁用"
        rule = make_rule(db, enabled=False)
        assert engine.evaluate_device(1, rule.id, db)["message"] == "规则不存在或已禁用"

    def test_no_telemetry(self, engine, db):
        st = make_station(db, "ED1")
        dev = make_device(db, st, sn="ED1-D")
        rule = make_rule(db)
        result = engine.evaluate_device(dev.id, rule.id, db)
        assert result["triggered"] is False
        assert result["message"] == "设备无遥测数据"

    def test_metric_missing(self, engine, db):
        st = make_station(db, "ED2")
        dev = make_device(db, st, sn="ED2-D")
        make_telemetry(db, dev, grid_voltage_a=220.0)  # 无 battery_temperature
        rule = make_rule(db, metric="battery_temperature")
        result = engine.evaluate_device(dev.id, rule.id, db)
        assert result["triggered"] is False
        assert "battery_temperature" in result["message"]

    def test_not_triggered(self, engine, db):
        st = make_station(db, "ED3")
        dev = make_device(db, st, sn="ED3-D")
        make_telemetry(db, dev, battery_temperature=30.0)
        rule = make_rule(db)
        result = engine.evaluate_device(dev.id, rule.id, db)
        assert result["triggered"] is False
        assert result["current_value"] == 30.0
        assert "未触发" in result["message"]

    def test_triggered_creates_alarm(self, engine, db):
        st = make_station(db, "ED4")
        dev = make_device(db, st, sn="ED4-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        rule = make_rule(db, level=AlarmLevel.WARNING)
        result = engine.evaluate_device(dev.id, rule.id, db)
        assert result["triggered"] is True
        assert result["alarm_id"] is not None
        assert result["current_value"] == 90.0
        assert result["level"] == "warning"


# ========== scan_and_escalate ==========

class TestScanAndEscalate:
    """覆盖 scan_and_escalate（471-499）。"""

    def test_with_explicit_db_escalates(self, engine, db):
        st = make_station(db, "SC1")
        dev = make_device(db, st, sn="SC1-D")
        rule = make_rule(db, escalation_timeout_minutes=10)
        make_alarm(db, device=dev, station=st, rule_id=rule.id, level=AlarmLevel.WARNING,
                   created_at=datetime.now(timezone.utc) - timedelta(minutes=20))
        results = engine.scan_and_escalate(db)
        assert len(results) == 1
        assert results[0]["from_level"] == "warning"
        assert results[0]["to_level"] == "critical"

    def test_db_none_creates_and_closes_session(self, engine, db, test_db, monkeypatch):
        st = make_station(db, "SC2")
        dev = make_device(db, st, sn="SC2-D")
        rule = make_rule(db, escalation_timeout_minutes=10)
        make_alarm(db, device=dev, station=st, rule_id=rule.id, level=AlarmLevel.WARNING,
                   created_at=datetime.now(timezone.utc) - timedelta(minutes=20))
        monkeypatch.setattr(alarm_rule_service, "SessionLocal", test_db["SessionLocal"])
        results = engine.scan_and_escalate()
        assert len(results) == 1

    def test_exception_caught(self, engine, db, monkeypatch):
        st = make_station(db, "SC3")
        dev = make_device(db, st, sn="SC3-D")
        make_alarm(db, device=dev, station=st, level=AlarmLevel.WARNING,
                   created_at=datetime.now(timezone.utc) - timedelta(minutes=5))

        def _raise(*a, **k):
            raise RuntimeError("esc-boom")
        monkeypatch.setattr(engine, "_escalate_single", _raise)
        # 异常被吞，返回 []
        assert engine.scan_and_escalate(db) == []


# ========== _escalate_single ==========

class TestEscalateSingle:
    """覆盖 _escalate_single 各分支（504-572）。"""

    def test_created_at_none_returns_none(self, engine, db):
        st = make_station(db, "ES1")
        dev = make_device(db, st, sn="ES1-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.WARNING)
        al.created_at = None
        db.commit()
        assert engine._escalate_single(al, datetime.now(timezone.utc), db) is None

    def test_warning_escalation_default_timeout(self, engine, db):
        """无规则 → 默认 30 分钟；超时 → WARN→CRITICAL（504-509 无 rule, 518-543）。"""
        st = make_station(db, "ES2")
        dev = make_device(db, st, sn="ES2-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.WARNING,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=35))
        result = engine._escalate_single(al, datetime.now(timezone.utc), db)
        assert result["from_level"] == "warning"
        assert result["to_level"] == "critical"
        db.refresh(al)
        assert al.level == AlarmLevel.CRITICAL
        assert al.escalated_from == "warning→critical"
        assert al.original_level == "warning"

    def test_warning_escalation_custom_timeout(self, engine, db):
        """规则自定义 escalation_timeout_minutes=10，12 分钟即升级（509 取 rule 值）。"""
        st = make_station(db, "ES3")
        dev = make_device(db, st, sn="ES3-D")
        rule = make_rule(db, escalation_timeout_minutes=10)
        al = make_alarm(db, device=dev, station=st, rule_id=rule.id,
                        level=AlarmLevel.WARNING,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=12))
        result = engine._escalate_single(al, datetime.now(timezone.utc), db)
        assert result["to_level"] == "critical"

    def test_warning_not_yet_timed_out(self, engine, db):
        """WARNING 未到超时 → None（518 False，落到 572）。"""
        st = make_station(db, "ES4")
        dev = make_device(db, st, sn="ES4-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.WARNING,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        assert engine._escalate_single(al, datetime.now(timezone.utc), db) is None

    def test_critical_escalation(self, engine, db):
        """CRITICAL 超 max(15, timeout//2) → 升级 FATAL（545-570）。"""
        st = make_station(db, "ES5")
        dev = make_device(db, st, sn="ES5-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.CRITICAL,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=20))
        result = engine._escalate_single(al, datetime.now(timezone.utc), db)
        assert result["from_level"] == "critical"
        assert result["to_level"] == "fatal"
        db.refresh(al)
        assert al.level == AlarmLevel.FATAL

    def test_critical_not_yet_timed_out(self, engine, db):
        st = make_station(db, "ES6")
        dev = make_device(db, st, sn="ES6-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.CRITICAL,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        assert engine._escalate_single(al, datetime.now(timezone.utc), db) is None


# ========== escalate_alarm_by_id ==========

class TestEscalateAlarmById:
    """覆盖手动升级入口（576-587）。"""

    def test_alarm_not_found(self, engine, db):
        assert engine.escalate_alarm_by_id(99999, db) == \
            {"success": False, "message": "告警不存在"}

    def test_already_fatal(self, engine, db):
        st = make_station(db, "EI1")
        dev = make_device(db, st, sn="EI1-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.FATAL)
        r = engine.escalate_alarm_by_id(al.id, db)
        assert r["success"] is False
        assert "最高级别" in r["message"]

    def test_escalation_success(self, engine, db):
        st = make_station(db, "EI2")
        dev = make_device(db, st, sn="EI2-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.WARNING,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=35))
        r = engine.escalate_alarm_by_id(al.id, db)
        assert r["success"] is True
        assert r["data"]["to_level"] == "critical"

    def test_not_meeting_conditions(self, engine, db):
        st = make_station(db, "EI3")
        dev = make_device(db, st, sn="EI3-D")
        al = make_alarm(db, device=dev, station=st, level=AlarmLevel.WARNING,
                        created_at=datetime.now(timezone.utc))  # 刚创建，未超时
        r = engine.escalate_alarm_by_id(al.id, db)
        assert r["success"] is False
        assert "未达到升级条件" in r["message"]


# ========== 模块入口函数 ==========

class TestModuleEntryFunctions:
    """覆盖 evaluate_all_rules / scan_and_escalate 模块入口（598-606, 611-618）。"""

    def test_evaluate_all_rules_normal(self, db, test_db, monkeypatch):
        st = make_station(db, "M1")
        dev = make_device(db, st, sn="M1-D")
        make_telemetry(db, dev, battery_temperature=90.0)
        make_rule(db, level=AlarmLevel.INFO)
        monkeypatch.setattr(alarm_rule_service, "SessionLocal", test_db["SessionLocal"])
        results = alarm_rule_service.evaluate_all_rules()
        assert isinstance(results, list)
        assert results and results[0]["triggered"] is True

    def test_evaluate_all_rules_exception_returns_empty(self, monkeypatch):
        def _raise(*a, **k):
            raise RuntimeError("module-boom")
        monkeypatch.setattr(alarm_rule_service.engine, "evaluate_all", _raise)
        assert alarm_rule_service.evaluate_all_rules() == []

    def test_scan_and_escalate_module_normal(self, db, test_db, monkeypatch):
        st = make_station(db, "M2")
        dev = make_device(db, st, sn="M2-D")
        rule = make_rule(db, escalation_timeout_minutes=10)
        make_alarm(db, device=dev, station=st, rule_id=rule.id, level=AlarmLevel.WARNING,
                   created_at=datetime.now(timezone.utc) - timedelta(minutes=20))
        monkeypatch.setattr(alarm_rule_service, "SessionLocal", test_db["SessionLocal"])
        results = alarm_rule_service.scan_and_escalate()
        assert len(results) == 1

    def test_scan_and_escalate_module_exception_returns_empty(self, monkeypatch):
        def _raise(*a, **k):
            raise RuntimeError("module-boom")
        monkeypatch.setattr(alarm_rule_service.engine, "scan_and_escalate", _raise)
        assert alarm_rule_service.scan_and_escalate() == []
