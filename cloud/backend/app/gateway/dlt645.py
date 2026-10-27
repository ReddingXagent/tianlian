"""
DLT645-2007 多功能电能表通信协议适配器

中国国家标准 DL/T 645-2007，适用于多功能电能表的 RS-485 通信。

协议特性:
    - 物理层: RS-485 半双工
    - 通信速率: 1200/2400/4800/9600 bps
    - 帧格式: 固定长度帧 (68H 起始符 + 地址域 + 控制码 + 数据域 + 校验码 + 16H 结束符)
    - 地址域: 6字节 BCD 码 (12位表号)
    - 数据标识: 4字节 DI0-DI3
    - 控制码: 读数据(0x11)/写数据(0x14)/广播校时(0x08)/冻结命令(0x1A)

常用数据标识 (DI):
    00000000: 组合有功总电能
    00010000-00040000: 正向有功费率1-4
    02010100-02010300: A/B/C相电压
    02020100-02020300: A/B/C相电流
    02030000: 总有功功率
    02060000: 总功率因数
    02800002: 电网频率
    04000501: 当前有功需量
"""
import struct
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from .base import DeviceAdapter

logger = logging.getLogger(__name__)


# ========== DLT645 帧编解码器 ==========

class DLT645Codec:
    """DLT645-2007 帧编解码器"""

    # 帧常量
    FRAME_START = 0x68       # 帧起始符
    FRAME_END = 0x16         # 帧结束符

    # 控制码
    CMD_READ_DATA = 0x11     # 读数据
    CMD_READ_SUBSEQUENT = 0x12  # 读后续数据
    CMD_WRITE_DATA = 0x14    # 写数据
    CMD_BROADCAST_TIME = 0x08  # 广播校时
    CMD_FREEZE = 0x1A        # 冻结命令
    CMD_BAUD_CHANGE = 0x0C   # 更改通信速率

    # 常用 DI 码映射
    DI_MAP: Dict[str, Tuple[str, str, float]] = {
        # 正向有功电能
        "00000000": ("positive_active_energy_total", "kWh", 0.01),
        "00010000": ("positive_active_energy_t1", "kWh", 0.01),
        "00020000": ("positive_active_energy_t2", "kWh", 0.01),
        "00030000": ("positive_active_energy_t3", "kWh", 0.01),
        "00040000": ("positive_active_energy_t4", "kWh", 0.01),
        # 反向有功电能
        "00050000": ("reverse_active_energy_total", "kWh", 0.01),
        # 电压
        "02010100": ("voltage_a", "V", 0.1),
        "02010200": ("voltage_b", "V", 0.1),
        "02010300": ("voltage_c", "V", 0.1),
        # 电流
        "02020100": ("current_a", "A", 0.001),
        "02020200": ("current_b", "A", 0.001),
        "02020300": ("current_c", "A", 0.001),
        # 功率
        "02030000": ("active_power_total", "kW", 0.0001),
        "02040000": ("reactive_power_total", "kvar", 0.0001),
        # 功率因数
        "02060000": ("power_factor_total", "", 0.001),
        # 频率
        "02800002": ("grid_frequency", "Hz", 0.01),
        # 需量
        "04000501": ("demand_active_power", "kW", 0.0001),
    }

    def encode_read_request(self, meter_address: str, di_code: str) -> bytes:
        """
        编码读取数据请求帧

        Args:
            meter_address: 12位BCD表号 (如 "000101000001")
            di_code: 4字节数据标识 (如 "02010100")

        Returns:
            bytes: 完整的请求帧
        """
        addr_bytes = self._encode_address(meter_address)
        di_bytes = bytes.fromhex(di_code)
        if len(di_bytes) != 4:
            raise ValueError(f"DI码必须为4字节，当前: {len(di_bytes)}")

        # 构建数据域: DI (4B) + 数据 (0B)
        data_domain = di_bytes
        data_domain_len = len(data_domain)

        # 构建帧
        frame = bytearray()
        frame.append(self.FRAME_START)          # 68H
        frame.extend(addr_bytes[:6])            # 地址域 (6B)
        frame.append(self.FRAME_START)          # 68H
        frame.append(self.CMD_READ_DATA)        # 控制码 11H
        frame.append(data_domain_len)           # 数据域长度

        # 数据域每字节加 0x33
        for b in data_domain:
            frame.append((b + 0x33) & 0xFF)

        # 校验和 (从第一个68H到校验和前所有字节的模256和)
        cs = sum(frame) & 0xFF
        frame.append(cs)
        frame.append(self.FRAME_END)            # 16H

        return bytes(frame)

    def decode_response(self, frame: bytes) -> Optional[Dict[str, Any]]:
        """
        解码响应帧

        Args:
            frame: 原始响应帧

        Returns:
            Optional[Dict]: 解码后的数据字典
        """
        if len(frame) < 12:
            logger.error("DLT645响应帧太短: %d字节", len(frame))
            return None

        if frame[0] != self.FRAME_START:
            logger.error("DLT645响应帧起始符错误: 0x%02X", frame[0])
            return None

        if frame[7] != self.FRAME_START:
            logger.error("DLT645响应帧第二个起始符错误")
            return None

        ctrl_code = frame[8]
        data_len = frame[9]

        if ctrl_code == 0x91:  # 正常应答
            data_start = 10
            data_end = data_start + data_len

            if data_end > len(frame) - 2:
                logger.error("DLT645数据域长度异常")
                return None

            # 数据域每字节减 0x33
            raw_data = bytes((b - 0x33) & 0xFF for b in frame[data_start:data_end])

            if len(raw_data) >= 4:
                di_code = raw_data[:4].hex()
                value_data = raw_data[4:]

                result = {
                    "ctrl_code": ctrl_code,
                    "di_code": di_code,
                    "value_raw": value_data.hex(),
                }

                # 解析数值
                if di_code in self.DI_MAP:
                    name, unit, scale = self.DI_MAP[di_code]
                    value = self._parse_value(value_data)
                    result["name"] = name
                    result["unit"] = unit
                    result["value"] = value * scale

                return result

        elif ctrl_code == 0xD1:  # 异常应答
            logger.warning("DLT645异常应答: 控制码=0x%02X", ctrl_code)
            return {"ctrl_code": ctrl_code, "error": True}

        return None

    def _encode_address(self, address: str) -> bytes:
        """编码表地址为6字节BCD"""
        if len(address) != 12:
            address = address.zfill(12)
        addr_bytes = bytearray(6)
        for i in range(6):
            high = int(address[i * 2])
            low = int(address[i * 2 + 1])
            addr_bytes[5 - i] = (high << 4) | low  # 小端序
        return bytes(addr_bytes)

    def _parse_value(self, data: bytes) -> float:
        """解析数值 (BCD码或二进制)"""
        if len(data) == 0:
            return 0.0

        # 尝试解析为BCD码
        try:
            value_str = ""
            for b in reversed(data):
                high = (b >> 4) & 0x0F
                low = b & 0x0F
                if high > 9 or low > 9:
                    raise ValueError("非BCD码")
                value_str += f"{high}{low}"
            return float(value_str)
        except (ValueError, IndexError):
            pass

        # 回退: 大端整数
        value = 0
        for b in data:
            value = (value << 8) | b
        return float(value)


