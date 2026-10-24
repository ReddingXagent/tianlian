"""
Modbus-RTU 模拟器 - 无真实设备时模拟逆变器遥测数据

模拟设备：
- EAHI5-20K 储能逆变器 (Modbus地址 1-10)
- PCS 功率转换系统 (Modbus地址 11-20)
- 电表 (Modbus地址 21-30)

使用：
- 直接导入测试
- 或作为独立进程运行，通过TCP暴露数据
"""
import logging
import random
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ModbusSimulator:
    """Modbus-RTU 设备模拟器"""

    def __init__(self, device_type: str = "inverter", address: int = 1):
        self.device_type = device_type
        self.address = address
        self.connected = False

        # 设备参数范围（真实设备规格）
        self.param_ranges = {
            "inverter": {
                "grid_voltage_a": (220, 240, 0.1),
                "grid_current_a": (0, 50, 0.01),
                "grid_power_a": (0, 20000, 100),
                "grid_frequency": (49.9, 50.1, 0.01),
                "battery_voltage": (400, 600, 0.1),
                "battery_current": (-100, 100, 0.1),
                "battery_soc": (20, 100, 1),
                "battery_temperature": (20, 45, 0.5),
                "pv_power": (0, 20000, 100),
                "pv_voltage": (200, 800, 1),
            },
            "pcs": {
                "dc_voltage": (400, 600, 0.1),
                "dc_current": (-100, 100, 0.1),
                "ac_power": (0, 50000, 100),
                "efficiency": (90, 98, 0.1),
                "temperature": (25, 50, 0.5),
            },
            "meter": {
                "voltage_a": (220, 240, 0.1),
                "voltage_b": (220, 240, 0.1),
                "voltage_c": (220, 240, 0.1),
                "current_a": (0, 100, 0.01),
                "power_total": (0, 100000, 100),
                "frequency": (49.9, 50.1, 0.01),
            }
        }

        # 故障码模拟
        self.fault_codes = {
            "inverter": [0x01, 0x03, 0x07, 0x27, 0x3C, 0x50, 0x7E, 0xA0, None],
            "pcs": [0x0101, 0x0201, None],
            "meter": [None],
        }

    async def connect(self) -> bool:
        """模拟连接"""
        try:
            self.connected = True
            return True
        except Exception:
            logger.exception("ModbusSimulator 连接失败, device_type=%s address=%s", self.device_type, self.address)
            return False

    async def disconnect(self) -> bool:
        try:
            self.connected = False
            return True
        except Exception:
            logger.exception("ModbusSimulator 断开失败, device_type=%s address=%s", self.device_type, self.address)
            return False

    def _generate_value(self, param: str) -> float:
        """生成模拟值（带正常波动）"""
        try:
            if self.device_type not in self.param_ranges:
                return 0
            range_def = self.param_ranges[self.device_type].get(param, (0, 100, 1))
            min_val, max_val, precision = range_def

            # 正常运行时，值在范围内波动（模拟真实设备）
            base = (min_val + max_val) / 2
            variation = (max_val - min_val) * 0.3  # ±30%波动
            value = base + random.uniform(-variation, variation)
            return round(value, int(-1 if precision < 1 else 0))
        except Exception:
            logger.exception("生成模拟值失败, device_type=%s param=%s", self.device_type, param)
            return 0

    async def read_data(self) -> Dict[str, Any]:
        """读取模拟遥测数据"""
        try:
            if not self.connected:
                return {}

            data = {
                "device_id": self.address,
                "device_type": self.device_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            params = self.param_ranges.get(self.device_type, {})
            for param in params:
                data[param] = self._generate_value(param)

            # 模拟故障码（95%正常）; 未知设备类型回退为无故障 [None]
            fault_pool = self.fault_codes.get(self.device_type, [None])
            data["fault_code"] = random.choice(fault_pool)

            return data
        except Exception:
            logger.exception("读取遥测数据失败, device_type=%s address=%s", self.device_type, self.address)
            return {}

    def parse_fault_code(self, raw_data: bytes) -> str:
        """解析故障码（简化版）"""
        try:
            if len(raw_data) < 2:
                return "正常"
            code = raw_data[0] << 8 | raw_data[1]
            fault_map = {
                0x01: "电网过压",
                0x03: "电网欠压",
                0x27: "电网频率异常",
                0x3C: "逆变器过温",
                0x50: "绝缘阻抗低",
                0x7E: "电池过压",
                0xA0: "电池过温",
                0x0101: "功率模块故障",
                0x0201: "通信故障",
            }
            return fault_map.get(code, f"未知故障(0x{code:04X})")
        except Exception:
            logger.exception("解析故障码失败, raw_data=%r", raw_data)
            return "解析异常"


class MQTTSimulator:
    """MQTT 充电桩模拟器"""

    def __init__(self, charger_id: str = "C001"):
        self.charger_id = charger_id
        self.connected = False

        # 充电桩状态
        self.state_ranges = {
            "charging_power": (0, 120000, 1000),  # W
            "charging_voltage": (200, 800, 1),
            "charging_current": (0, 250, 0.1),
            "soc": (0, 100, 1),
            "battery_temp": (20, 45, 0.5),
            "charging_duration": (0, 7200, 60),
            "connector_temp": (25, 55, 0.5),
        }

        self.fault_codes = [0x0101, 0x0201, 0x0601, None]

    async def connect(self) -> bool:
        try:
            self.connected = True
            return True
        except Exception:
            logger.exception("MQTTSimulator 连接失败, charger_id=%s", self.charger_id)
            return False

    async def disconnect(self) -> bool:
        try:
            self.connected = False
            return True
        except Exception:
            logger.exception("MQTTSimulator 断开失败, charger_id=%s", self.charger_id)
            return False

    def _generate_value(self, param: str) -> float:
        try:
            range_def = self.state_ranges.get(param, (0, 100, 1))
            min_val, max_val, precision = range_def
            base = (min_val + max_val) / 2
            variation = (max_val - min_val) * 0.3
            value = base + random.uniform(-variation, variation)
            return round(value, int(-1 if precision < 1 else 0))
        except Exception:
            logger.exception("生成充电桩模拟值失败, charger_id=%s param=%s", self.charger_id, param)
            return 0

    async def read_data(self) -> Dict[str, Any]:
        try:
            if not self.connected:
                return {}

            return {
                "charger_id": self.charger_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": random.choice(["charging", "idle", "fault"]),
                **{p: self._generate_value(p) for p in self.state_ranges},
                "fault_code": random.choice(self.fault_codes),
            }
        except Exception:
            logger.exception("读取充电桩遥测数据失败, charger_id=%s", self.charger_id)
            return {}


# ========== 测试入口 ==========

async def test_simulators():
    """测试模拟器"""
    logger.info("=== Modbus 逆变器模拟 ===")
    inv = ModbusSimulator("inverter", 1)
    await inv.connect()
    data = await inv.read_data()
    for k, v in data.items():
        logger.info("  %s: %s", k, v)

    logger.info("\n=== MQTT 充电桩模拟 ===")
    charger = MQTTSimulator("C001")
    await charger.connect()
    data = await charger.read_data()
    for k, v in data.items():
        logger.info("  %s: %s", k, v)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_simulators())
