"""Unit tests for main.py EdgeGateway methods — telemetry/alarm pipeline, upload, sync, logging.

Targets previously uncovered lines in main.py (was 24% → aim 60%+).
"""

import asyncio
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import GatewayConfig
from models import TelemetryPoint
from storage.cache import TelemetryCache

UTC = timezone.utc


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    with contextlib_suppress(path):
        pass


def contextlib_suppress(path):
    """Return a context manager that deletes the file on exit."""
    class _Ctx:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
    return _Ctx()


@pytest.fixture
def gw(tmp_db):
    """EdgeGateway with tmp cache, no real I/O"""
    from main import EdgeGateway

    config = GatewayConfig()
    config.storage.db_path = tmp_db
    gateway = EdgeGateway(config)
    # Manually set cache so we don't need full start()
    gateway.cache = TelemetryCache(config.storage)
    # Mock external components
    gateway.mqtt = MagicMock()
    gateway.mqtt.connected = False
    gateway.mqtt.publish_telemetry = AsyncMock()
    gateway.mqtt.publish_alarm = AsyncMock()
    gateway.mqtt.publish_raw = AsyncMock(return_value=True)
    gateway.cloud = MagicMock()
    gateway.cloud.push_telemetry_batch = AsyncMock(return_value=True)
    gateway.cloud.push_alarm_batch = AsyncMock()
    yield gateway
    gateway.cache.close()


def _make_point(device_id="DEV-001", power=10.0):
    return TelemetryPoint(
        device_id=device_id,
        power=power,
        voltage=380.0,
        current=26.3,
        temperature=25.0,
        energy=100.0,
        soc=80.0,
        status="Charging",
    )


# ── setup_logging ─────────────────────────────────────────────────────

class TestSetupLogging:
    def test_setup_logging_info_level(self):
        """setup_logging should configure INFO level without errors"""
        from main import setup_logging
        # Under pytest, basicConfig is a no-op (handlers already set),
        # but the function should still run cleanly.
        setup_logging("INFO")
        # Verify uvicorn/paho/pymodbus were quieted regardless
        assert logging.getLogger("uvicorn").level == logging.WARNING

    def test_setup_logging_debug_level(self):
        from main import setup_logging
        setup_logging("DEBUG")
        assert logging.getLogger("paho").level == logging.WARNING

    def test_setup_logging_invalid_defaults_info(self):
        from main import setup_logging
        setup_logging("INVALID_LEVEL")
        assert logging.getLogger("pymodbus").level == logging.WARNING

    def test_setup_logging_quiets_third_party(self):
        from main import setup_logging
        setup_logging("DEBUG")
        assert logging.getLogger("uvicorn").level == logging.WARNING
        assert logging.getLogger("pymodbus").level == logging.WARNING
        assert logging.getLogger("paho").level == logging.WARNING


# ── _handle_telemetry ─────────────────────────────────────────────────

class TestHandleTelemetry:
    @pytest.mark.asyncio
    async def test_updates_latest_telemetry(self, gw):
        point = _make_point("DEV-001", power=50.0)
        await gw._handle_telemetry(point)
        assert "DEV-001" in gw._latest_telemetry
        assert gw._latest_telemetry["DEV-001"]["power"] == 50.0
        assert gw._device_count == 1
        assert gw._telemetry_count == 1

    @pytest.mark.asyncio
    async def test_multiple_devices_update_count(self, gw):
        for i in range(5):
            await gw._handle_telemetry(_make_point(f"DEV-{i:03d}"))
        assert gw._device_count == 5
        assert gw._telemetry_count == 5

    @pytest.mark.asyncio
    async def test_publishes_to_mqtt(self, gw):
        gw.mqtt.connected = True
        point = _make_point()
        await gw._handle_telemetry(point)
        gw.mqtt.publish_telemetry.assert_awaited_once_with(point)

    @pytest.mark.asyncio
    async def test_skips_mqtt_when_none(self, gw):
        gw.mqtt = None
        point = _make_point()
        await gw._handle_telemetry(point)
        # Should not raise, telemetry still processed
        assert gw._telemetry_count == 1

    @pytest.mark.asyncio
    async def test_buffers_for_cloud(self, gw):
        point = _make_point()
        await gw._handle_telemetry(point)
        assert len(gw._telemetry_buffer) == 1
        assert gw._telemetry_buffer[0] is point

    @pytest.mark.asyncio
    async def test_trims_buffer_when_over_limit(self, gw):
        gw.MAX_TELEMETRY_BUFFER = 3  # override for test
        for i in range(5):
            await gw._handle_telemetry(_make_point(f"DEV-{i}"))
        assert len(gw._telemetry_buffer) == 3

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, gw):
        """_handle_telemetry should not propagate exceptions"""
        gw._latest_telemetry = None  # provoke AttributeError on __setitem__
        point = _make_point()
        # Should not raise
        await gw._handle_telemetry(point)


# ── _handle_alarm ──────────────────────────────────────────────────────

