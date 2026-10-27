"""开票通知模块测试 (用户端云端契约 §5.5, 工作卡 a09f8a21 / 189c5a13)

聚焦 app/services/invoice_notification.py 模块本身:
- 签名文件令牌: generate ↔ verify 正向 / 过期 / 篡改 / 跨 salt 不互通
- build_signed_file_url 拼接契约
- notify_invoice_issued 三通道 best-effort:
  · IM-B订阅消息 (openid 有值 + 凭证齐备 → 真实调用 send_subscribe_msg)
  · App push (仅日志)
  · SMTP 邮件 (email 非空 → send_invoice_email)

与 test_invoice_request.py::TestEmailNotification 互补: 那里只覆盖邮件分支,
本文件补齐IM-B订阅消息通道的真实发送验证 + token 契约边界。
"""
import pytest

from app.services import invoice_notification as mod


# ─── 测试用发票申请桩 ─────────────────────────────────────────────────────────

class _Req:
    """发票申请对象桩 (notify_* 钩子只读若干属性, 无需真实 ORM)。"""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.user_id = kw.get("user_id", 2)
        self.amount = kw.get("amount", 12800)  # 分
        self.email = kw.get("email", "user@example.com")
        self.title_name = kw.get("title_name", "张三")
        self.invoice_file_path = kw.get("invoice_file_path", None)
        self.reject_reason = kw.get("reject_reason", None)
        self.voided = kw.get("voided", False)
        self.void_reason = kw.get("void_reason", None)
        self.voided_by = kw.get("voided_by", None)
        self.voided_at = kw.get("voided_at", None)


# ═══════════════════════════════════════════════════════════════════════════════
# 签名文件令牌 (契约 §5.5: 2h 过期, itsdangerous URLSafeTimedSerializer)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileToken:
    def test_roundtrip(self):
        """generate → verify 正向: 取回原 invoice_id。"""
        tok = mod.generate_file_token(123)
        assert isinstance(tok, str)
        assert mod.verify_file_token(tok) == 123

    def test_roundtrip_large_id(self):
        tok = mod.generate_file_token(999999999)
        assert mod.verify_file_token(tok) == 999999999

    def test_tampered_token_returns_none(self):
        """篡改 token → BadSignature → None。

        卡 6d06831d 修复 flaky: 原写法改「末 2 字符」为 zz/yy —— 但签名段 27 个
        base64url 字符编码 162 bits, SHA1 实际 160 bits, 末字符低 2 位在解码时被
        丢弃 (无效位)。当原 token 末 2 字符恰与 zz/yy 同「有效位等价类」时
        (蒙特卡洛实测 ~0.085%/次), 篡改后解码字节不变 → verify 反而通过 → 偶发红。
        改为篡改签名段首字符 (6 bits 全有效), 确定性触发 BadSignature。
        """
        tok = mod.generate_file_token(5)
        head = tok.split(".")[0]  # payload 段
        sig = tok.split(".")[-1]
        flip = "A" if sig[0] != "A" else "B"
        tampered = f"{head}.{tok.split('.')[1]}.{flip}{sig[1:]}"
        assert mod.verify_file_token(tampered) is None

    def test_garbage_token_returns_none(self):
        """纯垃圾串 → None。"""
        assert mod.verify_file_token("not-a-token") is None
        assert mod.verify_file_token("") is None

    def test_expired_token_returns_none(self, monkeypatch):
        """过期 token (max_age=-1 立即判过期) → SignatureExpired → None。"""
        monkeypatch.setattr(mod, "SIGNED_URL_MAX_AGE", -1)
        tok = mod.generate_file_token(7)
        assert mod.verify_file_token(tok) is None

    def test_different_salt_not_interchangeable(self):
        """不同 salt 签发的 token 不互通 (用途隔离)。"""
        from itsdangerous import URLSafeTimedSerializer
        other = URLSafeTimedSerializer(
            mod.settings.SECRET_KEY, salt="other-purpose"
        ).dumps({"iid": 99})
        # 用 invoice-file-download salt 验证 → 签名不匹配 → None
        assert mod.verify_file_token(other) is None


