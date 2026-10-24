"""POST /auth/refresh 身份继承修复回归 (卡 a65f8b2c)。

原缺陷: 端点只经 oauth2_scheme 提取不验证旧 token, 且新 token 硬编码
{"sub":"user","user_id":1} — 无效 token 也能换取 token, 且任何有效请求者
都会被换成 user_id=1 的身份。修复后: decode_token 验证旧 token(无效 401),
新 token 按 user_id 反查 DB 取新鲜角色权限(防角色变更后 refresh 带旧权限)。
"""
import pytest
from fastapi.testclient import TestClient

from app.core.jwt_utils import decode_token
from tests.conftest import _get_token

REFRESH_URL = "/api/v1/auth/refresh"


class TestRefreshTokenValidation:
    """缺陷1: 旧 token 必须经验证, 无效/过期一律 401。"""

    def test_invalid_token_rejected(self, client: TestClient, seed_users):
        r = client.post(REFRESH_URL, headers={"Authorization": "Bearer not-a-jwt"})
        assert r.status_code == 401

    def test_garbage_signature_rejected(self, client: TestClient, seed_users):
        import jwt as pyjwt
        from app.core.jwt_utils import get_active_secret_key
        from app.core.config import settings
        forged = pyjwt.encode(
            {"sub": "admin", "user_id": 1},
            get_active_secret_key() + "tampered",
            algorithm=settings.ALGORITHM,
        )
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 401

    def test_expired_token_rejected(self, client: TestClient, seed_users):
        from datetime import datetime, timedelta, timezone
        import jwt as pyjwt
        from app.core.jwt_utils import get_active_secret_key
        from app.core.config import settings
        expired = pyjwt.encode(
            {
                "sub": "admin",
                "user_id": 1,
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            get_active_secret_key(),
            algorithm=settings.ALGORITHM,
        )
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_valid_token_accepted(self, client: TestClient, seed_users):
        token = _get_token(client, "admin", "admin123")
        assert token
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["access_token"]


class TestRefreshIdentityInheritance:
    """缺陷2: 新 token 必须继承原 token 身份, 不得硬编码 user_id=1。"""

    def test_identity_inherited(self, client: TestClient, seed_users):
        token = _get_token(client, "viewer1", "view123")
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        new_token = r.json()["data"]["access_token"]
        old_payload = decode_token(token)
        new_payload = decode_token(new_token)
        assert new_payload["sub"] == old_payload["sub"] == "viewer1"
        assert new_payload["user_id"] == old_payload["user_id"]

    def test_no_hardcoded_user_id_1(self, client: TestClient, seed_users):
        """请求者 id≠1 时, 新 token 不得是 user_id=1。"""
        # admin 是首建用户通常 id=1, 换 engineer1 (id 必然 >1) 验证
        token = _get_token(client, "engineer1", "eng123")
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        payload = decode_token(r.json()["data"]["access_token"])
        assert payload["sub"] == "engineer1"
        assert payload["user_id"] != 1

    def test_refreshed_token_passes_get_current_user(self, client: TestClient, seed_users):
        token = _get_token(client, "viewer1", "view123")
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        new_token = r.json()["data"]["access_token"]
        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}
        )
        assert me.status_code == 200, me.text
        body = me.json().get("data", me.json())
        assert body.get("username") == "viewer1"

    def test_claims_role_permissions_inherited(self, client: TestClient, seed_users):
        """新 token 携带 role/permissions claims (get_current_user 链路依赖)。"""
        token = _get_token(client, "viewer1", "view123")
        r = client.post(REFRESH_URL, headers={"Authorization": f"Bearer {token}"})
        payload = decode_token(r.json()["data"]["access_token"])
        assert payload.get("role")
        assert "permissions" in payload
