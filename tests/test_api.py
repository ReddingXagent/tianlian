"""Tests for api/server.py — Local debug API endpoint coverage.

Covers all 9 endpoints: health, status, telemetry/latest, devices,
simulate/telemetry, simulate/alarm, cache/stats, dashboard, perf.
"""

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from config import StorageConfig
from storage.cache import TelemetryCache


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def cache():
    """In-memory TelemetryCache."""
    return TelemetryCache(StorageConfig(db_path=":memory:"))


@pytest.fixture
def callbacks():
    """Standard callback set for testing."""
    return dict(
        device_count_callback=lambda: 3,
        latest_telemetry_callback=lambda: {
            "DEV-001": {
                "power": 10.5,
                "voltage": 380.0,
                "current": 27.6,
                "temperature": 35.2,
                "status": "charging",
                "timestamp": "2026-08-03T08:00:00Z",
            },
            "DEV-002": {
                "power": 0.0,
                "voltage": 380.0,
                "current": 0.0,
                "temperature": 25.0,
                "status": "idle",
                "timestamp": "2026-08-03T08:00:01Z",
            },
        },
        telemetry_count_callback=lambda: 500,
        alarm_count_callback=lambda: 12,
        cloud_push_callback=lambda: {
            "push_total": 480,
            "push_failures": 20,
        },
    )


@pytest.fixture
def client(cache, callbacks):
    """TestClient with standard app configuration."""
    app = create_app(cache=cache, start_time=time.monotonic(), **callbacks)
    return TestClient(app)


@pytest.fixture
def client_no_adapters(cache):
    """TestClient without adapters or extra callbacks."""
    app = create_app(cache=cache, start_time=time.monotonic())
    return TestClient(app)


