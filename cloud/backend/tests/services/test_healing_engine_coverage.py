#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
healing_engine.py 覆盖率补强测试

聚焦 service 层内部方法（API 测试难以覆盖的逻辑分支）：
- evaluate_alarm        规则匹配 / 冷却跳过 / 自动执行 / 待审批
- _match_alarm          各匹配条件分支
- _check_cooldown       冷却期判定
- _create_execution     执行记录创建
- execute_healing       设备/告警缺失、四种结果状态、异常、诊断结果解析
- verify_healing_result healed / partial / unhealed / 缺告警
- batch_verify_completed 批量验证 + error / exception 分支
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.healing_engine import HealingEngine
from app.models.healing_rule import HealingRule
from app.models.healing_execution import HealingExecution
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
from app.models.station import Station, StationStatus


# ========== 通用 fixtures / helpers ==========

@pytest.fixture
def engine():
    """独立 HealingEngine 实例，runbook_engine 替换为 mock 便于控制返回值。"""
    e = HealingEngine()
    e._runbook_engine = MagicMock()
    return e


@pytest.fixture
def db(test_db):
    return test_db["session"]


def _rb_result(**over):
    """构造 RunbookEngine.execute 的返回值。"""
    base = {
        "status": "success",
        "runbook_id": "RB-1",
        "steps": [{"name": "step1"}],
        "total_duration_ms": 200,
        "success_steps": 1,
        "failed_steps": 0,
        "skipped_steps": 0,
        "error_message": "",
    }
    base.update(over)
    return base


