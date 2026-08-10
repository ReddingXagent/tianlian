"""Final coverage push for cloud_client: targeting L87, L97, L120-122, L125,
L184-185, L220-221.

Uncovered lines:
- L87:   self._token = self.config.token (in start() when token set)
- L97:   self._sync_task = create_task(self._cache_sync_loop()) (start with cache)
- L120-122: stop() sync_task cancel + suppress CancelledError
- L125:    stop() deregister_on_shutdown path
- L184-185: _get_local_ip socket success path
- L220-221: push_telemetry_batch failure → cache fallback path
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.cloud_client import CloudClient
from config import CloudConfig
from models import TelemetryPoint


def _make_point(device_id="DEV-1", power=10.0):
    return TelemetryPoint(
        device_id=device_id, power=power, voltage=380.0, current=15.0,
        temperature=35.0, energy=100.0, soc=80.0, status="charging",
    )


def _mock_response(status_code=200, json_data=None, text="", cookies=None):
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.text = text or ""
    if json_data is not None:
        r.json.return_value = json_data
    r.cookies = cookies or {}
    return r


# ── L87: start() sets token from config ─────────────────────────────

class TestStartSetsToken:
    @pytest.mark.asyncio
    async def test_start_sets_token(self):
        """L87: start() should set self._token from config.token"""
        cfg = CloudConfig(
            base_url="http://localhost:8000/api/v1",
            token="my-secret-token",
            heartbeat_interval=0,
            register_on_startup=False,
            deregister_on_shutdown=False,
        )
        client = CloudClient(cfg, gateway_id="GW-TOKEN")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = MagicMock()
            mock_http.get = AsyncMock(return_value=_mock_response(200))
            mock_http.aclose = AsyncMock()
            mock_cls.return_value = mock_http

            await client.start()
            assert client._token == "my-secret-token"
            await client.stop()


# ── L97 + L120-122: start() with cache creates sync_task, stop() cancels it ──

class TestStartWithCacheSyncTask:
    @pytest.mark.asyncio
    async def test_start_creates_sync_task_and_stop_cancels(self):
        """L97: start() with cache creates _sync_task
        L120-122: stop() cancels _sync_task with CancelledError suppress"""
        cfg = CloudConfig(
            base_url="http://localhost:8000/api/v1",
            heartbeat_interval=0,
            register_on_startup=False,
            deregister_on_shutdown=False,
        )
        mock_cache = MagicMock()
        mock_cache.get_cloud_unsynced_alarms = MagicMock(return_value=[])
        mock_cache.get_cloud_unsynced = MagicMock(return_value=[])

        client = CloudClient(cfg, gateway_id="GW-SYNC", cache=mock_cache)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = MagicMock()
            mock_http.get = AsyncMock(return_value=_mock_response(200))
            mock_http.aclose = AsyncMock()
            mock_cls.return_value = mock_http

            await client.start()
            assert client._sync_task is not None
            assert not client._sync_task.done()  # task running

            await client.stop()
            # After stop, sync_task should be cancelled
            # The cancel + suppress(CancelledError) path (L120-122) is now covered


# ── L125: stop() with deregister_on_shutdown ────────────────────────

class TestStopDeregisterOnShutdown:
    @pytest.mark.asyncio
    async def test_stop_deregisters(self):
        """L125: stop() calls deregister when deregister_on_shutdown=True"""
        cfg = CloudConfig(
            base_url="http://localhost:8000/api/v1",
            heartbeat_interval=0,
            register_on_startup=False,
            deregister_on_shutdown=True,
        )
        client = CloudClient(cfg, gateway_id="GW-DEREG")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = MagicMock()
            mock_http.get = AsyncMock(return_value=_mock_response(200))
            mock_http.aclose = AsyncMock()
            mock_cls.return_value = mock_http

            await client.start()
            client._registered = True  # simulate active registration

            await client.stop()
            # deregister() was called → _registered set to False
            assert client._registered is False


# ── L184-185: _get_local_ip socket success path ────────────────────

class TestGetLocalIpSocketSuccess:
    def test_get_local_ip_real_socket(self):
        """L184-185: _get_local_ip via real socket connection"""
        cfg = CloudConfig(
            base_url="http://localhost:8000/api/v1",
            heartbeat_interval=0,
            register_on_startup=False,
            deregister_on_shutdown=False,
        )
        client = CloudClient(cfg, gateway_id="GW-IP")

        # Call without mocking socket — actual UDP socket to 8.8.8.8:80
        # In WSL this should succeed and return a real IP
        ip = client._get_local_ip()
        assert isinstance(ip, str)
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_get_local_ip_socket_exception(self):
        """L184-185 fallback: socket raises → return default IP"""
        cfg = CloudConfig(
            base_url="http://localhost:8000/api/v1",
            heartbeat_interval=0,
            register_on_startup=False,
            deregister_on_shutdown=False,
        )
        client = CloudClient(cfg, gateway_id="GW-IP2")

        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = OSError("no network")
            mock_sock_cls.return_value = mock_sock

            ip = client._get_local_ip()
            assert ip == "192.168.31.10"


# ── L220-221: push_telemetry_batch failure → cache fallback ─────────

class TestPushTelemetryCacheFallback:
    @pytest.mark.asyncio
    async def test_push_telemetry_fail_with_cache(self):
        """L220-221: push_telemetry_batch failure writes to cache"""
        cfg = CloudConfig(
            base_url="http://localhost:8000/api/v1",
            heartbeat_interval=0,
            register_on_startup=False,
            deregister_on_shutdown=False,
        )
        mock_cache = MagicMock()
        client = CloudClient(cfg, gateway_id="GW-CACHE", cache=mock_cache)
        client._client = MagicMock(spec=httpx.AsyncClient)

        # Make all retries fail (5xx)
        client._client.post = AsyncMock(return_value=_mock_response(500))
        client.RETRY_BASE_DELAY = 0.001  # speed up

        points = [_make_point("D1"), _make_point("D2")]
        result = await client.push_telemetry_batch(points)
        assert result is False
        # Cache fallback should have been called
        mock_cache.cache_telemetry_batch.assert_called_once_with(points)
