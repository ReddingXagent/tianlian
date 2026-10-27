"""
API 密钥管理 API 测试
覆盖: list, create, get, update, delete, usage-stats, rotate
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


class TestApiKeyAPI:

    def test_list_requires_auth(self):
        client.headers.pop("Authorization", None)  # 模块级 client 被 autouse 注入 admin token，清除以测真匿名拒绝
        assert client.get("/api/v1/api-keys").status_code == 401

    def test_list_empty(self, auth_token):
        resp = client.get("/api/v1/api-keys", headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_create_api_key(self, auth_token):
        resp = client.post("/api/v1/api-keys", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "name": "测试密钥",
            "description": "自动化测试",
            "scopes": ["read:devices"],
            "rate_limit": 1000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or "api_key" in data

    def test_get_api_key_detail(self, auth_token):
        # create first
        create = client.post("/api/v1/api-keys", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"name": "detail-key", "scopes": ["read:stations"], "rate_limit": 500})
        assert create.status_code == 200
        key_id = create.json().get("data", {}).get("id") or create.json().get("id", 1)

        resp = client.get(f"/api/v1/api-keys/{key_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200

    def test_update_api_key(self, auth_token):
        create = client.post("/api/v1/api-keys", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"name": "update-key", "scopes": ["write:devices"], "rate_limit": 1000})
        assert create.status_code == 200
        key_id = create.json().get("data", {}).get("id") or create.json().get("id", 1)

        resp = client.put(f"/api/v1/api-keys/{key_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"name": "已更新密钥"})
        assert resp.status_code == 200

    def test_delete_api_key(self, auth_token):
        create = client.post("/api/v1/api-keys", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"name": "delete-key", "scopes": ["read"], "rate_limit": 100})
        assert create.status_code == 200
        key_id = create.json().get("data", {}).get("id") or create.json().get("id", 1)

        resp = client.delete(f"/api/v1/api-keys/{key_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200

    def test_usage_stats(self, auth_token):
        resp = client.get("/api/v1/api-keys/usage-stats", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200

    def test_rotate_api_key(self, auth_token):
        create = client.post("/api/v1/api-keys", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"name": "rotate-key", "scopes": ["read"], "rate_limit": 100})
        assert create.status_code == 200
        key_id = create.json().get("data", {}).get("id") or create.json().get("id", 1)

        resp = client.post(f"/api/v1/api-keys/{key_id}/rotate", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200
