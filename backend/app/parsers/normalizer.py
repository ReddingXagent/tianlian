"""
标准化器 - 单位转换 + 时间对齐 + 字段映射

将不同设备的数据统一为标准格式，便于存储和分析。
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from .base_schema import DeviceSchema, Unit

logger = logging.getLogger(__name__)


class DataNormalizer:
    """
    数据标准化器
    
    功能：
        - 单位转换（统一为标准单位）
        - 时间对齐（对齐到整秒/整分）
        - 字段映射（统一字段命名）
        - 数据清洗（异常值过滤）
    
    Example:
        >>> normalizer = DataNormalizer(schema)
        >>> raw_data = {"grid_voltage_a": 2205, "timestamp": datetime.now()}
        >>> normalized = normalizer.normalize(raw_data)
        >>> print(normalized["grid_voltage_a"])  # 220.5V
    """
    
    # 标准单位映射
    STANDARD_UNITS = {
        Unit.VOLTAGE: "V",
        Unit.CURRENT: "A",
        Unit.POWER: "kW",
        Unit.ENERGY: "kWh",
        Unit.FREQUENCY: "Hz",
        Unit.TEMPERATURE: "°C",
        Unit.PERCENTAGE: "%",
        Unit.TIME: "s",
    }

    # 单位转换因子表：{(from_unit, to_unit): factor}
    # 例如 kW → W 乘以 1000，W → kW 除以 1000
    UNIT_CONVERSION_FACTORS = {
        # 功率
        ("kW", "W"): 1000.0,
        ("W", "kW"): 0.001,
        ("MW", "kW"): 1000.0,
        ("kW", "MW"): 0.001,
        ("MW", "W"): 1_000_000.0,
        ("W", "MW"): 0.000_001,
        # 电压
        ("kV", "V"): 1000.0,
        ("V", "kV"): 0.001,
        ("mV", "V"): 0.001,
        ("V", "mV"): 1000.0,
        # 电流
        ("kA", "A"): 1000.0,
        ("A", "kA"): 0.001,
        ("mA", "A"): 0.001,
        ("A", "mA"): 1000.0,
        # 电能
        ("MWh", "kWh"): 1000.0,
        ("kWh", "MWh"): 0.001,
        ("Wh", "kWh"): 0.001,
        ("kWh", "Wh"): 1000.0,
        # 时间
        ("h", "s"): 3600.0,
        ("s", "h"): 1.0 / 3600.0,
        ("min", "s"): 60.0,
        ("s", "min"): 1.0 / 60.0,
        # 频率
        ("kHz", "Hz"): 1000.0,
        ("Hz", "kHz"): 0.001,
        ("MHz", "Hz"): 1_000_000.0,
        ("Hz", "MHz"): 0.000_001,
        # 温度 (需要偏移量, 非纯因子, 由 _convert_temperature 处理)
        ("°F", "°C"): None,
        ("°C", "°F"): None,
        ("K", "°C"): None,
        ("°C", "K"): None,
        ("K", "°F"): None,
        ("°F", "K"): None,
    }
    
    def __init__(self, schema: Optional[DeviceSchema] = None):
        """
        初始化标准化器
        
        Args:
            schema: 设备数据 Schema（可选）
        """
        self.schema = schema
    
    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化数据
        
        Args:
            raw_data: 原始数据字典
            
        Returns:
            Dict[str, Any]: 标准化后的数据
            
        Note:
            处理步骤：
                1. 字段解析（应用 Schema 缩放）
                2. 时间对齐（对齐到整秒）
                3. 数据清洗（过滤异常值）
        """
        normalized = {}
        
        # 1. 字段解析
        for field_name, raw_value in raw_data.items():
            if field_name in ["timestamp", "device_address"]:
                normalized[field_name] = raw_value
                continue
            
            # 应用 Schema 解析
            if self.schema:
                parsed_value = self.schema.parse_value(field_name, raw_value)
                normalized[field_name] = parsed_value
            else:
                normalized[field_name] = raw_value
        
        # 2. 时间对齐
        if "timestamp" in normalized:
            normalized["timestamp"] = self._align_time(normalized["timestamp"])
        
        # 3. 数据清洗
        normalized = self._clean_data(normalized)
        
        return normalized
    
    def _align_time(self, timestamp: datetime) -> datetime:
        """
        时间对齐（对齐到整秒）
        
        Args:
            timestamp: 原始时间戳
            
        Returns:
            datetime: 对齐后的时间戳
        """
        # 对齐到整秒（丢弃微秒）
        aligned = timestamp.replace(microsecond=0)
        return aligned
    
    def _clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        数据清洗（过滤异常值）
        
        Args:
            data: 数据字典
            
        Returns:
            Dict[str, Any]: 清洗后的数据
            
        Note:
            清洗规则：
                - 过滤 None 值
                - 过滤超出范围的值（根据 Schema）
                - 过滤异常负值（电压、功率等）
        """
        cleaned = {}
        
        for field_name, value in data.items():
            # 跳过时间戳和地址
            if field_name in ["timestamp", "device_address"]:
                cleaned[field_name] = value
                continue
            
            # 过滤 None 值
            if value is None:
                logger.warning("过滤空值: %s", field_name)
                continue
            
            # 检查 Schema 范围
            if self.schema:
                field_schema = self.schema.get_field_schema(field_name)
                if field_schema:
                    min_val = field_schema.get("min")
                    max_val = field_schema.get("max")
                    
                    if min_val is not None and value < min_val:
                        logger.warning("过滤异常值: %s=%s < min=%s", field_name, value, min_val)
                        continue
                    
                    if max_val is not None and value > max_val:
                        logger.warning("过滤异常值: %s=%s > max=%s", field_name, value, max_val)
                        continue
            
            # 检查异常负值（电压、功率等不应为负）
            if field_name.endswith("_voltage") and value < 0:
                logger.warning("过滤异常负值: %s=%s", field_name, value)
                continue
            
            if field_name.endswith("_power") and "total" not in field_name and value < 0:
                logger.warning("过滤异常负值: %s=%s", field_name, value)
                continue
            
            cleaned[field_name] = value
        
        return cleaned
    
    def batch_normalize(self, raw_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量标准化数据
        
        Args:
            raw_data_list: 原始数据列表
            
        Returns:
            List[Dict[str, Any]: 标准化后的数据列表
        """
        return [self.normalize(raw_data) for raw_data in raw_data_list]
    
    def convert_units(self, value: float, from_unit: Unit, to_unit: Unit) -> float:
        """
        单位转换
        
        Args:
            value: 原始值
            from_unit: 原始单位
            to_unit: 目标单位
            
        Returns:
            float: 转换后的值
            
        Example:
            >>> value = normalizer.convert_units(1000, Unit.VOLTAGE, Unit.VOLTAGE)  # 无转换
            >>> value = normalizer.convert_units(1, Unit.POWER, Unit.ENERGY)  # kW -> kWh
        """
        # 相同单位，无需转换
        if from_unit == to_unit:
            return value

        from_label = from_unit.value if isinstance(from_unit, Unit) else str(from_unit)
        to_label = to_unit.value if isinstance(to_unit, Unit) else str(to_unit)

        # 正向查找: 用键成员判断区分 "键不存在" 与 "值为 None (温度, 需偏移转换)"。
        # 此前用 .get() is not None 判空, 温度对 value=None 直接跳过整个分支,
        # 导致内层温度调用成为死代码、温度转换静默返回原值。
        forward_key = (from_label, to_label)
        if forward_key in self.UNIT_CONVERSION_FACTORS:
            factor = self.UNIT_CONVERSION_FACTORS[forward_key]
            if factor is None:
                # 温度转换需要偏移量, 非纯因子
                return self._convert_temperature(value, from_label, to_label)
            return value * factor

        # 反向查找: 正向未命中时, 尝试用反方向因子 (value / factor)
        reverse_key = (to_label, from_label)
        if reverse_key in self.UNIT_CONVERSION_FACTORS:
            factor = self.UNIT_CONVERSION_FACTORS[reverse_key]
            if factor is None:
                return self._convert_temperature(value, from_label, to_label)
            return value / factor

        logger.warning("未实现单位转换: %s -> %s", from_label, to_label)
        return value

    def _convert_temperature(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        温度单位转换（需要偏移量，非纯因子）
        
        Formula:
            °F → °C: (°F - 32) × 5/9
            °C → °F: °C × 9/5 + 32
            K  → °C: K - 273.15
            °C → K:  °C + 273.15
        """
        if from_unit == "°F" and to_unit == "°C":
            return (value - 32) * 5.0 / 9.0
        elif from_unit == "°C" and to_unit == "°F":
            return value * 9.0 / 5.0 + 32
        elif from_unit == "K" and to_unit == "°C":
            return value - 273.15
        elif from_unit == "°C" and to_unit == "K":
            return value + 273.15
        elif from_unit == "K" and to_unit == "°F":
            # K → °C → °F
            celsius = value - 273.15
            return celsius * 9.0 / 5.0 + 32
        elif from_unit == "°F" and to_unit == "K":
            # °F → °C → K
            celsius = (value - 32) * 5.0 / 9.0
            return celsius + 273.15
        else:
            logger.warning("未实现温度转换: %s -> %s", from_unit, to_unit)
            return value