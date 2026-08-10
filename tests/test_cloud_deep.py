"""Deep coverage for cloud_client: register/deregister, heartbeat loop,
push_alarm/push_alarm_batch, _post_with_retry gzip, cache_sync loops,
_fetch_csrf_token, edge cases.

Targeting: L87, L142-148, L167-169, L184-185, L237, L269-294,
L312-316, L370-392, L422-423, L428, L456
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.cloud_client import CloudClient, _to_int_id
from config import CloudConfig
from models import TelemetryPoint


@pytest.fixture
def cloud_config():
    return CloudConfig(
        base_url="http://localhost:8000/api/v1",
        heartbeat_interval=0,
        register_on_startup=False,
        deregister_on_shutdown=False,
    )


@pytest.fixture
def cc(cloud_config):
    """CloudClient with mocked httpx client"""
    client = CloudClient(cloud_config, gateway_id="GW-TEST")
    client._client = MagicMock(spec=httpx.AsyncClient)
    return client


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


# ── _to_int_id helper ───────────────────────────────────────────────

class TestToIntId:
    def test_numeric_string(self):
        assert _to_int_id("42") == 42

    def test_non_numeric_string(self):
        assert _to_int_id("abc") == 1

    def test_none(self):
        assert _to_int_id(None) == 1

    def test_integer(self):
        assert _to_int_id(99) == 99


# ── _fetch_csrf_token (L87) ─────────────────────────────────────────

class TestFetchCsrfToken:
    @pytest.mark.asyncio
    async def test_fetch_csrf_success(self, cc):
        """CSRF token acquired from health endpoint"""
        cc._client.get = AsyncMock(return_value=_mock_response(
            200, cookies={"tianlian_csrf_token": "csrf_abc"}
        ))
        await cc._fetch_csrf_token()
        assert cc._csrf_token == "csrf_abc"

    @pytest.mark.asyncio
    async def test_fetch_csrf_no_cookie(self, cc):
        """No CSRF cookie in response"""
        cc._client.get = AsyncMock(return_value=_mock_response(200))
        await cc._fetch_csrf_token()
        assert cc._csrf_token == ""

    @pytest.mark.asyncio
    async def test_fetch_csrf_exception(self, cc):
        """Network error during CSRF fetch"""
        cc._client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        await cc._fetch_csrf_token()
        assert cc._csrf_token == ""


# ── register: pod already exists (L142-148) ─────────────────────────

class TestRegisterPodExists:
    @pytest.mark.asyncio
    async def test_register_pod_already_exists(self, cc):
        """Register finds existing pod and returns True"""
        pod_data = {"pods": [{"pod_id": "GW-TEST", "status": "online"}]}
        cc._client.get = AsyncMock(return_value=_mock_response(200, json_data=pod_data))

        result = await cc.register()
        assert result is True
        assert cc._registered is True

    @pytest.mark.asyncio
    async def test_register_pod_data_nested(self, cc):
        """Register handles nested data.pods structure"""
        pod_data = {"data": {"pods": [{"pod_id": "GW-TEST"}]}}
        cc._client.get = AsyncMock(return_value=_mock_response(200, json_data=pod_data))

        result = await cc.register()
        assert result is True

    @pytest.mark.asyncio
    async def test_register_new_pod_success(self, cc):
        """Register creates new pod"""
        cc._client.get = AsyncMock(return_value=_mock_response(200, json_data={"pods": []}))
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        result = await cc.register()
        assert result is True
        assert cc._registered is True

    @pytest.mark.asyncio
    async def test_register_single_pod_mode(self, cc):
        """Register handles single-pod mode rejection"""
        cc._client.get = AsyncMock(return_value=_mock_response(200, json_data={"pods": []}))
        cc._client.post = AsyncMock(return_value=_mock_response(
            400, text="单Pod模式 not supported"
        ))

        result = await cc.register()
        assert result is True  # single-pod mode = already registered

    @pytest.mark.asyncio
    async def test_register_failure(self, cc):
        """Register fails with non-single-pod error"""
        cc._client.get = AsyncMock(return_value=_mock_response(200, json_data={"pods": []}))
        cc._client.post = AsyncMock(return_value=_mock_response(500, text="Internal error"))

        result = await cc.register()
        assert result is False

    @pytest.mark.asyncio
    async def test_register_exception(self, cc):
        """Register handles network exception"""
        cc._client.get = AsyncMock(side_effect=httpx.ConnectError("network down"))

        result = await cc.register()
        assert result is False

    @pytest.mark.asyncio
    async def test_register_with_pod_secret(self, cc):
        """Register includes pod_secret when configured"""
        cc.config.pod_secret = "secret123"
        cc._client.get = AsyncMock(return_value=_mock_response(200, json_data={"pods": []}))
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        await cc.register()
        call_kwargs = cc._client.post.call_args[1]
        assert call_kwargs["json"]["pod_secret"] == "secret123"


# ── deregister (L167-169) ───────────────────────────────────────────

class TestDeregister:
    @pytest.mark.asyncio
    async def test_deregister_not_registered(self, cc):
        """Deregister when not registered is a no-op"""
        cc._registered = False
        await cc.deregister()  # should not raise
        assert cc._registered is False

    @pytest.mark.asyncio
    async def test_deregister_registered(self, cc):
        """Deregister when registered clears state"""
        cc._registered = True
        await cc.deregister()
        assert cc._registered is False


# ── push_telemetry_batch edge cases (L184-185) ──────────────────────

class TestPushTelemetryEdge:
    @pytest.mark.asyncio
    async def test_push_no_client(self, cc):
        """push_telemetry_batch returns False without client"""
        cc._client = None
        result = await cc.push_telemetry_batch([_make_point()])
        assert result is False

    @pytest.mark.asyncio
    async def test_push_empty_points(self, cc):
        """push_telemetry_batch returns False for empty list"""
        result = await cc.push_telemetry_batch([])
        assert result is False

    @pytest.mark.asyncio
    async def test_push_fail_no_cache(self, cc):
        """push failure with no cache returns False"""
        cc.cache = None
        cc._client.post = AsyncMock(return_value=_mock_response(500))
        result = await cc.push_telemetry_batch([_make_point()])
        assert result is False


# ── push_alarm single (L237) ────────────────────────────────────────

class TestPushAlarmSingle:
    @pytest.mark.asyncio
    async def test_push_alarm_success(self, cc):
        cc._client.post = AsyncMock(return_value=_mock_response(200))
        result = await cc.push_alarm("DEV-1", "overtemp", "critical", "too hot")
        assert result is True

    @pytest.mark.asyncio
    async def test_push_alarm_no_client(self, cc):
        cc._client = None
        result = await cc.push_alarm("DEV-1", "test", "warning", "msg")
        assert result is False

    @pytest.mark.asyncio
    async def test_push_alarm_fail_with_cache(self, cc):
        """Failed push caches alarm when cache available"""
        mock_cache = MagicMock()
        cc.cache = mock_cache
        cc._client.post = AsyncMock(return_value=_mock_response(500))
        result = await cc.push_alarm("DEV-1", "overtemp", "critical", "hot")
        assert result is False
        mock_cache.cache_alarm.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_alarm_fail_no_cache(self, cc):
        cc.cache = None
        cc._client.post = AsyncMock(return_value=_mock_response(500))
        result = await cc.push_alarm("DEV-1", "overtemp", "critical", "hot")
        assert result is False


# ── push_alarm_batch full (L269-294) ────────────────────────────────

class TestPushAlarmBatch:
    @pytest.mark.asyncio
    async def test_batch_all_success(self, cc):
        cc._client.post = AsyncMock(return_value=_mock_response(200))
        alarms = [
            {"device_id": "D1", "alarm_type": "t1", "severity": "warn", "message": "m1"},
            {"device_id": "D2", "alarm_type": "t2", "severity": "crit", "message": "m2"},
        ]
        result = await cc.push_alarm_batch(alarms)
        assert result is True
        assert cc._client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_batch_partial_fail_with_cache(self, cc):
        """Partial failure caches failed alarms"""
        mock_cache = MagicMock()
        cc.cache = mock_cache
        cc._client.post = AsyncMock(side_effect=[
            _mock_response(200),
            _mock_response(500),
        ])
        alarms = [
            {"device_id": "D1", "alarm_type": "t1", "severity": "warn", "message": "m1"},
            {"device_id": "D2", "alarm_type": "t2", "severity": "crit", "message": "m2"},
        ]
        result = await cc.push_alarm_batch(alarms)
        assert result is False
        mock_cache.cache_alarm.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_no_client(self, cc):
        cc._client = None
        result = await cc.push_alarm_batch([{"device_id": "D1"}])
        assert result is False

    @pytest.mark.asyncio
    async def test_batch_empty(self, cc):
        result = await cc.push_alarm_batch([])
        assert result is False

    @pytest.mark.asyncio
    async def test_batch_all_fail_no_cache(self, cc):
        cc.cache = None
        cc._client.post = AsyncMock(return_value=_mock_response(500))
        alarms = [{"device_id": "D1", "alarm_type": "t", "severity": "s", "message": "m"}]
        result = await cc.push_alarm_batch(alarms)
        assert result is False


# ── _post_with_retry gzip path (L312-316) ───────────────────────────

class TestPostWithRetryGzip:
    @pytest.mark.asyncio
    async def test_gzip_rejected_then_plain_retry(self, cc):
        """gzip rejected with 4xx → disable gzip, retry plain"""
        cc.config.compress_enabled = True
        cc.config.compress_threshold = 10  # small threshold for testing
        cc._token = "test_token"
        cc._csrf_token = "csrf"

        call_count = 0
        captured_headers = []

        async def mock_post(path, content=None, headers=None):
            nonlocal call_count
            call_count += 1
            captured_headers.append(dict(headers) if headers else {})
            if call_count == 1:
                return _mock_response(400, text="gzip not supported")
            return _mock_response(200)

        cc._client.post = mock_post

        result = await cc._post_with_retry("/test", {"data": "x" * 100}, "test_op")
        assert result is True
        assert call_count == 2
        assert "gzip" in captured_headers[0].get("Content-Encoding", "")
        assert "Content-Encoding" not in captured_headers[1]

    @pytest.mark.asyncio
    async def test_gzip_compressed_body(self, cc):
        """Verify gzip body is actually compressed"""
        cc.config.compress_enabled = True
        cc.config.compress_threshold = 10
        cc._token = "tok"

        captured_body = None

        async def mock_post(path, content=None, headers=None):
            nonlocal captured_body
            captured_body = content
            return _mock_response(200)

        cc._client.post = mock_post

        payload = {"data": "x" * 200}
        await cc._post_with_retry("/test", payload, "test_op")

        # Body should be gzip-compressed (starts with gzip magic bytes)
        assert captured_body[:2] == b'\x1f\x8b'

    @pytest.mark.asyncio
    async def test_4xx_no_gzip_returns_false(self, cc):
        """4xx without gzip returns False immediately"""
        cc._token = "tok"
        cc._client.post = AsyncMock(return_value=_mock_response(403, text="Forbidden"))
        result = await cc._post_with_retry("/test", {"data": "x"}, "test_op")
        assert result is False

    @pytest.mark.asyncio
    async def test_5xx_retries(self, cc):
        """5xx triggers retries"""
        cc._token = "tok"
        cc.RETRY_BASE_DELAY = 0.001  # speed up test
        cc._client.post = AsyncMock(return_value=_mock_response(503, text="Unavailable"))
        result = await cc._post_with_retry("/test", {"data": "x"}, "test_op")
        assert result is False
        assert cc._client.post.await_count == cc.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_connect_error_retries(self, cc):
        """ConnectError triggers retries"""
        cc._token = "tok"
        cc.RETRY_BASE_DELAY = 0.001
        cc._client.post = AsyncMock(side_effect=httpx.ConnectError("network down"))
        result = await cc._post_with_retry("/test", {"data": "x"}, "test_op")
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_retries(self, cc):
        """TimeoutException triggers retries"""
        cc._token = "tok"
        cc.RETRY_BASE_DELAY = 0.001
        cc._client.post = AsyncMock(side_effect=httpx.TimeoutException("slow"))
        result = await cc._post_with_retry("/test", {"data": "x"}, "test_op")
        assert result is False

    @pytest.mark.asyncio
    async def test_generic_exception_retries(self, cc):
        """Generic exception triggers retries"""
        cc._token = "tok"
        cc.RETRY_BASE_DELAY = 0.001
        cc._client.post = AsyncMock(side_effect=RuntimeError("unexpected"))
        result = await cc._post_with_retry("/test", {"data": "x"}, "test_op")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_token_no_csrf(self, cc):
        """Works without token and csrf"""
        cc._token = None
        cc._csrf_token = ""
        cc._client.post = AsyncMock(return_value=_mock_response(200))
        result = await cc._post_with_retry("/test", {"data": "x"}, "test_op")
        assert result is True


# ── _heartbeat_loop (L370-392) ──────────────────────────────────────

class TestHeartbeatLoop:
    @pytest.mark.asyncio
    async def test_heartbeat_loop_success(self, cc):
        """Heartbeat loop sends heartbeat and continues"""
        cc.config.heartbeat_interval = 0.02
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        # Run for a short time then cancel
        task = asyncio.create_task(cc._heartbeat_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert cc._client.post.await_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_loop_non_200(self, cc):
        """Heartbeat logs warning on non-200"""
        cc.config.heartbeat_interval = 0.02
        cc._client.post = AsyncMock(return_value=_mock_response(500))

        task = asyncio.create_task(cc._heartbeat_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_heartbeat_loop_exception(self, cc):
        """Heartbeat handles network exception"""
        cc.config.heartbeat_interval = 0.02
        cc._client.post = AsyncMock(side_effect=httpx.ConnectError("down"))

        task = asyncio.create_task(cc._heartbeat_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_heartbeat_with_pod_secret(self, cc):
        """Heartbeat includes pod_secret when configured"""
        cc.config.heartbeat_interval = 0.02
        cc.config.pod_secret = "secret456"
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        task = asyncio.create_task(cc._heartbeat_loop())
        await asyncio.sleep(0.08)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        call_kwargs = cc._client.post.call_args[1]
        assert call_kwargs["json"]["pod_secret"] == "secret456"


# ── _cache_sync_loop (L422-423, L428) ───────────────────────────────

class TestCacheSyncLoop:
    @pytest.mark.asyncio
    async def test_cache_sync_loop_idle(self, cc):
        """Cache sync loop runs idle cycle"""
        cc.cache = MagicMock()
        cc.cache.get_cloud_unsynced_alarms = MagicMock(return_value=[])
        cc.cache.get_cloud_unsynced = MagicMock(return_value=[])

        task = asyncio.create_task(cc._cache_sync_loop())
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_cache_sync_loop_with_data(self, cc):
        """Cache sync loop processes data"""
        cc.cache = MagicMock()
        cc.cache.get_cloud_unsynced_alarms = MagicMock(return_value=[
            {"id": 1, "payload": {"device_id": "D1", "alarm_type": "t", "message": "m", "severity": "s"}}
        ])
        cc.cache.get_cloud_unsynced = MagicMock(return_value=[])
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        task = asyncio.create_task(cc._cache_sync_loop())
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_cache_sync_loop_exception(self, cc):
        """Cache sync loop handles exceptions"""
        cc.cache = MagicMock()
        cc.cache.get_cloud_unsynced_alarms = MagicMock(side_effect=RuntimeError("db error"))

        task = asyncio.create_task(cc._cache_sync_loop())
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ── _sync_cached_alarms (L456) ──────────────────────────────────────

class TestSyncCachedAlarms:
    @pytest.mark.asyncio
    async def test_sync_alarms_no_cache(self, cc):
        """Returns 0 without cache"""
        cc.cache = None
        result = await cc._sync_cached_alarms()
        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_alarms_no_client(self, cc):
        """Returns 0 without client"""
        cc.cache = MagicMock()
        cc._client = None
        result = await cc._sync_cached_alarms()
        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_alarms_empty(self, cc):
        """Returns 0 when no unsynced alarms"""
        cc.cache = MagicMock()
        cc.cache.get_cloud_unsynced_alarms = MagicMock(return_value=[])
        result = await cc._sync_cached_alarms()
        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_alarms_all_success(self, cc):
        """All alarms synced successfully"""
        cc.cache = MagicMock()
        items = [
            {"id": 1, "payload": {"device_id": "D1", "alarm_type": "t1", "message": "m1", "severity": "s1"}},
            {"id": 2, "payload": {"device_id": "D2", "alarm_type": "t2", "message": "m2", "severity": "s2"}},
        ]
        cc.cache.get_cloud_unsynced_alarms = MagicMock(return_value=items)
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        result = await cc._sync_cached_alarms()
        assert result == 2
        cc.cache.mark_alarms_cloud_synced.assert_called_once_with([1, 2])

    @pytest.mark.asyncio
    async def test_sync_alarms_partial_fail(self, cc):
        """Partial failure: some synced, some retried"""
        cc.cache = MagicMock()
        items = [
            {"id": 1, "payload": {"device_id": "D1", "alarm_type": "t1", "message": "m1", "severity": "s1"}},
            {"id": 2, "payload": {"device_id": "D2", "alarm_type": "t2", "message": "m2", "severity": "s2"}},
        ]
        cc.cache.get_cloud_unsynced_alarms = MagicMock(return_value=items)
        cc._client.post = AsyncMock(side_effect=[
            _mock_response(200),
            _mock_response(500),
        ])

        result = await cc._sync_cached_alarms()
        assert result == 1
        cc.cache.mark_alarms_cloud_synced.assert_called_once_with([1])
        cc.cache.increment_alarm_retry.assert_called_once_with([2])

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_success(self, cc):
        """Telemetry cache sync success path"""
        cc.cache = MagicMock()
        items = [
            {"id": 1, "payload": {"device_id": "D1", "power": 10}},
        ]
        cc.cache.get_cloud_unsynced = MagicMock(return_value=items)
        cc._client.post = AsyncMock(return_value=_mock_response(200))

        result = await cc._sync_cached_telemetry()
        assert result == 1
        cc.cache.mark_cloud_synced.assert_called_once_with([1])

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_fail(self, cc):
        """Telemetry cache sync failure increments retry"""
        cc.cache = MagicMock()
        items = [{"id": 1, "payload": {"device_id": "D1"}}]
        cc.cache.get_cloud_unsynced = MagicMock(return_value=items)
        cc._client.post = AsyncMock(return_value=_mock_response(500))

        result = await cc._sync_cached_telemetry()
        assert result == 0
        cc.cache.increment_retry.assert_called_once_with([1])

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_no_cache(self, cc):
        cc.cache = None
        assert await cc._sync_cached_telemetry() == 0

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_empty(self, cc):
        cc.cache = MagicMock()
        cc.cache.get_cloud_unsynced = MagicMock(return_value=[])
        assert await cc._sync_cached_telemetry() == 0


# ── start() integration with mocked httpx ───────────────────────────

class TestStartIntegration:
    @pytest.mark.asyncio
    async def test_start_full_flow(self, cc):
        """start() initializes client, fetches CSRF, registers, starts heartbeat"""
        cc.config.register_on_startup = True
        cc.config.heartbeat_interval = 0.05

        with patch("httpx.AsyncClient") as mock_httpx_cls:
            mock_http = MagicMock()
            mock_http.get = AsyncMock(return_value=_mock_response(
                200, cookies={"tianlian_csrf_token": "csrf_test"}
            ))
            mock_http.post = AsyncMock(return_value=_mock_response(200))
            mock_http.aclose = AsyncMock()
            mock_httpx_cls.return_value = mock_http

            await cc.start()
            assert cc._token is None or cc._token == ""
            assert cc._registered is True
            assert cc._heartbeat_task is not None
            assert cc._sync_task is None  # no cache, so no sync task

            await cc.stop()

    @pytest.mark.asyncio
    async def test_start_no_register_no_heartbeat(self, cc):
        """start() without register/heartbeat"""
        cc.config.register_on_startup = False
        cc.config.heartbeat_interval = 0

        with patch("httpx.AsyncClient") as mock_httpx_cls:
            mock_http = MagicMock()
            mock_http.get = AsyncMock(return_value=_mock_response(200))
            mock_http.aclose = AsyncMock()
            mock_httpx_cls.return_value = mock_http

            await cc.start()
            assert cc._heartbeat_task is None

            await cc.stop()


# ── _get_local_ip ───────────────────────────────────────────────────

class TestGetLocalIp:
    def test_get_local_ip(self, cc):
        """_get_local_ip returns a string IP"""
        ip = cc._get_local_ip()
        assert isinstance(ip, str)
        # Should be an IP-like address or fallback
        assert len(ip) > 0


# ── pod_id property ─────────────────────────────────────────────────

class TestPodId:
    def test_pod_id_equals_gateway_id(self, cc):
        assert cc.pod_id == "GW-TEST"
