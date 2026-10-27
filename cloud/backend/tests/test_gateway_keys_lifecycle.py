"""卡片 ba9d3461: X-API-Key 网关密钥生命周期 — 管理面 /keys 挂载 + revoke/rotate。

覆盖:
- POST /api/v1/gateway/keys 创建 → X-API-Key 鉴权可用
- POST /api/v1/gateway/keys/{key_id}/revoke → 旧 key 立即 401 (缓存联动失效)
- POST /api/v1/gateway/keys/{key_id}/rotate → 旧 key 401, 新 key 可用
- GET /api/v1/gateway/stats days 参数边界 (ge=1, le=90)
- oauth/token authorization_code: code 查表验证, 无效/过期 code 拒绝
"""
from datetime import datetime as dt, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import auth_throttle as tel_mod

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_caches(test_db):
    """注入 test_db + 清空进程内网关鉴权缓存 (撤销/轮换后旧 key 不得残留缓存)。"""
    tel_mod._reset_gateway_auth_caches()
    yield
    tel_mod._reset_gateway_auth_caches()


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(
        name="密钥生命周期站", code="GW-KEY-STATION-001", status=StationStatus.NORMAL
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus
    device = Device(
        sn="GW-KEY-DEV-001",
        name="密钥生命周期设备",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=test_station.id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@pytest.fixture
def api_client_row(test_db):
    """直接落库一个 ApiClient (管理端 /clients 端点由 api_gateway 自身覆盖)。"""
    db = test_db["session"]
    from app.models.api_gateway import ApiClient
    import hashlib
    ac = ApiClient(
        client_id="gw_lifecycle_client_001",
        client_secret_hash=hashlib.sha256(b"secret-001").hexdigest(),
        name="lifecycle client",
    )
    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac


def _telemetry_with_key(api_key: str, device_id: int):
    # 临时摘掉 Authorization 强制走 X-API-Key 网关分支, 用完恢复 (后续管理面端点仍需 token)
    saved = client.headers.get("Authorization")
    client.headers.pop("Authorization", None)
    try:
        return client.post(
            "/api/v1/telemetry/batch-report",
            headers={"X-API-Key": api_key},
            json={"records": [{"device_id": device_id, "grid_voltage_a": 220.0}]},
        )
    finally:
        if saved:
            client.headers["Authorization"] = saved


class TestKeysLifecycle:
    """创建 → 鉴权 → 撤销 → 401 全链路"""

    def test_create_auth_revoke_full_chain(self, test_db, api_client_row, test_device):
        # ① 创建
        r = client.post(
            "/api/v1/gateway/keys",
            json={"client_id": api_client_row.client_id, "name": "k1", "expires_in": 30},
        )
        assert r.status_code == 200, r.text
        created = r.json()
        if isinstance(created, dict) and "data" in created:
            created = created["data"]
        key_id, api_key = created["key_id"], created["api_key"]
        assert created["status"] == "active"

        # ② 新 key 可通过网关鉴权
        assert _telemetry_with_key(api_key, test_device.id).status_code == 200

        # ③ 撤销
        r = client.post(f"/api/v1/gateway/keys/{key_id}/revoke")
        assert r.status_code == 200, r.text

        # ④ 旧 key 立即 401 (30s TTL 缓存必须联动失效)
        assert _telemetry_with_key(api_key, test_device.id).status_code == 401

        # DB 状态落 revoked
        db = test_db["session"]
        from app.models.api_gateway import GatewayApiKey
        db.expire_all()
        row = db.query(GatewayApiKey).filter(GatewayApiKey.key_id == key_id).first()
        assert row.status == "revoked", row.status

    def test_rotate_old_key_dead_new_key_alive(
        self, test_db, api_client_row, test_device
    ):
        r = client.post(
            "/api/v1/gateway/keys",
            json={"client_id": api_client_row.client_id, "name": "k2", "expires_in": 30},
        )
        assert r.status_code == 200, r.text
        created = r.json()
        if isinstance(created, dict) and "data" in created:
            created = created["data"]
        key_id, old_key = created["key_id"], created["api_key"]
        assert _telemetry_with_key(old_key, test_device.id).status_code == 200

        r = client.post(f"/api/v1/gateway/keys/{key_id}/rotate")
        assert r.status_code == 200, r.text
        rotated = r.json()
        if isinstance(rotated, dict) and "data" in rotated:
            rotated = rotated["data"]
        new_key = rotated["api_key"]
        assert new_key != old_key
        assert rotated["status"] == "active"

        # 旧 key 401, 新 key 200
        assert _telemetry_with_key(old_key, test_device.id).status_code == 401
        assert _telemetry_with_key(new_key, test_device.id).status_code == 200

    def test_revoke_missing_key_404(self, test_db, api_client_row):
        r = client.post("/api/v1/gateway/keys/key_nosuch/revoke")
        assert r.status_code == 404, r.text


class TestStatsDaysBounds:
    def test_days_below_min_422(self, test_db):
        assert client.get("/api/v1/gateway/stats", params={"days": 0}).status_code == 422

    def test_days_above_max_422(self, test_db):
        assert client.get("/api/v1/gateway/stats", params={"days": 91}).status_code == 422

    def test_days_in_range_200(self, test_db):
        assert client.get("/api/v1/gateway/stats", params={"days": 7}).status_code == 200


class TestOAuthAuthorizationCode:
    def _create_client_via_api(self):
        r = client.post(
            "/api/v1/gateway/clients",
            json={"name": "oauth-test-client", "scopes": ["read"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if isinstance(body, dict) and "data" in body:
            body = body["data"]
        return body

    def test_valid_code_exchanges_token(self, test_db, api_client_row):
        db = test_db["session"]
        from app.models.api_gateway import OAuthAuthorizationCode
        code_row = OAuthAuthorizationCode(
            code="oauth-code-valid-001",
            client_id=api_client_row.id,
            scopes="read",
            expires_at=dt.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
            used=False,
        )
        db.add(code_row)
        db.commit()

        r = client.post(
            "/api/v1/gateway/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": api_client_row.client_id,
                "client_secret": "secret-001",
                "code": "oauth-code-valid-001",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if isinstance(body, dict) and "data" in body:
            body = body["data"]
        assert body["access_token"]

        # code 一次性: 已用过的 code 再换 → 拒绝
        r2 = client.post(
            "/api/v1/gateway/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": api_client_row.client_id,
                "client_secret": "secret-001",
                "code": "oauth-code-valid-001",
            },
        )
        assert r2.status_code in (400, 401), r2.text

    def test_unknown_code_rejected(self, test_db, api_client_row):
        r = client.post(
            "/api/v1/gateway/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": api_client_row.client_id,
                "client_secret": "secret-001",
                "code": "not-a-real-code",
            },
        )
        assert r.status_code in (400, 401), r.text

    def test_expired_code_rejected(self, test_db, api_client_row):
        db = test_db["session"]
        from app.models.api_gateway import OAuthAuthorizationCode
        db.add(OAuthAuthorizationCode(
            code="oauth-code-expired-001",
            client_id=api_client_row.id,
            scopes="read",
            expires_at=dt.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
            used=False,
        ))
        db.commit()
        r = client.post(
            "/api/v1/gateway/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": api_client_row.client_id,
                "client_secret": "secret-001",
                "code": "oauth-code-expired-001",
            },
        )
        assert r.status_code in (400, 401), r.text