class TestBuildSignedFileUrl:
    def test_url_contains_token_and_path(self):
        """拼接 URL 含正确路径 + token 参数。"""
        url = mod.build_signed_file_url(42, "https://api.tianlian.example/")
        assert url.startswith("https://api.tianlian.example/api/v1/business/invoice-file?token=")
        tok = url.split("token=")[1]
        assert mod.verify_file_token(tok) == 42

    def test_url_strips_trailing_slash(self):
        """base_url 末尾斜杠被剥离 (避免 //)。"""
        url = mod.build_signed_file_url(1, "https://x.example/")
        assert "//api/v1" not in url


# ═══════════════════════════════════════════════════════════════════════════════
# notify_invoice_issued: 三通道 best-effort
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotifyIssuedChannels:
    """notify_invoice_issued 三通道: IM-B订阅消息 / App push / 邮件。

    best-effort 契约: 任一通道异常不阻断其它通道与主流程。
    """

    def test_miniprogram_subscribe_called_when_openid_and_credentials(
        self, monkeypatch
    ):
        """openid 有值 + 凭证齐备 + 模板ID配置 → 真实调用 send_subscribe_msg。

        mock _run_sync 捕获对 send_subscribe_msg 的调用, 验证 openid/template/page 透传。
        """
        calls = {"run_sync": None}

        # 凭证齐备 (否则 _push_miniprogram_subscribe 在 _credentials_configured 处提前返回)
        monkeypatch.setattr(
            "app.services.wx_subscribe_msg._credentials_configured", lambda: True
        )
        monkeypatch.setattr(mod.settings, "WX_INVOICE_ISSUED_TPL", "TPL_ISSUED_001")
        monkeypatch.setattr(mod.settings, "WX_INVOICE_REJECTED_TPL", "TPL_REJECTED_001")

        def fake_run_sync(coro):
            # coro 是 send_subscribe_msg(...) 返回的协程; 取其参数
            cr = coro.cr_frame
            calls["run_sync"] = {
                "openid": cr.f_locals.get("openid"),
                "template_id": cr.f_locals.get("template_id"),
                "page": cr.f_locals.get("page"),
                "data": cr.f_locals.get("data"),
            }
            coro.close()  # 不真正执行, 避免网络
            return {"status": "sent"}

        monkeypatch.setattr("app.services.channel_providers._run_sync", fake_run_sync)
        # App push / 邮件通道静默 (本用例聚焦IM-B)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(mod, "send_invoice_email", lambda *a, **kw: True)

        mod.notify_invoice_issued(_Req(email=None), openid="oXyz123", file_url="http://x")

        info = calls["run_sync"]
        assert info is not None, "IM-B订阅消息未被调用"
        assert info["openid"] == "oXyz123"
        assert info["template_id"] == "TPL_ISSUED_001"
        assert info["page"] == "pages/invoice/detail?id=1"
        # 模板参数结构 (IM-B标准 {key: {value: ...}})
        assert "invoice_no" in info["data"]
        assert "amount" in info["data"]
        assert info["data"]["status"]["value"] == "已开具"

    def test_miniprogram_subscribe_skipped_without_openid(self, monkeypatch):
        """无 openid → 仅日志, 不调用 send_subscribe_msg。"""
        called = {"n": 0}
        monkeypatch.setattr(
            "app.services.channel_providers._run_sync",
            lambda coro: called.__setitem__("n", called["n"] + 1),
        )
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(mod, "send_invoice_email", lambda *a, **kw: True)

        mod.notify_invoice_issued(_Req(email=None), openid=None)
        assert called["n"] == 0

    def test_miniprogram_subscribe_skipped_without_template(self, monkeypatch):
        """凭证齐备但模板ID未配置 → 不发送 (降级日志)。"""
        called = {"n": 0}
        monkeypatch.setattr(
            "app.services.wx_subscribe_msg._credentials_configured", lambda: True
        )
        monkeypatch.setattr(mod.settings, "WX_INVOICE_ISSUED_TPL", None)
        monkeypatch.setattr(
            "app.services.channel_providers._run_sync",
            lambda coro: called.__setitem__("n", called["n"] + 1),
        )
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(mod, "send_invoice_email", lambda *a, **kw: True)

        mod.notify_invoice_issued(_Req(email=None), openid="oXyz")
        assert called["n"] == 0

    def test_email_sent_when_email_present(self, monkeypatch):
        """email 非空 → 调用 send_invoice_email, 正文含 file_url。"""
        captured = {}
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)

        def fake_send(to_email, subject, body_text, attachment_path=None):
            captured["to"] = to_email
            captured["subject"] = subject
            captured["body"] = body_text
            return True
        monkeypatch.setattr(mod, "send_invoice_email", fake_send)

        mod.notify_invoice_issued(_Req(email="a@b.com"), file_url="http://x/inv.pdf")
        assert captured["to"] == "a@b.com"
        assert "http://x/inv.pdf" in captured["body"]
        assert "128.00" in captured["body"]  # 12800 分 → 128.00 元

    def test_email_skipped_when_no_email(self, monkeypatch):
        """email 为空 → 不调用 send_invoice_email。"""
        called = {"sent": False}
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(
            mod, "send_invoice_email", lambda *a, **kw: called.__setitem__("sent", True)
        )
        mod.notify_invoice_issued(_Req(email=None))
        assert called["sent"] is False

    def test_channel_exception_does_not_propagate(self, monkeypatch):
        """任一通道抛异常 → 仅记日志, 不阻断主流程与其它通道。"""
        def boom_mp(r, **kw):
            raise RuntimeError("mp down")
        def boom_app(r, **kw):
            raise RuntimeError("app down")
        def boom_email(*a, **kw):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", boom_mp)
        monkeypatch.setattr(mod, "_push_app_notification", boom_app)
        monkeypatch.setattr(mod, "send_invoice_email", boom_email)

        # 不应抛出 (best-effort)
        mod.notify_invoice_issued(_Req(email="a@b.com"))