def make_station(db, code="HEAL-ST"):
    st = Station(name=f"自愈站-{code}", code=code, status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def make_device(db, station, *, sn="HEAL-DEV", name="自愈设备",
                dtype=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, with_ip=True):
    dev = Device(
        sn=sn, name=name, code=sn,
        type=dtype, status=status,
        station_id=station.id,
        protocol_type=ProtocolType.MODBUS_RTU,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    if with_ip:
        # healing_engine 访问 device.ip_address（Device 模型无此列），补实例属性以走成功路径
        dev.ip_address = "10.0.0.1"
    return dev


def make_alarm(db, device, station, *, alarm_type="逆变器通讯中断",
               level=AlarmLevel.CRITICAL, content="逆变器通讯中断",
               status=AlarmStatus.ACTIVE, diagnosis_result=None):
    al = Alarm(
        device_id=device.id, station_id=station.id,
        alarm_type=alarm_type, level=level, content=content,
        status=status, diagnosis_result=diagnosis_result,
    )
    db.add(al)
    db.commit()
    db.refresh(al)
    return al


def make_rule(db, **kw):
    rule = HealingRule(
        name=kw.get("name", "测试自愈规则"),
        alarm_pattern=kw.get("alarm_pattern", {"alarm_levels": ["critical"]}),
        runbook_template=kw.get("runbook_template"),
        auto_approve=kw.get("auto_approve", False),
        max_retries=kw.get("max_retries", 1),
        cooldown_minutes=kw.get("cooldown_minutes", 30),
        priority=kw.get("priority", 10),
        enabled=kw.get("enabled", True),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def make_execution(db, rule, alarm, *, status="pending_approval", verified=False,
                   completed=True, fault_type="测试故障"):
    ex = HealingExecution(
        rule_id=rule.id, rule_name=rule.name,
        alarm_id=alarm.id if alarm else None,
        device_id=alarm.device_id if alarm else None,
        station_id=alarm.station_id if alarm else None,
        runbook_template=rule.runbook_template,
        fault_type=fault_type, status=status, steps=[],
        verified=verified,
    )
    # 显式 UTC naive 时间覆盖 server_default(UTC)，
    # 与 _check_cooldown(utcnow) 对齐避免时区错位
    ex.created_at = datetime.now(timezone.utc)
    if completed:
        ex.completed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


# ========== _match_alarm ==========

class TestMatchAlarm:
    """覆盖 _match_alarm 各条件分支"""

    def test_empty_pattern_returns_false(self, engine, db):
        st = make_station(db, "M0")
        dev = make_device(db, st, sn="M0-DEV")
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={})
        assert engine._match_alarm(al, rule) is False

    def test_alarm_level_mismatch(self, engine, db):
        st = make_station(db, "M1")
        dev = make_device(db, st, sn="M1-DEV")
        al = make_alarm(db, dev, st, level=AlarmLevel.INFO)
        rule = HealingRule(name="r", alarm_pattern={"alarm_levels": ["critical"]})
        assert engine._match_alarm(al, rule) is False

    def test_alarm_level_match(self, engine, db):
        st = make_station(db, "M2")
        dev = make_device(db, st, sn="M2-DEV")
        al = make_alarm(db, dev, st, level=AlarmLevel.CRITICAL)
        rule = HealingRule(name="r", alarm_pattern={"alarm_levels": ["critical"]})
        assert engine._match_alarm(al, rule) is True

    def test_alarm_type_mismatch(self, engine, db):
        st = make_station(db, "M3")
        dev = make_device(db, st, sn="M3-DEV")
        al = make_alarm(db, dev, st, alarm_type="温度异常")
        rule = HealingRule(name="r", alarm_pattern={"alarm_types": ["通讯中断"]})
        assert engine._match_alarm(al, rule) is False

    def test_alarm_type_none_skips(self, engine, db):
        # alarm_type 为 None → "" 不含任何关键词 → 不匹配
        st = make_station(db, "M4")
        dev = make_device(db, st, sn="M4-DEV")
        al = make_alarm(db, dev, st, alarm_type=None)
        rule = HealingRule(name="r", alarm_pattern={"alarm_types": ["通讯中断"]})
        assert engine._match_alarm(al, rule) is False

    def test_alarm_type_match(self, engine, db):
        st = make_station(db, "M5")
        dev = make_device(db, st, sn="M5-DEV")
        al = make_alarm(db, dev, st, alarm_type="逆变器通讯中断")
        rule = HealingRule(name="r", alarm_pattern={"alarm_types": ["通讯中断"]})
        assert engine._match_alarm(al, rule) is True

    def test_device_type_mismatch(self, engine, db):
        st = make_station(db, "M6")
        dev = make_device(db, st, sn="M6-DEV", dtype=DeviceType.PV_INVERTER)
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={"device_types": ["charger"]})
        assert engine._match_alarm(al, rule) is False

    def test_device_type_match(self, engine, db):
        # PV_INVERTER → device_type property 返回 "inverter"
        st = make_station(db, "M7")
        dev = make_device(db, st, sn="M7-DEV", dtype=DeviceType.PV_INVERTER)
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={"device_types": ["inverter"]})
        assert engine._match_alarm(al, rule) is True

    def test_device_type_pattern_but_no_device_relation(self, engine, db):
        # 缺陷2修复: device_types 非空但 alarm.device 为 None(设备删除/关联断裂)
        # → 规则既限定设备类型却取不到设备，判不匹配(防对错误目标过度匹配)
        st = make_station(db, "M8")
        dev = make_device(db, st, sn="M8-DEV")
        al = make_alarm(db, dev, st)
        # device_id=99999 触发 alarm.device 懒加载为 None
        al.device_id = 99999
        db.commit()
        rule = HealingRule(name="r", alarm_pattern={"device_types": ["inverter"]})
        assert engine._match_alarm(al, rule) is False

    def test_device_ids_mismatch(self, engine, db):
        st = make_station(db, "M9")
        dev = make_device(db, st, sn="M9-DEV")
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={"device_ids": [999999]})
        assert engine._match_alarm(al, rule) is False

    def test_device_ids_match(self, engine, db):
        st = make_station(db, "M10")
        dev = make_device(db, st, sn="M10-DEV")
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={"device_ids": [dev.id]})
        assert engine._match_alarm(al, rule) is True

    def test_station_ids_mismatch(self, engine, db):
        st = make_station(db, "M11")
        dev = make_device(db, st, sn="M11-DEV")
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={"station_ids": [999999]})
        assert engine._match_alarm(al, rule) is False

    def test_station_ids_match(self, engine, db):
        st = make_station(db, "M12")
        dev = make_device(db, st, sn="M12-DEV")
        al = make_alarm(db, dev, st)
        rule = HealingRule(name="r", alarm_pattern={"station_ids": [st.id]})
        assert engine._match_alarm(al, rule) is True

    def test_content_keywords_mismatch(self, engine, db):
        st = make_station(db, "M13")
        dev = make_device(db, st, sn="M13-DEV")
        al = make_alarm(db, dev, st, content="温度过高")
        rule = HealingRule(name="r", alarm_pattern={"content_keywords": ["通讯"]})
        assert engine._match_alarm(al, rule) is False

    def test_content_keywords_match(self, engine, db):
        st = make_station(db, "M14")
        dev = make_device(db, st, sn="M14-DEV")
        al = make_alarm(db, dev, st, content="逆变器通讯中断")
        rule = HealingRule(name="r", alarm_pattern={"content_keywords": ["通讯"]})
        assert engine._match_alarm(al, rule) is True

    def test_content_none_skips_keyword_check(self, engine, db):
        # 缺陷2修复: content_keywords 非空但 content 为 None → 判不匹配(防静默绕过)
        st = make_station(db, "M15")
        dev = make_device(db, st, sn="M15-DEV")
        al = make_alarm(db, dev, st, content=None)
        rule = HealingRule(name="r", alarm_pattern={"content_keywords": ["通讯"]})
        assert engine._match_alarm(al, rule) is False

    def test_all_conditions_match(self, engine, db):
        st = make_station(db, "M16")
        dev = make_device(db, st, sn="M16-DEV", dtype=DeviceType.PV_INVERTER)
        al = make_alarm(db, dev, st, level=AlarmLevel.CRITICAL,
                        alarm_type="逆变器通讯中断", content="逆变器通讯中断告警")
        rule = HealingRule(name="r", alarm_pattern={
            "alarm_levels": ["critical"],
            "alarm_types": ["通讯中断"],
            "device_types": ["inverter"],
            "device_ids": [dev.id],
            "station_ids": [st.id],
            "content_keywords": ["通讯"],
        })
        assert engine._match_alarm(al, rule) is True


