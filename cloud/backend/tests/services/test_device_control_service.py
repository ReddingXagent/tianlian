# -*- coding: utf-8 -*-
"""
设备控制服务测试 - 覆盖率 ≥70%

被测: app/services/device_control_service.py (DeviceControlService)

设计:
  - 主流程走 test_db 真实 SQLite, monkeypatch device_control_service.get_adapter
    注入 MagicMock(AsyncMock write_command), 不 mock DB。
  - get_control_history 主路径: 生产 app.models.operation_log 不存在, 默认走 ImportError
    回退; 本测试通过 monkeypatch sys.modules 注入 _FakeOperationLog ORM 替身覆盖主路径
    (模块级定义 -> 自动进入 Base.metadata -> schema_template 建表)。

本 service 通过 self.db 注入, 无模块级 SessionLocal 按值绑定坑。

覆盖:
- send_control    设备不存在 / 适配器None / 成功(校验write_command入参) / 失败 / 异常 /
                  config补充protocol+device_address
- reset_device    soft(0x01) / hard(0x02) / 未知类型
- set_parameter   4个映射寄存器(1026-1029) / 未知参数
- emergency_stop  成功->register1025+status=maintenance / 失败->不改状态
- get_control_history  主路径(OperationLog映射+action过滤+desc排序) /
                       ImportError回退(无control_log->[]) /
                       回退control_log(list切片/JSON字符串解析/None)
"""
import json
import sys
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Column, DateTime, Integer, String

from app.services import device_control_service as svc
from app.services.device_control_service import DeviceControlService
from app.core.database import Base
from app.models.device import Device, DeviceStatus, DeviceType, ProtocolType
from app.models.station import Station, StationStatus


# ═══════════════════════════════════════════════════════════════
# 测试替身: OperationLog ORM (覆盖 get_control_history 主路径)
# ═══════════════════════════════════════════════════════════════
# 模块级定义: 收集时进入 Base.metadata, session 级 _schema_template_db 建表,
# 每个 test_db copy 即含此表。sys.modules 注入后 get_control_history 主路径可查。
class _FakeOperationLog(Base):
    __tablename__ = "_fake_oplog_dcservice"
    id = Column(Integer, primary_key=True)
    resource_type = Column(String)
    resource_id = Column(String)
    action = Column(String)
    detail = Column(String)
    operator = Column(String)
    user_id = Column(Integer)
    result = Column(String)
    created_at = Column(DateTime)


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

STATION_ID = 9001


@pytest.fixture
def station(test_db):
    db = test_db["session"]
    st = Station(id=STATION_ID, name="T", code="ST-DC", status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    return st


def _device(db, did, **kw):
    d = Device(
        id=did, sn=f"SN-DC-{did}", name=f"d{did}", code=f"DC{did}",
        type=kw.get("type", DeviceType.CHARGER_DC),
        status=kw.get("status", DeviceStatus.ONLINE),
        station_id=kw.get("station_id", STATION_ID),
        protocol_type=kw.get("protocol_type", ProtocolType.MODBUS_TCP),
        device_address=kw.get("device_address", 7),
        comm_config=kw.get("comm_config", {}),
    )
    db.add(d)
    db.commit()
    return d


def _adapter(write_result=True, raises=None):
    """构造 get_adapter 返回的 mock adapter (write_command 为 AsyncMock)。"""
    adapter = MagicMock()
    if raises is not None:
        adapter.write_command = AsyncMock(side_effect=raises)
    else:
        adapter.write_command = AsyncMock(return_value=write_result)
    return adapter


# ═══════════════════════════════════════════════════════════════
# send_control
# ═══════════════════════════════════════════════════════════════

class TestSendControl:

    async def test_device_not_found(self, test_db):
        db = test_db["session"]
        result = await DeviceControlService(db).send_control(99999, {"register": 1})
        assert result == {"success": False, "error": "设备不存在"}

    async def test_adapter_unavailable(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7001)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: None)

        result = await DeviceControlService(db).send_control(7001, {"register": 1})
        assert result == {"success": False, "error": "适配器不可用"}

    async def test_success(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7002)
        adapter = _adapter(write_result=True)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)

        cmd = {"register": 1024, "value": 1}
        result = await DeviceControlService(db).send_control(7002, cmd)

        assert result["success"] is True
        assert result["device_id"] == 7002
        assert result["command"] == cmd
        assert "timestamp" in result
        # write_command 收到 device_address(7) + 原始 command
        adapter.write_command.assert_awaited_once_with(7, cmd)

    async def test_write_returns_false(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7003)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: _adapter(write_result=False))

        result = await DeviceControlService(db).send_control(7003, {"register": 1})
        assert result == {"success": False, "error": "指令下发失败"}

    async def test_write_raises(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7004)
        monkeypatch.setattr(
            svc, "get_adapter", lambda dt, cfg: _adapter(raises=TimeoutError("device timeout"))
        )

        result = await DeviceControlService(db).send_control(7004, {"register": 1})
        assert result == {"success": False, "error": "服务内部错误，请稍后重试"}

    async def test_config_supplements_protocol_and_address(self, test_db, station, monkeypatch):
        db = test_db["session"]
        # comm_config 不含 protocol/device_address, 由 device 字段补充
        _device(db, 7005, comm_config={"host": "1.2.3.4"})
        captured = {}

        def fake_get_adapter(dt, cfg):
            captured["dt"] = dt
            captured["cfg"] = cfg
            return _adapter(True)

        monkeypatch.setattr(svc, "get_adapter", fake_get_adapter)

        await DeviceControlService(db).send_control(7005, {"register": 1})

        # protocol 从 protocol_type.value 补充; device_address 从 device.device_address 补充
        assert captured["cfg"]["protocol"] == ProtocolType.MODBUS_TCP.value
        assert captured["cfg"]["device_address"] == 7
        assert captured["cfg"]["host"] == "1.2.3.4"        # 原配置保留
        assert captured["dt"] == "charger"                  # device_type property


