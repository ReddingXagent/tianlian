"""channel_providers 单元测试覆盖补全 (卡 fb54bc19)

被测: app/services/channel_providers.py — 通知渠道真实发送 (IM签名 / HTTP 重试 /
SMS·Voice Provider / 退避 / 同步桥接)。

10 个审计要点:
  1. im_sign            已知向量验证 HMAC-SHA256
  2. _build_im_payload  secret 有/无两分支
  3. _eval_im           code==0 / StatusCode==0 / 字段缺失
  4. SmsProvider/VoiceProvider ABC 抽象不可实例化
  5. _CloudProviderSmsProvider/_CloudProviderVoiceProvider 构造+参数
  6. get_sms_provider/get_voice_provider 工厂
  7. _send_sms/_send_voice 发送+异常 (注入抛错 Provider)
  8. dispatch_real_channel 未配置/缺凭证跳过 INFO + im/wecom/webhook 发送分支
  9. _run_sync             有 loop (线程池) / 无 loop (asyncio.run)
  10. _norm_channel        枚举/字符串归一化各分支

测试缝:
  - send_channel(client=FakeClient) 绕过真实 httpx
  - backoff=0 + monkeypatch asyncio.sleep 跳过退避
  - dispatch_real_channel 用 test_db + 注入 FakeClient

铁律: 只加测试, 不改 production。
"""
import asyncio
import base64
import hashlib
import hmac
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.models.channel_config import ChannelConfig, ChannelType
from app.services import channel_providers as cp


# ═══════════════════════════════════════════════════════════════
# FakeClient — 注入式 httpx 替身 (绕过真实网络)
# ═══════════════════════════════════════════════════════════════
class FakeClient:
    """最小化 httpx.AsyncClient 替身。

    resp_fn(attempt, url, json, headers) -> {status_code, payload}
    或 resp_fn 抛异常模拟网络错误。
    """

    def __init__(self, resp_fn=None, status_code=200, payload=None,
                 exc=None):
        self.calls = []
        self._resp_fn = resp_fn
        self._status_code = status_code
        self._payload = payload
        self._exc = exc

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self._exc is not None:
            raise self._exc
        if self._resp_fn is not None:
            return self._resp_fn(url, json, headers)
        r = MagicMock()
        r.status_code = self._status_code
        r.json.return_value = self._payload if self._payload is not None else {}
        return r


