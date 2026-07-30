"""Tests for enhanced TelemetryCache (T-1102: batch ops, alarms, stats, state)"""


import pytest

from config import StorageConfig
from models import TelemetryPoint
from storage.cache import TelemetryCache


@pytest.fixture
def temp_db(tmp_path):
    """Use a temporary database for each test"""
    db_path = str(tmp_path / "test_gateway.db")
    config = StorageConfig(db_path=db_path, max_retries=5, batch_sync_size=200)
    cache = TelemetryCache(config)
    yield cache
    cache.close()


@pytest.fixture
def sample_points():
    return [
        TelemetryPoint(device_id="EVSE-001", power=22.5, voltage=400.0, current=56.0),
        TelemetryPoint(device_id="EVSE-001", power=23.0, voltage=400.1, current=56.2),
        TelemetryPoint(device_id="EVSE-002", power=11.0, voltage=398.0, current=27.5),
        TelemetryPoint(device_id="EVSE-003", power=7.5, voltage=395.0, current=19.0),
        TelemetryPoint(device_id="EVSE-003", power=0.0, voltage=0.0, current=0.0, status="idle"),
    ]


class TestTelemetryBatchOps:
    """Test batch telemetry caching"""

    def test_cache_single_point(self, temp_db, sample_points):
        temp_db.cache_telemetry(sample_points[0])
        assert temp_db.get_cache_size() == 1

    def test_cache_batch_points(self, temp_db, sample_points):
        count = temp_db.cache_telemetry_batch(sample_points)
        assert count == 5
        assert temp_db.get_cache_size() == 5

    def test_cache_batch_empty(self, temp_db):
        count = temp_db.cache_telemetry_batch([])
        assert count == 0
        assert temp_db.get_cache_size() == 0

    def test_cache_batch_priority(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points, priority=5)
        unsynced = temp_db.get_unsynced(limit=10)
        assert all(u["priority"] == 5 for u in unsynced)

    def test_get_unsynced_orders_by_priority(self, temp_db, sample_points):
        # Cache low priority first, then high priority
        temp_db.cache_telemetry(sample_points[0], priority=0)
        temp_db.cache_telemetry(sample_points[1], priority=10)
        temp_db.cache_telemetry(sample_points[2], priority=5)

        unsynced = temp_db.get_unsynced(limit=10)
        # Highest priority should come first
        assert unsynced[0]["priority"] == 10
        assert unsynced[1]["priority"] == 5
        assert unsynced[2]["priority"] == 0

    def test_get_unsynced_priority_only(self, temp_db, sample_points):
        temp_db.cache_telemetry(sample_points[0], priority=0)
        temp_db.cache_telemetry(sample_points[1], priority=10)

        priority_only = temp_db.get_unsynced(limit=10, priority_only=True)
        assert len(priority_only) == 1
        assert priority_only[0]["priority"] == 10

    def test_mark_synced_batch(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        unsynced = temp_db.get_unsynced(limit=10)
        ids = [u["id"] for u in unsynced]

        temp_db.mark_synced_batch(ids)
        assert temp_db.get_cache_size() == 0

    def test_mark_synced_empty(self, temp_db):
        temp_db.mark_synced([])  # should not crash

    def test_increment_retry_batch(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        unsynced = temp_db.get_unsynced(limit=10)
        ids = [u["id"] for u in unsynced]

        temp_db.increment_retry(ids)
        unsynced2 = temp_db.get_unsynced(limit=10)
        assert all(u["retry_count"] == 1 for u in unsynced2)

    def test_increment_retry_empty(self, temp_db):
        temp_db.increment_retry([])  # should not crash

    def test_get_unsynced_count(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        assert temp_db.get_unsynced_count() == 5
        # Mark some synced
        unsynced = temp_db.get_unsynced(limit=3)
        temp_db.mark_synced([u["id"] for u in unsynced])
        assert temp_db.get_unsynced_count() == 2


class TestAlarmCache:
    """Test alarm caching (T-1102 new feature)"""

    def test_cache_alarm(self, temp_db):
        alarm_id = temp_db.cache_alarm("EVSE-001", {
            "alarm_type": "overtemp",
            "message": "Temperature exceeded 80°C",
            "severity": "critical",
            "timestamp": "2026-06-28T10:00:00Z",
        })
        assert alarm_id > 0

    def test_get_unsynced_alarms(self, temp_db):
        temp_db.cache_alarm("EVSE-001", {"type": "overtemp", "timestamp": "2026-06-28T10:00:00Z"})
        temp_db.cache_alarm("EVSE-002", {"type": "comm_loss", "timestamp": "2026-06-28T10:01:00Z"})

        alarms = temp_db.get_unsynced_alarms()
        assert len(alarms) == 2

    def test_mark_alarms_synced(self, temp_db):
        temp_db.cache_alarm("EVSE-001", {"type": "overtemp"})
        temp_db.cache_alarm("EVSE-002", {"type": "comm_loss"})

        alarms = temp_db.get_unsynced_alarms()
        temp_db.mark_alarms_synced([a["id"] for a in alarms])

        assert temp_db.get_unsynced_alarms() == []

    def test_increment_alarm_retry(self, temp_db):
        temp_db.cache_alarm("EVSE-001", {"type": "overtemp"})
        alarms = temp_db.get_unsynced_alarms()
        temp_db.increment_alarm_retry([a["id"] for a in alarms])

        alarms2 = temp_db.get_unsynced_alarms()
        assert all(a["retry_count"] == 1 for a in alarms2)

    def test_alarm_in_unsynced_count(self, temp_db):
        temp_db.cache_alarm("EVSE-001", {"type": "overtemp"})
        assert temp_db.get_unsynced_count() == 1

    def test_mark_alarms_synced_empty(self, temp_db):
        temp_db.mark_alarms_synced([])


class TestGatewayState:
    """Test gateway state persistence (T-1102 new feature)"""

    def test_save_load_state(self, temp_db):
        temp_db.save_state("last_boot", "2026-06-28T07:00:00Z")
        assert temp_db.load_state("last_boot") == "2026-06-28T07:00:00Z"

    def test_load_missing_state_returns_default(self, temp_db):
        assert temp_db.load_state("missing", "default_val") == "default_val"

    def test_overwrite_state(self, temp_db):
        temp_db.save_state("counter", "1")
        temp_db.save_state("counter", "2")
        assert temp_db.load_state("counter") == "2"

    def test_load_all_state(self, temp_db):
        temp_db.save_state("key1", "val1")
        temp_db.save_state("key2", "val2")
        state = temp_db.load_all_state()
        assert state["key1"] == "val1"
        assert state["key2"] == "val2"


class TestCacheStats:
    """Test cache statistics"""

    def test_get_stats_empty(self, temp_db):
        stats = temp_db.get_stats()
        assert stats["telemetry"]["total"] == 0
        assert stats["alarms"]["total"] == 0
        assert stats["db_size_bytes"] > 0  # file exists even if empty

    def test_get_stats_with_data(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        temp_db.cache_alarm("EVSE-001", {"type": "overtemp"})

        stats = temp_db.get_stats()
        assert stats["telemetry"]["total"] == 5
        assert stats["telemetry"]["unsynced"] == 5
        assert stats["telemetry"]["synced"] == 0
        assert stats["alarms"]["total"] == 1

    def test_get_stats_after_sync(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        unsynced = temp_db.get_unsynced(limit=5)
        temp_db.mark_synced([u["id"] for u in unsynced])

        stats = temp_db.get_stats()
        assert stats["telemetry"]["synced"] == 5
        assert stats["telemetry"]["unsynced"] == 0

    def test_get_stats_db_path(self, temp_db):
        stats = temp_db.get_stats()
        assert "db_path" in stats
        assert stats["db_path"].endswith(".db")


class TestCleanup:
    """Test cleanup operations"""

    def test_cleanup_removes_synced_old(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        unsynced = temp_db.get_unsynced(limit=5)
        temp_db.mark_synced([u["id"] for u in unsynced])

        deleted = temp_db.cleanup(max_age_days=7)
        # Entries created just now, so shouldn't be deleted
        assert deleted == 0

    def test_cleanup_keeps_unsynced(self, temp_db, sample_points):
        temp_db.cache_telemetry_batch(sample_points)
        # Don't mark as synced
        deleted = temp_db.cleanup(max_age_days=0)  # aggressive
        # Should still not delete unsynced
        assert temp_db.get_cache_size() == 5


class TestRetryBehavior:
    """Test retry count and max retry behavior"""

    def test_max_retries_excludes_entries(self, temp_db, sample_points):
        config = StorageConfig(
            db_path=temp_db.config.db_path,
            max_retries=2,
        )
        cache = TelemetryCache(config)
        try:
            cache.cache_telemetry(sample_points[0])

            # Increment retry beyond max
            entry = cache.get_unsynced()[0]
            cache.increment_retry([entry["id"]])
            cache.increment_retry([entry["id"]])

            # Should not appear in unsynced anymore
            assert cache.get_unsynced() == []
        finally:
            cache.close()
