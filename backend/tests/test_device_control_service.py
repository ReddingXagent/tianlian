"""
DeviceControlService 单元测试

覆盖 app/services/device_control_service.py 的 5 个方法：
- send_control (async):    设备不存在 / 适配器不可用 / 下发成功 / 下发失败(False) / 下发异常
- reset_device (async):    soft / hard / 未知复位类型
- set_parameter (async):   已知参数(寄存器映射) / 未知参数
- emergency_stop (async):  成功(更新设备状态为 maintenance) / 失败(状态不变)
- get_control_history:     OperationLog 正常路径 / ImportError 回退无 control_log /
                           control_log(list) 兜底 / control_log(str) 兜底 / 查询异常回退

外部依赖（设备适配器 / DB / OperationLog）用 MagicMock 与 monkeypatch 隔离，
不改 app/ 下任何业务代码。

注意：app/models/operation_log.py 在当前代码库尚不存在，故 get_control_history
首段 `from app.models.operation_log import OperationLog` 必抛 ImportError 走回退；
为覆盖「正常路径」与「查询异常回退」两条分支，测试通过 sys.modules 注入桩模块。
Device 模型无 control_log 列，list/str 兜底分支用 mock db 注入带 control_log 属性的桩设备。
"""

import sys
import types
from datetime import datetime
from unittest.mock import MagicMock

from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
from app.models.station import Station, StationStatus
from app.services.device_control_service import DeviceControlService


# ───────────────────────── helpers ─────────────────────────


def _make_device(session, **over):
    """造一台带协议/地址/通信配置的在线逆变器，返回已 flush 出 id 的 Device。"""
    st = Station(name="测试站", code="ST-CTL", address="测试地址", status=StationStatus.NORMAL)
    session.add(st)
    session.flush()
    base = dict(
        sn="SN-CTL-001",
        name="逆变器#控制测试",
        code="CTL001",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=st.id,
        health_score=95.0,
        total_run_hours=12.5,
        device_address=5,
        protocol_type=ProtocolType.MODBUS_RTU,
        comm_config={"port": "/dev/ttyUSB0", "baudrate": 9600},
    )
    base.update(over)
    dev = Device(**base)
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return dev


class _FakeControlAdapter:
    """模拟协议适配器：write_command 返回预设 bool，或抛预设异常；并记录调用入参。"""

    def __init__(self, ok=True, exc=None):
        self._ok = ok
        self._exc = exc
        self.calls = []  # [(device_address, command), ...]

    async def write_command(self, device_address, command):
        self.calls.append((device_address, command))
        if self._exc is not None:
            raise self._exc
        return self._ok


def _patch_adapter(monkeypatch, adapter):
    """把 device_control_service 命名空间的 get_adapter 替换为返回 adapter 的桩。"""
    monkeypatch.setattr(
        "app.services.device_control_service.get_adapter", lambda *a, **k: adapter
    )


def _inject_fake_operation_log(monkeypatch):
    """向 sys.modules 注入桩 app.models.operation_log（含 OperationLog 属性），
    使 get_control_history 的函数内 `from ... import OperationLog` 走「正常路径」。"""
    mod = types.ModuleType("app.models.operation_log")
    mod.OperationLog = MagicMock()
    monkeypatch.setitem(sys.modules, "app.models.operation_log", mod)
    return mod.OperationLog


# ───────────────────────── send_control ─────────────────────────


async def test_send_control_device_not_found(db_session):
    svc = DeviceControlService(db_session)
    result = await svc.send_control(99999, {"register": 1, "value": 1})
    assert result == {"success": False, "error": "设备不存在"}


async def test_send_control_adapter_unavailable(db_session, monkeypatch):
    dev = _make_device(db_session)
    _patch_adapter(monkeypatch, None)  # get_adapter 返回 None
    svc = DeviceControlService(db_session)
    result = await svc.send_control(dev.id, {"register": 1, "value": 1})
    assert result == {"success": False, "error": "适配器不可用"}


