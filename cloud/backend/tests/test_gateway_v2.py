"""
天链V3 设备适配器重构 v2 测试

测试内容：
    - DeviceAdapter 新生命周期 (initialize/shutdown/reset)
    - TelemetryPoint dataclass
    - ModbusRTUAdapter 寄存器映射 & 批量读取
    - MQTTAdapter TLS & 重连
    - OCPPAdapter
    - Registry 设备类型自动发现
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.gateway import (
    DeviceAdapter,
    ProtocolAdapter,
    ModbusRTUAdapter,
    MQTTAdapter,
    RESTAdapter,
    OCPPAdapter,
    ProtocolRegistry,
    get_registry,
    TelemetryPoint,
    PointType,
    RegisterMap,
)


# ========== TelemetryPoint 测试 ==========

class TestTelemetryPoint:
    def test_create_voltage_point(self):
        """测试创建电压遥测点"""
        point = TelemetryPoint(
            name="grid_voltage_a",
            address=0,
            point_type=PointType.VOLTAGE,
            scale=0.1,
            unit="V",
            description="A相电压",
        )
        assert point.name == "grid_voltage_a"
        assert point.address == 0
        assert point.point_type == PointType.VOLTAGE
        assert point.scale == 0.1
        assert point.unit == "V"
        assert point.description == "A相电压"

    def test_parse_voltage(self):
        """测试电压值解析"""
        point = TelemetryPoint("voltage", 0, scale=0.1)
        assert point.parse(2205) == 220.5

    def test_parse_current(self):
        """测试电流值解析"""
        point = TelemetryPoint("current", 0, scale=0.01)
        assert point.parse(500) == 5.0

    def test_parse_power(self):
        """测试功率值解析"""
        point = TelemetryPoint("power", 0, scale=0.1)
        assert point.parse(1000) == 100.0

    def test_parse_percentage(self):
        """测试百分比解析"""
        point = TelemetryPoint("soc", 0, scale=0.01)
        assert point.parse(8000) == 80.0

    def test_parse_signed_value(self):
        """测试有符号数解析"""
        point = TelemetryPoint("current", 0, scale=0.01, is_signed=True)
        # 0xFFFF = -1
        assert point.parse(0xFFFF) == -0.01

    def test_point_type_enum(self):
        """测试 PointType 枚举值"""
        assert PointType.VOLTAGE.value == "voltage"
        assert PointType.CURRENT.value == "current"
        assert PointType.POWER.value == "power"
        assert PointType.TEMPERATURE.value == "temperature"
        assert PointType.PERCENTAGE.value == "percentage"
        assert PointType.FREQUENCY.value == "frequency"
        assert PointType.STATUS.value == "status"


# ========== DeviceAdapter 生命周期测试 ==========

class TestDeviceAdapterLifecycle:
    """测试 DeviceAdapter 生命周期"""

    @pytest.mark.asyncio
    async def test_initialize(self):
        """测试初始化"""
        adapter = ModbusRTUAdapter()
        result = await adapter.initialize()
        assert result is True
        assert adapter.is_initialized()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """测试关闭"""
        adapter = ModbusRTUAdapter()
        await adapter.initialize()
        await adapter.connect()
        
        result = await adapter.shutdown()
        assert result is True
        assert not adapter.is_initialized()
        assert not adapter.is_connected()

    @pytest.mark.asyncio
    async def test_reset(self):
        """测试重置"""
        adapter = ModbusRTUAdapter()
        await adapter.initialize()
        await adapter.connect()
        
        result = await adapter.reset()
        assert result is True
        assert adapter.is_connected()

    @pytest.mark.asyncio
    async def test_device_adapter_health_check(self):
        """测试 DeviceAdapter 健康检查"""
        adapter = ModbusRTUAdapter()
        await adapter.initialize()
        await adapter.connect()
        
        health = await adapter.health_check()
        assert health["protocol"] == "modbus_rtu"
        assert health["connected"] is True
        assert health["initialized"] is True
        assert health["telemetry_points_count"] > 0

    def test_protocol_adapter_is_device_adapter(self):
        """测试 ProtocolAdapter 仍然是 DeviceAdapter"""
        assert ProtocolAdapter is DeviceAdapter
        assert issubclass(ProtocolAdapter, DeviceAdapter)


# ========== ModbusRTUAdapter 寄存器映射测试 ==========

class TestModbusRTUAdapterV2:
    """测试 ModbusRTUAdapter v2 新功能"""

    def test_default_register_maps(self):
        """测试默认寄存器映射"""
        adapter = ModbusRTUAdapter()
        assert len(adapter.register_maps) >= 4
        assert "grid" in adapter.register_maps
        assert "battery" in adapter.register_maps
        assert "pv" in adapter.register_maps
        assert "temperature" in adapter.register_maps

    def test_register_maps_synchronize_telemetry_points(self):
        """测试寄存器映射同步到遥测点"""
        adapter = ModbusRTUAdapter()
        assert len(adapter.telemetry_points) > 0
        assert "grid_voltage_a" in adapter.telemetry_points
        assert "battery_soc" in adapter.telemetry_points

    def test_custom_register_maps(self):
        """测试自定义寄存器映射"""
        custom_points = [
            TelemetryPoint("custom_value", 0, scale=1.0),
        ]
        custom_map = RegisterMap(points=custom_points, description="custom")
        adapter = ModbusRTUAdapter(register_maps=[custom_map])
        assert "custom" in adapter.register_maps
        assert adapter.register_maps["custom"].points[0].name == "custom_value"

    def test_set_register_maps(self):
        """测试动态设置寄存器映射"""
        adapter = ModbusRTUAdapter()
        custom_points = [
            TelemetryPoint("new_value", 500, scale=1.0),
        ]
        adapter.set_register_maps({
            "custom": RegisterMap(points=custom_points, description="new"),
        })
        assert "new_value" in adapter.telemetry_points

    def test_get_telemetry_point(self):
        """测试获取遥测点"""
        adapter = ModbusRTUAdapter()
        point = adapter.get_telemetry_point("grid_voltage_a")
        assert point is not None
        assert point.scale == 0.1

    def test_get_telemetry_point_not_found(self):
        """测试获取不存在的遥测点"""
        adapter = ModbusRTUAdapter()
        point = adapter.get_telemetry_point("nonexistent")
        assert point is None

    def test_parse_telemetry_value(self):
        """测试遥测值解析"""
        adapter = ModbusRTUAdapter()
        value = adapter.parse_telemetry_value("grid_voltage_a", 2205)
        assert value == 220.5

    def test_parse_telemetry_value_not_found(self):
        """测试不存在的遥测点解析"""
        adapter = ModbusRTUAdapter()
        value = adapter.parse_telemetry_value("nonexistent", 100)
        assert value is None

    def test_register_map_address_range(self):
        """测试寄存器映射地址范围计算"""
        points = [
            TelemetryPoint("v1", 0, scale=1.0),
            TelemetryPoint("v2", 10, scale=1.0),
        ]
        reg_map = RegisterMap(points=points, description="test")
        start, count = reg_map.get_address_range()
        assert start == 0
        assert count == 11  # 0-10 inclusive

    def test_register_map_contiguous_groups(self):
        """测试连续地址分组"""
        points = [
            TelemetryPoint("v1", 0, scale=1.0),
            TelemetryPoint("v2", 1, scale=1.0),
            TelemetryPoint("v3", 100, scale=1.0),  # 非连续
        ]
        reg_map = RegisterMap(points=points, description="test")
        groups = reg_map.get_contiguous_groups()
        assert len(groups) == 2
        assert len(groups[0]) == 2
        assert len(groups[1]) == 1

    @pytest.mark.asyncio
    async def test_read_telemetry_by_map(self):
        """测试按映射组读取遥测"""
        adapter = ModbusRTUAdapter()
        await adapter.connect()
        
        data = await adapter.read_telemetry_by_map(1, ["grid"])
        assert "grid_voltage_a" in data
        assert "grid_frequency" in data


# ========== MQTTAdapter TLS & 重连测试 ==========

class TestMQTTAdapterV2:
    """测试 MQTTAdapter v2 新功能"""

    def test_default_no_tls(self):
        """测试默认无 TLS"""
        adapter = MQTTAdapter()
        assert not adapter.tls_enabled

    def test_tls_enabled(self):
        """测试 TLS 启用"""
        adapter = MQTTAdapter(tls_enabled=True)
        assert adapter.tls_enabled

    def test_tls_port_auto(self):
        """测试 TLS 自动端口切换"""
        adapter = MQTTAdapter(tls_enabled=True)
        assert adapter.port == 8883  # 默认 1883 → 8883

    def test_tls_port_explicit(self):
        """测试显式 TLS 端口"""
        adapter = MQTTAdapter(tls_enabled=True, port=8883)
        assert adapter.port == 8883

    def test_tls_info(self):
        """测试获取 TLS 信息"""
        adapter = MQTTAdapter(tls_enabled=True)
        info = adapter.get_tls_info()
        assert info["enabled"] is True
        assert info["broker"] == "mqtt.example.com"

    def test_reconnect_default_config(self):
        """测试默认重连配置"""
        adapter = MQTTAdapter()
        assert adapter.reconnect_enabled
        assert adapter.reconnect_max_attempts == 10

    def test_reconnect_disabled(self):
        """测试禁用重连"""
        adapter = MQTTAdapter(reconnect_enabled=False)
        assert not adapter.reconnect_enabled

    def test_reconnect_status(self):
        """测试重连状态查询"""
        adapter = MQTTAdapter()
        status = adapter.get_reconnect_status()
        assert status["enabled"] is True
        assert status["reconnecting"] is False

    @pytest.mark.asyncio
    async def test_custom_callbacks(self):
        """测试自定义回调"""
        on_connect = AsyncMock()
        on_disconnect = AsyncMock()
        
        adapter = MQTTAdapter(
            on_connect_callback=on_connect,
            on_disconnect_callback=on_disconnect,
        )
        
        await adapter.connect()
        on_connect.assert_awaited_once()
        
        await adapter.disconnect()
        on_disconnect.assert_awaited_once()


# ========== OCPPAdapter 测试 ==========

class TestOCPPAdapter:
    """测试 OCPPAdapter"""

    def test_protocol_type(self):
        """测试协议类型"""
        adapter = OCPPAdapter()
        assert adapter.protocol_type == "ocpp"

    def test_init_defaults(self):
        """测试默认初始化"""
        adapter = OCPPAdapter()
        assert adapter.charge_point_id == "CP001"
        assert "wss://" in adapter.endpoint

    def test_custom_config(self):
        """测试自定义配置"""
        adapter = OCPPAdapter(
            charge_point_id="CP999",
            heartbeat_interval=120,
        )
        assert adapter.charge_point_id == "CP999"
        assert adapter.heartbeat_interval == 120

    def test_not_registered_at_start(self):
        """测试初始未注册"""
        adapter = OCPPAdapter()
        assert not adapter.is_registered()

    def test_no_transaction_at_start(self):
        """测试初始无交易"""
        adapter = OCPPAdapter()
        assert adapter.get_transaction_id() is None

    @pytest.mark.asyncio
    async def test_initialize(self):
        """测试初始化"""
        adapter = OCPPAdapter()
        result = await adapter.initialize()
        assert result is True
        assert adapter.is_initialized()

    @pytest.mark.asyncio
    async def test_connect_registers(self):
        """测试连接自动注册"""
        adapter = OCPPAdapter()
        await adapter.connect()
        assert adapter.is_registered()
        assert adapter.is_connected()

    @pytest.mark.asyncio
    async def test_send_boot_notification(self):
        """测试 BootNotification"""
        adapter = OCPPAdapter()
        result = await adapter.send_boot_notification(
            charge_point_model="DC-120kW",
            charge_point_vendor="Tianlian",
        )
        assert result["status"] == "Accepted"

    @pytest.mark.asyncio
    async def test_send_heartbeat(self):
        """测试 Heartbeat"""
        adapter = OCPPAdapter()
        result = await adapter.send_heartbeat()
        assert "currentTime" in result

    @pytest.mark.asyncio
    async def test_send_authorize_accepted(self):
        """测试 Authorize（成功）"""
        adapter = OCPPAdapter()
        result = await adapter.send_authorize("RFID001")
        assert result["idTagInfo"]["status"] == "Accepted"

    @pytest.mark.asyncio
    async def test_start_transaction(self):
        """测试 StartTransaction"""
        adapter = OCPPAdapter()
        result = await adapter.start_transaction(1, "RFID001")
        assert result["transactionId"] == 10001
        assert adapter.get_transaction_id() == 10001

    @pytest.mark.asyncio
    async def test_stop_transaction(self):
        """测试 StopTransaction"""
        adapter = OCPPAdapter()
        await adapter.start_transaction(1, "RFID001")
        result = await adapter.stop_transaction(10001, 50000)
        assert result["idTagInfo"]["status"] == "Accepted"
        assert adapter.get_transaction_id() is None

    @pytest.mark.asyncio
    async def test_send_meter_values(self):
        """测试 MeterValues"""
        adapter = OCPPAdapter()
        result = await adapter.send_meter_values(1, 10001, [
            {"value": "50000", "measurand": "Energy.Active.Import.Register"},
            {"value": "220.0", "measurand": "Voltage"},
        ])
        assert result == {}

    @pytest.mark.asyncio
    async def test_send_status_notification(self):
        """测试 StatusNotification"""
        adapter = OCPPAdapter()
        result = await adapter.send_status_notification(1, "Charging")
        assert result == {}

    @pytest.mark.asyncio
    async def test_remote_start_transaction(self):
        """测试远程启动充电"""
        adapter = OCPPAdapter()
        result = await adapter.remote_start_transaction("RFID001", 1)
        assert result is True

    @pytest.mark.asyncio
    async def test_remote_stop_transaction(self):
        """测试远程停止充电"""
        adapter = OCPPAdapter()
        result = await adapter.remote_stop_transaction(10001)
        assert result is True

    @pytest.mark.asyncio
    async def test_reset(self):
        """测试远程重启"""
        adapter = OCPPAdapter()
        result = await adapter.reset("Soft")
        assert result is True

    @pytest.mark.asyncio
    async def test_read_data(self):
        """测试读取充电桩数据"""
        adapter = OCPPAdapter()
        await adapter.connect()
        data = await adapter.read_data(1)
        assert "connector_id" in data
        assert "status" in data

    @pytest.mark.asyncio
    async def test_write_command_remote_start(self):
        """测试写入远程启动指令"""
        adapter = OCPPAdapter()
        await adapter.connect()
        result = await adapter.write_command(1, {
            "action": "remote_start",
            "id_tag": "RFID001",
        })
        assert result is True

    @pytest.mark.asyncio
    async def test_write_command_unknown_action(self):
        """测试未知的控制指令"""
        adapter = OCPPAdapter()
        result = await adapter.write_command(1, {"action": "unknown"})
        assert result is False

    @pytest.mark.asyncio
    async def test_write_command_reset(self):
        """测试写入重启指令"""
        adapter = OCPPAdapter()
        await adapter.connect()
        result = await adapter.write_command(1, {
            "action": "reset",
            "reset_type": "Hard",
        })
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        adapter = OCPPAdapter()
        await adapter.connect()
        health = await adapter.health_check()
        assert health["protocol"] == "ocpp"
        assert health["registered"] is True

    def test_get_ocpp_info(self):
        """测试获取 OCPP 信息"""
        adapter = OCPPAdapter(charge_point_id="CP001")
        info = adapter.get_ocpp_info()
        assert info["charge_point_id"] == "CP001"
        assert info["version"] == "1.6-J"

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """测试关闭"""
        adapter = OCPPAdapter()
        await adapter.initialize()
        await adapter.connect()
        result = await adapter.shutdown()
        assert result is True
        assert not adapter.is_initialized()
        assert not adapter.is_connected()

    @pytest.mark.asyncio
    async def test_disconnect_stops_heartbeat(self):
        """测试断开连接停止心跳"""
        adapter = OCPPAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert not adapter.is_connected()
        assert not adapter.is_registered()


# ========== Registry v2 测试 ==========

class TestRegistryV2:
    """测试 Registry v2 新功能"""

    def test_register_device_types_bulk(self):
        """测试批量注册设备类型"""
        registry = ProtocolRegistry()
        registry.register_device_types_bulk({
            "new_device_1": "modbus_rtu",
            "new_device_2": "mqtt",
        })
        types = registry.list_device_types()
        assert "new_device_1" in types
        assert "new_device_2" in types

    def test_get_protocol_for_device_type(self):
        """测试获取设备类型对应的协议"""
        registry = ProtocolRegistry()
        registry.register_device_type("custom_device", "modbus_rtu")
        protocol = registry.get_protocol_for_device_type("custom_device")
        assert protocol == "modbus_rtu"

    def test_get_protocol_not_found(self):
        """测试获取不存在的设备类型"""
        registry = ProtocolRegistry()
        protocol = registry.get_protocol_for_device_type("nonexistent")
        assert protocol is None

    def test_has_adapter(self):
        """测试检查协议是否已注册"""
        registry = ProtocolRegistry()
        registry.register_protocol("modbus_rtu", ModbusRTUAdapter)
        assert registry.has_adapter("modbus_rtu")
        assert not registry.has_adapter("nonexistent")

    def test_auto_discover_finds_ocpp(self):
        """测试自动扫描发现 OCPP 适配器"""
        registry = ProtocolRegistry()
        registry.auto_discover()
        protocols = registry.list_protocols()
        assert "ocpp" in protocols
        assert protocols["ocpp"] == "OCPPAdapter"


# ========== 向后兼容测试 ==========

def test_import_telemetry_point():
    """测试 TelemetryPoint 可导入"""
    from app.gateway import TelemetryPoint
    assert TelemetryPoint is not None

def test_import_point_type():
    """测试 PointType 可导入"""
    from app.gateway import PointType
    assert PointType is not None

def test_device_adapter_is_base():
    """测试 DeviceAdapter 是基类"""
    assert issubclass(ModbusRTUAdapter, DeviceAdapter)
    assert issubclass(MQTTAdapter, DeviceAdapter)
    assert issubclass(OCPPAdapter, DeviceAdapter)
    assert issubclass(RESTAdapter, DeviceAdapter)

def test_old_import_still_works():
    """测试旧的 ProtocolAdapter 导入仍有效"""
    from app.gateway.base import ProtocolAdapter
    assert ProtocolAdapter is DeviceAdapter