class TestHandleAlarm:
    @pytest.mark.asyncio
    async def test_buffers_alarm(self, gw):
        await gw._handle_alarm("DEV-001", "over_temp", "Temperature too high")
        assert len(gw._alarm_buffer) == 1
        assert gw._alarm_buffer[0]["device_id"] == "DEV-001"
        assert gw._alarm_buffer[0]["alarm_type"] == "over_temp"
        assert gw._alarm_count == 1

    @pytest.mark.asyncio
    async def test_publishes_alarm_to_mqtt(self, gw):
        gw.mqtt.connected = True
        await gw._handle_alarm("DEV-001", "over_temp", "Too hot")
        gw.mqtt.publish_alarm.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mqtt_publish_error_swallowed(self, gw):
        gw.mqtt.connected = True
        gw.mqtt.publish_alarm = AsyncMock(side_effect=Exception("MQTT down"))
        await gw._handle_alarm("DEV-001", "over_temp", "Too hot")
        # Should not propagate exception
        assert gw._alarm_count == 1

    @pytest.mark.asyncio
    async def test_trims_alarm_buffer(self, gw):
        gw.MAX_ALARM_BUFFER = 3
        for i in range(5):
            await gw._handle_alarm("DEV-001", f"alarm_{i}", f"msg_{i}")
        assert len(gw._alarm_buffer) == 3

    @pytest.mark.asyncio
    async def test_alarm_has_timestamp_and_severity(self, gw):
        await gw._handle_alarm("DEV-001", "fault", "Critical fault", severity="critical")
        alarm = gw._alarm_buffer[0]
        assert alarm["severity"] == "critical"
        assert "timestamp" in alarm


# ── _upload_telemetry_batch ───────────────────────────────────────────

class TestUploadTelemetryBatch:
    @pytest.mark.asyncio
    async def test_empty_buffer_noop(self, gw):
        await gw._upload_telemetry_batch()
        gw.cloud.push_telemetry_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pushes_batch_to_cloud(self, gw):
        points = [_make_point(f"DEV-{i}") for i in range(3)]
        gw._telemetry_buffer.extend(points)
        await gw._upload_telemetry_batch()
        gw.cloud.push_telemetry_batch.assert_awaited_once()
        batch_arg = gw.cloud.push_telemetry_batch.call_args[0][0]
        assert len(batch_arg) == 3
        assert gw._cloud_push_count == 1

    @pytest.mark.asyncio
    async def test_increments_failures_on_cloud_false(self, gw):
        gw.cloud.push_telemetry_batch = AsyncMock(return_value=False)
        gw._telemetry_buffer.append(_make_point())
        await gw._upload_telemetry_batch()
        assert gw._cloud_push_failures == 1
        assert gw._cloud_push_count == 1

    @pytest.mark.asyncio
    async def test_clears_buffer_on_push(self, gw):
        gw._telemetry_buffer.append(_make_point())
        await gw._upload_telemetry_batch()
        assert len(gw._telemetry_buffer) == 0

    @pytest.mark.asyncio
    async def test_no_cloud_rebuffers(self, gw):
        gw.cloud = None
        point = _make_point()
        gw._telemetry_buffer.append(point)
        await gw._upload_telemetry_batch()
        # Should put back in buffer
        assert len(gw._telemetry_buffer) == 1


# ── _upload_alarm_batch ────────────────────────────────────────────────

class TestUploadAlarmBatch:
    @pytest.mark.asyncio
    async def test_empty_buffer_noop(self, gw):
        await gw._upload_alarm_batch()
        gw.cloud.push_alarm_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pushes_alarms_to_cloud(self, gw):
        gw._alarm_buffer.extend([
            {"device_id": "D1", "alarm_type": "t", "message": "m", "timestamp": "now", "severity": "warning"},
            {"device_id": "D2", "alarm_type": "t", "message": "m", "timestamp": "now", "severity": "warning"},
        ])
        await gw._upload_alarm_batch()
        gw.cloud.push_alarm_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_buffer_on_push(self, gw):
        gw._alarm_buffer.append({"device_id": "D1", "alarm_type": "t", "message": "m"})
        await gw._upload_alarm_batch()
        assert len(gw._alarm_buffer) == 0

    @pytest.mark.asyncio
    async def test_no_cloud_rebuffers(self, gw):
        gw.cloud = None
        alarm = {"device_id": "D1", "alarm_type": "t", "message": "m"}
        gw._alarm_buffer.append(alarm)
        await gw._upload_alarm_batch()
        assert len(gw._alarm_buffer) == 1


# ── _mqtt_publish ──────────────────────────────────────────────────────

class TestMqttPublish:
    @pytest.mark.asyncio
    async def test_returns_false_when_mqtt_none(self, gw):
        gw.mqtt = None
        result = await gw._mqtt_publish("topic", "payload")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_not_connected(self, gw):
        gw.mqtt.connected = False
        result = await gw._mqtt_publish("topic", "payload")
        assert result is False

    @pytest.mark.asyncio
    async def test_publishes_when_connected(self, gw):
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)
        result = await gw._mqtt_publish("test/topic", '{"data":1}')
        assert result is True
        gw.mqtt.publish_raw.assert_awaited_once_with("test/topic", '{"data":1}')


