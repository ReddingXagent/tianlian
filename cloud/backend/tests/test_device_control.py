import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.device_control_log import DeviceControlLog
from app.services.device_control_service import DeviceControlService


@pytest.fixture(scope="function", autouse=True)
def _ensure_table(client):
    """确保 device_control_logs 表存在"""
    engine = client._sesh.get_bind()
    from sqlalchemy import inspect
    from app.core.database import Base
    if not inspect(engine).has_table("device_control_logs"):
        Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables["device_control_logs"]])


def _get_token(client, username="admin", password="admin123"):
    """获取认证 token；测试环境 login 应稳定可用，失败直接 fail 以暴露真实问题。"""
    resp = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"login 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    token = (data.get("data", {}).get("token") or data.get("token")
             or data.get("data", {}).get("access_token") or data.get("access_token"))
    assert token, f"login 响应未含 token: {data}"
    return token


class TestDeviceControl:
    """设备控制 API 测试"""

    def test_control_start_success(self, client: TestClient, seed_users, seed_devices):
        """启动设备 - 成功（模拟适配器）"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        # Mock the adapter to return success
        with patch("app.services.device_control_service.get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.write_command = AsyncMock(return_value=True)
            mock_get_adapter.return_value = mock_adapter
            
            response = client.post(
                f"/api/v1/devices/{device.id}/control",
                json={"action": "start"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, f"Failed: {response.text}"
            data = response.json()
            assert data["code"] == 200
            assert "成功" in data["message"]

    def test_control_stop_success(self, client: TestClient, seed_users, seed_devices):
        """停止设备 - 成功"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        with patch("app.services.device_control_service.get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.write_command = AsyncMock(return_value=True)
            mock_get_adapter.return_value = mock_adapter
            
            response = client.post(
                f"/api/v1/devices/{device.id}/control",
                json={"action": "stop"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, f"Failed: {response.text}"
            data = response.json()
            assert data["code"] == 200

    def test_control_restart_success(self, client: TestClient, seed_users, seed_devices):
        """重启设备 - 成功"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        with patch("app.services.device_control_service.get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.write_command = AsyncMock(return_value=True)
            mock_get_adapter.return_value = mock_adapter
            
            response = client.post(
                f"/api/v1/devices/{device.id}/control",
                json={"action": "restart", "reset_type": "soft"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, f"Failed: {response.text}"
            data = response.json()
            assert data["code"] == 200

    def test_control_emergency_stop_success(self, client: TestClient, seed_users, seed_devices):
        """急停 - 成功"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        with patch("app.services.device_control_service.get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.write_command = AsyncMock(return_value=True)
            mock_get_adapter.return_value = mock_adapter
            
            response = client.post(
                f"/api/v1/devices/{device.id}/control",
                json={"action": "emergency_stop"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, f"Failed: {response.text}"
            data = response.json()
            assert data["code"] == 200

    def test_control_set_param_success(self, client: TestClient, seed_users, seed_devices):
        """设置参数 - 成功"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        with patch("app.services.device_control_service.get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.write_command = AsyncMock(return_value=True)
            mock_get_adapter.return_value = mock_adapter
            
            response = client.post(
                f"/api/v1/devices/{device.id}/control",
                json={"action": "set_param", "parameter": "power_limit", "value": "80"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, f"Failed: {response.text}"
            data = response.json()
            assert data["code"] == 200

    def test_control_set_param_no_parameter(self, client: TestClient, seed_users, seed_devices):
        """设置参数 - 缺少 parameter 字段"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        response = client.post(
            f"/api/v1/devices/{device.id}/control",
            json={"action": "set_param", "value": "80"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_control_invalid_action(self, client: TestClient, seed_users, seed_devices):
        """不支持的 action"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        response = client.post(
            f"/api/v1/devices/{device.id}/control",
            json={"action": "invalid_action"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_control_nonexistent_device(self, client: TestClient, seed_users):
        """控制不存在的设备"""
        token = _get_token(client)
        
        response = client.post(
            "/api/v1/devices/99999/control",
            json={"action": "start"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"

    def test_control_non_charger_device(self, client: TestClient, seed_users, seed_devices):
        """控制非充电桩设备 - 应返回 400"""
        token = _get_token(client)
        
        # inv001 is PV_INVERTER, not a charger
        device = seed_devices["inv001"]
        
        response = client.post(
            f"/api/v1/devices/{device.id}/control",
            json={"action": "start"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_control_unauthenticated(self, anon_client, seed_devices):
        """未认证用户无法控制设备"""
        device = seed_devices["chg001"]

        response = anon_client.post(
            f"/api/v1/devices/{device.id}/control",
            json={"action": "start"},
        )
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}: {response.text}"


class TestDeviceControlHistory:
    """设备控制历史 API 测试"""

    def test_get_control_history_empty(self, client: TestClient, seed_users, seed_devices):
        """获取控制历史 - 空记录"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        response = client.get(
            f"/api/v1/devices/{device.id}/control-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["code"] == 200

    def test_get_control_history_with_data(self, client: TestClient, seed_users, seed_devices):
        """获取控制历史 - 有记录"""
        token = _get_token(client)
        
        device = seed_devices["chg001"]
        
        # First, perform a control action with mocked adapter
        with patch("app.services.device_control_service.get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_adapter.write_command = AsyncMock(return_value=True)
            mock_get_adapter.return_value = mock_adapter
            
            client.post(
                f"/api/v1/devices/{device.id}/control",
                json={"action": "start"},
                headers={"Authorization": f"Bearer {token}"},
            )
        
        # Then check history
        response = client.get(
            f"/api/v1/devices/{device.id}/control-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["code"] == 200
        items = data.get("data", {}).get("items", [])
        assert len(items) >= 1
        assert items[0]["action"] == "start"
        assert items[0]["result"] == "success"

    def test_get_control_history_nonexistent_device(self, client: TestClient, seed_users):
        """获取不存在设备的控制历史"""
        token = _get_token(client)
        
        response = client.get(
            "/api/v1/devices/99999/control-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"

    def test_get_control_history_unauthenticated(self, anon_client, seed_devices):
        """未认证用户无法查看控制历史"""
        device = seed_devices["chg001"]

        response = anon_client.get(
            f"/api/v1/devices/{device.id}/control-history",
        )
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}: {response.text}"


class TestDeviceControlLogModel:
    """DeviceControlLog 模型测试"""

    def test_create_control_log(self, client: TestClient, seed_users, seed_devices):
        """创建控制日志记录"""
        from datetime import datetime
        
        session = client._sesh
        device = seed_devices["chg001"]
        
        log = DeviceControlLog(
            device_id=device.id,
            device_name=device.name,
            action="start",
            parameter=None,
            value=None,
            params={"action": "start"},
            result="success",
            message="设备启动成功",
            operator="admin",
            operator_id=0,
        )
        session.add(log)
        session.commit()
        
        assert log.id is not None
        assert log.device_id == device.id
        assert log.action == "start"
        assert log.result == "success"
        assert log.created_at is not None
        
        # Test to_dict
        d = log.to_dict()
        assert d["action"] == "start"
        assert d["result"] == "success"
        assert d["device_name"] == device.name

    def test_control_log_to_dict(self):
        """测试 to_dict 方法"""
        log = DeviceControlLog(
            device_id=1,
            device_name="Test Device",
            action="stop",
            parameter="power_limit",
            value="50",
            params={"action": "set_param", "parameter": "power_limit", "value": "50"},
            result="success",
            message="参数设置成功",
            operator="admin",
            operator_id=0,
        )
        
        d = log.to_dict()
        assert d["device_id"] == 1
        assert d["action"] == "stop"
        assert d["parameter"] == "power_limit"
        assert d["value"] == "50"
        assert d["result"] == "success"
        assert d["params"] == {"action": "set_param", "parameter": "power_limit", "value": "50"}
        assert d["created_at"] is None  # not persisted yet


# ===========================================================================
# Unit tests for DeviceControlService — direct service-level coverage
# ===========================================================================

class TestDeviceControlServiceUnit:
    """DeviceControlService 的直接单元测试（不经过 API 层）"""

    def test_send_control_device_not_found(self):
        """设备不存在 → success=False"""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        svc = DeviceControlService(db)
        result = asyncio.run(
            svc.send_control(99999, {"register": 1, "value": 1})
        )
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_send_control_adapter_unavailable(self, seed_devices):
        """适配器不可用 → success=False"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {}
        device.protocol_type = MagicMock()
        device.protocol_type.value = "modbus_rtu"
        device.device_address = 1
        db.query.return_value.filter.return_value.first.return_value = device

        with patch("app.services.device_control_service.get_adapter", return_value=None):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.send_control(1, {"register": 1, "value": 1})
            )
        assert result["success"] is False
        assert "适配器" in result["error"]

    def test_send_control_write_fails(self):
        """适配器 write 返回 False → success=False"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(return_value=False)
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.send_control(1, {"register": 1, "value": 1})
            )
        assert result["success"] is False
        assert "失败" in result["error"]

    def test_send_control_write_raises_exception(self):
        """适配器 write 抛异常 → success=False, error 为通用消息(不泄露异常原文)"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(side_effect=ConnectionError("timeout"))
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.send_control(1, {"register": 1, "value": 1})
            )
        assert result["success"] is False
        # 安全：异常原文(timeout)不得泄露到 result.error，须返回通用消息
        assert "timeout" not in result["error"]
        assert result["error"] == "服务内部错误，请稍后重试"

    def test_send_control_success_path(self):
        """适配器 write 成功 → success=True"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.send_control(1, {"register": 1, "value": 1})
            )
        assert result["success"] is True
        assert result["device_id"] == 1

    # ---- reset_device ----

    def test_reset_device_soft(self):
        """软复位 → 构建 reset_soft 指令"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.reset_device(1, reset_type="soft")
            )
        assert result["success"] is True
        assert result["command"]["type"] == "reset_soft"
        assert result["command"]["value"] == 0x01

    def test_reset_device_hard(self):
        """硬复位 → 构建 reset_hard 指令"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.reset_device(1, reset_type="hard")
            )
        assert result["success"] is True
        assert result["command"]["type"] == "reset_hard"
        assert result["command"]["value"] == 0x02

    def test_reset_device_invalid_type(self):
        """未知复位类型 → success=False"""
        db = MagicMock()
        svc = DeviceControlService(db)
        result = asyncio.run(
            svc.reset_device(1, reset_type="unknown")
        )
        assert result["success"] is False
        assert "未知" in result["error"]

    # ---- set_parameter ----

    def test_set_parameter_unknown(self):
        """未知参数名 → success=False"""
        db = MagicMock()
        svc = DeviceControlService(db)
        result = asyncio.run(
            svc.set_parameter(1, "nonexistent_param", 100)
        )
        assert result["success"] is False
        assert "未知" in result["error"]

    def test_set_parameter_known(self):
        """已知参数 → 构建 param_set 指令并下发"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.set_parameter(1, "power_limit", 80)
            )
        assert result["success"] is True
        assert result["command"]["register"] == 1026
        assert result["command"]["value"] == 80

    # ---- get_control_history ----

    def test_get_control_history_operationlog_import_error_fallback_empty(self):
        """OperationLog 不可用 + Device 无 control_log → 返回空列表"""
        db = MagicMock()
        device = MagicMock()
        device.control_log = None
        # 第一次 query（OperationLog 路径触发 ImportError 后回退）→ Device 查询
        db.query.return_value.filter.return_value.first.return_value = device

        svc = DeviceControlService(db)
        result = svc.get_control_history(1)
        assert result == []

    def test_get_control_history_fallback_json_string(self):
        """control_log 为 JSON 字符串 → 解析后返回"""
        log_data = [{"action": "start", "result": "success"}]
        db = MagicMock()
        device = MagicMock()
        device.control_log = json.dumps(log_data)
        db.query.return_value.filter.return_value.first.return_value = device

        svc = DeviceControlService(db)
        result = svc.get_control_history(1)
        assert len(result) == 1
        assert result[0]["action"] == "start"

    def test_get_control_history_fallback_list(self):
        """control_log 为 list → 直接返回切片"""
        log_data = [{"action": f"cmd_{i}"} for i in range(5)]
        db = MagicMock()
        device = MagicMock()
        device.control_log = log_data
        db.query.return_value.filter.return_value.first.return_value = device

        svc = DeviceControlService(db)
        result = svc.get_control_history(1, limit=3)
        assert len(result) == 3

    def test_get_control_history_fallback_exception(self):
        """control_log 查询异常 → 返回空列表"""
        db = MagicMock()
        db.query.side_effect = Exception("DB exploded")

        svc = DeviceControlService(db)
        result = svc.get_control_history(1)
        assert result == []

    # ---- emergency_stop ----

    def test_emergency_stop_updates_device_status(self):
        """急停成功后更新设备状态为 maintenance"""
        db = MagicMock()
        device = MagicMock()
        device.device_type = "charger_dc"
        device.comm_config = {"device_address": 1}
        device.protocol_type = None
        device.device_address = None
        device.status = "online"
        # send_control 内部查 device → emergency_stop 再次查 device
        db.query.return_value.filter.return_value.first.return_value = device

        mock_adapter = AsyncMock()
        mock_adapter.write_command = AsyncMock(return_value=True)
        with patch("app.services.device_control_service.get_adapter", return_value=mock_adapter):
            svc = DeviceControlService(db)
            result = asyncio.run(
                svc.emergency_stop(1)
            )
        assert result["success"] is True
        assert device.status == "maintenance"
        db.commit.assert_called_once()
