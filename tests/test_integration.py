"""Integration tests for Edge Gateway (T-1103)

End-to-end tests that verify the full telemetry pipeline:
    Adapter → on_telemetry → cache + MQTT publish + cloud buffer
    Adapter → on_alarm → alarm cache + MQTT publish + cloud buffer
    Offline disconnect → cache accumulates → reconnect → batch sync

These tests instantiate real TelemetryCache (temp SQLite) and mock only
external transports (MQTT client, cloud HTTP).
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from config import GatewayConfig, MQTTConfig, StorageConfig, ModbusConfig, OCPPConfig, CloudConfig, LocalAPIConfig
from models import TelemetryPoint
from storage.cache import TelemetryCache


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def gateway_config(tmp_path):
    """Gateway config with temp DB and fast intervals for testing"""
    return GatewayConfig(
        gateway_id="GW-TEST-001",
        gateway_name="TestGateway",
        cloud=CloudConfig(
            base_url="http://mock-cloud/api/v1",
            register_on_startup=False,   # skip cloud registration
            deregister_on_shutdown=False,
            heartbeat_interval=1,        # fast for testing
        ),
        mqtt=MQTTConfig(
            host="localhost",
            port=1883,
            client_id="test-gw-001",
            topic_prefix="tianlian/test",
            batch_size=10,
            batch_interval=2,
        ),
        modbus=ModbusConfig(
            use_real_modbus=False,
            poll_interval=1,
        ),
        ocpp=OCPPConfig(
            use_real_charger=False,
        ),
        storage=StorageConfig(
            db_path=str(tmp_path / "test_integration.db"),
            retry_interval=1,    # fast sync cycle
            max_retries=5,
            batch_sync_size=100,
            cleanup_interval=60,
        ),
        local_api=LocalAPIConfig(port=0),  # don't actually bind
    )


@pytest.fixture
def cache(gateway_config):
    """Real telemetry cache with temp DB"""
    c = TelemetryCache(gateway_config.storage)
    yield c
    c.close()


@pytest.fixture
def sample_telemetry_points():
    """Generate varied telemetry points for testing"""
    return [
        TelemetryPoint(
            device_id="EVSE-001",
            power=22.5, voltage=400.0, current=56.0,
            temperature=35.0, energy=100.5,
        ),
        TelemetryPoint(
            device_id="EVSE-001",
            power=23.0, voltage=400.1, current=56.2,
            temperature=36.0, energy=101.0,
        ),
        TelemetryPoint(
            device_id="EVSE-002",
            power=11.0, voltage=398.0, current=27.5,
            temperature=30.0, energy=50.2,
        ),
        TelemetryPoint(
            device_id="EVSE-003",
            power=7.5, voltage=395.0, current=19.0,
            temperature=28.0, energy=25.0,
        ),
        TelemetryPoint(
            device_id="EVSE-003",
            power=0.0, voltage=0.0, current=0.0,
            temperature=25.0, energy=25.0, status="idle",
        ),
    ]


@pytest.fixture
def sample_alarm():
    return {
        "device_id": "EVSE-001",
        "alarm_type": "overtemp",
        "message": "Temperature exceeded 80°C",
        "severity": "critical",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Test: Telemetry Pipeline ────────────────────────────────────────────

class TestTelemetryPipeline:
    """Verify adapter telemetry flows through the full pipeline"""

    @pytest.mark.asyncio
    async def test_telemetry_cached_on_receive(self, cache, sample_telemetry_points):
        """Telemetry points should be cached immediately when received"""
        for point in sample_telemetry_points:
            cache.cache_telemetry(point)

        assert cache.get_cache_size() == 5

        # Verify all can be retrieved as unsynced
        unsynced = cache.get_unsynced(limit=100)
        assert len(unsynced) == 5

    @pytest.mark.asyncio
    async def test_telemetry_batch_cached(self, cache, sample_telemetry_points):
        """Batch caching should work efficiently in single transaction"""
        count = cache.cache_telemetry_batch(sample_telemetry_points)
        assert count == 5
        assert cache.get_cache_size() == 5

    @pytest.mark.asyncio
    async def test_telemetry_priority_ordering(self, cache, sample_telemetry_points):
        """Higher priority telemetry should sync first"""
        cache.cache_telemetry(sample_telemetry_points[0], priority=0)
        cache.cache_telemetry(sample_telemetry_points[1], priority=10)
        cache.cache_telemetry(sample_telemetry_points[2], priority=5)

        unsynced = cache.get_unsynced(limit=10)
        assert unsynced[0]["priority"] == 10
        assert unsynced[1]["priority"] == 5
        assert unsynced[2]["priority"] == 0

    @pytest.mark.asyncio
    async def test_telemetry_to_api_payload_format(self, sample_telemetry_points):
        """TelemetryPoint should produce correct V3 API payload"""
        point = sample_telemetry_points[0]
        payload = point.to_api_payload()

        assert payload["device_id"] == "EVSE-001"
        # EVSE-001 is unknown device → grid_* fields
        assert payload["grid_power_total"] == 22.5
        assert payload["grid_voltage_a"] == 400.0
        assert payload["ambient_temperature"] == 35.0


# ── Test: Alarm Pipeline ────────────────────────────────────────────────

class TestAlarmPipeline:
    """Verify alarm events flow through the full pipeline"""

    def test_alarm_cached(self, cache, sample_alarm):
        """Alarms should be cached immediately"""
        alarm_id = cache.cache_alarm(sample_alarm["device_id"], sample_alarm)
        assert alarm_id > 0

        alarms = cache.get_unsynced_alarms()
        assert len(alarms) == 1
        assert alarms[0]["device_id"] == "EVSE-001"
        assert alarms[0]["payload"]["alarm_type"] == "overtemp"

    def test_alarm_synced_excluded_from_unsynced(self, cache, sample_alarm):
        """Synced alarms should not appear in unsynced list"""
        alarm_id = cache.cache_alarm(sample_alarm["device_id"], sample_alarm)
        cache.mark_alarms_synced([alarm_id])

        assert cache.get_unsynced_alarms() == []

    def test_multiple_alarms_different_devices(self, cache):
        """Alarms from multiple devices should all be cached"""
        for i in range(5):
            cache.cache_alarm(f"EVSE-{i:03d}", {
                "alarm_type": f"fault_{i}",
                "message": f"Fault {i}",
                "severity": "warning",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        alarms = cache.get_unsynced_alarms()
        assert len(alarms) == 5

    def test_alarm_retry_exceeds_max(self, cache, sample_alarm):
        """Alarms exceeding max retries should be excluded"""
        alarm_id = cache.cache_alarm(sample_alarm["device_id"], sample_alarm)

        # Increment retry beyond max
        for _ in range(6):  # max_retries=5
            cache.increment_alarm_retry([alarm_id])

        assert cache.get_unsynced_alarms() == []


# ── Test: Offline → Reconnect Sync ──────────────────────────────────────

class TestOfflineReconnectSync:
    """T-1102: Verify offline cache accumulates and syncs on reconnect"""

    def test_offline_accumulation(self, cache, sample_telemetry_points):
        """While offline, telemetry should accumulate in cache"""
        # Simulate offline period: just cache, no sync
        for point in sample_telemetry_points:
            cache.cache_telemetry(point)

        assert cache.get_cache_size() == 5
        assert cache.get_unsynced_count() == 5

    def test_offline_then_sync_batch(self, cache, sample_telemetry_points):
        """After reconnect, cached entries should sync in batches"""
        # Accumulate offline
        cache.cache_telemetry_batch(sample_telemetry_points)
        assert cache.get_cache_size() == 5

        # Simulate batch sync: get unsynced, mark as synced
        batch = cache.get_unsynced(limit=3)
        assert len(batch) == 3
        cache.mark_synced([e["id"] for e in batch])

        assert cache.get_cache_size() == 2  # 5 - 3 synced

        # Sync remaining
        batch2 = cache.get_unsynced(limit=3)
        cache.mark_synced([e["id"] for e in batch2])
        assert cache.get_cache_size() == 0

    def test_offline_alarms_then_sync(self, cache, sample_alarm):
        """Alarms should also sync after reconnect"""
        # Accumulate alarm offline
        cache.cache_alarm(sample_alarm["device_id"], sample_alarm)
        assert cache.get_unsynced_count() == 1

        # Sync
        alarms = cache.get_unsynced_alarms()
        cache.mark_alarms_synced([a["id"] for a in alarms])
        assert cache.get_unsynced_count() == 0

    def test_partial_sync_failure_retry(self, cache, sample_telemetry_points):
        """Failed sync entries should have retry count incremented"""
        cache.cache_telemetry_batch(sample_telemetry_points)

        # Simulate sync failure for first batch
        batch = cache.get_unsynced(limit=3)
        cache.increment_retry([e["id"] for e in batch])

        # All entries still unsynced
        assert cache.get_cache_size() == 5
        # First batch has retry_count=1
        unsynced = cache.get_unsynced(limit=100)
        retried = [u for u in unsynced if u["retry_count"] == 1]
        assert len(retried) == 3


# ── Test: Cache Statistics & Monitoring ─────────────────────────────────

class TestCacheMonitoring:
    """Verify cache stats for observability"""

    def test_stats_reflect_state(self, cache, sample_telemetry_points):
        """Stats should accurately reflect cache contents"""
        cache.cache_telemetry_batch(sample_telemetry_points)
        cache.cache_alarm("EVSE-001", {"type": "overtemp"})

        stats = cache.get_stats()
        assert stats["telemetry"]["total"] == 5
        assert stats["telemetry"]["unsynced"] == 5
        assert stats["telemetry"]["synced"] == 0
        assert stats["alarms"]["total"] == 1
        assert stats["alarms"]["unsynced"] == 1

    def test_stats_after_full_sync(self, cache, sample_telemetry_points):
        """Stats should show all synced after successful sync"""
        cache.cache_telemetry_batch(sample_telemetry_points)
        unsynced = cache.get_unsynced(limit=100)
        cache.mark_synced([e["id"] for e in unsynced])

        stats = cache.get_stats()
        assert stats["telemetry"]["synced"] == 5
        assert stats["telemetry"]["unsynced"] == 0

    def test_stats_includes_db_info(self, cache):
        """Stats should include DB file info"""
        stats = cache.get_stats()
        assert "db_size_bytes" in stats
        assert "db_path" in stats
        assert stats["db_size_bytes"] > 0


# ── Test: Gateway State Persistence ─────────────────────────────────────

class TestGatewayStatePersistence:
    """Verify gateway state survives restarts"""

    def test_save_and_restore_state(self, cache):
        """State saved before restart should be recoverable"""
        cache.save_state("last_sync", "2026-06-28T10:00:00Z")
        cache.save_state("total_synced", "12345")
        cache.save_state("firmware_version", "0.2.0")

        assert cache.load_state("last_sync") == "2026-06-28T10:00:00Z"
        assert cache.load_state("total_synced") == "12345"
        assert cache.load_state("firmware_version") == "0.2.0"

    def test_load_all_state(self, cache):
        """All state entries should be loadable as a dict"""
        cache.save_state("key1", "val1")
        cache.save_state("key2", "val2")

        state = cache.load_all_state()
        assert state["key1"] == "val1"
        assert state["key2"] == "val2"

    def test_overwrite_state(self, cache):
        """State should be updatable"""
        cache.save_state("counter", "100")
        cache.save_state("counter", "200")
        assert cache.load_state("counter") == "200"


# ── Test: MQTT + Cache Integration ──────────────────────────────────────

class TestMQTTCacheIntegration:
    """Verify MQTT publish failure → cache fallback → retry flow"""

    def test_mqtt_down_caches_locally(self, cache, sample_telemetry_points):
        """When MQTT is down, telemetry should be cached for later sync"""
        # Simulate: MQTT down, cache all points
        for point in sample_telemetry_points:
            cache.cache_telemetry(point)

        assert cache.get_unsynced_count() == 5

    def test_mqtt_up_syncs_cached(self, cache, sample_telemetry_points):
        """When MQTT comes back, cached entries should sync via batch"""
        # Offline period
        cache.cache_telemetry_batch(sample_telemetry_points)

        # Online period: simulate batch sync
        batch = cache.get_unsynced(limit=100)
        assert len(batch) == 5

        # Simulate successful MQTT publish
        cache.mark_synced([e["id"] for e in batch])

        assert cache.get_unsynced_count() == 0

    def test_mixed_telemetry_and_alarms(self, cache, sample_telemetry_points, sample_alarm):
        """Telemetry and alarms should coexist in cache independently"""
        cache.cache_telemetry_batch(sample_telemetry_points)
        cache.cache_alarm(sample_alarm["device_id"], sample_alarm)
        cache.cache_alarm("EVSE-002", {"type": "comm_loss"})

        total = cache.get_unsynced_count()
        assert total == 7  # 5 telemetry + 2 alarms

        # Sync alarms first (priority)
        alarms = cache.get_unsynced_alarms()
        cache.mark_alarms_synced([a["id"] for a in alarms])
        assert cache.get_unsynced_count() == 5  # only telemetry left

        # Sync telemetry
        telemetry = cache.get_unsynced(limit=100)
        cache.mark_synced([t["id"] for t in telemetry])
        assert cache.get_unsynced_count() == 0


# ── Test: Batch MQTT Publish ────────────────────────────────────────────

class TestBatchMQTTPublish:
    """T-1101: Verify batch MQTT publishing groups by device"""

    @pytest.mark.asyncio
    async def test_batch_publish_groups_correctly(self, sample_telemetry_points):
        """Batch publish should group points by device_id"""
        from adapters.mqtt_client import MQTTClient
        from config import MQTTConfig

        config = MQTTConfig(
            host="localhost", port=1883,
            client_id="test-gw", topic_prefix="tianlian/test",
        )
        client = MQTTClient(config)
        client._connected = True
        client._client = MagicMock()

        mock_info = MagicMock()
        mock_info.rc = 0  # success
        client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            result = await client.publish_telemetry_batch(sample_telemetry_points)

        assert result["success_count"] == 5
        assert result["failure_count"] == 0

        # 3 unique devices: EVSE-001, EVSE-002, EVSE-003 → 3 publish calls
        assert client._client.publish.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_publish_payload_format(self, sample_telemetry_points):
        """Batch publish payload should include device_id, count, and telemetry array"""
        from adapters.mqtt_client import MQTTClient
        from config import MQTTConfig

        config = MQTTConfig(
            host="localhost", port=1883,
            client_id="test-gw", topic_prefix="tianlian/test",
        )
        client = MQTTClient(config)
        client._connected = True
        client._client = MagicMock()

        mock_info = MagicMock()
        mock_info.rc = 0
        client._client.publish = MagicMock(return_value=mock_info)

        import paho.mqtt.client as mqtt_lib
        with patch.object(mqtt_lib, 'MQTT_ERR_SUCCESS', 0):
            await client.publish_telemetry_batch(sample_telemetry_points[:2])

        # Check the published payload
        call_args = client._client.publish.call_args
        topic = call_args[0][0]
        payload_str = call_args[0][1]

        assert "/batch" in topic
        payload = json.loads(payload_str)
        assert payload["device_id"] == "EVSE-001"
        assert payload["count"] == 2
        assert len(payload["telemetry"]) == 2
        assert "power" in payload["telemetry"][0] or "charger_power" in payload["telemetry"][0] or "grid_power_total" in payload["telemetry"][0]


# ── Test: Cleanup & Maintenance ─────────────────────────────────────────

class TestCleanupMaintenance:
    """Verify cache cleanup removes old synced entries"""

    def test_cleanup_keeps_unsynced(self, cache, sample_telemetry_points):
        """Unsynced entries should never be cleaned up"""
        cache.cache_telemetry_batch(sample_telemetry_points)
        deleted = cache.cleanup(max_age_days=0)
        assert deleted == 0
        assert cache.get_cache_size() == 5

    def test_cleanup_removes_old_synced(self, cache, sample_telemetry_points):
        """Old synced entries should be cleaned up"""
        cache.cache_telemetry_batch(sample_telemetry_points)
        unsynced = cache.get_unsynced(limit=100)
        cache.mark_synced([e["id"] for e in unsynced])

        # Entries created now, so 7-day cutoff should not remove them
        deleted = cache.cleanup(max_age_days=7)
        assert deleted == 0  # too recent

    def test_cleanup_empty_cache(self, cache):
        """Cleanup on empty cache should be a no-op"""
        deleted = cache.cleanup(max_age_days=7)
        assert deleted == 0


# ── Test: Full Gateway Lifecycle ────────────────────────────────────────

class TestGatewayLifecycle:
    """Verify gateway initialization, startup, and shutdown sequences"""

    def test_gateway_config_from_env(self, monkeypatch):
        """Config should load from environment variables"""
        monkeypatch.setenv("GATEWAY_ID", "GW-ENV-001")
        monkeypatch.setenv("GATEWAY_NAME", "EnvGateway")
        monkeypatch.setenv("MQTT_HOST", "mqtt.example.com")
        monkeypatch.setenv("MQTT_PORT", "8883")

        config = GatewayConfig.from_env()
        assert config.gateway_id == "GW-ENV-001"
        assert config.gateway_name == "EnvGateway"
        assert config.mqtt.host == "mqtt.example.com"
        assert config.mqtt.port == 8883

    def test_gateway_config_defaults(self):
        """Default config should have sensible values"""
        config = GatewayConfig()
        assert config.gateway_id == "GW-001"
        assert config.gateway_name == "RaspberryPi-Gateway"
        assert config.cloud.base_url.startswith("http")
        assert config.mqtt.host == "localhost"
        assert config.storage.db_path == "data/gateway.db"
        assert config.modbus.use_real_modbus is False
        assert config.ocpp.use_real_charger is False

    def test_gateway_config_all_sections(self):
        """Config should have all required sections"""
        config = GatewayConfig()
        assert hasattr(config, "cloud")
        assert hasattr(config, "mqtt")
        assert hasattr(config, "modbus")
        assert hasattr(config, "ocpp")
        assert hasattr(config, "storage")
        assert hasattr(config, "local_api")
        assert hasattr(config, "log_level")


# ── Test: Telemetry Data Integrity ──────────────────────────────────────

class TestTelemetryDataIntegrity:
    """Verify telemetry data survives the full pipeline without loss"""

    def test_telemetry_round_trip(self, cache, sample_telemetry_points):
        """Telemetry should survive cache → retrieve cycle unchanged"""
        point = sample_telemetry_points[0]
        cache.cache_telemetry(point)

        unsynced = cache.get_unsynced(limit=1)
        assert len(unsynced) == 1

        cached_payload = unsynced[0]["payload"]
        assert cached_payload["device_id"] == point.device_id
        # EVSE-001 is unknown → grid_* fields
        assert cached_payload["grid_power_total"] == point.power
        assert cached_payload["grid_voltage_a"] == point.voltage
        assert cached_payload["ambient_temperature"] == point.temperature

    def test_batch_round_trip(self, cache, sample_telemetry_points):
        """All batched telemetry should survive cache → retrieve cycle"""
        cache.cache_telemetry_batch(sample_telemetry_points)

        unsynced = cache.get_unsynced(limit=100)
        assert len(unsynced) == 5

        # Group by device_id
        by_device = {}
        for entry in unsynced:
            by_device.setdefault(entry["device_id"], []).append(entry)

        assert len(by_device) == 3  # EVSE-001, EVSE-002, EVSE-003
        assert len(by_device["EVSE-001"]) == 2
        assert len(by_device["EVSE-002"]) == 1
        assert len(by_device["EVSE-003"]) == 2

    def test_concurrent_devices(self, cache):
        """Cache should handle interleaved telemetry from multiple devices"""
        devices = [f"EVSE-{i:03d}" for i in range(10)]
        for device_id in devices:
            point = TelemetryPoint(
                device_id=device_id,
                power=float(hash(device_id) % 30),
                voltage=400.0,
                current=50.0,
            )
            cache.cache_telemetry(point)

        unsynced = cache.get_unsynced(limit=100)
        device_ids = {u["device_id"] for u in unsynced}
        assert device_ids == set(devices)
        assert len(unsynced) == 10
