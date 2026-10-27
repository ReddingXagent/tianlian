"""
协议注册中心测试 - 测试 gateway 层核心功能

测试内容：
    - ProtocolAdapter 基类接口
    - ModbusRTUAdapter 协议适配器
    - MQTTAdapter 协议适配器
    - RESTAdapter 协议适配器
    - ProtocolRegistry 注册中心
"""
import pytest
from datetime import datetime

from app.gateway import (
    ProtocolAdapter,
    ModbusRTUAdapter,
    MQTTAdapter,
    RESTAdapter,
    ProtocolRegistry,
    get_registry,
    register_protocol,
    get_adapter,
)


# ========== ProtocolAdapter 基类测试 ==========

class MockAdapter(ProtocolAdapter):
    """测试用的模拟适配器"""
    protocol_type = "mock"
    
    def __init__(self, test_param: str = "default"):
        self.test_param = test_param
        self.connected = False
    
    async def connect(self) -> bool:
        self.connected = True
        return True
    
    async def disconnect(self) -> bool:
        self.connected = False
        return True
    
    async def read_data(self, device_address: int) -> dict:
        return {"test": "data", "address": device_address}
    
    async def write_command(self, device_address: int, command: dict) -> bool:
        return True
    
    def parse_fault_code(self, raw_data: bytes) -> str:
        return "0x00"


@pytest.mark.asyncio
async def test_mock_adapter_connect():
    """测试模拟适配器连接"""
    adapter = MockAdapter()
    assert not adapter.is_connected()
    
    result = await adapter.connect()
    assert result is True
    assert adapter.is_connected()


@pytest.mark.asyncio
async def test_mock_adapter_disconnect():
    """测试模拟适配器断开"""
    adapter = MockAdapter()
    await adapter.connect()
    
    result = await adapter.disconnect()
    assert result is True
    assert not adapter.is_connected()


@pytest.mark.asyncio
async def test_mock_adapter_read_data():
    """测试模拟适配器读取数据"""
    adapter = MockAdapter()
    await adapter.connect()
    
    data = await adapter.read_data(1)
    assert data["test"] == "data"
    assert data["address"] == 1


@pytest.mark.asyncio
async def test_mock_adapter_write_command():
    """测试模拟适配器写入指令"""
    adapter = MockAdapter()
    await adapter.connect()
    
    result = await adapter.write_command(1, {"test": "command"})
    assert result is True


@pytest.mark.asyncio
async def test_mock_adapter_health_check():
    """测试健康检查"""
    adapter = MockAdapter()
    adapter.connected = True
    
    health = await adapter.health_check()
    assert health["protocol"] == "mock"
    assert health["connected"] is True
    assert health["status"] == "healthy"


# ========== ModbusRTUAdapter 测试 ==========

def test_modbus_adapter_init():
    """测试 Modbus 适配器初始化"""
    adapter = ModbusRTUAdapter(
        port="/dev/ttyUSB0",
        baudrate=9600
    )
    
    assert adapter.port == "/dev/ttyUSB0"
    assert adapter.baudrate == 9600
    assert adapter.protocol_type == "modbus_rtu"


@pytest.mark.asyncio
async def test_modbus_adapter_connect():
    """测试 Modbus 适配器连接"""
    adapter = ModbusRTUAdapter(port="/dev/ttyUSB0")
    
    result = await adapter.connect()
    assert result is True
    assert adapter.is_connected()


@pytest.mark.asyncio
async def test_modbus_adapter_read_telemetry():
    """测试 Modbus 读取遥测数据"""
    adapter = ModbusRTUAdapter(port="/dev/ttyUSB0")
    await adapter.connect()
    
    # 测试读取（模拟返回）
    data = await adapter.read_telemetry(1)
    
    # 验证返回结构
    assert "timestamp" in data
    assert "device_address" in data
    assert data["device_address"] == 1


@pytest.mark.asyncio
async def test_modbus_adapter_write_control():
    """测试 Modbus 写入控制指令"""
    adapter = ModbusRTUAdapter(port="/dev/ttyUSB0")
    await adapter.connect()
    
    result = await adapter.write_control(1, 1024, 0x01)
    assert result is True


def test_modbus_adapter_parse_voltage():
    """测试电压解析"""
    adapter = ModbusRTUAdapter()
    
    # 原始值 2205 → 220.5V
    voltage = adapter._parse_voltage(2205)
    assert voltage == 220.5


def test_modbus_adapter_parse_current():
    """测试电流解析"""
    adapter = ModbusRTUAdapter()
    
    # 原始值 500 → 5.0A
    current = adapter._parse_current(500)
    assert current == 5.0


def test_modbus_adapter_parse_power():
    """测试功率解析"""
    adapter = ModbusRTUAdapter()
    
    # 原始值 1000 → 100.0kW
    power = adapter._parse_power(1000)
    assert power == 100.0


# ========== MQTTAdapter 测试 ==========

