"""test_device_log_simulator.py — 设备日志模拟器单元测试

覆盖: _fill 模板填充, generate_normal_logs, generate_fault_logs (已知/未知故障码),
get_logs_for_alarm, 常量模板完整性。
"""
import pytest
from app.services.device_log_simulator import DeviceLogSimulator


# ─── _fill ───

class TestFill:
    def test_fill_with_defaults(self):
        result = DeviceLogSimulator._fill("电压: {voltage}V")
        assert "电压:" in result
        assert "V" in result

    def test_fill_with_custom_kwargs(self):
        result = DeviceLogSimulator._fill("电压: {voltage}V", voltage=230.5)
        assert "230.5" in result

    def test_fill_multiple_placeholders(self):
        result = DeviceLogSimulator._fill("{voltage}V {freq}Hz {temp}°C")
        assert "V" in result
        assert "Hz" in result
        assert "°C" in result

    def test_fill_overrides_defaults(self):
        result = DeviceLogSimulator._fill("{temp}°C", temp=99.9)
        assert "99.9" in result


# ─── generate_normal_logs ───

class TestGenerateNormalLogs:
    def test_inverter_normal_logs(self):
        logs = DeviceLogSimulator.generate_normal_logs("inverter", count=5)
        assert len(logs) == 5
        assert all(isinstance(l, str) for l in logs)
        assert all("[" in l for l in logs)  # has timestamp

    def test_charger_normal_logs(self):
        logs = DeviceLogSimulator.generate_normal_logs("charger", count=3)
        assert len(logs) == 3

    def test_default_count(self):
        logs = DeviceLogSimulator.generate_normal_logs()
        assert len(logs) == 10

    def test_log_has_timestamp_prefix(self):
        logs = DeviceLogSimulator.generate_normal_logs("inverter", count=1)
        assert logs[0].startswith("[20")  # year prefix


# ─── generate_fault_logs ───

class TestGenerateFaultLogs:
    def test_known_inverter_fault(self):
        logs = DeviceLogSimulator.generate_fault_logs("0x01", "inverter")
        assert len(logs) > 0
        assert any("ERROR" in l or "WARN" in l for l in logs)

    def test_known_charger_fault(self):
        logs = DeviceLogSimulator.generate_fault_logs("0x0101", "charger")
        assert len(logs) > 0
        assert any("ERROR" in l or "WARN" in l for l in logs)

    def test_unknown_fault_code(self):
        logs = DeviceLogSimulator.generate_fault_logs("0xZZZZ", "inverter")
        assert len(logs) > 0
        assert any("未知故障码" in l for l in logs)

    def test_fault_logs_include_normal_prefix(self):
        """故障日志应在故障前有正常运行日志"""
        logs = DeviceLogSimulator.generate_fault_logs("0x01", "inverter")
        # First few should be INFO/DEBUG (normal), later should have WARN/ERROR
        assert any("INFO" in l or "DEBUG" in l for l in logs)


# ─── get_logs_for_alarm ───

class TestGetLogsForAlarm:
    def test_returns_logs(self):
        logs = DeviceLogSimulator.get_logs_for_alarm("inverter", "0x01", "过压")
        assert len(logs) > 0
        assert all(isinstance(l, str) for l in logs)

    def test_default_fault_code(self):
        logs = DeviceLogSimulator.get_logs_for_alarm("inverter")
        assert len(logs) > 0

    def test_charger_device_type(self):
        logs = DeviceLogSimulator.get_logs_for_alarm("charger", "0x0101")
        assert len(logs) > 0


# ─── 常量完整性 ───

class TestConstants:
    def test_inverter_normal_templates_exist(self):
        assert len(DeviceLogSimulator.INVERTER_NORMAL_LOGS) > 0

    def test_charger_normal_templates_exist(self):
        assert len(DeviceLogSimulator.CHARGER_NORMAL_LOGS) > 0

    def test_inverter_fault_codes(self):
        assert "0x01" in DeviceLogSimulator.INVERTER_FAULT_LOGS
        assert "0x27" in DeviceLogSimulator.INVERTER_FAULT_LOGS
        assert "0xA0" in DeviceLogSimulator.INVERTER_FAULT_LOGS

    def test_charger_fault_codes(self):
        assert "0x0101" in DeviceLogSimulator.CHARGER_FAULT_LOGS
        assert "0x0601" in DeviceLogSimulator.CHARGER_FAULT_LOGS

    def test_fault_log_templates_are_lists(self):
        for code, logs in DeviceLogSimulator.INVERTER_FAULT_LOGS.items():
            assert isinstance(logs, list)
            assert len(logs) > 0


# ─── 健壮性 (异常路径) [卡101bdfb3] ───

class TestRobustness:
    """未知输入/缺陷模板不应让模拟器崩溃。"""

    def test_fill_missing_placeholder_does_not_raise(self):
        """模板含 defaults 未定义的占位符 → 不抛 KeyError, 返回安全字符串。"""
        result = DeviceLogSimulator._fill("异常字段: {totally_unknown_field}")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fill_mixed_known_and_unknown_placeholders(self):
        """已知占位符正常填充, 未知占位符不致整体崩溃。"""
        result = DeviceLogSimulator._fill("{voltage}V / {ghost_field}", voltage=230.0)
        assert isinstance(result, str)
        assert "230.0" in result

    def test_generate_normal_logs_unknown_device_type_falls_back(self):
        """未知 device_type → 回退默认模板, 仍返回 count 条日志。"""
        logs = DeviceLogSimulator.generate_normal_logs("totally_unknown_type", count=4)
        assert isinstance(logs, list)
        assert len(logs) == 4
        assert all(isinstance(l, str) and l for l in logs)

    def test_generate_fault_logs_unknown_device_type_falls_back(self):
        """未知 device_type → 回退默认故障模板, 返回非空日志列表。"""
        logs = DeviceLogSimulator.generate_fault_logs("0x01", "totally_unknown_type")
        assert isinstance(logs, list)
        assert len(logs) > 0

    def test_get_logs_for_alarm_unknown_device_type_does_not_raise(self):
        """未知 device_type 不应抛异常。"""
        logs = DeviceLogSimulator.get_logs_for_alarm("totally_unknown_type", "0x01")
        assert isinstance(logs, list)
