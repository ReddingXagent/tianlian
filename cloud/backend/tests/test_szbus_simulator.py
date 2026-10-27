"""SZBus 深圳巴士协议模拟器测试: 帧构造/序号/计费编码/run 主循环。"""
import asyncio
import struct

import pytest

from app.gateway.szbus import Cmd, FRAME_HEAD, MIN_FRAME_LEN, crc16_ccitt
from app.services.szbus_simulator import SZBusPileSimulator

SN = "13800000100001"


def make_sim(**kw):
    return SZBusPileSimulator("127.0.0.1", 8767, SN, **kw)


def assert_frame_wire(sim_frame, cmd, body):
    """逐字节验证线格式: 帧头/长度域/头字段/CRC。"""
    assert sim_frame.cmd == cmd
    assert sim_frame.body == body
    assert sim_frame.version == 0x16
    assert sim_frame.manufacturer == 0x01
    raw = sim_frame.encode()
    assert raw[:2] == FRAME_HEAD
    (total_len,) = struct.unpack("<H", raw[2:4])
    assert total_len == MIN_FRAME_LEN + len(body)
    (seq, ver, mfr) = struct.unpack("<HBB", raw[4:8])
    assert (seq, ver, mfr) == (sim_frame.seq, 0x16, 0x01)
    assert raw[8:16] == sim_frame.device_id
    assert raw[16] == cmd
    assert raw[17:17 + len(body)] == body
    (crc,) = struct.unpack("<H", raw[-2:])
    assert crc == crc16_ccitt(raw[:-2])


# ----- __init__ / _next_seq / _frame -----

def test_init_params_and_defaults():
    sim = make_sim()
    assert sim.host == "127.0.0.1" and sim.port == 8767 and sim.sn == SN
    assert sim.device_id == bytes.fromhex(SN.rjust(16, "0"))
    assert (sim.guns, sim.model, sim.sw) == (2, "SDEE_DC_CHARGER", "SIM-V1.09")
    assert sim.seq == 0 and not sim.charging and sim.soc == 42
    assert sim.meter == 1234.5 and sim.energy == 0.0
    assert sim.user == "SIM-USER-001" and sim.exec_price == 0.6


def test_init_override_kwargs():
    sim = make_sim(guns=4, model="M1", sw="SW-9")
    assert (sim.guns, sim.model, sim.sw) == (4, "M1", "SW-9")
    assert sim.device_id == bytes.fromhex(SN.rjust(16, "0"))


@pytest.mark.parametrize("sn", [SN, "1", "FFFFFFFFFFFFFFFF"])
def test_sn_to_device_id_roundtrip(sn):
    sim = SZBusPileSimulator("h", 1, sn)
    assert len(sim.device_id) == 8
    assert sim.device_id.hex().lstrip("0") == sn.lstrip("0").lower()


def test_next_seq_increments():
    sim = make_sim()
    assert sim._next_seq() == 1
    assert sim._next_seq() == 2
    assert sim.seq == 2


def test_next_seq_wraparound():
    sim = make_sim()
    sim.seq = 0xFFFE
    assert sim._next_seq() == 0xFFFF
    assert sim._next_seq() == 0  # 回绕
    assert sim._next_seq() == 1


def test_frame_uses_next_seq_and_device_id():
    sim = make_sim()
    f = sim._frame(Cmd.HEARTBEAT, b"xy")
    assert_frame_wire(f, Cmd.HEARTBEAT, b"xy")
    assert f.seq == 1 and sim.seq == 1


# ----- 六类帧 -----

