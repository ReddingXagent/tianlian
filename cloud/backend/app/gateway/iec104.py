"""
IEC60870-5-104 电力远动通信协议适配器

IEC104 是 IEC60870-5-101 的 TCP/IP 网络版本，广泛应用于电力调度自动化系统。

协议架构:
    - 传输层: TCP/IP (默认端口 2404)
    - 应用层: APCI (应用规约控制信息) + ASDU (应用服务数据单元)

APCI 帧格式 (6字节):
    - 启动字符: 0x68
    - APDU长度: 1字节 (最大253)
    - 控制域: 4字节
        - I帧 (信息传输): 发送序号 + 接收序号
        - S帧 (编号监视): 接收序号
        - U帧 (控制功能): STARTDT/STOPDT/TESTFR

ASDU 类型标识 (TypeID):
    1:  M_SP_NA   单点信息 (遥信)
    3:  M_DP_NA   双点信息
    9:  M_ME_NA   测量值,归一化值
    11: M_ME_NB   测量值,标度化值
    13: M_ME_NC   测量值,短浮点数
    15: M_IT_NA   累计量
    30: M_SP_TB   带CP56时标的单点信息
    45: C_SC_NA   单点命令 (遥控)
    46: C_DC_NA   双点命令
    100: C_IC_NA  总召唤命令
    103: C_CS_NA  时钟同步命令

传输原因 (COT):
    1:  周期/循环
    2:  背景扫描
    3:  突发
    4:  初始化
    5:  请求/被请求
    6:  激活
    7:  激活确认
    8:  停止激活
    9:  停止激活确认
    10: 激活终止
    20: 响应总召唤
"""
import struct
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from enum import IntEnum

from .base import DeviceAdapter

logger = logging.getLogger(__name__)


# ========== IEC104 常量 ==========

class ASDUType(IntEnum):
    """ASDU 类型标识"""
    M_SP_NA = 1       # 单点信息
    M_DP_NA = 3       # 双点信息
    M_ME_NA = 9       # 归一化测量值
    M_ME_NB = 11      # 标度化测量值
    M_ME_NC = 13      # 短浮点测量值
    M_IT_NA = 15      # 累计量
    C_SC_NA = 45      # 单点命令
    C_DC_NA = 46      # 双点命令
    C_IC_NA = 100     # 总召唤命令
    C_CS_NA = 103     # 时钟同步


class CauseOfTransmission(IntEnum):
    """传输原因"""
    PERIODIC = 1
    BACKGROUND = 2
    SPONTANEOUS = 3
    INITIALIZED = 4
    REQUEST = 5
    ACTIVATION = 6
    ACTIVATION_CONFIRM = 7
    DEACTIVATION = 8
    DEACTIVATION_CONFIRM = 9
    ACTIVATION_TERM = 10
    INTERROGATED = 20


# ========== ASDU 编解码器 ==========

