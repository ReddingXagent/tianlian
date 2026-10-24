#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notification Rule 模型测试
"""
import pytest
from app.models.notification_rule import NotificationRule

class TestNotificationRuleModel:
    def test_notification_rule_columns(self):
        cols = [c.name for c in NotificationRule.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "level" in cols
        assert "channels" in cols
        assert "receivers" in cols
        assert "enabled" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_level_indexed(self):
        assert NotificationRule.__table__.columns["level"].index

    def test_channel_and_receivers_as_json(self):
        col_channels = NotificationRule.__table__.columns["channels"]
        col_receivers = NotificationRule.__table__.columns["receivers"]
        assert "JSON" in str(col_channels.type).upper()
        assert "JSON" in str(col_receivers.type).upper()

    def test_to_dict_method_exists(self):
        assert hasattr(NotificationRule, "to_dict")

    def test_default_enabled(self):
        assert NotificationRule.__table__.columns["enabled"].default.arg is True