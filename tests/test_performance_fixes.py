"""Tests for performance fixes: buffer limits, cache threading, cloud-client cache integration.

Covers T-1202: Performance optimization + Bug fixes.
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import GatewayConfig, StorageConfig
from storage.cache import TelemetryCache
from models import TelemetryPoint


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_cache():
    """Temporary cache with isolated DB"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = StorageConfig(db_path=db_path, max_cache_size=100, max_retries=3)
        cache = TelemetryCache(config)
        yield cache
        cache.close()
    finally:
        os.unlink(db_path)


@pytest.fixture
def make_telemetry_point():
    """Factory for telemetry points"""
    counter = [0]

    def _make(device_id="DEV-001", power=10.0):
        counter[0] += 1
        return TelemetryPoint(
            device_id=device_id,
            power=power,
            voltage=380.0,
            current=power / 380.0 * 1000,
            temperature=25.0,
            energy=float(counter[0]),
            status="Charging",
        )

    return _make


# ── Buffer Trim Tests ─────────────────────────────────────────────────


class TestBufferTrimming:
    """Test telemetry and alarm buffer trimming logic"""

    def test_telemetry_buffer_trim(self):
        """Telemetry buffer should be capped at MAX_TELEMETRY_BUFFER (500)"""
        from main import EdgeGateway

        gw = EdgeGateway(GatewayConfig())
        gw._telemetry_buffer = [f"point_{i}" for i in range(600)]
        gw._trim_telemetry_buffer()

        assert len(gw._telemetry_buffer) == EdgeGateway.MAX_TELEMETRY_BUFFER
        # Should keep the latest 500
        assert gw._telemetry_buffer[0] == "point_100"
        assert gw._telemetry_buffer[-1] == "point_599"

    def test_alarm_buffer_trim(self):
        """Alarm buffer should be capped at MAX_ALARM_BUFFER (100)"""
        from main import EdgeGateway

        gw = EdgeGateway(GatewayConfig())
        gw._alarm_buffer = [{"alarm": f"a_{i}"} for i in range(150)]
        gw._trim_alarm_buffer()

        assert len(gw._alarm_buffer) == EdgeGateway.MAX_ALARM_BUFFER
        # Should keep the latest 100
        assert gw._alarm_buffer[0] == {"alarm": "a_50"}
        assert gw._alarm_buffer[-1] == {"alarm": "a_149"}

    def test_buffer_trim_no_op_when_under_limit(self):
        """Buffer trim should be no-op when under limit"""
        from main import EdgeGateway

        gw = EdgeGateway(GatewayConfig())
        gw._telemetry_buffer = ["a", "b", "c"]
        gw._trim_telemetry_buffer()
        assert len(gw._telemetry_buffer) == 3

    def test_alarm_buffer_trim_no_op_when_under_limit(self):
        from main import EdgeGateway

        gw = EdgeGateway(GatewayConfig())
        gw._alarm_buffer = [{"a": 1}]
        gw._trim_alarm_buffer()
        assert len(gw._alarm_buffer) == 1


# ── Cache Threading Test ──────────────────────────────────────────────


class TestCacheThreading:
    """Test SQLite cache with check_same_thread=False"""

    def test_cache_works_across_threads(self, tmp_cache, make_telemetry_point):
        """Cache should be usable from different threads (async callbacks)"""
        import threading

        points = [make_telemetry_point() for _ in range(10)]
        errors = []

        def writer():
            try:
                for p in points:
                    tmp_cache.cache_telemetry(p)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threading errors: {errors}"
        size = tmp_cache.get_cache_size()
        assert size == 30, f"Expected 30 cached points, got {size}"


# ── Cloud Client Cache Integration ────────────────────────────────────


