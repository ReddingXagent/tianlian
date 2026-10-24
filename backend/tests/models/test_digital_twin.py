#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Digital Twin 模型测试
"""
import pytest
from app.models.digital_twin import DigitalTwinModel, DigitalTwinScene, DigitalTwinDataPoint, ThreeDModelType

class TestDigitalTwinModel:
    def test_3d_model_type_enum_values(self):
        assert ThreeDModelType.SOLAR_INVERTER.value == "solar_inverter"
        assert ThreeDModelType.BATTERY_INVERTER.value == "battery_inverter"
        assert ThreeDModelType.PCS.value == "pcs"
        assert ThreeDModelType.BATTERY_RACK.value == "battery_rack"
        assert ThreeDModelType.CHARGER_DC.value == "charger_dc"
        assert ThreeDModelType.CHARGER_AC.value == "charger_ac"
        assert ThreeDModelType.GATEWAY.value == "gateway"
        assert ThreeDModelType.METER.value == "meter"
        assert ThreeDModelType.TRANSFORMER.value == "transformer"
        assert ThreeDModelType.PANEL.value == "panel"

    def test_digital_twin_model_columns(self):
        cols = [c.name for c in DigitalTwinModel.__table__.columns]
        assert "id" in cols
        assert "device_id" in cols
        assert "model_type" in cols
        assert "position_x" in cols
        assert "position_y" in cols
        assert "position_z" in cols

    def test_digital_twin_scene_columns(self):
        cols = [c.name for c in DigitalTwinScene.__table__.columns]
        assert "id" in cols
        assert "station_id" in cols
        assert "name" in cols
        assert "scene_config" in cols  # DigitalTwinScene uses scene_config

    def test_digital_twin_data_point_columns(self):
        cols = [c.name for c in DigitalTwinDataPoint.__table__.columns]
        assert "id" in cols
        assert "device_id" in cols
        assert "param_key" in cols  # DigitalTwinDataPoint uses param_key
        assert "display_name" in cols  # DigitalTwinDataPoint uses display_name

    def test_digital_twin_model_uniqueness(self):
        assert DigitalTwinModel.__table__.columns["device_id"].unique