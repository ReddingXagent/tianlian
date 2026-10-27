#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit Log 模型测试
"""
import pytest
from app.models.audit_log import AuditLog, AuditAction, AuditModule

class TestAuditLogModel:
    def test_audit_action_enum_values(self):
        assert AuditAction.LOGIN.value == "login"
        assert AuditAction.LOGOUT.value == "logout"
        assert AuditAction.CREATE.value == "create"
        assert AuditAction.UPDATE.value == "update"
        assert AuditAction.DELETE.value == "delete"
        assert AuditAction.EXPORT.value == "export"
        assert AuditAction.DISPATCH.value == "dispatch"
        assert AuditAction.CONFIG.value == "config"
        assert AuditAction.OTHER.value == "other"

    def test_audit_module_enum_values(self):
        assert AuditModule.AUTH.value == "auth"
        assert AuditModule.USERS.value == "users"
        assert AuditModule.STATIONS.value == "stations"
        assert AuditModule.DEVICES.value == "devices"
        assert AuditModule.ALARMS.value == "alarms"
        assert AuditModule.WORKORDERS.value == "workorders"
        assert AuditModule.KNOWLEDGE.value == "knowledge"
        assert AuditModule.REPORTS.value == "reports"

    def test_audit_log_columns(self):
        cols = [c.name for c in AuditLog.__table__.columns]
        assert "id" in cols
        assert "user_id" in cols
        assert "action" in cols
        assert "module" in cols
        assert "target_id" in cols
        assert "detail" in cols
        assert "ip_address" in cols