class TestCloudClientCacheIntegration:
    """Test that CloudClient correctly uses cache for offline degradation"""

    @pytest.mark.asyncio
    async def test_cloud_client_receives_cache(self):
        """CloudClient should accept and store cache reference"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        config = CloudConfig(base_url="http://localhost:99999", register_on_startup=False)
        mock_cache = MagicMock()
        client = CloudClient(config, "GW-TEST", cache=mock_cache)

        assert client.cache is mock_cache

    @pytest.mark.asyncio
    async def test_telemetry_cached_on_cloud_failure(self, tmp_cache, make_telemetry_point):
        """When cloud is unreachable, telemetry should be cached via CloudClient.cache"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        config = CloudConfig(
            base_url="http://localhost:99999",  # nothing listening
            register_on_startup=False,
            heartbeat_interval=0,
        )
        client = CloudClient(config, "GW-TEST", cache=tmp_cache)
        await client.start()

        point = make_telemetry_point()
        result = await client.push_telemetry_batch([point])

        assert result is False  # cloud push failed

        # Telemetry should have been cached
        unsynced = tmp_cache.get_unsynced()
        assert len(unsynced) == 1, f"Expected 1 cached point, got {len(unsynced)}"

        await client.stop()

    @pytest.mark.asyncio
    async def test_alarm_cached_on_cloud_failure(self, tmp_cache):
        """When cloud is unreachable, alarms should be cached via CloudClient.cache"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        config = CloudConfig(
            base_url="http://localhost:99999",
            register_on_startup=False,
            heartbeat_interval=0,
        )
        client = CloudClient(config, "GW-TEST", cache=tmp_cache)
        await client.start()

        result = await client.push_alarm("DEV-001", "test_alarm", "warning", "test message")

        assert result is False

        # Alarm should have been cached
        alarms = tmp_cache.get_unsynced_alarms()
        assert len(alarms) == 1, f"Expected 1 cached alarm, got {len(alarms)}"

        await client.stop()


# ── Cleanup Cutoff Fix ────────────────────────────────────────────────


class TestCleanupCutoff:
    """Test that cleanup() properly computes the cutoff datetime"""

    def test_cleanup_removes_old_synced_entries(self, tmp_cache, make_telemetry_point):
        """Cleanup should remove synced entries older than max_age_days"""
        # Cache a point and mark it as synced
        point = make_telemetry_point()
        tmp_cache.cache_telemetry(point)
        unsynced = tmp_cache.get_unsynced()
        tmp_cache.mark_synced([unsynced[0]["id"]])

        # Manually backdate the created_at to 10 days ago
        from datetime import datetime, timezone, timedelta
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        conn = tmp_cache._get_conn()
        conn.execute("UPDATE telemetry_cache SET created_at = ? WHERE id = ?", (old_date, unsynced[0]["id"]))
        conn.commit()

        # Cleanup with 7-day retention
        deleted = tmp_cache.cleanup(max_age_days=7)
        assert deleted == 1, f"Expected 1 deleted, got {deleted}"

        # Verify it's gone
        stats = tmp_cache.get_stats()
        assert stats["telemetry"]["total"] == 0

    def test_cleanup_keeps_recent_synced_entries(self, tmp_cache, make_telemetry_point):
        """Cleanup should keep synced entries newer than max_age_days"""
        point = make_telemetry_point()
        tmp_cache.cache_telemetry(point)
        unsynced = tmp_cache.get_unsynced()
        tmp_cache.mark_synced([unsynced[0]["id"]])

        # Cleanup with 7-day retention - entry is fresh
        deleted = tmp_cache.cleanup(max_age_days=7)
        assert deleted == 0

        stats = tmp_cache.get_stats()
        assert stats["telemetry"]["total"] == 1


# ── Cache Sync Loop Tests (T-1202) ────────────────────────────────────


class TestCacheSyncLoop:
    """Test the cache recovery sync loop in CloudClient"""

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_success(self, tmp_cache, make_telemetry_point):
        """_sync_cached_telemetry should push cached data and mark synced"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        # Seed cache with unsynced telemetry
        for i in range(5):
            tmp_cache.cache_telemetry(make_telemetry_point())
        assert tmp_cache.get_cache_size() == 5

        config = CloudConfig(
            base_url="http://localhost:8000",
            register_on_startup=False,
            heartbeat_interval=0,
        )
        client = CloudClient(config, "GW-SYNC", cache=tmp_cache)
        await client.start()

        # Mock successful POST
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client._client.post = AsyncMock(return_value=mock_resp)

        synced = await client._sync_cached_telemetry(batch_size=10)
        assert synced == 5
        assert len(tmp_cache.get_cloud_unsynced()) == 0  # all marked cloud_synced

        await client.stop()

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_empty(self, tmp_cache):
        """_sync_cached_telemetry should return 0 when cache is empty"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        config = CloudConfig(base_url="http://localhost:8000", register_on_startup=False)
        client = CloudClient(config, "GW-SYNC2", cache=tmp_cache)
        await client.start()

        synced = await client._sync_cached_telemetry()
        assert synced == 0

        await client.stop()

    @pytest.mark.asyncio
    async def test_sync_cached_telemetry_failure_increments_retry(self, tmp_cache, make_telemetry_point):
        """Failed sync should increment retry count, not mark synced"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        for i in range(3):
            tmp_cache.cache_telemetry(make_telemetry_point())

        config = CloudConfig(
            base_url="http://localhost:99999",  # nothing listening
            register_on_startup=False,
            heartbeat_interval=0,
        )
        client = CloudClient(config, "GW-SYNC3", cache=tmp_cache)
        await client.start()

        synced = await client._sync_cached_telemetry(batch_size=10)
        assert synced == 0  # failed

        # Retry count should be incremented
        unsynced = tmp_cache.get_unsynced()
        assert all(item["retry_count"] >= 1 for item in unsynced)

        await client.stop()

    @pytest.mark.asyncio
    async def test_sync_cached_alarms_success(self, tmp_cache):
        """_sync_cached_alarms should push cached alarms and mark synced"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        # Seed cache with unsynced alarms
        for i in range(3):
            tmp_cache.cache_alarm("DEV-001", {
                "device_id": "DEV-001",
                "alarm_type": f"alarm_{i}",
                "severity": "warning",
                "message": f"Test alarm {i}",
                "timestamp": "2025-01-01T00:00:00Z",
            })

        config = CloudConfig(
            base_url="http://localhost:8000",
            register_on_startup=False,
            heartbeat_interval=0,
        )
        client = CloudClient(config, "GW-SYNC4", cache=tmp_cache)
        await client.start()

        # Mock successful POST
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client._client.post = AsyncMock(return_value=mock_resp)

        synced = await client._sync_cached_alarms(batch_size=10)
        assert synced == 3

        # All alarms should be marked cloud_synced
        remaining = tmp_cache.get_cloud_unsynced_alarms()
        assert len(remaining) == 0

        await client.stop()

    @pytest.mark.asyncio
    async def test_sync_cached_alarms_failure_increments_retry(self, tmp_cache):
        """Failed alarm sync should increment retry count"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        tmp_cache.cache_alarm("DEV-001", {
            "device_id": "DEV-001",
            "alarm_type": "test",
            "severity": "critical",
            "message": "Test",
            "timestamp": "2025-01-01T00:00:00Z",
        })

        config = CloudConfig(
            base_url="http://localhost:99999",
            register_on_startup=False,
            heartbeat_interval=0,
        )
        client = CloudClient(config, "GW-SYNC5", cache=tmp_cache)
        await client.start()

        synced = await client._sync_cached_alarms(batch_size=10)
        assert synced == 0

        # Retry count should be incremented
        remaining = tmp_cache.get_unsynced_alarms()
        assert all(item["retry_count"] >= 1 for item in remaining)

        await client.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_sync_task(self):
        """CloudClient.stop() should cancel the cache sync task"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        config = CloudConfig(
            base_url="http://localhost:99999",
            register_on_startup=False,
            heartbeat_interval=0,
        )
        mock_cache = MagicMock()
        client = CloudClient(config, "GW-STOPS", cache=mock_cache)
        await client.start()

        # Sync task should exist
        assert hasattr(client, '_sync_task')
        assert client._sync_task is not None

        await client.stop()

        # Task should be cancelled
        assert client._sync_task.cancelled() or client._sync_task.done()
