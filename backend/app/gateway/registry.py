"""
协议注册中心 - 动态加载协议适配器，按设备类型自动路由

核心功能：
    - register_protocol(): 注册协议适配器类
    - get_adapter(): 根据设备配置获取适配器实例
    - auto_discover(): 自动扫描注册所有适配器
    - device_type_mapping 从 YAML 模板动态加载（P6）
"""
from typing import Dict, Any, Type, Optional
import logging
import importlib
import pkgutil
import threading
from pathlib import Path

from .base import ProtocolAdapter, DeviceAdapter

logger = logging.getLogger(__name__)


class ProtocolRegistry:
    """
    协议注册中心
    
    管理所有协议适配器的注册、查询和实例化。
    设备类型 -> 协议类型映射可从 YAML 模板动态加载（P6）。
    
    Example:
        >>> registry = ProtocolRegistry()
        >>> registry.register_protocol("modbus_rtu", ModbusRTUAdapter)
        >>> adapter = registry.get_adapter("inverter_eahi_20k", {"port": "/dev/ttyUSB0"})
        >>> data = await adapter.read_data(1)
    """
    
    def __init__(self, template_dir: Optional[str] = None):
        """初始化注册中心

        Args:
            template_dir: YAML 模板目录路径（可选）
        """
        self._protocol_classes: Dict[str, Type[ProtocolAdapter]] = {}

        # P6: 从 YAML 模板动态加载（保留硬编码兜底）
        self._device_type_mapping: Dict[str, str] = self._load_mapping_from_templates(template_dir)
        self._mapping_loaded_from_templates = len(self._device_type_mapping) > 0

        if not self._mapping_loaded_from_templates:
            self._device_type_mapping = {
                "inverter_eahi_20k": "modbus_rtu",
                "pcs_100kw": "modbus_rtu",
                "meter_three_phase": "modbus_rtu",
                "charger_dc_60kw": "mqtt",
                "charger_dc_120kw": "ocpp",
                "charger_ac_7kw": "ocpp",
                "charger_ykc": "ykc",
                "bms_lithium": "modbus_rtu",
                "ev_charger_ocpp": "ocpp",
            }
            logger.warning("未能从模板加载设备映射，使用硬编码兜底")
        else:
            logger.info("从 YAML 模板加载设备映射: %d 个设备类型", len(self._device_type_mapping))

    def _load_mapping_from_templates(self, template_dir: Optional[str] = None) -> Dict[str, str]:
        from .template_loader import get_template_loader, reset_template_loader
        if template_dir:
            reset_template_loader()
        loader = get_template_loader(template_dir=template_dir)
        return loader.list_device_types()

    def reload_templates(self, template_dir: Optional[str] = None) -> int:
        from .template_loader import get_template_loader, reset_template_loader
        if template_dir:
            reset_template_loader()
        loader = get_template_loader(template_dir=template_dir)
        count = loader.reload_if_changed()
        if count > 0:
            self._device_type_mapping.update(loader.list_device_types())
            self._mapping_loaded_from_templates = True
            logger.info("热重载完成: %d 个模板已更新", count)
        return count
        
    def register_protocol(self, protocol_type: str, adapter_class: Type[ProtocolAdapter]) -> None:
        """
        注册协议适配器类
        
        Args:
            protocol_type: 协议类型标识（如 'modbus_rtu', 'mqtt'）
            adapter_class: 协议适配器类
            
        Example:
            >>> registry.register_protocol("modbus_rtu", ModbusRTUAdapter)
        """
        if not isinstance(adapter_class, type) or not issubclass(adapter_class, ProtocolAdapter):
            logger.error("无效的适配器类: %s", adapter_class)
            return
        
        self._protocol_classes[protocol_type] = adapter_class
        logger.info("注册协议: %s -> %s", protocol_type, adapter_class.__name__)
    
    def get_adapter(self, device_type: str, config: Dict[str, Any]) -> Optional[ProtocolAdapter]:
        """
        根据设备类型获取适配器实例
        
        Args:
            device_type: 设备类型标识（如 'inverter_eahi_20k'）
            config: 设备配置字典
            
        Returns:
            Optional[ProtocolAdapter]: 协议适配器实例
            
        Example:
            >>> adapter = registry.get_adapter("inverter_eahi_20k", {"port": "/dev/ttyUSB0"})
            >>> if adapter:
            ...     data = await adapter.read_data(1)
        """
        # 1. 查找设备类型对应的协议类型
        protocol_type = config.get("protocol") or self._device_type_mapping.get(device_type)
        
        if not protocol_type:
            logger.error("未找到设备类型 %s 的协议映射", device_type)
            return None
        
        # 2. 查找协议类
        adapter_class = self._protocol_classes.get(protocol_type)
        
        if not adapter_class:
            logger.error("未找到协议类型 %s 的适配器", protocol_type)
            return None
        
        # 3. 实例化适配器
        try:
            adapter = adapter_class(**config)
            logger.info("创建适配器: %s for %s", protocol_type, device_type)
            return adapter
        except Exception as e:
            logger.error("实例化适配器失败: %s", e)
            return None
    
    def register_device_type(self, device_type: str, protocol_type: str) -> None:
        """
        注册设备类型到协议类型的映射
        
        Args:
            device_type: 设备类型标识
            protocol_type: 协议类型标识
            
        Example:
            >>> registry.register_device_type("new_device", "mqtt")
        """
        self._device_type_mapping[device_type] = protocol_type
        logger.info("注册设备类型映射: %s -> %s", device_type, protocol_type)
    
    def list_protocols(self) -> Dict[str, str]:
        """
        列出所有已注册的协议
        
        Returns:
            Dict[str, str]: 协议类型 -> 适配器类名映射
        """
        return {
            protocol_type: adapter_class.__name__
            for protocol_type, adapter_class in self._protocol_classes.items()
        }
    
    def list_device_types(self) -> Dict[str, str]:
        """
        列出所有已注册的设备类型
        
        Returns:
            Dict[str, str]: 设备类型 -> 协议类型映射
        """
        return self._device_type_mapping.copy()
    
    @property
    def is_mapping_from_templates(self) -> bool:
        """映射是否从 YAML 模板加载"""
        return self._mapping_loaded_from_templates

    def auto_discover(self, package_path: Optional[str] = None) -> None:
        """
        自动扫描注册所有适配器
        
        Args:
            package_path: 扫描路径（默认为当前 gateway 包）
            
        Note:
            扫描 gateway 包下所有模块，查找 DeviceAdapter/ProtocolAdapter 子类
            自动注册设备类型映射（如果适配器类定义了 device_type 类属性）
        """
        if package_path is None:
            package_path = str(Path(__file__).parent)
        
        logger.info("自动扫描协议适配器: %s", package_path)
        
        # 扫描 gateway 包下的所有模块
        for importer, modname, ispkg in pkgutil.iter_modules([package_path]):
            if modname in ["__init__", "base", "registry", "template_loader"]:
                continue
            
            try:
                module = importlib.import_module(f".{modname}", package="app.gateway")
                
                # 查找模块中的 DeviceAdapter/ProtocolAdapter 子类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, DeviceAdapter)
                        and attr not in (DeviceAdapter, ProtocolAdapter)
                        and hasattr(attr, "protocol_type")
                    ):
                        protocol_type = attr.protocol_type
                        self.register_protocol(protocol_type, attr)
                        logger.debug("自动注册: %s from %s", protocol_type, modname)
                        
                        # 自动注册设备类型映射（如果定义了 device_type）
                        if hasattr(attr, "device_type") and attr.device_type:
                            self.register_device_type(attr.device_type, protocol_type)
                            logger.debug("自动映射设备类型: %s -> %s", attr.device_type, protocol_type)
                        
            except Exception as e:
                logger.warning("扫描模块 %s 失败: %s", modname, e)
        
        logger.info("自动扫描完成: 注册 %d 个协议", len(self._protocol_classes))
    
    # ===== v2 增强方法 =====
    
    def register_device_types_bulk(self, mappings: Dict[str, str]) -> None:
        """
        批量注册设备类型映射
        
        Args:
            mappings: 设备类型 -> 协议类型映射字典
        """
        self._device_type_mapping.update(mappings)
        logger.info("批量注册 %d 个设备类型映射", len(mappings))
    
    def get_protocol_for_device_type(self, device_type: str) -> Optional[str]:
        """
        获取设备类型对应的协议类型
        
        Args:
            device_type: 设备类型标识
            
        Returns:
            Optional[str]: 协议类型
        """
        return self._device_type_mapping.get(device_type)
    
    def has_adapter(self, protocol_type: str) -> bool:
        """
        检查协议类型是否已注册
        
        Args:
            protocol_type: 协议类型
            
        Returns:
            bool: 是否已注册
        """
        return protocol_type in self._protocol_classes


