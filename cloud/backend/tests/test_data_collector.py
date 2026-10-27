"""test_data_collector.py — DataCollectionManager 单元测试

被测对象: app/services/data_collector.py 的 DataCollectionManager(向后兼容代理层)。

纯逻辑测试: 协议适配器(ModbusRTUAdapter/MQTTAdapter/RESTAdapter)与 read_data 全部用
MagicMock/AsyncMock 替换, 不连接任何真实硬件或网络。

覆盖维度:
- register_device: modbus/mqtt/rest 协议分发、未知协议拒绝、device_address 提取与默认值、
  config.pop 对调用方字典的副作用、device_address 不外泄给适配器初始化。
- collect_all: 全量采集成功、单设备异常隔离、空管理器、默认 device_address、多设备聚合、键类型(int)。
- collect_device: 未注册设备返回 error、正常采集、默认 device_address。
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.data_collector import DataCollectionManager


# ─── fixtures ───

@pytest.fixture
def manager():
    """每个用例一个全新 DataCollectionManager(空 adapters/device_config)。"""
    return DataCollectionManager()


def _wire(manager, device_id, device_address=None, adapter=None, protocol="modbus_rtu"):
    """直接注入一个 mock adapter + config, 绕过 register_device 的真实适配器实例化。"""
    adapter = adapter or MagicMock()
    cfg = {"protocol": protocol, "config": {}}
    if device_address is not None:
        cfg["device_address"] = device_address
    manager.adapters[str(device_id)] = adapter
    manager.device_config[device_id] = cfg
    return adapter


# ═══════════════════════════════════════════════════════════════
# register_device
# ═══════════════════════════════════════════════════════════════

class TestRegisterDevice:
    def test_register_modbus_creates_adapter(self, manager):
        with patch("app.services.data_collector.ModbusRTUAdapter") as MockAdapter:
            instance = MagicMock()
            MockAdapter.return_value = instance
            manager.register_device(1, "modbus_rtu", {"port": "/dev/ttyUSB0", "baudrate": 9600})

            MockAdapter.assert_called_once_with(port="/dev/ttyUSB0", baudrate=9600)
            assert manager.adapters["1"] is instance
            assert manager.device_config[1]["protocol"] == "modbus_rtu"

    def test_register_mqtt_creates_adapter(self, manager):
        with patch("app.services.data_collector.MQTTAdapter") as MockAdapter:
            instance = MagicMock()
            MockAdapter.return_value = instance
            manager.register_device(2, "mqtt", {"broker": "mqtt.example.com", "port": 1883})

            MockAdapter.assert_called_once_with(broker="mqtt.example.com", port=1883)
            assert manager.adapters["2"] is instance

    def test_register_rest_creates_adapter(self, manager):
        with patch("app.services.data_collector.RESTAdapter") as MockAdapter:
            instance = MagicMock()
            MockAdapter.return_value = instance
            manager.register_device(3, "rest", {"url": "http://example.com/api"})

            MockAdapter.assert_called_once_with(url="http://example.com/api")
            assert manager.adapters["3"] is instance

    def test_register_unknown_protocol_no_adapter(self, manager):
        """未知协议: 不创建任何适配器, adapters 不收录该设备。"""
        with patch("app.services.data_collector.ModbusRTUAdapter"), \
             patch("app.services.data_collector.MQTTAdapter"), \
             patch("app.services.data_collector.RESTAdapter"):
            manager.register_device(99, "canbus", {"iface": "can0"})

            assert "99" not in manager.adapters

    def test_register_extracts_device_address(self, manager):
        """device_address 从 config 中提取, 不外泄给适配器初始化。"""
        with patch("app.services.data_collector.ModbusRTUAdapter") as MockAdapter:
            MockAdapter.return_value = MagicMock()
            manager.register_device(1, "modbus_rtu", {"port": "/dev/x", "device_address": 7})

            # 适配器初始化不应收到 device_address
            MockAdapter.assert_called_once_with(port="/dev/x")
            assert manager.device_config[1]["device_address"] == 7

    def test_register_default_device_address(self, manager):
        """config 未提供 device_address 时默认为 1。"""
        with patch("app.services.data_collector.ModbusRTUAdapter"):
            manager.register_device(1, "modbus_rtu", {"port": "/dev/x"})

            assert manager.device_config[1]["device_address"] == 1

    def test_register_pops_device_address_from_caller_dict(self, manager):
        """register_device 会 mutate 调用方传入的 config(pop device_address)。"""
        with patch("app.services.data_collector.ModbusRTUAdapter"):
            cfg = {"port": "/dev/x", "device_address": 5}
            manager.register_device(1, "modbus_rtu", cfg)

            assert "device_address" not in cfg  # 已被 pop
            assert cfg == {"port": "/dev/x"}


# ═══════════════════════════════════════════════════════════════
# collect_all
# ═══════════════════════════════════════════════════════════════

class TestCollectAll:
    @pytest.mark.asyncio
    async def test_collect_all_success(self, manager):
        adapter = _wire(manager, 1, device_address=3)
        adapter.read_data = AsyncMock(return_value={"voltage": 220})

        results = await manager.collect_all()

        adapter.read_data.assert_awaited_once_with(3)
        assert results == {1: {"voltage": 220}}

    @pytest.mark.asyncio
    async def test_collect_all_isolates_per_device_error(self, manager):
        adapter = _wire(manager, 1, device_address=1)
        adapter.read_data = AsyncMock(side_effect=ConnectionError("timeout"))

        results = await manager.collect_all()

        assert 1 in results and results[1].get("error")  # cc2272b84: 底层异常脱敏

    @pytest.mark.asyncio
    async def test_collect_all_empty_manager(self, manager):
        """无注册设备时返回空 dict。"""
        assert await manager.collect_all() == {}

    @pytest.mark.asyncio
    async def test_collect_all_uses_default_device_address(self, manager):
        """device_config 无 device_address 时回退默认 1。"""
        adapter = _wire(manager, 1)  # 不设 device_address
        adapter.read_data = AsyncMock(return_value={"ok": True})

        await manager.collect_all()

        adapter.read_data.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_collect_all_aggregates_multiple_devices(self, manager):
        a1 = _wire(manager, 1, device_address=1)
        a2 = _wire(manager, 2, device_address=2, protocol="mqtt")
        a1.read_data = AsyncMock(return_value={"a": 1})
        a2.read_data = AsyncMock(return_value={"b": 2})

        results = await manager.collect_all()

        assert results == {1: {"a": 1}, 2: {"b": 2}}

    @pytest.mark.asyncio
    async def test_collect_all_keys_are_int(self, manager):
        """结果键为 int(adapters 的 str key 转换回来)。"""
        adapter = _wire(manager, 5, device_address=1)
        adapter.read_data = AsyncMock(return_value={"v": 1})

        results = await manager.collect_all()

        assert list(results.keys()) == [5]
        assert isinstance(list(results.keys())[0], int)

    @pytest.mark.asyncio
    async def test_collect_all_partial_failure_keeps_successes(self, manager):
        """一个设备失败不影响其他设备采集。"""
        good = _wire(manager, 1, device_address=1)
        bad = _wire(manager, 2, device_address=2)
        good.read_data = AsyncMock(return_value={"ok": True})
        bad.read_data = AsyncMock(side_effect=RuntimeError("boom"))

        results = await manager.collect_all()

        assert results[1] == {"ok": True}
        assert results[2].get("error")  # cc2272b84: 底层异常脱敏


# ═══════════════════════════════════════════════════════════════
# collect_device
# ═══════════════════════════════════════════════════════════════

class TestCollectDevice:
    @pytest.mark.asyncio
    async def test_collect_device_unregistered_returns_error(self, manager):
        result = await manager.collect_device(999)

        assert result == {"error": "设备未注册"}

    @pytest.mark.asyncio
    async def test_collect_device_success(self, manager):
        adapter = _wire(manager, 1, device_address=7)
        adapter.read_data = AsyncMock(return_value={"power": 42})

        result = await manager.collect_device(1)

        adapter.read_data.assert_awaited_once_with(7)
        assert result == {"power": 42}

    @pytest.mark.asyncio
    async def test_collect_device_default_address(self, manager):
        adapter = _wire(manager, 1)  # 无 device_address
        adapter.read_data = AsyncMock(return_value={"v": 1})

        await manager.collect_device(1)

        adapter.read_data.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_collect_device_id_int_to_str_lookup(self, manager):
        """collect_device 接收 int device_id, 内部用 str(device_id) 查 adapters。"""
        adapter = _wire(manager, 10, device_address=1)
        adapter.read_data = AsyncMock(return_value={"v": 1})

        result = await manager.collect_device(10)

        assert result == {"v": 1}
