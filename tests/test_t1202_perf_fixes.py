"""T-1202 Performance Optimisation & Bug Fix Tests

Tests cover:
1. cache_stats() API uses thread-safe get_stats() instead of raw SQL
2. get_cache_size() now includes alarms
3. cloud_client cache sync loop dynamic interval logic
4. /api/perf success_rate calculation correctness
5. Buffer trimming under sustained load
"""

import asyncio
import json
import pytest
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import GatewayConfig, StorageConfig
from models import TelemetryPoint
from storage.cache import TelemetryCache


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def cache(tmp_path):
    """Fresh TelemetryCache with temp DB"""
    cfg = StorageConfig(db_path=str(tmp_path / "test_cache.db"))
    c = TelemetryCache(cfg)
    yield c
    c.close()


def _make_point(device_id="EV-001", power=22.5):
    return TelemetryPoint(
        device_id=device_id,
        timestamp="2026-06-29T06:00:00Z",
        power=power,
        voltage=380.0,
        current=59.2,
        temperature=42.0,
        energy=1000.0,
        soc=80,
        status="charging",
    )


# ── 1. get_cache_size includes alarms ─────────────────────────────────────

class TestCacheSizeFix:
    """T-1202: get_cache_size() should include alarm count, not just telemetry"""

    def test_cache_size_includes_alarms(self, cache):
        point = _make_point()
        cache.cache_telemetry(point)
        cache.cache_alarm("EV-001", {"alarm_type": "test", "message": "overheat"})

        # Before fix: would return only telemetry count (1), ignoring alarms
        assert cache.get_cache_size() == 2, "get_cache_size should return telemetry + alarms"

    def test_cache_size_zero_when_empty(self, cache):
        assert cache.get_cache_size() == 0

    def test_cache_size_after_sync(self, cache):
        point = _make_point()
        cache.cache_telemetry(point)
        cache.cache_alarm("EV-001", {"type": "test"})

        entries = cache.get_unsynced(limit=10)
        cache.mark_synced([e["id"] for e in entries])

        alarms = cache.get_unsynced_alarms(limit=10)
        cache.mark_alarms_synced([a["id"] for a in alarms])

        assert cache.get_cache_size() == 0


# ── 2. get_stats thread safety (no raw conn access) ───────────────────────

class TestStatsThreadSafety:
    """T-1202: cache_stats API must use get_stats() not direct conn access"""

    def test_get_stats_returns_both_telemetry_and_alarms(self, cache):
        cache.cache_telemetry(_make_point())
        cache.cache_alarm("EV-001", {"type": "warn"})

        stats = cache.get_stats()

        assert "telemetry" in stats
        assert "alarms" in stats
        assert stats["telemetry"]["total"] == 1
        assert stats["alarms"]["total"] == 1
        assert stats["telemetry"]["unsynced"] == 1
        assert stats["alarms"]["unsynced"] == 1

    def test_get_stats_after_sync(self, cache):
        cache.cache_telemetry(_make_point())
        entries = cache.get_unsynced(limit=10)
        cache.mark_synced([e["id"] for e in entries])

        stats = cache.get_stats()
        assert stats["telemetry"]["synced"] == 1
        assert stats["telemetry"]["unsynced"] == 0


# ── 3. Cloud sync dynamic interval ────────────────────────────────────────

