"""契约§8 P1: C端用户登录/资料/设备token 测试 (卡 d95dafd3)."""

from types import SimpleNamespace

import jwt as pyjwt
from fastapi import HTTPException

from app.core.config import settings
from app.models.channel_config import ChannelConfig, ChannelType
from app.models.end_user import EndUser, EndUserStatus
from app.models.end_user_device_token import EndUserDeviceToken


AUTH_URL = "/api/v1/business/auth/wx-login"
ME_URL = "/api/v1/business/user/me"
PHONE_URL = "/api/v1/business/user/phone-bind"
DEVICE_URL = "/api/v1/business/devices/token"


def _body(response, status=200):
    assert response.status_code == status, response.text
    assert response.json()["code"] == 0
    return response.json()["data"]


def _end_user_token(client, code="login-code"):
    body = _body(client.post(AUTH_URL, json={"code": code}))
    return body


def test_wx_login_mock_new_and_existing_end_user(client):
    first = _end_user_token(client, code="same-code")
    second = _end_user_token(client, code="same-code")

    assert first["is_mock"] is True
    assert first["is_new"] is True
    assert first["token_type"] == "Bearer"
    assert first["expires_in"] == 43200
    assert first["user"]["user_type"] == "app"
    assert second["is_new"] is False
    assert second["user"]["end_user_id"] == first["user"]["end_user_id"]

    payload = pyjwt.decode(
        first["token"],
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        audience="end_user",
    )
    assert payload["sub"] == str(first["user"]["end_user_id"])
    assert payload["aud"] == "end_user"


def test_wx_login_real_credentials_code2session(client, monkeypatch):
    import app.api.v1.business_end_user_auth as mod

    monkeypatch.setattr(mod.settings, "WX_MP_APPID", "wx-appid", raising=False)
    monkeypatch.setattr(mod.settings, "WX_MP_SECRET", "wx-secret", raising=False)

    class FakeClient:
        calls = []

        async def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "openid": "real-openid",
                    "unionid": "real-unionid",
                    "session_key": "session-key",
                },
            )

        async def aclose(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    fake_client = FakeClient()
    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kwargs: fake_client)

    data = _end_user_token(client, code="wx-code")
    assert data["is_mock"] is False
    assert data["is_new"] is True
    assert data["user"]["end_user_id"] > 0

    url, kwargs = fake_client.calls[0]
    assert url == "https://api.weixin.qq.com/sns/jscode2session"
    assert kwargs["params"]["appid"] == "wx-appid"
    assert kwargs["params"]["secret"] == "wx-secret"
    assert kwargs["params"]["js_code"] == "wx-code"
    assert kwargs["params"]["grant_type"] == "authorization_code"


def test_end_user_profile_and_phone_bind_mock(client, monkeypatch):
    # 卡 75a0069e: SMS_DEV_MODE 默认 False, 演示绑定测试内显式 opt-in
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "SMS_DEV_MODE", True)
    monkeypatch.setattr(_settings, "SMS_DEV_CODE", "123456")
    login = _end_user_token(client)
    headers = {"Authorization": f"Bearer {login['token']}"}

    me = _body(client.get(ME_URL, headers=headers))
    assert me["end_user_id"] == login["user"]["end_user_id"]
    assert me["nickname"] == ""
    assert me["phone"] is None
    assert me["created_at"]

    updated = _body(
        client.patch(
            ME_URL,
            json={"nickname": "丁哥", "avatar_url": "https://example.com/a.png"},
            headers=headers,
        )
    )
    assert updated["nickname"] == "丁哥"
    assert updated["avatar_url"] == "https://example.com/a.png"

    bound = _body(
        client.post(
            PHONE_URL,
            json={"phone": "13800138000", "sms_code": "123456"},
            headers=headers,
        )
    )
    assert bound["phone"] == "13800138000"
    assert bound["is_mock"] is True


