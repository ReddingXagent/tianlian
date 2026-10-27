"""Tests for enhanced TelemetryCache (T-1102: batch ops, alarms, stats, state)"""


from unittest.mock import patch

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
        temp_db.cleanup(max_age_days=0)  # aggressive
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


# ── Coverage boost: empty-list guards, cleanup VACUUM, close/__del__ ──


class TestEmptyListGuards:
    """Cover the early-return paths when ids list is empty."""

    def test_mark_cloud_synced_empty_list(self, temp_db):
        """mark_cloud_synced with empty list should return immediately."""
        # Should not raise
        temp_db.mark_cloud_synced([])

    def test_mark_alarms_cloud_synced_empty_list(self, temp_db):
        """mark_alarms_cloud_synced with empty list should return immediately."""
        temp_db.mark_alarms_cloud_synced([])

    def test_increment_alarm_retry_empty_list(self, temp_db):
        """increment_alarm_retry with empty list should return immediately."""
        temp_db.increment_alarm_retry([])


class TestCleanupVacuum:
    """Cover the VACUUM path in cleanup() when entries are actually deleted."""

    def test_cleanup_vacuums_when_entries_deleted(self, temp_db, sample_points):
        """cleanup() should execute VACUUM when old synced entries are purged."""
        # Insert and sync telemetry
        for p in sample_points:
            temp_db.cache_telemetry(p)
        unsynced = temp_db.get_unsynced()
        ids = [e["id"] for e in unsynced]
        temp_db.mark_cloud_synced(ids)
        temp_db.mark_synced(ids)

        # Insert and sync an alarm
        temp_db.cache_alarm("EVSE-001", {"type": "OverVoltage", "message": "Voltage too high"})
        alarms = temp_db.get_unsynced_alarms()
        alarm_ids = [a["id"] for a in alarms]
        temp_db.mark_alarms_cloud_synced(alarm_ids)
        temp_db.mark_alarms_synced(alarm_ids)

        # Manually backdate timestamps so cleanup finds them
        conn = temp_db._get_conn()
        conn.execute(
            "UPDATE telemetry_cache SET created_at = '2020-01-01T00:00:00Z'"
        )
        conn.execute(
            "UPDATE alarm_cache SET created_at = '2020-01-01T00:00:00Z'"
        )
        conn.commit()

        deleted = temp_db.cleanup(max_age_days=1)
        assert deleted > 0


class TestCloseAndDel:
    """Cover close() and __del__ cleanup paths."""

    def test_close_sets_conn_to_none(self, tmp_path):
        """close() should set _conn to None."""
        db_path = str(tmp_path / "test_close.db")
        config = StorageConfig(db_path=db_path)
        cache = TelemetryCache(config)
        # Trigger lazy connection
        cache._get_conn()
        assert cache._conn is not None
        cache.close()
        assert cache._conn is None

    def test_close_idempotent(self, tmp_path):
        """Double close should not raise."""
        db_path = str(tmp_path / "test_double.db")
        config = StorageConfig(db_path=db_path)
        cache = TelemetryCache(config)
        cache.close()
        cache.close()  # Should not raise

    def test_del_calls_close(self, tmp_path):
        """__del__ should call close() without raising."""
        db_path = str(tmp_path / "test_del.db")
        config = StorageConfig(db_path=db_path)
        cache = TelemetryCache(config)
        # Force __del__
        cache.__del__()
        assert cache._conn is None

    def test_del_swallows_exception(self, tmp_path):
        """__del__ should swallow any exception during cleanup."""
        db_path = str(tmp_path / "test_del_exc.db")
        config = StorageConfig(db_path=db_path)
        cache = TelemetryCache(config)
        cache.close()
        # After close, _conn is None; calling __del__ again should still not raise
        cache.__del__()

    def test_del_swallows_close_exception(self, tmp_path):
        """__del__ should catch and swallow exceptions from close()."""
        db_path = str(tmp_path / "test_del_swallow.db")
        config = StorageConfig(db_path=db_path)
        cache = TelemetryCache(config)
        # Patch close to raise
        with patch.object(cache, "close", side_effect=RuntimeError("boom")):
            # Should not raise
            cache.__del__()


class TestEnforceCacheLimit:
    """Cover _enforce_cache_limit eviction path when cache exceeds max_cache_size."""

    def test_eviction_when_over_limit(self, tmp_path, sample_points):
        """When telemetry_cache rows exceed max_cache_size * 1.05, oldest are evicted."""
        db_path = str(tmp_path / "test_evict.db")
        config = StorageConfig(db_path=db_path, max_cache_size=5)
        cache = TelemetryCache(config)
        try:
            # Insert 10 points (well above threshold of int(5 * 1.05) = 5)
            for _i in range(10):
                cache.cache_telemetry(sample_points[0])

            # Verify eviction occurred - should have at most max_cache_size entries
            conn = cache._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM telemetry_cache")
            count = cursor.fetchone()[0]
            assert count <= 5, f"Expected <= 5 after eviction, got {count}"
        finally:
            cache.close()
