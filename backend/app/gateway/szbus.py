"""
深圳巴士充电桩协议接入适配器 V1.09

依据《智能充电桩(机)与中心运营管理平台对接接口规范（十六进制字节版）》
深圳巴士集团 V1.09（2022-07-01）。

协议特性:
    - 通信模型: 桩主动 TCP 直连平台（平台为 TCP server），长连接
    - 帧格式: FA FB | 总长度(2,LE) | 报序(2,LE) | 版本(1) | 生产商(1) |
              设备ID(8) | 命令码(1) | 数据域(N) | CRC16-CCITT(2,LE)
    - CRC16-CCITT: poly 0x1021, init 0xFFFF, 查表法, 校验从报头到数据域, 小端存放
    - 数值: 小端（低字节在前）, 乘倍率上送
    - 问答式: 接收方必须回复, 响应报序与请求一致
    - 设备ID: 8 字节, hex 字符串去前导零即桩编号(SN)

支持命令（接入范围）:
    - 0x01 签到 / 0x11 签到应答（+ 入网登记 ONLINE）
    - 0x05 心跳 / 0x15 心跳应答（含对时）
    - 0x04 设备状态 / 0x14 应答
    - 0x06 计费模板请求 / 0x16 应答（单时段平价, 费率可配）
    - 0x20 用户鉴权 / 0x30 应答（默认放行, 余额可配）
    - 0x23 充放电操作结果 / 0x33 应答
    - 0x24 充电开始 / 0x34 应答
    - 0x25 充电信息 / 0x35 应答（遥测归一化入库）
    - 0x26 充电结束 / 0x36 应答
    - 0x27 充电账单 / 0x37 应答
    - 0x60 告警 / 0x70 应答
    - 0x12 工作参数设置（签到成功后主动下发, 含对时）
    - 0x31 远程启动 / 0x32 远程停止（write_command 暴露）
"""
import asyncio
import logging
import struct
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .base import DeviceAdapter

logger = logging.getLogger(__name__)


# ========== 帧常量 ==========

FRAME_HEAD = b"\xfa\xfb"
HEADER_LEN = 17   # 报头2+长度2+报序2+版本1+生产商1+设备ID8+命令码1
CRC_LEN = 2
MIN_FRAME_LEN = HEADER_LEN + CRC_LEN  # 19


# ========== CRC16-CCITT (poly 0x1021, init 0xFFFF, 查表法) ==========

def _make_crc_table() -> List[int]:
    table = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        table.append(c)
    return table


_CRC_TABLE = _make_crc_table()


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC_TABLE[((crc >> 8) ^ b) & 0xFF]
    return crc


# ========== CP56Time2a 时标（7字节） ==========

def encode_cp56time2a(dt: datetime) -> bytes:
    ms = int(dt.microsecond / 1000)
    return struct.pack(
        "<H5B",
        ms,
        dt.minute,
        dt.hour,
        dt.day,
        dt.month,
        dt.year - 2000,
    )


