"""
天链 V3 边缘网关 - 测试
"""
import pytest
from app.core.config import load_config, AppConfig


class TestConfig:
    """配置加载测试"""

    def test_load_config(self):
        """测试加载配置文件"""
        config = load_config()
        assert config is not None
        assert config.gateway.sn == "TL-GW-001"
        assert config.cloud.api_base == "http://demo.example.com/api/v1"
        assert config.heartbeat.interval_seconds == 30
        assert config.ocpp.port == 9000
        assert config.modbus.poll_interval_seconds == 5
        assert config.telemetry.report_interval_seconds == 10
        assert config.offline_buffer.enabled is True

    def test_config_types(self):
        """测试配置类型"""
        config = load_config()
        assert isinstance(config, AppConfig)
        assert isinstance(config.gateway.sn, str)
        assert isinstance(config.heartbeat.interval_seconds, int)
        assert isinstance(config.ocpp.enabled, bool)
        assert isinstance(config.modbus.devices, list)


class TestGatewayRegistry:
    """网关注册测试"""

    def test_registry_initial_state(self):
        """测试注册器初始状态"""
        from app.modules.registry import gateway_registry
        assert gateway_registry.is_registered is False
        assert gateway_registry.is_online is False
        assert gateway_registry.gateway_id is None


class TestOCPPServer:
    """OCPP 服务端测试"""

    def test_ocpp_server_initial_state(self):
        """测试 OCPP 服务端初始状态"""
        from app.modules.ocpp_server import ocpp_server
        assert len(ocpp_server.connections) == 0


class TestModbusMaster:
    """Modbus 主站测试"""

    def test_modbus_master_initial_state(self):
        """测试 Modbus 主站初始状态"""
        from app.modules.modbus_master import modbus_master
        assert len(modbus_master.devices) == 0


class TestTelemetryReporter:
    """遥测上报测试"""

    def test_telemetry_reporter_initial_state(self):
        """测试遥测上报器初始状态"""
        from app.modules.telemetry_reporter import telemetry_reporter
        stats = telemetry_reporter.stats
        assert stats["total_reported"] == 0
        assert stats["total_failed"] == 0
        assert stats["buffer_size"] == 0

    def test_transform_modbus_data_empty(self):
        """测试空数据转换"""
        from app.modules.telemetry_reporter import telemetry_reporter
        result = telemetry_reporter._transform_modbus_data({})
        assert result is None

    def test_transform_modbus_data_disconnected(self):
        """测试断开连接的数据转换"""
        from app.modules.telemetry_reporter import telemetry_reporter
        result = telemetry_reporter._transform_modbus_data({"connected": False})
        assert result is None

    def test_transform_modbus_data_valid(self):
        """测试有效数据转换"""
        from app.modules.telemetry_reporter import telemetry_reporter
        raw = {
            "device_id": 1,
            "device_name": "test-device",
            "timestamp": "2026-01-01T00:00:00",
            "connected": True,
            "registers": {
                "holding_0_49": [1, 2, 100, 220] + [0] * 46,
                "input_0_49": [2200, 2210, 2190, 500, 510, 490, 10000, 5000, 990, 350] + [0] * 40,
                "coils_0_15": [1, 0, 0, 1] + [0] * 12,
            },
        }
        result = telemetry_reporter._transform_modbus_data(raw)
        assert result is not None
        assert result["device_id"] == 1
        assert result["source"] == "modbus"
        assert result["data"]["run_mode"] == 1
        assert result["data"]["voltage_a"] == 220.0
        assert result["data"]["power_total"] == 100.0
        assert result["data"]["frequency"] == 50.0
        assert result["data"]["running"] is True
        assert result["data"]["fault"] is False


class TestOfflineBuffer:
    """断网续传测试"""

    def test_offline_buffer_initial_state(self):
        """测试离线缓存初始状态"""
        from app.modules.offline_buffer import offline_buffer
        stats = offline_buffer.stats
        assert stats["total_buffered"] == 0
        assert stats["total_retried"] == 0
        assert stats["total_flushed"] == 0


class TestHelpers:
    """工具函数测试"""

    def test_get_local_ip(self):
        """测试获取本地 IP"""
        from app.utils.helpers import get_local_ip
        ip = get_local_ip()
        assert ip is not None

    def test_get_host_info(self):
        """测试获取主机信息"""
        from app.utils.helpers import get_host_info
        info = get_host_info()
        assert "hostname" in info
        assert "platform" in info
        assert "python_version" in info
