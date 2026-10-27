#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Healing Execution 模型测试
"""
import pytest
from app.models.healing_execution import HealingExecution

class TestHealingExecutionModel:
    def test_healing_execution_columns(self):
        cols = [c.name for c in HealingExecution.__table__.columns]
        assert "id" in cols
        assert "rule_id" in cols
        assert "rule_name" in cols
        assert "alarm_id" in cols
        assert "device_id" in cols
        assert "station_id" in cols
        assert "runbook_id" in cols
        assert "runbook_template" in cols
        assert "fault_type" in cols
        assert "status" in cols
        assert "result" in cols
        assert "started_at" in cols
        assert "completed_at" in cols
        assert "error_message" in cols

    def test_healing_execution_indexes(self):
        assert HealingExecution.__table__.columns["rule_id"].index
        assert HealingExecution.__table__.columns["alarm_id"].index
        assert HealingExecution.__table__.columns["device_id"].index