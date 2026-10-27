"""PII 日志脱敏回归测试 (卡 d6303b65-9219-43f6-a9f7-e27bb177edbd)

此前卡 d9e74956 只修了 notification_dispatcher 的 mock 分发分支, 真实触达渠道层
(channel_providers / wx_subscribe_msg / invoice_notification) 仍有裸 PII 进日志。

本文件用 caplog 断言: 脱敏后的日志中不出现完整手机号 / 完整 openid / 完整邮箱,
且业务返回结构不受影响 (只改日志参数, 不改逻辑)。
"""
import logging
import re

import pytest

from app.services import channel_providers as cp
from app.services import invoice_notification as inv
from app.services import wx_subscribe_msg as wxs

# 完整中国手机号 (与 sanitize_for_log 同款模式)
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
OPENID = "oXb1xUserOPENIDsecret28chars0"
PHONE = "13812345678"
EMAIL = "dage@example.com"


def _records_text(caplog) -> str:
    return caplog.text


@pytest.fixture(autouse=True)
def _caplog_all_levels(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


# ─── channel_providers ───────────────────────────────────────────────────────

class TestSmsVoiceMask:
    def test_sms_stub_log_masks_phone(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.services.channel_providers"):
            cp._CloudProviderSmsProvider().send(PHONE, "内容", {})
        text = _records_text(caplog)
        assert "138****5678" in text
        assert not _PHONE_RE.search(text)

    def test_voice_stub_log_masks_phone(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.services.channel_providers"):
            cp._CloudProviderVoiceProvider().send(PHONE, "内容", {})
        text = _records_text(caplog)
        assert "138****5678" in text
        assert not _PHONE_RE.search(text)

    def test_provider_result_error_log_masks_phone(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.services.channel_providers"):
            result = cp._provider_result("sms", PHONE, None, exc=RuntimeError("boom"))
        assert result["phone"] == PHONE  # 返回结构不脱敏, 仅日志脱敏
        assert not _PHONE_RE.search(_records_text(caplog))

    def test_email_mock_log_masks_email(self, caplog):
        with caplog.at_level(logging.INFO, logger="app.services.channel_providers"):
            cp._send_email_mock({}, "body", {"email": EMAIL}, "subj")
        text = _records_text(caplog)
        assert EMAIL not in text
        assert "d***e@example.com" in text


class TestWxSubscribeChannelMask:
    def test_send_wx_subscribe_exception_masks_openid(self, caplog):
        async def _boom(**kw):
            raise RuntimeError("net down")

        import unittest.mock as mock
        with mock.patch.object(wxs, "send_subscribe_msg", _boom), \
             caplog.at_level(logging.ERROR, logger="app.services.channel_providers"):
            result = cp._run_sync(cp._send_wx_subscribe(
                {"openid": OPENID, "template_id": "TPL"}, None, client=None))
        assert result["status"] == "failed"
        text = _records_text(caplog)
        assert OPENID not in text
        assert OPENID[:4] in text  # 前4位可见


# ─── wx_subscribe_msg ────────────────────────────────────────────────────────

class TestWxSubscribeMsgMask:
    def test_no_credentials_log_masks_openid(self, caplog, monkeypatch):
        monkeypatch.setattr(wxs.settings, "WX_MP_APPID", "", raising=False)
        with caplog.at_level(logging.INFO, logger="app.services.wx_subscribe_msg"):
            import asyncio
            result = asyncio.run(wxs.send_subscribe_msg(
                openid=OPENID, template_id="TPL", data={}))
        assert result["reason"] == "no_credentials"
        text = _records_text(caplog)
        assert OPENID not in text
        assert OPENID[:4] in text


# ─── invoice_notification ────────────────────────────────────────────────────

class _FakeInvoice:
    id = 42
    user_id = 7
    amount = 1000
    title_name = "t"


class TestInvoiceNotificationMask:
    def test_resolve_device_targets_error_masks_openid(self, caplog):
        class _RaisingQuery:
            def __getattr__(self, name):
                raise RuntimeError("db down")

        with caplog.at_level(logging.WARNING, logger="app.services.invoice_notification"):
            result = inv.resolve_device_targets(_RaisingQuery(), OPENID)
        assert result == []
        text = _records_text(caplog)
        assert OPENID not in text


# ─── auth 短信验证码日志脱敏 (卡 31e9390f) ────────────────────────────────────

class AuthSmsCodeLogMask:
    """auth.py 两条发送验证码路径: 裸 code / 完整手机号不进日志, 仅遮蔽手机号+purpose。"""

    def test_create_sms_code_helper_masks_phone_and_code(self, caplog, db_session):
        from app.api.v1 import auth as auth_mod
        with caplog.at_level(logging.INFO, logger="app.api.v1.auth"):
            code = auth_mod._create_sms_code(db_session, PHONE, "login")
        assert re.fullmatch(r"\d{6}", code)
        text = _records_text(caplog)
        assert code not in text  # 验证码不进日志
        assert not _PHONE_RE.search(text)  # 完整手机号不进日志
        assert "138****5678" in text  # 遮蔽形态保留

    def test_send_sms_endpoint_masks_phone_and_code(self, caplog, client):
        with caplog.at_level(logging.INFO, logger="app.api.v1.auth"):
            r = client.post("/api/v1/auth/sms/send", json={"phone": PHONE, "purpose": "login"})
        assert r.status_code == 200  # 业务返回不受影响
        text = _records_text(caplog)
        assert not _PHONE_RE.search(text)
        assert "138****5678" in text
        assert "(purpose: login)" in text


# pytest 收集兼容: 以 Test* 暴露给 runner
TestAuthSmsCodeLogMask = AuthSmsCodeLogMask
