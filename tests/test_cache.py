"""Tests for storage/cache.py"""

import json
import os
import pytest
import tempfile

from config import StorageConfig
from models.telemetry import TelemetryPoint
from storage.cache import TelemetryCache


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    # Also clean up WAL and SHM files
    for ext in ("-wal", "-shm"):
        extra = db_path + ext
        if os.path.exists(extra):
            os.unlink(extra)


@pytest.fixture
def cache(temp_db_path):
    """Create a TelemetryCache with a temp DB"""
    config = StorageConfig(db_path=temp_db_path, max_retries=3)
    tc = TelemetryCache(config)
    yield tc
    tc.close()


class TestTelemetryCache:
    """TelemetryCache unit tests"""

    def test_cache_init(self, cache, temp_db_path):
        """Test cache initialization creates tables"""
        # The fixture already initializes, but we verify the DB exists
        assert os.path.exists(temp_db_path)

        # Verify the table was created by checking we can query it
        conn = cache._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_cache'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "telemetry_cache" in tables

        # Verify index exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_telemetry_synced'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        assert "idx_telemetry_synced" in indexes

    def test_cache_and_get_unsynced(self, cache):
        """Test caching telemetry and retrieving unsynced data"""
        point = TelemetryPoint(
            device_id="CHARGER-001",
            timestamp="2026-06-22T12:00:00Z",
            power=50.0,
            voltage=220.0,
            current=30.0,
            temperature=40.0,
            energy=1000.0,
            soc=85.0,
            status="charging",
        )
        cache.cache_telemetry(point)

        unsynced = cache.get_unsynced()
        assert len(unsynced) == 1
        assert unsynced[0]["device_id"] == "CHARGER-001"
        assert unsynced[0]["retry_count"] == 0
        assert unsynced[0]["payload"]["metrics"]["power"] == 50.0

    def test_get_unsynced_multiple(self, cache):
        """Test retrieving multiple unsynced points in order"""
        points = [
            TelemetryPoint(device_id="CHARGER-001", power=10.0),
            TelemetryPoint(device_id="CHARGER-002", power=20.0),
            TelemetryPoint(device_id="CHARGER-003", power=30.0),
        ]
        for p in points:
            cache.cache_telemetry(p)

        unsynced = cache.get_unsynced(limit=10)
        assert len(unsynced) == 3
        # Should be in insertion order
        assert unsynced[0]["payload"]["metrics"]["power"] == 10.0
        assert unsynced[1]["payload"]["metrics"]["power"] == 20.0
        assert unsynced[2]["payload"]["metrics"]["power"] == 30.0

    def test_get_unsynced_limit(self, cache):
        """Test limit parameter of get_unsynced"""
        for i in range(5):
            cache.cache_telemetry(TelemetryPoint(device_id=f"DEVICE-{i:03d}", power=float(i)))

        unsynced = cache.get_unsynced(limit=2)
        assert len(unsynced) == 2
        assert unsynced[0]["device_id"] == "DEVICE-000"
        assert unsynced[1]["device_id"] == "DEVICE-001"

    def test_mark_synced(self, cache):
        """Test marking telemetry points as synced"""
        cache.cache_telemetry(TelemetryPoint(device_id="CHARGER-001", power=50.0))
        cache.cache_telemetry(TelemetryPoint(device_id="CHARGER-002", power=75.0))

        # Both should be unsynced
        assert len(cache.get_unsynced()) == 2

        # Mark first as synced
        unsynced = cache.get_unsynced()
        cache.mark_synced([unsynced[0]["id"]])

        # Now only one unsynced remains
        remaining = cache.get_unsynced()
        assert len(remaining) == 1
        assert remaining[0]["device_id"] == "CHARGER-002"

    def test_mark_synced_multiple(self, cache):
        """Test marking multiple points as synced at once"""
        ids = []
        for i in range(3):
            cache.cache_telemetry(TelemetryPoint(device_id=f"DEVICE-{i}", power=float(i)))

        unsynced = cache.get_unsynced()
        ids_to_mark = [u["id"] for u in unsynced[:2]]
        cache.mark_synced(ids_to_mark)

        remaining = cache.get_unsynced()
        assert len(remaining) == 1
        assert remaining[0]["device_id"] == "DEVICE-2"

    def test_increment_retry(self, cache):
        """Test incrementing retry count"""
        cache.cache_telemetry(TelemetryPoint(device_id="CHARGER-001", power=50.0))

        unsynced = cache.get_unsynced()
        assert unsynced[0]["retry_count"] == 0

        cache.increment_retry([unsynced[0]["id"]])
        unsynced = cache.get_unsynced()
        assert unsynced[0]["retry_count"] == 1

        cache.increment_retry([unsynced[0]["id"]])
        unsynced = cache.get_unsynced()
        assert unsynced[0]["retry_count"] == 2

    def test_retry_exhaustion(self, cache):
        """Test that points exceeding max_retries are excluded from get_unsynced"""
        # max_retries = 3 from fixture
        cache.cache_telemetry(TelemetryPoint(device_id="CHARGER-001", power=50.0))

        unsynced = cache.get_unsynced()
        id_ = unsynced[0]["id"]

        # Increment retry 3 times (to reach max_retries = 3, so retry_count >= 3 excludes it)
        cache.increment_retry([id_])
        cache.increment_retry([id_])
        cache.increment_retry([id_])

        remaining = cache.get_unsynced()
        assert len(remaining) == 0

    def test_get_cache_size(self, cache):
        """Test get_cache_size returns correct count"""
        assert cache.get_cache_size() == 0

        cache.cache_telemetry(TelemetryPoint(device_id="DEVICE-001", power=10.0))
        assert cache.get_cache_size() == 1

        cache.cache_telemetry(TelemetryPoint(device_id="DEVICE-002", power=20.0))
        assert cache.get_cache_size() == 2

        # Mark one as synced, cache size should decrease
        unsynced = cache.get_unsynced()
        cache.mark_synced([unsynced[0]["id"]])
        assert cache.get_cache_size() == 1

    def test_cleanup(self, cache):
        """Test cleanup removes old synced entries"""
        # Insert a point with an old timestamp and mark it synced
        point = TelemetryPoint(
            device_id="OLD-DEVICE",
            power=10.0,
            timestamp="2020-01-01T00:00:00Z",
        )
        cache.cache_telemetry(point)

        unsynced = cache.get_unsynced()
        cache.mark_synced([unsynced[0]["id"]])

        # Cleanup with max_age_days=1 — the point is years old, should be removed
        cache.cleanup(max_age_days=1)

        # Verify it's gone from the table entirely
        conn = cache._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM telemetry_cache")
        count = cursor.fetchone()[0]
        assert count == 0

    def test_cleanup_preserves_unsynced(self, cache):
        """Test cleanup does not remove unsynced entries"""
        cache.cache_telemetry(TelemetryPoint(device_id="ACTIVE-DEVICE", power=50.0))
        cache.cache_telemetry(TelemetryPoint(device_id="TO-SYNC-DEVICE", power=30.0))

        # Mark one as synced
        unsynced = cache.get_unsynced()
        cache.mark_synced([unsynced[1]["id"]])

        # Cleanup with max_age_days=0 to remove old synced
        cache.cleanup(max_age_days=0)

        # Unsynced should still be there
        remaining = cache.get_unsynced()
        assert len(remaining) == 1
        assert remaining[0]["device_id"] == "ACTIVE-DEVICE"