def _seed_cfg(db, team_id=None, channel=ChannelType.IM, config=None,
              enabled=True):
    cfg = ChannelConfig(
        team_id=team_id, channel=channel,
        config=config or {}, enabled=enabled,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


async def _noop_sleep(_seconds=None):
    """退避替身: 不睡眠, 不递归 (patch cp.asyncio.sleep 时用)。"""
    return None


# ═══════════════════════════════════════════════════════════════
# 1. im_sign — 已知向量
# ═══════════════════════════════════════════════════════════════
def test_im_sign_known_vector():
    """已知向量: ts=1700000000, secret='mytestsecret' → 手算 HMAC-SHA256/base64。"""
    ts = 1700000000
    secret = "mytestsecret"
    # 独立手算 (不复用被测代码), 确保不是自我验证
    string_to_sign = f"{ts}\n{secret}"
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    assert expected == "yqSD4MwlqXdjZX/tCtqd+2Rk2nyNOs9oSHTPRgDNGZ8="

    assert cp.im_sign(ts, secret) == expected


def test_im_sign_deterministic_and_distinct():
    """同一输入确定性; 不同 secret/ts 产生不同签名。"""
    s1 = cp.im_sign(1700000000, "abc")
    s2 = cp.im_sign(1700000000, "abc")
    assert s1 == s2  # 确定性
    assert cp.im_sign(1700000000, "abc") != cp.im_sign(1700000000, "xyz")
    assert cp.im_sign(1700000000, "abc") != cp.im_sign(1700000001, "abc")


def test_im_sign_is_base64_sha256():
    """签名长度 = base64(SHA256) = 44 字符, 且 base64 可解码为 32 字节。"""
    sig = cp.im_sign(1, "s")
    assert len(sig) == 44
    raw = base64.b64decode(sig)
    assert len(raw) == 32  # SHA-256 摘要


def test_im_sign_empty_secret():
    """空 secret 仍可签名 (HMAC key = f"{ts}\n"), 不抛, 结果确定性。

    注意: 这是 im_sign 函数级行为; _build_im_payload 因 `if secret:` 不会对
    空串调用签名, 但 im_sign 自身对空 secret 不应崩溃。"""
    sig = cp.im_sign(1700000000, "")
    assert isinstance(sig, str)
    assert len(sig) == 44
    # 确定性
    assert cp.im_sign(1700000000, "") == sig
    # 与非空 secret 结果不同
    assert sig != cp.im_sign(1700000000, "x")
    # 独立手算验证 (key = "1700000000\n")
    string_to_sign = "1700000000\n"
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    assert sig == expected


# ═══════════════════════════════════════════════════════════════
# 2. _build_im_payload — secret 有/无
# ═══════════════════════════════════════════════════════════════
def test_build_im_payload_no_secret():
    """无 secret → 仅 msg_type/content, 不含 timestamp/sign。"""
    p = cp._build_im_payload("hello", None)
    assert p["msg_type"] == "text"
    assert p["content"] == {"text": "hello"}
    assert "timestamp" not in p
    assert "sign" not in p


def test_build_im_payload_with_secret(monkeypatch):
    """有 secret → 附加 timestamp(str) + sign(HMAC-SHA256)。"""
    monkeypatch.setattr(cp.time, "time", lambda: 1700000000.0)
    p = cp._build_im_payload("hello", "sec")
    assert p["msg_type"] == "text"
    assert p["content"] == {"text": "hello"}
    assert p["timestamp"] == "1700000000"  # str 形式
    assert p["sign"] == cp.im_sign(1700000000, "sec")


def test_build_im_payload_empty_string_secret_treated_as_none():
    """空串 secret → falsy, 不附加签名 (与 `if secret:` 一致)。"""
    p = cp._build_im_payload("hi", "")
    assert "sign" not in p
    assert "timestamp" not in p


# ═══════════════════════════════════════════════════════════════
# 3. _eval_im — code==0 / StatusCode==0 / 字段缺失
# ═══════════════════════════════════════════════════════════════
def _im_resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    return r


def test_eval_im_code_zero_success():
    out = cp._eval_im(_im_resp({"code": 0}))
    assert out == {"status": "sent", "channel": "im"}


def test_eval_im_legacy_status_code_zero_success():
    out = cp._eval_im(_im_resp({"StatusCode": 0}))
    assert out == {"status": "sent", "channel": "im"}


def test_eval_im_nonzero_code_failed():
    out = cp._eval_im(_im_resp({"code": 19021, "msg": "sign invalid"}))
    assert out["status"] == "failed"
    assert out["channel"] == "im"
    assert "19021" in out["error"]


def test_eval_im_missing_fields_failed():
    """无 code/StatusCode → 落 failed 分支, error 含 body。"""
    out = cp._eval_im(_im_resp({"unrelated": "x"}))
    assert out["status"] == "failed"
    assert "unrelated" in out["error"]


def test_eval_im_json_exception_returns_empty_failed():
    """resp.json() 抛异常 → body={}, 落 failed。"""
    r = MagicMock()
    r.json.side_effect = ValueError("bad json")
    out = cp._eval_im(r)
    assert out["status"] == "failed"
    assert out["channel"] == "im"


# ═══════════════════════════════════════════════════════════════
# 4. SmsProvider/VoiceProvider ABC — 抽象不可实例化
# ═══════════════════════════════════════════════════════════════
def test_sms_provider_is_abstract():
    assert cp.SmsProvider.__abstractmethods__
    with pytest.raises(TypeError):
        cp.SmsProvider()


def test_voice_provider_is_abstract():
    assert cp.VoiceProvider.__abstractmethods__
    with pytest.raises(TypeError):
        cp.VoiceProvider()


def test_provider_subclass_must_implement_send():
    """缺 send 仍不可实例化。"""
    class Half(cp.SmsProvider):
        pass
    with pytest.raises(TypeError):
        Half()


# ═══════════════════════════════════════════════════════════════
# 5. _CloudProviderSmsProvider / _CloudProviderVoiceProvider — 构造+参数
# ═══════════════════════════════════════════════════════════════
def test_cloud_provider_sms_provider_send_shape(caplog):
    cfg = {"sign_name": "天链", "template_code": "SMS_1"}
    caplog.set_level(logging.INFO, logger="app.services.channel_providers")
    out = cp._CloudProviderSmsProvider().send("13800000000", "告警内容", cfg)
    assert out["status"] == "mock"
    assert out["channel"] == "sms"
    assert out["provider"] == "cloud_provider-stub"
    assert out["phone"] == "13800000000"
    # stub 走 info log
    assert any("SMS ALIYUN-STUB" in r.message for r in caplog.records)


def test_cloud_provider_sms_provider_send_none_config_safe():
    """config=None / content=None 不抛 ([:60] 切片对 None 须前置 (content or ''))。"""
    out = cp._CloudProviderSmsProvider().send("138", None, None)
    assert out["status"] == "mock"


def test_cloud_provider_voice_provider_send_shape(caplog):
    cfg = {"voice_caller": "4001", "voice_template_code": "TTS_1"}
    caplog.set_level(logging.INFO, logger="app.services.channel_providers")
    out = cp._CloudProviderVoiceProvider().send("13900000000", "外呼", cfg)
    assert out["status"] == "mock"
    assert out["channel"] == "voice"
    assert out["provider"] == "cloud_provider-stub"
    assert out["phone"] == "13900000000"
    assert any("VOICE ALIYUN-STUB" in r.message for r in caplog.records)


def test_cloud_provider_providers_are_provider_subclasses():
    assert isinstance(cp._CloudProviderSmsProvider(), cp.SmsProvider)
    assert isinstance(cp._CloudProviderVoiceProvider(), cp.VoiceProvider)


# ═══════════════════════════════════════════════════════════════
# 6. get_sms_provider / get_voice_provider — 工厂
# ═══════════════════════════════════════════════════════════════
def test_get_sms_provider_default_cloud_provider():
    p = cp.get_sms_provider({})
    assert isinstance(p, cp._CloudProviderSmsProvider)


def test_get_sms_provider_explicit_cloud_provider():
    p = cp.get_sms_provider({"provider": "cloud-a"})
    assert isinstance(p, cp._CloudProviderSmsProvider)


def test_get_sms_provider_unknown_falls_back_stub():
    """未知厂商亦走 stub (未报备)。"""
    p = cp.get_sms_provider({"provider": "cloud-b"})
    assert isinstance(p, cp._CloudProviderSmsProvider)


def test_get_sms_provider_none_config():
    p = cp.get_sms_provider(None)
    assert isinstance(p, cp._CloudProviderSmsProvider)


def test_get_voice_provider_returns_stub():
    p = cp.get_voice_provider({})
    assert isinstance(p, cp._CloudProviderVoiceProvider)


# ═══════════════════════════════════════════════════════════════
# 7. _send_sms / _send_voice — 发送 + 异常
# ═══════════════════════════════════════════════════════════════
def test_send_sms_phone_from_receiver():
    out = cp._send_sms({"sign_name": "s"}, "msg", {"phone": "13800000000"})
    assert out == {"status": "sent", "channel": "sms",
                   "provider": "mock", "phone": "13800000000"}


def test_send_sms_phone_fallback_to_id():
    """无 phone 字段 → 回退 receiver.id。"""
    out = cp._send_sms({}, "msg", {"id": "user-9"})
    assert out["phone"] == "user-9"


def test_send_sms_empty_receiver():
    out = cp._send_sms({}, "msg", {})
    assert out["phone"] == ""
    assert out["status"] == "sent"  # mock 永不抛


def test_send_sms_none_receiver():
    out = cp._send_sms({}, "msg", None)
    assert out["phone"] == ""


def test_send_sms_provider_exception_propagates():
    """注入抛异常的 Provider → _send_sms 不吞异常 (真实 SDK 报错应上抛,
    由调用方落 notification_logs)。验证契约: send 抛则上抛。"""
    class BoomProvider(cp.SmsProvider):
        def send(self, phone, content, config):
            raise RuntimeError("cloud_provider 500")
    with patch.object(cp, "get_sms_provider", return_value=BoomProvider()):
        with pytest.raises(RuntimeError, match="cloud_provider 500"):
            cp._send_sms({}, "msg", {"phone": "138"})


def test_send_voice_phone_from_receiver():
    out = cp._send_voice({}, "msg", {"phone": "13900000000"})
    assert out == {"status": "sent", "channel": "voice",
                   "provider": "mock", "phone": "13900000000"}


def test_send_voice_phone_fallback_to_id():
    out = cp._send_voice({}, "msg", {"id": "user-1"})
    assert out["phone"] == "user-1"


def test_send_voice_provider_exception_propagates():
    class BoomVoice(cp.VoiceProvider):
        def send(self, phone, content, config):
            raise ConnectionError("voice gateway down")
    with patch.object(cp, "get_voice_provider", return_value=BoomVoice()):
        with pytest.raises(ConnectionError, match="voice gateway down"):
            cp._send_voice({}, "msg", {"phone": "139"})


# ═══════════════════════════════════════════════════════════════
# 8. dispatch_real_channel — 跳过 + 发送分支 (含 send_channel HTTP 渠道)
# ═══════════════════════════════════════════════════════════════
def test_dispatch_unconfigured_channel_skipped(test_db, caplog):
    db = test_db["session"]
    caplog.set_level(logging.INFO, logger="app.services.channel_providers")
    out = cp.dispatch_real_channel(
        "im", team_id=10, db=db, receiver={},
        content="hi", subject="s",
    )
    assert out == {"status": "skipped", "channel": "im", "reason": "no_config"}
    assert any("未配置" in r.message for r in caplog.records)


def test_dispatch_invalid_channel_name_skipped(test_db):
    """非法渠道名 → _lookup_channel_config 转 ChannelType 失败 → None → no_config。"""
    db = test_db["session"]
    out = cp.dispatch_real_channel(
        "telegram", team_id=1, db=db, receiver={}, content="hi", subject="s",
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "no_config"


def test_dispatch_disabled_channel_skipped(test_db):
    """enabled=False 行存在 → _lookup 过滤 enabled==True 查不到 → no_config。"""
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.IM,
              config={"webhook_url": "https://x"}, enabled=False)
    out = cp.dispatch_real_channel(
        "im", team_id=10, db=db, receiver={}, content="hi", subject="s",
    )
    assert out == {"status": "skipped", "channel": "im", "reason": "no_config"}


def test_dispatch_missing_credential_skipped(test_db, caplog):
    """HTTP 渠道已配置但缺 webhook_url → no_credential。"""
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.WECOM, config={"secret": "x"})
    caplog.set_level(logging.INFO, logger="app.services.channel_providers")
    out = cp.dispatch_real_channel(
        "wecom", team_id=10, db=db, receiver={}, content="hi", subject="s",
    )
    assert out == {"status": "skipped", "channel": "wecom", "reason": "no_credential"}
    assert any("缺 webhook_url" in r.message for r in caplog.records)


