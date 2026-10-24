"""通知渠道真实发送 单元测试 (卡 d3ee0167)

源文件 app/services/channel_providers.py 当前零测试。本文件覆盖:
- im_sign / _build_im_payload: IM HMAC-SHA256 签名与消息体
- _eval_im: 响应判定 (code0 / StatusCode0 / 失败 / 异常)
- _post_with_retry: 2xx/4xx 立返 / 5xx 重试 / 异常重试 / 退避
- _send_im / _send_wecom / _send_webhook: webhook_url 缺失 skipped / 正常 sent / 失败 / 异常
- SmsProvider / VoiceProvider (ABC) + _CloudProviderSmsProvider / _CloudProviderVoiceProvider mock
- get_sms_provider / get_voice_provider 工厂
- _send_sms / _send_voice / _send_email_mock: phone 解析 / mock 返回
- _send_wx_subscribe: openid/template_id 缺失 skipped / 转发 send_subscribe_msg / 异常兜底
- _norm_channel: str / ChannelType
- send_channel: 各渠道分发 + 未知渠道 failed
- _lookup_channel_config / dispatch_real_channel: no_config / no_credential / 真实发送桥接

测试缝 (源码 docstring 约定):
- FakeClient 注入 httpx (send_channel / _send_* 接受 client 参数)
- backoff 归零 + monkeypatch cp.asyncio.sleep 跳过退避
"""
import asyncio
import types
from unittest.mock import MagicMock

import pytest

from app.models.channel_config import ChannelConfig, ChannelType
from app.services import channel_providers as cp


# ============================================================
# FakeClient / FakeResp
# ============================================================

class _FakeResp:
    def __init__(self, status_code=200, body=None, json_exc=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._body


class FakeClient:
    """httpx.AsyncClient 替身。responses 优先, 耗尽后抛 post_exc。"""

    def __init__(self, responses=None, post_exc=None):
        if responses is None:
            responses = []
        if isinstance(responses, _FakeResp):
            responses = [responses]
        self._responses = list(responses)
        self.post_exc = post_exc
        self.posts = []
        self.aclosed = False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if self._responses:
            return self._responses.pop(0)
        if self.post_exc is not None:
            if isinstance(self.post_exc, list):
                exc = self.post_exc.pop(0)
                if exc is not None:
                    raise exc
            else:
                raise self.post_exc
        return _FakeResp(200, {})

    async def aclose(self):
        self.aclosed = True


# ============================================================
# 公共 fixture
# ============================================================

@pytest.fixture(autouse=True)
def _skip_backoff_sleep(monkeypatch):
    async def _no_sleep(_):
        return None
    monkeypatch.setattr(cp.asyncio, "sleep", _no_sleep)


# ============================================================
# im_sign
# ============================================================

class TestIMSign:
    def test_returns_base64_string(self):
        sig = cp.im_sign(1700000000, "mysecret")
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_deterministic_for_same_inputs(self):
        assert cp.im_sign(123, "s") == cp.im_sign(123, "s")

    def test_different_secret_different_sig(self):
        assert cp.im_sign(123, "s1") != cp.im_sign(123, "s2")

    def test_different_timestamp_different_sig(self):
        assert cp.im_sign(123, "s") != cp.im_sign(124, "s")

    def test_matches_manual_computation(self):
        """对照官方算法手算验证 (HMAC-SHA256 of f'{ts}\\n{secret}', base64)。"""
        import base64
        import hashlib
        import hmac
        ts, secret = 1700000000, "abc"
        expected = base64.b64encode(
            hmac.new(f"{ts}\n{secret}".encode(), digestmod=hashlib.sha256).digest()
        ).decode()
        assert cp.im_sign(ts, secret) == expected


# ============================================================
# _build_im_payload
# ============================================================

class TestBuildIMPayload:
    def test_no_secret_omits_timestamp_sign(self, monkeypatch):
        # 固定 time.time 避免偶然影响
        payload = cp._build_im_payload("hello", None)
        assert payload["msg_type"] == "text"
        assert payload["content"] == {"text": "hello"}
        assert "timestamp" not in payload
        assert "sign" not in payload

    def test_with_secret_attaches_timestamp_sign(self, monkeypatch):
        monkeypatch.setattr(cp.time, "time", lambda: 1700000000.0)
        payload = cp._build_im_payload("hello", "sec")
        assert payload["timestamp"] == "1700000000"
        assert payload["sign"] == cp.im_sign(1700000000, "sec")


# ============================================================
# _eval_im
# ============================================================

class TestEvalIM:
    def test_code_zero_sent(self):
        assert cp._eval_im(_FakeResp(200, {"code": 0})) == {
            "status": "sent", "channel": "im"}

    def test_statuscode_zero_sent(self):
        assert cp._eval_im(_FakeResp(200, {"StatusCode": 0})) == {
            "status": "sent", "channel": "im"}

    def test_nonzero_code_failed(self):
        result = cp._eval_im(_FakeResp(200, {"code": 19021, "msg": "bad"}))
        assert result["status"] == "failed"
        assert "19021" in result["error"]

    def test_json_exception_failed(self):
        result = cp._eval_im(_FakeResp(200, json_exc=ValueError()))
        assert result["status"] == "failed"


# ============================================================
# _post_with_retry
# ============================================================

class TestPostWithRetry:
    def test_2xx_returns_immediately(self):
        client = FakeClient(_FakeResp(200, {}))
        resp = asyncio.run(cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0))
        assert resp.status_code == 200
        assert len(client.posts) == 1

    def test_4xx_returns_immediately_no_retry(self):
        client = FakeClient(_FakeResp(404, {}))
        resp = asyncio.run(cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0))
        assert resp.status_code == 404
        assert len(client.posts) == 1

    def test_5xx_retries_then_success(self):
        client = FakeClient([_FakeResp(503), _FakeResp(200, {})])
        resp = asyncio.run(cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0))
        assert resp.status_code == 200
        assert len(client.posts) == 2

    def test_5xx_exhausts_retries_raises(self):
        client = FakeClient([_FakeResp(500), _FakeResp(500), _FakeResp(500)])
        with pytest.raises(RuntimeError, match="http 500"):
            asyncio.run(cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0))
        assert len(client.posts) == 3

    def test_exception_retries_then_raises(self):
        client = FakeClient(post_exc=[ConnectionError(), ConnectionError(), ConnectionError()])
        with pytest.raises(ConnectionError):
            asyncio.run(cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0))
        assert len(client.posts) == 3

    def test_backoff_exponential(self, monkeypatch):
        sleeps = []

        async def _record(d):
            sleeps.append(d)

        monkeypatch.setattr(cp.asyncio, "sleep", _record)
        client = FakeClient([_FakeResp(500), _FakeResp(500), _FakeResp(500)])
        with pytest.raises(RuntimeError):
            asyncio.run(cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0.1))
        assert sleeps == [0.1, 0.2]