# ═══════════════════════════════════════════════════════════════
# reset_device
# ═══════════════════════════════════════════════════════════════

class TestResetDevice:

    async def test_soft_reset(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7101)
        adapter = _adapter(True)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)

        result = await DeviceControlService(db).reset_device(7101, reset_type="soft")

        assert result["success"] is True
        command = adapter.write_command.await_args.args[1]
        assert command["register"] == 1024
        assert command["value"] == 0x01
        assert command["type"] == "reset_soft"

    async def test_hard_reset(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7102)
        adapter = _adapter(True)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)

        await DeviceControlService(db).reset_device(7102, reset_type="hard")

        command = adapter.write_command.await_args.args[1]
        assert command["value"] == 0x02
        assert command["type"] == "reset_hard"

    async def test_unknown_reset_type(self, test_db, station):
        db = test_db["session"]
        _device(db, 7103)
        result = await DeviceControlService(db).reset_device(7103, reset_type="nuke")
        assert result["success"] is False
        assert "未知的复位类型" in result["error"]


# ═══════════════════════════════════════════════════════════════
# set_parameter
# ═══════════════════════════════════════════════════════════════

class TestSetParameter:

    async def test_all_mapped_parameters(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7201)
        adapter = _adapter(True)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)
        service = DeviceControlService(db)

        expected = {
            "power_limit": 1026,
            "voltage_threshold_high": 1027,
            "voltage_threshold_low": 1028,
            "frequency_threshold": 1029,
        }
        for param, reg in expected.items():
            result = await service.set_parameter(7201, param, 50)
            assert result["success"] is True
            command = adapter.write_command.await_args.args[1]
            assert command["register"] == reg
            assert command["value"] == 50
            assert command["type"] == "param_set"

    async def test_unknown_parameter(self, test_db, station):
        db = test_db["session"]
        _device(db, 7299)
        result = await DeviceControlService(db).set_parameter(7299, "nope_param", 1)
        assert result["success"] is False
        assert "未知的参数" in result["error"]


# ═══════════════════════════════════════════════════════════════
# emergency_stop
# ═══════════════════════════════════════════════════════════════

class TestEmergencyStop:

    async def test_success_updates_status(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7301, status=DeviceStatus.CHARGING)
        adapter = _adapter(True)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: adapter)

        result = await DeviceControlService(db).emergency_stop(7301)

        assert result["success"] is True
        command = adapter.write_command.await_args.args[1]
        assert command["register"] == 1025
        assert command["value"] == 0x01
        assert command["type"] == "emergency_stop"
        # 设备状态持久化为 maintenance
        d = db.query(Device).filter(Device.id == 7301).first()
        assert d.status == DeviceStatus.MAINTENANCE

    async def test_failure_no_status_change(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7302, status=DeviceStatus.CHARGING)
        monkeypatch.setattr(svc, "get_adapter", lambda dt, cfg: _adapter(write_result=False))

        result = await DeviceControlService(db).emergency_stop(7302)

        assert result["success"] is False
        d = db.query(Device).filter(Device.id == 7302).first()
        assert d.status == DeviceStatus.CHARGING


# ═══════════════════════════════════════════════════════════════
# get_control_history
# ═══════════════════════════════════════════════════════════════