def decode_cp56time2a(data: bytes) -> Optional[datetime]:
    """非法日期（如全 0 或桩未对时）返回 None，不抛异常。"""
    try:
        ms, mi, h, d, mo, y = struct.unpack("<H5B", data[:7])
        if not (1 <= mo <= 12 and 1 <= d <= 31 and h <= 23 and mi <= 59):
            return None
        return datetime(2000 + y, mo, d, h, mi, ms // 1000, (ms % 1000) * 1000)
    except Exception:
        return None


# ========== 桩侧对时(卡 b4788b6b) ==========

def _device_now() -> datetime:
    """桩业务时区当前时间(aware)。CP56Time2A 是墙钟字段, 桩按北京墙钟理解,
    容器 UTC 部署时禁用裸 datetime.now()。配置非法时回退 Asia/Shanghai。"""
    try:
        from app.core.config import settings
        tz = ZoneInfo(settings.SZBUS_DEVICE_TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz)


# ========== 设备 SN 映射 ==========

def device_id_to_sn(device_id: bytes) -> str:
    """设备ID(8字节) → 桩编号: hex 字符串去前导零（已验证与库内 SN 一致）。"""
    return device_id.hex().lstrip("0")


def sn_to_device_id(sn: str) -> bytes:
    """桩编号 → 设备ID(8字节): hex 左补零到 16 字符。"""
    return bytes.fromhex(sn.rjust(16, "0"))


# ========== 入网状态钩子（参照 ykc.mark_device_online 模式） ==========

def reconcile_stale_online(active_sessions: dict) -> int:
    """启动对账 (2026-10-10): SIGKILL 重启无 finally, 清理无 session 的 SZBUS 设备陈旧 ONLINE 状态.

    场景: 桩曾在线→后端被 kill -9(session丢失, DB未来得及置offline)→桩此后物理离网
    → devices.status 永久残留 ONLINE. 启动时以网关内存 session 为准对账.
    """
    try:
        from app.models.device import Device
        from app.core.database import SessionLocal

        s = SessionLocal()
        n = 0
        try:
            devices = s.query(Device).all()
            stale = []
            for d in devices:
                proto = getattr(d.protocol_type, "value", d.protocol_type) if d.protocol_type else None
                st = getattr(d.status, "value", d.status) if d.status else None
                if str(proto or "").lower() == "szbus" and str(st or "").lower() == "online" and d.sn not in active_sessions:
                    stale.append(d.sn)
        finally:
            s.close()
        for sn in stale:
            if update_device_status(sn, "offline"):
                n += 1
        if n:
            logger.info("SZBus 启动对账: %d 台无 session 的陈旧在线设备已置 offline", n)
        return n
    except Exception as e:
        logger.warning("SZBus 启动对账失败: %s", e)
        return 0


def find_device_by_sn(sn: str):
    try:
        from app.models.device import Device
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            return session.query(Device).filter(Device.sn == sn).first()
        finally:
            session.close()
    except Exception as e:
        logger.warning("SZBus 设备查询失败 sn=%s: %s", sn, e)
        return None


def mark_device_online(sn: str) -> bool:
    """签到成功 → provision_status ONLINE（幂等, 失败不影响通信）。"""
    if not sn:
        return False
    try:
        from app.models.device import Device, ProvisionStatus
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            device = session.query(Device).filter(Device.sn == sn).first()
            if device is None:
                logger.info("SZBus 入网登记跳过：未匹配到设备 sn=%s", sn)
                return False
            if device.provision_status == ProvisionStatus.ONLINE:
                return True
            device.provision_status = ProvisionStatus.ONLINE
            session.commit()
            logger.info("SZBus 入网登记成功：device=%s → online", sn)
            return True
        finally:
            session.close()
    except Exception as e:
        logger.warning("SZBus 入网登记失败（不影响通信）sn=%s: %s", sn, e)
        return False


# ========== 告警代码表（协议 7.1.1） ==========

ALARM_CODES: Dict[int, str] = {
    1: "交流接触器故障", 2: "急停", 3: "电流表通讯故障", 4: "绝缘监测故障",
    5: "绝缘设备通信故障", 6: "绝缘监测异常", 7: "绝缘监测模块故障", 8: "异常掉电",
    9: "烟雾报警告警", 10: "交流断路器故障", 11: "直流母线输出接触器故障", 12: "直流母线输出熔断器故障",
    13: "充电接口电子锁故障", 14: "充电机风扇故障", 15: "避雷器故障", 16: "控制导引告警(CC1故障)",
    17: "充电桩过温故障", 18: "充电枪过温故障", 19: "充电枪未归位故障", 20: "BMS辅助电源异常",
    21: "预充失败告警", 22: "空闲时直流母线电压异常告警", 23: "整组模块通讯故障", 24: "泄放电路故障",
    25: "电压不匹配,5%误差", 26: "维修门开停止充电", 27: "平台通讯故障", 28: "车辆充电连接器故障",
    29: "车辆侧高压继电器故障", 30: "单模块通讯故障", 31: "充电模块故障",
    101: "BMS通讯超时", 102: "电池反接故障", 103: "充电前电池未连接", 104: "电池组过压",
    105: "电池组连接器故障", 106: "单体电池电压过低", 107: "单体电池电压过高", 108: "SOC异常",
    109: "车辆检测点2电压检测故障", 110: "车辆其他故障", 111: "车辆侧电流过大", 112: "车辆侧电压过高",
    113: "电量不能传输", 114: "电流不匹配", 115: "车辆侧输出连接器过温故障", 116: "BMS元件输出连接器过温",
    117: "绝缘检测前直流接触器外侧电压异常", 118: "充电前电池电压检测过低", 119: "充电前电池电压检测过高",
    120: "动力蓄电池温度过高", 121: "动力蓄电池绝缘状态", 122: "蓄电池充电过流告警", 123: "模块分配板通讯超时",
    124: "充电枪板通讯超时",
    201: "电压过高", 202: "过负荷", 203: "开关跳闸", 204: "变压器温度过高",
    205: "环境温度过高", 206: "烟感报警", 207: "交流下限故障",
    301: "刷卡器通信故障",
}


def alarm_text(code: int) -> str:
    return ALARM_CODES.get(code, f"未知告警(码{code})")


# ========== 入库钩子（同步, 经 asyncio.to_thread 卸载; 失败不影响通信） ==========

def _get_device_row(sn: str):
    try:
        from app.models.device import Device
        from app.core.database import SessionLocal
        session = SessionLocal()
        try:
            return session, session.query(Device).filter(Device.sn == sn).first()
        except Exception:
            session.close()
            raise
    except Exception as e:
        logger.warning("SZBus 设备查询失败 sn=%s: %s", sn, e)
        return None, None


def persist_telemetry(sn: str, data: Dict[str, Any]) -> bool:
    """0x25 充电信息 → telemetry_charger 入库。"""
    session, device = _get_device_row(sn)
    if device is None:
        if session:
            session.close()
        return False
    try:
        try:
            from app.models.telemetry_v2 import TelemetryCharger
        except ImportError:
            from app.models.telemetry import TelemetryCharger
        record = TelemetryCharger(
            device_id=device.id,
            station_id=device.station_id,
            timestamp=datetime.now(timezone.utc),
            region_id="default",
            pod_id="pod-01",
            charger_voltage=data.get("voltage"),
            charger_current=data.get("current"),
            charger_power=data.get("power"),
            charger_soc=data.get("soc"),
            charger_kwh=data.get("energy"),
            gun_status=1 if data.get("work_mode") == 1 else 2,
            gun_temperature=data.get("gun_temp"),
            internal_temperature=data.get("env_temp"),
        )
        session.add(record)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.warning("SZBus 遥测入库失败 sn=%s: %s", sn, e)
        return False
    finally:
        session.close()


def persist_alarm(sn: str, alarm_no: int, code: int, alarm_type: int, dev_no: int) -> bool:
    """0x60 告警 → alarms 入库（1发生 2恢复 3历史）。"""
    session, device = _get_device_row(sn)
    if device is None:
        if session:
            session.close()
        return False
    try:
        from app.models.alarm import Alarm, AlarmLevel
        text = alarm_text(code)
        if alarm_type == 1:
            content = f"桩{sn} 枪{dev_no}: {text}"
            level = AlarmLevel.WARNING
        elif alarm_type == 2:
            content = f"桩{sn} 枪{dev_no}: {text} 已恢复"
            level = AlarmLevel.INFO
        else:
            content = f"桩{sn} 枪{dev_no}: {text} (历史告警补报)"
            level = AlarmLevel.INFO
        alarm = Alarm(
            device_id=device.id,
            station_id=device.station_id,
            alarm_type="szbus",
            level=level,
            content=content,
            fault_code=f"0x{code:04X}",
            fault_source="charger",
            sequence_no=alarm_no,
        )
        session.add(alarm)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.warning("SZBus 告警入库失败 sn=%s: %s", sn, e)
        return False
    finally:
        session.close()


def update_device_status(sn: str, status: str) -> bool:
    """同步 devices.status（online/charging/fault/offline）。"""
    session, device = _get_device_row(sn)
    if device is None:
        if session:
            session.close()
        return False
    try:
        from app.models.device import DeviceStatus, ProvisionStatus
        device.status = DeviceStatus(status)
        if status == "offline":
            # 2026-10-10 修复: ProvisionStatus 枚举无 OFFLINE 成员, 直接访问抛 AttributeError
            # → rollback 连 status 写入一并回滚(陈旧 ONLINE 无法清除的根因)。容错: 无成员则跳过。
            _ps = getattr(ProvisionStatus, "OFFLINE", None)
            if _ps is not None:
                device.provision_status = _ps
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.warning("SZBus 状态同步失败 sn=%s status=%s: %s", sn, status, e)
        return False
    finally:
        session.close()


# ========== 帧编解码 ==========

class SZBusFrame:
    __slots__ = ("seq", "version", "manufacturer", "device_id", "cmd", "body")

    def __init__(self, seq: int, version: int, manufacturer: int,
                 device_id: bytes, cmd: int, body: bytes = b""):
        self.seq = seq
        self.version = version
        self.manufacturer = manufacturer
        self.device_id = device_id
        self.cmd = cmd
        self.body = body

    def encode(self) -> bytes:
        head = FRAME_HEAD + struct.pack(
            "<HHBB8sB",
            MIN_FRAME_LEN + len(self.body),
            self.seq,
            self.version,
            self.manufacturer,
            self.device_id,
            self.cmd,
        )
        crc = crc16_ccitt(head + self.body)
        return head + self.body + struct.pack("<H", crc)

    @classmethod
    def decode(cls, data: bytes) -> "SZBusFrame":
        (total_len,) = struct.unpack("<H", data[2:4])
        (seq, ver, mfr) = struct.unpack("<HBB", data[4:8])
        device_id = data[8:16]
        cmd = data[16]
        body = data[HEADER_LEN:total_len - CRC_LEN]
        return cls(seq, ver, mfr, device_id, cmd, body)


def extract_frames(buffer: bytes) -> Tuple[List[SZBusFrame], bytes]:
    """从流缓冲提取完整帧。坏帧按帧头扫描重同步，不吞后续好帧。"""
    frames: List[SZBusFrame] = []
    buf = buffer
    while True:
        idx = buf.find(FRAME_HEAD)
        if idx < 0:
            return frames, b"" if len(buf) < 2 else buf[-1:]
        if idx > 0:
            buf = buf[idx:]
        if len(buf) < MIN_FRAME_LEN:
            return frames, buf
        (total_len,) = struct.unpack("<H", buf[2:4])
        if total_len < MIN_FRAME_LEN:
            buf = buf[2:]  # 假帧头, 跳过继续扫
            continue
        if len(buf) < total_len:
            return frames, buf
        frame_bytes = buf[:total_len]
        (crc_recv,) = struct.unpack("<H", frame_bytes[-2:])
        if crc16_ccitt(frame_bytes[:-2]) != crc_recv:
            logger.warning("SZBus CRC 校验失败: 收到 0x%04X", crc_recv)
            buf = buf[2:]
            continue
        frames.append(SZBusFrame.decode(frame_bytes))
        buf = buf[total_len:]


# ========== 命令码 ==========

class Cmd:
    # 上行 (桩 → 平台)
    CHECKIN = 0x01            # 签到
    WORK_PARAM_ACK = 0x02     # 工作参数设置响应
    OP_PARAM_ACK = 0x03       # 运营参数设置响应
    STATUS = 0x04             # 设备状态
    HEARTBEAT = 0x05          # 心跳
    BILLING_REQ = 0x06        # 计费模板更新请求
    AUTH = 0x20               # 用户鉴权
    START_ACK = 0x21          # 远程启动响应
    STOP_ACK = 0x22           # 远程停止响应
    OP_RESULT = 0x23          # 充放电操作结果
    CHARGE_START = 0x24       # 充电开始
    CHARGE_INFO = 0x25        # 充电信息
    CHARGE_END = 0x26         # 充电结束
    BILL = 0x27               # 充电账单
    UPGRADE_RESP = 0x41        # 远程升级响应
    UPGRADE_RESULT = 0x42      # 升级结果上报
    ALARM = 0x60              # 告警
    # 下行 (平台 → 桩)
    CHECKIN_ACK = 0x11
    WORK_PARAM = 0x12
    OP_PARAM = 0x13
    STATUS_ACK = 0x14
    HEARTBEAT_ACK = 0x15
    BILLING = 0x16
    AUTH_ACK = 0x30
    UPGRADE = 0x51             # 远程升级(2026-10-10 协议6.1: 版本60B+地址160B+重试1B)
    UPGRADE_RESULT_ACK = 0x52  # 升级结果响应(版本60B)
    START = 0x31
    STOP = 0x32
    OP_RESULT_ACK = 0x33
    CHARGE_START_ACK = 0x34
    CHARGE_INFO_ACK = 0x35
    CHARGE_END_ACK = 0x36
    BILL_ACK = 0x37
    ALARM_ACK = 0x70


# ========== 数据域解析 ==========

def decode_checkin(body: bytes) -> Dict[str, Any]:
    p = 0
    out: Dict[str, Any] = {
        "time": decode_cp56time2a(body[0:7]),
        "last_checkin": decode_cp56time2a(body[7:14]),
        "last_boot": decode_cp56time2a(body[14:21]),
    }
    p = 21
    out["model"] = body[p:p + 32].split(b"\0")[0].decode(errors="replace"); p += 32
    out["device_type"] = body[p]; p += 1          # 1直流 2交流 3交直流 5充放电
    out["hw"] = body[p:p + 32].split(b"\0")[0].decode(errors="replace"); p += 32
    out["sw"] = body[p:p + 32].split(b"\0")[0].decode(errors="replace"); p += 32
    out["total_kw"] = struct.unpack("<H", body[p:p + 2])[0] * 0.1; p += 2
    out["rated_kw"] = struct.unpack("<H", body[p:p + 2])[0] * 0.1; p += 2
    out["gb_standard"] = body[p]; p += 1
    out["offline_mode"] = body[p]; p += 1
    out["vin_mode"] = body[p]; p += 1
    gun_count = body[p]; p += 1
    out["gun_count"] = gun_count
    guns = []
    for _ in range(gun_count):
        g = {
            "interface": body[p],                 # 4=直流带枪线
            "output": body[p + 1],                # 2=直流
            "v_max": struct.unpack("<H", body[p + 2:p + 4])[0] * 0.1,
            "v_min": struct.unpack("<H", body[p + 4:p + 6])[0] * 0.1,
            "aux": body[p + 6],
            "v_rated": struct.unpack("<H", body[p + 7:p + 9])[0] * 0.1,
            "i_rated": (struct.unpack("<H", body[p + 9:p + 11])[0] - 32768) * 0.1,
            "p_rated": struct.unpack("<H", body[p + 11:p + 13])[0] * 0.1,
        }
        guns.append(g)
        p += 13
    out["guns"] = guns
    return out


def _s32(buf: bytes, off: int) -> int:
    return struct.unpack("<i", buf[off:off + 4])[0]


def _u16(buf: bytes, off: int) -> int:
    return struct.unpack("<H", buf[off:off + 2])[0]


def decode_charge_info(body: bytes) -> Dict[str, Any]:
    """0x25 充电信息 → 遥测字段（交流/直流侧自动）。"""
    out: Dict[str, Any] = {
        "trade_no": body[0:32].split(b"\0")[0].decode(errors="replace"),
        "gun_no": body[32],
        "output_type": body[33],     # 1交流 2直流
        "work_mode": body[34],       # 1充电 2放电
        "collect_time": decode_cp56time2a(body[35:42]),
    }
    out["price"] = _s32(body, 42) * 0.0001
    out["service_price"] = _s32(body, 46) * 0.0001
    out["energy_kwh"] = _s32(body, 50) * 0.0001      # 实时消费电量
    out["amount"] = _s32(body, 54) * 0.01            # 实时消费金额
    out["meter_kwh"] = struct.unpack("<Q", body[58:66])[0] * 0.0001  # 电表读数
    out["gun_temp"] = (_u16(body, 66) - 500) * 0.1
    out["env_temp"] = (_u16(body, 68) - 500) * 0.1
    out["guide_v"] = _u16(body, 70) * 0.01
    # 交流区: A/B/C电压(72/74/76) A/B/C电流(78/80/82) 有功(84) 无功(86)
    if out["output_type"] == 1:
        out["voltage"] = _u16(body, 72) * 0.1
        out["current"] = _u16(body, 78) * 0.01
        out["power"] = _u16(body, 84) * 0.1
    else:
        # 直流区: 电压(88) 电流(90,偏移32768) 功率(92)
        out["voltage"] = _u16(body, 88) * 0.1
        out["current"] = (_u16(body, 90) - 32768) * 0.1
        out["power"] = _u16(body, 92) * 0.1
    out["soc"] = body[94]
    out["soh"] = body[95]
    out["bat_temp_min"] = (_u16(body, 96) - 500) * 0.1
    out["bat_temp_max"] = (_u16(body, 98) - 500) * 0.1
    out["cell_v_max"] = _u16(body, 100) * 0.01
    out["cell_v_min"] = _u16(body, 102) * 0.01
    out["charged_min"] = _u16(body, 104)
    out["remain_min"] = _u16(body, 106)
    out["bms_req_v"] = _u16(body, 108) * 0.1
    out["bms_req_i"] = (_u16(body, 110) - 32768) * 0.1
    return out


def decode_charge_start(body: bytes) -> Dict[str, Any]:
    return {
        "user": body[0:32].split(b"\0")[0].decode(errors="replace"),
        "trade_no": body[32:64].split(b"\0")[0].decode(errors="replace"),
        "start_type": body[64],       # 1刷卡 2远程 3VIN 4深圳通
        "work_mode": body[65],        # 1充电 2放电
        "gun_no": body[66],
        "meter_kwh": struct.unpack("<Q", body[67:75])[0] * 0.0001,
        "strategy": body[75],
        "strategy_value": _u16(body, 76),
        "vin": body[78:95].split(b"\0")[0].decode(errors="replace"),
        "soc_start": body[95],
        "bms_code": body[96:104].hex(),
        "bms_ver": body[104:112].split(b"\0")[0].decode(errors="replace"),
        "bat_type": body[112],
        "trade_time": decode_cp56time2a(body[113:120]),
        "charge_time": decode_cp56time2a(body[120:127]),
    }


def decode_charge_end(body: bytes) -> Dict[str, Any]:
    return {
        "user": body[0:32].split(b"\0")[0].decode(errors="replace"),
        "trade_no": body[32:64].split(b"\0")[0].decode(errors="replace"),
        "start_type": body[64],
        "work_mode": body[65],
        "result": body[66],
        "charge_time": decode_cp56time2a(body[67:74]),
        "end_time": decode_cp56time2a(body[74:81]),
        "energy_kwh": _s32(body, 81) * 0.0001,
        "vin": body[85:102].split(b"\0")[0].decode(errors="replace"),
        "soc_start": body[102],
        "soc_end": body[103],
        "gun_no": body[104],
        "meter_start": struct.unpack("<Q", body[105:113])[0] * 0.0001,
        "meter_end": struct.unpack("<Q", body[113:121])[0] * 0.0001,
    }


# ========== 网关适配器 ==========

class SZBusGateway(DeviceAdapter):
    """深圳巴士 V1.09 协议 TCP 接入网关。"""

    protocol_type = "szbus"
    device_type = "charger_szbus"

    def __init__(self, host: str, port: int, *, protocol_type: str = "szbus",
                 electricity_price: float = 0.6, service_price: float = 1.0,
                 balance_threshold: float = 1.0, default_balance: float = 9999.0,
                 **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.port = port
        self.protocol_type = protocol_type
        self.electricity_price = electricity_price      # 元/度
        self.service_price = service_price              # 元/度
        self.balance_threshold = balance_threshold      # 元
        self.default_balance = default_balance          # 元 (鉴权返回余额)
        self._server: Optional[asyncio.AbstractServer] = None
        self._sessions: Dict[str, Dict[str, Any]] = {}  # sn → session
        self._pipeline = None
        self._seq = 0                                    # 平台下行报序自增
        self._watchdog: Optional[asyncio.Task] = None    # 心跳超时清理任务
        # 下发-回读证据链（2026-10-09 丁哥: 校验=读桩上传数据比对下发定值）
        # sn → {dispatch_time, wp_ack:{time,ok}, billing_version, pile_billing_version,
        #        pile_price_report:{time, price, service}}
        self._dispatch_records: Dict[str, Dict[str, Any]] = {}

    # ----- 生命周期 -----

    async def initialize(self) -> bool:
        logger.info("初始化 SZBus(深圳巴士) 网关: %s:%d", self.host, self.port)
        try:
            from app.parsers.pipeline import ParsePipeline
            self._pipeline = ParsePipeline(device_type=self.device_type, protocol=self.protocol_type)
        except Exception as e:
            logger.warning("SZBus 解析管道初始化失败（遥测仅解析不入库）: %s", e)
        return True

    async def connect(self) -> bool:
        if self._server is not None:
            return True
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        # 心跳超时清理：桩断网/TCP半开时回收会话并置 offline（2026-10-09）
        if self._watchdog is None:
            self._watchdog = asyncio.create_task(self._heartbeat_watchdog())
        logger.info("SZBus 网关已监听 %s:%d", self.host, self.port)
        # 启动对账: 清理上次异常退出(SIGKILL)残留的陈旧 ONLINE 状态 (2026-10-10)
        await asyncio.to_thread(reconcile_stale_online, self._sessions)
        return True

    async def _heartbeat_watchdog(self) -> None:
        """每60s扫描会话, 心跳>180s 未更新则断开连接（由 finally 统一置 offline）。"""
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            for sn, sess in list(self._sessions.items()):
                hb = sess.get("last_heartbeat")
                if hb is None:
                    continue
                if (now - hb).total_seconds() > 180:
                    logger.warning("SZBus 心跳超时 sn=%s, 断开回收", sn)
                    writer = sess.get("writer")
                    if writer is not None:
                        try:
                            writer.close()
                        except Exception:
                            pass

    async def disconnect(self) -> bool:
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._sessions.clear()
        return True

    async def shutdown(self) -> bool:
        await self.disconnect()
        return True

    # ----- 连接处理 -----

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        session: Dict[str, Any] = {
            "sn": None, "checked_in": False, "device_id": b"",
            "version": 0x16, "manufacturer": 0x01,
            "last_heartbeat": None, "writer": writer,
        }
        logger.info("SZBus 桩接入: %s", peer)
        buffer = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                frames, buffer = extract_frames(buffer)
                for frame in frames:
                    try:
                        reply = await self._dispatch(frame, session)
                    except Exception as e:
                        logger.error("SZBus 帧处理异常 cmd=0x%02X: %s", frame.cmd, e)
                        reply = None
                    if reply is not None:
                        for r in (reply if isinstance(reply, list) else [reply]):
                            writer.write(r.encode())
                        await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError, OSError) as e:
            logger.info("SZBus 连接断开: %s (%s)", peer, e)
        finally:
            sn = session.get("sn")
            if sn:
                self._sessions.pop(sn, None)
                try:
                    await asyncio.to_thread(update_device_status, sn, "offline")
                except Exception:
                    pass
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("SZBus 连接关闭: %s (sn=%s)", peer, sn)

    # ----- 帧分发 -----

    async def _dispatch(self, frame: SZBusFrame, session: Dict[str, Any]):
        cmd = frame.cmd
        # 未签到仅放行签到（规约4.1④）
        if not session.get("checked_in") and cmd not in (Cmd.CHECKIN,):
            logger.warning("SZBus 丢弃未签到报文 cmd=0x%02X sn=%s", cmd,
                           device_id_to_sn(frame.device_id))
            return None
        if cmd == Cmd.CHECKIN:
            return await self._handle_checkin(frame, session)
        if cmd == Cmd.UPGRADE_RESP:
            # 0x41: 版本60B + 响应码1B (1立刻执行/2稍后执行/3地址无法解析/4版本一致/5不兼容)
            code = frame.body[60] if len(frame.body) > 60 else 0
            rec = session.setdefault("upgrade", {})
            rec["resp_code"] = code
            rec["resp_time"] = _device_now().isoformat()
            logger.info("SZBus 升级响应 sn=%s code=%s(%s)", session.get("sn"), code,
                        {1: "立刻执行", 2: "稍后执行", 3: "地址无法解析", 4: "版本一致", 5: "不兼容"}.get(code, "未知"))
            return None
        if cmd == Cmd.UPGRADE_RESULT:
            # 0x42: 版本60B + 结果1B (1成功/2地址不可达/3账密错/4下载失败/5校验失败/6解压失败/7安装失败/8不兼容)
            code = frame.body[60] if len(frame.body) > 60 else 0
            rec = session.setdefault("upgrade", {})
            rec["result_code"] = code
            rec["result_time"] = _device_now().isoformat()
            logger.info("SZBus 升级结果 sn=%s code=%s(%s)", session.get("sn"), code,
                        {1: "升级成功", 2: "地址不可达", 3: "账密错误", 4: "下载失败", 5: "校验失败", 6: "解压失败", 7: "安装失败", 8: "不兼容"}.get(code, "未知"))
            return self._reply(frame, session, Cmd.UPGRADE_RESULT_ACK, frame.body[:60])
        if cmd == Cmd.HEARTBEAT:
            session["last_heartbeat"] = datetime.now(timezone.utc)
            return self._reply(frame, session, Cmd.HEARTBEAT_ACK,
                               encode_cp56time2a(_device_now()))
        if cmd == Cmd.STATUS:
            # 设备状态应答: 携带平台最新计费模板版本(桩对比不一致会主动 0x06 拉新, 协议原生闭环)
            rec = self._dispatch_records.get(session.get("sn") or "") or {}
            bill_ver = rec.get("billing_version", 0) or 0
            return self._reply(frame, session, Cmd.STATUS_ACK,
                               struct.pack("<HH", bill_ver, 0))
        if cmd == Cmd.BILLING_REQ:
            # 桩上报当前使用的计费模板版本 → 下发回读证据链
            if len(frame.body) >= 5:
                (pile_ver,) = struct.unpack("<I", frame.body[1:5])
                rec = self._dispatch_records.setdefault(session.get("sn") or "", {})
                rec["pile_billing_version"] = pile_ver
            # 优先应答平台配置的计费模板(dispatch 时缓存), 否则单时段平价
            rec = self._dispatch_records.get(session.get("sn") or "") or {}
            billing_body = rec.get("billing_seg") or self._encode_billing()
            return self._reply(frame, session, Cmd.BILLING, billing_body)
        if cmd == Cmd.AUTH:
            return self._reply(frame, session, Cmd.AUTH_ACK,
                               self._encode_auth_ack(frame.body))
        if cmd == Cmd.OP_RESULT:
            user = frame.body[0:32].split(b"\0")[0].decode(errors="replace")
            op_type, result, start_type, work_mode, gun = frame.body[32:37]
            logger.info("SZBus 操作结果 sn=%s user=%s op=%d result=%d gun=%d",
                        session.get("sn"), user, op_type, result, gun)
            ack = frame.body[0:32] + bytes([op_type, gun])
            return self._reply(frame, session, Cmd.OP_RESULT_ACK, ack)
        if cmd == Cmd.CHARGE_START:
            return await self._handle_charge_start(frame, session)
        if cmd == Cmd.CHARGE_INFO:
            return await self._handle_charge_info(frame, session)
        if cmd == Cmd.CHARGE_END:
            return await self._handle_charge_end(frame, session)
        if cmd == Cmd.BILL:
            return await self._handle_bill(frame, session)
        if cmd == Cmd.ALARM:
            return await self._handle_alarm(frame, session)
        if cmd in (Cmd.WORK_PARAM_ACK, Cmd.OP_PARAM_ACK, Cmd.START_ACK, Cmd.STOP_ACK):
            logger.info("SZBus 下行应答 cmd=0x%02X sn=%s body=%s", cmd,
                        session.get("sn"), frame.body.hex()[:64])
            if cmd == Cmd.WORK_PARAM_ACK and len(frame.body) >= 7:
                # 0x02: 对时/保活/超时/信息上报/离线/VIN/密码 逐项 0x01=成功
                ok = all(b == 1 for b in frame.body[:7])
                rec = self._dispatch_records.setdefault(session.get("sn") or "", {})
                rec["wp_ack"] = {"time": datetime.now(timezone.utc), "ok": ok,
                                  "detail": list(frame.body[:7])}
                logger.info("SZBus 工作参数桩端确认 sn=%s 全部成功=%s", session.get("sn"), ok)
            return None
        logger.debug("SZBus 暂不处理的命令码: 0x%02X", cmd)
        return None

    def _reply(self, req: SZBusFrame, session: Dict[str, Any],
               cmd: int, body: bytes) -> SZBusFrame:
        """响应帧：报序与请求一致（规约1.3）。"""
        return SZBusFrame(req.seq, req.version, req.manufacturer,
                          req.device_id, cmd, body)

    # ----- 报文处理 -----

    async def _handle_checkin(self, frame: SZBusFrame, session: Dict[str, Any]):
        sn = device_id_to_sn(frame.device_id)
        info = decode_checkin(frame.body)
        session.update({
            "sn": sn, "device_id": frame.device_id, "checked_in": False,
            "version": frame.version, "manufacturer": frame.manufacturer,
        })
        device = await asyncio.to_thread(find_device_by_sn, sn)
        ok = device is not None
        session["checked_in"] = ok
        result = 1 if ok else 3  # 1成功 3未录入系统
        # 签到应答: 结果1 + 服务费率4 + 电价4 + 余额阈值2
        body = (bytes([result])
                + struct.pack("<i", int(self.service_price * 10000))
                + struct.pack("<i", int(self.electricity_price * 10000))
                + struct.pack("<H", int(self.balance_threshold * 100)))
        reply = self._reply(frame, session, Cmd.CHECKIN_ACK, body)
        logger.info("SZBus 签到 sn=%s model=%s sw=%s 枪数=%d 版本=%d.%d → %s",
                    sn, info.get("model"), info.get("sw"), info.get("gun_count", 0),
                    frame.version >> 4, frame.version & 0xF,
                    "成功" if ok else "失败(未录入)")
        if ok:
            self._sessions[sn] = session
            session["last_heartbeat"] = datetime.now(timezone.utc)
            try:
                await asyncio.to_thread(mark_device_online, sn)
                await asyncio.to_thread(update_device_status, sn, "online")
            except Exception as e:
                logger.warning("SZBus 入网登记调度失败 sn=%s: %s", sn, e)
            # 签到成功后下发工作参数(0x12)：对时 + 保活30s×3 + 信息上报30s
            return [reply, self._make_work_param(session)]
        return reply

    def _make_work_param(self, session: Dict[str, Any]) -> SZBusFrame:
        self._seq = (self._seq + 1) & 0xFFFF
        body = (encode_cp56time2a(_device_now())  # 当前时间(对时, 桩业务时区)
                + bytes([30, 3, 30])               # 保活间隔/超时次数/信息上报间隔
                + bytes([1, 1])                    # 离线/VIN: 保持原有状态
                + b"\0" * 32 + b"\0" * 32 + b"\0" * 32)  # 管理员/操作密码/预留
        return SZBusFrame(self._seq, session["version"], session["manufacturer"],
                          session["device_id"], Cmd.WORK_PARAM, body)

    def _encode_billing(self) -> bytes:
        """0x16 计费模板: 单时段全平（00:00-24:00）。"""
        return (bytes([1])                          # 模板类型: 基础
                + struct.pack("<I", 1)              # 版本
                + bytes([1])                        # 时段数量
                + bytes([3])                        # 平
                + bytes([0x00, 0x00, 0x24, 0x00])   # 00:00-24:00 BCD
                + struct.pack("<i", int(self.electricity_price * 10000))
                + struct.pack("<i", int(self.service_price * 10000)))

    def _encode_auth_ack(self, body: bytes) -> bytes:
        user32, auth_type = body[0:32], body[32]
        user = user32.split(b"\0")[0].decode(errors="replace")
        logger.info("SZBus 用户鉴权 user=%s type=%d → 放行", user, auth_type)
        return (user32 + bytes([auth_type])
                + bytes([1])                        # 鉴权成功
                + struct.pack("<i", int(self.default_balance * 100))
                + bytes([1])                        # 普通匹配
                + b"\0" * 17                        # VIN
                + struct.pack("<I", 0)              # 无私有模板
                + b"\0" * 28)

    async def _handle_charge_start(self, frame, session):
        d = decode_charge_start(frame.body)
        logger.info("SZBus 充电开始 sn=%s trade=%s gun=%d vin=%s soc=%d",
                    session.get("sn"), d["trade_no"], d["gun_no"], d["vin"], d["soc_start"])
        sn = session.get("sn")
        if sn:
            try:
                await asyncio.to_thread(update_device_status, sn, "charging")
            except Exception:
                pass
        await self._normalize_telemetry(session.get("sn"), {
            "type": "charge_start", "gun_no": d["gun_no"],
            "trade_no": d["trade_no"], "user": d["user"], "vin": d["vin"],
            "soc": d["soc_start"], "energy": d["meter_kwh"],
        })
        ack = frame.body[0:32] + frame.body[32:64] + bytes([d["gun_no"]])
        return self._reply(frame, session, Cmd.CHARGE_START_ACK, ack)

    async def _handle_charge_info(self, frame, session):
        d = decode_charge_info(frame.body)
        logger.debug("SZBus 充电信息 sn=%s gun=%d P=%.1fkW V=%.1f I=%.1f SOC=%d%%",
                     session.get("sn"), d["gun_no"], d["power"], d["voltage"],
                     d["current"], d["soc"])
        # 0x25 → telemetry_charger 直接入库（2026-10-09: pipeline 无入库能力, 改为自写库）
        sn = session.get("sn")
        if sn:
            # 桩端实际执行电价 → 下发回读证据链（计费模板验证）
            rec = self._dispatch_records.setdefault(sn, {})
            rec["pile_price_report"] = {"time": datetime.now(timezone.utc),
                                        "price": d["price"], "service": d["service_price"]}
            payload = {"voltage": d["voltage"], "current": d["current"],
                       "power": d["power"], "soc": float(d["soc"]),
                       "energy": d["energy_kwh"], "work_mode": d["work_mode"],
                       "gun_temp": d["gun_temp"], "env_temp": d["env_temp"]}
            try:
                await asyncio.to_thread(persist_telemetry, sn, payload)
            except Exception as e:
                logger.warning("SZBus 遥测入库调度失败 sn=%s: %s", sn, e)
        ack = frame.body[0:32] + bytes([d["gun_no"]])
        return self._reply(frame, session, Cmd.CHARGE_INFO_ACK, ack)

    async def _handle_charge_end(self, frame, session):
        d = decode_charge_end(frame.body)
        logger.info("SZBus 充电结束 sn=%s trade=%s gun=%d result=%d 电量=%.4fkWh SOC %d→%d",
                    session.get("sn"), d["trade_no"], d["gun_no"], d["result"],
                    d["energy_kwh"], d["soc_start"], d["soc_end"])
        sn = session.get("sn")
        if sn:
            try:
                await asyncio.to_thread(update_device_status, sn, "online")
            except Exception:
                pass
        await self._normalize_telemetry(session.get("sn"), {
            "type": "charge_end", "gun_no": d["gun_no"],
            "trade_no": d["trade_no"], "user": d["user"],
            "energy": d["energy_kwh"], "soc": d["soc_end"],
            "meter": d["meter_end"], "status": "IDLE",
        })
        ack = frame.body[0:32] + frame.body[32:64] + bytes([d["gun_no"]])
        return self._reply(frame, session, Cmd.CHARGE_END_ACK, ack)

    async def _handle_bill(self, frame, session):
        user = frame.body[0:32].split(b"\0")[0].decode(errors="replace")
        trade = frame.body[32:64].split(b"\0")[0].decode(errors="replace")
        total_kwh = _s32(frame.body, 78) * 0.0001
        amount = _s32(frame.body, 94) * 0.01
        logger.info("SZBus 账单 sn=%s trade=%s 电量=%.4fkWh 金额=%.2f元",
                    session.get("sn"), trade, total_kwh, amount)
        await self._normalize_telemetry(session.get("sn"), {
            "type": "bill", "trade_no": trade, "user": user,
            "energy": total_kwh, "amount": amount,
        })
        return self._reply(frame, session, Cmd.BILL_ACK,
                           frame.body[0:32] + frame.body[32:64])

    async def _handle_alarm(self, frame, session):
        (alarm_no,) = struct.unpack("<I", frame.body[0:4])
        (alarm_code,) = struct.unpack("<H", frame.body[6:8])
        dev_no, alarm_type = frame.body[4], frame.body[5]
        logger.warning("SZBus 告警 sn=%s 序号=%d 设备=%d 类型=%d(1发生2恢复3历史) 码=%d(%s)",
                       session.get("sn"), alarm_no, dev_no, alarm_type, alarm_code,
                       alarm_text(alarm_code))
        sn = session.get("sn")
        if sn:
            try:
                await asyncio.to_thread(persist_alarm, sn, alarm_no, alarm_code, alarm_type, dev_no)
            except Exception as e:
                logger.warning("SZBus 告警入库调度失败 sn=%s: %s", sn, e)
        return self._reply(frame, session, Cmd.ALARM_ACK,
                           frame.body[0:4] + frame.body[6:8])

    async def _normalize_telemetry(self, sn: Optional[str], data: Dict[str, Any]) -> None:
        if not sn or self._pipeline is None:
            return
        payload = dict(data)
        payload["device_sn"] = sn
        payload["protocol"] = self.protocol_type
        payload["timestamp"] = datetime.now(timezone.utc)
        try:
            await self._pipeline.execute(payload)
        except Exception as e:
            logger.warning("SZBus 遥测归一化失败（不影响通信）: %s", e)

    # ----- 下行控制（远程启停） -----

    async def _send_cmd(self, sn: str, cmd: int, body: bytes) -> bool:
        session = self._sessions.get(sn)
        if not session or not session.get("checked_in"):
            logger.warning("SZBus 下行失败：桩不在线 sn=%s", sn)
            return False
        self._seq = (self._seq + 1) & 0xFFFF
        frame = SZBusFrame(self._seq, session["version"], session["manufacturer"],
                           session["device_id"], cmd, body)
        writer = session.get("writer")
        if writer is None:
            return False
        writer.write(frame.encode())
        await writer.drain()
        return True

    async def remote_upgrade(self, sn: str, version: str, url: str, retries: int = 1) -> bool:
        """远程升级 0x51 (协议6.1, 2026-10-10): 版本60B + 下载地址160B + 重试次数1B.

        桩比对版本→落后则按URL下载(FTP/HTTP, zip压缩+MD5)→充电中稍后执行→结果经0x42上报
        """
        try:
            body = (version.encode("ascii", "ignore").ljust(60, b"\0")[:60]
                    + url.encode("ascii", "ignore").ljust(160, b"\0")[:160]
                    + bytes([retries]))
        except Exception as e:
            logger.error("SZBus 升级帧构造失败 sn=%s: %s", sn, e)
            return False
        ok = await self._send_cmd(sn, Cmd.UPGRADE, body)
        if ok:
            rec = self._sessions.get(sn, {}).setdefault("upgrade", {})
            rec["dispatched"] = True
            rec["dispatch_version"] = version
            rec["dispatch_time"] = _device_now().isoformat()
            logger.info("SZBus 升级已下发 sn=%s version=%s url=%s", sn, version, url)
        return ok

    async def remote_start(self, sn: str, user: str, gun_no: int = 1,
                           strategy: int = 0, strategy_value: int = 0) -> bool:
        body = (user.encode().ljust(32, b"\0") + bytes([gun_no])
                + struct.pack("<i", int(self.default_balance * 100))
                + bytes([1])                        # 立即充电
                + b"\0" * 7                         # 预约时间
                + bytes([strategy]) + struct.pack("<H", strategy_value)
                + bytes([1]) + b"\0" * 17 + struct.pack("<I", 0) + b"\0" * 28)
        return await self._send_cmd(sn, Cmd.START, body)

    async def remote_stop(self, sn: str, user: str, gun_no: int = 1) -> bool:
        body = (user.encode().ljust(32, b"\0") + bytes([gun_no])
                + bytes([2]) + b"\0" * 32)          # 主动停止
        return await self._send_cmd(sn, Cmd.STOP, body)

    # ----- DeviceAdapter 接口 -----

    async def read_data(self, device_address: int) -> Dict[str, Any]:
        for sn, session in self._sessions.items():
            if sn == str(device_address) or sn.endswith(str(device_address)[-6:]):
                return {
                    "sn": sn, "checked_in": session["checked_in"],
                    "last_heartbeat": session["last_heartbeat"],
                    "timestamp": datetime.now(timezone.utc),
                }
        return {"sn": None, "checked_in": False, "timestamp": datetime.now(timezone.utc)}

    async def write_command(self, device_address: int, command: Dict) -> bool:
        sn = str(device_address)
        action = (command or {}).get("action")
        if action == "start":
            return await self.remote_start(sn, command.get("user", "platform"),
                                           int(command.get("gun_no", 1)),
                                           int(command.get("strategy", 0)),
                                           int(command.get("strategy_value", 0)))
        if action == "stop":
            return await self.remote_stop(sn, command.get("user", "platform"),
                                          int(command.get("gun_no", 1)))
        logger.warning("SZBus 未知下行命令: %s", action)
        return False

    def parse_fault_code(self, raw_data: bytes) -> Optional[str]:
        """0x60 告警码（交直流充电桩故障代码表, 协议 7.1.1）。"""
        if len(raw_data) < 2:
            return None
        (code,) = struct.unpack("<H", raw_data[:2])
        return format(code, "04d") if code else None


# ========== 模块级生命周期（参照 ykc.py） ==========

_gateway: Optional[SZBusGateway] = None


async def start_szbus_gateway() -> bool:
    global _gateway
    if _gateway is not None:
        return True
    try:
        from app.core.config import settings
    except Exception as e:
        logger.warning("SZBus 读取配置失败: %s", e)
        return False
    _gateway = SZBusGateway(
        host=settings.SZBUS_GATEWAY_HOST,
        port=settings.SZBUS_GATEWAY_PORT,
        electricity_price=getattr(settings, "SZBUS_ELECTRICITY_PRICE", 0.6),
        service_price=getattr(settings, "SZBUS_SERVICE_PRICE", 1.0),
        balance_threshold=getattr(settings, "SZBUS_BALANCE_THRESHOLD", 1.0),
        default_balance=getattr(settings, "SZBUS_DEFAULT_BALANCE", 9999.0),
    )
    await _gateway.initialize()
    await _gateway.connect()
    return True


async def stop_szbus_gateway() -> None:
    global _gateway
    if _gateway is not None:
        await _gateway.shutdown()
        _gateway = None