# ============================================================
# _send_im / _send_wecom / _send_webhook
# ============================================================

class TestSendIM:
    def test_no_webhook_url_skipped(self):
        result = asyncio.run(cp._send_im({}, "hi", FakeClient(), backoff=0))
        assert result == {"status": "skipped", "channel": "im", "reason": "no webhook_url"}

    def test_success_sent(self):
        client = FakeClient(_FakeResp(200, {"code": 0}))
        result = asyncio.run(cp._send_im(
            {"webhook_url": "http://x"}, "hi", client, backoff=0))
        assert result["status"] == "sent"
        assert result["channel"] == "im"

    def test_failed_response(self):
        client = FakeClient(_FakeResp(200, {"code": 99999}))
        result = asyncio.run(cp._send_im(
            {"webhook_url": "http://x"}, "hi", client, backoff=0))
        assert result["status"] == "failed"

    def test_request_exception_failed(self):
        client = FakeClient(post_exc=[asyncio.TimeoutError()] * 3)
        result = asyncio.run(cp._send_im(
            {"webhook_url": "http://x"}, "hi", client, max_retries=2, backoff=0))
        assert result["status"] == "failed"

    def test_secret_included_in_payload(self, monkeypatch):
        monkeypatch.setattr(cp.time, "time", lambda: 1700000000.0)
        client = FakeClient(_FakeResp(200, {"code": 0}))
        asyncio.run(cp._send_im(
            {"webhook_url": "http://x", "secret": "sec"}, "hi", client, backoff=0))
        _, kw = client.posts[0]
        assert kw["json"]["sign"] == cp.im_sign(1700000000, "sec")


