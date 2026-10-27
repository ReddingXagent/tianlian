"""
协议注册中心 - Gateway 包入口

自动扫描注册所有协议适配器，提供统一的导入接口。
"""
from .base import ProtocolAdapter, DeviceAdapter, TelemetryPoint, PointType
from .modbus import ModbusRTUAdapter, RegisterMap
from .mqtt import MQTTAdapter
from .rest import RESTAdapter
from .ocpp import OCPPAdapter
from .dlt645 import DLT645Adapter
from .iec104 import IEC104Client
from .registry import (
    ProtocolRegistry,
    get_registry,
    register_protocol,
    get_adapter,
)
from .template_loader import (
    DeviceTemplate,
    TemplateLoader,
    get_template_loader,
    reset_template_loader,
)
from .edge_cache import (
    EdgeCache,
    get_edge_cache,
    reset_edge_caches,
)


__all__ = [
    # 基类
    "ProtocolAdapter",
    "DeviceAdapter",
    
    # 遥测点
    "TelemetryPoint",
    "PointType",
    
    # 协议适配器
    "ModbusRTUAdapter",
    "MQTTAdapter",
    "RESTAdapter",
    "OCPPAdapter",
    "DLT645Adapter",
    "IEC104Client",
    
    # Modbus 映射
    "RegisterMap",
    
    # 注册中心
    "ProtocolRegistry",
    "get_registry",
    "register_protocol",
    "get_adapter",

    # 模板加载器
    "DeviceTemplate",
    "TemplateLoader",
    "get_template_loader",
    "reset_template_loader",

    # 边缘缓存
    "EdgeCache",
    "get_edge_cache",
    "reset_edge_caches",
]


# ========== 自动注册内置协议 ==========

def _auto_register():
    """自动注册内置协议适配器"""
    registry = get_registry()
    
    # 注册内置协议（如果尚未注册）
    if "modbus_rtu" not in registry.list_protocols():
        registry.register_protocol("modbus_rtu", ModbusRTUAdapter)
    
    if "mqtt" not in registry.list_protocols():
        registry.register_protocol("mqtt", MQTTAdapter)
    
    if "rest" not in registry.list_protocols():
        registry.register_protocol("rest", RESTAdapter)
    
    if "ocpp" not in registry.list_protocols():
        registry.register_protocol("ocpp", OCPPAdapter)

    if "dlt645" not in registry.list_protocols():
        registry.register_protocol("dlt645", DLT645Adapter)

    if "iec104" not in registry.list_protocols():
        registry.register_protocol("iec104", IEC104Client)


# 包导入时自动注册
_auto_register()