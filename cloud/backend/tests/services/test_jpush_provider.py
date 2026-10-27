"""JPush 极光推送适配器 (卡 7f601f7f).

REST v3 https://api.jpush.cn/v3/push, Basic auth = AppKey:MasterSecret,
audience registration_id 数组定向; 失败重试 1 次; errcode 1011 → 失效 token
信号供上层清理。未配置凭证 → 不发请求降级 (与 base.py no-op 语义一致)。

测试缝: FakeClient (注入式 httpx 替身, 与 test_wx_subscribe_msg 同源) +
monkeypatch settings / time.sleep — 绝不发真实请求, 凭证为测试占位串。
"""

import asyncio
from unittest.mock import MagicMock


JPUSH_URL = "https://api.jpush.cn/v3/push"

_real_sleep = asyncio.sleep


def _sleep_recorder(sleeps):
    """记录 backoff 参数且真睡 0s 的 asyncio.sleep 替身 (避免自引用递归)。"""
    async def _sleep(s):
        sleeps.append(s)
        return await _real_sleep(0)
    return _sleep


# ═══════════════════════════════════════════════════════════════════════════════
# FakeClient — 注入式 httpx 替身 (异步 post, 与 wx_subscribe_msg 测试同源)
# ═══════════════════════════════════════════════════════════════════════════════

class FakeClient:
    """按序返回 responses 列表的 httpx 替身; exc 抛网络异常。

    requests 记录全部请求 (url/json/headers/auth)。
    """

    def __init__(self, responses=None, exc=None):
        self.requests = []
        self._responses = list(responses or [])
        self._exc = exc

    async def post(self, url, json=None, headers=None, auth=None, timeout=None):
        self.requests.append(
            {"url": url, "json": json, "headers": headers, "auth": auth}
        )
        if self._exc is not None:
            raise self._exc
        spec = self._responses.pop(0) if self._responses else {}
        r = MagicMock()
        r.status_code = spec.get("status_code", 200)
        r.json.return_value = spec.get("payload", {})
        return r


def _resp(status_code=200, payload=None):
    return {"status_code": status_code, "payload": payload or {}}


def _ok():
    return _resp(200, {"sendno": "1"})


