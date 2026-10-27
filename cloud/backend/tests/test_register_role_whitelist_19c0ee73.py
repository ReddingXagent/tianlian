"""
卡 19c0ee73 — /auth/register 匿名自注册角色白名单回归测试

漏洞: register 仅校验 role 是合法枚举值, super_admin/admin 均合法 → 匿名注册即超管。
修复: 白名单仅允许 viewer/technician, 其余 422; 不传 role 落默认 technician。
"""
import uuid

from fastapi.testclient import TestClient


def _payload(**overrides):
    payload = {
        "username": f"reg19c0ee73_{uuid.uuid4().hex[:8]}",
        "password": "test123456",
        "real_name": "白名单回归",
    }
    payload.update(overrides)
    return payload


class TestRegisterRoleWhitelist19c0ee73:
    """匿名注册角色白名单 (P0)"""

    def test_register_super_admin_rejected(self, client: TestClient, seed_users):
        """注册 role=super_admin 必须被 422 拒绝"""
        response = client.post("/api/v1/auth/register", json=_payload(role="super_admin"))
        assert response.status_code == 422, (
            f"super_admin 自注册未被拦截: {response.status_code} {response.text}"
        )

    def test_register_admin_rejected(self, client: TestClient, seed_users):
        """注册 role=admin 必须被 422 拒绝"""
        response = client.post("/api/v1/auth/register", json=_payload(role="admin"))
        assert response.status_code == 422, (
            f"admin 自注册未被拦截: {response.status_code} {response.text}"
        )

    def test_register_other_backoffice_roles_rejected(self, client: TestClient, seed_users):
        """其余后台角色 (dispatcher/engineer/auditor 等) 一律 422"""
        for role in ("dispatcher", "station_master", "engineer", "operator", "auditor"):
            response = client.post(
                "/api/v1/auth/register", json=_payload(role=role)
            )
            assert response.status_code == 422, (
                f"role={role} 未被拦截: {response.status_code}"
            )

    def test_register_viewer_success(self, client: TestClient, seed_users):
        """最低权限角色 viewer 注册成功"""
        response = client.post("/api/v1/auth/register", json=_payload(role="viewer"))
        assert response.status_code == 200, f"viewer 注册失败: {response.text}"
        assert response.json()["data"]["role"] == "viewer"

    def test_register_technician_success(self, client: TestClient, seed_users):
        """technician 注册成功"""
        response = client.post(
            "/api/v1/auth/register", json=_payload(role="technician")
        )
        assert response.status_code == 200, f"technician 注册失败: {response.text}"
        assert response.json()["data"]["role"] == "technician"

    def test_register_default_role_is_safe(self, client: TestClient, seed_users):
        """不传 role → 落默认安全角色 technician"""
        response = client.post("/api/v1/auth/register", json=_payload())
        assert response.status_code == 200, f"默认注册失败: {response.text}"
        assert response.json()["data"]["role"] == "technician"