class TestSendWecom:
    def test_no_webhook_url_skipped(self):
        result = asyncio.run(cp._send_wecom({}, "hi", FakeClient(), backoff=0))
        assert result["status"] == "skipped"

    def test_success_sent(self):
        client = FakeClient(_FakeResp(200, {"errcode": 0}))
        result = asyncio.run(cp._send_wecom(
            {"webhook_url": "http://x"}, "hi", client, backoff=0))
        assert result["status"] == "sent"
        _, kw = client.posts[0]
        assert kw["json"]["msgtype"] == "markdown"

    def test_errcode_nonzero_failed(self):
        client = FakeClient(_FakeResp(200, {"errcode": 93000}))
        result = asyncio.run(cp._send_wecom(
            {"webhook_url": "http://x"}, "hi", client, backoff=0))
        assert result["status"] == "failed"


class TestSendWebhook:
    def test_no_webhook_url_skipped(self):
        result = asyncio.run(cp._send_webhook({}, "hi", "subj", FakeClient(), backoff=0))
        assert result["status"] == "skipped"

    def test_2xx_sent(self):
        client = FakeClient(_FakeResp(200, {}))
        result = asyncio.run(cp._send_webhook(
            {"webhook_url": "http://x"}, "hi", "subj", client, backoff=0))
        assert result["status"] == "sent"
        _, kw = client.posts[0]
        assert kw["json"]["subject"] == "subj"
        assert kw["json"]["text"] == "hi"

    def test_4xx_failed(self):
        client = FakeClient(_FakeResp(404, {}))
        result = asyncio.run(cp._send_webhook(
            {"webhook_url": "http://x"}, "hi", "subj", client, backoff=0))
        assert result["status"] == "failed"
        assert "404" in result["error"]

    def test_secret_added_to_header(self):
        client = FakeClient(_FakeResp(200, {}))
        asyncio.run(cp._send_webhook(
            {"webhook_url": "http://x", "secret": "whsec"}, "hi", "subj", client, backoff=0))
        _, kw = client.posts[0]
        assert kw["headers"]["X-Webhook-Secret"] == "whsec"


# ============================================================
# SMS / Voice Provider
# ============================================================

class TestSmsVoiceProviders:
    def test_cloud_provider_sms_provider_returns_mock(self):
        provider = cp._CloudProviderSmsProvider()
        result = provider.send("13800000000", "你的发票已开具",
                               {"sign_name": "S", "template_code": "T"})
        assert result["status"] == "mock"
        assert result["channel"] == "sms"
        assert result["provider"] == "cloud_provider-stub"
        assert result["phone"] == "13800000000"

    def test_cloud_provider_voice_provider_returns_mock(self):
        provider = cp._CloudProviderVoiceProvider()
        result = provider.send("13800000000", "外呼内容",
                               {"voice_caller": "C", "voice_template_code": "T"})
        assert result["status"] == "mock"
        assert result["channel"] == "voice"
        assert result["phone"] == "13800000000"

    def test_sms_provider_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            cp.SmsProvider()

    def test_voice_provider_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            cp.VoiceProvider()

    def test_get_sms_provider_default_cloud_provider(self):
        assert isinstance(cp.get_sms_provider({}), cp._CloudProviderSmsProvider)

    def test_get_sms_provider_cloud_provider_explicit(self):
        assert isinstance(cp.get_sms_provider({"provider": "cloud-a"}), cp._CloudProviderSmsProvider)

    def test_get_sms_provider_unknown_falls_back_to_stub(self):
        # 未报备厂商亦走 stub
        assert isinstance(cp.get_sms_provider({"provider": "cloud-b"}), cp._CloudProviderSmsProvider)

    def test_get_voice_provider_default(self):
        assert isinstance(cp.get_voice_provider({}), cp._CloudProviderVoiceProvider)


