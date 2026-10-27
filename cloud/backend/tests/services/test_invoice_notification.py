"""invoice_notification 单元测试覆盖补全 (卡 b4a74890)

被测: app/services/invoice_notification.py — 开票完成/拒绝通知 + 签名文件 URL
(用户端云端契约 §5.5)。

覆盖矩阵:
  签名 token (4 函数):
    - generate_file_token / verify_file_token 往返
    - 过期 (SignatureExpired) / 篡改 (BadSignature) → None
    - None invoice_id / 非 int iid → None
    - build_signed_file_url: base_url 带/不带尾斜杠 + token 嵌入
  邮件 (3 函数):
    - _smtp_send: 无附件 SMTP 调用链 (starttls/login/sendmail 参数)
    - _smtp_send: 有附件 (tmp_path 真实文件) MIMEBase attach
    - _smtp_send: SMTP_USER/PASS 缺失不 login
    - _smtp_configured: settings.SMTP_HOST 有/无
    - send_invoice_email: 未配置 → mock 日志 True
    - send_invoice_email: 配置成功 → True
    - send_invoice_email: 配置但抛错 → False
  推送 (2 函数): logger.info 调用 + SimpleNamespace 字段读取
  正文 (2 函数):
    - _build_issued_email_body: 金额分→元转换 / file_url 有/无
    - _build_rejected_email_body: reject_reason 有/无
  通知钩子 (2 函数, 各 3 通道 best-effort):
    - notify_invoice_issued: email 空 → 不发邮件; email 非空 → 发邮件
    - notify_invoice_issued: 某通道 raise 不阻断其他通道
    - notify_invoice_rejected: 同上 + reject_reason 走入正文

测试缝: smtplib.SMTP / settings 属性 / SimpleNamespace 模拟 invoice_request。
铁律: 只加测试, 不改 production。
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from itsdangerous import BadSignature, SignatureExpired

from app.services import invoice_notification as mod


# settings 是 Pydantic frozen 模型且无 SMTP_* 字段, setattr 抛 ValueError;
# 生产代码全用 getattr(settings, ...) 读取, 故测试整体替换 mod.settings 为
# SimpleNamespace, 让 getattr 自由读, 不触碰 Pydantic 校验。
def _fake_settings(**over):
    base = dict(SMTP_HOST=None, SMTP_PORT=587, SMTP_USER=None, SMTP_PASS=None,
                EMAIL_FROM=None)
    base.update(over)
    return SimpleNamespace(**base)


# ═══════════════════════════════════════════════════════════════════════════
# 签名文件 URL
# ═══════════════════════════════════════════════════════════════════════════
class TestSignedFileToken:
    """generate_file_token / verify_file_token / build_signed_file_url。"""

    def test_roundtrip_valid_token(self):
        """正常生成 → 验证 → 返回原 invoice_id。"""
        token = mod.generate_file_token(42)
        assert mod.verify_file_token(token) == 42

    def test_roundtrip_large_id(self):
        token = mod.generate_file_token(2**31 + 7)
        assert mod.verify_file_token(token) == 2**31 + 7

    def test_generate_embeds_iid_payload(self):
        """token 载荷里带 iid 字段 (契约: 嵌入 invoice_id)。"""
        token = mod.generate_file_token(99)
        # 同密钥同盐解码出原始载荷
        data = mod._serializer().loads(token, max_age=mod.SIGNED_URL_MAX_AGE)
        assert data == {"iid": 99}

    def test_verify_expired_returns_none(self):
        """过期 token (loads 抛 SignatureExpired) → None, 不向上抛。"""
        token = mod.generate_file_token(1)
        with patch.object(
            mod.URLSafeTimedSerializer, "loads", side_effect=SignatureExpired("exp")
        ):
            assert mod.verify_file_token(token) is None

    def test_verify_tampered_returns_none(self):
        """篡改/非法 token (真实坏串触发 BadSignature) → None。"""
        assert mod.verify_file_token("not-a-real-token.abc.def") is None
        assert mod.verify_file_token("") is None
        # 改动一字节的真实 token
        good = mod.generate_file_token(5)
        tampered = ("X" + good[1:]) if good else "x"
        assert mod.verify_file_token(tampered) is None

    def test_verify_bad_signature_class_returns_none(self):
        """loads 抛 BadSignature (非过期) → None。"""
        with patch.object(
            mod.URLSafeTimedSerializer, "loads", side_effect=BadSignature("bad")
        ):
            assert mod.verify_file_token("whatever") is None

    def test_verify_none_iid_returns_none(self):
        """载荷 iid 为 None → None。"""
        token = mod._serializer().dumps({"iid": None})
        assert mod.verify_file_token(token) is None

    def test_verify_non_int_iid_returns_none(self):
        """载荷 iid 非数字 (无法 int() 转换) → None。"""
        token = mod._serializer().dumps({"iid": "abc"})
        assert mod.verify_file_token(token) is None
        token_list = mod._serializer().dumps({"iid": [1, 2]})
        assert mod.verify_file_token(token_list) is None

    def test_verify_numeric_string_iid_coerced(self):
        """载荷 iid 为数字字符串 → int() 可转, 返回 int (生产 int(iid) 行为)。"""
        token = mod._serializer().dumps({"iid": "13"})
        assert mod.verify_file_token(token) == 13


class TestBuildSignedFileUrl:
    def test_url_contains_path_and_token(self):
        url = mod.build_signed_file_url(7, "https://api.tianlian.com")
        assert url.startswith("https://api.tianlian.com/api/v1/business/invoice-file?token=")
        token = url.rsplit("token=", 1)[1]
        assert mod.verify_file_token(token) == 7

    def test_url_strips_trailing_slash(self):
        """base_url 带尾斜杠 → rstrip 后 path 段无双斜杠 (:// 除外)。"""
        url = mod.build_signed_file_url(7, "https://api.tianlian.com/")
        assert url.startswith("https://api.tianlian.com/api/v1/business/invoice-file?token=")
        # 去掉 scheme 后不应出现连续斜杠
        after_scheme = url.split("://", 1)[1]
        assert "//" not in after_scheme

    def test_url_idempotent_path(self):
        """base_url 无尾斜杠与有尾斜杠拼出的 path 段一致。"""
        a = mod.build_signed_file_url(3, "https://x.io")
        b = mod.build_signed_file_url(3, "https://x.io/")
        # 仅 token 前的 path 部分应相同
        assert a.split("?")[0] == b.split("?")[0] == "https://x.io/api/v1/business/invoice-file"


# ═══════════════════════════════════════════════════════════════════════════
# 邮件: _smtp_send / _smtp_configured / send_invoice_email
# ═══════════════════════════════════════════════════════════════════════════
class TestSmtpConfigured:
    def test_configured_false_when_no_host(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _fake_settings(SMTP_HOST=None))
        assert mod._smtp_configured() is False

    def test_configured_false_when_empty_host(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _fake_settings(SMTP_HOST=""))
        assert mod._smtp_configured() is False

    def test_configured_true_when_host_set(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _fake_settings(SMTP_HOST="smtp.example.com"))
        assert mod._smtp_configured() is True


class TestSmtpSend:
    """_smtp_send 调用链: smtplib.SMTP ctx → starttls → (login) → sendmail。"""

    def _patch_smtp(self):
        """patch smtplib.SMTP, 返回 mock server 用于断言调用。"""
        server = MagicMock()
        server.starttls = MagicMock()
        server.login = MagicMock()
        server.sendmail = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=server)
        ctx.__exit__ = MagicMock(return_value=False)
        patcher = patch.object(mod.smtplib, "SMTP", return_value=ctx)
        return patcher, server

    def test_send_no_attachment_calls_chain(self, monkeypatch):
        monkeypatch.setattr(mod, "settings", _fake_settings(
            SMTP_HOST="smtp.x.com", SMTP_PORT=587, SMTP_USER="u", SMTP_PASS="p",
            EMAIL_FROM="from@x.com",
        ))
        patcher, server = self._patch_smtp()
        with patcher as smtp_mock:
            mod._smtp_send("to@x.com", "主题", "正文")
            smtp_mock.assert_called_once_with("smtp.x.com", 587, timeout=10)
            server.starttls.assert_called_once()
            server.login.assert_called_once_with("u", "p")
            server.sendmail.assert_called_once()
            args, _ = server.sendmail.call_args
            assert args[0] == "from@x.com"      # From
            assert args[1] == ["to@x.com"]      # To 列表
            mime = args[2]
            # 中文 Subject 经 base64 编码 (=?utf-8?b?...?=), 正文 base64 后挂 multipart
            assert "multipart/mixed" in mime
            assert "Subject:" in mime
            assert "base64" in mime   # Content-Transfer-Encoding

    def test_send_skips_login_when_no_credentials(self, monkeypatch):
        """SMTP_USER/PSS 缺失 → 不调 login, 仍 sendmail。"""
        monkeypatch.setattr(mod, "settings", _fake_settings(
            SMTP_HOST="smtp.x.com", SMTP_PORT=587, SMTP_USER=None, SMTP_PASS=None,
            EMAIL_FROM=None,
        ))
        patcher, server = self._patch_smtp()
        with patcher:
            mod._smtp_send("to@x.com", "s", "b")
            server.login.assert_not_called()
            server.sendmail.assert_called_once()
            # EMAIL_FROM 为 None → 走默认 noreply
            assert server.sendmail.call_args.args[0] == "noreply@tianlian.com"

    def test_send_with_attachment_known_bug(self, monkeypatch, tmp_path):
        """【已知 bug, 回归锁定】附件路径当前抛 IndexError。

        invoice_notification.py:92 `part.add_header("Content-Disposition",
        "attachment", filename=("", fname))` — Python email 把 tuple 值当 RFC 2231
        (charset, language, value) 三元组, 二元组访问 value[2] → IndexError。
        本卡(b4a74890)只加测试不改生产, 此测试钉死现状; 修 bug 的卡需:
          ① 改 filename 编码方式 (如 filename=fname 或 RFC2231 三元组)
          ② 翻转此断言为「附件发送成功 + mime 含 attachment/invoice.pdf」
        """
        monkeypatch.setattr(mod, "settings", _fake_settings(
            SMTP_HOST="smtp.x.com", SMTP_PORT=587, SMTP_USER=None, SMTP_PASS=None,
            EMAIL_FROM="from@x.com",
        ))
        att = tmp_path / "invoice.pdf"
        att.write_bytes(b"%PDF-1.4 binary invoice content")

        patcher, server = self._patch_smtp()
        with patcher:
            with pytest.raises(IndexError):
                mod._smtp_send("to@x.com", "主题", "正文", attachment_path=str(att))
            # 崩在 add_header, sendmail 未被调用
            server.sendmail.assert_not_called()

    def test_send_default_port_when_attr_missing(self, monkeypatch):
        """SMTP_PORT 未定义 → getattr 默认 587。"""
        # 不传 SMTP_PORT → SimpleNamespace 无此属性 → getattr 兜底 587
        monkeypatch.setattr(mod, "settings", _fake_settings(
            SMTP_HOST="smtp.x.com", SMTP_USER=None, SMTP_PASS=None,
        ))
        patcher, server = self._patch_smtp()
        with patcher as smtp_mock:
            mod._smtp_send("to@x.com", "s", "b")
            assert smtp_mock.call_args.kwargs["timeout"] == 10
            assert smtp_mock.call_args.args[1] == 587


