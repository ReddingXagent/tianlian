"""
D2 安全缺口修复测试 — 任务卡 69acc93c。

5 组零认证/弱认证写端点补防护的回归:
1. HIGH  pod_routes/cross_pod: X-Pod-Secret 共享密钥
        (无头/错头/未配置→403, 合法→200) + pod_id 格式校验 (非法→400)
2. MED   ssl_certificates: 写端点 admin only (admin→200, 非 admin→403, anon→401)
3.       scan: qrcode + quick-repair/device 全部收紧需认证 (anon→401, 带 token→200);
        quick-repair 调用补审计日志 (追溯报修来源)
4.       health: POST /devices/health/refresh admin only (anon→401, 非 admin→403, admin→200)

风格参考 tests/test_alert_webhook_auth.py (monkeypatch settings + 头控制)
与 tests/test_ssl_certificates_authorization.py (三档角色)。
"""
import logging

import pytest

from app.core.config import settings

POD_SECRET = "test-pod-comm-secret-d2-69acc93c"


def _login_as(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


@pytest.fixture
def viewer_token(client):
    """seed 一个 VIEWER 用户并登录, 供非 admin 403 测试。"""
    import bcrypt
    from app.models.user import User, UserRole
    s = client._sesh
    if not s.query(User).filter(User.username == "d2viewer").first():
        s.add(User(
            username="d2viewer",
            password_hash=bcrypt.hashpw(b"d2view123", bcrypt.gensalt()).decode(),
            role=UserRole.VIEWER,
            status="active",
        ))
        s.commit()
    return _login_as(client, "d2viewer", "d2view123")


# ========== 1. Pod 间通信共享密钥 (HIGH) ==========

class TestPodSharedSecret:
    """/pod register/heartbeat/routes/stations + /cross query/internal/query/routes
    在 enforce_auth 白名单内 (全局认证放行), 必须自证 X-Pod-Secret 共享密钥。"""

    @pytest.fixture(autouse=True)
    def _set_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", POD_SECRET)

    # --- pod/register ---
    def test_register_no_secret_header_403(self, client):
        r = client.post("/api/v1/pod/register", json={
            "pod_id": "pod-99", "region_id": "r", "endpoint": "http://1.1.1.1", "version": "3"})
        assert r.status_code == 403

    def test_register_wrong_secret_403(self, client):
        r = client.post("/api/v1/pod/register",
            json={"pod_id": "pod-99", "region_id": "r", "endpoint": "http://1.1.1.1"},
            headers={"X-Pod-Secret": "wrong"})
        assert r.status_code == 403

    def test_register_valid_secret_200(self, client):
        r = client.post("/api/v1/pod/register",
            json={"pod_id": "pod-99", "region_id": "r", "endpoint": "http://1.1.1.1"},
            headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200
        # 单 Pod 模式不支持注册, 但密钥通过后正常返回 (success=False)
        assert r.json()["success"] is False

    def test_register_invalid_pod_id_400(self, client):
        # 合法密钥头通过后, 端点内 validate_pod_id 拦截非法 pod_id (防 Redis key 注入)
        r = client.post("/api/v1/pod/register",
            json={"pod_id": "../../etc/passwd", "region_id": "r", "endpoint": "http://1.1.1.1"},
            headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 400

    # --- pod/heartbeat ---
    def test_heartbeat_no_secret_403(self, client):
        r = client.post("/api/v1/pod/heartbeat", json={"pod_id": "pod-01"})
        assert r.status_code == 403

    def test_heartbeat_valid_secret_200(self, client):
        r = client.post("/api/v1/pod/heartbeat",
            json={"pod_id": "pod-01"}, headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    def test_heartbeat_invalid_pod_id_400(self, client):
        r = client.post("/api/v1/pod/heartbeat",
            json={"pod_id": "bad pod id!"}, headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 400

    # --- pod/routes & stations (GET 读端点同样要求密钥) ---
    def test_routes_no_secret_403(self, client):
        assert client.get("/api/v1/pod/routes").status_code == 403

    def test_routes_valid_secret_200(self, client):
        r = client.get("/api/v1/pod/routes", headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    def test_stations_no_secret_403(self, client):
        assert client.get("/api/v1/pod/stations").status_code == 403

    def test_stations_valid_secret_200(self, client):
        r = client.get("/api/v1/pod/stations", headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    # --- pod/health (GET 读端点同样要求密钥, 卡508ef378) ---
    def test_health_no_secret_403(self, client):
        assert client.get("/api/v1/pod/health").status_code == 403

    def test_health_wrong_secret_403(self, client):
        r = client.get("/api/v1/pod/health", headers={"X-Pod-Secret": "wrong"})
        assert r.status_code == 403

    def test_health_valid_secret_200(self, client):
        r = client.get("/api/v1/pod/health", headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    # --- pod/list & info (GET 读端点同样要求密钥, 卡020e44db) ---
    def test_list_no_secret_403(self, client):
        assert client.get("/api/v1/pod/list").status_code == 403

    def test_list_valid_secret_200(self, client):
        r = client.get("/api/v1/pod/list", headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    def test_info_no_secret_403(self, client):
        assert client.get("/api/v1/pod/info/pod-01").status_code == 403

    def test_info_valid_secret_200(self, client):
        # 合法密钥从 list 取真实 pod_id, 再查 info
        pod_id = client.get("/api/v1/pod/list", headers={"X-Pod-Secret": POD_SECRET}).json()["pods"][0]["pod_id"]
        r = client.get(f"/api/v1/pod/info/{pod_id}", headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    # --- cross/* ---
    def test_cross_query_no_secret_403(self, client):
        r = client.post("/api/v1/cross/query", json={"station_ids": [1]})
        assert r.status_code == 403

    def test_cross_query_valid_secret_200(self, client):
        r = client.post("/api/v1/cross/query",
            json={"station_ids": [999999]}, headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200
        assert r.json()["results"] == []

    def test_cross_internal_query_no_secret_403(self, client):
        r = client.post("/api/v1/cross/internal/query", json={"station_ids": [1]})
        assert r.status_code == 403

    def test_cross_internal_query_valid_secret_200(self, client):
        r = client.post("/api/v1/cross/internal/query",
            json={"station_ids": [999999]}, headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    def test_cross_routes_no_secret_403(self, client):
        r = client.post("/api/v1/cross/routes", json={"station_ids": [1]})
        assert r.status_code == 403

    def test_cross_routes_valid_secret_200(self, client):
        r = client.post("/api/v1/cross/routes",
            json={"station_ids": [1]}, headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 200

    # --- secret 未配置: 即便带正确头也 403 (强制配置, 不裸奔) ---
    def test_secret_not_configured_rejects_all(self, client, monkeypatch):
        monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", None)
        r = client.post("/api/v1/pod/register",
            json={"pod_id": "pod-99", "region_id": "r", "endpoint": "http://1.1.1.1"},
            headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 403

    def test_empty_secret_rejects_all(self, client, monkeypatch):
        monkeypatch.setattr(settings, "POD_COMM_SHARED_SECRET", "  ")
        r = client.post("/api/v1/cross/query",
            json={"station_ids": [1]}, headers={"X-Pod-Secret": POD_SECRET})
        assert r.status_code == 403


# ========== 2. SSL 证书写端点 admin only (MEDIUM, 回归) ==========

class TestSSLCertAuthRegression:
    """ssl 写端点 require_platform_admin 收紧回归 (卡 55f8d345 已治理, 此处防回退)。"""

    def test_admin_write_200(self, client):
        from unittest.mock import patch
        with patch("app.api.v1.ssl_certificates._async_request_cert"):
            r = client.post("/api/v1/ssl/certificates",
                json={"domain": "d2ok.example.com", "email": "admin@d2.com"})
        assert r.status_code == 200

    def test_viewer_write_403(self, client, viewer_token):
        r = client.post("/api/v1/ssl/certificates",
            json={"domain": "d2evil.example.com", "email": "admin@d2.com"},
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 403

    def test_anon_write_401(self, anon_client):
        r = anon_client.post("/api/v1/ssl/certificates",
            json={"domain": "d2anon.example.com", "email": "admin@d2.com"})
        assert r.status_code == 401


# ========== 3. scan: qrcode + quick-repair/device 全部收紧需认证 + 审计 ==========

class TestScanAuthAndAudit:
    """扫码报修(device/quick-repair) 与 qrcode 全部收紧需认证 (卡 b1b04cda);
    quick-repair 调用补审计日志 (追溯报修来源)。"""

    def test_qrcode_delete_anon_401(self, anon_client):
        r = anon_client.delete("/api/v1/scan/qrcode/1")
        assert r.status_code == 401

    def test_qrcode_delete_with_token_200(self, client, seed_devices):
        dev_id = seed_devices["chg001"].id
        g = client.post("/api/v1/scan/qrcode/generate", json={"device_id": dev_id})
        assert g.status_code == 200
        r = client.delete(f"/api/v1/scan/qrcode/{dev_id}")
        assert r.status_code == 200

    # --- qrcode 管理三端点 (generate/get/list) 收紧需认证 (卡020e44db) ---
    def test_qrcode_generate_anon_401(self, anon_client):
        r = anon_client.post("/api/v1/scan/qrcode/generate", json={"device_id": 1})
        assert r.status_code == 401

    def test_qrcode_get_anon_401(self, anon_client):
        r = anon_client.get("/api/v1/scan/qrcode/1")
        assert r.status_code == 401

    def test_qrcode_list_anon_401(self, anon_client):
        r = anon_client.get("/api/v1/scan/qrcodes")
        assert r.status_code == 401

    def test_qrcode_generate_with_token_200(self, client, seed_devices):
        dev_id = seed_devices["chg001"].id
        r = client.post("/api/v1/scan/qrcode/generate", json={"device_id": dev_id})
        assert r.status_code == 200

    def test_qrcode_get_with_token_200(self, client, seed_devices):
        dev_id = seed_devices["chg001"].id
        client.post("/api/v1/scan/qrcode/generate", json={"device_id": dev_id})
        r = client.get(f"/api/v1/scan/qrcode/{dev_id}")
        assert r.status_code == 200

    def test_qrcode_list_with_token_200(self, client):
        r = client.get("/api/v1/scan/qrcodes")
        assert r.status_code == 200

    def test_quick_repair_anon_401(self, anon_client):
        """quick-repair 收紧需认证 (卡 b1b04cda), 匿名不再可达 → 401。"""
        r = anon_client.post("/api/v1/scan/quick-repair",
            json={"device_id": 999999, "fault_desc": "x"})
        assert r.status_code == 401

    def test_scan_device_anon_401(self, anon_client):
        """scan/device 收紧需认证 (卡 b1b04cda), 匿名 → 401。"""
        r = anon_client.post("/api/v1/scan/device", json={"qr_code": "NONEXIST"})
        assert r.status_code == 401

    def test_quick_repair_emits_audit_log(self, client, seed_devices, caplog):
        """quick_repair 调用写审计日志 (追溯报修来源, 匿名场景的可观测性补偿)。"""
        caplog.set_level(logging.INFO, logger="app.api.v1.scan")
        client.post("/api/v1/scan/quick-repair",
            json={"device_id": seed_devices["inv001"].id, "fault_desc": "审计测试"})
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "报修" in msgs or "quick_repair" in msgs


# ========== 4. health refresh admin only ==========

class TestHealthRefreshAdmin:
    """POST /devices/health/refresh 移出公开白名单 + admin only。"""

    def test_refresh_anon_401(self, anon_client):
        r = anon_client.post("/api/v1/devices/health/refresh")
        assert r.status_code == 401

    def test_refresh_viewer_403(self, client, viewer_token):
        r = client.post("/api/v1/devices/health/refresh",
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 403

    def test_refresh_admin_200(self, client):
        r = client.post("/api/v1/devices/health/refresh")
        assert r.status_code == 200


# ========== 5. 登录500异常分支脱敏 (D1卫生, 卡0f29184a) ==========

class TestLoginUnexpectedExceptionSanitized:
    """auth.py 登录 unexpected exception 分支(358-362):
    500 detail 脱敏(不回传异常类型/消息), 完整异常仅留服务端日志。
    回归保护 5267c9ce2 的脱敏修复。"""

    @pytest.fixture
    def seeded_user(self, client):
        import bcrypt
        from app.models.user import User, UserRole
        s = client._sesh
        if not s.query(User).filter(User.username == "d1erruser").first():
            s.add(User(
                username="d1erruser",
                password_hash=bcrypt.hashpw(b"d1err123", bcrypt.gensalt()).decode(),
                role=UserRole.VIEWER,
                status="active",
            ))
            s.commit()

    @staticmethod
    def _boom(plain, hashed):
        raise RuntimeError("internal db down")

    def test_login_500_detail_sanitized(self, client, seeded_user, monkeypatch):
        monkeypatch.setattr("app.api.v1.auth.verify_password", self._boom)
        r = client.post("/api/v1/auth/login",
            data={"username": "d1erruser", "password": "***"})
        assert r.status_code == 500
        # 响应体不得泄露内部异常类型/消息
        assert "RuntimeError" not in r.text
        assert "internal db down" not in r.text
        detail = r.json().get("detail", "")
        assert detail == "登录内部错误，请稍后重试"

    def test_login_500_server_log_keeps_full_exception(self, client, seeded_user, monkeypatch, caplog):
        monkeypatch.setattr("app.api.v1.auth.verify_password", self._boom)
        caplog.set_level(logging.ERROR, logger="app.api.v1.auth")
        client.post("/api/v1/auth/login",
            data={"username": "d1erruser", "password": "***"})
        msgs = " ".join(rec.getMessage() for rec in caplog.records)
        # 服务端日志仍记录完整异常(排障可观测性不丢)
        assert "internal db down" in msgs