class TestSendSmsVoiceEmail:
    def test_send_sms_uses_phone(self):
        result = cp._send_sms({"sign_name": "S"}, "msg", {"phone": "13900000000"})
        assert result["status"] == "sent"
        assert result["channel"] == "sms"
        assert result["phone"] == "13900000000"

    def test_send_sms_falls_back_to_receiver_id(self):
        # phone 缺失时用 receiver.id
        result = cp._send_sms({}, "msg", {"id": "user-123"})
        assert result["phone"] == "user-123"

    def test_send_sms_empty_receiver(self):
        result = cp._send_sms({}, "msg", None)
        assert result["phone"] == ""

    def test_send_voice_uses_phone(self):
        result = cp._send_voice({}, "msg", {"phone": "13700000000"})
        assert result["status"] == "sent"
        assert result["channel"] == "voice"

    def test_send_email_mock(self):
        result = cp._send_email_mock({}, "msg", {"email": "a@b.com"}, "发票通知")
        assert result == {"status": "sent", "channel": "email", "provider": "mock"}


# ============================================================
# _send_wx_subscribe (转发 wx_subscribe_msg)
# ============================================================

class TestSendWxSubscribeChannel:
    def test_no_openid_skipped(self):
        result = asyncio.run(cp._send_wx_subscribe(
            {"template_id": "tpl"}, "msg", FakeClient(), backoff=0))
        assert result["status"] == "skipped"
        assert result["reason"] == "no_openid"

    def test_no_template_id_skipped(self):
        result = asyncio.run(cp._send_wx_subscribe(
            {"openid": "oid"}, "msg", FakeClient(), backoff=0))
        assert result["status"] == "skipped"
        assert result["reason"] == "no_template_id"

    def test_forwards_to_send_subscribe_msg(self, monkeypatch):
        # 凭证缺失 → send_subscribe_msg 返回 skipped (no_credentials), 验证转发链路通
        from app.services import wx_subscribe_msg
        monkeypatch.setattr(wx_subscribe_msg.settings, "WX_MP_APPID", None)
        monkeypatch.setattr(wx_subscribe_msg.settings, "WX_MP_SECRET", None)
        result = asyncio.run(cp._send_wx_subscribe(
            {"openid": "oid", "template_id": "tpl"}, "msg", FakeClient(), backoff=0))
        assert result["status"] == "skipped"
        assert result["reason"] == "no_credentials"

    def test_exception_caught_returns_failed(self, monkeypatch):
        from app.services import wx_subscribe_msg
        async def _boom(**kwargs):
            raise RuntimeError("downstream crash")
        monkeypatch.setattr(wx_subscribe_msg, "send_subscribe_msg", _boom)
        result = asyncio.run(cp._send_wx_subscribe(
            {"openid": "oid", "template_id": "tpl"}, "msg", FakeClient(), backoff=0))
        assert result["status"] == "failed"
        assert "downstream crash" in result["error"]


# ============================================================
# _norm_channel + send_channel 分发
# ============================================================

class TestNormChannel:
    def test_str_passthrough(self):
        assert cp._norm_channel("im") == "im"

    def test_channeltype_uses_value(self):
        assert cp._norm_channel(ChannelType.IM) == "im"

    def test_channeltype_wecom(self):
        assert cp._norm_channel(ChannelType.WECOM) == "wecom"


class TestSendChannelDispatch:
    def test_im_dispatch(self):
        client = FakeClient(_FakeResp(200, {"code": 0}))
        result = asyncio.run(cp.send_channel(
            "im", {"webhook_url": "http://x"}, "hi", client=client, backoff=0))
        assert result["status"] == "sent"

    def test_wecom_dispatch(self):
        client = FakeClient(_FakeResp(200, {"errcode": 0}))
        result = asyncio.run(cp.send_channel(
            "wecom", {"webhook_url": "http://x"}, "hi", client=client, backoff=0))
        assert result["status"] == "sent"

    def test_webhook_dispatch(self):
        client = FakeClient(_FakeResp(200, {}))
        result = asyncio.run(cp.send_channel(
            "webhook", {"webhook_url": "http://x"}, "hi", "subj", client=client, backoff=0))
        assert result["status"] == "sent"

    def test_sms_dispatch(self):
        result = asyncio.run(cp.send_channel(
            "sms", {"sign_name": "S"}, "msg", receiver={"phone": "13800000000"}))
        assert result["status"] == "sent"
        assert result["channel"] == "sms"

    def test_voice_dispatch(self):
        result = asyncio.run(cp.send_channel(
            "voice", {}, "msg", receiver={"phone": "13800000000"}))
        assert result["status"] == "sent"
        assert result["channel"] == "voice"

    def test_email_dispatch(self):
        result = asyncio.run(cp.send_channel(
            "email", {}, "msg", subject="subj", receiver={"email": "a@b.com"}))
        assert result == {"status": "sent", "channel": "email", "provider": "mock"}

    def test_unknown_channel_failed(self):
        result = asyncio.run(cp.send_channel("unknown_ch", {}, "msg"))
        assert result["status"] == "failed"
        assert "unsupported channel" in result["error"]

    def test_channeltype_enum_dispatch(self):
        client = FakeClient(_FakeResp(200, {"code": 0}))
        result = asyncio.run(cp.send_channel(
            ChannelType.IM, {"webhook_url": "http://x"}, "hi", client=client, backoff=0))
        assert result["status"] == "sent"