class ASDUCodec:
    """IEC104 ASDU 编解码器"""

    @staticmethod
    def encode_general_interrogation(
        common_address: int = 1,
        cause_of_transmission: int = CauseOfTransmission.ACTIVATION,
    ) -> bytes:
        """
        编码总召唤命令 (C_IC_NA)

        ASDU: TypeID(1B) + VSQ(1B) + COT(2B) + CASDU(2B) + IOA(3B) + QOI(1B)
        """
        asdu = bytearray()
        asdu.append(ASDUType.C_IC_NA)       # 类型标识
        asdu.append(0x01)                    # 可变结构限定词 (SQ=0, N=1)
        asdu.append(cause_of_transmission)   # 传输原因 (低字节)
        asdu.append(0x00)                    # 传输原因 (高字节)
        asdu.append(0x00)                    # 公共地址 (低字节)
        asdu.append(common_address & 0xFF)   # 公共地址 (高字节)
        asdu.append(0x00)                    # IOA 低字节
        asdu.append(0x00)                    # IOA 中字节
        asdu.append(0x00)                    # IOA 高字节
        asdu.append(0x14)                    # QOI: 总召唤限定词 (0x14=总召唤)
        return bytes(asdu)

    @staticmethod
    def encode_single_command(
        ioa: int,
        value: bool,
        common_address: int = 1,
    ) -> bytes:
        """
        编码单点遥控命令 (C_SC_NA)

        ASDU: TypeID(1B) + VSQ(1B) + COT(2B) + CASDU(2B) + IOA(3B) + SCO(1B)
        """
        asdu = bytearray()
        asdu.append(ASDUType.C_SC_NA)                # 类型标识
        asdu.append(0x01)                             # 可变结构限定词
        asdu.append(CauseOfTransmission.ACTIVATION)   # 传输原因
        asdu.append(0x00)
        asdu.append(0x00)                             # 公共地址
        asdu.append(common_address & 0xFF)
        # IOA (3字节, 小端)
        asdu.append(ioa & 0xFF)
        asdu.append((ioa >> 8) & 0xFF)
        asdu.append((ioa >> 16) & 0xFF)
        # SCO: 单点命令 0=分闸, 1=合闸
        asdu.append(0x01 if value else 0x00)
        return bytes(asdu)

    @staticmethod
    def decode_asdu(asdu_bytes: bytes) -> Optional[Dict[str, Any]]:
        """
        解码 ASDU

        Returns:
            Optional[Dict]: 解码后的 ASDU 信息
        """
        if len(asdu_bytes) < 7:
            return None

        type_id = asdu_bytes[0]
        vsq = asdu_bytes[1]
        num_elements = vsq & 0x7F
        cot = asdu_bytes[2] | (asdu_bytes[3] << 8)
        casdu = asdu_bytes[4] | (asdu_bytes[5] << 8)

        result = {
            "type_id": type_id,
            "type_name": ASDUType(type_id).name if type_id in [t.value for t in ASDUType] else f"UNKNOWN({type_id})",
            "num_elements": num_elements,
            "cause_of_transmission": cot,
            "common_address": casdu,
        }

        data_start = 6

        # 单点信息 (M_SP_NA)
        if type_id == ASDUType.M_SP_NA and len(asdu_bytes) >= 10:
            ioa = asdu_bytes[data_start] | (asdu_bytes[data_start + 1] << 8) | (asdu_bytes[data_start + 2] << 16)
            siq = asdu_bytes[data_start + 3]
            result["ioa"] = ioa
            result["value"] = bool(siq & 0x01)
            result["quality_valid"] = bool(siq & 0x80)

        # 归一化测量值 (M_ME_NA)
        elif type_id == ASDUType.M_ME_NA and len(asdu_bytes) >= 9:
            ioa = asdu_bytes[data_start] | (asdu_bytes[data_start + 1] << 8) | (asdu_bytes[data_start + 2] << 16)
            raw = struct.unpack(">h", asdu_bytes[data_start + 3:data_start + 5])[0]
            result["ioa"] = ioa
            result["raw_value"] = raw
            result["normalized_value"] = raw / 32767.0

        # 标度化测量值 (M_ME_NB)
        elif type_id == ASDUType.M_ME_NB and len(asdu_bytes) >= 9:
            ioa = asdu_bytes[data_start] | (asdu_bytes[data_start + 1] << 8) | (asdu_bytes[data_start + 2] << 16)
            raw = struct.unpack(">h", asdu_bytes[data_start + 3:data_start + 5])[0]
            result["ioa"] = ioa
            result["raw_value"] = raw

        # 短浮点测量值 (M_ME_NC)
        elif type_id == ASDUType.M_ME_NC and len(asdu_bytes) >= 11:
            ioa = asdu_bytes[data_start] | (asdu_bytes[data_start + 1] << 8) | (asdu_bytes[data_start + 2] << 16)
            float_val = struct.unpack(">f", asdu_bytes[data_start + 3:data_start + 7])[0]
            result["ioa"] = ioa
            result["float_value"] = float(float_val)

        # 累计量 (M_IT_NA)
        elif type_id == ASDUType.M_IT_NA and len(asdu_bytes) >= 10:
            ioa = asdu_bytes[data_start] | (asdu_bytes[data_start + 1] << 8) | (asdu_bytes[data_start + 2] << 16)
            raw = struct.unpack(">I", asdu_bytes[data_start + 3:data_start + 7])[0]
            result["ioa"] = ioa
            result["raw_value"] = raw

        return result


# ========== IEC104 客户端 ==========

