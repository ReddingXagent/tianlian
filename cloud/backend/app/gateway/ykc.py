"""
YKC 云快充 V1.6 协议接入适配器 - 适用于电动汽车充电桩（任务卡 9a5d070e）

江苏云快充《充电桩与云快充服务平台交互协议》V1.6。

协议特性:
    - 通信模型: 桩主动 TCP 直连平台（平台为 TCP server），长连接，端口约定 8767
    - 帧格式: 0x68 | 长度(1) | 序列号(2) | 加密标志(1) | 帧类型(1) | 消息体(N) | CRC16(2)
    - 长度 = 序列号+加密标志+帧类型+消息体 字节数
    - CRC16: 附录 13.2 码表即标准 Modbus CRC（poly 0xA001, init 0xFFFF，低字节在前），
      校验范围从序列号域到消息体末尾
    - 数值: BIN 小端，乘倍率上送（如电压 0.1V/位）

支持帧（本适配器接入范围）:
    - 0x01 登录认证 / 0x02 登录应答
    - 0x03 心跳 / 0x04 心跳应答
    - 0x13 实时监测数据（遥测归一化入库）
    - 0x3B 交易记录 / 0x40 交易记录确认

双格式自适应（V1.6 / V1.8+）:
    - V1.6 桩编号 7 字节 BCD（14 位），V1.8+ 8 字节 BCD（16 位）
    - 登录帧按通信协议版本字节（版本×10，0x10=V1.6）或帧长度自动识别
    - Device.sn 匹配两种都认：14 位左补零到 16 位
"""
import asyncio
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

from .base import DeviceAdapter

logger = logging.getLogger(__name__)


# ========== 入网状态钩子（参照 ocpp.mark_device_online 模式） ==========

def normalize_sn(sn: str) -> str:
    """桩编号归一化：14 位（V1.6）左补零到 16 位，其余原样返回。"""
    sn = (sn or "").strip()
    if len(sn) == 14 and sn.isdigit():
        return sn.zfill(16)
    return sn


def find_device_by_sn(sn: str):
    """按归一化 SN 查询 Device，两种格式都认。未匹配返回 None。"""
    normalized = normalize_sn(sn)
    try:
        from app.models.device import Device

        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            return (
                session.query(Device)
                .filter((Device.sn == normalized) | (Device.sn == sn))
                .first()
            )
        finally:
            session.close()
    except Exception as e:  # 网关侧兜底：查询失败不得影响通信
        logger.warning("YKC 设备查询失败 sn=%s: %s", sn, e)
        return None


def mark_device_online(sn: str) -> bool:
    """桩登录成功后，将其 provision_status 置 ONLINE（幂等）。

    模块级、同步：供连接协程经 ``asyncio.to_thread`` 卸载到线程池调用，
    避免同步 DB IO 阻塞事件循环；任何异常仅记日志、不抛。
    """
    if not sn:
        return False
    try:
        from app.models.device import Device, ProvisionStatus

        from app.core.database import SessionLocal

        normalized = normalize_sn(sn)
        session = SessionLocal()
        try:
            device = (
                session.query(Device)
                .filter((Device.sn == normalized) | (Device.sn == sn))
                .first()
            )
            if device is None:
                logger.info("YKC 入网登记跳过：未匹配到设备 sn=%s", sn)
                return False
            if device.provision_status == ProvisionStatus.ONLINE:
                return True  # 幂等：已在网，免写
            device.provision_status = ProvisionStatus.ONLINE
            session.commit()
            logger.info("YKC 入网登记成功：device=%s → online", sn)
            return True
        finally:
            session.close()
    except Exception as e:  # 网关侧兜底：登记失败不得阻断通信
        logger.warning("YKC 入网登记失败（不影响通信）sn=%s: %s", sn, e)
        return False


# ========== CRC16（附录 13.2 Modbus 码表的等价位运算实现） ==========