# ============================================================
# Fake DB for _lookup_channel_config / dispatch_real_channel
# ============================================================

class _FakeConfigRow:
    """模拟 ChannelConfig ORM 行: 有 .config dict + .channel + .team_id + .enabled。"""

    def __init__(self, config, channel="im", team_id=None, enabled=True):
        self.config = config
        self.channel = channel
        self.team_id = team_id
        self.enabled = enabled


class _FakeQuery:
    """链式 .filter(...).first() 的替身。返回预设的 row (或 None)。"""

    def __init__(self, return_value):
        self._return_value = return_value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._return_value


class _FakeDB:
    """query(Model) 返回 _FakeQuery。可按模型切换返回值。"""

    def __init__(self, returns):
        # returns: {Model: row_or_None}
        self._returns = returns

    def query(self, model):
        return _FakeQuery(self._returns.get(model))


# ============================================================
# _lookup_channel_config
# ============================================================

class TestLookupChannelConfig:
    def test_team_level_hit(self):
        row = _FakeConfigRow({"webhook_url": "http://x"}, team_id=1)
        db = _FakeDB({ChannelConfig: row})
        assert cp._lookup_channel_config(db, 1, "im") is row

    def test_no_team_row_falls_back_to_platform(self):
        platform_row = _FakeConfigRow({"webhook_url": "http://x"}, team_id=None)
        # 团队级查询返回 None → 但 _FakeDB 只能返回一个固定值
        # 用两次 query 返回不同值: 扩展 _FakeDB 支持 callable
        calls = {"count": 0}

        class _DB:
            def query(self, model):
                calls["count"] += 1
                return _FakeQuery(None if calls["count"] == 1 else platform_row)
        result = cp._lookup_channel_config(_DB(), 5, "im")
        assert result is platform_row

    def test_invalid_channel_returns_none(self):
        # ChannelType("unknown") 抛 ValueError → 返回 None
        db = _FakeDB({})
        assert cp._lookup_channel_config(db, 1, "totally-unknown") is None

    def test_no_row_team_none(self):
        # team_id=None 且无行 → 直接 None, 不回退
        db = _FakeDB({ChannelConfig: None})
        assert cp._lookup_channel_config(db, None, "im") is None


# ============================================================
# dispatch_real_channel (同步桥接)
# ============================================================

class TestDispatchRealChannel:
    def test_no_config_skipped(self):
        db = _FakeDB({ChannelConfig: None})
        result = cp.dispatch_real_channel("im", 1, db, {"phone": "x"}, "hi")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_config"

    def test_http_channel_no_webhook_url_skipped(self):
        row = _FakeConfigRow({"secret": "s"})  # 缺 webhook_url
        db = _FakeDB({ChannelConfig: row})
        result = cp.dispatch_real_channel("im", 1, db, {"phone": "x"}, "hi")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_credential"

    def test_im_real_send_sent(self):
        row = _FakeConfigRow({"webhook_url": "http://x"})
        db = _FakeDB({ChannelConfig: row})
        client = FakeClient(_FakeResp(200, {"code": 0}))
        result = cp.dispatch_real_channel(
            "im", 1, db, {"phone": "x"}, "hi", client=client)
        assert result["status"] == "sent"
        assert result["channel"] == "im"

    def test_sms_real_send_uses_mock_provider(self):
        row = _FakeConfigRow({"sign_name": "S"}, channel="sms")
        db = _FakeDB({ChannelConfig: row})
        result = cp.dispatch_real_channel(
            "sms", 1, db, {"phone": "13800000000"}, "msg")
        assert result["status"] == "sent"
        assert result["channel"] == "sms"

    def test_send_exception_returns_failed(self, monkeypatch):
        row = _FakeConfigRow({"webhook_url": "http://x"})
        db = _FakeDB({ChannelConfig: row})
        # 注入的 client 永远超时 → _post_with_retry 重试耗尽 → _send_im 返回 failed
        client = FakeClient(post_exc=[asyncio.TimeoutError()] * 3)
        result = cp.dispatch_real_channel(
            "im", 1, db, {"phone": "x"}, "hi", client=client)
        assert result["status"] == "failed"

    def test_unknown_channel_no_config_skipped(self):
        # _lookup_channel_config 对未知渠道返回 None → no_config
        db = _FakeDB({})
        result = cp.dispatch_real_channel("ghost", 1, db, {"phone": "x"}, "hi")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_config"


