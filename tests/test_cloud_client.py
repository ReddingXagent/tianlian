"""CloudClient 单元测试 — 边缘网关→云端对接验证"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.cloud_client import CloudClient
from config import CloudConfig
from models import TelemetryPoint


@pytest.fixture
def cloud_config():
    return CloudConfig(
        base_url="http://localhost:8000/api/v1",
        heartbeat_interval=0,  # 禁用心跳
        register_on_startup=False,
        deregister_on_shutdown=False,
    )


@pytest.fixture
def cloud_client(cloud_config):
    return CloudClient(cloud_config, gateway_id="GW-TEST")


@pytest.fixture
def telemetry_points():
    return [
        TelemetryPoint(device_id="CHG-001", power=60.5, voltage=400),
        TelemetryPoint(device_id="CHG-002", power=30.0, voltage=398),
    ]


# ── 注册/注销 ─────────────────────────────────────────────────────────

class TestCloudRegister:

    @pytest.mark.asyncio
    async def test_register_success(self, cloud_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=mock_resp)

        ok = await cloud_client.register()
        assert ok is True
        assert cloud_client._registered is True
        cloud_client._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_failure(self, cloud_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=mock_resp)

        ok = await cloud_client.register()
        assert ok is False
        assert cloud_client._registered is False

    @pytest.mark.asyncio
    async def test_register_network_error(self, cloud_client):
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(side_effect=httpx.ConnectError("nope"))

        ok = await cloud_client.register()
        assert ok is False

    @pytest.mark.asyncio
    async def test_deregister(self, cloud_client):
        cloud_client._registered = True
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=MagicMock(status_code=200))

        await cloud_client.deregister()
        assert cloud_client._registered is False

    @pytest.mark.asyncio
    async def test_deregister_not_registered(self, cloud_client):
        """未注册时不发注销请求"""
        cloud_client._client = AsyncMock()
        await cloud_client.deregister()
        cloud_client._client.post.assert_not_called()


# ── 遥测上报 ──────────────────────────────────────────────────────────

class TestCloudTelemetry:

    @pytest.mark.asyncio
    async def test_push_telemetry_success(self, cloud_client, telemetry_points):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=mock_resp)

        ok = await cloud_client.push_telemetry_batch(telemetry_points)
        assert ok is True

        # 验证payload格式 (V3对齐: pod_id + records)
        call_args = cloud_client._client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["pod_id"] == "GW-TEST"
        assert len(payload["records"]) == 2
        assert payload["records"][0]["device_id"] == "CHG-001"

    @pytest.mark.asyncio
    async def test_push_telemetry_empty(self, cloud_client):
        ok = await cloud_client.push_telemetry_batch([])
        assert ok is False

    @pytest.mark.asyncio
    async def test_push_telemetry_server_error(self, cloud_client, telemetry_points):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=mock_resp)

        ok = await cloud_client.push_telemetry_batch(telemetry_points)
        assert ok is False

    @pytest.mark.asyncio
    async def test_push_telemetry_network_error(self, cloud_client, telemetry_points):
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        ok = await cloud_client.push_telemetry_batch(telemetry_points)
        assert ok is False


# ── 告警上报 ──────────────────────────────────────────────────────────

class TestCloudAlarm:

    @pytest.mark.asyncio
    async def test_push_alarm_success(self, cloud_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=mock_resp)

        ok = await cloud_client.push_alarm("CHG-001", "over_temp", "critical", "Too hot")
        assert ok is True

    @pytest.mark.asyncio
    async def test_push_alarm_failure(self, cloud_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        cloud_client._client = AsyncMock()
        cloud_client._client.post = AsyncMock(return_value=mock_resp)

        ok = await cloud_client.push_alarm("CHG-001", "over_temp", "critical", "Too hot")
        assert ok is False


# ── 生命周期 ──────────────────────────────────────────────────────────

class TestCloudLifecycle:

    @pytest.mark.asyncio
    async def test_start_no_register(self, cloud_config):
        cloud_config.register_on_startup = False
        cloud_config.heartbeat_interval = 0
        client = CloudClient(cloud_config, "GW-LC")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await client.start()
            assert client._client is not None

    @pytest.mark.asyncio
    async def test_heartbeat_loop_cancelled(self, cloud_config):
        cloud_config.heartbeat_interval = 0  # no heartbeat
        client = CloudClient(cloud_config, "GW-HB")
        await client.start()
        assert client._heartbeat_task is None
        await client.stop()
