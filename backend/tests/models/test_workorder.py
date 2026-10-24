#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkOrder 模型测试
"""
import pytest
from app.models.workorder import WorkOrder, WorkOrderLog

class TestWorkOrderModel:
    def test_workorder_columns(self):
        cols = [c.name for c in WorkOrder.__table__.columns]
        assert "id" in cols
        assert "fault_desc" in cols  # WorkOrder uses fault_desc
        assert "solution" in cols  # WorkOrder uses solution
        assert "status" in cols
        assert "level" in cols  # WorkOrder uses level
        assert "device_id" in cols
        assert "station_id" in cols
        assert "creator_id" in cols  # WorkOrder uses creator_id
        assert "assignee_id" in cols
        assert "creator_id" in cols
        assert "type" in cols  # WorkOrder uses type
        assert "create_time" in cols  # WorkOrder uses create_time
        assert "finish_time" in cols  # WorkOrder uses finish_time
        assert "verify_time" in cols  # WorkOrder uses verify_time
        assert "accept_time" in cols  # WorkOrder uses accept_time

    def test_workorder_log_columns(self):
        cols = [c.name for c in WorkOrderLog.__table__.columns]
        assert "id" in cols
        assert "order_id" in cols  # WorkOrderLog uses order_id
        assert "action" in cols
        assert "user_id" in cols  # WorkOrderLog uses user_id
        assert "attachments" in cols  # WorkOrderLog uses attachments
        assert "created_at" in cols  # WorkOrderLog uses created_at