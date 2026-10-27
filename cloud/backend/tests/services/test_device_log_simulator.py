#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备日志模拟器测试

测试对齐 DeviceLogSimulator 实际 API:
- generate_normal_logs(device_type, count) -> List[str]
- generate_fault_logs(fault_code, device_type) -> List[str]
- get_logs_for_alarm(device_type, fault_code, fault_name) -> List[str]
"""
import pytest
from app.services.device_log_simulator import DeviceLogSimulator

class TestDeviceLogSimulator:
    def test_simulator_initialization(self):
        sim = DeviceLogSimulator()
        assert sim is not None

    def test_inverter_logs_defined(self):
        assert hasattr(DeviceLogSimulator, "INVERTER_NORMAL_LOGS")
        assert len(DeviceLogSimulator.INVERTER_NORMAL_LOGS) > 0

    def test_generate_normal_inverter_log(self):
        sim = DeviceLogSimulator()
        logs = sim.generate_normal_logs(device_type="inverter", count=1)
        assert isinstance(logs, list)
        assert len(logs) == 1
        assert isinstance(logs[0], str)
        assert len(logs[0]) > 0

    def test_generate_normal_charger_log(self):
        sim = DeviceLogSimulator()
        logs = sim.generate_normal_logs(device_type="charger", count=1)
        assert isinstance(logs, list)
        assert len(logs) == 1
        assert isinstance(logs[0], str)

    def test_generate_fault_log(self):
        sim = DeviceLogSimulator()
        logs = sim.generate_fault_logs(fault_code="0x01", device_type="inverter")
        assert logs is not None
        assert isinstance(logs, list)
        assert len(logs) > 0
        assert all(isinstance(log, str) for log in logs)

    def test_generate_logs_batch(self):
        sim = DeviceLogSimulator()
        logs = sim.generate_normal_logs(device_type="inverter", count=10)
        assert isinstance(logs, list)
        assert len(logs) == 10

    def test_generate_logs_with_faults(self):
        sim = DeviceLogSimulator()
        logs = sim.generate_fault_logs(fault_code="0x01", device_type="inverter")
        assert isinstance(logs, list)
        assert len(logs) > 0

    def test_station_log_generation(self):
        sim = DeviceLogSimulator()
        logs = sim.get_logs_for_alarm(device_type="inverter", fault_code="0x01")
        assert isinstance(logs, list)
        assert len(logs) > 0


class TestDeviceLogSimulatorRobustness:
    """[卡101bdfb3] 未知输入/缺陷模板不应让模拟器崩溃。"""

    def test_fill_missing_placeholder_does_not_raise(self):
        result = DeviceLogSimulator._fill("异常字段: {totally_unknown_field}")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_normal_logs_unknown_device_type_falls_back(self):
        logs = DeviceLogSimulator.generate_normal_logs("totally_unknown_type", count=4)
        assert isinstance(logs, list)
        assert len(logs) == 4

    def test_generate_fault_logs_unknown_device_type_falls_back(self):
        logs = DeviceLogSimulator.generate_fault_logs("0x01", "totally_unknown_type")
        assert isinstance(logs, list)
        assert len(logs) > 0

    def test_get_logs_for_alarm_unknown_device_type_does_not_raise(self):
        logs = DeviceLogSimulator.get_logs_for_alarm("totally_unknown_type", "0x01")
        assert isinstance(logs, list)
