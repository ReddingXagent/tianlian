"""真实渠道发送单元测试 (卡 8d98ebe3)

被测模块: app/services/channel_providers.py
- im HMAC-SHA256 签名 + markdown POST
- wecom markdown POST
- webhook JSON POST
- sms/voice Provider ABC + mock 实现 (未报备)
- httpx 超时5s + 失败重试2次 (指数退避)
- 配置缺失/enabled=False/凭证缺失 → 跳过 (INFO)

httpx 用注入式 FakeClient 模拟 (项目无 respx)。
"""
import asyncio
import base64

import pytest

from app.services import channel_providers as cp
from app.services.channel_providers import (
    im_sign,
    send_channel,
    dispatch_real_channel,
    get_sms_provider,
    get_voice_provider,
    SmsProvider,
    VoiceProvider,
)
from app.models.channel_config import ChannelConfig, ChannelType


# ========== Fake httpx client ==========

class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class FakeClient:
    """按顺序返回预设响应 (FakeResponse 或 Exception)。记录所有 post 调用。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# ========== im_sign ==========

def test_im_sign_is_deterministic():
    a = im_sign(1599360473, "test-secret")
    b = im_sign(1599360473, "test-secret")
    assert a == b


def test_im_sign_changes_with_inputs():
    assert im_sign(1, "a") != im_sign(2, "a")
    assert im_sign(1, "a") != im_sign(1, "b")


def test_im_sign_is_base64_sha256():
    # HMAC-SHA256 → 32 字节 → base64 编码
    sign = im_sign(1599360473, "test-secret")
    raw = base64.b64decode(sign)
    assert len(raw) == 32


# ========== send_channel: im ==========

async def test_send_im_signs_payload_when_secret(monkeypatch):
    monkeypatch.setattr(cp.time, "time", lambda: 1700000000)
    client = FakeClient([FakeResponse(200, {"code": 0, "msg": "ok"})])
    result = await send_channel("im", {
        "webhook_url": "https://open.im.cn/hook/x", "secret": "s3cr3t",
    }, "hello", client=client, backoff=0)
    assert result["status"] == "sent"
    payload = client.calls[0]["json"]
    assert payload["timestamp"] == "1700000000"
    assert payload["sign"] == im_sign(1700000000, "s3cr3t")
    # markdown 消息体
    assert payload["msg_type"] in ("text", "interactive", "markdown")


async def test_send_im_no_secret_omits_sign():
    client = FakeClient([FakeResponse(200, {"code": 0})])
    await send_channel("im", {"webhook_url": "https://h"}, "hi", client=client, backoff=0)
    payload = client.calls[0]["json"]
    assert "sign" not in payload
    assert "timestamp" not in payload


async def test_send_im_accepts_statuscode_zero():
    # IM旧版返回 StatusCode: 0
    client = FakeClient([FakeResponse(200, {"StatusCode": 0})])
    result = await send_channel("im", {"webhook_url": "https://h"}, "hi",
                                client=client, backoff=0)
    assert result["status"] == "sent"


async def test_send_im_business_error_marks_failed():
    client = FakeClient([FakeResponse(200, {"code": 19021, "msg": "invalid sign"})])
    result = await send_channel("im", {"webhook_url": "https://h", "secret": "s"},
                                "hi", client=client, backoff=0)
    assert result["status"] == "failed"


# ========== send_channel: wecom / webhook ==========

async def test_send_wecom_success():
    client = FakeClient([FakeResponse(200, {"errcode": 0, "errmsg": "ok"})])
    result = await send_channel("wecom", {"webhook_url": "https://qy/hook"},
                                "msg", client=client, backoff=0)
    assert result["status"] == "sent"
    payload = client.calls[0]["json"]
    assert payload["msgtype"] in ("markdown", "text")


async def test_send_webhook_success():
    client = FakeClient([FakeResponse(200)])  # 2xx 即成功
    result = await send_channel("webhook", {"webhook_url": "https://ex/hook"},
                                "msg", subject="subj", client=client, backoff=0)
    assert result["status"] == "sent"
    payload = client.calls[0]["json"]
    assert "msg" in payload["text"] or payload["text"] == "msg"


# ========== retry / timeout ==========

async def test_retry_then_success_on_server_error(monkeypatch):
    # 500, 500, 200 → 重试两次后成功
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(cp.asyncio, "sleep", fake_sleep)
    client = FakeClient([
        FakeResponse(500), FakeResponse(500), FakeResponse(200, {"code": 0})
    ])
    result = await send_channel("im", {"webhook_url": "https://h"}, "hi",
                                client=client, max_retries=2, backoff=0.1)
    assert result["status"] == "sent"
    assert len(client.calls) == 3
    assert len(sleeps) == 2          # 两次重试各退避一次
    assert sleeps == [0.1, 0.2]       # 指数退避


async def test_retry_exhausted_returns_failed(monkeypatch):
    async def noop(s):
        return None
    monkeypatch.setattr(cp.asyncio, "sleep", noop)
    client = FakeClient([FakeResponse(500)] * 3)  # 一直 500
    result = await send_channel("im", {"webhook_url": "https://h"}, "hi",
                                client=client, max_retries=2, backoff=0)
    assert result["status"] == "failed"
    assert len(client.calls) == 3     # 初次 + 2 重试


async def test_timeout_retried_then_failed(monkeypatch):
    import httpx

    async def noop(s):
        return None
    monkeypatch.setattr(cp.asyncio, "sleep", noop)
    client = FakeClient([httpx.TimeoutException("slow")] * 3)
    result = await send_channel("webhook", {"webhook_url": "https://h"}, "hi",
                                client=client, max_retries=2, backoff=0)
    assert result["status"] == "failed"
    assert "slow" in result["error"]


async def test_no_retry_on_4xx(monkeypatch):
    # 4xx 客户端错误不重试
    client = FakeClient([FakeResponse(400)])
    result = await send_channel("webhook", {"webhook_url": "https://h"}, "hi",
                                client=client, max_retries=2, backoff=0)
    assert result["status"] == "failed"
    assert len(client.calls) == 1


# ========== sms / voice Provider ==========

def test_sms_provider_abc_and_mock():
    provider = get_sms_provider({})
    assert isinstance(provider, SmsProvider)
    result = provider.send("13800000000", "hi", {"sign_name": "天链", "template_code": "T1"})
    # 未报备 → mock log, 返回 sent/mock
    assert result["status"] in ("sent", "mock")
    assert "provider" in result


def test_voice_provider_abc_and_mock():
    provider = get_voice_provider({})
    assert isinstance(provider, VoiceProvider)
    result = provider.send("13800000000", "hi", {"voice_caller": "4001"})
    assert result["status"] in ("sent", "mock")


async def test_send_channel_sms_uses_provider(monkeypatch):
    sent = []

    class StubSms(SmsProvider):
        def send(self, phone, content, config):
            sent.append((phone, content))
            return {"status": "sent", "provider": "stub"}

    monkeypatch.setattr(cp, "get_sms_provider", lambda config: StubSms())
    result = await send_channel("sms", {"sms_access_key": "AK"}, "hello",
                                receiver={"phone": "13900000000"})
    assert result["status"] == "sent"
    assert sent == [("13900000000", "hello")]


# ========== dispatch_real_channel (ChannelConfig 查询 + 跳过) ==========

def test_dispatch_no_channel_config_skipped(test_db):
    db = test_db["session"]
    result = dispatch_real_channel("im", team_id=99, db=db,
                                   receiver={}, content="hi", subject=None)
    assert result["status"] == "skipped"
    assert "no_config" in result["reason"] or "配置" in result.get("reason", "")


def test_dispatch_disabled_config_skipped(test_db):
    db = test_db["session"]
    db.add(ChannelConfig(team_id=5, channel=ChannelType.IM,
                         config={"webhook_url": "https://h"}, enabled=False))
    db.commit()
    result = dispatch_real_channel("im", team_id=5, db=db,
                                   receiver={}, content="hi", subject=None)
    assert result["status"] == "skipped"


def test_dispatch_missing_webhook_url_skipped(test_db):
    db = test_db["session"]
    db.add(ChannelConfig(team_id=5, channel=ChannelType.IM,
                         config={}, enabled=True))  # 无 webhook_url
    db.commit()
    result = dispatch_real_channel("im", team_id=5, db=db,
                                   receiver={}, content="hi", subject=None)
    assert result["status"] == "skipped"


def test_dispatch_real_send_uses_channel_config(test_db, monkeypatch):
    db = test_db["session"]
    db.add(ChannelConfig(team_id=7, channel=ChannelType.WEBHOOK,
                         config={"webhook_url": "https://h"}, enabled=True))
    db.commit()
    monkeypatch.setattr(cp.asyncio, "sleep", lambda s: asyncio.sleep(0))

    async def fake_send(channel, config, content, subject=None, receiver=None, **kw):
        assert channel == "webhook"
        assert config["webhook_url"] == "https://h"
        return {"status": "sent", "channel": channel}

    monkeypatch.setattr(cp, "send_channel", fake_send)
    result = dispatch_real_channel("webhook", team_id=7, db=db,
                                   receiver={}, content="hi", subject=None)
    assert result["status"] == "sent"


def test_dispatch_sms_via_provider(test_db, monkeypatch):
    db = test_db["session"]
    db.add(ChannelConfig(team_id=7, channel=ChannelType.SMS,
                         config={"sms_access_key": "AK", "sign_name": "天链"}, enabled=True))
    db.commit()
    result = dispatch_real_channel("sms", team_id=7, db=db,
                                   receiver={"phone": "13800000000"}, content="hi", subject=None)
    assert result["status"] == "sent"


# ========== _dispatch_channel 双路径接线 (notification_sender ↔ channel_providers) ==========

def _fake_send_factory(status="sent", error="boom"):
    async def fake_send(channel, config, content, subject=None, receiver=None, **kw):
        return {"status": status, "channel": channel,
                "error": error if status == "failed" else None}
    return fake_send


def test_dispatch_channel_real_path_when_team_id_and_config(test_db, monkeypatch):
    """team_id + ChannelConfig → 真实路径 (send_channel), legacy dispatcher 不触达。"""
    from unittest.mock import MagicMock
    from app.services.notification_sender import NotificationSender

    db = test_db["session"]
    db.add(ChannelConfig(team_id=3, channel=ChannelType.IM,
                         config={"webhook_url": "https://h"}, enabled=True))
    db.commit()
    monkeypatch.setattr(cp, "send_channel", _fake_send_factory("sent"))
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    sender._dispatch_channel("im", {}, "msg", None, {}, db=db, team_id=3)
    sender._dispatcher.notify_im.assert_not_called()


def test_dispatch_channel_legacy_when_no_team_id():
    """无 db/team_id (含既有 145 测试) → legacy mock dispatcher, 行为不变。"""
    from unittest.mock import MagicMock
    from app.services.notification_sender import NotificationSender

    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    sender._dispatch_channel("im", {}, "msg", None, {})
    sender._dispatcher.notify_im.assert_called_once()


def test_dispatch_channel_skipped_when_team_id_but_no_config(test_db):
    """team_id 给定但无 ChannelConfig → skipped, 不走 legacy, 不抛。"""
    from unittest.mock import MagicMock
    from app.services.notification_sender import NotificationSender

    db = test_db["session"]
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    sender._dispatch_channel("im", {}, "msg", None, {}, db=db, team_id=999)
    sender._dispatcher.notify_im.assert_not_called()


def test_dispatch_channel_real_failed_raises(test_db, monkeypatch):
    """真实路径最终失败 → 抛 RuntimeError, 由 send() 落 failed 日志。"""
    from unittest.mock import MagicMock
    from app.services.notification_sender import NotificationSender

    db = test_db["session"]
    db.add(ChannelConfig(team_id=3, channel=ChannelType.WEBHOOK,
                         config={"webhook_url": "https://h"}, enabled=True))
    db.commit()
    monkeypatch.setattr(cp, "send_channel", _fake_send_factory("failed"))
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    with pytest.raises(RuntimeError):
        sender._dispatch_channel("webhook", {}, "msg", None, {}, db=db, team_id=3)