# ═══════════════════════════════════════════════════════════════════════════════
# notify_invoice_rejected: 同构三通道
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotifyRejectedChannels:
    def test_miniprogram_uses_rejected_template(self, monkeypatch):
        """拒绝通知用 REJECTED 模板 + status=未通过。"""
        calls = {"run_sync": None}
        monkeypatch.setattr(
            "app.services.wx_subscribe_msg._credentials_configured", lambda: True
        )
        monkeypatch.setattr(mod.settings, "WX_INVOICE_ISSUED_TPL", "TPL_ISSUED")
        monkeypatch.setattr(mod.settings, "WX_INVOICE_REJECTED_TPL", "TPL_REJ")

        def fake_run_sync(coro):
            cr = coro.cr_frame
            calls["run_sync"] = {
                "template_id": cr.f_locals.get("template_id"),
                "data": cr.f_locals.get("data"),
            }
            coro.close()
            return {"status": "sent"}
        monkeypatch.setattr("app.services.channel_providers._run_sync", fake_run_sync)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(mod, "send_invoice_email", lambda *a, **kw: True)

        mod.notify_invoice_rejected(
            _Req(email=None, reject_reason="抬头错误"), openid="oXyz"
        )
        info = calls["run_sync"]
        assert info is not None
        assert info["template_id"] == "TPL_REJ"
        assert info["data"]["status"]["value"] == "未通过"

    def test_rejected_email_contains_reason(self, monkeypatch):
        """拒绝邮件正文含拒绝原因。"""
        captured = {}
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)

        def fake_send(to_email, subject, body_text, attachment_path=None):
            captured["body"] = body_text
            return True
        monkeypatch.setattr(mod, "send_invoice_email", fake_send)

        mod.notify_invoice_rejected(_Req(email="a@b.com", reject_reason="抬头错误"))
        assert "抬头错误" in captured["body"]