def test_dispatch_im_sent(test_db):
    """im 渠道 + 注入 FakeClient(code=0) → sent。"""
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.IM,
              config={"webhook_url": "https://hook", "secret": "sec"})
    client = FakeClient(status_code=200, payload={"code": 0})
    out = cp.dispatch_real_channel(
        "im", team_id=10, db=db, receiver={}, content="hi", subject="s",
        client=client,
    )
    assert out == {"status": "sent", "channel": "im"}
    assert len(client.calls) == 1
    # secret 存在 → payload 应带 sign
    sent_payload = client.calls[0]["json"]
    assert "sign" in sent_payload and "timestamp" in sent_payload


def test_dispatch_wecom_sent(test_db):
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.WECOM,
              config={"webhook_url": "https://hook"})
    client = FakeClient(status_code=200, payload={"errcode": 0})
    out = cp.dispatch_real_channel(
        "wecom", team_id=10, db=db, receiver={}, content="hi", subject="s",
        client=client,
    )
    assert out == {"status": "sent", "channel": "wecom"}
    assert client.calls[0]["json"]["msgtype"] == "markdown"


def test_dispatch_webhook_sent(test_db):
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.WEBHOOK,
              config={"webhook_url": "https://hook", "secret": "whsec"})
    client = FakeClient(status_code=200)
    out = cp.dispatch_real_channel(
        "webhook", team_id=10, db=db, receiver={}, content="hi", subject="subj",
        client=client,
    )
    assert out == {"status": "sent", "channel": "webhook"}
    # secret → 自定义校验头注入
    assert client.calls[0]["headers"]["X-Webhook-Secret"] == "whsec"