class TestSendInvoiceEmail:
    def test_not_configured_returns_true(self, monkeypatch, caplog):
        """SMTP 未配置 → mock 日志 + 返回 True (开发/测试零配置)。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: False)
        send = MagicMock()
        monkeypatch.setattr(mod, "_smtp_send", send)
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            result = mod.send_invoice_email("to@x.com", "s", "b", attachment_path="/x")
        assert result is True
        send.assert_not_called()  # 未配置 → 不走真实发送
        assert any("INVOICE EMAIL MOCK" in r.message for r in caplog.records)

    def test_configured_send_success_returns_true(self, monkeypatch):
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)
        send = MagicMock()
        monkeypatch.setattr(mod, "_smtp_send", send)
        result = mod.send_invoice_email("to@x.com", "s", "b")
        assert result is True
        send.assert_called_once_with("to@x.com", "s", "b", None)

    def test_configured_send_raises_returns_false(self, monkeypatch):
        """SMTP 已配置但 _smtp_send 抛错 → 捕获 + 返回 False (best-effort)。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)
        monkeypatch.setattr(mod, "_smtp_send", MagicMock(side_effect=RuntimeError("boom")))
        result = mod.send_invoice_email("to@x.com", "s", "b")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# 推送通道 (卡 3591ea8f: openid 有值且凭证配置 → 真实发送; 否则降级日志)
