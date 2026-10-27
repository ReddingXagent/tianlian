"""
网关数据采集适配器 - 向后兼容代理层

⚠️ 本文件已重构为三层架构：
    - 协议层：app.gateway/
    - 解析层：app.parsers/
    - 服务层：app.services/device_data_service.py, device_control_service.py

此文件仅作为向后兼容代理，所有类均从新架构导入。

迁移指南：
    - ProtocolAdapter → from app.gateway import ProtocolAdapter
    - ModbusRTUAdapter → from app.gateway import ModbusRTUAdapter
    - MQTTAdapter → from app.gateway import MQTTAdapter
    - DataCollectionManager → 使用 DeviceDataService
"""

# ========== 向后兼容导入 ==========

from app.gateway import (
    ProtocolAdapter,
    ModbusRTUAdapter,
    MQTTAdapter,
    RESTAdapter,
)

from app.parsers import (
    DeviceSchema,
    DataNormalizer,
    ParsePipeline,
)

from app.services.device_data_service import DeviceDataService
from app.services.device_control_service import DeviceControlService

import logging

logger = logging.getLogger(__name__)


# ========== DataCollectionManager（向后兼容） ==========

class DataCollectionManager:
    """
    数据采集管理器（向后兼容代理）
    
    ⚠️ 建议迁移到 DeviceDataService
    
    管理多个设备的协议适配器，统一采集调度。
    """
    
    def __init__(self):
        self.adapters: dict = {}
        self.device_config: dict = {}  # 设备ID -> 配置
        
    def register_device(self, device_id: int, protocol: str, config: dict):
        """
        注册设备
        
        Args:
            device_id: 设备ID
            protocol: 协议类型（modbus_rtu / mqtt）
            config: 协议参数
        """
        # 提取 device_address（不传递给适配器初始化）
        device_address = config.pop("device_address", 1)
        
        self.device_config[device_id] = {
            "protocol": protocol,
            "config": config,
            "device_address": device_address,
        }
        
        # 创建适配器实例
        if protocol == "modbus_rtu":
            adapter = ModbusRTUAdapter(**config)
        elif protocol == "mqtt":
            adapter = MQTTAdapter(**config)
        elif protocol == "rest":
            adapter = RESTAdapter(**config)
        else:
            logger.error("未知协议: %s", protocol)
            return
        
        self.adapters[str(device_id)] = adapter
        logger.info("注册设备: ID=%s, 协议=%s", device_id, protocol)
    
    async def collect_all(self) -> dict:
        """
        采集所有设备数据
        
        Returns:
            dict: 设备ID -> 遥测数据
        """
        results = {}
        
        for device_id, adapter in self.adapters.items():
            try:
                config = self.device_config[int(device_id)]
                device_address = config.get("device_address", 1)
                
                data = await adapter.read_data(device_address)
                results[int(device_id)] = data
                
                logger.debug("采集成功: 设备%s", device_id)
            except Exception as e:
                logger.error("采集失败: 设备%s, 错误: %s", device_id, e)
                results[int(device_id)] = {"error": "服务内部错误，请稍后重试"}
        
        return results
    
    async def collect_device(self, device_id: int) -> dict:
        """采集单个设备"""
        adapter = self.adapters.get(str(device_id))
        if not adapter:
            return {"error": "设备未注册"}
        
        config = self.device_config[device_id]
        device_address = config.get("device_address", 1)
        
        return await adapter.read_data(device_address)


# ========== 导出所有类（向后兼容） ==========

__all__ = [
    # 协议适配器
    "ProtocolAdapter",
    "ModbusRTUAdapter",
    "MQTTAdapter",
    "RESTAdapter",
    
    # 解析器
    "DeviceSchema",
    "DataNormalizer",
    "ParsePipeline",
    
    # 服务层
    "DeviceDataService",
    "DeviceControlService",
    
    # 向后兼容管理器
    "DataCollectionManager",
]


# ========== 使用示例（向后兼容） ==========

async def example_collection():
    """采集示例"""
    manager = DataCollectionManager()
    
    # 注册逆变器（Modbus-RTU）
    manager.register_device(
        device_id=1,
        protocol="modbus_rtu",
        config={
            "port": "/dev/ttyUSB0",
            "baudrate": 9600,
            "device_address": 1,
        }
    )
    
    # 注册充电桩（MQTT）
    manager.register_device(
        device_id=2,
        protocol="mqtt",
        config={
            "broker": "mqtt.example.com",
            "port": 1883,
        }
    )
    
    # 采集所有设备
    data = await manager.collect_all()
    logging.getLogger(__name__).info('采集结果: %s', data)