"""
SZBus 深圳巴士 V1.09 协议充电桩模拟器

模拟一台直流双枪充电桩: 签到 → 心跳保活 → 可选充电全流程
(0x24 开始 → 周期 0x25 充电信息 → 0x26 结束 → 0x27 账单)。
支持响应平台下行 0x12 工作参数 / 0x31 远程启动 / 0x32 远程停止。

用法:
    python -m app.services.szbus_simulator --host 127.0.0.1 --port 8767 \
        --sn 13800000100001 --charge

依赖 app.gateway.szbus 的帧编解码（协议同源, 双向互测）。
"""
import argparse
import asyncio
import random
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.gateway.szbus import (  # noqa: E402
    Cmd, SZBusFrame, encode_cp56time2a, extract_frames, sn_to_device_id,
)


class SZBusPileSimulator:
    """模拟桩: TCP client, 问答回合制。"""

    def __init__(self, host: str, port: int, sn: str, *, guns: int = 2,
                 model: str = "SDEE_DC_CHARGER", sw: str = "SIM-V1.09"):
        self.host = host
        self.port = port
        self.sn = sn
        self.device_id = sn_to_device_id(sn)
        self.guns = guns
        self.model = model
        self.sw = sw
        self.seq = 0
        self.charging = False
        self.soc = 42
        self.meter = 1234.5
        self.energy = 0.0
        self.trade_no = ""
        self.user = "SIM-USER-001"
        self.exec_price = 0.6  # 桩端执行电价(收到平台0x16计费模板后更新, 用于定值回读验证)

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFFFF
        return self.seq

    def _frame(self, cmd: int, body: bytes) -> SZBusFrame:
        return SZBusFrame(self._next_seq(), 0x16, 0x01, self.device_id, cmd, body)

    # ----- 报文构造 -----

    def build_checkin(self) -> SZBusFrame:
        now = encode_cp56time2a(datetime.now())
        gun_block = b""
        for _ in range(self.guns):
            gun_block += (bytes([4, 2])                      # 直流接口/直流输出
                          + struct.pack("<HH", 7500, 2000)   # 最高750V 最低200V
                          + bytes([3])                       # 辅源自适应
                          + struct.pack("<HHH", 5000, 30000, 12000)  # 500V/300A/120kW
                          )
        body = (now + now + now
                + self.model.encode().ljust(32, b"\0")
                + bytes([1])                                  # 直流
                + "SIM-HW-GB2".encode().ljust(32, b"\0")
                + self.sw.encode().ljust(32, b"\0")
                + struct.pack("<HH", 1200, 1200)              # 总/额定 120kW
                + bytes([2, 1, 1, self.guns])                 # 国标2015/离线/VIN/枪数
                + gun_block + b"\0" * 32)
        return self._frame(Cmd.CHECKIN, body)

    def build_heartbeat(self) -> SZBusFrame:
        return self._frame(Cmd.HEARTBEAT, encode_cp56time2a(datetime.now()))

    def build_charge_start(self) -> SZBusFrame:
        self.trade_no = (self.sn + datetime.now().strftime("%y%m%d%H%M%S")
                         + "0001")
        body = (self.user.encode().ljust(32, b"\0")
                + self.trade_no.encode().ljust(32, b"\0")
                + bytes([2, 1, 1])                            # 远程/充电/1枪
                + struct.pack("<Q", int(self.meter * 10000))
                + bytes([0]) + struct.pack("<H", 0)           # 自然充满
                + b"\0" * 17 + bytes([self.soc])
                + b"\0" * 8 + b"\0" * 8 + bytes([3])          # BMS码/版本/磷酸铁锂
                + encode_cp56time2a(datetime.now())
                + encode_cp56time2a(datetime.now()))
        return self._frame(Cmd.CHARGE_START, body)

    def build_charge_info(self) -> SZBusFrame:
        v = 400 + random.uniform(-5, 5)
        i = 80 + random.uniform(-5, 5)
        p = v * i / 1000
        self.energy += p * 30 / 3600                          # 30s一报
        self.meter += p * 30 / 3600
        if random.random() < 0.3:
            self.soc = min(100, self.soc + 1)
        body = (self.trade_no.encode().ljust(32, b"\0")
                + bytes([1, 2, 1])                            # 1枪/直流/充电
                + encode_cp56time2a(datetime.now())
                + struct.pack("<ii", int(self.exec_price * 10000), 10000)  # 桩端执行电价/服务费
                + struct.pack("<ii", int(self.energy * 10000), 100)  # 电量/金额
                + struct.pack("<Q", int(self.meter * 10000))
                + struct.pack("<HH", 350 + 500, 300 + 500)    # 枪温/环温(偏移500)
                + struct.pack("<H", 1200)                     # 导引电压
                + b"\0" * 16                                  # 交流区16字节(A/B/C电压电流+有功无功, 直流桩填0)
                + struct.pack("<HHH", int(v * 10),
                              int(i * 10) + 32768, int(p * 10))
                + bytes([self.soc, 98])                       # SOC/SOH
                + struct.pack("<HH", 250 + 500, 350 + 500)    # 电池温度min/max
                + struct.pack("<HH", 365, 355)                # 单体电压
                + struct.pack("<HH", 30, 90)                  # 已充/剩余分钟
                + struct.pack("<HH", int(v * 10), int(i * 10) + 32768)  # BMS需求
                + b"\0" * 28)
        return self._frame(Cmd.CHARGE_INFO, body)

    def build_charge_end(self) -> SZBusFrame:
        start = datetime.now() - timedelta(minutes=42)
        body = (self.user.encode().ljust(32, b"\0")
                + self.trade_no.encode().ljust(32, b"\0")
                + bytes([2, 1, 3])                            # 远程/充电/充满
                + encode_cp56time2a(start)
                + encode_cp56time2a(datetime.now())
                + struct.pack("<i", int(self.energy * 10000))
                + b"\0" * 17
                + bytes([42, self.soc, 1])                    # 起始SOC/结束SOC/枪号
                + struct.pack("<QQ", int((self.meter - self.energy) * 10000),
                              int(self.meter * 10000)))
        return self._frame(Cmd.CHARGE_END, body)

    def build_bill(self) -> SZBusFrame:
        amount = self.energy * 1.6
        body = (self.user.encode().ljust(32, b"\0")
                + self.trade_no.encode().ljust(32, b"\0")
                + bytes([2, 1])                               # 远程/充电
                + encode_cp56time2a(datetime.now())
                + encode_cp56time2a(datetime.now())
                + bytes([1]) + b"\0" * 20                     # 扣费成功/流水号
                + struct.pack("<i", int(self.energy * 10000))
                + struct.pack("<iiii", int(amount * 100), 999900,
                              int(amount * 0.4 * 100), int(amount * 0.6 * 100))
                + bytes([1])                                  # 1时段
                + bytes([3])
                + encode_cp56time2a(datetime.now() - timedelta(hours=1))
                + encode_cp56time2a(datetime.now())
                + struct.pack("<ii", 6000, 10000)
                + struct.pack("<i", int(self.energy * 10000))
                + struct.pack("<ii", int(amount * 0.4 * 100), int(amount * 0.6 * 100)))
        return self._frame(Cmd.BILL, body)

    # ----- 主循环 -----

    async def run(self, charge: bool, duration: float = 0):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        print(f"[SIM] 已连接 {self.host}:{self.port} SN={self.sn}")

        async def send(frame: SZBusFrame):
            writer.write(frame.encode())
            await writer.drain()
            print(f"[SIM] → 0x{frame.cmd:02X} seq={frame.seq} len={len(frame.body)}")

        async def recv() -> SZBusFrame:
            data = await reader.read(4096)
            frames, _ = extract_frames(data)
            for f in frames:
                print(f"[SIM] ← 0x{f.cmd:02X} seq={f.seq} body={f.body[:12].hex()}...")
            return frames[0] if frames else None

        await send(self.build_checkin())
        ack = await recv()
        if ack is None or ack.cmd != Cmd.CHECKIN_ACK or ack.body[0] != 1:
            print("[SIM] 签到失败, 退出")
            writer.close()
            return
        print("[SIM] 签到成功 ✓")

        started = datetime.now()
        charged_once = False
        while duration == 0 or (datetime.now() - started).total_seconds() < duration:
            await asyncio.sleep(1)
            # 处理下行
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=0.1)
                frames, _ = extract_frames(data) if data else ([], b"")
                for f in frames:
                    print(f"[SIM] ← 下行 0x{f.cmd:02X} seq={f.seq}")
                    if f.cmd == Cmd.WORK_PARAM:
                        await send(self._frame(Cmd.WORK_PARAM_ACK, bytes([1] * 7)))
                    elif f.cmd == Cmd.BILLING:
                        # 采用平台计费模板: 取第一时段电价作为桩端执行电价(定值回读验证)
                        try:
                            n = f.body[6]
                            if n >= 1:
                                (price,) = struct.unpack("<i", f.body[11:15])
                                self.exec_price = price / 10000
                                print(f"[SIM] 已采用计费模板: {self.exec_price} 元/度 ({n}时段)")
                        except Exception as e:
                            print(f"[SIM] 计费模板解析失败: {e}")
                    elif f.cmd == Cmd.START:
                        self.charging = True
                        await send(self._frame(Cmd.START_ACK,
                                               self.user.encode().ljust(32, b"\0") + bytes([1, 1])))
                        await send(self._frame(Cmd.OP_RESULT,
                                               self.user.encode().ljust(32, b"\0")
                                               + bytes([1, 1, 2, 1, 1, 1])))
                        await send(self.build_charge_start())
                    elif f.cmd == Cmd.STOP:
                        self.charging = False
                        await send(self._frame(Cmd.STOP_ACK,
                                               self.user.encode().ljust(32, b"\0")
                                               + bytes([1, 1, 1]) + self.trade_no.encode().ljust(32, b"\0")))
                        await send(self.build_charge_end())
                        await send(self.build_bill())
            except asyncio.TimeoutError:
                pass
            # 周期任务: 心跳5s / 充电信息30s
            el = (datetime.now() - started).total_seconds()
            if int(el) % 5 == 0:
                await send(self.build_heartbeat())
                await asyncio.sleep(0.2)
                try:
                    await asyncio.wait_for(recv(), timeout=1)
                except asyncio.TimeoutError:
                    pass
            if charge and self.charging and int(el) % 30 == 0 and int(el) > 0:
                await send(self.build_charge_info())
                try:
                    await asyncio.wait_for(recv(), timeout=1)
                except asyncio.TimeoutError:
                    pass
            if charge and not self.charging and not charged_once and int(el) > 3:
                # 自演示: 连上3秒后自动开始充电
                self.charging = True
                charged_once = True
                await send(self._frame(Cmd.OP_RESULT,
                                       self.user.encode().ljust(32, b"\0")
                                       + bytes([1, 1, 2, 1, 1, 1])))
                await send(self.build_charge_start())
            if charge and self.charging and self.soc >= 100:
                self.charging = False
                await send(self.build_charge_end())
                await send(self.build_bill())
                print("[SIM] 充满结束 ✓")
        writer.close()
        print("[SIM] 退出")


async def main():
    ap = argparse.ArgumentParser(description="SZBus 深圳巴士协议模拟桩")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--sn", default="13800000100001")
    ap.add_argument("--charge", action="store_true", help="自动演示充电流程")
    ap.add_argument("--duration", type=float, default=0, help="运行秒数, 0=直到Ctrl+C")
    args = ap.parse_args()
    sim = SZBusPileSimulator(args.host, args.port, args.sn)
    await sim.run(args.charge, args.duration)


if __name__ == "__main__":
    asyncio.run(main())