async def test_send_control_success(db_session, monkeypatch):
    """下发成功 → success dict；覆盖 protocol_type.value / device_address 补充配置分支。"""
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=True)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    cmd = {"register": 1024, "value": 0x01}
    result = await svc.send_control(dev.id, cmd)

    assert result["success"] is True
    assert result["device_id"] == dev.id
    assert result["command"] == cmd
    assert "timestamp" in result
    # write_command 收到的 device_address 来自 device.device_address(=5)
    assert adapter.calls[0][0] == 5
    assert adapter.calls[0][1] == cmd


async def test_send_control_write_returns_false(db_session, monkeypatch):
    """adapter.write_command 返回 False → 下发失败。"""
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=False)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.send_control(dev.id, {"register": 1, "value": 1})
    assert result == {"success": False, "error": "指令下发失败"}


async def test_send_control_write_raises(db_session, monkeypatch):
    """adapter.write_command 抛异常 → 捕获并返回 {"error": str(exc)}。"""
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(exc=TimeoutError("写超时"))
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.send_control(dev.id, {"register": 1, "value": 1})
    assert result["success"] is False and result["error"]  # cc2272b84: 底层异常脱敏


async def test_send_control_no_comm_config_uses_empty(db_session, monkeypatch):
    """comm_config=None → `device.comm_config or {}` 走空 dict 分支，
    仍依赖 device.protocol_type / device_address 补充配置。"""
    dev = _make_device(db_session, comm_config=None, sn="SN-CTL-NOCFG", code="CTLNOCFG")
    adapter = _FakeControlAdapter(ok=True)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.send_control(dev.id, {"register": 1, "value": 1})
    assert result["success"] is True


# ───────────────────────── reset_device ─────────────────────────


async def test_reset_soft(db_session, monkeypatch):
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=True)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.reset_device(dev.id, reset_type="soft")
    assert result["success"] is True
    assert adapter.calls[0] == (5, {"register": 1024, "value": 0x01, "type": "reset_soft"})


async def test_reset_hard(db_session, monkeypatch):
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=True)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.reset_device(dev.id, reset_type="hard")
    assert result["success"] is True
    assert adapter.calls[0] == (5, {"register": 1024, "value": 0x02, "type": "reset_hard"})


async def test_reset_unknown_type(db_session):
    """未知 reset_type → 直接返回错误，不调用 send_control。"""
    dev = _make_device(db_session)
    svc = DeviceControlService(db_session)
    result = await svc.reset_device(dev.id, reset_type="boom")
    assert result == {"success": False, "error": "未知的复位类型: boom"}


# ───────────────────────── set_parameter ─────────────────────────


async def test_set_parameter_known(db_session, monkeypatch):
    """已知参数 power_limit → 寄存器 1026，透传 value。"""
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=True)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.set_parameter(dev.id, "power_limit", 80)
    assert result["success"] is True
    assert adapter.calls[0] == (5, {"register": 1026, "value": 80, "type": "param_set"})


async def test_set_parameter_unknown(db_session):
    """未知参数 → 直接返回错误。"""
    dev = _make_device(db_session)
    svc = DeviceControlService(db_session)
    result = await svc.set_parameter(dev.id, "nope_param", 1)
    assert result == {"success": False, "error": "未知的参数: nope_param"}


# ───────────────────────── emergency_stop ─────────────────────────


async def test_emergency_stop_success_updates_status(db_session, monkeypatch):
    """急停成功 → 设备状态被更新为 maintenance 并 commit。"""
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=True)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.emergency_stop(dev.id)
    assert result["success"] is True
    assert adapter.calls[0][1]["register"] == 1025  # 急停寄存器

    # status 被写为字符串 "maintenance"，SQLEnum 读回时按 value lookup 回 DeviceStatus.MAINTENANCE
    db_session.refresh(dev)
    assert dev.status == DeviceStatus.MAINTENANCE


