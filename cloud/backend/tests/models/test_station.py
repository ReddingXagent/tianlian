#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Station 模型测试
"""
import pytest
from app.models.station import Station, ApprovalStatus

class TestStationModel:
    def test_station_columns(self):
        cols = [c.name for c in Station.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "code" in cols
        assert "address" in cols
        assert "lat" in cols  # Station uses lat
        assert "lon" in cols  # Station uses lon
        assert "status" in cols
        assert "total_power" in cols  # Station uses total_power
        assert "total_devices" in cols  # Station uses total_devices
        assert "gun_count" in cols  # Station uses gun_count
        assert "operator_name" in cols  # Station uses operator_name
        assert "health_score" in cols  # Station uses health_score

    # ── 任务卡 1256e7fa：审核策略预留字段 ──
    def test_approval_status_enum_values(self):
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.REJECTED.value == "rejected"

    def test_station_approval_status_column_and_default(self):
        cols = [c.name for c in Station.__table__.columns]
        assert "approval_status" in cols
        default_arg = Station.__table__.c.approval_status.default
        assert default_arg is not None
        assert default_arg.arg.value == "approved"

    def test_code_uniqueness(self):
        assert Station.__table__.columns["code"].unique

    def test_relationships_exist(self):
        assert hasattr(Station, "devices")
        assert hasattr(Station, "operator_id")  # Station has operator_id FK