class TestCloudSyncDynamicInterval:
    """T-1202: cache sync should use dynamic interval (faster when backlog exists)"""

    @pytest.mark.asyncio
    async def test_sync_loop_faster_when_backlog(self):
        """When there's data to sync, interval should be shorter"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        cfg = CloudConfig(base_url="http://localhost:1", heartbeat_interval=0)
        client = CloudClient(cfg, "GW-TEST")
        client._client = MagicMock()

        # Mock _sync_cached_alarms to return >0 (has backlog)
        client._sync_cached_alarms = AsyncMock(return_value=5)
        client._sync_cached_telemetry = AsyncMock(return_value=0)

        # Track sleep calls
        sleep_calls = []
        original_sleep = asyncio.sleep

        async def fast_sleep(duration):
            sleep_calls.append(duration)
            if len(sleep_calls) >= 3:
                raise asyncio.CancelledError()
            return

        with patch('asyncio.sleep', side_effect=fast_sleep):
            try:
                await client._cache_sync_loop()
            except asyncio.CancelledError:
                pass

        # When backlog exists, should use active_interval (5s)
        assert sleep_calls[0] == 5, f"Expected active_interval=5, got {sleep_calls[0]}"

    @pytest.mark.asyncio
    async def test_sync_loop_slower_when_idle(self):
        """When no data to sync, interval should gradually increase"""
        from adapters.cloud_client import CloudClient
        from config import CloudConfig

        cfg = CloudConfig(base_url="http://localhost:1", heartbeat_interval=0)
        client = CloudClient(cfg, "GW-TEST")
        client._client = MagicMock()

        client._sync_cached_alarms = AsyncMock(return_value=0)
        client._sync_cached_telemetry = AsyncMock(return_value=0)

        sleep_calls = []

        async def fast_sleep(duration):
            sleep_calls.append(duration)
            if len(sleep_calls) >= 5:
                raise asyncio.CancelledError()
            return

        with patch('asyncio.sleep', side_effect=fast_sleep):
            try:
                await client._cache_sync_loop()
            except asyncio.CancelledError:
                pass

        # Idle: intervals should increase: 5*2=10, 5*4=20, 5*8=40, min(60, 5*16=80)=60
        assert sleep_calls[0] == 10, f"First idle interval should be 10, got {sleep_calls[0]}"
        assert sleep_calls[1] == 20, f"Second idle interval should be 20, got {sleep_calls[1]}"
        assert sleep_calls[2] == 40, f"Third idle interval should be 40, got {sleep_calls[2]}"
        assert sleep_calls[3] == 60, f"Fourth idle interval should cap at 60, got {sleep_calls[3]}"


# ── 4. Buffer trimming under load ─────────────────────────────────────────

class TestBufferTrimming:
    """T-1202: Verify buffers are trimmed under sustained load to prevent OOM"""

    def test_telemetry_buffer_trim(self):
        """Simulate buffer overflow and verify it's capped"""
        from main import EdgeGateway
        from config import GatewayConfig

        gw = EdgeGateway(GatewayConfig.from_env())

        # Fill beyond max
        for i in range(600):
            gw._telemetry_buffer.append(_make_point(power=float(i)))

        gw._trim_telemetry_buffer()

        assert len(gw._telemetry_buffer) == gw.MAX_TELEMETRY_BUFFER
        # Should keep the latest entries
        assert gw._telemetry_buffer[-1].power == 599.0

    def test_alarm_buffer_trim(self):
        from main import EdgeGateway
        from config import GatewayConfig

        gw = EdgeGateway(GatewayConfig.from_env())

        for i in range(150):
            gw._alarm_buffer.append({"alarm_type": f"test_{i}"})

        gw._trim_alarm_buffer()

        assert len(gw._alarm_buffer) == gw.MAX_ALARM_BUFFER


# ── 5. Cache stats API endpoint correctness ───────────────────────────────

class TestCacheStatsAPIFix:
    """T-1202: /api/cache/stats should use get_stats() not raw SQL"""

    def test_cache_stats_no_direct_conn_access(self):
        """Verify the server.py cache_stats route does NOT call _cache._get_conn()"""
        server_code = Path(__file__).resolve().parent.parent / "api" / "server.py"
        content = server_code.read_text()

        # The old buggy line should be gone
        assert "_cache._get_conn()" not in content, \
            "server.py still has direct _get_conn() call in cache_stats — thread safety bug!"

    def test_cache_stats_uses_get_stats(self):
        """Verify cache_stats uses the thread-safe get_stats() method"""
        server_code = Path(__file__).resolve().parent.parent / "api" / "server.py"
        content = server_code.read_text()

        # Find the cache_stats function
        assert "stats = _cache.get_stats()" in content, \
            "cache_stats should use _cache.get_stats() for thread safety"


# ── 6. Perf endpoint cloud success rate ───────────────────────────────────

class TestPerfEndpointFixes:
    """T-1202: /api/perf should compute success_rate from correct field names"""

    def test_perf_uses_correct_cloud_fields(self):
        """Verify server.py uses 'push_total'/'push_failures' not 'pushed'/'failed'"""
        server_code = Path(__file__).resolve().parent.parent / "api" / "server.py"
        content = server_code.read_text()

        assert 'cloud_info.get("push_total"' in content, \
            "perf endpoint should read 'push_total' from cloud_push_callback"
