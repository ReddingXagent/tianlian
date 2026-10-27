"""
向后兼容测试 - 测试旧的导入路径是否仍然可用

测试内容：
    - from app.services.data_collector import ProtocolAdapter
    - from app.services.data_collector import ModbusRTUAdapter
    - from app.services.data_collector import MQTTAdapter
    - from app.services.data_collector import DataCollectionManager
"""
import pytest


def test_backward_import_protocol_adapter():
    """测试向后兼容导入 ProtocolAdapter"""
    from app.services.data_collector import ProtocolAdapter
    
    assert ProtocolAdapter is not None
    assert hasattr(ProtocolAdapter, "connect")
    assert hasattr(ProtocolAdapter, "disconnect")
    assert hasattr(ProtocolAdapter, "read_data")


def test_backward_import_modbus_adapter():
    """测试向后兼容导入 ModbusRTUAdapter"""
    from app.services.data_collector import ModbusRTUAdapter
    
    assert ModbusRTUAdapter is not None
    assert ModbusRTUAdapter.protocol_type == "modbus_rtu"


def test_backward_import_mqtt_adapter():
    """测试向后兼容导入 MQTTAdapter"""
    from app.services.data_collector import MQTTAdapter
    
    assert MQTTAdapter is not None
    assert MQTTAdapter.protocol_type == "mqtt"


def test_backward_import_rest_adapter():
    """测试向后兼容导入 RESTAdapter"""
    from app.services.data_collector import RESTAdapter
    
    assert RESTAdapter is not None
    assert RESTAdapter.protocol_type == "rest"


def test_backward_import_data_collection_manager():
    """测试向后兼容导入 DataCollectionManager"""
    from app.services.data_collector import DataCollectionManager
    
    assert DataCollectionManager is not None
    assert hasattr(DataCollectionManager, "register_device")
    assert hasattr(DataCollectionManager, "collect_all")


def test_backward_import_device_schema():
    """测试向后兼容导入 DeviceSchema"""
    from app.services.data_collector import DeviceSchema
    
    assert DeviceSchema is not None


def test_backward_import_data_normalizer():
    """测试向后兼容导入 DataNormalizer"""
    from app.services.data_collector import DataNormalizer
    
    assert DataNormalizer is not None


def test_backward_import_parse_pipeline():
    """测试向后兼容导入 ParsePipeline"""
    from app.services.data_collector import ParsePipeline
    
    assert ParsePipeline is not None


@pytest.mark.asyncio
async def test_data_collection_manager_usage():
    """测试 DataCollectionManager 使用"""
    from app.services.data_collector import DataCollectionManager
    
    manager = DataCollectionManager()
    
    # 注册 Modbus 设备
    manager.register_device(
        device_id=1,
        protocol="modbus_rtu",
        config={"port": "/dev/ttyUSB0", "device_address": 1}
    )
    
    # 注册 MQTT 设备
    manager.register_device(
        device_id=2,
        protocol="mqtt",
        config={"broker": "mqtt.example.com", "port": 1883}
    )
    
    # 采集所有设备
    results = await manager.collect_all()
    
    assert 1 in results
    assert 2 in results


@pytest.mark.asyncio
async def test_data_collection_manager_single_device():
    """测试 DataCollectionManager 单设备采集"""
    from app.services.data_collector import DataCollectionManager
    
    manager = DataCollectionManager()
    
    manager.register_device(
        device_id=1,
        protocol="modbus_rtu",
        config={"port": "/dev/ttyUSB0", "device_address": 1}
    )
    
    data = await manager.collect_device(1)
    
    # 验证返回数据结构
    assert data is not None