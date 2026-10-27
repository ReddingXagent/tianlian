#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alarm 模型测试
"""
import pytest
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus, AlarmRule, AlarmRuleLog

class TestAlarmModel:
    def test_alarm_level_enum_values(self):
        assert AlarmLevel.INFO.value == "info"
        assert AlarmLevel.WARNING.value == "warning"
        assert AlarmLevel.CRITICAL.value == "critical"
        assert AlarmLevel.FATAL.value == "fatal"

    def test_alarm_status_enum_values(self):
        assert AlarmStatus.ACTIVE.value == "active"
        assert AlarmStatus.ACKNOWLEDGED.value == "acknowledged"
        assert AlarmStatus.PROCESSING.value == "processing"
        assert AlarmStatus.RESOLVED.value == "resolved"
        assert AlarmStatus.PROCESSED.value == "processed"
        assert AlarmStatus.IGNORED.value == "ignored"

    def test_alarm_columns_exist(self):
        cols = [c.name for c in Alarm.__table__.columns]
        assert "id" in cols
        assert "level" in cols
        assert "status" in cols
        assert "device_id" in cols
        assert "content" in cols  # Alarm模型使用content字段，不是message

    def test_alarm_rule_columns_exist(self):
        cols = [c.name for c in AlarmRule.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "metric" in cols
        assert "operator" in cols
        assert "threshold" in cols

    def test_alarm_rule_log_columns_exist(self):
        cols = [c.name for c in AlarmRuleLog.__table__.columns]
        assert "id" in cols
        assert "rule_id" in cols
        assert "metric" in cols  # AlarmRuleLog uses metric  # AlarmRule has enabled not action