class IEC104Client(DeviceAdapter):
    """
    IEC60870-5-104 客户端 (主站)

    用于与变电站 RTU/间隔层设备通信，获取遥测、遥信数据，
    发送遥控命令。

    适用场景: 新能源场站接入调度主站、光伏/储能电站远动通信
    """

    protocol_type = "iec104"

    def __init__(
        self,
        host: str = "192.168.10.50",
        port: int = 2404,
        common_address: int = 1,
        originator_address: int = 10,
        t0_timeout: int = 30,
        t1_timeout: int = 15,
        t2_timeout: int = 10,
        t3_timeout: int = 20,
        k_value: int = 12,
        w_value: int = 8,
        use_tls: bool = False,
        tls_ca_cert: Optional[str] = None,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.common_address = common_address
        self.originator_address = originator_address

        # 超时参数
        self.t0 = t0_timeout
        self.t1 = t1_timeout
        self.t2 = t2_timeout
        self.t3 = t3_timeout

        # 窗口参数
        self.k = k_value
        self.w = w_value

        # TLS
        self.use_tls = use_tls
        self.tls_ca_cert = tls_ca_cert

        # 内部状态
        self._send_seq = 0
        self._recv_seq = 0
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def initialize(self) -> bool:
        logger.info("初始化 IEC104: %s:%d", self.host, self.port)
        self.initialized = True
        return True

    async def connect(self) -> bool:
        logger.info("连接 IEC104 RTU: %s:%d", self.host, self.port)
        # 注: 真实实现需要 asyncio.open_connection + TLS
        self.connected = True
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        if self._writer:
            self._writer.close()
            self._writer = None
        return True

    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """读取 RTU 所有数据"""
        telemetry = await self.read_analog_values()
        telemetry.update(await self.read_digital_values())
        telemetry.update(await self.read_integrated_values())
        telemetry["timestamp"] = datetime.now(timezone.utc)
        telemetry["common_address"] = self.common_address
        return telemetry

    async def write_command(self, device_address: int, command: Dict) -> bool:
        ioa = command.get("ioa", 0)
        value = command.get("value", False)
        return await self.send_command(ioa, value)

    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        return None

    async def general_interrogation(self) -> bool:
        """发送总召唤命令"""
        logger.info("IEC104: 总召唤 公共地址=%d", self.common_address)
        asdu = ASDUCodec.encode_general_interrogation(self.common_address)
        logger.debug("总召唤 ASDU: %s", asdu.hex())
        return True

    async def read_analog_values(self) -> Dict[str, Any]:
        """读取遥测值 (模拟量)"""
        return self._simulate_analog()

    async def read_digital_values(self) -> Dict[str, Any]:
        """读取遥信值 (数字量)"""
        return self._simulate_digital()

    async def read_integrated_values(self) -> Dict[str, Any]:
        """读取累计量"""
        return self._simulate_integrated()

    async def send_command(self, ioa: int, value: bool) -> bool:
        """发送遥控命令"""
        logger.info("IEC104 遥控: IOA=%d, 值=%s", ioa, "合闸" if value else "分闸")
        return True

    async def clock_sync(self) -> bool:
        """时钟同步"""
        logger.info("IEC104: 时钟同步")
        return True

    def _simulate_analog(self) -> Dict[str, Any]:
        """模拟遥测数据"""
        import random
        return {
            "bus_voltage_a": round(random.uniform(215, 225), 1),
            "bus_voltage_b": round(random.uniform(215, 225), 1),
            "bus_voltage_c": round(random.uniform(215, 225), 1),
            "bus_current_a": round(random.uniform(0, 800), 1),
            "bus_current_b": round(random.uniform(0, 800), 1),
            "bus_current_c": round(random.uniform(0, 800), 1),
            "active_power_total": round(random.uniform(0, 50), 2),
            "reactive_power_total": round(random.uniform(-10, 20), 2),
            "grid_frequency": round(random.uniform(49.9, 50.1), 2),
            "power_factor": round(random.uniform(0.85, 1.0), 3),
            "ambient_temperature": round(random.uniform(20, 40), 1),
            "humidity": round(random.uniform(30, 80), 1),
            "wind_speed": round(random.uniform(0, 15), 1),
            "irradiance": round(random.uniform(100, 1000), 0),
        }

    def _simulate_digital(self) -> Dict[str, Any]:
        return {
            "breaker_cb101_status": True,
            "breaker_cb102_status": True,
            "disconnector_ds101_status": True,
            "ground_switch_es101_status": False,
            "protection_relay_status": False,
            "fire_alarm_status": False,
            "door_open_status": False,
            "inverter_running": True,
            "grid_connected": True,
        }

    def _simulate_integrated(self) -> Dict[str, Any]:
        import random
        return {
            "energy_import": round(random.uniform(10000, 50000), 2),
            "energy_export": round(random.uniform(0, 5000), 2),
            "pv_total_energy": round(random.uniform(50000, 200000), 2),
        }
