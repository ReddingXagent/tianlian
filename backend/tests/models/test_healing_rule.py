#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Healing Rule 模型测试
"""
import pytest
from app.models.healing_rule import HealingRule

class TestHealingRuleModel:
    def test_healing_rule_columns(self):
        cols = [c.name for c in HealingRule.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "description" in cols
        assert "alarm_pattern" in cols
        assert "runbook_template" in cols
        assert "auto_approve" in cols
        assert "max_retries" in cols
        assert "cooldown_minutes" in cols
        assert "enabled" in cols
        assert "priority" in cols  # HealingRule uses priority
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_alarm_pattern_is_json(self):
        col = HealingRule.__table__.columns["alarm_pattern"]
        assert "JSON" in str(col.type).upper() or str(col.type).upper() == "JSON"

    def test_default_values(self):
        assert HealingRule.__table__.columns["auto_approve"].default.arg is False
        assert HealingRule.__table__.columns["max_retries"].default.arg == 1
        assert HealingRule.__table__.columns["enabled"].default.arg is True