# ============================================================
# _run_sync (同步执行协程)
# ============================================================

class TestRunSync:
    def test_runs_coroutine_no_running_loop(self):
        async def coro():
            return 42

        assert cp._run_sync(coro()) == 42

    def test_runs_coroutine_within_running_loop_uses_thread(self):
        """已有运行循环时走 ThreadPoolExecutor (避免嵌套 asyncio.run)。"""
        async def outer():
            # 在协程内调用 _run_sync → 检测到运行循环 → 线程执行
            return cp._run_sync(_inner_coro())

        async def _inner_coro():
            return "from-thread"

        assert asyncio.run(outer()) == "from-thread"


# ============================================================
# 卡 c7b06c98: _send_sms/_send_voice 透传 provider.send() 结果
# ============================================================

class _FakeProvider:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    def send(self, phone, content, config):
        self.calls.append((phone, content, config))
        if self.exc:
            raise self.exc
        return dict(self.result)


class TestSendSmsVoiceProviderPassthrough:
    def test_sms_failed_result_passthrough(self, monkeypatch):
        fake = _FakeProvider({"status": "failed", "error": "provider down"})
        monkeypatch.setattr(cp, "get_sms_provider", lambda cfg: fake)
        result = cp._send_sms({}, "msg", {"phone": "13900000000"})
        assert result["status"] == "failed"
        assert "provider down" in result["error"]
        assert result["channel"] == "sms"
        assert fake.calls and fake.calls[0][0] == "13900000000"

    def test_voice_failed_result_passthrough(self, monkeypatch):
        fake = _FakeProvider({"status": "failed", "error": "quota exceeded"})
        monkeypatch.setattr(cp, "get_voice_provider", lambda cfg: fake)
        result = cp._send_voice({}, "msg", {"phone": "13700000000"})
        assert result["status"] == "failed"
        assert "quota exceeded" in result["error"]
        assert result["channel"] == "voice"

    def test_sms_exception_propagates(self, monkeypatch):
        fake = _FakeProvider(exc=RuntimeError("network unreachable"))
        monkeypatch.setattr(cp, "get_sms_provider", lambda cfg: fake)
        with pytest.raises(RuntimeError, match="network unreachable"):
            cp._send_sms({}, "msg", {"phone": "13900000000"})

    def test_voice_exception_propagates(self, monkeypatch):
        fake = _FakeProvider(exc=RuntimeError("boom"))
        monkeypatch.setattr(cp, "get_voice_provider", lambda cfg: fake)
        with pytest.raises(RuntimeError, match="boom"):
            cp._send_voice({}, "msg", {"phone": "13700000000"})

    def test_sms_mock_status_backward_compatible(self, monkeypatch):
        fake = _FakeProvider({"status": "mock", "channel": "sms", "provider": "cloud_provider-stub"})
        monkeypatch.setattr(cp, "get_sms_provider", lambda cfg: fake)
        result = cp._send_sms({}, "msg", {"phone": "13900000000"})
        assert result["status"] == "sent"
        assert result["provider"] == "mock"
        assert result["channel"] == "sms"
        assert result["phone"] == "13900000000"

    def test_voice_mock_status_backward_compatible(self, monkeypatch):
        fake = _FakeProvider({"status": "mock", "channel": "voice", "provider": "cloud_provider-stub"})
        monkeypatch.setattr(cp, "get_voice_provider", lambda cfg: fake)
        result = cp._send_voice({}, "msg", {"phone": "13700000000"})
        assert result["status"] == "sent"
        assert result["provider"] == "mock"
        assert result["channel"] == "voice"