# ── Health ───────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """GET /health"""

    def test_returns_healthy_status(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["gateway"] == "tianlian-v3-edge"
        assert "timestamp" in body

    def test_response_time_under_50ms(self, client):
        start = time.monotonic()
        client.get("/health")
        elapsed = time.monotonic() - start
        assert elapsed < 0.05, f"Health check took {elapsed:.3f}s"


# ── Gateway Status ───────────────────────────────────────────────────────


class TestStatusEndpoint:
    """GET /api/v1/status"""

    def test_returns_all_fields(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "uptime_seconds" in body
        assert "uptime_formatted" in body
        assert body["device_count"] == 3
        assert "cache_size" in body
        assert "cache_max" in body

    def test_uptime_non_negative(self, client):
        resp = client.get("/api/v1/status")
        assert resp.json()["uptime_seconds"] >= 0

    def test_uptime_formatted_is_string(self, client):
        resp = client.get("/api/v1/status")
        assert isinstance(resp.json()["uptime_formatted"], str)

    def test_no_callbacks_returns_zeros(self, client_no_adapters):
        resp = client_no_adapters.get("/api/v1/status")
        body = resp.json()
        assert body["device_count"] == 0


# ── Latest Telemetry ─────────────────────────────────────────────────────


class TestLatestTelemetryEndpoint:
    """GET /api/v1/telemetry/latest"""

    def test_returns_telemetry_data(self, client):
        resp = client.get("/api/v1/telemetry/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert "DEV-001" in body["telemetry"]
        assert body["telemetry"]["DEV-001"]["power"] == 10.5

    def test_empty_when_no_callback(self, client_no_adapters):
        resp = client_no_adapters.get("/api/v1/telemetry/latest")
        body = resp.json()
        assert body["count"] == 0
        assert body["telemetry"] == {}


# ── Devices ──────────────────────────────────────────────────────────────


class TestDevicesEndpoint:
    """GET /api/v1/devices"""

    def test_returns_device_list(self, client):
        resp = client.get("/api/v1/devices")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        devices = body["devices"]
        ids = {d["device_id"] for d in devices}
        assert ids == {"DEV-001", "DEV-002"}

    def test_device_fields(self, client):
        resp = client.get("/api/v1/devices")
        device = resp.json()["devices"][0]
        expected_keys = {
            "device_id",
            "last_seen",
            "status",
            "power_kw",
            "voltage_v",
            "temperature_c",
        }
        assert expected_keys.issubset(device.keys())

    def test_empty_devices(self, client_no_adapters):
        resp = client_no_adapters.get("/api/v1/devices")
        body = resp.json()
        assert body["count"] == 0
        assert body["devices"] == []


# ── Cache Stats ──────────────────────────────────────────────────────────


class TestCacheStatsEndpoint:
    """GET /api/v1/cache/stats"""

    def test_returns_stats(self, client):
        resp = client.get("/api/v1/cache/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "unsynced_count" in body
        assert "total_count" in body
        assert "max_cache_size" in body
        assert "max_retries" in body
        assert "db_path" in body

    def test_cache_max_matches_config(self, client):
        resp = client.get("/api/v1/cache/stats")
        body = resp.json()
        assert body["max_cache_size"] == 10000
        assert body["max_retries"] == 5


# ── Dashboard ────────────────────────────────────────────────────────────


class TestDashboardEndpoint:
    """GET /api/v1/dashboard"""

    def test_returns_aggregated_data(self, client):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["gateway"] == "tianlian-v3-edge"
        assert body["device_count"] == 3
        assert len(body["devices"]) == 2
        assert body["telemetry"]["total"] == 500
        assert body["alarms"]["total"] == 12

    def test_cloud_success_rate(self, client):
        resp = client.get("/api/v1/dashboard")
        body = resp.json()
        # 480 pushed, 20 failed → 480/500 = 0.96
        assert body["cloud"]["success_rate"] == 0.96

    def test_cloud_success_rate_zero_division(self, cache):
        """When no pushes at all, success rate should be 1.0."""
        app = create_app(
            cache=cache,
            start_time=time.monotonic(),
            cloud_push_callback=lambda: {"push_total": 0, "push_failures": 0},
        )
        resp = TestClient(app).get("/api/v1/dashboard")
        assert resp.json()["cloud"]["success_rate"] == 1.0

    def test_telemetry_rate(self, client):
        resp = client.get("/api/v1/dashboard")
        body = resp.json()
        assert body["telemetry"]["rate_per_sec"] > 0


# ── Performance Metrics ─────────────────────────────────────────────────


class TestPerfEndpoint:
    """GET /api/v1/perf"""

    def test_returns_perf_data(self, client):
        resp = client.get("/api/v1/perf")
        assert resp.status_code == 200
        body = resp.json()
        assert "uptime_seconds" in body
        assert body["device_count"] == 3
        assert body["throughput"]["telemetry_total"] == 500
        assert body["throughput"]["alarm_total"] == 12
        assert body["throughput"]["telemetry_rate_per_sec"] > 0
        assert "cache" in body
        assert "cloud" in body

    def test_cloud_success_rate_in_perf(self, client):
        resp = client.get("/api/v1/perf")
        body = resp.json()
        assert body["cloud"]["success_rate"] == 0.96


# ── Simulate Telemetry ──────────────────────────────────────────────────


class TestSimulateTelemetryEndpoint:
    """POST /api/v1/simulate/telemetry"""

    def test_ocpp_without_adapter_returns_400(self, client):
        resp = client.post(
            "/api/v1/simulate/telemetry",
            json={"device_type": "ocpp", "power": 50.0},
        )
        assert resp.status_code == 400
        assert "OCPP adapter not available" in resp.json()["detail"]

    def test_modbus_without_adapter_returns_400(self, client):
        resp = client.post(
            "/api/v1/simulate/telemetry",
            json={"device_type": "modbus", "power": 30.0},
        )
        assert resp.status_code == 400
        assert "Modbus adapter not available" in resp.json()["detail"]

    def test_unknown_device_type_returns_400(self, client):
        resp = client.post(
            "/api/v1/simulate/telemetry",
            json={"device_type": "unknown", "power": 10.0},
        )
        assert resp.status_code == 400
        assert "unknown" in resp.json()["detail"].lower()

    def test_with_mock_ocpp_adapter(self, cache):
        """Test successful telemetry injection with mock adapter."""
        mock_ocpp = MagicMock()
        mock_ocpp.inject_telemetry.return_value = MagicMock(
            to_dict=lambda: {"power": 50.0, "status": "injected"}
        )
        app = create_app(
            cache=cache,
            start_time=time.monotonic(),
            ocpp_adapter=mock_ocpp,
        )
        resp = TestClient(app).post(
            "/api/v1/simulate/telemetry",
            json={"device_type": "ocpp", "power": 50.0, "voltage": 400.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "injected"
        assert body["device_type"] == "ocpp"
        mock_ocpp.inject_telemetry.assert_called_once()

    def test_with_mock_modbus_adapter(self, cache):
        """Test successful modbus telemetry injection."""
        mock_modbus = MagicMock()
        mock_modbus.inject_telemetry.return_value = MagicMock(
            to_dict=lambda: {"power": 25.0, "status": "injected"}
        )
        app = create_app(
            cache=cache,
            start_time=time.monotonic(),
            modbus_adapter=mock_modbus,
        )
        resp = TestClient(app).post(
            "/api/v1/simulate/telemetry",
            json={"device_type": "modbus", "power": 25.0},
        )
        assert resp.status_code == 200
        assert resp.json()["device_type"] == "modbus"

    def test_default_values(self, cache):
        """Test that default values from the schema work."""
        mock_ocpp = MagicMock()
        mock_ocpp.inject_telemetry.return_value = MagicMock(to_dict=lambda: {})
        app = create_app(
            cache=cache, start_time=time.monotonic(), ocpp_adapter=mock_ocpp
        )
        resp = TestClient(app).post(
            "/api/v1/simulate/telemetry",
            json={},
        )
        assert resp.status_code == 200
        # Verify defaults were used
        call_kwargs = mock_ocpp.inject_telemetry.call_args.kwargs
        assert call_kwargs["power"] == 0.0
        assert call_kwargs["voltage"] == 380.0
        assert call_kwargs["status"] == "normal"


# ── Simulate Alarm ──────────────────────────────────────────────────────


class TestSimulateAlarmEndpoint:
    """POST /api/v1/simulate/alarm"""

    def test_ocpp_without_adapter_returns_400(self, client):
        resp = client.post(
            "/api/v1/simulate/alarm",
            json={"device_type": "ocpp", "alarm_type": "overheating"},
        )
        assert resp.status_code == 400

    def test_unknown_device_type_returns_400(self, client):
        resp = client.post(
            "/api/v1/simulate/alarm",
            json={"device_type": "invalid"},
        )
        assert resp.status_code == 400

    def test_with_mock_ocpp_adapter(self, cache):
        mock_ocpp = MagicMock()
        app = create_app(
            cache=cache, start_time=time.monotonic(), ocpp_adapter=mock_ocpp
        )
        resp = TestClient(app).post(
            "/api/v1/simulate/alarm",
            json={
                "device_type": "ocpp",
                "alarm_type": "over_voltage",
                "message": "Voltage exceeded threshold",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "triggered"
        assert body["alarm_type"] == "over_voltage"
        mock_ocpp.inject_alarm.assert_called_once_with(
            "over_voltage", "Voltage exceeded threshold"
        )

    def test_with_mock_modbus_adapter(self, cache):
        mock_modbus = MagicMock()
        app = create_app(
            cache=cache, start_time=time.monotonic(), modbus_adapter=mock_modbus
        )
        resp = TestClient(app).post(
            "/api/v1/simulate/alarm",
            json={"device_type": "modbus", "alarm_type": "comm_loss"},
        )
        assert resp.status_code == 200
        assert resp.json()["device_type"] == "modbus"

    def test_default_values(self, cache):
        mock_ocpp = MagicMock()
        app = create_app(
            cache=cache, start_time=time.monotonic(), ocpp_adapter=mock_ocpp
        )
        resp = TestClient(app).post("/api/v1/simulate/alarm", json={})
        assert resp.status_code == 200
        call_args = mock_ocpp.inject_alarm.call_args.args
        assert call_args[0] == "test_alarm"
        assert call_args[1] == "Manual test alarm"


# ── CORS ─────────────────────────────────────────────────────────────────


class TestCORS:
    """Verify CORS middleware is configured for mobile app access."""

    def test_cors_allows_all_origins(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        # CORSMiddleware echoes the requesting origin when allow_origins=[*]
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_allows_post(self, client):
        resp = client.options(
            "/api/v1/simulate/telemetry",
            headers={
                "Origin": "http://192.168.31.10:8081",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200


# ── Format Uptime Helper ────────────────────────────────────────────────


class TestFormatUptime:
    """Test the _format_uptime helper function."""

    def test_formats_seconds(self):
        from api.server import _format_uptime

        assert _format_uptime(0) == "0s"
        assert _format_uptime(45) == "45s"
        assert _format_uptime(60) == "1m 0s"
        assert _format_uptime(3600) == "1h 0s"
        assert _format_uptime(90061) == "1d 1h 1m 1s"

    def test_formats_days(self):
        from api.server import _format_uptime

        result = _format_uptime(86400 * 3 + 3661)
        assert "3d" in result
        assert "1h" in result
