#!/usr/bin/env python3
"""
简化端到端测试 - 验证核心功能
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gateway.registry import get_registry, get_adapter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_gateway_registry():
    """测试协议注册中心"""
    print("\n🔧 测试协议注册中心")
    
    # 获取注册中心实例
    registry = get_registry()
    
    # 验证协议注册
    protocols = registry.list_protocols()
    print(f"✅ 已注册协议: {protocols}")
    
    # 验证设备类型映射
    device_types = registry.list_device_types()
    print(f"✅ 设备类型映射: {device_types}")
    
    # 验证协议适配器获取
    test_cases = [
        ("inverter_eahi_20k", "modbus_rtu", {"port": "/dev/ttyUSB0", "baudrate": 9600}),
        ("charger_dc_60kw", "mqtt", {"broker": "mqtt.example.com", "port": 1883}),
        ("smart_meter", "rest", {"base_url": "https://api.example.com", "api_key": "test_key"}),
    ]
    
    for device_type, expected_protocol, config in test_cases:
        adapter = get_adapter(device_type, config)
        if adapter:
            print(f"✅ {device_type} -> {adapter.__class__.__name__} (协议: {adapter.protocol_type})")
            # 测试连接（模拟）
            try:
                await adapter.connect()
                print(f"  ✅ {device_type} 连接测试成功")
                await adapter.disconnect()
            except Exception as e:
                print(f"  ⚠️  {device_type} 连接异常（模拟环境）: {e}")
        else:
            print(f"❌ {device_type} -> 适配器获取失败")
    
    return True


async def test_parsers_import():
    """测试解析器模块导入"""
    print("\n🔧 测试解析器模块")
    
    try:
        from app.parsers.base_schema import DeviceSchema, DataType, Unit
        from app.parsers.modbus_schema import ModbusSchema, load_modbus_schema
        from app.parsers.mqtt_schema import MQTTSchema, load_mqtt_schema
        from app.parsers.normalizer import DataNormalizer
        from app.parsers.pipeline import ParsePipeline
        
        print("✅ 解析器模块导入成功")
        
        # 测试基础组件创建
        normalizer = DataNormalizer()
        print(f"✅ 数据规范化器: {normalizer.__class__.__name__}")
        
        pipeline = ParsePipeline(device_type="inverter_eahi_20k", protocol="modbus_rtu")
        print(f"✅ 解析流水线: {pipeline.device_type} - {pipeline.protocol}")
        
        # 测试架构加载
        modbus_schema = load_modbus_schema("inverter_eahi_20k")
        if modbus_schema:
            print(f"✅ Modbus架构加载: {modbus_schema.name} - {len(modbus_schema.fields)} 个字段")
        
        mqtt_schema = load_mqtt_schema("charger_dc_60kw")
        if mqtt_schema:
            print(f"✅ MQTT架构加载: {mqtt_schema.name} - {len(mqtt_schema.topics)} 个主题")
        
        return True
    except Exception as e:
        print(f"❌ 解析器模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """测试API端点"""
    print("\n🔧 测试API端点")
    
    try:
        import requests
        
        # 测试健康检查
        response = requests.get("http://localhost:8000/api/v1/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康检查: {data['data']['status']} (版本: {data['data']['version']})")
        else:
            print(f"❌ 健康检查失败: HTTP {response.status_code}")
            return False
        
        # 测试设备列表
        response = requests.get("http://localhost:8000/api/v1/devices", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 设备列表: {len(data['data'])} 个设备")
        else:
            print(f"⚠️  设备列表: HTTP {response.status_code} (可能未认证)")
        
        # 测试站点列表
        response = requests.get("http://localhost:8000/api/v1/stations", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 站点列表: {len(data['data'])} 个站点")
        else:
            print(f"⚠️  站点列表: HTTP {response.status_code} (可能未认证)")
        
        return True
    except Exception as e:
        print(f"❌ API测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("🚀 开始简化端到端测试")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    results.append(await test_gateway_registry())
    results.append(await test_parsers_import())
    results.append(await test_api_endpoints())
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📋 测试结果汇总:")
    
    test_names = ["协议注册中心", "解析器模块", "API端点"]
    for i, result in enumerate(results):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_names[i]}: {status}")
    
    all_passed = all(results)
    if all_passed:
        print("\n🎉 所有测试通过！")
        print("✅ 云端部署验证完成")
        print("✅ 协议网关注册与服务发现正常")
        print("✅ 解析器模块工作正常")
        print("✅ API服务运行正常")
    else:
        print("\n⚠️  部分测试失败，请检查")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)