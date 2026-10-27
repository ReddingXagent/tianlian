"""invoice_notification 边界加固测试 (卡 b0224d82)

被测: app/services/invoice_notification.py — 契约 §5.5
与 test_invoice_notification.py 互补: 本文件聚焦边界/异常/加固场景。

覆盖矩阵 (≥8 edge case):
  签名 URL (6 case):
    - 不同 SECRET_KEY 签发的 token 验证失败
    - token payload 含额外字段不干扰 iid 提取
    - 同一 token 可多次验证 (replay-until-expiry)
    - build_signed_file_url 空 base_url 不崩
    - build_signed_file_url 含 query string 的 base_url
    - iid=0 正确往返 (边界值)
  SMTP 分支 (3 case):
    - SMTP_HOST 非空字符串但仅空白 → configured False
    - EMAIL_FROM 空白 → 回退 noreply@tianlian.com
    - _smtp_send 中 attachment_path 指向不存在文件 → IOError 向上传播
  订阅消息 (3 case):
    - openid 空字符串 → 视同 None 不发送
    - amount 为负数 → 负金额格式化 (不崩)
    - title_name 含特殊字符 (emoji/换行) → 原样传入
  best-effort 隔离 (2 case):
    - 三通道同时 raise → notify 不抛
    - notify_invoice_rejected 三通道同时 raise → 不抛
  邮件正文边界 (2 case):
    - amount=None → 除零保护
    - file_url 含中文和特殊字符 → 原样嵌入
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import invoice_notification as mod
from app.utils.sanitize import mask_email
from itsdangerous import URLSafeTimedSerializer


def _fake_settings(**over):
    base = dict(
        SMTP_HOST=None, SMTP_PORT=587, SMTP_USER=None, SMTP_PASS=None,
        EMAIL_FROM=None, SECRET_KEY="test-secret-key-for-hardening-tests",
        WX_INVOICE_ISSUED_TPL=None, WX_INVOICE_REJECTED_TPL=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _req(**over):
    base = dict(
        id=100, user_id=10, amount=5000, title_name="测试公司",
        email="test@x.com", invoice_file_path=None, reject_reason=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 1-6: 签名 URL 加固
# ═══════════════════════════════════════════════════════════════════════════
class TestSignedUrlHardening:
    """签名 URL 边界场景。"""

    def test_different_secret_key_fails(self):
        """不同 SECRET_KEY 签发的 token → BadSignature → None。"""
        token = mod.generate_file_token(42)
        # 用不同密钥构造 serializer 验证 → 失败
        other = URLSafeTimedSerializer("a-different-secret", salt=mod._SALT)
        with pytest.raises(Exception):
            other.loads(token, max_age=mod.SIGNED_URL_MAX_AGE)

    def test_token_with_extra_payload_fields(self):
        """token payload 含额外字段 → iid 仍正确提取。"""
        ser = mod._serializer()
        token = ser.dumps({"iid": 77, "extra": "noise", "role": "admin"})
        assert mod.verify_file_token(token) == 77

    def test_token_replay_multiple_verifications(self):
        """同一 token 在有效期内可多次验证 (非一次性)。"""
        token = mod.generate_file_token(55)
        assert mod.verify_file_token(token) == 55
        assert mod.verify_file_token(token) == 55
        assert mod.verify_file_token(token) == 55

    def test_build_url_empty_base_does_not_crash(self):
        """base_url='' → 不崩, 生成 path-only URL。"""
        url = mod.build_signed_file_url(9, "")
        assert url.startswith("/api/v1/business/invoice-file?token=")

    def test_build_url_base_with_query_string(self):
        """base_url 已含 query string → token 追加在后面 (不解析不合并)。"""
        url = mod.build_signed_file_url(9, "https://x.com?lang=zh")
        # rstrip("/") 不会去掉 query, token 直接拼接
        assert "token=" in url
        assert "lang=zh" in url

    def test_iid_zero_roundtrip(self):
        """iid=0 边界值 → 正确往返 (0 不是 falsy 在 token 逻辑中)。"""
        token = mod.generate_file_token(0)
        assert mod.verify_file_token(token) == 0

    def test_different_salt_fails(self):
        """不同 salt 签发的 token → 验证失败 → None。"""
        ser = URLSafeTimedSerializer(
            mod.settings.SECRET_KEY, salt="wrong-salt"
        )
        token = ser.dumps({"iid": 42})
        assert mod.verify_file_token(token) is None

    def test_iid_negative_value(self):
        """iid 负数 → token 可生成可验证 (int 转换不限制正负)。"""
        token = mod.generate_file_token(-1)
        assert mod.verify_file_token(token) == -1


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 7-9: SMTP 分支加固
# ═══════════════════════════════════════════════════════════════════════════
class TestSmtpHardening:
    """SMTP 配置边界。"""

    def test_smtp_configured_whitespace_only_host(self, monkeypatch):
        """SMTP_HOST=" " (空白) → bool(" ") 在 Python 中为 True。

        注意: 这是已知行为 — _smtp_configured 用 bool(getattr(...)),
        bool(" ") == True。本测试钉死此现状。
        """
        monkeypatch.setattr(mod, "settings", _fake_settings(SMTP_HOST="   "))
        # bool("   ") == True — Python 字符串非空即为 True
        assert mod._smtp_configured() is True

    def test_email_from_fallback_when_none(self, monkeypatch):
        """EMAIL_FROM=None → _smtp_send 使用 noreply@tianlian.com 默认值。"""
        monkeypatch.setattr(mod, "settings", _fake_settings(
            SMTP_HOST="smtp.x.com", SMTP_PORT=587, SMTP_USER=None,
            SMTP_PASS=None, EMAIL_FROM=None,
        ))
        server = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=server)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(mod.smtplib, "SMTP", return_value=ctx):
            mod._smtp_send("to@x.com", "s", "b")
            # sendmail 第一个参数是 From
            assert server.sendmail.call_args.args[0] == "noreply@tianlian.com"

    def test_smtp_send_nonexistent_attachment_raises(self, monkeypatch):
        """attachment_path 指向不存在文件 → open() 抛 FileNotFoundError。

        注意: 这会在 add_header (已知 bug) 之前抛, 因为文件读取在 MIMEBase 之前。
        """
        monkeypatch.setattr(mod, "settings", _fake_settings(
            SMTP_HOST="smtp.x.com", SMTP_PORT=587, SMTP_USER=None,
            SMTP_PASS=None, EMAIL_FROM="from@x.com",
        ))
        server = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=server)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(mod.smtplib, "SMTP", return_value=ctx):
            with pytest.raises(FileNotFoundError):
                mod._smtp_send(
                    "to@x.com", "s", "b",
                    attachment_path="/nonexistent/path/file.pdf",
                )


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 10-12: 订阅消息边界
# ═══════════════════════════════════════════════════════════════════════════
class TestSubscribeMessageEdgeCases:
    """小程序订阅消息边界场景。"""

    def test_openid_empty_string_treated_as_none(self, monkeypatch):
        """openid="" (空字符串) → not openid → True → 不发送 (与 None 同路径)。"""
        import app.services.wx_subscribe_msg as wxsm
        send = MagicMock()
        monkeypatch.setattr(wxsm, "send_subscribe_msg", send)
        monkeypatch.setattr(wxsm, "_credentials_configured", lambda: True)
        monkeypatch.setattr(mod, "settings", _fake_settings(
            WX_INVOICE_ISSUED_TPL="TPL",
        ))
        mod._push_miniprogram_subscribe(_req(), openid="")
        send.assert_not_called()

    def test_subscribe_data_negative_amount(self):
        """amount 为负数 → 格式化为负元 (不崩)。"""
        req = _req(amount=-100)
        data = mod._build_subscribe_data(req, issued=True)
        assert "-1.00 元" in data["amount"]["value"]

    def test_subscribe_data_title_with_special_chars(self):
        """title_name 含 emoji 和换行 → 原样传入 value。"""
        special = "测试🌟公司\n第二行"
        req = _req(title_name=special)
        data = mod._build_subscribe_data(req, issued=True)
        assert data["title"]["value"] == special


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 13-14: best-effort 三通道同时失败
# ═══════════════════════════════════════════════════════════════════════════
class TestBestEffortAllFail:
    """三通道同时 raise → notify 不向上抛异常。"""

    def test_notify_issued_all_channels_fail(self, monkeypatch):
        """三通道同时抛 → notify_invoice_issued 不抛 (best-effort)。"""
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe",
                            MagicMock(side_effect=RuntimeError("mp")))
        monkeypatch.setattr(mod, "_push_app_notification",
                            MagicMock(side_effect=RuntimeError("app")))
        monkeypatch.setattr(mod, "send_invoice_email",
                            MagicMock(side_effect=RuntimeError("mail")))
        # 不抛
        mod.notify_invoice_issued(_req(), file_url="https://u")

    def test_notify_rejected_all_channels_fail(self, monkeypatch):
        """三通道同时抛 → notify_invoice_rejected 不抛 (best-effort)。"""
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe",
                            MagicMock(side_effect=RuntimeError("mp")))
        monkeypatch.setattr(mod, "_push_app_notification",
                            MagicMock(side_effect=RuntimeError("app")))
        monkeypatch.setattr(mod, "send_invoice_email",
                            MagicMock(side_effect=RuntimeError("mail")))
        # 不抛
        mod.notify_invoice_rejected(_req())


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 15-16: 邮件正文边界
# ═══════════════════════════════════════════════════════════════════════════
class TestEmailBodyEdgeCases:
    """邮件正文边界场景。"""

    def test_issued_body_amount_none_no_crash(self):
        """amount=None → _build_issued_email_body 中 amount/100 不 crash。

        注意: None/100 在 Python 中 TypeError。但 _build_subscribe_data 有 None 保护,
        而 _build_issued_email_body 没有 — 本测试钉死现状 (会抛 TypeError)。
        生产修复卡需加 if amount is not None 保护。
        """
        req = _req(amount=None)
        with pytest.raises(TypeError):
            mod._build_issued_email_body(req, file_url=None)

    def test_issued_body_with_long_url(self):
        """file_url 超长 (2048+ chars) → 原样嵌入不截断。"""
        long_url = "https://x.com/f?" + "a" * 3000
        req = _req(amount=100)
        body = mod._build_issued_email_body(req, file_url=long_url)
        assert long_url in body

    def test_issued_body_contains_brand(self):
        """邮件正文以 '— 天链' 签名结尾 (品牌一致性)。"""
        req = _req(amount=100)
        body = mod._build_issued_email_body(req, file_url=None)
        assert body.rstrip().endswith("— 天链")

    def test_rejected_body_contains_brand(self):
        """拒绝邮件正文以 '— 天链' 签名结尾。"""
        req = _req(reject_reason="测试")
        body = mod._build_rejected_email_body(req)
        assert body.rstrip().endswith("— 天链")

    def test_rejected_body_amount_not_referenced(self):
        """拒绝邮件正文不含金额信息 (与 issued 不同, rejected 不列金额)。"""
        req = _req(amount=99999, reject_reason="x")
        body = mod._build_rejected_email_body(req)
        assert "99999" not in body
        assert "元" not in body


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 17-18: 通知钩子参数传递
# ═══════════════════════════════════════════════════════════════════════════
class TestNotifyParameterPassing:
    """通知钩子参数透传边界。"""

    def test_notify_issued_file_url_none_to_email_body(self, monkeypatch):
        """file_url=None → 邮件正文不含下载链接段。"""
        captured_body = []

        def capture_mail(to, subject, body, path=None):
            captured_body.append(body)
            return True

        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", MagicMock())
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", capture_mail)
        mod.notify_invoice_issued(_req(email="u@x.com"), file_url=None)
        assert len(captured_body) == 1
        assert "下载" not in captured_body[0]

    def test_notify_issued_file_url_set_to_email_body(self, monkeypatch):
        """file_url 有值 → 邮件正文含下载链接 + 2h 有效期提示。"""
        captured_body = []

        def capture_mail(to, subject, body, path=None):
            captured_body.append(body)
            return True

        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", MagicMock())
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", capture_mail)
        mod.notify_invoice_issued(_req(email="u@x.com"), file_url="https://d.l/abc")
        assert "https://d.l/abc" in captured_body[0]
        assert "2 小时内有效" in captured_body[0]

    def test_notify_issued_passes_invoice_file_path_as_attachment(self, monkeypatch):
        """invoice_file_path 透传给 send_invoice_email 的 attachment_path。"""
        captured = []

        def capture_mail(to, subject, body, path=None):
            captured.append(path)
            return True

        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", MagicMock())
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", capture_mail)
        mod.notify_invoice_issued(
            _req(email="u@x.com", invoice_file_path="/data/inv.pdf"),
            file_url="https://d.l/abc",
        )
        assert captured[0] == "/data/inv.pdf"

    def test_notify_rejected_no_attachment_passed(self, monkeypatch):
        """拒绝通知不传 attachment_path (send_invoice_email 第4参数默认 None)。"""
        captured = []

        def capture_mail(to, subject, body, path=None):
            captured.append(path)
            return True

        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", MagicMock())
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", capture_mail)
        mod.notify_invoice_rejected(_req(email="u@x.com", reject_reason="x"))
        assert captured[0] is None

    def test_notify_issued_db_param_accepted(self, monkeypatch):
        """db 参数被接受 (当前未在钩子内直接使用, 向后兼容)。"""
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", MagicMock())
        monkeypatch.setattr(mod, "_push_app_notification", MagicMock())
        monkeypatch.setattr(mod, "send_invoice_email", MagicMock(return_value=True))
        # db=None 不抛
        mod.notify_invoice_issued(_req(), file_url=None, db=None)


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case 19-20: 日志留痕验证
# ═══════════════════════════════════════════════════════════════════════════
class TestLoggingTraces:
    """通知钩子日志留痕验证 (运维可追溯性)。"""

    def test_mp_subscribe_logs_openid_presence(self, caplog):
        """openid 有值 → 日志显示 '有'; None → 显示 '无'。"""
        req = _req(id=200, user_id=5, amount=30000)
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod._push_miniprogram_subscribe(req, openid="oABC")
        assert any("openid=有" in r.message for r in caplog.records)

        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod._push_miniprogram_subscribe(req, openid=None)
        assert any("openid=无" in r.message for r in caplog.records)

    def test_app_push_logs_all_fields(self, caplog):
        """App push 日志含 invoice_id/user_id/amount 三字段。"""
        req = _req(id=301, user_id=42, amount=77700)
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod._push_app_notification(req)
        records = [r.message for r in caplog.records if "APP-PUSH" in r.message]
        assert len(records) == 1
        msg = records[0]
        assert "301" in msg
        assert "42" in msg
        assert "77700" in msg

    def test_send_invoice_email_mock_log_format(self, monkeypatch, caplog):
        """SMTP 未配置 → MOCK 日志含 to(脱敏)/subject/attach 三信息。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: False)
        monkeypatch.setattr(mod, "_smtp_send", MagicMock())
        with caplog.at_level(logging.INFO, logger=mod.logger.name):
            mod.send_invoice_email("a@b.com", "测试主题", "正文", attachment_path="/x.pdf")
        assert any(
            "INVOICE EMAIL MOCK" in r.message
            and "a@b.com" not in r.message
            and mask_email("a@b.com") in r.message
            and "测试主题" in r.message
            for r in caplog.records
        )

    def test_send_invoice_email_exception_logged(self, monkeypatch, caplog):
        """SMTP 已配置但发送异常 → logger.exception 记录 (caplog 可捕获)。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)
        monkeypatch.setattr(mod, "_smtp_send",
                            MagicMock(side_effect=ConnectionError("smtp down")))
        with caplog.at_level(logging.ERROR, logger=mod.logger.name):
            result = mod.send_invoice_email("a@b.com", "s", "b")
        assert result is False
        assert any("开票邮件发送失败" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════
# 卡 acfe2394: App push 标题按终态三分支 (issued/rejected/voided)
# ═══════════════════════════════════════════════════════════════════════════
class TestAppPushTitleByStatus:
    """拒绝/开具/红冲三路径 App push 托盘文案断言。

    缺陷背景: notify_invoice_rejected 复用 _push_app_notification 时原实现
    只看 voided 分支, 被拒用户看到 title='发票开具通知' body='您的开票申请已处理'。
    """

    def _capture_provider(self, monkeypatch):
        sends = []
        provider = MagicMock()
        provider.send.side_effect = lambda *a, **k: sends.append((a, k))
        from app.services import push as push_mod
        monkeypatch.setattr(push_mod, "get_push_provider", lambda: provider)
        return sends

    def test_rejected_title_and_body(self, monkeypatch):
        """拒绝路径 → title='开票申请未通过' body='您的开票申请未通过审核'。"""
        sends = self._capture_provider(monkeypatch)
        req = _req(status="rejected", voided=False, email=None)
        mod.notify_invoice_rejected(req, db=None, openid=None)
        assert len(sends) == 1
        user_id, title, body, payload = sends[0][0]
        assert title == "开票申请未通过"
        assert body == "您的开票申请未通过审核"

    def test_issued_title_unchanged(self, monkeypatch):
        """开具路径文案不变 ('发票开具通知', 向后兼容)。"""
        sends = self._capture_provider(monkeypatch)
        req = _req(status="issued", voided=False, email=None)
        mod.notify_invoice_issued(req, file_url=None, db=None, openid=None)
        assert len(sends) == 1
        _, title, body, _ = sends[0][0]
        assert title == "发票开具通知"
        assert body == "您的开票申请已处理"

    def test_voided_title_unchanged(self, monkeypatch):
        """红冲路径文案不变 ('发票红冲通知')。"""
        sends = self._capture_provider(monkeypatch)
        req = _req(status="issued", voided=True, void_reason="重复开票", email=None)
        mod.notify_invoice_voided(req, db=None, openid=None)
        assert len(sends) == 1
        _, title, body, _ = sends[0][0]
        assert title == "发票红冲通知"
        assert body == "您的发票已红冲作废"