def test_build_checkin_layout():
    sim = make_sim()
    f = sim.build_checkin()
    body = f.body
    # 3×7 时标 + 型号32 + 直流1 + 硬件32 + 软件32 + 功率4 + 协议4 + 枪块13×2 + 32
    assert len(body) == 21 + 32 + 1 + 32 + 32 + 4 + 4 + 13 * 2 + 32
    assert f.cmd == Cmd.CHECKIN
    assert body[21:21 + len(sim.model)] == sim.model.encode()
    assert body[21 + len(sim.model):53] == b"\0" * (32 - len(sim.model))
    assert body[53] == 1                                    # 直流
    assert body[86:86 + len(sim.sw)] == sim.sw.encode()
    assert struct.unpack("<HH", body[118:122]) == (1200, 1200)
    assert body[122:126] == bytes([2, 1, 1, 2])             # 国标/离线/VIN/2枪
    gun = body[126:139]
    assert gun[:2] == bytes([4, 2])
    assert struct.unpack("<HH", gun[2:6]) == (7500, 2000)
    assert gun[6] == 3
    assert struct.unpack("<HHH", gun[7:13]) == (5000, 30000, 12000)
    assert body[152:] == b"\0" * 32
    assert_frame_wire(f, Cmd.CHECKIN, body)


def test_build_checkin_guns_variable():
    f = make_sim(guns=4).build_checkin()
    assert f.body[125] == 4
    assert len(f.body) == 21 + 32 + 1 + 32 + 32 + 4 + 4 + 13 * 4 + 32


def test_build_heartbeat():
    sim = make_sim()
    f = sim.build_heartbeat()
    assert f.cmd == Cmd.HEARTBEAT
    assert len(f.body) == 7                      # CP56Time2a
    now = struct.unpack("<H5B", f.body)
    assert now[1] <= 59 and now[2] <= 23 and 1 <= now[3] <= 31  # 分/时/日
    assert_frame_wire(f, Cmd.HEARTBEAT, f.body)


def test_build_charge_start_fields():
    sim = make_sim()
    f = sim.build_charge_start()
    body = f.body
    assert f.cmd == Cmd.CHARGE_START
    assert body[0:32].rstrip(b"\0") == sim.user.encode()
    assert sim.trade_no.startswith(SN) and sim.trade_no.endswith("0001")
    assert len(sim.trade_no) == len(SN) + 12 + 4      # SN + %y%m%d%H%M%S + 枪流水
    assert body[32:64].rstrip(b"\0") == sim.trade_no.encode()
    assert body[64:67] == bytes([2, 1, 1])       # 远程/充电/1枪
    assert struct.unpack("<Q", body[67:75])[0] == int(1234.5 * 10000)
    assert body[75:78] == bytes([0]) + struct.pack("<H", 0)   # 自然充满
    assert body[95] == 42                        # 起始 SOC
    assert body[96 + 16] == 3                    # 磷酸铁锂
    assert_frame_wire(f, Cmd.CHARGE_START, body)


def _freeze_random(monkeypatch, uniform_val=0.0, random_val=0.9):
    import random as _random
    monkeypatch.setattr(_random, "uniform", lambda a, b: uniform_val)
    monkeypatch.setattr(_random, "random", lambda: random_val)


def test_build_charge_info_fields(monkeypatch):
    _freeze_random(monkeypatch)                 # v=400 i=80 p=32kW
    sim = make_sim()
    sim.trade_no = "T123"
    e0, m0 = sim.energy, sim.meter
    f = sim.build_charge_info()
    body = f.body
    assert f.cmd == Cmd.CHARGE_INFO
    assert body[0:32].rstrip(b"\0") == b"T123"
    assert body[32:35] == bytes([1, 2, 1])
    assert len(body[35:42]) == 7                # 时标
    # 电价/服务费(万分位定点)
    assert struct.unpack("<ii", body[42:50]) == (int(0.6 * 10000), 10000)
    # 电量递增 p*30/3600 = 32*30/3600
    delta = 32.0 * 30 / 3600
    assert sim.energy == pytest.approx(e0 + delta)
    assert sim.meter == pytest.approx(m0 + delta)
    assert struct.unpack("<ii", body[50:58]) == (int(sim.energy * 10000), 100)
    assert struct.unpack("<Q", body[58:66])[0] == int(sim.meter * 10000)
    assert struct.unpack("<HH", body[66:70]) == (850, 800)      # 枪温/环温+500
    assert struct.unpack("<H", body[70:72]) == (1200,)          # 导引电压
    assert body[72:88] == b"\0" * 16                             # 交流区全0
    v10, i10, p10 = struct.unpack("<HHH", body[88:94])
    assert (v10, i10, p10) == (4000, 800 + 32768, 320)          # 0.1单位, 电流带偏移
    assert body[94:96] == bytes([42, 98])                        # SOC/SOH
    assert struct.unpack("<ii", body[50:58])[1] == 100           # 金额固定1元
    assert_frame_wire(f, Cmd.CHARGE_INFO, body)