# ═══════════════════════════════════════════════════════════════════════════════
# 邮件发送: SMTP 两条路径 (mock / 真实)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSendInvoiceEmail:
    def test_no_smtp_returns_true(self, monkeypatch):
        """SMTP 未配置 → mock 日志, 返回 True。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: False)
        assert mod.send_invoice_email("a@b.com", "s", "b") is True

    def test_smtp_configured_calls_smtp_send(self, monkeypatch):
        """SMTP 已配置 → 调用 _smtp_send, 成功返回 True。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)
        captured = {}

        def fake_smtp(to_email, subject, body_text, attachment_path=None):
            captured["to"] = to_email
            captured["attach"] = attachment_path
        monkeypatch.setattr(mod, "_smtp_send", fake_smtp)

        assert mod.send_invoice_email("a@b.com", "s", "b", "/x/y.pdf") is True
        assert captured["to"] == "a@b.com"
        assert captured["attach"] == "/x/y.pdf"

    def test_smtp_failure_returns_false(self, monkeypatch):
        """SMTP 已配置但发送抛错 → 返回 False (不抛出)。"""
        monkeypatch.setattr(mod, "_smtp_configured", lambda: True)
        monkeypatch.setattr(mod, "_smtp_send", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down")))
        assert mod.send_invoice_email("a@b.com", "s", "b") is False


# ═══════════════════════════════════════════════════════════════════════════════
# notify_invoice_voided: 红冲三通道 (卡 9211f668)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotifyVoidedChannels:
    """notify_invoice_voided 三通道: 与 issued/rejected 同构, 红冲文案语义区分。"""

    def test_void_subscribe_uses_void_mode(self, monkeypatch):
        """红冲通知: 订阅消息走 void 模式, 文案「已红冲作废」+ void_reason。"""
        calls = {"run_sync": None}
        monkeypatch.setattr(
            "app.services.wx_subscribe_msg._credentials_configured", lambda: True
        )
        monkeypatch.setattr(mod.settings, "WX_INVOICE_ISSUED_TPL", "TPL_ISSUED")
        monkeypatch.setattr(mod.settings, "WX_INVOICE_REJECTED_TPL", "TPL_REJ")

        def fake_run_sync(coro):
            cr = coro.cr_frame
            calls["run_sync"] = {
                "openid": cr.f_locals.get("openid"),
                "template_id": cr.f_locals.get("template_id"),
                "data": cr.f_locals.get("data"),
            }
            coro.close()
            return {"status": "sent"}
        monkeypatch.setattr("app.services.channel_providers._run_sync", fake_run_sync)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(mod, "send_invoice_email", lambda *a, **kw: True)

        req = _Req(email=None, void_reason="开票信息有误")
        mod.notify_invoice_voided(req, openid="oVoid")
        info = calls["run_sync"]
        assert info is not None, "红冲订阅消息未被调用"
        assert info["openid"] == "oVoid"
        # 模板复用 REJECTED 模板 (复用拒绝类模板, 不新增渠道配置)
        assert info["template_id"] == "TPL_REJ"
        status_val = info["data"]["status"]["value"]
        assert "红冲" in status_val, "红冲文案必须含红冲语义, 区别于已开具/未通过"
        assert status_val != "已开具" and status_val != "未通过"
        # void_reason 出现在模板参数或正文里
        joined = str(info["data"])
        assert "开票信息有误" in joined

    def test_void_subscribe_mode_backward_compat(self, monkeypatch):
        """行为锁: void 模式默认关闭, issued=True/False 原行为不变。"""
        # issued=True → 已开具
        d_issued = mod._build_subscribe_data(_Req(), issued=True)
        assert d_issued["status"]["value"] == "已开具"
        # issued=False → 未通过 (rejected 复用)
        d_rej = mod._build_subscribe_data(_Req(), issued=False)
        assert d_rej["status"]["value"] == "未通过"

    def test_void_app_push_payload_status_voided(self, monkeypatch):
        """行为锁: _payload_status 对红冲单 → 'voided' (小写, 契约 v1.3 风格)。"""
        req = _Req(voided=True)
        req.status = type("S", (), {"value": "issued"})()  # status 保持 issued
        assert mod._payload_status(req) == "voided"
        # 未红冲 → 原行为 (状态原样)
        req2 = _Req(voided=False)
        req2.status = type("S", (), {"value": "issued"})()
        assert mod._payload_status(req2) == "issued"

    def test_void_email_sent_with_void_reason(self, monkeypatch):
        """email 非空 → 发红冲邮件: subject 含「已红冲」, 正文含红冲原因/申请单号/抬头。"""
        captured = {}
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)

        def fake_send(to_email, subject, body_text, attachment_path=None):
            captured["to"] = to_email
            captured["subject"] = subject
            captured["body"] = body_text
            return True
        monkeypatch.setattr(mod, "send_invoice_email", fake_send)

        req = _Req(id=9, email="a@b.com", void_reason="抬头开错")
        mod.notify_invoice_voided(req)
        assert captured["to"] == "a@b.com"
        assert "已红冲" in captured["subject"]
        assert "#9" in captured["subject"]
        assert "抬头开错" in captured["body"]
        assert "#9" in captured["body"]
        assert "张三" in captured["body"]  # 抬头
        assert "作废" in captured["body"]  # 原票作废说明
        # 区别于 issued/rejected 文案
        assert "未通过" not in captured["body"]
        assert "已完成开具" not in captured["body"]

    def test_void_email_skipped_when_no_email(self, monkeypatch):
        """email 为空 → 不发红冲邮件。"""
        called = {"sent": False}
        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", lambda r, **kw: None)
        monkeypatch.setattr(mod, "_push_app_notification", lambda r, **kw: None)
        monkeypatch.setattr(
            mod, "send_invoice_email", lambda *a, **kw: called.__setitem__("sent", True)
        )
        mod.notify_invoice_voided(_Req(email=None))
        assert called["sent"] is False

    def test_void_channel_exception_does_not_propagate(self, monkeypatch):
        """任一通道抛异常 → 仅记日志, 不抛出不阻断其它通道 (best-effort)。"""
        def boom_mp(r, **kw):
            raise RuntimeError("mp down")
        def boom_app(r, **kw):
            raise RuntimeError("app down")
        def boom_email(*a, **kw):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(mod, "_push_miniprogram_subscribe", boom_mp)
        monkeypatch.setattr(mod, "_push_app_notification", boom_app)
        monkeypatch.setattr(mod, "send_invoice_email", boom_email)

        # 不应抛出
        mod.notify_invoice_voided(_Req(email="a@b.com", void_reason="x"))

    def test_void_all_three_channels_invoked(self, monkeypatch):
        """三通道全部被触发 (订阅消息/App push/邮件)。"""
        invoked = {"mp": 0, "app": 0, "email": 0}
        monkeypatch.setattr(
            mod, "_push_miniprogram_subscribe",
            lambda r, **kw: invoked.__setitem__("mp", invoked["mp"] + 1),
        )
        monkeypatch.setattr(
            mod, "_push_app_notification",
            lambda r, **kw: invoked.__setitem__("app", invoked["app"] + 1),
        )
        monkeypatch.setattr(
            mod, "send_invoice_email",
            lambda *a, **kw: invoked.__setitem__("email", invoked["email"] + 1) or True,
        )
        mod.notify_invoice_voided(_Req(email="a@b.com"))
        assert invoked == {"mp": 1, "app": 1, "email": 1}