def test_dispatch_sms_uses_mock_provider(test_db):
    """sms 非 HTTP 渠道, 不要求 webhook_url, 走 _send_sms (mock)。"""
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.SMS,
              config={"sign_name": "s", "template_code": "t"})
    out = cp.dispatch_real_channel(
        "sms", team_id=10, db=db, receiver={"phone": "138"}, content="hi", subject="s",
    )
    assert out["status"] == "sent"
    assert out["phone"] == "138"


def test_dispatch_platform_fallback(test_db):
    """team 未配置 → 平台级 (team_id NULL) 回退命中。"""
    db = test_db["session"]
    _seed_cfg(db, team_id=None, channel=ChannelType.IM,
              config={"webhook_url": "https://plat"})
    client = FakeClient(status_code=200, payload={"code": 0})
    out = cp.dispatch_real_channel(
        "im", team_id=999, db=db, receiver={}, content="hi", subject="s",
        client=client,
    )
    assert out == {"status": "sent", "channel": "im"}


def test_dispatch_send_failure_caught(test_db, caplog):
    """send_channel 链路抛未捕获异常 → dispatch 兜底捕获落 failed (永不抛) +
    ERROR 日志。

    _send_im 等子渠道内部已 try/except 兜底返回 failed 不抛; dispatch 的 except
    兜的是更深层未预期异常 (如 _run_sync 桥接失败)。patch _run_sync 抛异常验证契约。"""
    db = test_db["session"]
    _seed_cfg(db, team_id=10, channel=ChannelType.IM,
              config={"webhook_url": "https://hook"})
    caplog.set_level(logging.ERROR, logger="app.services.channel_providers")

    # _run_sync 被 patch 后不再 await 传入的 send_channel 协程; 拦截并关闭它,
    # 避免 "coroutine was never awaited" 警告。
    def fake_run_sync(coro):
        coro.close()
        raise RuntimeError("bridge failed")

    with patch.object(cp, "_run_sync", side_effect=fake_run_sync):
        out = cp.dispatch_real_channel(
            "im", team_id=10, db=db, receiver={}, content="hi", subject="s",
            client=FakeClient(),
        )
    assert out["status"] == "failed"
    assert out["channel"] == "im"
    assert "bridge failed" in out["error"]
    assert any("真实发送异常" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════
# 9. _run_sync — async→sync 桥接
# ═══════════════════════════════════════════════════════════════
def test_run_sync_no_running_loop():
    """主线程无运行 loop → asyncio.run 执行协程。"""

    async def coro():
        return 42

    assert cp._run_sync(coro()) == 42


def test_run_sync_with_running_loop_uses_threadpool():
    """有运行 loop (如在 async test 内) → 走 ThreadPoolExecutor, 不污染当前 loop。"""

    async def inner():
        return "from-threadpool"

    async def outer():
        # 当前已有运行 loop → _run_sync 应转入独立线程跑 asyncio.run
        return cp._run_sync(inner())

    assert asyncio.run(outer()) == "from-threadpool"


def test_run_sync_preserves_exception():
    """协程内异常透传。"""

    async def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        cp._run_sync(boom())


# ═══════════════════════════════════════════════════════════════
# 10. _norm_channel — 枚举/字符串归一化
# ═══════════════════════════════════════════════════════════════
def test_norm_channel_from_enum():
    assert cp._norm_channel(ChannelType.IM) == "im"
    assert cp._norm_channel(ChannelType.WEBHOOK) == "webhook"
    assert cp._norm_channel(ChannelType.SMS) == "sms"


def test_norm_channel_from_string():
    assert cp._norm_channel("im") == "im"
    assert cp._norm_channel("wecom") == "wecom"


def test_norm_channel_unknown_string_passthrough():
    """未知字符串原样返回 (send_channel 末尾走 unsupported 分支)。"""
    assert cp._norm_channel("telegram") == "telegram"


def test_norm_channel_all_enums_covered():
    for ct in ChannelType:
        assert cp._norm_channel(ct) == ct.value


# ═══════════════════════════════════════════════════════════════
# 补充: send_channel 入口 + _post_with_retry 重试退避
# ═══════════════════════════════════════════════════════════════
async def test_send_channel_unsupported():
    out = await cp.send_channel("telegram", {}, "hi")
    assert out["status"] == "failed"
    assert "unsupported channel" in out["error"]


async def test_send_channel_wx_subscribe_skipped_no_openid():
    """卡 3591ea8f: wx_subscribe 缺 openid → skipped (no_openid)。"""
    out = await cp.send_channel(
        "wx_subscribe", {"template_id": "TPL"}, "发票已开具"
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "no_openid"


async def test_send_channel_wx_subscribe_skipped_no_template(monkeypatch):
    """缺 template_id → skipped (no_template_id)。"""
    out = await cp.send_channel(
        "wx_subscribe", {"openid": "oABC"}, "内容"
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "no_template_id"


async def test_send_channel_wx_subscribe_delegates(monkeypatch):
    """完整 config → 委托给 wx_subscribe_msg.send_subscribe_msg, 透传 client/retry。"""
    import app.services.wx_subscribe_msg as wxsm
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {"status": "sent", "channel": "wx_subscribe"}

    monkeypatch.setattr(wxsm, "send_subscribe_msg", fake_send)
    client = FakeClient()
    out = await cp.send_channel(
        "wx_subscribe",
        {"openid": "oABC", "template_id": "TPL", "page": "pages/x",
         "data": {"k": {"value": "v"}}, "miniprogram_state": "trial"},
        "发票已开具", client=client, max_retries=1, timeout=2.0, backoff=0,
    )
    assert out["status"] == "sent"
    assert captured["openid"] == "oABC"
    assert captured["template_id"] == "TPL"
    assert captured["page"] == "pages/x"
    assert captured["miniprogram_state"] == "trial"
    assert captured["client"] is client
    assert captured["max_retries"] == 1
    assert captured["timeout"] == 2.0


async def test_send_channel_wx_subscribe_send_exception_swallowed(monkeypatch):
    """send_subscribe_msg 抛异常 → _send_wx_subscribe 二次兜底 → failed (不向上抛)。"""
    import app.services.wx_subscribe_msg as wxsm

    async def boom(**kwargs):
        raise RuntimeError("send down")

    monkeypatch.setattr(wxsm, "send_subscribe_msg", boom)
    out = await cp.send_channel(
        "wx_subscribe", {"openid": "oABC", "template_id": "TPL"}, "x"
    )
    assert out["status"] == "failed"
    assert "send down" in out["error"]


async def test_send_channel_im_skipped_no_url():
    out = await cp.send_channel("im", {}, "hi")
    assert out == {"status": "skipped", "channel": "im", "reason": "no webhook_url"}


async def test_post_with_retry_4xx_no_retry(monkeypatch):
    """4xx 立即返回, 不重试。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(status_code=404)
    resp = await cp._post_with_retry(client, "u", {}, {}, max_retries=3, backoff=0)
    assert resp.status_code == 404
    assert len(client.calls) == 1  # 未重试


async def test_post_with_retry_5xx_retries(monkeypatch):
    """5xx 重试到 max_retries+1 次。"""
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(cp.asyncio, "sleep", fake_sleep)
    client = FakeClient(status_code=500)
    with pytest.raises(RuntimeError, match="http 500"):
        await cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0.1)
    assert len(client.calls) == 3  # 1 + 2 retries
    # 指数退避: backoff * 2^0, backoff * 2^1
    assert sleeps == [0.1 * 1, 0.1 * 2]


async def test_post_with_retry_network_exc_then_success(monkeypatch):
    """网络异常重试, 随后成功返回。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    calls = {"i": 0}

    def fn(url, json, headers):
        calls["i"] += 1
        if calls["i"] == 1:
            raise ConnectionError("reset")
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"code": 0}
        return r

    client = FakeClient(resp_fn=fn)
    resp = await cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0)
    assert resp.status_code == 200
    assert calls["i"] == 2


async def test_send_webhook_failed_non_2xx(monkeypatch):
    """webhook 渠道 HTTP 非 2xx → failed。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(status_code=403)
    out = await cp.send_channel(
        "webhook", {"webhook_url": "https://h"}, "c", subject="s", client=client,
        backoff=0,
    )
    assert out["status"] == "failed"
    assert "http 403" in out["error"]


async def test_send_email_channel_via_send_channel():
    out = await cp.send_channel("email", {}, "body", subject="subj",
                                receiver={"email": "a@b.com"})
    assert out == {"status": "sent", "channel": "email", "provider": "mock"}


async def test_send_im_exception_returns_failed(monkeypatch):
    """_send_im 内 _post_with_retry 抛 (重试耗尽) → 子渠道兜底 failed 不抛。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(exc=ConnectionError("network down"))
    out = await cp.send_channel(
        "im", {"webhook_url": "https://h"}, "hi", client=client,
        max_retries=1, backoff=0,
    )
    assert out["status"] == "failed"
    assert out["channel"] == "im"
    assert "network down" in out["error"]


async def test_send_wecom_failed_non_zero_errcode(monkeypatch):
    """wecom 渠道 errcode!=0 → failed。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(status_code=200, payload={"errcode": 93000, "errmsg": "bad"})
    out = await cp.send_channel(
        "wecom", {"webhook_url": "https://h"}, "hi", client=client, backoff=0,
    )
    assert out["status"] == "failed"
    assert "93000" in out["error"]


# ═══════════════════════════════════════════════════════════════
# 补充 (卡 b69888ed): _post_with_retry 重试耗尽 + _send_webhook payload 字段
# ═══════════════════════════════════════════════════════════════
async def test_post_with_retry_exhausts_re_raises_last(monkeypatch):
    """重试耗尽 → 抛最后一次异常 (RuntimeError(http 5xx)), error 信息含状态码。

    backoff=0 + patch sleep 消除等待; 与上游 5xx 重试用例互补: 这里断言"最终失败"
    的错误内容 (任务点名 _post_with_retry 最终失败返回错误)。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(status_code=503)
    with pytest.raises(RuntimeError, match="http 503"):
        await cp._post_with_retry(client, "u", {"k": "v"}, {}, max_retries=2, backoff=0)
    assert len(client.calls) == 3  # 1 + 2 重试


async def test_post_with_retry_network_exc_exhausts_re_raises(monkeypatch):
    """纯网络异常重试耗尽 → 抛原始网络异常 (非 RuntimeError http)。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(exc=ConnectionError("dns fail"))
    with pytest.raises(ConnectionError, match="dns fail"):
        await cp._post_with_retry(client, "u", {}, {}, max_retries=1, backoff=0)
    assert len(client.calls) == 2  # 1 + 1 重试


async def test_post_with_retry_default_no_backoff_wait(monkeypatch):
    """backoff=0 时 sleep 入参恒为 0 (验证退避时间公式 backoff*2^attempt 归零)。"""
    sleeps = []

    async def rec_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(cp.asyncio, "sleep", rec_sleep)
    client = FakeClient(status_code=500)
    with pytest.raises(RuntimeError):
        await cp._post_with_retry(client, "u", {}, {}, max_retries=2, backoff=0)
    assert sleeps == [0, 0]  # 两次退避均为 0


async def test_send_webhook_payload_carries_subject_and_content(monkeypatch):
    """_send_webhook payload 含 text/subject/content 三个字段, POST 到 webhook_url。

    与 test_dispatch_webhook_sent (断言 header) 互补: 这里直测 send_channel → payload
    字段 (任务点名 subject 在 payload)。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(status_code=200)
    out = await cp.send_channel(
        "webhook", {"webhook_url": "https://hook.example/notify"},
        "告警内容", subject="CPU 过载", client=client, backoff=0,
    )
    assert out == {"status": "sent", "channel": "webhook"}
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://hook.example/notify"  # POST 到配置 URL
    payload = call["json"]
    assert payload["text"] == "告警内容"
    assert payload["subject"] == "CPU 过载"
    assert payload["content"] == "告警内容"


# ═══════════════════════════════════════════════════════════════
# 补全 (卡 676d2fa1): 自建 client 路径 + wecom/webhook skip 分支 + voice 入口
#
# 盲区根因 (coverage 11 行 Missing): 上方所有 HTTP 用例均注入 FakeClient(client=),
# 绕过 client=None 时 _post_with_retry 自建 httpx.AsyncClient + finally aclose 的路径
# (生产环境 dispatch_real_channel 调 send_channel 不传 client → 恒走自建路径)。
# 测试缝: monkeypatch cp.httpx.AsyncClient → 返回带 aclose 的 fake, 触达自建分支
# 同时保持网络隔离。另补 wecom/webhook 经 send_channel 入口的 skip 分支、voice/email
# 经 send_channel 入口的 dispatch 分支。
# ═══════════════════════════════════════════════════════════════

class _ClosableFakeClient:
    """带 aclose 的 httpx 替身 (自建 client 路径 finally 调 aclose)。

    status_code/payload 控制响应; exc 非空则每次 post 抛; close_tracked 记是否 aclose。
    """

    def __init__(self, status_code=200, payload=None, exc=None):
        self.calls = []
        self._status_code = status_code
        self._payload = payload if payload is not None else {}
        self._exc = exc
        self.close_tracked = False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self._exc is not None:
            raise self._exc
        r = MagicMock()
        r.status_code = self._status_code
        r.json.return_value = self._payload
        return r

    async def aclose(self):
        self.close_tracked = True


async def test_post_with_retry_own_client_success(monkeypatch):
    """client=None 自建 httpx.AsyncClient, 成功响应后 finally aclose (生产真实路径)。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    fake = _ClosableFakeClient(status_code=200, payload={"code": 0})
    monkeypatch.setattr(cp.httpx, "AsyncClient", lambda **kw: fake)
    resp = await cp._post_with_retry(None, "https://x", {"k": "v"}, {}, backoff=0)
    assert resp.status_code == 200
    assert len(fake.calls) == 1
    assert fake.close_tracked is True  # finally 关闭


async def test_post_with_retry_own_client_closed_on_exhaustion(monkeypatch):
    """自建 client 在 5xx 重试耗尽抛异常后也被 aclose。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    fake = _ClosableFakeClient(status_code=503)
    monkeypatch.setattr(cp.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(RuntimeError, match="http 503"):
        await cp._post_with_retry(None, "https://x", {}, {}, max_retries=1, backoff=0)
    assert len(fake.calls) == 2  # 1 + 1 重试
    assert fake.close_tracked is True


async def test_post_with_retry_own_client_closed_on_network_exc(monkeypatch):
    """自建 client 在网络异常重试耗尽后也被 aclose。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    fake = _ClosableFakeClient(exc=ConnectionError("dns fail"))
    monkeypatch.setattr(cp.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ConnectionError, match="dns fail"):
        await cp._post_with_retry(None, "https://x", {}, {}, max_retries=0, backoff=0)
    assert fake.close_tracked is True


async def test_send_im_own_client_path(monkeypatch):
    """send_channel('im') 不传 client → 子渠道自建 client, sent 路径。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    fake = _ClosableFakeClient(status_code=200, payload={"code": 0})
    monkeypatch.setattr(cp.httpx, "AsyncClient", lambda **kw: fake)
    out = await cp.send_channel(
        "im", {"webhook_url": "https://hook"}, "hi", backoff=0,
    )
    assert out == {"status": "sent", "channel": "im"}
    assert len(fake.calls) == 1
    assert fake.close_tracked is True


async def test_send_channel_wecom_skipped_no_url():
    """wecom 经 send_channel 入口缺 webhook_url → skipped。"""
    out = await cp.send_channel("wecom", {}, "hi")
    assert out == {"status": "skipped", "channel": "wecom", "reason": "no webhook_url"}


async def test_send_channel_webhook_skipped_no_url():
    """webhook 经 send_channel 入口缺 webhook_url → skipped。"""
    out = await cp.send_channel("webhook", {}, "hi", subject="s")
    assert out == {"status": "skipped", "channel": "webhook", "reason": "no webhook_url"}


async def test_send_wecom_json_exception_returns_failed(monkeypatch):
    """wecom 响应 resp.json() 抛异常 → body={} → errcode 缺失 → failed。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(status_code=200)
    # 让 resp.json() 抛
    client._resp_fn = lambda url, json, headers: MagicMock(
        status_code=200, **{"json.side_effect": ValueError("bad")})
    out = await cp.send_channel(
        "wecom", {"webhook_url": "https://h"}, "hi", client=client, backoff=0,
    )
    assert out["status"] == "failed"
    assert out["channel"] == "wecom"


def test_send_voice_channel_via_send_channel():
    """voice 经 send_channel 入口 → _send_voice (mock provider) → sent。

    voice 是同步分支 (非 HTTP), send_channel 直接 return _send_voice 结果,
    用 asyncio.run 驱动 send_channel 协程。"""
    out = asyncio.run(cp.send_channel(
        "voice", {"sign_name": "s"}, "msg", receiver={"phone": "13900000000"},
    ))
    assert out == {"status": "sent", "channel": "voice",
                   "provider": "mock", "phone": "13900000000"}


def test_send_sms_channel_via_send_channel():
    """sms 经 send_channel 入口 → _send_sms (mock provider) → sent。"""
    out = asyncio.run(cp.send_channel(
        "sms", {"sign_name": "s"}, "msg", receiver={"phone": "13800000000"},
    ))
    assert out == {"status": "sent", "channel": "sms",
                   "provider": "mock", "phone": "13800000000"}


async def test_send_wecom_exception_returns_failed(monkeypatch):
    """_send_wecom 内 _post_with_retry 重试耗尽抛 → 子渠道 except 兜底 failed 不抛。

    覆盖 channel_providers.py L146-147 (wecom 的 except 分支)。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(exc=ConnectionError("wecom net down"))
    out = await cp.send_channel(
        "wecom", {"webhook_url": "https://h"}, "hi", client=client,
        max_retries=1, backoff=0,
    )
    assert out["status"] == "failed"
    assert out["channel"] == "wecom"
    assert "wecom net down" in out["error"]


async def test_send_webhook_exception_returns_failed(monkeypatch):
    """_send_webhook 内 _post_with_retry 重试耗尽抛 → 子渠道 except 兜底 failed。

    覆盖 channel_providers.py L168-169 (webhook 的 except 分支)。"""
    monkeypatch.setattr(cp.asyncio, "sleep", _noop_sleep)
    client = FakeClient(exc=ConnectionError("webhook net down"))
    out = await cp.send_channel(
        "webhook", {"webhook_url": "https://h"}, "hi", subject="s",
        client=client, max_retries=1, backoff=0,
    )
    assert out["status"] == "failed"
    assert out["channel"] == "webhook"
    assert "webhook net down" in out["error"]
