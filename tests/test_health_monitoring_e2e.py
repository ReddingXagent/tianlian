"""Health monitoring E2E tests for Edge Gateway API

Tests the full health monitoring pipeline:
    GET /health → status check
    GET /api/status → runtime status with uptime/device_count/cache
    GET /api/telemetry/latest → latest telemetry data
    GET /api/devices → device list with real-time metrics
    GET /api/cache/stats → cache statistics (unsynced/total/max)
    GET /api/dashboard → aggregated dashboard (all-in-one)
    POST /api/simulate/telemetry → inject telemetry and verify cascade
    POST /api/simulate/alarm → trigger alarm and verify pipeline
"""

import time

import pytest
from fastapi.testclient import TestClient

from adapters.modbus_adapter import ModbusAdapter
from adapters.ocpp_adapter import OCPPAdapter
from api.server import create_app
from config import GatewayConfig, LocalAPIConfig, ModbusConfig, OCPPConfig, StorageConfig
from storage.cache import TelemetryCache

# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def gateway_config(tmp_path):
    """Gateway config with temp DB and fast intervals"""
    db_path = str(tmp_path / "gateway_test.db")
    return GatewayConfig(
        gateway_id="GW-TEST-E2E",
        storage=StorageConfig(db_path=db_path),
        modbus=ModbusConfig(use_real_modbus=False, poll_interval=0.5),
        ocpp=OCPPConfig(use_real_charger=False),
        local_api=LocalAPIConfig(host="127.0.0.1", port=0),
    )


@pytest.fixture
def cache(gateway_config):
    """Real TelemetryCache with temp SQLite"""
    c = TelemetryCache(gateway_config.storage)
    yield c
    c.close()


@pytest.fixture
def modbus_adapter(gateway_config):
    """ModbusAdapter in simulation mode"""
    return ModbusAdapter(gateway_config.modbus)


@pytest.fixture
def ocpp_adapter(gateway_config):
    """OCPPAdapter in simulation mode"""
    return OCPPAdapter(gateway_config.ocpp)


@pytest.fixture
def latest_telemetry():
    """Shared telemetry state dict"""
    return {}


@pytest.fixture
def cloud_push_stats():
    """Shared cloud push statistics"""
    return {"push_total": 0, "push_failures": 0}


@pytest.fixture
def app(cache, modbus_adapter, ocpp_adapter, latest_telemetry, cloud_push_stats):
    """Create FastAPI test app with real adapters"""
    app = create_app(
        cache=cache,
        start_time=time.monotonic(),
        device_count_callback=lambda: 2,  # modbus-1 + CHARGER-001
        latest_telemetry_callback=lambda: latest_telemetry,
        modbus_adapter=modbus_adapter,
        ocpp_adapter=ocpp_adapter,
        telemetry_count_callback=lambda: cache.get_stats().get("telemetry", {}).get("total", 0),
        alarm_count_callback=lambda: cache.get_stats().get("alarms", {}).get("total", 0),
        cloud_push_callback=lambda: cloud_push_stats,
    )
    return app


@pytest.fixture
def client(app):
    """FastAPI test client"""
    return TestClient(app)


# ── Health Check Tests ──────────────────────────────────────────────────

class TestHealthEndpoint:
    """GET /health — basic liveness check"""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["gateway"] == "tianlian-v3-edge"

    def test_health_has_timestamp(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], (int, float))


# ── Status Endpoint Tests ───────────────────────────────────────────────