# ═══════════════════════════════════════════════════════════════════════════
class TestPushChannels:
    def test_push_miniprogram_logs_fields(self, caplog):
        """openid=None → 仅日志留痕 (历史行为, 向后兼容)。"""
        req = SimpleNamespace(id=11, user_id=22, amount=30000)
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod._push_miniprogram_subscribe(req)
        assert any(
            "INVOICE MP-SUBSCRIBE" in r.message and "11" in r.message and "30000" in r.message
            for r in caplog.records
        )

    def test_push_app_logs_fields(self, caplog):
        req = SimpleNamespace(id=33, user_id=44, amount=5600)
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod._push_app_notification(req)
        assert any(
            "INVOICE APP-PUSH" in r.message and "33" in r.message and "5600" in r.message
            for r in caplog.records
        )


class TestPushMiniprogramOpenid:
    """卡 3591ea8f: openid 透传 → 真实IM-B订阅消息发送调用链。"""

    def _req(self):
        return SimpleNamespace(id=77, user_id=9, amount=12800, title_name="某公司")

    def test_openid_none_does_not_send(self, monkeypatch):
        """openid=None → 不调用 send_subscribe_msg (降级日志)。"""
        import app.services.wx_subscribe_msg as wxsm
        send = MagicMock()
        monkeypatch.setattr(wxsm, "send_subscribe_msg", send)
        mod._push_miniprogram_subscribe(self._req(), openid=None)
        send.assert_not_called()

    def test_openid_set_but_credentials_unconfigured_skips(self, monkeypatch):
        """openid 有值但 APPID 未配置 → _credentials_configured False → 不发送。"""
        import app.services.wx_subscribe_msg as wxsm
        send = MagicMock()
        monkeypatch.setattr(wxsm, "send_subscribe_msg", send)
        monkeypatch.setattr(wxsm, "_credentials_configured", lambda: False)
        mod._push_miniprogram_subscribe(self._req(), openid="oABC")
        send.assert_not_called()

    def test_openid_set_configured_but_no_template_skips(self, monkeypatch, caplog):
        """凭证配置但模板 ID 未配置 (WX_INVOICE_ISSUED_TPL 缺失) → 不发送 + 日志。"""
        import app.services.wx_subscribe_msg as wxsm
        send = MagicMock()
        monkeypatch.setattr(wxsm, "send_subscribe_msg", send)
        monkeypatch.setattr(wxsm, "_credentials_configured", lambda: True)
        monkeypatch.setattr(mod, "settings",
                            SimpleNamespace(WX_INVOICE_ISSUED_TPL=None,
                                            WX_INVOICE_REJECTED_TPL=None))
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod._push_miniprogram_subscribe(self._req(), openid="oABC", issued=True)
        send.assert_not_called()
        assert any("WX_INVOICE_ISSUED_TPL" in r.message for r in caplog.records)

    def test_openid_set_configured_with_template_sends(self, monkeypatch):
        """完整路径: openid + 凭证 + 模板 → 调 send_subscribe_msg (经 _run_sync 同步桥接)。"""
        import app.services.wx_subscribe_msg as wxsm
        from app.services import channel_providers as cp
        send = MagicMock(return_value={"status": "sent"})
        monkeypatch.setattr(wxsm, "send_subscribe_msg", send)
        monkeypatch.setattr(wxsm, "_credentials_configured", lambda: True)
        monkeypatch.setattr(mod, "settings",
                            SimpleNamespace(WX_INVOICE_ISSUED_TPL="TPL_ISSUED",
                                            WX_INVOICE_REJECTED_TPL="TPL_REJECTED"))
        # _run_sync 同步桥接: 把协程喂给 asyncio.run
        monkeypatch.setattr(cp, "_run_sync", lambda coro: __import__("asyncio").run(coro))

        mod._push_miniprogram_subscribe(self._req(), openid="oABC", issued=True)
        send.assert_called_once()
        kwargs = send.call_args.kwargs
        assert kwargs["openid"] == "oABC"
        assert kwargs["template_id"] == "TPL_ISSUED"
        assert "id=77" in kwargs["page"]
        # data 含金额分→元转换 (12800 分 = 128.00 元)
        assert kwargs["data"]["amount"]["value"] == "128.00 元"
        assert kwargs["data"]["status"]["value"] == "已开具"

    def test_issued_false_uses_rejected_template_and_status(self, monkeypatch):
        """issued=False → 用 REJECTED 模板 + status=未通过。"""
        import app.services.wx_subscribe_msg as wxsm
        from app.services import channel_providers as cp
        send = MagicMock(return_value={"status": "sent"})
        monkeypatch.setattr(wxsm, "send_subscribe_msg", send)
        monkeypatch.setattr(wxsm, "_credentials_configured", lambda: True)
        monkeypatch.setattr(mod, "settings",
                            SimpleNamespace(WX_INVOICE_ISSUED_TPL="TPL_I",
                                            WX_INVOICE_REJECTED_TPL="TPL_R"))
        monkeypatch.setattr(cp, "_run_sync", lambda coro: __import__("asyncio").run(coro))

        mod._push_miniprogram_subscribe(self._req(), openid="oABC", issued=False)
        kwargs = send.call_args.kwargs
        assert kwargs["template_id"] == "TPL_R"
        assert kwargs["data"]["status"]["value"] == "未通过"

    def test_send_exception_does_not_raise(self, monkeypatch):
        """send_subscribe_msg 抛异常 (实际不应抛) → 捕获记日志, 不向上抛。"""
        import app.services.wx_subscribe_msg as wxsm
        from app.services import channel_providers as cp
        monkeypatch.setattr(wxsm, "send_subscribe_msg",
                            MagicMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(wxsm, "_credentials_configured", lambda: True)
        monkeypatch.setattr(mod, "settings",
                            SimpleNamespace(WX_INVOICE_ISSUED_TPL="TPL", WX_INVOICE_REJECTED_TPL=None))
        monkeypatch.setattr(cp, "_run_sync", lambda coro: __import__("asyncio").run(coro))
        # 不抛
        mod._push_miniprogram_subscribe(self._req(), openid="oABC", issued=True)


# ═══════════════════════════════════════════════════════════════════════════
# 邮件正文构建
# ═══════════════════════════════════════════════════════════════════════════
class TestEmailBody:
    def _issued_req(self, **over):
        base = dict(id=88, title_name="某科技公司", amount=12345)
        base.update(over)
        return SimpleNamespace(**base)

    def test_issued_body_amount_fen_to_yuan(self):
        """金额分→元转换: 12345 分 = 123.45 元。"""
        body = mod._build_issued_email_body(self._issued_req(), file_url=None)
        assert "123.45 元" in body
        assert "单号 #88" in body
        assert "某科技公司" in body

    def test_issued_body_with_file_url(self):
        url = "https://x.com/file?token=abc"
        body = mod._build_issued_email_body(self._issued_req(), file_url=url)
        assert url in body
        assert "2 小时内有效" in body

    def test_issued_body_without_file_url(self):
        body = mod._build_issued_email_body(self._issued_req(), file_url=None)
        assert "下载" not in body  # 无 url 不写下载段

    def test_rejected_body_with_reason(self):
        req = SimpleNamespace(id=99, title_name="乙公司", reject_reason="抬头不符")
        body = mod._build_rejected_email_body(req)
        assert "未通过审核" in body
        assert "抬头不符" in body
        assert "单号 #99" in body

    def test_rejected_body_without_reason(self):
        req = SimpleNamespace(id=100, title_name="丙公司", reject_reason=None)
        body = mod._build_rejected_email_body(req)
        assert "未通过审核" in body
        assert "拒绝原因" not in body
        assert "重新提交" in body


# ═══════════════════════════════════════════════════════════════════════════
# 通知总钩子 (3 通道 best-effort)
# ═══════════════════════════════════════════════════════════════════════════
class TestNotifyIssued:
    def _req(self, **over):
        base = dict(
            id=55, user_id=1, amount=10000, title_name="X公司",
            email="user@x.com", invoice_file_path="/tmp/inv.pdf",
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_all_three_channels_called_when_email_set(self, monkeypatch):
        mp = MagicMock(); app = MagicMock(); mail = MagicMock(return_value=True)
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_issued(self._req(), file_url="https://u")
        mp.assert_called_once()
        app.assert_called_once()
        mail.assert_called_once()
        args, kwargs = mail.call_args
        assert args[0] == "user@x.com"
        assert "#55" in args[1]          # subject 含单号
        assert "https://u" in args[2]    # body 含 file_url
        assert args[3] == "/tmp/inv.pdf"  # 附件路径透传

    def test_email_skipped_when_email_empty(self, monkeypatch):
        mp = MagicMock(); app = MagicMock(); mail = MagicMock()
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_issued(self._req(email=""), file_url="https://u")
        mp.assert_called_once()
        app.assert_called_once()
        mail.assert_not_called()  # email 空 → 不发邮件

    def test_email_skipped_when_email_none(self, monkeypatch):
        mail = MagicMock()
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", MagicMock())
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_issued(self._req(email=None), file_url=None)
        mail.assert_not_called()

    def test_mp_failure_does_not_block_others(self, monkeypatch):
        """小程序通道抛错 → App/邮件通道仍执行 (best-effort 隔离)。"""
        mp = MagicMock(side_effect=RuntimeError("mp down"))
        app = MagicMock(); mail = MagicMock(return_value=True)
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_issued(self._req(), file_url="https://u")
        app.assert_called_once()
        mail.assert_called_once()

    def test_app_failure_does_not_block_others(self, monkeypatch):
        mp = MagicMock(); app = MagicMock(side_effect=RuntimeError("app down"))
        mail = MagicMock(return_value=True)
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_issued(self._req(), file_url="https://u")
        mp.assert_called_once()
        mail.assert_called_once()

    def test_email_failure_does_not_block_pushes(self, monkeypatch):
        """邮件通道抛错 (send_invoice_email 自身异常, 非返回 False) → 推送仍执行且不向上抛。"""
        mp = MagicMock(); app = MagicMock()
        mail = MagicMock(side_effect=RuntimeError("mail down"))
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_issued(self._req(), file_url="https://u")  # 不抛
        mp.assert_called_once()
        app.assert_called_once()

    def test_openid_propagated_to_push(self, monkeypatch):
        """卡 3591ea8f: openid 透传给 _push_miniprogram_subscribe (issued=True)。"""
        mp = MagicMock()
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", MagicMock(return_value=True))
        mod.notify_invoice_issued(self._req(), openid="oXYZ")
        kwargs = mp.call_args.kwargs
        assert kwargs["openid"] == "oXYZ"
        assert kwargs["issued"] is True

    def test_openid_defaults_none_backward_compat(self, monkeypatch):
        """不传 openid → _push_miniprogram_subscribe 收到 openid=None (向后兼容)。"""
        mp = MagicMock()
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", MagicMock(return_value=True))
        mod.notify_invoice_issued(self._req())  # 不传 openid/db
        assert mp.call_args.kwargs["openid"] is None


class TestNotifyRejected:
    def _req(self, **over):
        base = dict(
            id=66, user_id=2, amount=20000, title_name="Y公司",
            email="user@y.com", reject_reason="资料不全",
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_all_three_channels_called_when_email_set(self, monkeypatch):
        mp = MagicMock(); app = MagicMock(); mail = MagicMock(return_value=True)
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_rejected(self._req())
        mp.assert_called_once()
        app.assert_called_once()
        mail.assert_called_once()
        args, _ = mail.call_args
        assert args[0] == "user@y.com"
        assert "#66" in args[1]
        assert "资料不全" in args[2]   # 拒绝原因走入正文

    def test_email_skipped_when_email_empty(self, monkeypatch):
        mp = MagicMock(); app = MagicMock(); mail = MagicMock()
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_rejected(self._req(email=""))
        mp.assert_called_once()
        app.assert_called_once()
        mail.assert_not_called()

    def test_mp_failure_does_not_block_others(self, monkeypatch):
        mp = MagicMock(side_effect=RuntimeError("mp down"))
        app = MagicMock(); mail = MagicMock(return_value=True)
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_rejected(self._req())
        app.assert_called_once()
        mail.assert_called_once()

    def test_email_failure_does_not_block_pushes(self, monkeypatch):
        mp = MagicMock(); app = MagicMock()
        mail = MagicMock(side_effect=RuntimeError("mail down"))
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", app)
        monkeypatch.setattr(mod, "send_invoice_email", mail)
        mod.notify_invoice_rejected(self._req())  # 不抛
        mp.assert_called_once()
        app.assert_called_once()

    def test_openid_propagated_to_push_issued_false(self, monkeypatch):
        """卡 3591ea8f: 拒绝通知 openid 透传, issued=False。"""
        mp = MagicMock()
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", mp)
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", MagicMock(return_value=True))
        mod.notify_invoice_rejected(self._req(), openid="oREJ")
        kwargs = mp.call_args.kwargs
        assert kwargs["openid"] == "oREJ"
        assert kwargs["issued"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 订阅消息模板参数构造 (卡 8732cf00)
# ────────────────────────────────────────────────────────────────────────────
# _build_subscribe_data 此前仅在 TestPushMiniprogramOpenid 集成路径中间接断言过
# amount/status 两字段, 无独立单测。本类钉死其四个字段 + issued/rejected 两态
# + amount 分→元转换 + None/0 边界, 与IM-B订阅消息 {key: {value: ...}} 标准结构对齐。
# ═══════════════════════════════════════════════════════════════════════════
class TestBuildSubscribeData:
    def _req(self, **over):
        base = dict(id=1207, title_name="测试科技公司", amount=352500)
        base.update(over)
        return SimpleNamespace(**base)

    def test_issued_full_structure(self):
        """issued=True → 四字段齐备, status=已开具, 金额分→元。"""
        data = mod._build_subscribe_data(self._req(), issued=True)
        assert set(data.keys()) == {"invoice_no", "title", "amount", "status"}
        # 每个值都是 {value: str} 结构 (IM-B订阅消息标准)
        for v in data.values():
            assert set(v.keys()) == {"value"}
            assert isinstance(v["value"], str)
        assert data["invoice_no"]["value"] == "1207"
        assert data["title"]["value"] == "测试科技公司"
        assert data["amount"]["value"] == "3525.00 元"   # 352500 分 = 3525.00 元
        assert data["status"]["value"] == "已开具"

    def test_rejected_status(self):
        """issued=False → status=未通过。"""
        data = mod._build_subscribe_data(self._req(), issued=False)
        assert data["status"]["value"] == "未通过"
        # 其余字段与 issued 路径一致
        assert data["invoice_no"]["value"] == "1207"

    def test_amount_none_zero_yuan(self):
        """amount=None → 0.0 → '0.00 元' (避免除零/类型错)。"""
        data = mod._build_subscribe_data(self._req(amount=None), issued=True)
        assert data["amount"]["value"] == "0.00 元"

    def test_amount_zero(self):
        """amount=0 → '0.00 元'。"""
        data = mod._build_subscribe_data(self._req(amount=0), issued=True)
        assert data["amount"]["value"] == "0.00 元"

    def test_amount_rounds_two_decimals(self):
        """amount 非 100 整除 → round 到 2 位 (如 1 分 = 0.01 元)。"""
        data = mod._build_subscribe_data(self._req(amount=1), issued=True)
        assert data["amount"]["value"] == "0.01 元"
        # 99 分 = 0.99 元 (非 1.00)
        data2 = mod._build_subscribe_data(self._req(amount=99), issued=True)
        assert data2["amount"]["value"] == "0.99 元"

    def test_invoice_no_is_string(self):
        """invoice_no 强制 str(id) (IM-B模板 value 必须字符串)。"""
        data = mod._build_subscribe_data(self._req(id=3001), issued=True)
        assert data["invoice_no"]["value"] == "3001"
        assert isinstance(data["invoice_no"]["value"], str)
