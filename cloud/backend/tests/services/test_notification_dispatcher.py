#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知分发器服务测试
"""
import pytest
from app.services.notification_dispatcher import NotificationDispatcher, notification_dispatcher

class TestNotificationDispatcher:
    def test_singleton_exists(self):
        assert notification_dispatcher is not None
        assert isinstance(notification_dispatcher, NotificationDispatcher)

    def test_has_dispatch_method(self):
        assert hasattr(notification_dispatcher, "dispatch")
        assert callable(notification_dispatcher.dispatch)

    def test_dispatch_returns_result(self, test_db):
        result = notification_dispatcher.dispatch(
            alarm_id=1,
            level="warning",
            message="测试告警通知",
            channels=["sms"]
        )
        assert result is not None

    def test_has_notify_sms_method(self):
        assert hasattr(notification_dispatcher, "notify_sms") or hasattr(notification_dispatcher, "send_sms")

    def test_has_notify_email_method(self):
        assert hasattr(notification_dispatcher, "notify_email") or hasattr(notification_dispatcher, "send_email")

    def test_has_notify_im_method(self):
        assert hasattr(notification_dispatcher, "notify_im") or hasattr(notification_dispatcher, "send_im")

    def test_has_notify_webhook_method(self):
        assert hasattr(notification_dispatcher, "notify_webhook") or hasattr(notification_dispatcher, "send_webhook")

    def test_get_notification_history(self):
        history = notification_dispatcher.get_history(page=1, page_size=10)
        assert isinstance(history, list) or isinstance(history, dict)

    def test_notification_dispatcher_attributes(self):
        attrs = [a for a in dir(notification_dispatcher) if not a.startswith('_')]
        assert len(attrs) >= 5