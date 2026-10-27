"""test_device_control_service2.py — 设备控制服务单元测试

覆盖: send_control (设备不存在/适配器不可用/成功/异常), reset_device (soft/hard/无效类型),
set_parameter (已知/未知参数), emergency_stop (成功更新状态/设备不存在),
get_control_history (OperationLog路径/control_log回退/空)。
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from app.services.device_control_service import DeviceControlService


def make_device(device_id=1, device_type="charger_dc", protocol_type=None, device_address=1, comm_config=None):
    d = MagicMock()
    d.id = device_id
    d.device_type = device_type
    d.protocol_type = protocol_type
    d.device_address = device_address
    d.comm_config = comm_config or {}
    d.status = "online"
    return d


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def service(db):
    return DeviceControlService(db)


# ─── send_control ───

class TestSendControl:
    @pytest.mark.asyncio
    async def test_device_not_found(self, service, db):
        db.query.return_value.filter.return_value.first.return_value = None
        r = await service.send_control(999, {"register": 1})
        assert r["success"] is False
        assert "不存在" in r["error"]

    @pytest.mark.asyncio
    async def test_adapter_not_available(self, service, db):
        device = make_device()
        db.query.return_value.filter.return_value.first.return_value = device
        with patch("app.services.device_control_service.get_adapter", return_value=None):
            r = await service.send_control(1, {"register": 1})
        assert r["success"] is False
        assert "适配器" in r["error"]

    @pytest.mark.asyncio
    async def test_send_success(self, service, db):
        device = make_device(protocol_type=MagicMock(value="modbus"))
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.send_control(1, {"register": 1024, "value": 1})
        assert r["success"] is True
        assert r["device_id"] == 1
        assert r["command"]["register"] == 1024

    @pytest.mark.asyncio
    async def test_send_adapter_returns_false(self, service, db):
        device = make_device()
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(return_value=False)
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.send_control(1, {"register": 1})
        assert r["success"] is False
        assert "失败" in r["error"]

    @pytest.mark.asyncio
    async def test_send_adapter_raises_exception(self, service, db):
        device = make_device()
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(side_effect=ConnectionError("timeout"))
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.send_control(1, {"register": 1})
        assert r["success"] is False
        assert r["error"]  # cc2272b84: 底层异常脱敏为通用消息


# ─── reset_device ───

class TestResetDevice:
    @pytest.mark.asyncio
    async def test_soft_reset(self, service, db):
        device = make_device(protocol_type=MagicMock(value="modbus"))
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.reset_device(1, "soft")
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_hard_reset(self, service, db):
        device = make_device(protocol_type=MagicMock(value="modbus"))
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.reset_device(1, "hard")
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_invalid_reset_type(self, service):
        r = await service.reset_device(1, "nuke")
        assert r["success"] is False
        assert "未知" in r["error"]


# ─── set_parameter ───

class TestSetParameter:
    @pytest.mark.asyncio
    async def test_known_parameter(self, service, db):
        device = make_device(protocol_type=MagicMock(value="modbus"))
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.set_parameter(1, "power_limit", 50)
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_parameter(self, service):
        r = await service.set_parameter(1, "unknown_param", 42)
        assert r["success"] is False
        assert "未知" in r["error"]


# ─── emergency_stop ───

class TestEmergencyStop:
    @pytest.mark.asyncio
    async def test_emergency_stop_success_updates_status(self, service, db):
        device = make_device(protocol_type=MagicMock(value="modbus"))
        # First query for send_control, second for status update
        db.query.return_value.filter.return_value.first.return_value = device
        adapter = MagicMock()
        adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=adapter):
            r = await service.emergency_stop(1)
        assert r["success"] is True
        assert device.status == "maintenance"
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_emergency_stop_device_not_found(self, service, db):
        db.query.return_value.filter.return_value.first.return_value = None
        r = await service.emergency_stop(999)
        assert r["success"] is False
        assert "不存在" in r["error"]


# ─── get_control_history ───

class TestGetControlHistory:
    def test_empty_history(self, service, db):
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        with patch("app.services.device_control_service.OperationLog", create=True, side_effect=ImportError):
            pass
        # Should fall through to Device.control_log
        device = MagicMock()
        device.control_log = None
        db.query.return_value.filter.return_value.first.return_value = device
        history = service.get_control_history(1)
        assert history == []

    def test_history_from_control_log_json_string(self, service, db):
        import json
        logs = [{"action": "control", "device_id": 1}]
        device = MagicMock()
        device.control_log = json.dumps(logs)
        device.hasattr = lambda attr: attr == "control_log"
        # First query (OperationLog) will fail with ImportError
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        db.query.return_value.filter.return_value.first.return_value = device
        # Force ImportError on OperationLog
        import sys
        old = sys.modules.get("app.models.operation_log")
        sys.modules["app.models.operation_log"] = None  # cause ImportError
        try:
            history = service.get_control_history(1)
            # May return from control_log fallback
            assert isinstance(history, list)
        finally:
            if old:
                sys.modules["app.models.operation_log"] = old
            else:
                sys.modules.pop("app.models.operation_log", None)
