#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fault Code 模型测试
"""
import pytest
from app.models.fault_code import FaultCode, FaultLevel, FaultCategory, DiagnosisRule, RepairGuide

class TestFaultCodeModel:
    def test_fault_level_enum_values(self):
        assert FaultLevel.EMERGENCY.value == "emergency"
        assert FaultLevel.SERIOUS.value == "serious"
        assert FaultLevel.WARNING_SERIOUS.value == "warning_serious"
        assert FaultLevel.WARNING_GENERAL.value == "warning_general"

    def test_fault_category_enum_values(self):
        assert FaultCategory.GRID.value == "grid"
        assert FaultCategory.INVERTER.value == "inverter"
        assert FaultCategory.BATTERY.value == "battery"
        assert FaultCategory.BUS.value == "bus"
        assert FaultCategory.TEMPERATURE.value == "temperature"
        assert FaultCategory.RELAY.value == "relay"
        assert FaultCategory.OVERLOAD.value == "overload"
        assert FaultCategory.OTHER.value == "other"
        assert FaultCategory.BCU_BMS.value == "bcu_bms"

    def test_fault_code_columns(self):
        cols = [c.name for c in FaultCode.__table__.columns]
        assert "id" in cols
        assert "fault_code" in cols  # FaultCode model uses fault_code
        assert "fault_level" in cols  # FaultCode uses fault_level
        assert "fault_category" in cols  # FaultCode uses fault_category
        assert "fault_description" in cols  # FaultCode uses fault_description
        assert "repair_suggestions" in cols  # FaultCode uses repair_suggestions

    def test_diagnosis_rule_columns(self):
        cols = [c.name for c in DiagnosisRule.__table__.columns]
        assert "id" in cols
        assert "conditions" in cols  # DiagnosisRule uses conditions
        assert "priority" in cols  # DiagnosisRule uses priority
        assert "enabled" in cols  # DiagnosisRule uses enabled

    def test_repair_guide_columns(self):
        cols = [c.name for c in RepairGuide.__table__.columns]
        assert "id" in cols
        assert "symptoms" in cols
        assert "repair_steps" in cols  # RepairGuide uses repair_steps