def _configured_settings(**over):
    from types import SimpleNamespace

    base = dict(
        JIGUANG_APP_KEY="test-app-key",
        JIGUANG_MASTER_SECRET="test-master-secret",
        JIGUANG_ENABLED=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _make_provider(client, monkeypatch, settings_over=None):
    """构造 JPushProvider 并注入 FakeClient + settings 替身。"""
    from app.services.push import jpush_provider as mod

    over = settings_over or {}
    if over is not None:
        monkeypatch.setattr(mod, "settings", _configured_settings(**over))
    provider = mod.JPushProvider()
    monkeypatch.setattr(provider, "_client", lambda: client)
    return provider, mod


async def _async_noop(_=None):
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 发送成功
# ═══════════════════════════════════════════════════════════════════════════════

class TestJPushSendSuccess:
    def test_send_success_builds_v3_payload(self, monkeypatch):
        """成功: 200 → send 返回 True, payload 用 registration_id 定向带 extras。"""
        client = FakeClient(responses=[_ok()])
        provider, mod = _make_provider(client, monkeypatch)
        monkeypatch.setattr(mod.asyncio, "sleep", _async_noop)

        ok = provider.send(
            42, "发票开具通知", "您的开票申请已处理",
            {"invoice_id": 301, "device_token": "reg-id-1",
             "platform": "ios", "status": "issued", "amount": 6600},
        )

        assert ok is True
        assert len(client.requests) == 1
        req = client.requests[0]
        assert req["url"] == JPUSH_URL
        # Basic auth = AppKey:MasterSecret
        assert req["auth"] == ("test-app-key", "test-master-secret")
        body = req["json"]
        assert body["audience"]["registration_id"] == ["reg-id-1"]
        assert body["notification"]["android"]["title"] == "发票开具通知"
        assert body["notification"]["android"]["alert"] == "您的开票申请已处理"
        assert body["notification"]["ios"]["alert"] == "您的开票申请已处理"
        for plat in ("android", "ios"):
            assert body["notification"][plat]["extras"] == {
                "invoice_id": 301, "status": "issued",
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 重试与失败分类
# ═══════════════════════════════════════════════════════════════════════════════

class TestJPushRetryAndFailure:
    def test_5xx_retries_once_then_success(self, monkeypatch):
        """5xx → 重试 1 次, 第二次成功 → True, 共 2 个请求。"""
        client = FakeClient(responses=[_resp(500), _ok()])
        provider, mod = _make_provider(client, monkeypatch)
        sleeps = []
        monkeypatch.setattr(mod.asyncio, "sleep", _sleep_recorder(sleeps))

        ok = provider.send(
            42, "t", "b", {"invoice_id": 1, "device_token": "r1"},
        )

        assert ok is True
        assert len(client.requests) == 2
        assert sleeps == [mod.DEFAULT_BACKOFF]

    def test_all_attempts_fail_returns_false(self, monkeypatch):
        """两次都 5xx → False (失败不抛, best-effort)。"""
        client = FakeClient(responses=[_resp(500), _resp(503)])
        provider, mod = _make_provider(client, monkeypatch)
        monkeypatch.setattr(mod.asyncio, "sleep", _async_noop)

        ok = provider.send(
            42, "t", "b", {"invoice_id": 1, "device_token": "r1"},
        )

        assert ok is False
        assert len(client.requests) == 2

    def test_4xx_no_retry(self, monkeypatch):
        """4xx (非 1011) 不重试 → 立即 False, 仅 1 个请求。"""
        client = FakeClient(responses=[_resp(400, {"error": {"code": 1003}})])
        provider, mod = _make_provider(client, monkeypatch)
        monkeypatch.setattr(mod.asyncio, "sleep", _async_noop)

        ok = provider.send(
            42, "t", "b", {"invoice_id": 1, "device_token": "r1"},
        )

        assert ok is False
        assert len(client.requests) == 1

    def test_network_exception_retries_then_false(self, monkeypatch):
        """网络异常同样重试 1 次, 耗尽 → False。"""
        client = FakeClient(exc=RuntimeError("network down"))
        provider, mod = _make_provider(client, monkeypatch)
        monkeypatch.setattr(mod.asyncio, "sleep", _async_noop)

        ok = provider.send(
            42, "t", "b", {"invoice_id": 1, "device_token": "r1"},
        )

        assert ok is False
        assert len(client.requests) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# errcode 1011 → 失效 token 清理信号
# ═══════════════════════════════════════════════════════════════════════════════

class TestJPushInvalidToken:
    def test_errcode_1011_records_invalid_token(self, monkeypatch):
        """errcode 1011 (invalid registration_id) → 记入失效列表供 drain。"""
        client = FakeClient(responses=[_resp(200, {"errcode": 1011})])
        provider, mod = _make_provider(client, monkeypatch)
        monkeypatch.setattr(mod.asyncio, "sleep", _async_noop)

        ok = provider.send(
            42, "t", "b", {"invoice_id": 1, "device_token": "dead-reg"},
        )

        assert ok is False
        assert provider.drain_invalid_tokens() == ["dead-reg"]
        # drain 一次性消费
        assert provider.drain_invalid_tokens() == []


# ═══════════════════════════════════════════════════════════════════════════════
# 未配置降级 (no-op)
# ═══════════════════════════════════════════════════════════════════════════════

class TestJPushNotConfigured:
    def test_no_credentials_skips_http_and_returns_true(self, monkeypatch):
        """凭证缺失 → 不发请求, 日志降级, 返回 True (与 base no-op 语义一致)。"""
        from types import SimpleNamespace

        from app.services.push import jpush_provider as mod

        monkeypatch.setattr(
            mod, "settings",
            SimpleNamespace(
                JIGUANG_APP_KEY=None, JIGUANG_MASTER_SECRET=None,
                JIGUANG_ENABLED=True,
            ),
        )
        client = FakeClient()
        provider = mod.JPushProvider()
        monkeypatch.setattr(provider, "_client", lambda: client)

        ok = provider.send(42, "t", "b", {"invoice_id": 1, "device_token": "r"})

        assert ok is True
        assert client.requests == []

    def test_disabled_flag_skips_http(self, monkeypatch):
        """JIGUANG_ENABLED=False → 同样 no-op 降级。"""
        from types import SimpleNamespace

        from app.services.push import jpush_provider as mod

        monkeypatch.setattr(
            mod, "settings",
            SimpleNamespace(
                JIGUANG_APP_KEY="k", JIGUANG_MASTER_SECRET="s",
                JIGUANG_ENABLED=False,
            ),
        )
        client = FakeClient()
        provider = mod.JPushProvider()
        monkeypatch.setattr(provider, "_client", lambda: client)

        assert provider.send(42, "t", "b", {"invoice_id": 1}) is True
        assert client.requests == []


# ═══════════════════════════════════════════════════════════════════════════════
# 注册表: create_provider / get_push_provider 接线
# ═══════════════════════════════════════════════════════════════════════════════

class TestProviderRegistry:
    def test_create_provider_returns_log_when_unconfigured(self, monkeypatch):
        """未配置凭证 → LogPushProvider (默认 no-op)。"""
        from types import SimpleNamespace

        import app.services.push as push_module
        from app.services.push.log_provider import LogPushProvider

        monkeypatch.setattr(
            push_module, "settings",
            SimpleNamespace(
                JIGUANG_APP_KEY=None, JIGUANG_MASTER_SECRET=None,
                JIGUANG_ENABLED=False,
            ),
        )
        provider = push_module.create_provider()
        assert isinstance(provider, LogPushProvider)

    def test_create_provider_returns_jpush_when_configured(self, monkeypatch):
        """凭证齐 + ENABLED → JPushProvider。"""
        from types import SimpleNamespace

        import app.services.push as push_module
        from app.services.push.jpush_provider import JPushProvider

        monkeypatch.setattr(
            push_module, "settings",
            SimpleNamespace(
                JIGUANG_APP_KEY="k", JIGUANG_MASTER_SECRET="s",
                JIGUANG_ENABLED=True,
            ),
        )
        provider = push_module.create_provider()
        assert isinstance(provider, JPushProvider)

    def test_get_push_provider_lazy_registry(self, monkeypatch):
        """get_push_provider 无注入时返回默认实现 (不抛)。"""
        from app.services.push.base import PushProvider

        import app.services.push as push_module

        assert isinstance(push_module.get_push_provider(), PushProvider)


# ═══════════════════════════════════════════════════════════════════════════════
# 配置项: 从环境读, 无硬编码
# ═══════════════════════════════════════════════════════════════════════════════

class TestJPushConfig:
    def test_settings_declare_jiguang_fields_default_off(self):
        """Settings 声明三项 JIGUANG 配置, 默认 None/False (env 可覆盖)。"""
        from app.core.config import Settings

        fields = Settings.model_fields
        assert fields["JIGUANG_APP_KEY"].default is None
        assert fields["JIGUANG_MASTER_SECRET"].default is None
        assert fields["JIGUANG_ENABLED"].default is False


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_device_targets: DISABLED 用户过滤 (卡 7f601f7f INFO 顺带修复)
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveTargetsFiltersDisabled:
    def test_disabled_user_tokens_not_resolved(self, db_session):
        from app.models.end_user import EndUser, EndUserStatus, EndUserType
        from app.models.end_user_device_token import EndUserDeviceToken
        from app.services.invoice_notification import resolve_device_targets

        active = EndUser(
            wx_openid="jp-active", nickname="", avatar_url="",
            user_type=EndUserType.APP, status=EndUserStatus.ACTIVE,
        )
        disabled = EndUser(
            wx_openid="jp-disabled", nickname="", avatar_url="",
            user_type=EndUserType.APP, status=EndUserStatus.DISABLED,
        )
        db_session.add_all([active, disabled])
        db_session.flush()
        db_session.add(EndUserDeviceToken(
            end_user_id=active.id, platform="ios", device_token="tok-live",
        ))
        db_session.add(EndUserDeviceToken(
            end_user_id=disabled.id, platform="ios", device_token="tok-dead",
        ))
        db_session.commit()

        assert [t.device_token for t in
                resolve_device_targets(db_session, "jp-active")] == ["tok-live"]
        assert resolve_device_targets(db_session, "jp-disabled") == []


# ═══════════════════════════════════════════════════════════════════════════════
# _push_app_notification: 1011 失效 token 清理接线
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidTokenCleanup:
    def test_push_app_notification_drains_and_deletes_invalid_tokens(self, client, monkeypatch):
        """provider 报 1011 → 该 token 从 end_user_device_tokens 删除。"""
        from app.models.end_user import EndUser, EndUserStatus, EndUserType
        from app.models.end_user_device_token import EndUserDeviceToken
        from app.models.invoice_request import InvoiceRequest
        from app.services import invoice_notification as mod

        s = client._sesh
        u = EndUser(
            wx_openid="jp-clean-openid", nickname="", avatar_url="",
            user_type=EndUserType.APP, status=EndUserStatus.ACTIVE,
        )
        s.add(u)
        s.flush()
        s.add(EndUserDeviceToken(
            end_user_id=u.id, platform="ios", device_token="dead-reg",
        ))
        s.commit()

        from app.services.push import JPushProvider  # noqa: F401 验证可导入

        from app.services.push import JPushProvider as JP

        class FakeJP(JP):
            """不发 HTTP 的 JPush 替身: send 后报一个失效 token。"""

            def send(self, end_user_id, title, body, payload):
                self._invalid_tokens.append(payload["device_token"])
                return False

            def _configured(self):
                return True

        import app.services.push as push_module

        fake = FakeJP()
        monkeypatch.setattr(push_module, "get_push_provider", lambda: fake)

        request = InvoiceRequest(id=501, user_id=42, amount=100)
        mod._push_app_notification(request, db=s, openid="jp-clean-openid")

        s.flush()
        remaining = [t.device_token for t in s.query(EndUserDeviceToken).all()]
        assert remaining == []  # 失效 token 已清理


# ═══════════════════════════════════════════════════════════════════════════════
# 端点: POST /business/devices/token 接受 provider 字段 (卡 7f601f7f)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeviceTokenProviderField:
    """provider 可选字段: 接受 "jpush" / 缺省; 拒绝未知值 (当前仅 jpush)。"""

    def _login(self, client):
        body = client.post(
            "/api/v1/business/auth/wx-login", json={"code": "jp-login"},
        ).json()["data"]
        return {"Authorization": f"Bearer {body['token']}"}

    def test_accepts_jpush_provider(self, client):
        headers = self._login(client)
        r = client.post(
            "/api/v1/business/devices/token",
            json={"platform": "ios", "device_token": "reg-1",
                  "provider": "jpush"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0

    def test_provider_omitted_backward_compatible(self, client):
        headers = self._login(client)
        r = client.post(
            "/api/v1/business/devices/token",
            json={"platform": "android", "device_token": "reg-2"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["code"] == 0

    def test_unknown_provider_rejected(self, client):
        headers = self._login(client)
        r = client.post(
            "/api/v1/business/devices/token",
            json={"platform": "ios", "device_token": "reg-3",
                  "provider": "getui"},
            headers=headers,
        )
        assert r.status_code == 422