def test_build_charge_info_zero_energy(monkeypatch):
    _freeze_random(monkeypatch)
    sim = make_sim()
    f = sim.build_charge_info()
    # energy 从0起, 单报累计 32kW×30s = 0.26667 kWh → 万分位 2666
    assert struct.unpack("<i", f.body[50:54])[0] == 2666


def test_build_charge_info_soc_bump_and_cap(monkeypatch):
    import random as _random
    monkeypatch.setattr(_random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(_random, "random", lambda: 0.0)          # <0.3 → SOC+1
    sim = make_sim()
    sim.build_charge_info()
    assert sim.soc == 43
    sim.soc = 100
    sim.build_charge_info()
    assert sim.soc == 100                                        # 封顶


def test_build_charge_end_fields():
    sim = make_sim()
    sim.trade_no = "TEnd"
    sim.energy = 50.0
    f = sim.build_charge_end()
    body = f.body
    assert f.cmd == Cmd.CHARGE_END
    assert body[0:32].rstrip(b"\0") == sim.user.encode()
    assert body[32:64].rstrip(b"\0") == b"TEnd"
    assert body[64:67] == bytes([2, 1, 3])       # 远程/充电/充满
    assert len(body[67:74]) == 7 and len(body[74:81]) == 7       # 起止时标
    assert struct.unpack("<i", body[81:85])[0] == int(50.0 * 10000)
    assert body[102:105] == bytes([42, sim.soc, 1])              # 起始SOC/结束SOC/枪号
    start_meter, end_meter = struct.unpack("<QQ", body[105:121])
    assert end_meter == int(sim.meter * 10000)
    assert start_meter == int((sim.meter - sim.energy) * 10000)
    assert_frame_wire(f, Cmd.CHARGE_END, body)


# ----- build_bill 计费编码重点 -----

@pytest.mark.parametrize("energy", [0.0, 0.0001, 12.345, 12345.678])
def test_build_bill_amount_encoding(energy):
    sim = make_sim()
    sim.trade_no = "TB"
    sim.energy = energy
    f = sim.build_bill()
    body = f.body
    assert f.cmd == Cmd.BILL
    assert body[0:32].rstrip(b"\0") == sim.user.encode()
    assert body[32:64].rstrip(b"\0") == b"TB"
    assert body[64:66] == bytes([2, 1])          # 远程/充电
    assert len(body[66:73]) == 7 and len(body[73:80]) == 7       # 起止/扣费时标
    assert body[80] == 1                         # 扣费成功
    amount = energy * 1.6
    # 总电量(0.0001度定点)
    assert struct.unpack("<i", body[101:105])[0] == int(energy * 10000)
    # 总金额/电费/服务费: 0.01元定点(分)
    total, svc_fixed, fee, svc = struct.unpack("<iiii", body[105:121])
    assert total == int(amount * 100)
    assert svc_fixed == 999900                   # 服务费率固定 99.99元
    assert fee == int(amount * 0.4 * 100)
    assert svc == int(amount * 0.6 * 100)
    assert body[121] == 1                        # 1时段
    assert body[122] == 3                        # 尖峰?时段类型
    assert struct.unpack("<ii", body[137:145]) == (6000, 10000)  # 时段电价/服务费率
    assert struct.unpack("<i", body[145:149])[0] == int(energy * 10000)
    a2, b2 = struct.unpack("<ii", body[149:157])
    assert (a2, b2) == (fee, svc)
    assert_frame_wire(f, Cmd.BILL, body)


def test_build_bill_fee_service_split_integer_consistency():
    sim = make_sim()
    sim.energy = 0.07             # amount=0.112 → 总11分, 4/6拆
    body = sim.build_bill().body
    total, _, fee, svc = struct.unpack("<iiii", body[105:121])
    assert (total, fee, svc) == (11, 4, 6)       # int截断: 4.48→4, 6.72→6


def test_build_bill_max_amount():
    sim = make_sim()
    sim.energy = 100000.0         # amount=160000元 → 16000000分, i32 安全
    body = sim.build_bill().body
    assert struct.unpack("<i", body[105:109])[0] == 16000000


# ----- run() 主循环 -----

class FakeReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        return self._chunks.pop(0) if self._chunks else b""


class FakeWriter:
    def __init__(self):
        self.written = []
        self.closed = False

    def write(self, data):
        self.written.append(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True


def _ack(sim, cmd, body):
    from app.gateway.szbus import SZBusFrame
    return SZBusFrame(sim.seq, 0x16, 0x01, sim.device_id, cmd, body).encode()


async def test_run_connection_failure(monkeypatch):
    async def fail(host, port):
        raise OSError("refused")
    monkeypatch.setattr(asyncio, "open_connection", fail)
    sim = make_sim()
    with pytest.raises(OSError):
        await sim.run(charge=False, duration=1)


async def test_run_checkin_rejected_exits(monkeypatch, capsys):
    sim = make_sim()
    reader = FakeReader([b"\x00garbage-no-frame"])
    writer = FakeWriter()

    async def oc(host, port):
        return reader, writer
    monkeypatch.setattr(asyncio, "open_connection", oc)
    await sim.run(charge=False, duration=10)
    assert "签到失败" in capsys.readouterr().out
    assert writer.closed
    assert len(writer.written) == 1              # 只发了签到, 未进主循环


async def test_run_checkin_success_and_exit(monkeypatch, capsys):
    sim = make_sim()
    checkin_ack = _ack(sim, Cmd.CHECKIN_ACK, bytes([1]))
    reader = FakeReader([checkin_ack])
    writer = FakeWriter()

    async def oc(host, port):
        return reader, writer
    monkeypatch.setattr(asyncio, "open_connection", oc)
    await sim.run(charge=False, duration=1)
    out = capsys.readouterr().out
    assert "签到成功" in out
    first = (await _frames(writer.written))[0]
    assert first.cmd == Cmd.CHECKIN
    assert writer.closed


async def test_run_remote_start_triggers_charge_flow(monkeypatch):
    sim = make_sim()
    checkin_ack = _ack(sim, Cmd.CHECKIN_ACK, bytes([1]))
    start_cmd = _ack(sim, Cmd.START, b"\0" * 40)
    reader = FakeReader([checkin_ack, start_cmd])
    writer = FakeWriter()

    async def oc(host, port):
        return reader, writer
    monkeypatch.setattr(asyncio, "open_connection", oc)
    await sim.run(charge=False, duration=2.5)
    frames = await _frames(writer.written)
    cmds = [f.cmd for f in frames]
    assert cmds[0] == Cmd.CHECKIN
    assert Cmd.START_ACK in cmds
    assert Cmd.OP_RESULT in cmds
    assert Cmd.CHARGE_START in cmds
    assert sim.charging is True


async def _frames(raw_list):
    """逐帧独立解析(mock write 收到的每条都是完整 encode 帧)。"""
    from app.gateway.szbus import SZBusFrame, extract_frames
    out = []
    for raw in raw_list:
        fs, _ = extract_frames(raw)
        out.extend(fs)
    assert all(f is not None for f in out)
    return out
