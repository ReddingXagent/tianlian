"""时间窗 Query 参数无界加固测试 (任务卡 eb23751f)

给 5 个端点的时间窗参数补 FastAPI 声明式 ge/le 边界 (纯校验, 零逻辑改动):
- GET  /api/v1/telemetry/device/{id}/history   hours: ge=1, le=720
- GET  /api/v1/telemetry/device/{id}/stats     hours: ge=1, le=720
- POST /api/v1/telemetry/device/{id}/simulate  hours: ge=1, le=72; interval_seconds: ge=1, le=3600
- POST /api/v1/healing/batch-verify            hours: ge=1, le=720
- GET  /api/v1/operate/revenue/daily-trend     days: ge=1, le=730

超界/越下限 → 422 (Pydantic 声明式校验); 合法边界值 → 非 422。
鉴权: telemetry 三端点走 X-API-Key 网关路径 (对齐 test_telemetry_routes.py);
healing / revenue 走 client fixture 默认 admin token。
"""
import pytest

from app.models.api_gateway import ApiClient, GatewayApiKey
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus

TLM_URL = "/api/v1/telemetry"
HEAL_URL = "/api/v1/healing/batch-verify"
REV_URL = "/api/v1/operate/revenue/daily-trend"


@pytest.fixture
def tlm_station(client):
    s = client._sesh
    st = Station(name="时间窗站A", code="TW-A", status=StationStatus.NORMAL)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


@pytest.fixture
def tlm_device(client, tlm_station):
    s = client._sesh
    d = Device(sn="TW-PV", name="光伏#1", code="TWPV",
               type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
               station_id=tlm_station.id)
    s.add(d)
    s.commit()
    s.refresh(d)
    return d


@pytest.fixture
def gw_headers(client):
    """签发一张 active 网关 X-API-Key (对齐 tests/api/test_telemetry_routes.py 范式)。"""
    s = client._sesh
    ac = ApiClient(client_id="tw-cli", client_secret_hash="x", name="tw")
    s.add(ac)
    s.commit()
    s.refresh(ac)
    s.add(GatewayApiKey(key_id="tw-k1", client_id=ac.id, name="k",
                        api_key="tw-gw-key-secret"))
    s.commit()
    return {"X-API-Key": "tw-gw-key-secret"}


# ─── GET /telemetry/device/{id}/history ────────────────────────────────────

class TestTelemetryHistoryBounds:
    def test_over_max_422(self, client, tlm_device, gw_headers):
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/history",
                       params={"hours": 100000}, headers=gw_headers)
        assert r.status_code == 422

    def test_below_min_422(self, client, tlm_device, gw_headers):
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/history",
                       params={"hours": 0}, headers=gw_headers)
        assert r.status_code == 422
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/history",
                       params={"hours": -1}, headers=gw_headers)
        assert r.status_code == 422

    def test_boundary_720_ok(self, client, tlm_device, gw_headers):
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/history",
                       params={"hours": 720}, headers=gw_headers)
        assert r.status_code != 422


# ─── GET /telemetry/device/{id}/stats ──────────────────────────────────────

class TestTelemetryStatsBounds:
    def test_over_max_422(self, client, tlm_device, gw_headers):
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/stats",
                       params={"hours": 100000}, headers=gw_headers)
        assert r.status_code == 422

    def test_below_min_422(self, client, tlm_device, gw_headers):
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/stats",
                       params={"hours": 0}, headers=gw_headers)
        assert r.status_code == 422

    def test_boundary_720_ok(self, client, tlm_device, gw_headers):
        r = client.get(f"{TLM_URL}/device/{tlm_device.id}/stats",
                       params={"hours": 720}, headers=gw_headers)
        assert r.status_code != 422


# ─── POST /telemetry/device/{id}/simulate ──────────────────────────────────

class TestTelemetrySimulateBounds:
    URL_FMT = TLM_URL + "/device/{}/simulate"

    def test_hours_over_max_422(self, client, tlm_device, gw_headers):
        r = client.post(self.URL_FMT.format(tlm_device.id),
                        params={"hours": 100000, "interval_seconds": 60},
                        headers=gw_headers)
        assert r.status_code == 422

    def test_hours_below_min_422(self, client, tlm_device, gw_headers):
        r = client.post(self.URL_FMT.format(tlm_device.id),
                        params={"hours": 0, "interval_seconds": 60},
                        headers=gw_headers)
        assert r.status_code == 422

    def test_interval_over_max_422(self, client, tlm_device, gw_headers):
        r = client.post(self.URL_FMT.format(tlm_device.id),
                        params={"hours": 1, "interval_seconds": 100000},
                        headers=gw_headers)
        assert r.status_code == 422

    def test_interval_zero_422(self, client, tlm_device, gw_headers):
        r = client.post(self.URL_FMT.format(tlm_device.id),
                        params={"hours": 1, "interval_seconds": 0},
                        headers=gw_headers)
        assert r.status_code == 422

    def test_boundary_minimal_ok(self, client, tlm_device, gw_headers):
        """最小写放大组合 hours=1 + interval_seconds=3600 (仅 1 条)"""
        r = client.post(self.URL_FMT.format(tlm_device.id),
                        params={"hours": 1, "interval_seconds": 3600},
                        headers=gw_headers)
        assert r.status_code != 422

    def test_interval_boundary_1_ok(self, client, tlm_device, gw_headers):
        """interval_seconds=1 合法边界 (hours=1 → 3600 条, 最小 hours 下可接受)"""
        r = client.post(self.URL_FMT.format(tlm_device.id),
                        params={"hours": 1, "interval_seconds": 1},
                        headers=gw_headers)
        assert r.status_code != 422


# ─── POST /healing/batch-verify ────────────────────────────────────────────

class TestHealingBatchVerifyBounds:
    def test_over_max_422(self, client):
        r = client.post(HEAL_URL, params={"hours": 100000})
        assert r.status_code == 422

    def test_below_min_422(self, client):
        r = client.post(HEAL_URL, params={"hours": 0})
        assert r.status_code == 422
        r = client.post(HEAL_URL, params={"hours": -5})
        assert r.status_code == 422

    def test_boundary_720_ok(self, client):
        r = client.post(HEAL_URL, params={"hours": 720})
        assert r.status_code != 422


# ─── GET /operate/revenue/daily-trend ──────────────────────────────────────

class TestRevenueDailyTrendBounds:
    def test_over_max_422(self, client):
        r = client.get(REV_URL, params={"days": 100000})
        assert r.status_code == 422

    def test_below_min_422(self, client):
        r = client.get(REV_URL, params={"days": 0})
        assert r.status_code == 422
        r = client.get(REV_URL, params={"days": -1})
        assert r.status_code == 422

    def test_boundary_730_ok(self, client):
        r = client.get(REV_URL, params={"days": 730})
        assert r.status_code != 422
