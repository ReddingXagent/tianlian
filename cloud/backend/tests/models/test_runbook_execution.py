#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runbook Execution 模型测试
"""
import pytest
from app.models.runbook_execution import RunbookExecutionRecord as RunbookExecutionRecord

class TestRunbookExecutionModel:
    def test_runbook_execution_columns(self):
        cols = [c.name for c in RunbookExecutionRecord.__table__.columns]
        assert "id" in cols
        assert "fault_type" in cols  # RunbookExecutionRecord uses fault_type
        assert "device_id" in cols
        assert "alarm_id" in cols
        assert "status" in cols
        assert "steps_json" in cols  # RunbookExecutionRecord uses steps_json
        assert "success_steps" in cols  # RunbookExecutionRecord uses success_steps
        assert "error_message" in cols  # RunbookExecutionRecord uses error_message
        assert "start_time" in cols  # RunbookExecutionRecord uses start_time
        assert "end_time" in cols  # RunbookExecutionRecord uses end_time