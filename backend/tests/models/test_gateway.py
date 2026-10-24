#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway 模型测试
"""
import pytest
from app.models.gateway import Gateway, GatewaySN, Firmware, UpgradeTask

class TestGatewayModel:
    def test_gateway_columns(self):
        cols = [c.name for c in Gateway.__table__.columns]
        assert "id" in cols
        assert "sn" in cols
        assert "name" in cols
        assert "model" in cols
        assert "manufacturer" in cols
        assert "station_id" in cols
        assert "status" in cols
        assert "firmware_version" in cols
        assert "ip_address" in cols
        assert "mac_address" in cols

    def test_gateway_sn_unique(self):
        assert Gateway.__table__.columns["sn"].unique

    def test_gateway_sn_columns(self):
        cols = [c.name for c in GatewaySN.__table__.columns]
        assert "id" in cols
        assert "sn" in cols
        assert "model" in cols

    def test_firmware_columns(self):
        cols = [c.name for c in Firmware.__table__.columns]
        assert "id" in cols
        assert "version" in cols
        assert "file_path" in cols
        assert "status" in cols

    def test_upgrade_task_columns(self):
        cols = [c.name for c in UpgradeTask.__table__.columns]
        assert "id" in cols
        assert "gateway_id" in cols
        assert "firmware_id" in cols
        assert "status" in cols