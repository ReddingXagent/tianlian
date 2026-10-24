"""data_collector 单元测试 — DataCollectionManager 向后兼容代理"""
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from app.services.data_collector import DataCollectionManager


class TestDataCollectionManagerInit:
    """DataCollectionManager.__init__"""

    def test_empty_adapters(self):
        mgr = DataCollectionManager()
        assert mgr.adapters == {}

    def test_empty_device_config(self):
        mgr = DataCollectionManager()
        assert mgr.device_config == {}


class TestRegisterDevice:
    """register_device"""

    def test_register_modbus_rtu(self):
        mgr = DataCollectionManager()
        with patch("app.services.data_collector.ModbusRTUAdapter") as mock_adapter:
            mgr.register_device(1, "modbus_rtu", {"port": "/dev/ttyUSB0", "baudrate": 9600})
            mock_adapter.assert_called_once_with(port="/dev/ttyUSB0", baudrate=9600)
            assert "1" in mgr.adapters

    def test_register_mqtt(self):
        mgr = DataCollectionManager()
        with patch("app.services.data_collector.MQTTAdapter") as mock_adapter:
            mgr.register_device(2, "mqtt", {"broker": "localhost", "port": 1883})
            mock_adapter.assert_called_once_with(broker="localhost", port=1883)
            assert "2" in mgr.adapters

    def test_register_rest(self):
        mgr = DataCollectionManager()
        with patch("app.services.data_collector.RESTAdapter") as mock_adapter:
            mgr.register_device(3, "rest", {"base_url": "http://example.com"})
            mock_adapter.assert_called_once_with(base_url="http://example.com")
            assert "3" in mgr.adapters

    def test_register_extracts_device_address(self):
        """device_address 从 config 中弹出，不传给适配器"""
        mgr = DataCollectionManager()
        with patch("app.services.data_collector.ModbusRTUAdapter") as mock_adapter:
            mgr.register_device(
                1, "modbus_rtu",
                {"port": "/dev/ttyUSB0", "device_address": 5}
            )
            # device_address 不应传给适配器
            mock_adapter.assert_called_once_with(port="/dev/ttyUSB0")
            # device_address 保存在 config 中
            assert mgr.device_config[1]["device_address"] == 5

    def test_register_unknown_protocol(self):
        """未知协议不创建适配器"""
        mgr = DataCollectionManager()
        mgr.register_device(99, "unknown_proto", {})
        assert "99" not in mgr.adapters
        # device_config 仍然保存了
        assert 99 in mgr.device_config

    def test_register_multiple_devices(self):
        mgr = DataCollectionManager()
        with patch("app.services.data_collector.ModbusRTUAdapter"), \
             patch("app.services.data_collector.MQTTAdapter"):
            mgr.register_device(1, "modbus_rtu", {"port": "/dev/tty0"})
            mgr.register_device(2, "mqtt", {"broker": "localhost"})
            assert len(mgr.adapters) == 2


class TestCollectAll:
    """collect_all"""

    def test_collect_success(self):
        mgr = DataCollectionManager()
        mock_adapter = AsyncMock()
        mock_adapter.read_data.return_value = {"voltage": 220}
        mgr.adapters = {"1": mock_adapter}
        mgr.device_config = {1: {"device_address": 1}}

        results = asyncio.run(mgr.collect_all())
        assert results[1]["voltage"] == 220

    def test_collect_error_continues(self):
        """单个设备出错不影响其他设备"""
        mgr = DataCollectionManager()
        bad_adapter = AsyncMock()
        bad_adapter.read_data.side_effect = Exception("timeout")
        good_adapter = AsyncMock()
        good_adapter.read_data.return_value = {"temp": 30}

        mgr.adapters = {"1": bad_adapter, "2": good_adapter}
        mgr.device_config = {1: {"device_address": 1}, 2: {"device_address": 1}}

        results = asyncio.run(mgr.collect_all())
        assert results[1].get("error")  # cc2272b84: 底层异常脱敏
        assert results[2]["temp"] == 30

    def test_collect_empty_devices(self):
        """无设备时返回空字典"""
        mgr = DataCollectionManager()
        results = asyncio.run(mgr.collect_all())
        assert results == {}

    def test_collect_uses_device_address_from_config(self):
        """采集时使用 device_config 中的 device_address"""
        mgr = DataCollectionManager()
        mock_adapter = AsyncMock()
        mock_adapter.read_data.return_value = {"ok": True}
        mgr.adapters = {"1": mock_adapter}
        mgr.device_config = {1: {"device_address": 7}}

        asyncio.run(mgr.collect_all())
        mock_adapter.read_data.assert_called_once_with(7)

    def test_collect_default_device_address(self):
        """config 中无 device_address 时默认 1"""
        mgr = DataCollectionManager()
        mock_adapter = AsyncMock()
        mock_adapter.read_data.return_value = {"ok": True}
        mgr.adapters = {"1": mock_adapter}
        mgr.device_config = {1: {}}  # 无 device_address

        asyncio.run(mgr.collect_all())
        mock_adapter.read_data.assert_called_once_with(1)


class TestCollectDevice:
    """collect_device"""

    def test_single_device_success(self):
        mgr = DataCollectionManager()
        mock_adapter = AsyncMock()
        mock_adapter.read_data.return_value = {"power": 100}
        mgr.adapters = {"1": mock_adapter}
        mgr.device_config = {1: {"device_address": 1}}

        result = asyncio.run(mgr.collect_device(1))
        assert result["power"] == 100

    def test_unregistered_device(self):
        """未注册设备返回 error"""
        mgr = DataCollectionManager()
        result = asyncio.run(mgr.collect_device(999))
        assert result["error"] == "设备未注册"

    def test_uses_correct_device_address(self):
        mgr = DataCollectionManager()
        mock_adapter = AsyncMock()
        mock_adapter.read_data.return_value = {"ok": True}
        mgr.adapters = {"5": mock_adapter}
        mgr.device_config = {5: {"device_address": 3}}

        asyncio.run(mgr.collect_device(5))
        mock_adapter.read_data.assert_called_once_with(3)