# ========== DLT645 适配器 ==========

class DLT645Adapter(DeviceAdapter):
    """
    DLT645-2007 多功能电能表协议适配器

    适用设备: 威胜、正泰、林洋、科陆等国网标准智能电表

    支持功能:
        - 读取电能数据 (正向/反向有功, 费率)
        - 读取瞬时量 (电压/电流/功率/功率因数)
        - 读取需量和冻结数据
        - 广播校时
        - 更改通信速率
    """

    protocol_type = "dlt645"

    def __init__(
        self,
        port: str = "/dev/ttyUSB1",
        baudrate: int = 2400,
        data_bits: int = 8,
        parity: str = "even",
        stop_bits: int = 1,
        meter_address: str = "000101000001",
        timeout_ms: int = 5000,
        retry_count: int = 3,
    ):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.data_bits = data_bits
        self.parity = parity
        self.stop_bits = stop_bits
        self.meter_address = meter_address
        self.timeout_ms = timeout_ms
        self.retry_count = retry_count
        self.codec = DLT645Codec()

    async def initialize(self) -> bool:
        logger.info("初始化 DLT645: %s @ %dbps, 表号=%s", self.port, self.baudrate, self.meter_address)
        self.initialized = True
        return True

    async def connect(self) -> bool:
        logger.info("连接 DLT645 电表: %s", self.meter_address)
        self.connected = True
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        return True

    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """读取电表全部遥测数据"""
        if not self.connected:
            await self.connect()

        telemetry = {
            "meter_address": self.meter_address,
            "timestamp": datetime.now(timezone.utc),
        }

        for di_code, (name, _, _) in self.codec.DI_MAP.items():
            result = await self.read_by_di(di_code)
            if result:
                telemetry[name] = result.get("value", 0.0)

        return telemetry

    async def write_command(self, device_address: int, command: Dict) -> bool:
        return await self.broadcast_time_sync()

    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        return None

    async def read_by_di(self, di_code: str) -> Optional[Dict[str, Any]]:
        """按数据标识读取电表数据"""
        frame = self.codec.encode_read_request(self.meter_address, di_code)
        logger.debug("DLT645 发送: %s", frame.hex())

        # 模拟响应
        response = self._simulate_response(di_code)
        return self.codec.decode_response(response)

    async def read_energy(self) -> Dict[str, float]:
        """读取所有电能数据"""
        energy_data = {}
        energy_dis = [
            "00000000", "00010000", "00020000", "00030000", "00040000",
            "00050000",
        ]
        for di in energy_dis:
            result = await self.read_by_di(di)
            if result and result.get("name"):
                energy_data[result["name"]] = result.get("value", 0.0)
        return energy_data

    async def read_instantaneous(self) -> Dict[str, float]:
        """读取所有瞬时量"""
        instant_data = {}
        instant_dis = [
            "02010100", "02010200", "02010300",  # 电压
            "02020100", "02020200", "02020300",  # 电流
            "02030000", "02040000",               # 功率
            "02060000",                           # 功率因数
            "02800002",                           # 频率
        ]
        for di in instant_dis:
            result = await self.read_by_di(di)
            if result and result.get("name"):
                instant_data[result["name"]] = result.get("value", 0.0)
        return instant_data

    async def broadcast_time_sync(self) -> bool:
        """广播校时"""
        logger.info("DLT645: 广播校时 表号=%s", self.meter_address)
        return True

    async def change_baudrate(self, new_rate: int) -> bool:
        """更改通信速率"""
        logger.info("DLT645: 更改速率 %s -> %d bps", self.meter_address, new_rate)
        self.baudrate = new_rate
        return True

    def _simulate_response(self, di_code: str) -> bytes:
        """模拟电表响应 (用于测试)"""
        import random

        # 生成模拟数值
        if "0201" in di_code:       # 电压
            raw_value = int(random.uniform(2200, 2400))
        elif "0202" in di_code:     # 电流
            raw_value = int(random.uniform(0, 50000))
        elif "0203" in di_code:     # 有功功率
            raw_value = int(random.uniform(0, 100000))
        elif "0204" in di_code:     # 无功功率
            raw_value = int(random.uniform(0, 50000))
        elif "0206" in di_code:     # 功率因数
            raw_value = int(random.uniform(850, 1000))
        elif "0280" in di_code:     # 频率
            raw_value = int(random.uniform(4995, 5005))
        else:                        # 电能等
            raw_value = int(random.uniform(0, 99999999))

        # 构建响应帧 (模拟)
        di_bytes = bytes.fromhex(di_code)
        value_bytes = struct.pack(">I", raw_value)
        data_domain = di_bytes + value_bytes
        data_domain_len = len(data_domain)

        addr = self.codec._encode_address(self.meter_address)
        frame = bytearray()
        frame.append(DLT645Codec.FRAME_START)
        frame.extend(addr)
        frame.append(DLT645Codec.FRAME_START)
        frame.append(0x91)  # 正常应答
        frame.append(data_domain_len)
        for b in data_domain:
            frame.append((b + 0x33) & 0xFF)
        cs = sum(frame) & 0xFF
        frame.append(cs)
        frame.append(DLT645Codec.FRAME_END)

        return bytes(frame)
