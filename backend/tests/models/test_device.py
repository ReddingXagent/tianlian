#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Device 模型测试
"""
import pytest
from app.models.device import (
    Device, DeviceHealthRecord, DeviceType, DeviceStatus, ProtocolType,
    ProvisionStatus,
)

class TestDeviceModel:
    def test_device_type_enum_values(self):
        assert DeviceType.CHARGER_DC.value == "charger_dc"
        assert DeviceType.CHARGER_AC.value == "charger_ac"
        assert DeviceType.PV_INVERTER.value == "pv_inverter"
        assert DeviceType.BATTERY_INVERTER.value == "battery_inverter"
        assert DeviceType.PCS.value == "pcs"
        assert DeviceType.BATTERY.value == "battery"
        assert DeviceType.METER.value == "meter"
        assert DeviceType.GATEWAY.value == "gateway"

    def test_device_status_enum_values(self):
        assert DeviceStatus.ONLINE.value == "online"
        assert DeviceStatus.OFFLINE.value == "offline"
        assert DeviceStatus.CHARGING.value == "charging"
        assert DeviceStatus.FAULT.value == "fault"
        assert DeviceStatus.MAINTENANCE.value == "maintenance"

    def test_protocol_type_enum_values(self):
        assert ProtocolType.MODBUS_RTU.value == "modbus_rtu"
        assert ProtocolType.MQTT.value == "mqtt"
        assert ProtocolType.MODBUS_TCP.value == "modbus_tcp"
        assert ProtocolType.CAN.value == "can"
        assert ProtocolType.OPCUA.value == "opcua"

    def test_device_columns(self):
        cols = [c.name for c in Device.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "type" in cols  # Device model uses type
        assert "status" in cols
        assert "station_id" in cols
        assert "protocol_type" in cols  # Device uses protocol_type
        assert "device_address" in cols  # Device uses device_address
        assert "modbus_baudrate" in cols  # Device uses modbus_baudrate

    def test_device_health_record_columns(self):
        cols = [c.name for c in DeviceHealthRecord.__table__.columns]
        assert "id" in cols
        assert "device_id" in cols
        assert "total_score" in cols  # DeviceHealthRecord uses total_score
        assert "created_at" in cols  # DeviceHealthRecord uses created_at

    # ── 任务卡 1256e7fa：入网状态 + 接入凭证字段 ──
    def test_provision_status_enum_values(self):
        assert ProvisionStatus.UNPROVISIONED.value == "unprovisioned"
        assert ProvisionStatus.PROVISIONING.value == "provisioning"
        assert ProvisionStatus.ONLINE.value == "online"

    def test_device_provision_and_credential_columns(self):
        cols = [c.name for c in Device.__table__.columns]
        # 入网状态
        assert "provision_status" in cols
        # 接入凭证（OCPP chargeBoxId / MQTT username+password / 通用 token）
        assert "charge_box_id" in cols
        assert "mqtt_username" in cols
        assert "mqtt_password" in cols
        assert "auth_token" in cols

    def test_device_provision_status_default(self):
        """新建设备未指定 provision_status 时默认 unprovisioned。"""
        col = Device.__table__.c.provision_status
        # 默认值经 SQLEnum + default 表达式，取其字面值
        default_arg = col.default
        assert default_arg is not None
        assert default_arg.arg.value == "unprovisioned"