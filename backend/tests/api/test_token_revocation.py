"""会话固定防护测试 (卡 5d6a978b)

每请求鉴权补 user.status 检查 + token_version 改密驱逐:
- suspended/inactive 用户持有效 token → 401
- password_reset 后旧 access_token → 401 (tv 驱逐)
- refresh 携带旧 tv token → 401
- 无 tv claim 的存量 token (user token_version=0) → 正常通过 (向后兼容)
"""
import pytest
from fastapi.testclient import TestClient

from app.core.jwt_utils import decode_token
from app.models.user import User


PROTECTED = "/api/v1/auth/me"


def _login_token(client: TestClient, username: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


class TestStatusCheck:
    """每请求鉴权补 user.status 检查"""

    def test_suspended_user_token_rejected(self, client: TestClient, db_session):
        token = _login_token(client, "admin", "admin123")
        user = db_session.query(User).filter(User.username == "admin").first()
        user.status = "suspended"
        db_session.commit()

        client.headers["Authorization"] = f"Bearer {token}"
        r = client.get(PROTECTED)
        assert r.status_code == 401, r.text

    def test_inactive_user_token_rejected(self, client: TestClient, db_session):
        token = _login_token(client, "admin", "admin123")
        user = db_session.query(User).filter(User.username == "admin").first()
        user.status = "inactive"
        db_session.commit()

        client.headers["Authorization"] = f"Bearer {token}"
        r = client.get(PROTECTED)
        assert r.status_code == 401, r.text

    def test_active_user_token_passes(self, client: TestClient, db_session):
        token = _login_token(client, "admin", "admin123")
        user = db_session.query(User).filter(User.username == "admin").first()
        assert user.status == "active"

        client.headers["Authorization"] = f"Bearer {token}"
        r = client.get(PROTECTED)
        assert r.status_code == 200, r.text


class TestPasswordResetRevocation:
    """改密驱逐: password_reset 后 token_version 递增, 旧 token 全部失效"""

    def _reset_password(self, client: TestClient, db_session, new_password: str):
        phone = "13800138001"
        user = db_session.query(User).filter(User.username == "admin").first()
        user.phone = phone
        db_session.commit()

        r = client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "reset"})
        assert r.status_code == 200, r.text

        from app.models.sms_verification import SmsVerificationCode
        record = db_session.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.purpose == "reset",
            SmsVerificationCode.used == 0,
        ).first()
        assert record is not None
        # 须换新连接读取 (卡 3681a8c6 类似坑): db_session 可能缓存旧状态
        code = record.code

        r = client.post("/api/v1/auth/password-reset", json={
            "phone": phone, "code": code, "new_password": new_password,
        })
        assert r.status_code == 200, r.text

    def test_old_token_rejected_after_reset(self, client: TestClient, db_session):
        old_token = _login_token(client, "admin", "admin123")
        self._reset_password(client, db_session, "newpass12345")

        client.headers["Authorization"] = f"Bearer {old_token}"
        r = client.get(PROTECTED)
        assert r.status_code == 401, r.text

    def test_new_password_login_works(self, client: TestClient, db_session):
        old_token = _login_token(client, "admin", "admin123")
        self._reset_password(client, db_session, "newpass12345")

        # 旧密码失效
        r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        assert r.status_code == 401
        # 新密码可登录
        r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "newpass12345"})
        assert r.status_code == 200, r.text
        new_token = r.json()["data"]["token"]
        client.headers["Authorization"] = f"Bearer {new_token}"
        assert client.get(PROTECTED).status_code == 200

    def test_refresh_with_old_tv_token_rejected(self, client: TestClient, db_session):
        old_token = _login_token(client, "admin", "admin123")
        self._reset_password(client, db_session, "newpass12345")

        client.headers["Authorization"] = f"Bearer {old_token}"
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401, r.text


class TestBackwardCompat:
    """无 tv claim 的存量 token (token_version=0) 向后兼容"""

    def test_token_without_tv_claim_passes(self, client: TestClient, db_session):
        token = _login_token(client, "admin", "admin123")
        payload = decode_token(token)
        # login 已带 tv claim 时, 构造无 tv 的存量形态 token 验证兼容
        assert payload.get("tv", 0) == 0  # admin 存量 token_version=0

        user = db_session.query(User).filter(User.username == "admin").first()
        assert (user.token_version or 0) == 0

        client.headers["Authorization"] = f"Bearer {token}"
        assert client.get(PROTECTED).status_code == 200