def test_phone_bind_sms_configured_returns_501(client):
    login = _end_user_token(client)
    session = client._sesh
    session.add(
        ChannelConfig(
            team_id=None,
            channel=ChannelType.SMS,
            config={
                "sms_access_key": "key",
                "sms_secret": "secret",
                "sign_name": "天链",
            },
            enabled=True,
        )
    )
    session.commit()

    response = client.post(
        PHONE_URL,
        json={"phone": "13800138000", "sms_code": "123456"},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert response.status_code == 501


def test_device_token_register_idempotent_and_delete(client):
    login = _end_user_token(client)
    headers = {"Authorization": f"Bearer {login['token']}"}

    _body(
        client.post(
            DEVICE_URL,
            json={
                "platform": "ios",
                "device_token": "first-token",
                "app_version": "1.0.0",
            },
            headers=headers,
        )
    )
    _body(
        client.post(
            DEVICE_URL,
            json={"platform": "ios", "device_token": "second-token"},
            headers=headers,
        )
    )

    session = client._sesh
    tokens = session.query(EndUserDeviceToken).all()
    assert len(tokens) == 1
    assert tokens[0].device_token == "second-token"
    assert tokens[0].app_version == "1.0.0"

    _body(client.request("DELETE", DEVICE_URL, json={"platform": "ios"}, headers=headers))
    assert session.query(EndUserDeviceToken).count() == 0


def test_operate_token_rejected_by_end_user_endpoints(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    token = response.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(ME_URL, headers=headers).status_code == 401
    assert client.post(DEVICE_URL, json={"platform": "ios", "device_token": "x"}, headers=headers).status_code == 401


def test_disabled_end_user_token_rejected(client):
    login = _end_user_token(client)
    session = client._sesh
    end_user = session.query(EndUser).get(login["user"]["end_user_id"])
    end_user.status = EndUserStatus.DISABLED
    session.commit()

    response = client.get(ME_URL, headers={"Authorization": f"Bearer {login['token']}"})
    assert response.status_code == 401


def test_wx_login_race_duplicate_openid_returns_existing(client):
    """并发首登竞态: 预检查漏检, INSERT 撞 wx_openid 唯一约束 (卡 1c54c2b2).

    模拟: patch Session.commit —— 本请求 commit 前用独立连接插入同 openid 行
    (并发请求先行落库), 本请求 commit 必撞 IntegrityError。
    契约§8: 回查现有用户正常返回 200, is_new=False, 非 500。

    注意 (卡67523030): wx_login 的 DB 段经 asyncio.to_thread 在线程池执行,
    _wx_login_db_sync 内部通过 db_module.SessionLocal() 创建独立 session
    (与 client._sesh 的 sessionmaker 是不同子类), 故必须 patch
    Session.commit (基类) 而非 type(client._sesh).commit 才能覆盖线程内 session。
    """
    from unittest.mock import patch

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    session = client._sesh
    orig_commit = Session.commit
    fired = {"on": True}

    def racing_commit(self):
        pending = [o for o in self.new if isinstance(o, EndUser)]
        if fired["on"] and pending:
            fired["on"] = False
            openid = pending[0].wx_openid
            conn = self.get_bind().connect()
            try:
                conn.execute(
                    text("INSERT INTO end_users (wx_openid) VALUES (:o)"),
                    {"o": openid},
                )
                conn.commit()
            finally:
                conn.close()
        return orig_commit(self)

    with patch.object(Session, "commit", racing_commit):
        resp = client.post(AUTH_URL, json={"code": "race-code"})

    assert resp.status_code == 200, resp.text
    data = _body(resp)
    assert data["is_new"] is False
    assert data["token"]
    # 同 openid 只剩并发方那一行, 本请求 INSERT 未落库
    assert session.query(EndUser).filter(EndUser.wx_openid.like("mock_%")).count() == 1


def test_device_token_race_duplicate_platform_updates_existing(client):
    """并发注册竞态: 预检查漏检, INSERT 撞 uq_end_user_device_platform (卡 1c54c2b2).

    模拟: patch Session.commit —— 本请求 commit 前用独立连接插入同
    (end_user_id, platform) 行, 本请求 commit 必撞 IntegrityError。
    语义应为更新: 200 registered, 现有行 device_token 更新为本请求的值, 非 500。

    注意 (卡67523030): 与 wx_login race test 同理, device token 注册
    仍走同步 get_db session (非 to_thread), 但 patch 基类 Session.commit
    可同时覆盖 client._sesh 与请求级 session。
    """
    from unittest.mock import patch

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    login = _end_user_token(client, code="race-device-code")
    headers = {"Authorization": f"Bearer {login['token']}"}
    session = client._sesh
    orig_commit = Session.commit
    fired = {"on": True}

    def racing_commit(self):
        pending = [o for o in self.new if isinstance(o, EndUserDeviceToken)]
        if fired["on"] and pending:
            fired["on"] = False
            d = pending[0]
            conn = self.get_bind().connect()
            try:
                conn.execute(
                    text(
                        "INSERT INTO end_user_device_tokens"
                        " (end_user_id, platform, device_token)"
                        " VALUES (:u, :p, :t)"
                    ),
                    {"u": d.end_user_id, "p": d.platform, "t": "racing-token"},
                )
                conn.commit()
            finally:
                conn.close()
        return orig_commit(self)

    with patch.object(Session, "commit", racing_commit):
        resp = client.post(
            DEVICE_URL,
            json={"platform": "android", "device_token": "winner-token"},
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    assert _body(resp) == {"registered": True}
    tokens = session.query(EndUserDeviceToken).all()
    assert len(tokens) == 1
    # 更新语义: 本请求的 token 覆盖并发方先落的行
    assert tokens[0].device_token == "winner-token"


def test_wx_login_real_credentials_error_mapped_502(client, monkeypatch):
    import app.api.v1.business_end_user_auth as mod

    monkeypatch.setattr(mod.settings, "WX_MP_APPID", "wx-appid", raising=False)
    monkeypatch.setattr(mod.settings, "WX_MP_SECRET", "wx-secret", raising=False)

    async def failed_code2session(code):
        raise HTTPException(502, "IM-B登录失败")

    monkeypatch.setattr(mod, "_code2session", failed_code2session)
    response = client.post(AUTH_URL, json={"code": "bad-code"})
    assert response.status_code == 502


def _login_headers(client):
    login = _end_user_token(client)
    return {"Authorization": f"Bearer {login['token']}"}


def test_patch_me_explicit_null_clears_fields_not_500(client):
    """显式null=清空字段(存None,回显空串),与_profile回显语义一致 (卡 a1781e04)."""
    headers = _login_headers(client)
    client.patch(ME_URL, json={"nickname": "丁哥", "avatar_url": "https://example.com/a.png"}, headers=headers)

    cleared = _body(client.patch(ME_URL, json={"nickname": None, "avatar_url": None}, headers=headers))
    assert cleared["nickname"] == ""
    assert cleared["avatar_url"] == ""


def test_patch_me_empty_string_stored_as_empty(client):
    headers = _login_headers(client)
    client.patch(ME_URL, json={"nickname": "旧昵称"}, headers=headers)

    updated = _body(client.patch(ME_URL, json={"nickname": "  ", "avatar_url": ""}, headers=headers))
    assert updated["nickname"] == ""
    assert updated["avatar_url"] == ""


def test_patch_me_normal_values_stripped(client):
    headers = _login_headers(client)
    updated = _body(
        client.patch(
            ME_URL,
            json={"nickname": "  石猴  ", "avatar_url": " https://example.com/b.png "},
            headers=headers,
        )
    )
    assert updated["nickname"] == "石猴"
    assert updated["avatar_url"] == "https://example.com/b.png"