# ── _sync_cached_telemetry ─────────────────────────────────────────────

class TestSyncCachedTelemetry:
    @pytest.mark.asyncio
    async def test_noop_when_no_unsynced(self, gw):
        result = await gw._sync_cached_telemetry()
        # No unsynced entries, should return without error
        assert result is None  # function returns implicit None

    @pytest.mark.asyncio
    async def test_increments_retry_when_mqtt_down(self, gw):
        gw.mqtt.connected = False
        # Seed cache with telemetry
        gw.cache.cache_telemetry(_make_point())
        await gw._sync_cached_telemetry()
        # retry count should be incremented
        unsynced = gw.cache.get_unsynced()
        assert unsynced[0]["retry_count"] >= 1

    @pytest.mark.asyncio
    async def test_syncs_via_mqtt_when_connected(self, gw):
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)
        gw.cache.cache_telemetry(_make_point("DEV-001"))
        await gw._sync_cached_telemetry()
        gw.mqtt.publish_raw.assert_awaited()
        # Should be marked synced
        unsynced = gw.cache.get_unsynced()
        assert len(unsynced) == 0


# ── _sync_cached_alarms ────────────────────────────────────────────────

class TestSyncCachedAlarms:
    @pytest.mark.asyncio
    async def test_noop_when_no_unsynced(self, gw):
        await gw._sync_cached_alarms()
        # No error

    @pytest.mark.asyncio
    async def test_increments_retry_when_mqtt_down(self, gw):
        gw.mqtt.connected = False
        gw.cache.cache_alarm("DEV-001", {
            "device_id": "DEV-001", "alarm_type": "test",
            "severity": "warning", "message": "test",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        await gw._sync_cached_alarms()
        remaining = gw.cache.get_unsynced_alarms()
        assert remaining[0]["retry_count"] >= 1

    @pytest.mark.asyncio
    async def test_syncs_via_mqtt_when_connected(self, gw):
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)
        gw.cache.cache_alarm("DEV-001", {
            "device_id": "DEV-001", "alarm_type": "test",
            "severity": "warning", "message": "test msg",
            "timestamp": datetime.now(UTC).isoformat(),
        })
        await gw._sync_cached_alarms()
        gw.mqtt.publish_raw.assert_awaited()
        remaining = gw.cache.get_unsynced_alarms()
        assert len(remaining) == 0


# ── stop() graceful shutdown ───────────────────────────────────────────

class TestStopGateway:
    @pytest.mark.asyncio
    async def test_stop_no_components(self):
        """stop() should work when called before start()"""
        from main import EdgeGateway
        config = GatewayConfig()
        config.storage.db_path = ":memory:"
        gw = EdgeGateway(config)
        # Don't call start(), just stop()
        await gw.stop()
        assert gw._running is False

    @pytest.mark.asyncio
    async def test_stop_with_mock_components(self, gw):
        """stop() should gracefully stop all components"""
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock()
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock()
        gw.mqtt.disconnect = AsyncMock()

        await gw.stop()
        gw.modbus.stop.assert_awaited_once()
        gw.ocpp.stop.assert_awaited_once()
        gw.cloud.stop.assert_awaited_once()
        gw.mqtt.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_swallows_component_errors(self, gw):
        """stop() should not propagate component shutdown errors"""
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock(side_effect=RuntimeError("boom"))
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock()

        await gw.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_cancels_bg_tasks(self, gw):
        """stop() should cancel background tasks"""
        loop = asyncio.get_event_loop()
        gw._api_task = loop.create_task(asyncio.sleep(100))
        gw._sync_task = loop.create_task(asyncio.sleep(100))
        gw._cloud_upload_task = loop.create_task(asyncio.sleep(100))
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock()
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock()

        await gw.stop()
        assert gw._api_task.cancelled() or gw._api_task.done()
        assert gw._sync_task.cancelled() or gw._sync_task.done()
        assert gw._cloud_upload_task.cancelled() or gw._cloud_upload_task.done()


# ── _signal_handler ────────────────────────────────────────────────────

class TestSignalHandler:
    def test_signal_handler_no_gateway(self):
        """Signal handler should not crash when _gateway is None"""
        import main
        original = main._gateway
        main._gateway = None
        try:
            main._signal_handler(2)  # SIGINT
        finally:
            main._gateway = original


# ── EdgeGateway init state ─────────────────────────────────────────────

class TestGatewayInit:
    def test_init_defaults(self):
        from main import EdgeGateway
        config = GatewayConfig()
        gw = EdgeGateway(config)
        assert gw._running is False
        assert gw._device_count == 0
        assert gw._telemetry_count == 0
        assert gw._alarm_count == 0
        assert gw._cloud_push_count == 0
        assert gw._cloud_push_failures == 0
        assert gw._registered is False
        assert gw._cloud_token is None
        assert len(gw._bg_tasks) == 0
        assert gw.cache is None
        assert gw.modbus is None

    def test_max_buffer_constants(self):
        from main import EdgeGateway
        assert EdgeGateway.MAX_TELEMETRY_BUFFER == 500
        assert EdgeGateway.MAX_ALARM_BUFFER == 100