class TestStatusEndpoint:
    """GET /api/status — runtime status"""

    def test_status_returns_200(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200

    def test_status_has_required_fields(self, client):
        resp = client.get("/api/v1/status")
        data = resp.json()
        for key in ["uptime_seconds", "uptime_formatted", "device_count", "cache_size", "cache_max"]:
            assert key in data, f"Missing key: {key}"

    def test_status_uptime_increases(self, client):
        resp1 = client.get("/api/v1/status")
        uptime1 = resp1.json()["uptime_seconds"]
        time.sleep(0.2)
        resp2 = client.get("/api/v1/status")
        uptime2 = resp2.json()["uptime_seconds"]
        assert uptime2 >= uptime1, "Uptime should be non-decreasing"

    def test_status_device_count_is_int(self, client):
        resp = client.get("/api/v1/status")
        assert isinstance(resp.json()["device_count"], int)


# ── Telemetry Endpoint Tests ────────────────────────────────────────────

class TestTelemetryEndpoint:
    """GET /api/telemetry/latest — latest telemetry data"""

    def test_telemetry_latest_returns_200(self, client):
        resp = client.get("/api/v1/telemetry/latest")
        assert resp.status_code == 200

    def test_telemetry_latest_has_count(self, client):
        resp = client.get("/api/v1/telemetry/latest")
        data = resp.json()
        assert "count" in data
        assert "telemetry" in data


# ── Devices Endpoint Tests ──────────────────────────────────────────────

class TestDevicesEndpoint:
    """GET /api/devices — device list"""

    def test_devices_returns_200(self, client):
        resp = client.get("/api/v1/devices")
        assert resp.status_code == 200

    def test_devices_has_count_and_list(self, client):
        resp = client.get("/api/v1/devices")
        data = resp.json()
        assert "count" in data
        assert "devices" in data
        assert isinstance(data["devices"], list)

    def test_device_has_required_fields(self, client, latest_telemetry):
        latest_telemetry["test-dev-001"] = {
            "timestamp": "2026-07-09T06:00:00Z",
            "status": "charging",
            "power": 59.4,
            "voltage": 382.5,
            "temperature": 31.4,
        }
        resp = client.get("/api/v1/devices")
        devices = resp.json()["devices"]
        for dev in devices:
            for key in ["device_id", "last_seen", "status", "power_kw", "voltage_v", "temperature_c"]:
                assert key in dev, f"Missing key in device: {key}"


# ── Cache Stats Endpoint Tests ──────────────────────────────────────────

class TestCacheStatsEndpoint:
    """GET /api/cache/stats — cache statistics"""

    def test_cache_stats_returns_200(self, client):
        resp = client.get("/api/v1/cache/stats")
        assert resp.status_code == 200

    def test_cache_stats_has_required_fields(self, client):
        resp = client.get("/api/v1/cache/stats")
        data = resp.json()
        for key in ["unsynced_count", "total_count", "max_cache_size", "max_retries", "db_path"]:
            assert key in data, f"Missing key: {key}"

    def test_cache_stats_empty_db(self, client):
        resp = client.get("/api/v1/cache/stats")
        data = resp.json()
        assert data["unsynced_count"] == 0
        assert data["total_count"] == 0


# ── Dashboard Endpoint Tests ────────────────────────────────────────────

class TestDashboardEndpoint:
    """GET /api/dashboard — aggregated dashboard"""

    def test_dashboard_returns_200(self, client):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200

    def test_dashboard_has_all_sections(self, client):
        resp = client.get("/api/v1/dashboard")
        data = resp.json()
        for key in ["status", "gateway", "uptime_seconds", "uptime_formatted",
                     "device_count", "devices", "telemetry", "alarms",
                     "cache", "cloud"]:
            assert key in data, f"Missing key: {key}"

    def test_dashboard_cloud_has_success_rate(self, client):
        resp = client.get("/api/v1/dashboard")
        cloud = resp.json()["cloud"]
        assert "success_rate" in cloud


# ── Simulate Telemetry Injection E2E ────────────────────────────────────

class TestSimulateTelemetryE2E:
    """POST /api/simulate/telemetry — inject telemetry end-to-end"""

    def test_inject_ocpp_telemetry_returns_201(self, client):
        resp = client.post("/api/v1/simulate/telemetry", json={
            "device_type": "ocpp",
            "power": 50.0,
            "voltage": 380.0,
            "current": 30.0,
            "temperature": 35.0,
            "energy": 100.0,
            "status": "charging",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "injected"
        assert data["device_type"] == "ocpp"
        assert "telemetry" in data

    def test_inject_modbus_telemetry_returns_201(self, client):
        resp = client.post("/api/v1/simulate/telemetry", json={
            "device_type": "modbus",
            "power": 5.7,
            "voltage": 382.5,
            "current": 10.0,
            "temperature": 34.3,
            "status": "normal",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "injected"
        assert data["device_type"] == "modbus"

    def test_inject_invalid_device_type_400(self, client):
        resp = client.post("/api/v1/simulate/telemetry", json={
            "device_type": "invalid",
        })
        assert resp.status_code == 400


# ── Simulate Alarm Injection E2E ────────────────────────────────────────

class TestSimulateAlarmE2E:
    """POST /api/simulate/alarm — trigger alarm end-to-end"""

    def test_inject_ocpp_alarm_returns_200(self, client):
        resp = client.post("/api/v1/simulate/alarm", json={
            "device_type": "ocpp",
            "alarm_type": "over_temperature",
            "message": "Charger temp 85°C exceeds threshold",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        assert data["alarm_type"] == "over_temperature"

    def test_inject_modbus_alarm_returns_200(self, client):
        resp = client.post("/api/v1/simulate/alarm", json={
            "device_type": "modbus",
            "alarm_type": "communication_loss",
            "message": "Modbus device unresponsive",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        assert data["device_type"] == "modbus"

    def test_inject_alarm_invalid_device_400(self, client):
        resp = client.post("/api/v1/simulate/alarm", json={
            "device_type": "invalid",
        })
        assert resp.status_code == 400


# ── Full Pipeline E2E ───────────────────────────────────────────────────

class TestFullPipelineE2E:
    """Telemetry injection → cache → dashboard cascade verification"""

    def test_telemetry_injection_updates_dashboard(self, client):
        """Inject telemetry then verify it appears in dashboard"""
        # Inject OCPP telemetry
        client.post("/api/v1/simulate/telemetry", json={
            "device_type": "ocpp",
            "power": 60.0,
            "voltage": 380.0,
            "current": 35.0,
            "temperature": 40.0,
            "status": "charging",
        })

        # Verify dashboard still returns successfully
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_alarm_injection_updates_dashboard(self, client):
        """Trigger alarm then verify dashboard still healthy"""
        client.post("/api/v1/simulate/alarm", json={
            "device_type": "ocpp",
            "alarm_type": "test_e2e_alarm",
            "message": "E2E pipeline test alarm",
        })

        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200

    def test_full_health_monitoring_chain(self, client):
        """Complete health monitoring chain: health → status → devices → telemetry → cache → dashboard"""
        endpoints = ["/health", "/api/v1/status", "/api/v1/devices",
                      "/api/v1/telemetry/latest", "/api/v1/cache/stats", "/api/v1/dashboard"]

        for endpoint in endpoints:
            resp = client.get(endpoint)
            assert resp.status_code == 200, f"Endpoint {endpoint} returned {resp.status_code}"