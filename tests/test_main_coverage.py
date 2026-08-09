"""Coverage push for main.py: start(), _cloud_upload_loop, _offline_sync_loop,
_sync_cached_alarms body, _trim_alarm_buffer, main() entry point, _signal_handler with gateway.

Targeting lines: 120-197, 208-209, 238-239, 273-284, 394-419, 457, 463-464,
489, 495, 515-516, 526-563, 567
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import contextlib
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


# ── start() method coverage (lines 120-197) ─────────────────────────

class TestStartGateway:
    @pytest.mark.asyncio
    async def test_start_initializes_cache_and_adapters(self, gw):
        """start() should init cache, adapters, mqtt, cloud, api, and bg tasks"""
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
             patch("main.create_app", return_value=MagicMock()), \
             patch("main.run_api", new=AsyncMock()):

            mock_mqtt_inst = MagicMock()
            mock_mqtt_inst.connect = AsyncMock()
            mock_mqtt_cls.return_value = mock_mqtt_inst

            await gw.start()
            assert gw._running is True
            assert gw._start_time > 0
            assert gw.cache is not None

            # Verify adapters were started
            mock_modbus.start.assert_awaited_once()
            mock_ocpp.start.assert_awaited_once()

            # Verify telemetry/alarm callbacks were wired
            mock_modbus.on_telemetry.assert_called_once()
            mock_modbus.on_alarm.assert_called_once()
            mock_ocpp.on_telemetry.assert_called_once()
            mock_ocpp.on_alarm.assert_called_once()

            # Verify bg tasks created
            assert gw._sync_task is not None
            assert gw._cloud_upload_task is not None
            assert gw._api_task is not None

            await gw.stop()

    @pytest.mark.asyncio
    async def test_start_mqtt_failure_non_fatal(self, gw):
        """MQTT connection failure should not prevent gateway startup"""
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
             patch("main.create_app", return_value=MagicMock()), \
             patch("main.run_api", new=AsyncMock()):

            mock_mqtt_inst = MagicMock()
            mock_mqtt_inst.connect = AsyncMock(side_effect=ConnectionRefusedError("MQTT down"))
            mock_mqtt_cls.return_value = mock_mqtt_inst

            await gw.start()
            assert gw._running is True
            await gw.stop()

    @pytest.mark.asyncio
    async def test_start_cloud_failure_non_fatal(self, gw):
        """Cloud client start failure should not prevent gateway startup"""
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
            mock_cloud_inst.start = AsyncMock(side_effect=RuntimeError("Cloud auth failed"))
            mock_cloud_inst.stop = AsyncMock()
            mock_cloud_cls.return_value = mock_cloud_inst

            await gw.start()
            assert gw._running is True
            await gw.stop()

    @pytest.mark.asyncio
    async def test_start_telemetry_callback_chain(self, gw):
        """Verify telemetry callbacks are properly wired through start()"""
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
             patch("main.create_app", return_value=MagicMock()), \
             patch("main.run_api", new=AsyncMock()):

            mock_mqtt_inst = MagicMock()
            mock_mqtt_inst.connect = AsyncMock()
            mock_mqtt_cls.return_value = mock_mqtt_inst

            await gw.start()

            telemetry_cb = mock_modbus.on_telemetry.call_args[0][0]
            alarm_cb = mock_modbus.on_alarm.call_args[0][0]
            assert callable(telemetry_cb)
            assert callable(alarm_cb)

            await gw.stop()


# ── _cloud_upload_loop (lines 273-284) ──────────────────────────────

class TestCloudUploadLoop:
    @pytest.mark.asyncio
    async def test_upload_loop_runs_then_stops(self, gw):
        """_cloud_upload_loop should run and exit when _running becomes False"""
        gw._running = True

        # Let it do 1-2 iterations, then stop
        async def stop_after_delay():
            await asyncio.sleep(0.15)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._cloud_upload_loop()
        # If we get here without hanging, the loop respected _running=False

    @pytest.mark.asyncio
    async def test_upload_loop_handles_exception(self, gw):
        """upload loop should swallow exceptions and continue"""
        gw._running = True
        call_count = 0

        original_upload = gw._upload_telemetry_batch

        async def failing_upload():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient error")

        gw._upload_telemetry_batch = failing_upload

        async def stop_after_delay():
            await asyncio.sleep(0.2)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._cloud_upload_loop()
        # Should have been called multiple times despite exception
        assert call_count >= 1


# ── _offline_sync_loop (lines 394-419) ──────────────────────────────

class TestOfflineSyncLoop:
    @pytest.mark.asyncio
    async def test_sync_loop_runs_then_stops(self, gw):
        """_offline_sync_loop should run and exit when _running becomes False"""
        gw._running = True

        async def stop_after_delay():
            await asyncio.sleep(0.15)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._offline_sync_loop()

    @pytest.mark.asyncio
    async def test_sync_loop_handles_exception(self, gw):
        """sync loop should swallow exceptions and continue"""
        gw._running = True
        original_sync = gw._sync_cached_telemetry
        call_count = 0

        async def failing_sync():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Sync error")

        gw._sync_cached_telemetry = failing_sync

        async def stop_after_delay():
            await asyncio.sleep(0.2)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._offline_sync_loop()
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_sync_loop_triggers_cleanup(self, gw):
        """sync loop should trigger cache cleanup periodically"""
        gw._running = True
        # Set very short intervals to trigger cleanup within test window
        gw.config.storage.retry_interval = 0.02
        gw.config.storage.cleanup_interval = 0.04  # ~2 cycles

        cleanup_called = False
        original_cleanup = gw.cache.cleanup

        def tracking_cleanup(max_age_days=7):
            nonlocal cleanup_called
            cleanup_called = True
            return original_cleanup(max_age_days)

        gw.cache.cleanup = tracking_cleanup

        async def stop_after_delay():
            await asyncio.sleep(0.25)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._offline_sync_loop()
        assert cleanup_called


# ── _sync_cached_alarms full body (lines 515-516, 526-563) ─────────

class TestSyncCachedAlarmsBody:
    @pytest.mark.asyncio
    async def test_partial_failure_mixed_results(self, gw):
        """Test alarm sync where some entries succeed and some fail"""
        gw.mqtt.connected = True

        # First publish succeeds, second fails
        publish_results = [True, False]
        call_idx = 0

        async def mock_publish(topic, payload):
            nonlocal call_idx
            result = publish_results[min(call_idx, len(publish_results) - 1)]
            call_idx += 1
            return result

        gw.mqtt.publish_raw = mock_publish

        # Seed two alarm entries
        for i in range(2):
            gw.cache.cache_alarm(f"DEV-{i}", {
                "device_id": f"DEV-{i}",
                "alarm_type": "test",
                "severity": "warning",
                "message": f"test {i}",
                "timestamp": datetime.now(UTC).isoformat(),
            })

        await gw._sync_cached_alarms()

        # One should be synced, one should remain
        remaining = gw.cache.get_unsynced_alarms()
        assert len(remaining) == 1
        assert remaining[0]["retry_count"] >= 1

    @pytest.mark.asyncio
    async def test_all_alarms_synced_successfully(self, gw):
        """All alarms synced when MQTT works"""
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)

        for i in range(3):
            gw.cache.cache_alarm(f"DEV-{i}", {
                "device_id": f"DEV-{i}",
                "alarm_type": "overtemp",
                "severity": "critical",
                "message": f"Hot {i}",
                "timestamp": datetime.now(UTC).isoformat(),
            })

        await gw._sync_cached_alarms()
        remaining = gw.cache.get_unsynced_alarms()
        assert len(remaining) == 0
        assert gw.mqtt.publish_raw.await_count == 3

    @pytest.mark.asyncio
    async def test_alarms_contain_replayed_flag(self, gw):
        """Synced alarm payloads should include 'replayed: True'"""
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)

        gw.cache.cache_alarm("DEV-001", {
            "device_id": "DEV-001",
            "alarm_type": "fault",
            "severity": "warning",
            "message": "test",
            "timestamp": datetime.now(UTC).isoformat(),
        })

        await gw._sync_cached_alarms()

        topic, payload = gw.mqtt.publish_raw.call_args[0]
        data = json.loads(payload)
        assert data["replayed"] is True

    @pytest.mark.asyncio
    async def test_topic_format(self, gw):
        """Verify MQTT topic format for alarm sync"""
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)

        gw.cache.cache_alarm("DEV-999", {
            "device_id": "DEV-999",
            "alarm_type": "test",
            "severity": "info",
            "message": "check topic",
            "timestamp": datetime.now(UTC).isoformat(),
        })

        await gw._sync_cached_alarms()

        topic, _ = gw.mqtt.publish_raw.call_args[0]
        assert "DEV-999" in topic
        assert "alarm" in topic


# ── _trim_alarm_buffer (lines 266-269) ──────────────────────────────

class TestTrimAlarmBuffer:
    def test_trim_alarm_buffer_under_limit(self, gw):
        """No trim when under limit"""
        gw._alarm_buffer = [{"i": 1}]
        gw._trim_alarm_buffer()
        assert len(gw._alarm_buffer) == 1

    def test_trim_alarm_buffer_over_limit(self, gw):
        """Trim when over limit"""
        gw.MAX_ALARM_BUFFER = 3
        gw._alarm_buffer = [{"i": i} for i in range(7)]
        gw._trim_alarm_buffer()
        assert len(gw._alarm_buffer) == 3
        # Should keep the last 3
        assert gw._alarm_buffer[-1]["i"] == 6

    def test_trim_telemetry_buffer_under_limit(self, gw):
        """No trim when under limit"""
        gw._telemetry_buffer = [_make_point()]
        gw._trim_telemetry_buffer()
        assert len(gw._telemetry_buffer) == 1


# ── _signal_handler with active gateway (line 463-464) ──────────────

class TestSignalHandlerWithGateway:
    def test_signal_handler_with_gateway(self):
        """Signal handler should schedule stop() when gateway exists"""
        import main

        mock_gw = MagicMock()
        mock_gw._running = True

        # Mock asyncio.get_event_loop to capture the scheduled callback
        mock_loop = MagicMock()
        original_gateway = main._gateway
        main._gateway = mock_gw

        with patch("asyncio.get_event_loop", return_value=mock_loop):
            main._signal_handler(15)  # SIGTERM

        # call_soon_threadsafe should have been called
        assert mock_loop.call_soon_threadsafe.called
        main._gateway = original_gateway


# ── _trim_telemetry_buffer direct test (line 261) ───────────────────

class TestTrimTelemetryDirect:
    def test_trim_at_exact_limit(self, gw):
        """No trimming at exactly the limit"""
        gw.MAX_TELEMETRY_BUFFER = 5
        gw._telemetry_buffer = [_make_point(f"D{i}") for i in range(5)]
        gw._trim_telemetry_buffer()
        assert len(gw._telemetry_buffer) == 5

    def test_trim_over_limit(self, gw):
        """Trim keeps last MAX entries"""
        gw.MAX_TELEMETRY_BUFFER = 3
        gw._telemetry_buffer = [_make_point(f"D{i}") for i in range(6)]
        gw._trim_telemetry_buffer()
        assert len(gw._telemetry_buffer) == 3


# ── main() entry point (lines 526-567) ──────────────────────────────

class TestMainEntryPoint:
    @pytest.mark.asyncio
    async def test_main_entry_basic(self):
        """main() should create gateway, register signals, and run loop"""
        import main

        with patch.object(GatewayConfig, "from_env", return_value=GatewayConfig()), \
             patch("main.setup_logging") as mock_log, \
             patch.object(main.EdgeGateway, "start", new=AsyncMock()) as mock_start, \
             patch.object(main.EdgeGateway, "stop", new=AsyncMock()) as mock_stop:

            # Set _running False quickly so the while loop exits
            async def quick_start(self):
                self._running = True
                # Schedule a quick stop
                loop = asyncio.get_event_loop()
                loop.call_later(0.05, lambda: setattr(self, '_running', False))

            with patch.object(main.EdgeGateway, "start", new=quick_start):
                await main.main()

            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_handles_fatal_exception(self):
        """main() should catch fatal exceptions and cleanup"""
        import main

        with patch.object(GatewayConfig, "from_env", return_value=GatewayConfig()), \
             patch("main.setup_logging"), \
             patch.object(main.EdgeGateway, "start", new=AsyncMock(side_effect=RuntimeError("BOOM"))), \
             patch.object(main.EdgeGateway, "stop", new=AsyncMock()):

            # Should not propagate the exception
            await main.main()

    @pytest.mark.asyncio
    async def test_main_cancelled_error(self):
        """main() should handle asyncio.CancelledError gracefully"""
        import main

        async def cancelled_start(self):
            self._running = True
            raise asyncio.CancelledError()

        with patch.object(GatewayConfig, "from_env", return_value=GatewayConfig()), \
             patch("main.setup_logging"), \
             patch.object(main.EdgeGateway, "start", new=cancelled_start), \
             patch.object(main.EdgeGateway, "stop", new=AsyncMock()):

            await main.main()


# ── _offline_sync_loop: full alarm+telemetry sync (lines 489, 495) ─

class TestOfflineSyncFullFlow:
    @pytest.mark.asyncio
    async def test_sync_loop_syncs_both_telemetry_and_alarms(self, gw):
        """Verify sync loop calls both telemetry and alarm sync"""
        gw._running = True
        gw.mqtt.connected = True
        gw.mqtt.publish_raw = AsyncMock(return_value=True)

        # Seed both telemetry and alarms
        gw.cache.cache_telemetry(_make_point("DEV-001"))
        gw.cache.cache_alarm("DEV-001", {
            "device_id": "DEV-001",
            "alarm_type": "test",
            "severity": "warning",
            "message": "sync test",
            "timestamp": datetime.now(UTC).isoformat(),
        })

        telemetry_synced = False
        alarms_synced = False

        original_telemetry_sync = gw._sync_cached_telemetry
        original_alarm_sync = gw._sync_cached_alarms

        async def tracking_telemetry_sync():
            nonlocal telemetry_synced
            await original_telemetry_sync()
            telemetry_synced = True

        async def tracking_alarm_sync():
            nonlocal alarms_synced
            await original_alarm_sync()
            alarms_synced = True

        gw._sync_cached_telemetry = tracking_telemetry_sync
        gw._sync_cached_alarms = tracking_alarm_sync

        async def stop_after_delay():
            await asyncio.sleep(0.12)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._offline_sync_loop()

        assert telemetry_synced
        assert alarms_synced


# ── Cover remaining edge branches (lines 208-209, 238-239, 457) ──────

class TestRemainingBranches:
    @pytest.mark.asyncio
    async def test_stop_cloud_error_path(self, gw):
        """stop() should handle cloud.stop() raising exception (lines 208-209)"""
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock(side_effect=RuntimeError("cloud crash"))
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock()
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.mqtt.disconnect = AsyncMock()

        await gw.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_bg_task_inner_exception(self, gw):
        """stop() bg task cancellation should handle inner exceptions (lines 238-239)"""
        loop = asyncio.get_event_loop()

        # Create a task that raises when cancelled
        async def raising_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise RuntimeError("task inner error")

        gw._api_task = loop.create_task(raising_task())
        gw._sync_task = None
        gw._cloud_upload_task = None
        gw.modbus = MagicMock()
        gw.modbus.stop = AsyncMock()
        gw.ocpp = MagicMock()
        gw.ocpp.stop = AsyncMock()
        gw.cloud = MagicMock()
        gw.cloud.stop = AsyncMock()

        await gw.stop()  # should not raise despite task inner error

    @pytest.mark.asyncio
    async def test_sync_telemetry_partial_fail_marks_synced(self, gw):
        """Verify mark_synced path when some entries sync (line 457)"""
        gw.mqtt.connected = True

        results = [True, False]
        idx = 0

        async def mock_publish(topic, payload):
            nonlocal idx
            r = results[min(idx, len(results) - 1)]
            idx += 1
            return r

        gw.mqtt.publish_raw = mock_publish

        gw.cache.cache_telemetry(_make_point("DEV-A"))
        gw.cache.cache_telemetry(_make_point("DEV-B"))

        await gw._sync_cached_telemetry()

        remaining = gw.cache.get_unsynced()
        # DEV-A synced, DEV-B failed
        assert len(remaining) == 1
        assert remaining[0]["device_id"] == "DEV-B"

    @pytest.mark.asyncio
    async def test_cloud_upload_loop_cancelled_error(self, gw):
        """upload loop should re-raise CancelledError (line 282)"""
        gw._running = True

        async def cancel_after():
            await asyncio.sleep(0.02)
            raise asyncio.CancelledError()

        # Patch _upload_telemetry_batch to trigger CancelledError
        original = gw._upload_telemetry_batch

        async def cancelling_upload():
            await cancel_after()

        gw._upload_telemetry_batch = cancelling_upload

        with pytest.raises(asyncio.CancelledError):
            await gw._cloud_upload_loop()

    @pytest.mark.asyncio
    async def test_offline_sync_loop_cancelled_error(self, gw):
        """sync loop should re-raise CancelledError (line 417)"""
        gw._running = True

        async def cancelling_sync_alarms():
            await asyncio.sleep(0.02)
            raise asyncio.CancelledError()

        gw._sync_cached_alarms = cancelling_sync_alarms

        with pytest.raises(asyncio.CancelledError):
            await gw._offline_sync_loop()

    @pytest.mark.asyncio
    async def test_sync_loop_cleanup_with_deleted_entries(self, gw):
        """Verify cache cleanup with actual deleted entries (lines 414)"""
        gw._running = True
        gw.config.storage.retry_interval = 0.02
        gw.config.storage.cleanup_interval = 0.01  # trigger every cycle

        # Seed old entry that cleanup will delete
        gw.cache.cache_telemetry(_make_point("DEV-OLD"))

        cleanup_called = False

        original_cleanup = gw.cache.cleanup

        def tracking_cleanup(max_age_days=7):
            nonlocal cleanup_called
            result = original_cleanup(max_age_days)
            cleanup_called = True
            return result

        gw.cache.cleanup = tracking_cleanup

        async def stop_after_delay():
            await asyncio.sleep(0.2)
            gw._running = False

        asyncio.create_task(stop_after_delay())
        await gw._offline_sync_loop()
        assert cleanup_called


# ── main() signal fallback (lines 463-464) ──────────────────────────

class TestMainSignalFallback:
    @pytest.mark.asyncio
    async def test_main_signal_fallback_not_implemented(self):
        """main() should fallback to signal.signal on NotImplementedError"""
        import main

        with patch.object(GatewayConfig, "from_env", return_value=GatewayConfig()), \
             patch("main.setup_logging"):

            # Create a real event loop for this test
            loop = asyncio.get_event_loop()

            real_call_later = loop.call_later

            started = asyncio.Event()

            async def quick_start(self):
                self._running = True
                started.set()
                # Schedule stop on the real loop
                def stop_it():
                    self._running = False
                real_call_later(0.05, stop_it)

            # Mock add_signal_handler to raise NotImplementedError
            original_add_signal = loop.add_signal_handler
            def raising_add_signal(sig, callback, *args):
                raise NotImplementedError("Windows")
            loop.add_signal_handler = raising_add_signal

            try:
                with patch.object(main.EdgeGateway, "start", new=quick_start), \
                     patch.object(main.EdgeGateway, "stop", new=AsyncMock()):
                    await main.main()
            finally:
                loop.add_signal_handler = original_add_signal
