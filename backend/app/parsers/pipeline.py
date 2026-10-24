"""
解析流水线编排 - 编排多个解析器，形成完整的解析流程

支持灵活的解析流程配置，可以串联多个解析步骤。
"""
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime, timezone
import logging

from .base_schema import DeviceSchema
from .normalizer import DataNormalizer
from .modbus_schema import load_modbus_schema
from .mqtt_schema import load_mqtt_schema

logger = logging.getLogger(__name__)


class ParsePipeline:
    """
    解析流水线
    
    编排多个解析步骤，形成完整的解析流程。
    
    Example:
        >>> pipeline = ParsePipeline()
        >>> pipeline.add_step("load_schema", load_schema_step)
        >>> pipeline.add_step("normalize", normalize_step)
        >>> result = await pipeline.execute(raw_data)
    """
    
    def __init__(self, device_type: str = "unknown", protocol: str = "unknown"):
        """
        初始化解析流水线
        
        Args:
            device_type: 设备类型标识
            protocol: 协议类型
        """
        self.device_type = device_type
        self.protocol = protocol
        self.steps: List[Callable] = []
        self.schema: Optional[DeviceSchema] = None
        self.normalizer: Optional[DataNormalizer] = None
    
    def add_step(self, name: str, step_func: Callable) -> None:
        """
        添加解析步骤
        
        Args:
            name: 步骤名称
            step_func: 步骤函数
            
        Example:
            >>> def custom_step(data):
            ...     data["custom_field"] = 100
            ...     return data
            >>> pipeline.add_step("custom", custom_step)
        """
        self.steps.append(step_func)
        logger.debug("添加解析步骤: %s", name)
    
    async def execute(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行解析流水线
        
        Args:
            raw_data: 原始数据
            
        Returns:
            Dict[str, Any]: 解析后的数据
            
        Note:
            按顺序执行所有步骤，每个步骤可以修改数据
        """
        data = raw_data.copy()
        
        for step in self.steps:
            try:
                # 支持同步和异步步骤
                if hasattr(step, "__call__"):
                    # 检查是否为协程函数
                    if hasattr(step, "__code__") and step.__code__.co_flags & 0x80:
                        # 异步函数
                        data = await step(data)
                    else:
                        # 同步函数
                        data = step(data)
                else:
                    logger.warning("无效的步骤函数: %s", step)
            except Exception as e:
                logger.error("解析步骤执行失败: %s", e)
                # 继续执行后续步骤
        
        return data
    
    def load_schema(self) -> None:
        """
        加载设备 Schema
        
        Note:
            根据 protocol 类型加载对应的 Schema
        """
        if self.protocol == "modbus":
            self.schema = load_modbus_schema(self.device_type)
        elif self.protocol == "mqtt":
            self.schema = load_mqtt_schema(self.device_type)
        else:
            logger.warning("未知的协议类型: %s", self.protocol)
            self.schema = DeviceSchema(self.device_type, self.protocol)
        
        # 初始化标准化器
        self.normalizer = DataNormalizer(self.schema)
    
    def build_default_pipeline(self) -> None:
        """
        构建默认解析流水线
        
        默认步骤：
            1. 加载 Schema
            2. 字段解析
            3. 数据标准化
            4. 添加元信息
        """
        # 1. 加载 Schema
        self.load_schema()
        
        # 2. 字段解析（应用 Schema 缩放）
        def parse_fields_step(data: Dict[str, Any]) -> Dict[str, Any]:
            parsed = {}
            for field_name, raw_value in data.items():
                if field_name in ["timestamp", "device_address"]:
                    parsed[field_name] = raw_value
                elif self.schema:
                    parsed[field_name] = self.schema.parse_value(field_name, raw_value)
                else:
                    parsed[field_name] = raw_value
            return parsed
        
        self.add_step("parse_fields", parse_fields_step)
        
        # 3. 数据标准化
        def normalize_step(data: Dict[str, Any]) -> Dict[str, Any]:
            if self.normalizer:
                return self.normalizer.normalize(data)
            return data
        
        self.add_step("normalize", normalize_step)
        
        # 4. 添加元信息
        def add_metadata_step(data: Dict[str, Any]) -> Dict[str, Any]:
            data["device_type"] = self.device_type
            data["protocol"] = self.protocol
            if "timestamp" not in data:
                data["timestamp"] = datetime.now(timezone.utc)
            return data
        
        self.add_step("add_metadata", add_metadata_step)


def create_pipeline(device_type: str, protocol: str) -> ParsePipeline:
    """
    创建解析流水线
    
    Args:
        device_type: 设备类型标识
        protocol: 协议类型
        
    Returns:
        ParsePipeline: 解析流水线实例
        
    Example:
        >>> pipeline = create_pipeline("inverter_eahi_20k", "modbus")
        >>> result = await pipeline.execute(raw_data)
    """
    pipeline = ParsePipeline(device_type, protocol)
    pipeline.build_default_pipeline()
    
    logger.info("创建解析流水线: %s (%s)", device_type, protocol)
    return pipeline