async def test_emergency_stop_failure_keeps_status(db_session, monkeypatch):
    """急停下发失败 → 不更新设备状态，保持 ONLINE。"""
    dev = _make_device(db_session)
    adapter = _FakeControlAdapter(ok=False)
    _patch_adapter(monkeypatch, adapter)
    svc = DeviceControlService(db_session)
    result = await svc.emergency_stop(dev.id)
    assert result["success"] is False
    db_session.refresh(dev)
    assert dev.status == DeviceStatus.ONLINE


# ───────────────────────── get_control_history ─────────────────────────


def test_history_operationlog_path(monkeypatch):
    """OperationLog 正常路径：注入桩模块 + mock db 查询链 → 组装 history 记录。"""
    _inject_fake_operation_log(monkeypatch)
    fake_log = MagicMock()
    fake_log.id = 1
    fake_log.action = "control"
    fake_log.detail = {"register": 1024}
    fake_log.operator = "admin"
    fake_log.user_id = 10
    fake_log.result = "success"
    fake_log.created_at = datetime(2026, 1, 2, 3, 4, 5)

    mock_db = MagicMock()
    # service 实际链路: query().filter(a,b,c).order_by().limit().all()
    # （单次 filter 多参数，非两次 filter）
    chain = (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
    )
    chain.all.return_value = [fake_log]

    svc = DeviceControlService(mock_db)
    history = svc.get_control_history(7)
    assert len(history) == 1
    rec = history[0]
    assert rec["id"] == 1
    assert rec["device_id"] == 7
    assert rec["action"] == "control"
    assert rec["detail"] == {"register": 1024}
    assert rec["operator"] == "admin"
    assert rec["operator_id"] == 10
    assert rec["result"] == "success"
    assert rec["created_at"] == "2026-01-02T03:04:05"


def test_history_importerror_fallback_no_controllog(db_session):
    """OperationLog 模块缺失(ImportError) + Device 无 control_log 列 → 回退后返回 []。"""
    dev = _make_device(db_session)
    svc = DeviceControlService(db_session)
    assert svc.get_control_history(dev.id) == []


def test_history_controllog_list_fallback(monkeypatch):
    """回退路径：device.control_log 为 list → 返回 list[:limit]。"""
    fake_dev = MagicMock()
    fake_dev.control_log = [{"a": 1}, {"b": 2}, {"c": 3}]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = fake_dev

    svc = DeviceControlService(mock_db)
    result = svc.get_control_history(1, limit=2)
    assert result == [{"a": 1}, {"b": 2}]


def test_history_controllog_str_fallback(monkeypatch):
    """回退路径：device.control_log 为 JSON 字符串 → json.loads 后返回。"""
    fake_dev = MagicMock()
    fake_dev.control_log = '[{"x": 1}, {"y": 2}]'
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = fake_dev

    svc = DeviceControlService(mock_db)
    result = svc.get_control_history(1)
    assert result == [{"x": 1}, {"y": 2}]


def test_history_controllog_malformed_json_returns_empty(monkeypatch):
    """回退路径：device.control_log 为非法 JSON 字符串(DB 存了坏 JSON) →
    json.loads 抛 JSONDecodeError 被 except Exception 捕获 → 返回 []，不崩。"""
    fake_dev = MagicMock()
    fake_dev.control_log = "{not valid json"  # DB 里存了坏 JSON
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = fake_dev

    svc = DeviceControlService(mock_db)
    assert svc.get_control_history(1) == []


def test_history_operationlog_query_exception(monkeypatch):
    """OperationLog 正常 import 但查询抛异常 → except Exception 回退 → []。"""
    _inject_fake_operation_log(monkeypatch)
    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("db connection lost")

    svc = DeviceControlService(mock_db)
    assert svc.get_control_history(1) == []