# ========== 全局注册中心实例 ==========

_global_registry: Optional[ProtocolRegistry] = None
# 缺陷4: 模块级单例的 check-then-act 在多线程下存在 TOCTOU 竞态（各自构造实例 +
# 重复 auto_discover 扫描），参照 app/services/ai_model_config.py 用双重检查锁(DCL)加固
_registry_lock = threading.Lock()


def get_registry(template_dir: Optional[str] = None) -> ProtocolRegistry:
    """
    获取全局注册中心实例

    Returns:
        ProtocolRegistry: 全局注册中心

    Note:
        首次调用时会自动初始化并扫描注册所有适配器
        双重检查锁保证并发首次调用只构造一个实例
    """
    global _global_registry

    if _global_registry is None:
        with _registry_lock:
            # 内层二次检查：拿到锁后可能已被其他线程完成构造
            if _global_registry is None:
                _global_registry = ProtocolRegistry(template_dir=template_dir)
                _global_registry.auto_discover()

    return _global_registry


def reset_registry() -> None:
    """重置全局注册中心（用于测试）"""
    global _global_registry
    with _registry_lock:
        _global_registry = None


def register_protocol(protocol_type: str, adapter_class: Type[ProtocolAdapter]) -> None:
    """
    注册协议适配器（全局注册中心）
    
    Args:
        protocol_type: 协议类型标识
        adapter_class: 协议适配器类
    """
    registry = get_registry()
    registry.register_protocol(protocol_type, adapter_class)


def get_adapter(device_type: str, config: Dict[str, Any]) -> Optional[ProtocolAdapter]:
    """
    获取协议适配器实例（全局注册中心）
    
    Args:
        device_type: 设备类型标识
        config: 设备配置字典
        
    Returns:
        Optional[ProtocolAdapter]: 协议适配器实例
    """
    registry = get_registry()
    return registry.get_adapter(device_type, config)