def crc16(data: bytes) -> int:
    """Modbus CRC16：poly 0xA001（0x180D 族），init 0xFFFF。

    帧内低字节在前、高字节在后（``struct.pack('<H', crc16(...))``）。
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


# ========== 帧类型码 ==========

class YKCFrameType:
    """YKC 帧类型码常量（桩奇数 / 平台偶数）"""
    LOGIN = 0x01               # 充电桩登录认证
    LOGIN_ACK = 0x02           # 登录认证应答
    HEARTBEAT = 0x03           # 充电桩心跳包
    HEARTBEAT_ACK = 0x04       # 心跳包应答
    REALTIME_DATA = 0x13       # 上传实时监测数据
    REMOTE_START_ACK = 0x33    # 远程启机命令回复
    REMOTE_STOP_ACK = 0x35     # 远程停机命令回复
    TRANSACTION = 0x3B         # 交易记录
    TRANSACTION_ACK = 0x40     # 交易记录确认


class YKCLoginResult:
    SUCCESS = 0x00
    FAILURE = 0x01


class YKCGunStatus:
    """0x13 实时数据枪状态"""
    OFFLINE = 0x00
    FAULT = 0x01
    IDLE = 0x02
    CHARGING = 0x03


GUN_STATUS_NAMES = {
    YKCGunStatus.OFFLINE: "offline",
    YKCGunStatus.FAULT: "fault",
    YKCGunStatus.IDLE: "idle",
    YKCGunStatus.CHARGING: "charging",
}


# ========== 桩业务时区 (卡 3364cef4, 参照 szbus._device_now) ==========

def _device_tz() -> ZoneInfo:
    """CP56Time2a 墙钟字段所属的桩业务时区。配置非法时回退 Asia/Shanghai。"""
    try:
        from app.core.config import settings
        return ZoneInfo(settings.YKC_DEVICE_TIMEZONE)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


# ========== BCD / CP56Time2a 辅助 ==========

def encode_bcd(value: str, length: int) -> bytes:
    """数字串编码为 BCD 字节，不足长度左补零（0），奇数位前置 0。"""
    value = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(value) < length * 2:
        value = value.zfill(length * 2)
    return bytes.fromhex(value[-length * 2:])


def decode_bcd(data: bytes) -> str:
    """BCD 字节解码为数字串。"""
    return "".join(format(b, "02X") for b in data)


def encode_cp56time2a(dt: datetime) -> bytes:
    """时间编码为 CP56Time2a 7 字节格式（SPEC §3.2）。

    入参当绝对时刻, 先转到桩业务时区再打包墙钟字段（卡 3364cef4）。
    毫秒域 = 秒×1000 + 毫秒（规格书样例 98B70E = 47.000s）。
    """
    dt = dt.astimezone(_device_tz())
    ms = dt.second * 1000 + dt.microsecond // 1000
    return bytes([
        ms & 0xFF,
        (ms >> 8) & 0xFF,
        dt.minute & 0x3F,
        dt.hour & 0x1F,
        ((dt.isoweekday() << 5) | dt.day) & 0xFF,
        dt.month & 0x0F,
        (dt.year - 2000) & 0x7F,
    ])


def decode_cp56time2a(data: bytes) -> datetime:
    """CP56Time2a 7 字节解码为 UTC aware datetime（卡 3364cef4）。

    墙钟字段按桩业务时区（默认北京墙钟, settings.YKC_DEVICE_TIMEZONE 可配）
    解释, 归一为 UTC 存储。
    """
    ms = data[0] | (data[1] << 8)
    minute = data[2] & 0x3F
    hour = data[3] & 0x1F
    day = data[4] & 0x1F
    month = data[5] & 0x0F
    year = 2000 + (data[6] & 0x7F)
    wallclock = datetime(year, month, day, hour, minute, ms // 1000, (ms % 1000) * 1000,
                         tzinfo=_device_tz())
    return wallclock.astimezone(timezone.utc)


# ========== 双格式自适应 ==========

def detect_protocol_version(login_body: bytes) -> int:
    """识别登录帧通信协议版本，返回 16 / 18。

    优先按协议版本字节（版本×10，V1.6=0x10）识别，回退帧长度识别:
      - V1.6 登录体 30 字节（桩编号 7B），版本字节偏移 9
      - V1.8 登录体 31 字节（桩编号 8B），版本字节偏移 10
    """
    if len(login_body) == 30:
        return 16
    if len(login_body) == 31:
        return 18
    # 非标准长度：按版本字节探测（0x10~0x20 视为合法版本×10）
    # V1.6 布局版本字节偏移 9（桩编号 7B 后），V1.8+ 偏移 10（桩编号 8B 后）
    if len(login_body) > 9 and 0x10 <= login_body[9] <= 0x16:
        return 16
    if len(login_body) > 10 and 0x10 <= login_body[10] <= 0x20:
        return 18
    return 16  # 默认按规格书主体 V1.6


def sn_length_for_version(version: int) -> int:
    """按协议版本取桩编号字节数：V1.6=7（14位），V1.8+=8（16位）。"""
    return 7 if version <= 16 else 8


# ========== 帧结构 ==========

@dataclass
class YKCFrame:
    """应用层报文帧（§3.1）"""
    seq: int
    frame_type: int
    body: bytes = b""
    encrypt: int = 0

    def encode(self) -> bytes:
        head = struct.pack("<HBB", self.seq, self.encrypt, self.frame_type)
        crc = crc16(head + self.body)
        length = len(head) + len(self.body)
        if length > 0xFF:
            raise ValueError("数据域超过 255 字节: %d" % length)
        return b"\x68" + bytes([length]) + head + self.body + struct.pack("<H", crc)


class YKCCodec:
    """YKC 帧编解码器"""

    FRAME_START = 0x68
    FRAME_OVERHEAD = 7  # start(1)+len(1)+seq(2)+encrypt(1)+type(1)+crc(2) - len 已含 seq..body

    class FrameError(ValueError):
        pass

    def decode(self, data: bytes) -> YKCFrame:
        """解码单帧（不含粘包处理）。帧不合法抛 FrameError。"""
        if len(data) < 8:
            raise self.FrameError("帧过短: %d 字节" % len(data))
        if data[0] != self.FRAME_START:
            raise self.FrameError("起始标志错误: 0x%02X" % data[0])
        length = data[1]
        total = 2 + length + 2  # start+len 之后：数据域 length 字节 + crc 2 字节
        if len(data) < total:
            raise self.FrameError("帧不完整: 需 %d 字节, 实际 %d" % (total, len(data)))
        payload = data[2:2 + length]
        seq, encrypt, frame_type = struct.unpack("<HBB", payload[:4])
        body = payload[4:]
        crc_recv = struct.unpack("<H", data[2 + length:2 + length + 2])[0]
        crc_calc = crc16(payload)
        if crc_recv != crc_calc:
            raise self.FrameError(
                "CRC 校验失败: 收到 0x%04X, 计算 0x%04X" % (crc_recv, crc_calc)
            )
        if encrypt != 0x00:
            raise self.FrameError("不支持加密帧: 0x%02X" % encrypt)
        return YKCFrame(seq=seq, frame_type=frame_type, body=body, encrypt=encrypt)

    def extract_frames(self, buffer: bytes):
        """从 TCP 接收缓冲中切分完整帧，返回 (帧列表, 剩余字节)。"""
        frames = []
        rest = buffer
        while len(rest) >= 8:
            if rest[0] != self.FRAME_START:
                # 丢弃垃圾字节直到下一个起始标志
                idx = rest.find(bytes([self.FRAME_START]))
                if idx < 0:
                    return frames, b""
                rest = rest[idx:]
                continue
            length = rest[1]
            total = 2 + length + 2
            if len(rest) < total:
                break
            try:
                frames.append(self.decode(rest[:total]))
            except self.FrameError as e:
                logger.warning("YKC 丢弃坏帧: %s", e)
            rest = rest[total:]
        return frames, rest


# ========== 报文体编解码 ==========

def encode_login_ack(sn: str, result: int, sn_len: int) -> bytes:
    """0x02 登录应答体: 桩编码 + 登陆结果。"""
    return encode_bcd(sn, sn_len) + bytes([result])


def encode_heartbeat_ack(sn: str, gun_no: int, sn_len: int) -> bytes:
    """0x04 心跳应答体: 桩编码 + 枪号 + 心跳应答(置0)。"""
    return encode_bcd(sn, sn_len) + bytes([gun_no, 0x00])


def encode_transaction_ack(trade_no: str) -> bytes:
    """0x40 交易记录确认体: 交易流水号 + 确认结果(0=上传成功)。"""
    return encode_bcd(trade_no, 16) + bytes([0x00])


def decode_login(body: bytes) -> Dict[str, Any]:
    """解析 0x01 登录认证体（自动适配 V1.6/V1.8+）。"""
    version = detect_protocol_version(body)
    sn_len = sn_length_for_version(version)
    if len(body) < sn_len + 4:
        raise YKCCodec.FrameError("登录体过短: %d" % len(body))
    offset = sn_len
    return {
        "sn": decode_bcd(body[:sn_len]),
        "sn_len": sn_len,
        "pile_type": body[offset],          # 0 直流 / 1 交流
        "gun_count": body[offset + 1],
        "protocol_version_raw": body[offset + 2],
        "protocol_version": version,
        "program_version": body[offset + 3:offset + 11].split(b"\x00")[0].decode("ascii", "ignore"),
        "net_type": body[offset + 11] if len(body) > offset + 11 else None,
        "sim": decode_bcd(body[offset + 12:offset + 22]) if len(body) >= offset + 22 else "",
        "operator": body[offset + 22] if len(body) > offset + 22 else None,
    }


def decode_heartbeat(body: bytes, sn_len: int) -> Dict[str, Any]:
    """解析 0x03 心跳体。"""
    if len(body) < sn_len + 2:
        raise YKCCodec.FrameError("心跳体过短: %d" % len(body))
    return {
        "sn": decode_bcd(body[:sn_len]),
        "gun_no": body[sn_len],
        "gun_status": body[sn_len + 1],  # 0x00 正常 0x01 故障
    }


def decode_realtime(body: bytes, sn_len: int) -> Dict[str, Any]:
    """解析 0x13 实时监测数据体（遥测）。"""
    need = sn_len + 1 + 1 + 1 + 1 + 2 + 2 + 1 + 8 + 1 + 1 + 2 + 2 + 4 + 4 + 4 + 2
    if len(body) < need:
        raise YKCCodec.FrameError("实时数据体过短: %d < %d" % (len(body), need))
    off = 0
    trade_no = decode_bcd(body[off:off + 16]); off += 16
    sn = decode_bcd(body[off:off + sn_len]); off += sn_len
    gun_no = body[off]; off += 1
    status = body[off]; off += 1
    gun_homed = body[off]; off += 1
    plugged = body[off]; off += 1
    voltage = struct.unpack("<H", body[off:off + 2])[0] * 0.1; off += 2
    current = struct.unpack("<H", body[off:off + 2])[0] * 0.1; off += 2
    gun_temp = body[off] - 50; off += 1
    gun_code = body[off:off + 8].hex(); off += 8
    soc = body[off]; off += 1
    max_battery_temp = body[off] - 50; off += 1
    charged_minutes = struct.unpack("<H", body[off:off + 2])[0]; off += 2
    remain_minutes = struct.unpack("<H", body[off:off + 2])[0]; off += 2
    energy = struct.unpack("<I", body[off:off + 4])[0] * 0.0001; off += 4
    loss_energy = struct.unpack("<I", body[off:off + 4])[0] * 0.0001; off += 4
    amount = struct.unpack("<I", body[off:off + 4])[0] * 0.0001; off += 4
    fault_bits = struct.unpack("<H", body[off:off + 2])[0]; off += 2
    return {
        "trade_no": trade_no,
        "sn": sn,
        "gun_no": gun_no,
        "status": status,
        "status_name": GUN_STATUS_NAMES.get(status, "unknown"),
        "gun_homed": gun_homed,
        "plugged": plugged,
        "voltage": voltage,
        "current": current,
        "power": round(voltage * current / 1000.0, 4),  # kW
        "gun_temp": gun_temp,
        "gun_code": gun_code,
        "soc": soc,
        "max_battery_temp": max_battery_temp,
        "charged_minutes": charged_minutes,
        "remain_minutes": remain_minutes,
        "energy": energy,
        "loss_energy": loss_energy,
        "amount": amount,
        "fault_bits": fault_bits,
        "has_fault": fault_bits != 0,
    }


def decode_transaction(body: bytes, sn_len: int) -> Dict[str, Any]:
    """解析 0x3B 交易记录体。"""
    need = 16 + sn_len + 1 + 7 + 7 + 64 + 5 + 5 + 4 + 4 + 4 + 17 + 1 + 7 + 1 + 8
    if len(body) < need:
        raise YKCCodec.FrameError("交易记录体过短: %d < %d" % (len(body), need))
    off = 0
    trade_no = decode_bcd(body[off:off + 16]); off += 16
    sn = decode_bcd(body[off:off + sn_len]); off += sn_len
    gun_no = body[off]; off += 1
    start_time = decode_cp56time2a(body[off:off + 7]); off += 7
    end_time = decode_cp56time2a(body[off:off + 7]); off += 7
    tou = {}
    for name in ("peak_tip", "peak", "flat", "valley"):
        tou[name] = {
            "price": struct.unpack("<I", body[off:off + 4])[0] * 0.00001,
            "energy": struct.unpack("<I", body[off + 4:off + 8])[0] * 0.0001,
            "loss_energy": struct.unpack("<I", body[off + 8:off + 12])[0] * 0.0001,
            "amount": struct.unpack("<I", body[off + 12:off + 16])[0] * 0.0001,
        }
        off += 16
    meter_start = int.from_bytes(body[off:off + 5], "little") * 0.0001; off += 5
    meter_stop = int.from_bytes(body[off:off + 5], "little") * 0.0001; off += 5
    total_energy = struct.unpack("<I", body[off:off + 4])[0] * 0.0001; off += 4
    loss_total_energy = struct.unpack("<I", body[off:off + 4])[0] * 0.0001; off += 4
    total_amount = struct.unpack("<I", body[off:off + 4])[0] * 0.0001; off += 4
    vin = body[off:off + 17].decode("ascii", "ignore").rstrip("\x00"); off += 17
    trade_flag = body[off]; off += 1
    trade_time = decode_cp56time2a(body[off:off + 7]); off += 7
    stop_reason = body[off]; off += 1
    physical_card = body[off:off + 8].hex(); off += 8
    return {
        "trade_no": trade_no,
        "sn": sn,
        "gun_no": gun_no,
        "start_time": start_time,
        "end_time": end_time,
        "tou": tou,
        "meter_start": meter_start,
        "meter_stop": meter_stop,
        "total_energy": total_energy,
        "loss_total_energy": loss_total_energy,
        "total_amount": total_amount,
        "vin": vin,
        "trade_flag": trade_flag,
        "trade_time": trade_time,
        "stop_reason": stop_reason,
        "physical_card": physical_card,
    }


# ========== YKC 适配器（TCP server，桩主动直连） ==========

class YKCAdapter(DeviceAdapter):
    """YKC 云快充协议适配器

    平台侧 TCP server：监听 host:port（默认 0.0.0.0:8767），桩主动连接。
    每连接独立会话，登录成功前拒绝业务帧（心跳/遥测/交易）。

    典型流程（§5.1 上电流程）:
        1. 桩 → 平台: 0x01 登录认证（桩编号+版本）
        2. 平台 → 桩: 0x02 登录应答（成功才允许后续交互，失败断连）
        3. 桩 → 平台: 0x03 心跳（10 秒周期，3 次未收到视为离线）
        4. 桩 → 平台: 0x13 实时监测数据（归一化入管道）
        5. 桩 → 平台: 0x3B 交易记录 → 0x40 确认
    """

    protocol_type = "ykc"
    device_type = "charger_ykc"

    HEARTBEAT_TIMEOUT_MISSING = 3  # 3 次未收到心跳视为离线

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8767,
        pile_password: str = "",
        heartbeat_interval: int = 10,
    ):
        self.host = host
        self.port = port
        self.pile_password = pile_password  # 空 = 不校验密码（YKC 登录帧本身无密码域）
        self.heartbeat_interval = heartbeat_interval
        self.codec = YKCCodec()
        self._server: Optional[asyncio.AbstractServer] = None
        self._sessions: Dict[str, Dict[str, Any]] = {}  # sn -> session 状态
        self._pipeline = None
        super().__init__()

    # ===== 生命周期 =====

    async def initialize(self) -> bool:
        logger.info("初始化 YKC 网关: %s:%d", self.host, self.port)
        try:
            from app.parsers.pipeline import ParsePipeline
            self._pipeline = ParsePipeline(device_type=self.device_type, protocol=self.protocol_type)
        except Exception as e:
            logger.warning("YKC 解析管道初始化失败（遥测仅解析不入库）: %s", e)
        self.initialized = True
        return True

    async def connect(self) -> bool:
        """启动 TCP server，接受桩直连。"""
        if self._server is not None:
            return True
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        self.connected = True
        logger.info("YKC 网关已监听 %s:%d", self.host, self.port)
        return True

    async def disconnect(self) -> bool:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._sessions.clear()
        self.connected = False
        return True

    async def shutdown(self) -> bool:
        if self.connected:
            await self.disconnect()
        self.initialized = False
        return True

    # ===== 连接处理 =====

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        session: Dict[str, Any] = {
            "logged_in": False,
            "sn": None,
            "sn_len": 7,
            "version": 16,
            "last_heartbeat": None,
            "missed_heartbeats": 0,
        }
        logger.info("YKC 桩接入: %s", peer)
        buffer = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                frames, buffer = self.codec.extract_frames(buffer)
                for frame in frames:
                    try:
                        reply = await self._dispatch(frame, session)
                    except Exception as e:
                        logger.error("YKC 帧处理异常 type=0x%02X: %s", frame.frame_type, e)
                        reply = None
                    if reply is not None:
                        if isinstance(reply, list):
                            for r in reply:
                                writer.write(r.encode())
                        else:
                            writer.write(reply.encode())
                        await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError, OSError) as e:
            logger.info("YKC 连接断开: %s (%s)", peer, e)
        finally:
            if session.get("sn"):
                self._sessions.pop(session["sn"], None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("YKC 连接关闭: %s (sn=%s)", peer, session.get("sn"))

    # ===== 帧分发 =====

    async def _dispatch(self, frame: YKCFrame, session: Dict[str, Any]):
        ftype = frame.frame_type
        if ftype == YKCFrameType.LOGIN:
            return await self._handle_login(frame, session)
        # 登录成功前拒绝业务帧（§5.1: 登录成功后才能进行后续交互）
        if not session.get("logged_in"):
            logger.warning("YKC 拒绝未登录业务帧 type=0x%02X", ftype)
            return None
        if ftype == YKCFrameType.HEARTBEAT:
            return self._handle_heartbeat(frame, session)
        if ftype == YKCFrameType.REALTIME_DATA:
            await self._handle_realtime(frame, session)
            return None
        if ftype == YKCFrameType.TRANSACTION:
            return await self._handle_transaction(frame, session)
        logger.debug("YKC 暂不处理的帧类型: 0x%02X", ftype)
        return None

    async def _handle_login(self, frame: YKCFrame, session: Dict[str, Any]) -> YKCFrame:
        login = decode_login(frame.body)
        sn = login["sn"]
        session.update({
            "sn": sn,
            "sn_len": login["sn_len"],
            "version": login["protocol_version"],
            "logged_in": False,
        })
        ok = await self._authenticate(sn)
        result = YKCLoginResult.SUCCESS if ok else YKCLoginResult.FAILURE
        if ok:
            session["logged_in"] = True
            session["last_heartbeat"] = datetime.now(timezone.utc)
            self._sessions[sn] = session
            # 入网登记：登录通过 → 置 ONLINE（线程池卸载，失败不影响通信）
            try:
                await asyncio.to_thread(mark_device_online, sn)
            except Exception as e:
                logger.warning("YKC 入网登记调度失败 sn=%s: %s", sn, e)
        logger.info(
            "YKC 登录 sn=%s version=V1.%d result=%s",
            sn, login["protocol_version"], "成功" if ok else "失败",
        )
        return YKCFrame(
            seq=frame.seq,
            frame_type=YKCFrameType.LOGIN_ACK,
            body=encode_login_ack(sn, result, login["sn_len"]),
        )

    async def _authenticate(self, sn: str) -> bool:
        """登录鉴权：桩编号须能匹配到已注册 Device。"""
        device = await asyncio.to_thread(find_device_by_sn, sn)
        if device is None:
            logger.warning("YKC 登录鉴权失败：桩编号未注册 sn=%s", sn)
            return False
        return True

    def _handle_heartbeat(self, frame: YKCFrame, session: Dict[str, Any]) -> YKCFrame:
        hb = decode_heartbeat(frame.body, session["sn_len"])
        session["last_heartbeat"] = datetime.now(timezone.utc)
        session["missed_heartbeats"] = 0
        logger.debug("YKC 心跳 sn=%s gun=%d status=0x%02X", hb["sn"], hb["gun_no"], hb["gun_status"])
        return YKCFrame(
            seq=frame.seq,
            frame_type=YKCFrameType.HEARTBEAT_ACK,
            body=encode_heartbeat_ack(hb["sn"], hb["gun_no"], session["sn_len"]),
        )

    async def _handle_realtime(self, frame: YKCFrame, session: Dict[str, Any]) -> None:
        data = decode_realtime(frame.body, session["sn_len"])
        logger.debug("YKC 实时数据 sn=%s gun=%d status=%s", data["sn"], data["gun_no"], data["status_name"])
        await self._normalize_telemetry(data)

    async def _handle_transaction(self, frame: YKCFrame, session: Dict[str, Any]) -> YKCFrame:
        txn = decode_transaction(frame.body, session["sn_len"])
        logger.info(
            "YKC 交易记录 sn=%s gun=%d trade_no=%s energy=%.4f amount=%.4f",
            txn["sn"], txn["gun_no"], txn["trade_no"],
            txn["total_energy"], txn["total_amount"],
        )
        await self._normalize_telemetry({
            "sn": txn["sn"],
            "gun_no": txn["gun_no"],
            "trade_no": txn["trade_no"],
            "type": "transaction",
            "energy": txn["total_energy"],
            "amount": txn["total_amount"],
            "start_time": txn["start_time"],
            "end_time": txn["end_time"],
            "stop_reason": txn["stop_reason"],
        })
        return YKCFrame(
            seq=frame.seq,
            frame_type=YKCFrameType.TRANSACTION_ACK,
            body=encode_transaction_ack(txn["trade_no"]),
        )

    async def _normalize_telemetry(self, data: Dict[str, Any]) -> None:
        """解析后走 parsers/pipeline 归一化。"""
        payload = dict(data)
        payload["device_sn"] = normalize_sn(data.get("sn", ""))
        payload["protocol"] = self.protocol_type
        payload["timestamp"] = datetime.now(timezone.utc)
        if self._pipeline is None:
            return
        try:
            await self._pipeline.execute(payload)
        except Exception as e:
            logger.warning("YKC 遥测归一化失败（不影响通信）: %s", e)

    # ===== DeviceAdapter 接口 =====

    async def read_data(self, device_address: int) -> Dict[str, Any]:
        """返回指定桩的最新会话状态（在线遥测由桩主动上送）。"""
        for sn, session in self._sessions.items():
            if normalize_sn(sn).endswith(format(device_address, "016d")[-6:]) or sn == str(device_address):
                return {
                    "sn": sn,
                    "logged_in": session["logged_in"],
                    "protocol_version": session["version"],
                    "last_heartbeat": session["last_heartbeat"],
                    "timestamp": datetime.now(timezone.utc),
                }
        return {"sn": None, "logged_in": False, "timestamp": datetime.now(timezone.utc)}

    async def write_command(self, device_address: int, command: Dict) -> bool:
        """远程控制帧（0x34 启机/0x36 停机）暂不支持下发到已连桩。"""
        logger.warning("YKC write_command 暂未实现: address=%s command=%s", device_address, command)
        return False

    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """0x13 实时数据硬件故障位（bit1..bit13）。"""
        if len(raw_data) < 2:
            return None
        bits = struct.unpack("<H", raw_data[-2:])[0]
        return format(bits, "016b") if bits else None

    # ===== 状态查询 =====

    def get_online_piles(self) -> Dict[str, Dict[str, Any]]:
        """当前已登录桩列表（SN 已归一化为 16 位）。"""
        return {normalize_sn(sn): {"version": s["version"]} for sn, s in self._sessions.items() if s["logged_in"]}

    async def health_check(self) -> Dict[str, Any]:
        base = await super().health_check()
        base.update({
            "host": self.host,
            "port": self.port,
            "online_piles": len(self.get_online_piles()),
        })
        return base


# ========== 全局单例（供应用生命周期调度，任务卡 9a5d070e） ==========

_global_ykc_adapter: Optional[YKCAdapter] = None


def get_ykc_adapter() -> Optional[YKCAdapter]:
    return _global_ykc_adapter


async def start_ykc_gateway() -> Optional[YKCAdapter]:
    """按 settings 启动 YKC 网关（默认关，云端环境变量 YKC_GATEWAY_ENABLED=true 开）。"""
    global _global_ykc_adapter
    try:
        from app.core.config import settings
    except Exception as e:
        logger.warning("YKC 网关配置读取失败，不启动: %s", e)
        return None
    if not getattr(settings, "YKC_GATEWAY_ENABLED", False):
        logger.info("YKC 网关未启用 (YKC_GATEWAY_ENABLED=false)")
        return None
    adapter = YKCAdapter(
        host=settings.YKC_GATEWAY_HOST,
        port=settings.YKC_GATEWAY_PORT,
    )
    await adapter.initialize()
    ok = await adapter.connect()
    if not ok:
        logger.error("YKC 网关启动失败: %s:%d", adapter.host, adapter.port)
        return None
    _global_ykc_adapter = adapter
    return adapter


async def stop_ykc_gateway() -> None:
    global _global_ykc_adapter
    if _global_ykc_adapter is not None:
        await _global_ykc_adapter.shutdown()
        _global_ykc_adapter = None