class TestGetControlHistory:

    def test_importerror_fallback_empty(self, test_db, station):
        # operation_log 模块不存在 -> ImportError -> 回退 Device.control_log
        # Device 无 control_log 字段 -> 返回 []
        db = test_db["session"]
        _device(db, 7401)
        assert DeviceControlService(db).get_control_history(7401) == []

    def test_operation_log_primary_path(self, test_db, station, monkeypatch):
        # 注入 fake OperationLog 覆盖主路径
        db = test_db["session"]
        _device(db, 7402)
        monkeypatch.setitem(
            sys.modules,
            "app.models.operation_log",
            types.SimpleNamespace(OperationLog=_FakeOperationLog),
        )

        db.add_all([
            _FakeOperationLog(resource_type="device", resource_id="7402", action="control",
                              detail="开闸", operator="admin", user_id=1, result="ok",
                              created_at=datetime(2026, 8, 2, 10, 0)),
            _FakeOperationLog(resource_type="device", resource_id="7402", action="reset",
                              detail="软复位", operator="admin", user_id=1, result="ok",
                              created_at=datetime(2026, 8, 2, 11, 0)),
            # action=view 不在白名单 -> 被过滤
            _FakeOperationLog(resource_type="device", resource_id="7402", action="view",
                              detail="查看", operator="admin", user_id=1, result="ok",
                              created_at=datetime(2026, 8, 2, 9, 0)),
        ])
        db.commit()

        history = DeviceControlService(db).get_control_history(7402)

        # view 被过滤剩 2 条; desc 排序 -> 11:00 在前
        assert len(history) == 2
        assert history[0]["action"] == "reset"
        assert history[0]["device_id"] == 7402
        assert history[0]["operator"] == "admin"
        assert history[0]["operator_id"] == 1
        assert history[0]["detail"] == "软复位"
        assert history[0]["result"] == "ok"
        assert history[0]["created_at"].startswith("2026-08-02T11")

    def test_operation_log_primary_path_limit(self, test_db, station, monkeypatch):
        db = test_db["session"]
        _device(db, 7403)
        monkeypatch.setitem(
            sys.modules,
            "app.models.operation_log",
            types.SimpleNamespace(OperationLog=_FakeOperationLog),
        )
        db.add_all([
            _FakeOperationLog(resource_type="device", resource_id="7403", action="control",
                              detail=f"c{i}", operator="admin", user_id=1, result="ok",
                              created_at=datetime(2026, 8, 2, 10, i))
            for i in range(5)
        ])
        db.commit()

        history = DeviceControlService(db).get_control_history(7403, limit=2)
        assert len(history) == 2
        # desc: 最新两条 (i=4, i=3)
        assert history[0]["detail"] == "c4"
        assert history[1]["detail"] == "c3"

    def test_fallback_control_log_list(self, test_db, station):
        # 回退路径: device.control_log 是 list
        db = test_db["session"]
        d = _device(db, 7404)
        d.control_log = [{"a": 1}, {"b": 2}, {"c": 3}]   # 动态属性
        db.flush()

        result = DeviceControlService(db).get_control_history(7404, limit=2)
        assert result == [{"a": 1}, {"b": 2}]

    def test_fallback_control_log_json_string(self, test_db, station):
        db = test_db["session"]
        d = _device(db, 7405)
        d.control_log = json.dumps([{"x": 1}])
        db.flush()

        result = DeviceControlService(db).get_control_history(7405)
        assert result == [{"x": 1}]

    def test_fallback_control_log_none(self, test_db, station):
        db = test_db["session"]
        d = _device(db, 7406)
        d.control_log = None
        db.flush()

        assert DeviceControlService(db).get_control_history(7406) == []

    def test_primary_path_query_error_caught(self, test_db, station, monkeypatch):
        # 主路径: OperationLog 导入成功但 query 抛非 ImportError 异常 -> except Exception -> 回退
        db = test_db["session"]
        _device(db, 7410)
        # 注入非法 OperationLog (非 ORM 实体) -> filter 构建时抛 AttributeError
        monkeypatch.setitem(
            sys.modules, "app.models.operation_log",
            types.SimpleNamespace(OperationLog="not-an-orm-class"),
        )
        # device 无 control_log -> 回退兜底返回 []
        assert DeviceControlService(db).get_control_history(7410) == []

    def test_fallback_control_log_invalid_json(self, test_db, station):
        # 回退路径: control_log 是非法 JSON 字符串 -> json.loads 抛 -> except -> 返回 []
        db = test_db["session"]
        d = _device(db, 7411)
        d.control_log = "{not valid json"
        db.flush()

        assert DeviceControlService(db).get_control_history(7411) == []


# ═══════════════════════════════════════════════════════════════
# emergency_stop commit 异常 rollback 保护
# ═══════════════════════════════════════════════════════════════

class TestEmergencyStopCommitRollback:
    """急停指令已下发成功后, 设备状态持久化 commit 失败必须 rollback —— 防脏事务残留连接池。

    用 MagicMock 注入 db + AsyncMock 桩 send_control(绕过适配器细节, 聚焦 commit 路径),
    不连真实 DB。
    """

    async def test_rollback_on_commit_error(self):
        mock_db = MagicMock()
        # 设备查询命中(truthy) → 进入 status 更新 + commit 分支
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()
        mock_db.commit.side_effect = RuntimeError("db boom")

        service = DeviceControlService(mock_db)
        # 指令下发已成功, 聚焦后续 commit 路径
        service.send_control = AsyncMock(return_value={
            "success": True, "device_id": 7301, "command": {}, "timestamp": datetime.now(timezone.utc),
        })

        with pytest.raises(RuntimeError):
            await service.emergency_stop(7301)

        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_called_once()