# ========== _check_cooldown ==========

class TestCheckCooldown:

    def test_rule_not_found(self, engine, db):
        assert engine._check_cooldown(99999, 1, db) is False

    def test_cooldown_zero(self, engine, db):
        rule = make_rule(db, cooldown_minutes=0)
        assert engine._check_cooldown(rule.id, 1, db) is False

    def test_no_recent_execution(self, engine, db):
        rule = make_rule(db, cooldown_minutes=30)
        assert engine._check_cooldown(rule.id, 1, db) is False

    def test_in_cooldown(self, engine, db):
        st = make_station(db, "C1")
        dev = make_device(db, st, sn="C1-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, cooldown_minutes=30)
        make_execution(db, rule, al, status="success")
        assert engine._check_cooldown(rule.id, dev.id, db) is True

    def test_old_execution_not_in_cooldown(self, engine, db):
        st = make_station(db, "C2")
        dev = make_device(db, st, sn="C2-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, cooldown_minutes=1)
        ex = make_execution(db, rule, al, status="success")
        # 改为 1 小时前完成，超出 1 分钟冷却窗
        ex.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        assert engine._check_cooldown(rule.id, dev.id, db) is False


# ========== _create_execution ==========

class TestCreateExecution:

    def test_creates_pending_execution(self, engine, db):
        st = make_station(db, "CE1")
        dev = make_device(db, st, sn="CE1-DEV")
        al = make_alarm(db, dev, st, alarm_type="过温告警")
        rule = make_rule(db, runbook_template="过温恢复")
        ex = engine._create_execution(rule, al, db)
        assert ex.id is not None
        assert ex.status == "pending_approval"
        assert ex.rule_id == rule.id
        assert ex.alarm_id == al.id
        assert ex.device_id == dev.id
        assert ex.station_id == st.id
        assert ex.fault_type == "过温告警"
        assert ex.runbook_template == "过温恢复"

    def test_fault_type_fallback_when_alarm_type_none(self, engine, db):
        st = make_station(db, "CE2")
        dev = make_device(db, st, sn="CE2-DEV")
        # alarm_type 与 fault_code 均空 → "未知故障"
        al = Alarm(
            device_id=dev.id, station_id=st.id,
            alarm_type=None, level=AlarmLevel.WARNING,
            content="x", status=AlarmStatus.ACTIVE, fault_code=None,
        )
        db.add(al)
        db.commit()
        db.refresh(al)
        rule = make_rule(db)
        ex = engine._create_execution(rule, al, db)
        assert ex.fault_type == "未知故障"


# ========== evaluate_alarm ==========

class TestEvaluateAlarm:

    def test_no_enabled_rules_returns_none(self, engine, db):
        st = make_station(db, "E0")
        dev = make_device(db, st, sn="E0-DEV")
        al = make_alarm(db, dev, st)
        assert engine.evaluate_alarm(al, db) is None

    def test_disabled_rule_ignored(self, engine, db):
        st = make_station(db, "E0b")
        dev = make_device(db, st, sn="E0b-DEV")
        al = make_alarm(db, dev, st)
        make_rule(db, enabled=False, alarm_pattern={"alarm_levels": ["critical"]})
        assert engine.evaluate_alarm(al, db) is None

    def test_no_match_returns_none(self, engine, db):
        st = make_station(db, "E1")
        dev = make_device(db, st, sn="E1-DEV")
        al = make_alarm(db, dev, st, level=AlarmLevel.INFO)
        make_rule(db, alarm_pattern={"alarm_levels": ["critical"]})
        assert engine.evaluate_alarm(al, db) is None

    def test_match_non_auto_returns_pending_approval(self, engine, db):
        st = make_station(db, "E2")
        dev = make_device(db, st, sn="E2-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, alarm_pattern={"alarm_levels": ["critical"]}, auto_approve=False)
        result = engine.evaluate_alarm(al, db)
        assert result is not None
        assert result["status"] == "pending_approval"
        assert result["rule_id"] == rule.id
        assert result["alarm_id"] == al.id
        assert result["message"] == "等待人工审批"

    def test_match_auto_approve_executes_success(self, engine, db):
        st = make_station(db, "E3")
        dev = make_device(db, st, sn="E3-DEV")
        al = make_alarm(db, dev, st)
        make_rule(db, alarm_pattern={"alarm_levels": ["critical"]},
                  auto_approve=True, runbook_template="通讯恢复")
        engine._runbook_engine.execute.return_value = _rb_result(
            status="success", success_steps=2, failed_steps=0)
        result = engine.evaluate_alarm(al, db)
        assert result["status"] == "success"
        engine._runbook_engine.execute.assert_called_once()
        # auto 审批标记
        _, kwargs = engine._runbook_engine.execute.call_args
        assert kwargs["auto_trigger"] is True

    def test_match_in_cooldown_skipped_returns_none(self, engine, db):
        st = make_station(db, "E4")
        dev = make_device(db, st, sn="E4-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, alarm_pattern={"alarm_levels": ["critical"]}, cooldown_minutes=30)
        # 预置一条最近的成功执行 → 进入冷却（created_at 用本地时间覆盖 UTC server_default）
        recent = HealingExecution(
            rule_id=rule.id, rule_name=rule.name, alarm_id=al.id,
            device_id=dev.id, station_id=st.id, fault_type="x",
            status="success", steps=[])
        recent.created_at = datetime.now(timezone.utc)
        db.add(recent)
        db.commit()
        # 唯一规则处于冷却 → 跳过 → 无可执行规则
        assert engine.evaluate_alarm(al, db) is None

    def test_priority_higher_matched_first(self, engine, db):
        # 高优先级规则非auto，低优先级规则auto；告警匹配两者 → 取高优先级（pending）
        st = make_station(db, "E5")
        dev = make_device(db, st, sn="E5-DEV")
        al = make_alarm(db, dev, st)
        make_rule(db, name="低优先级auto", alarm_pattern={"alarm_levels": ["critical"]},
                  auto_approve=True, priority=1)
        make_rule(db, name="高优先级manual", alarm_pattern={"alarm_levels": ["critical"]},
                  auto_approve=False, priority=100)
        result = engine.evaluate_alarm(al, db)
        # 高优先级先匹配且非auto → pending_approval，不执行 runbook
        assert result["status"] == "pending_approval"
        engine._runbook_engine.execute.assert_not_called()


# ========== execute_healing ==========

class TestExecuteHealing:

    def test_execution_not_found(self, engine, db):
        r = engine.execute_healing(99999, db=db)
        assert "不存在" in r["error"]

    def test_alarm_not_found_marks_failed(self, engine, db):
        st = make_station(db, "X1")
        dev = make_device(db, st, sn="X1-DEV")
        rule = make_rule(db)
        ex = HealingExecution(
            rule_id=rule.id, rule_name=rule.name, alarm_id=99999,
            device_id=dev.id, station_id=st.id, fault_type="x",
            status="approved", steps=[])
        db.add(ex)
        db.commit()
        db.refresh(ex)
        r = engine.execute_healing(ex.id, db=db)
        assert r["error"] == "告警不存在"
        db.refresh(ex)
        assert ex.status == "failed"

    def test_device_not_found_marks_failed(self, engine, db):
        st = make_station(db, "X2")
        al = Alarm(
            device_id=99999, station_id=st.id, alarm_type="x",
            level=AlarmLevel.CRITICAL, content="x", status=AlarmStatus.ACTIVE)
        db.add(al)
        db.commit()
        db.refresh(al)
        rule = make_rule(db)
        ex = HealingExecution(
            rule_id=rule.id, rule_name=rule.name, alarm_id=al.id,
            device_id=99999, station_id=st.id, fault_type="x",
            status="approved", steps=[])
        db.add(ex)
        db.commit()
        db.refresh(ex)
        r = engine.execute_healing(ex.id, db=db)
        assert r["error"] == "设备不存在"

    def test_success_path(self, engine, db):
        st = make_station(db, "X3")
        dev = make_device(db, st, sn="X3-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, runbook_template="t")
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result(
            status="success", runbook_id="RB-9", success_steps=3,
            failed_steps=0, skipped_steps=1, total_duration_ms=500)
        r = engine.execute_healing(ex.id, db=db)
        assert r["status"] == "success"
        assert r["success_steps"] == 3
        assert r["runbook_id"] == "RB-9"
        db.refresh(ex)
        assert ex.status == "success"
        assert ex.runbook_id == "RB-9"
        assert ex.success_steps == 3
        assert "3成功" in ex.result

    def test_partial_success_path(self, engine, db):
        st = make_station(db, "X4")
        dev = make_device(db, st, sn="X4-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result(
            status="failed", success_steps=2, failed_steps=1)
        r = engine.execute_healing(ex.id, db=db)
        assert r["status"] == "partial_success"

    def test_failed_all_steps_path(self, engine, db):
        st = make_station(db, "X5")
        dev = make_device(db, st, sn="X5-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result(
            status="failed", success_steps=0, failed_steps=2)
        r = engine.execute_healing(ex.id, db=db)
        assert r["status"] == "failed"

    def test_pending_approval_result_path(self, engine, db):
        st = make_station(db, "X6")
        dev = make_device(db, st, sn="X6-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result(
            status="pending_approval", success_steps=0, failed_steps=0)
        r = engine.execute_healing(ex.id, db=db)
        assert r["status"] == "pending_approval"

    def test_exception_path_marks_failed(self, engine, db):
        st = make_station(db, "X7")
        dev = make_device(db, st, sn="X7-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.side_effect = RuntimeError("boom-error")
        r = engine.execute_healing(ex.id, db=db)
        assert r["status"] == "failed"
        assert "boom-error" not in r["error"]
        db.refresh(ex)
        assert ex.status == "failed"
        assert "boom-error" in ex.error_message

    def test_diagnosis_result_json_string_parsed(self, engine, db):
        st = make_station(db, "X8")
        dev = make_device(db, st, sn="X8-DEV")
        al = make_alarm(db, dev, st, diagnosis_result='{"fault_type":"通讯中断"}')
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result()
        engine.execute_healing(ex.id, db=db)
        _, kwargs = engine._runbook_engine.execute.call_args
        assert kwargs["diagnosis_result"]["fault_type"] == "通讯中断"

    def test_diagnosis_result_invalid_json_falls_back(self, engine, db):
        st = make_station(db, "X9")
        dev = make_device(db, st, sn="X9-DEV")
        al = make_alarm(db, dev, st, diagnosis_result="not-json{")
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved", fault_type="兜底故障")
        engine._runbook_engine.execute.return_value = _rb_result()
        engine.execute_healing(ex.id, db=db)
        _, kwargs = engine._runbook_engine.execute.call_args
        # 非法 JSON → {} → 用 execution.fault_type 兜底
        assert kwargs["diagnosis_result"]["fault_type"] == "兜底故障"

    def test_diagnosis_result_dict_passthrough(self, engine, db):
        # SQLite Text 列无法直接存 dict；用脱离 session 的独立内存 alarm 对象
        # 传给 execute_healing(alarm=...)，覆盖 isinstance(...,str) False 的 dict 直传分支。
        # 该对象不进 session，execute_healing 内部 commit 不会 flush 它。
        st = make_station(db, "X10")
        dev = make_device(db, st, sn="X10-DEV")
        al_db = make_alarm(db, dev, st)
        al_mem = Alarm(
            id=al_db.id, device_id=dev.id, station_id=st.id,
            alarm_type="x", level=AlarmLevel.CRITICAL, content="x",
            status=AlarmStatus.ACTIVE, diagnosis_result={"fault_type": "直传故障"})
        rule = make_rule(db)
        ex = make_execution(db, rule, al_db, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result()
        engine.execute_healing(ex.id, alarm=al_mem, rule=rule, db=db)
        _, kwargs = engine._runbook_engine.execute.call_args
        assert kwargs["diagnosis_result"]["fault_type"] == "直传故障"

    def test_device_info_built_from_device(self, engine, db):
        st = make_station(db, "X11")
        dev = make_device(db, st, sn="X11-DEV", name="逆变器A")
        dev.ip_address = "192.168.1.55"
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="approved")
        engine._runbook_engine.execute.return_value = _rb_result()
        engine.execute_healing(ex.id, db=db)
        _, kwargs = engine._runbook_engine.execute.call_args
        info = kwargs["device_info"]
        assert info["id"] == dev.id
        assert info["ip"] == "192.168.1.55"
        assert info["sn"] == "X11-DEV"
        assert info["name"] == "逆变器A"
        assert info["type"] == "inverter"


# ========== verify_healing_result ==========

class TestVerifyHealingResult:

    def test_execution_not_found(self, engine, db):
        r = engine.verify_healing_result(99999, db)
        assert "不存在" in r["error"]

    def test_status_not_verifiable(self, engine, db):
        st = make_station(db, "V1")
        dev = make_device(db, st, sn="V1-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="failed")
        r = engine.verify_healing_result(ex.id, db)
        assert "不可验证" in r["error"]

    def test_healed(self, engine, db):
        st = make_station(db, "V2")
        dev = make_device(db, st, sn="V2-DEV", status=DeviceStatus.ONLINE)
        al = make_alarm(db, dev, st, status=AlarmStatus.RESOLVED)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="success")
        r = engine.verify_healing_result(ex.id, db)
        assert r["verification_result"] == "healed"
        assert r["alarm_cleared"] is True
        assert r["device_online"] is True
        db.refresh(ex)
        assert ex.verified is True
        assert ex.verification_result == "healed"
        assert ex.alarm_cleared is True

    def test_partial_only_alarm_cleared(self, engine, db):
        st = make_station(db, "V3")
        dev = make_device(db, st, sn="V3-DEV", status=DeviceStatus.FAULT)
        al = make_alarm(db, dev, st, status=AlarmStatus.RESOLVED)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="success")
        r = engine.verify_healing_result(ex.id, db)
        assert r["verification_result"] == "partial"
        assert r["alarm_cleared"] is True
        assert r["device_online"] is False

    def test_partial_only_device_online(self, engine, db):
        st = make_station(db, "V4")
        dev = make_device(db, st, sn="V4-DEV", status=DeviceStatus.ONLINE)
        al = make_alarm(db, dev, st, status=AlarmStatus.ACTIVE)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="success")
        r = engine.verify_healing_result(ex.id, db)
        assert r["verification_result"] == "partial"
        assert r["alarm_cleared"] is False
        assert r["device_online"] is True

    def test_unhealed(self, engine, db):
        st = make_station(db, "V5")
        dev = make_device(db, st, sn="V5-DEV", status=DeviceStatus.OFFLINE)
        al = make_alarm(db, dev, st, status=AlarmStatus.ACTIVE)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="partial_success")
        r = engine.verify_healing_result(ex.id, db)
        assert r["verification_result"] == "unhealed"
        assert r["alarm_cleared"] is False
        assert r["device_online"] is False

    def test_alarm_missing(self, engine, db):
        # execution.alarm_id 指向不存在告警 → alarm None → alarm_cleared False
        st = make_station(db, "V6")
        dev = make_device(db, st, sn="V6-DEV", status=DeviceStatus.ONLINE)
        rule = make_rule(db)
        ex = HealingExecution(
            rule_id=rule.id, rule_name=rule.name, alarm_id=99999,
            device_id=dev.id, station_id=st.id, fault_type="x",
            status="success", steps=[])
        db.add(ex)
        db.commit()
        db.refresh(ex)
        r = engine.verify_healing_result(ex.id, db)
        assert r["alarm_cleared"] is False
        assert r["device_online"] is True
        assert r["verification_result"] == "partial"

    def test_device_missing(self, engine, db):
        st = make_station(db, "V7")
        dev = make_device(db, st, sn="V7-DEV")
        al = make_alarm(db, dev, st, status=AlarmStatus.RESOLVED)
        rule = make_rule(db)
        ex = HealingExecution(
            rule_id=rule.id, rule_name=rule.name, alarm_id=al.id,
            device_id=99999, station_id=st.id, fault_type="x",
            status="success", steps=[])
        db.add(ex)
        db.commit()
        db.refresh(ex)
        r = engine.verify_healing_result(ex.id, db)
        assert r["device_online"] is False
        assert r["alarm_cleared"] is True
        assert r["verification_result"] == "partial"


# ========== batch_verify_completed ==========

class TestBatchVerifyCompleted:

    def test_empty(self, engine, db):
        r = engine.batch_verify_completed(db, hours=24)
        assert r["total_verified"] == 0
        assert r["results"] == {"healed": 0, "partial": 0, "unhealed": 0, "errors": 0}

    def test_mixed_results(self, engine, db):
        st = make_station(db, "B1")
        dev_online = make_device(db, st, sn="B1-ON", status=DeviceStatus.ONLINE)
        dev_fault = make_device(db, st, sn="B1-FT", status=DeviceStatus.FAULT)
        al_resolved = make_alarm(db, dev_online, st, status=AlarmStatus.RESOLVED)
        al_active = make_alarm(db, dev_fault, st, status=AlarmStatus.ACTIVE)
        rule = make_rule(db)
        make_execution(db, rule, al_resolved, status="success", verified=False)
        make_execution(db, rule, al_active, status="partial_success", verified=False)
        r = engine.batch_verify_completed(db, hours=24)
        assert r["total_verified"] == 2
        assert r["results"]["healed"] == 1
        assert r["results"]["unhealed"] == 1

    def test_skips_verified_and_old(self, engine, db):
        st = make_station(db, "B2")
        dev = make_device(db, st, sn="B2-DEV", status=DeviceStatus.ONLINE)
        al = make_alarm(db, dev, st, status=AlarmStatus.RESOLVED)
        rule = make_rule(db)
        # 新且未验证 → 入选
        make_execution(db, rule, al, status="success", verified=False, completed=True)
        # 已验证 → 跳过
        make_execution(db, rule, al, status="success", verified=True, completed=True)
        # 超出时间窗 → 跳过
        ex_old = make_execution(db, rule, al, status="success", verified=False)
        ex_old.completed_at = datetime.now(timezone.utc) - timedelta(hours=48)
        db.commit()
        r = engine.batch_verify_completed(db, hours=24)
        assert r["total_verified"] == 1
        assert r["results"]["healed"] == 1

    def test_error_dict_branch(self, engine, db, monkeypatch):
        st = make_station(db, "B3")
        dev = make_device(db, st, sn="B3-DEV", status=DeviceStatus.ONLINE)
        al = make_alarm(db, dev, st, status=AlarmStatus.RESOLVED)
        rule = make_rule(db)
        make_execution(db, rule, al, status="success", verified=False)
        # verify 返回含 error 键 → 计入 errors（覆盖 "error" in r 分支）
        monkeypatch.setattr(engine, "verify_healing_result",
                            lambda eid, s: {"error": "boom"})
        r = engine.batch_verify_completed(db, hours=24)
        assert r["total_verified"] == 1
        assert r["results"]["errors"] == 1

    def test_exception_branch(self, engine, db, monkeypatch):
        st = make_station(db, "B4")
        dev = make_device(db, st, sn="B4-DEV", status=DeviceStatus.ONLINE)
        al = make_alarm(db, dev, st, status=AlarmStatus.RESOLVED)
        rule = make_rule(db)
        make_execution(db, rule, al, status="success", verified=False)
        # verify 抛异常 → 计入 errors（覆盖 except 分支）
        def _raise(eid, s):
            raise RuntimeError("verify-crash")
        monkeypatch.setattr(engine, "verify_healing_result", _raise)
        r = engine.batch_verify_completed(db, hours=24)
        assert r["total_verified"] == 1
        assert r["results"]["errors"] == 1


# ========== 规则管理 / 执行记录 / 统计（service 直调补行覆盖）==========

class TestRuleManagementService:

    def test_list_rules_enabled_only(self, engine, db):
        make_rule(db, name="启用", enabled=True, priority=5)
        make_rule(db, name="禁用", enabled=False, priority=10)
        all_rules = engine.list_rules(db, enabled_only=False)
        enabled = engine.list_rules(db, enabled_only=True)
        assert len(all_rules) == 2
        assert len(enabled) == 1
        assert enabled[0]["name"] == "启用"
        # 禁用规则仍出现在全量列表
        assert any(r["name"] == "禁用" for r in all_rules)

    def test_list_rules_serialization(self, engine, db):
        rule = make_rule(db, name="序列化", alarm_pattern={"alarm_levels": ["warning"]})
        items = engine.list_rules(db)
        item = next(r for r in items if r["id"] == rule.id)
        assert item["alarm_pattern"] == {"alarm_levels": ["warning"]}
        assert item["priority"] == 10
        assert item["created_at"] is not None

    def test_update_rule_not_found(self, engine, db):
        r = engine.update_rule(99999, {"name": "x"}, db)
        assert "不存在" in r["error"]

    def test_update_rule_success(self, engine, db):
        rule = make_rule(db, name="原名")
        r = engine.update_rule(rule.id, {"name": "新名", "priority": 99, "enabled": False}, db)
        assert r["name"] == "新名"
        db.refresh(rule)
        assert rule.priority == 99
        assert rule.enabled is False

    def test_delete_rule_not_found(self, engine, db):
        r = engine.delete_rule(99999, db)
        assert "不存在" in r["error"]

    def test_delete_rule_blocked_by_active_execution(self, engine, db):
        st = make_station(db, "D1")
        dev = make_device(db, st, sn="D1-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        make_execution(db, rule, al, status="running")
        r = engine.delete_rule(rule.id, db)
        assert "正在执行" in r["error"]

    def test_delete_rule_success(self, engine, db):
        rule = make_rule(db, name="待删")
        r = engine.delete_rule(rule.id, db)
        assert r["message"] == "删除成功"
        assert db.query(HealingRule).filter(HealingRule.id == rule.id).first() is None


class TestExecutionQueryService:

    def test_list_executions_with_station_scope(self, engine, db):
        st = make_station(db, "L1")
        dev = make_device(db, st, sn="L1-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        make_execution(db, rule, al, status="success")
        # station_ids 限定为空列表 → 隔离返回 0
        r = engine.list_executions(db, station_ids=[])
        assert r["total"] == 0
        # 限定为本站 → 命中
        r2 = engine.list_executions(db, station_ids=[st.id])
        assert r2["total"] == 1
        assert r2["items"][0]["station_id"] == st.id

    def test_list_executions_filters(self, engine, db):
        st = make_station(db, "L2")
        dev = make_device(db, st, sn="L2-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        make_execution(db, rule, al, status="success")
        make_execution(db, rule, al, status="failed")
        r = engine.list_executions(db, status="success")
        assert r["total"] == 1
        assert all(it["status"] == "success" for it in r["items"])

    def test_list_executions_pagination(self, engine, db):
        st = make_station(db, "L3")
        dev = make_device(db, st, sn="L3-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        for _ in range(5):
            make_execution(db, rule, al, status="success")
        r = engine.list_executions(db, page=1, page_size=2)
        assert r["total"] == 5
        assert len(r["items"]) == 2
        assert r["page"] == 1
        assert r["page_size"] == 2

    def test_get_execution_not_found(self, engine, db):
        assert engine.get_execution(99999, db) is None

    def test_get_execution_detail(self, engine, db):
        st = make_station(db, "L4")
        dev = make_device(db, st, sn="L4-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, runbook_template="tpl")
        ex = make_execution(db, rule, al, status="success")
        d = engine.get_execution(ex.id, db)
        assert d["id"] == ex.id
        assert d["runbook_template"] == "tpl"
        assert d["status"] == "success"


class TestStatsService:

    def test_stats_empty(self, engine, db):
        s = engine.get_stats(db)
        assert s["total"] == 0
        assert s["success_rate"] == 0
        assert s["auto_approve_rate"] == 0
        assert s["pending_approvals"] == 0

    def test_stats_with_data(self, engine, db):
        st = make_station(db, "S1")
        dev = make_device(db, st, sn="S1-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        make_execution(db, rule, al, status="success")
        make_execution(db, rule, al, status="partial_success")
        make_execution(db, rule, al, status="failed")
        # 自动执行的标记 approved_by=auto
        ex_auto = make_execution(db, rule, al, status="success")
        ex_auto.approved_by = "auto"
        db.commit()
        s = engine.get_stats(db)
        assert s["total"] == 4
        assert s["status_breakdown"]["success"] == 2
        # success(2)+partial(1) = 3 / 4 = 75.0
        assert s["success_rate"] == 75.0
        # auto 1 / 4 = 25.0
        assert s["auto_approve_rate"] == 25.0


# ========== 审批 / 重试（service 直调，覆盖与 API 不同的内部返回结构）==========

class TestApproveRejectRetryService:

    def test_approve_not_found(self, engine, db):
        r = engine.approve_execution(99999, "u", db)
        assert "不存在" in r["error"]

    def test_approve_wrong_status(self, engine, db):
        st = make_station(db, "A1")
        dev = make_device(db, st, sn="A1-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="success")
        r = engine.approve_execution(ex.id, "u", db)
        assert "不可审批" in r["error"]

    def test_approve_pending_then_execute(self, engine, db):
        st = make_station(db, "A2")
        dev = make_device(db, st, sn="A2-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="pending_approval")
        engine._runbook_engine.execute.return_value = _rb_result(status="success")
        r = engine.approve_execution(ex.id, "审批人", db)
        assert r["status"] == "success"
        db.refresh(ex)
        assert ex.approved_by == "审批人"

    def test_reject_not_found(self, engine, db):
        r = engine.reject_execution(99999, "u", "理由", db)
        assert "不存在" in r["error"]

    def test_reject_wrong_status(self, engine, db):
        st = make_station(db, "A3")
        dev = make_device(db, st, sn="A3-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="success")
        r = engine.reject_execution(ex.id, "u", "理由", db)
        assert "不可拒绝" in r["error"]

    def test_reject_pending_success(self, engine, db):
        st = make_station(db, "A4")
        dev = make_device(db, st, sn="A4-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="pending_approval")
        r = engine.reject_execution(ex.id, "拒绝人", "现场处理", db)
        assert r["status"] == "rejected"
        db.refresh(ex)
        assert ex.status == "rejected"
        assert ex.approved_by == "拒绝人"
        assert ex.reject_reason == "现场处理"

    def test_retry_not_found(self, engine, db):
        r = engine.retry_execution(99999, db)
        assert "不存在" in r["error"]

    def test_retry_wrong_status(self, engine, db):
        st = make_station(db, "A5")
        dev = make_device(db, st, sn="A5-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db)
        ex = make_execution(db, rule, al, status="pending_approval")
        r = engine.retry_execution(ex.id, db)
        assert "不可重试" in r["error"]

    def test_retry_exceeds_max(self, engine, db):
        st = make_station(db, "A6")
        dev = make_device(db, st, sn="A6-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, max_retries=2)
        ex = make_execution(db, rule, al, status="failed")
        ex.retry_count = 2
        db.commit()
        r = engine.retry_execution(ex.id, db)
        assert "最大重试次数" in r["error"]

    def test_retry_success_path(self, engine, db):
        st = make_station(db, "A7")
        dev = make_device(db, st, sn="A7-DEV")
        al = make_alarm(db, dev, st)
        rule = make_rule(db, max_retries=3)
        ex = make_execution(db, rule, al, status="failed")
        engine._runbook_engine.execute.return_value = _rb_result(status="success")
        r = engine.retry_execution(ex.id, db)
        assert r["status"] == "success"
        db.refresh(ex)
        assert ex.retry_count == 1