def test_mqtt_adapter_init():
    """测试 MQTT 适配器初始化"""
    adapter = MQTTAdapter(
        broker="mqtt.example.com",
        port=1883,
        client_id="gateway_001"
    )
    
    assert adapter.broker == "mqtt.example.com"
    assert adapter.port == 1883
    assert adapter.protocol_type == "mqtt"


@pytest.mark.asyncio
async def test_mqtt_adapter_connect():
    """测试 MQTT 适配器连接"""
    adapter = MQTTAdapter(broker="mqtt.example.com")
    
    result = await adapter.connect()
    assert result is True
    assert adapter.is_connected()


@pytest.mark.asyncio
async def test_mqtt_adapter_subscribe_device():
    """测试 MQTT 订阅设备"""
    adapter = MQTTAdapter(broker="mqtt.example.com")
    await adapter.connect()
    
    result = await adapter.subscribe_device("TCU001")
    assert result is True


@pytest.mark.asyncio
async def test_mqtt_adapter_read_telemetry():
    """测试 MQTT 读取遥测数据"""
    adapter = MQTTAdapter(broker="mqtt.example.com")
    await adapter.connect()
    
    data = await adapter.read_telemetry("TCU001")
    
    assert "tcu_address" in data
    assert data["tcu_address"] == "TCU001"


def test_mqtt_adapter_parse_fault_level():
    """测试 MQTT 故障等级解析"""
    adapter = MQTTAdapter()
    
    level = adapter._parse_fault_level(0x01)
    assert level == "emergency"
    
    level = adapter._parse_fault_level(0x02)
    assert level == "serious"


# ========== RESTAdapter 测试 ==========

def test_rest_adapter_init():
    """测试 REST 适配器初始化"""
    adapter = RESTAdapter(
        base_url="https://api.example.com",
        api_key="test_key"
    )
    
    assert adapter.base_url == "https://api.example.com"
    assert adapter.api_key == "test_key"
    assert adapter.protocol_type == "rest"


@pytest.mark.asyncio
async def test_rest_adapter_connect():
    """测试 REST 适配器连接"""
    adapter = RESTAdapter(base_url="https://api.example.com")
    
    result = await adapter.connect()
    assert result is True
    assert adapter.is_connected()


@pytest.mark.asyncio
async def test_rest_adapter_read_data():
    """测试 REST 读取数据"""
    adapter = RESTAdapter(base_url="https://api.example.com")
    await adapter.connect()
    
    data = await adapter.read_data(1)
    
    assert "device_id" in data
    assert data["device_id"] == 1


def test_rest_adapter_build_headers():
    """测试 REST 构建请求头"""
    adapter = RESTAdapter(base_url="https://api.example.com", api_key="test_key")
    
    headers = adapter._build_headers()
    
    assert "Content-Type" in headers
    assert headers["Content-Type"] == "application/json"
    assert "Authorization" in headers


# ========== ProtocolRegistry 测试 ==========

def test_registry_register_protocol():
    """测试注册协议"""
    registry = ProtocolRegistry()
    
    registry.register_protocol("mock", MockAdapter)
    
    protocols = registry.list_protocols()
    assert "mock" in protocols
    assert protocols["mock"] == "MockAdapter"


def test_registry_get_adapter():
    """测试获取适配器"""
    registry = ProtocolRegistry()
    registry.register_protocol("mock", MockAdapter)
    registry.register_device_type("test_device", "mock")
    
    adapter = registry.get_adapter("test_device", {"test_param": "custom"})
    
    assert adapter is not None
    assert adapter.test_param == "custom"
    assert adapter.protocol_type == "mock"


def test_registry_register_device_type():
    """测试注册设备类型"""
    registry = ProtocolRegistry()
    
    registry.register_device_type("new_device", "mock")
    
    device_types = registry.list_device_types()
    assert "new_device" in device_types
    assert device_types["new_device"] == "mock"


def test_registry_auto_discover():
    """测试自动扫描"""
    registry = ProtocolRegistry()
    
    registry.auto_discover()
    
    protocols = registry.list_protocols()
    
    # 应自动注册 modbus_rtu, mqtt, rest
    assert "modbus_rtu" in protocols
    assert "mqtt" in protocols
    assert "rest" in protocols


def test_get_registry():
    """测试全局注册中心"""
    registry = get_registry()
    
    assert registry is not None
    
    # 测试重复调用返回同一实例
    registry2 = get_registry()
    assert registry == registry2


def test_register_protocol_global():
    """测试全局注册协议"""
    register_protocol("test_protocol", MockAdapter)
    
    registry = get_registry()
    protocols = registry.list_protocols()
    
    assert "test_protocol" in protocols


def test_get_adapter_global():
    """测试全局获取适配器"""
    registry = get_registry()
    registry.register_device_type("test_device", "test_protocol")
    
    adapter = get_adapter("test_device", {})
    
    assert adapter is not None
    # 实际返回的是 MockAdapter，protocol_type 是 "mock"
    assert adapter.protocol_type == "mock"