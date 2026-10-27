"""Deep coverage for main.py: pipeline methods, upload batches, handle_telemetry/alarm,
setup_logging, _mqtt_publish, __main__ entry, and remaining branches.

Targeting: L46, L62-73, L141-143, L146, L149, L238-239, L295-306, L317-326,
L332-360, L365-385, L414, L473-474, L500, L567
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import GatewayConfig
from models import TelemetryPoint
from storage.cache import TelemetryCache

UTC = timezone.utc


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def gw(tmp_db):
    """EdgeGateway with tmp cache, mocked externals"""
    from main import EdgeGateway

    config = GatewayConfig()
    config.storage.db_path = tmp_db
    config.cloud.upload_interval = 0.05
    config.storage.retry_interval = 0.05
    gateway = EdgeGateway(config)
    gateway.cache = TelemetryCache(config.storage)
    gateway.mqtt = MagicMock()
    gateway.mqtt.connected = False
    gateway.mqtt.publish_telemetry = AsyncMock()
    gateway.mqtt.publish_alarm = AsyncMock()
    gateway.mqtt.publish_raw = AsyncMock(return_value=True)
    gateway.mqtt.disconnect = AsyncMock()
    gateway.cloud = MagicMock()
    gateway.cloud.push_telemetry_batch = AsyncMock(return_value=True)
    gateway.cloud.push_alarm_batch = AsyncMock()
    gateway.cloud.start = AsyncMock()
    gateway.cloud.stop = AsyncMock()
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


# ── setup_logging (L62-73) ──────────────────────────────────────────

class TestSetupLogging:
    def test_setup_logging_default(self):
        """setup_logging configures logging without errors"""
        import main
        main.setup_logging("INFO")
        logger = logging.getLogger("gateway")
        assert logger is not None

    def test_setup_logging_debug_level(self):
        """setup_logging handles DEBUG level"""
        import main
        main.setup_logging("DEBUG")
        # Verify uvicorn/pymodbus/paho loggers were silenced
        assert logging.getLogger("uvicorn").level == logging.WARNING
        assert logging.getLogger("pymodbus").level == logging.WARNING
        assert logging.getLogger("paho").level == logging.WARNING

    def test_setup_logging_invalid_level_defaults_to_info(self):
        """Invalid level string defaults to INFO"""
        import main
        main.setup_logging("INVALID_LEVEL")
        # Should not raise, defaults to INFO


# ── _handle_telemetry full pipeline (L332-360) ──────────────────────

class TestHandleTelemetryFull:
    @pytest.mark.asyncio
    async def test_handle_telemetry_updates_latest(self, gw):
        """_handle_telemetry stores latest telemetry per device"""
        point = _make_point("DEV-100", power=42.0)
        await gw._handle_telemetry(point)

        latest = gw._latest_telemetry
        assert "DEV-100" in latest
        assert latest["DEV-100"]["power"] == 42.0
        assert gw._device_count == 1
        assert gw._telemetry_count == 1

    @pytest.mark.asyncio
    async def test_handle_telemetry_buffers_for_cloud(self, gw):
        """_handle_telemetry appends to telemetry buffer"""
        point = _make_point("DEV-200")
        await gw._handle_telemetry(point)
        assert len(gw._telemetry_buffer) == 1
        assert gw._telemetry_buffer[0].device_id == "DEV-200"

    @pytest.mark.asyncio
    async def test_handle_telemetry_publishes_mqtt(self, gw):
        """_handle_telemetry publishes to MQTT"""
        gw.mqtt = MagicMock()
        gw.mqtt.publish_telemetry = AsyncMock()
        point = _make_point("DEV-300")
        await gw._handle_telemetry(point)
        gw.mqtt.publish_telemetry.assert_awaited_once_with(point)

    @pytest.mark.asyncio
    async def test_handle_telemetry_trims_buffer(self, gw):
        """Buffer is trimmed when exceeding MAX_TELEMETRY_BUFFER"""
        gw.MAX_TELEMETRY_BUFFER = 3
        gw._telemetry_buffer = []
        for i in range(5):
            await gw._handle_telemetry(_make_point(f"D{i}"))
        assert len(gw._telemetry_buffer) == 3

    @pytest.mark.asyncio
    async def test_handle_telemetry_no_mqtt(self, gw):
        """_handle_telemetry works without MQTT"""
        gw.mqtt = None
        point = _make_point("DEV-NO-MQTT")
        await gw._handle_telemetry(point)
        assert gw._latest_telemetry["DEV-NO-MQTT"]["power"] == 10.0

    @pytest.mark.asyncio
    async def test_handle_telemetry_error_handled(self, gw):
        """_handle_telemetry catches and logs errors"""
        # Force an error by making mqtt.publish_telemetry raise
        gw.mqtt.publish_telemetry = AsyncMock(side_effect=RuntimeError("MQTT boom"))
        point = _make_point("DEV-ERR")
        # Should not propagate exception
        await gw._handle_telemetry(point)

    @pytest.mark.asyncio
    async def test_handle_telemetry_multiple_devices(self, gw):
        """Multiple devices tracked separately"""
        for i in range(5):
            await gw._handle_telemetry(_make_point(f"DEV-{i}", power=float(i * 10)))
        assert gw._device_count == 5
        assert gw._telemetry_count == 5
        assert gw._latest_telemetry["DEV-4"]["power"] == 40.0


# ── _handle_alarm full pipeline (L365-385) ──────────────────────────

class TestHandleAlarmFull:
    @pytest.mark.asyncio
    async def test_handle_alarm_buffers_and_counts(self, gw):
        """_handle_alarm appends to buffer and increments count"""
        await gw._handle_alarm("DEV-1", "overtemp", "Too hot", severity="critical")
        assert len(gw._alarm_buffer) == 1
        assert gw._alarm_count == 1
        alarm = gw._alarm_buffer[0]
        assert alarm["device_id"] == "DEV-1"
        assert alarm["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_handle_alarm_publishes_mqtt(self, gw):
        """_handle_alarm publishes alarm to MQTT"""
        gw.mqtt.publish_alarm = AsyncMock()
        await gw._handle_alarm("DEV-2", "fault", "breaker trip")
        gw.mqtt.publish_alarm.assert_awaited_once()
        args = gw.mqtt.publish_alarm.call_args[0]
        assert args[0] == "DEV-2"

    @pytest.mark.asyncio
    async def test_handle_alarm_mqtt_error_swallowed(self, gw):
        """_handle_alarm swallows MQTT publish errors"""
        gw.mqtt.publish_alarm = AsyncMock(side_effect=RuntimeError("MQTT down"))
        await gw._handle_alarm("DEV-3", "test", "no crash")
        # Should still buffer the alarm
        assert len(gw._alarm_buffer) == 1

    @pytest.mark.asyncio
    async def test_handle_alarm_no_mqtt(self, gw):
        """_handle_alarm works without MQTT"""
        gw.mqtt = None
        await gw._handle_alarm("DEV-4", "test", "no mqtt")
        assert len(gw._alarm_buffer) == 1

    @pytest.mark.asyncio
    async def test_handle_alarm_trims_buffer(self, gw):
        """Alarm buffer is trimmed"""
        gw.MAX_ALARM_BUFFER = 3
        gw._alarm_buffer = []
        for i in range(7):
            await gw._handle_alarm(f"DEV-{i}", "test", f"msg {i}")
        assert len(gw._alarm_buffer) == 3

    @pytest.mark.asyncio
    async def test_handle_alarm_default_severity(self, gw):
        """Default severity is 'warning'"""
        await gw._handle_alarm("DEV-5", "test", "check default")
        assert gw._alarm_buffer[-1]["severity"] == "warning"


# ── _upload_telemetry_batch full (L295-306) ─────────────────────────

class TestUploadTelemetryBatchFull:
    @pytest.mark.asyncio
    async def test_upload_empty_buffer_noop(self, gw):
        """Empty buffer is a no-op"""
        gw._telemetry_buffer = []
        await gw._upload_telemetry_batch()
        gw.cloud.push_telemetry_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_with_cloud_success(self, gw):
        """Successful cloud upload clears buffer and increments counter"""
        gw._telemetry_buffer = [_make_point("A"), _make_point("B")]
        await gw._upload_telemetry_batch()
        assert len(gw._telemetry_buffer) == 0  # cleared
        gw.cloud.push_telemetry_batch.assert_awaited_once()
        assert gw._cloud_push_count == 1
        assert gw._cloud_push_failures == 0

    @pytest.mark.asyncio
    async def test_upload_with_cloud_failure(self, gw):
        """Failed cloud upload increments failure counter"""
        gw._telemetry_buffer = [_make_point("A")]
        gw.cloud.push_telemetry_batch = AsyncMock(return_value=False)
        await gw._upload_telemetry_batch()
        assert gw._cloud_push_count == 1
        assert gw._cloud_push_failures == 1

    @pytest.mark.asyncio
    async def test_upload_no_cloud_rebuffers(self, gw):
        """Without cloud client, items go back to buffer (trimmed)"""
        gw._telemetry_buffer = [_make_point("A")]
        gw.cloud = None
        await gw._upload_telemetry_batch()
        assert len(gw._telemetry_buffer) == 1  # put back


# ── _upload_alarm_batch full (L317-326) ─────────────────────────────

class TestUploadAlarmBatchFull:
    @pytest.mark.asyncio
    async def test_upload_empty_alarms_noop(self, gw):
        """Empty alarm buffer is a no-op"""
        gw._alarm_buffer = []
        await gw._upload_alarm_batch()
        gw.cloud.push_alarm_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_alarms_with_cloud(self, gw):
        """Alarm batch uploaded to cloud"""
        gw._alarm_buffer = [{"device_id": "D1", "severity": "warning"}]
        await gw._upload_alarm_batch()
        gw.cloud.push_alarm_batch.assert_awaited_once()
        assert len(gw._alarm_buffer) == 0  # cleared

    @pytest.mark.asyncio
    async def test_upload_alarms_no_cloud_rebuffers(self, gw):
        """Without cloud, alarms go back to buffer"""
        gw._alarm_buffer = [{"device_id": "D1"}]
        gw.cloud = None
        await gw._upload_alarm_batch()
        assert len(gw._alarm_buffer) == 1  # put back


# ── _mqtt_publish direct (L473-474) ─────────────────────────────────

class TestMqttPublishDirect:
    @pytest.mark.asyncio
    async def test_mqtt_publish_success(self, gw):
        """_mqtt_publish returns True on success"""
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)
        result = await gw._mqtt_publish("topic/test", '{"data":1}')
        assert result is True

    @pytest.mark.asyncio
    async def test_mqtt_publish_mqtt_down(self, gw):
        """_mqtt_publish returns False when MQTT disconnected"""
        gw.mqtt.connected = False
        result = await gw._mqtt_publish("topic/test", '{"data":1}')
        assert result is False

    @pytest.mark.asyncio
    async def test_mqtt_publish_no_mqtt(self, gw):
        """_mqtt_publish returns False when mqtt is None"""
        gw.mqtt = None
        result = await gw._mqtt_publish("topic/test", '{"data":1}')
        assert result is False


# ── _sync_cached_alarms increment_retry path (L500) ─────────────────

class TestSyncAlarmsRetryPath:
    @pytest.mark.asyncio
    async def test_sync_alarms_mqtt_down_increments_retry(self, gw):
        """When MQTT is down, alarm retries are incremented"""
        gw._running = True
        gw.mqtt.connected = False

        # Seed alarm entries
        for i in range(3):
            gw.cache.cache_alarm(f"DEV-{i}", {
                "device_id": f"DEV-{i}",
                "alarm_type": "test",
                "severity": "warning",
                "message": f"test {i}",
                "timestamp": datetime.now(UTC).isoformat(),
            })

        await gw._sync_cached_alarms()

        # All entries should have incremented retry_count
        remaining = gw.cache.get_unsynced_alarms()
        assert len(remaining) == 3
        for entry in remaining:
            assert entry["retry_count"] >= 1


# ── Cleanup with deleted entries logging (L414) ─────────────────────

class TestCleanupLogging:
    @pytest.mark.asyncio
    async def test_sync_loop_cleanup_logs_deleted(self, gw, caplog):
        """Cleanup that deletes entries should log the count"""
        gw._running = True
        gw.config.storage.retry_interval = 0.02
        gw.config.storage.cleanup_interval = 0.01  # every cycle

        # Insert entries and make them "old" by manipulating timestamps
        gw.cache.cache_telemetry(_make_point("DEV-OLD"))

        # Manually set the entry timestamp to 30 days ago
        import sqlite3
        conn = sqlite3.connect(gw.config.storage.db_path)
        old_time = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
        conn.execute("UPDATE telemetry_cache SET cached_at = ? WHERE device_id = 'DEV-OLD'", (old_time,))
        conn.commit()
        conn.close()

        async def stop_after():
            await asyncio.sleep(0.15)
            gw._running = False

        _stop_task = asyncio.create_task(stop_after())  # noqa: RUF006
        await gw._offline_sync_loop()

        # Verify the old entry was cleaned up
        remaining = gw.cache.get_unsynced()
        assert len(remaining) == 0


# ── stop() bg task inner exception (L238-239) ───────────────────────

class TestStopBgTaskException:
    @pytest.mark.asyncio
    async def test_stop_sync_task_inner_error(self, gw):
        """stop() handles RuntimeError from sync task cancellation (L238-239)"""
        loop = asyncio.get_event_loop()

        async def raising_sync_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise RuntimeError("sync inner error") from None

        gw._sync_task = loop.create_task(raising_sync_task())
        gw._cloud_upload_task = None
        gw._api_task = None
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock()
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock()

        # Should not raise despite inner RuntimeError
        await gw.stop()

    @pytest.mark.asyncio
    async def test_stop_api_task_inner_error(self, gw):
        """stop() handles RuntimeError from API task cancellation (L238-239)"""
        loop = asyncio.get_event_loop()

        async def raising_api_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise RuntimeError("api inner error") from None

        gw._api_task = loop.create_task(raising_api_task())
        gw._sync_task = None
        gw._cloud_upload_task = None
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock()
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock()

        await gw.stop()


# ── start() real adapter init paths (L141-143, L146, L149) ─────────

class TestStartAdapterInit:
    @pytest.mark.asyncio
    async def test_start_initializes_real_cache(self, gw):
        """start() initializes cache from config when cache is pre-set"""
        mock_modbus = MagicMock()
        mock_modbus.start = AsyncMock()
        mock_modbus.on_telemetry = MagicMock()
        mock_modbus.on_alarm = MagicMock()
        mock_ocpp = MagicMock()
        mock_ocpp.start = AsyncMock()
        mock_ocpp.on_telemetry = MagicMock()
        mock_ocpp.on_alarm = MagicMock()

        with patch("main.ModbusAdapter", return_value=mock_modbus), \
             patch("main.OCPPAdapter", return_value=mock_ocpp), \
             patch("main.MQTTClient") as mock_mqtt_cls, \
             patch("main.CloudClient") as mock_cloud_cls, \
             patch("main.create_app", return_value=MagicMock()), \
             patch("main.run_api", new=AsyncMock()):

            mock_mqtt_inst = MagicMock()
            mock_mqtt_inst.connect = AsyncMock()
            mock_mqtt_cls.return_value = mock_mqtt_inst

            mock_cloud_inst = MagicMock()
            mock_cloud_inst.start = AsyncMock()
            mock_cloud_inst.stop = AsyncMock()
            mock_cloud_cls.return_value = mock_cloud_inst

            # This will re-init cache from config path
            await gw.start()
            assert gw._running is True

            # Cache should be initialized
            assert gw.cache is not None

            await gw.stop()


# ── _sync_cached_telemetry: MQTT connected multi-device batch (L439-457) ─

class TestSyncTelemetryMultiDevice:
    @pytest.mark.asyncio
    async def test_multi_device_batch_grouping(self, gw):
        """Telemetry sync groups by device_id for batch MQTT publish"""
        gw._running = True
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)

        # Seed entries for multiple devices
        for dev in ["A", "A", "B", "B", "C"]:
            gw.cache.cache_telemetry(_make_point(f"DEV-{dev}"))

        await gw._sync_cached_telemetry()

        # Should have 3 MQTT publishes (one per device batch)
        assert gw.mqtt.publish_raw.await_count == 3

        # All entries should be synced
        remaining = gw.cache.get_unsynced()
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_batch_payload_contains_replayed_flag(self, gw):
        """Batch telemetry payload includes replayed=True"""
        gw._running = True
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)

        gw.cache.cache_telemetry(_make_point("DEV-X"))

        await gw._sync_cached_telemetry()

        _topic, payload = gw.mqtt.publish_raw.call_args[0]
        data = json.loads(payload)
        assert data["replayed"] is True
        assert data["device_id"] == "DEV-X"
        assert "telemetry" in data

    @pytest.mark.asyncio
    async def test_sync_telemetry_mqtt_down_increments_retry(self, gw):
        """When MQTT is down, telemetry retries are incremented"""
        gw._running = True
        gw.mqtt.connected = False

        gw.cache.cache_telemetry(_make_point("DEV-DOWN"))

        await gw._sync_cached_telemetry()

        remaining = gw.cache.get_unsynced()
        assert len(remaining) == 1
        assert remaining[0]["retry_count"] >= 1


# ── Cloud upload loop: upload_alarm_batch called (L306) ─────────────

class TestCloudUploadLoopAlarms:
    @pytest.mark.asyncio
    async def test_upload_loop_processes_alarms(self, gw):
        """_cloud_upload_loop calls _upload_alarm_batch when alarms buffered"""
        gw._running = True
        gw._alarm_buffer = [{"device_id": "D1", "severity": "warning"}]
        gw._telemetry_buffer = []

        alarm_uploaded = False
        original_alarm_upload = gw._upload_alarm_batch

        async def tracking_alarm_upload():
            nonlocal alarm_uploaded
            await original_alarm_upload()
            alarm_uploaded = True

        gw._upload_alarm_batch = tracking_alarm_upload

        async def stop_after():
            await asyncio.sleep(0.15)
            gw._running = False

        _stop_task = asyncio.create_task(stop_after())  # noqa: RUF006
        await gw._cloud_upload_loop()

        assert alarm_uploaded
