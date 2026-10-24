"""
通知分发器 (app/services/notification_dispatcher.py) 单元测试

被测: NotificationDispatcher —— 邮件/IM-B/短信/IM/日志 多通道告警分发。
隔离: MagicMock/patch 隔离 settings/smtplib/requests/im/audit_service/SessionLocal;
      alarm 与 rule 用 SimpleNamespace 构造, 完全脱离 DB。
覆盖: 正常路径 + 边界条件 + 异常处理。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.alarm import AlarmLevel
from app.models.channel_config import ChannelConfig, ChannelType
from app.models.station import Station
from app.services import notification_dispatcher as nd_mod
from app.services.notification_dispatcher import (
    LEVEL_CHANNEL_MAP,
    URGENT_LEVELS,
    NotificationDispatcher,
)


# ═══════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════
def _fake_settings(**over):
    """构造覆盖 __init__ 全部 getattr(settings, ...) 读取的伪 settings。"""
    base = SimpleNamespace(
        SMTP_HOST=None,
        SMTP_PORT=587,
        SMTP_USER=None,
        SMTP_PASS=None,
        EMAIL_FROM=None,
        EMAIL_TO="admin@tianlian.com",
        WECHAT_WEBHOOK_URL=None,
        SMS_API_URL=None,
        ADMIN_EMAILS="admin@tianlian.com",
    )
    for k, v in over.items():
        setattr(base, k, v)
    return base


def _alarm(**kw):
    """构造一个具备 Alarm 全部被读属性的 alarm-like 对象。"""
    base = dict(
        id=1,
        level=AlarmLevel.WARNING,
        content="电池过温告警",
        device_id=10,
        station_id=20,
        fault_code="0x01",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        escalated_from=None,
        escalated_at=None,
        aggregation_count=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _rule(**kw):
    base = dict(id=1, name="rule1", level="warning", channels=["email"], enabled=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _new_dispatcher():
    """绕过 settings 读取, 直接构造后注入可控默认配置。"""
    d = NotificationDispatcher()
    d._email_config = {
        "smtp_host": None, "smtp_port": 587, "smtp_user": None,
        "smtp_pass": None, "from_addr": None, "to_addr": "admin@tianlian.com",
    }
    d._im_b_webhook = None
    d._sms_api_url = None
    d._admin_emails = ["admin@tianlian.com"]
    return d


# ═══════════════════════════════════════════════════════════════════
# 初始化 / 配置读取
# ═══════════════════════════════════════════════════════════════════
class TestInit:
    @patch("app.services.notification_dispatcher.settings", _fake_settings())
    def test_default_admin_emails(self):
        d = NotificationDispatcher()
        assert d._admin_emails == ["admin@tianlian.com"]
        assert isinstance(d._admin_emails, list)

    @patch(
        "app.services.notification_dispatcher.settings",
        _fake_settings(ADMIN_EMAILS="a@x.com, b@x.com,c@x.com"),
    )
    def test_admin_emails_csv_split(self):
        d = NotificationDispatcher()
        assert d._admin_emails == ["a@x.com", "b@x.com", "c@x.com"]

    @patch(
        "app.services.notification_dispatcher.settings",
        _fake_settings(ADMIN_EMAILS=["x@x.com", "y@x.com"]),
    )
    def test_admin_emails_list_kept_as_is(self):
        # 已是 list → 不拆分
        d = NotificationDispatcher()
        assert d._admin_emails == ["x@x.com", "y@x.com"]

    @patch("app.services.notification_dispatcher.settings", _fake_settings())
    def test_email_and_channel_config_defaults(self):
        d = NotificationDispatcher()
        assert d._email_config["smtp_host"] is None
        assert d._email_config["smtp_port"] == 587
        assert d._im_b_webhook is None
        assert d._sms_api_url is None


# ═══════════════════════════════════════════════════════════════════
# dispatch
# ═══════════════════════════════════════════════════════════════════
class TestDispatch:
    def test_no_channels_returns_no_channels(self):
        d = _new_dispatcher()
        r = d.dispatch(alarm=_alarm(), channels=[])
        assert r["status"] == "no_channels"
        assert r["channels"] == []

    def test_routes_each_known_channel(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_email") as me, patch.object(d, "_send_im_b") as mw, \
             patch.object(d, "_send_sms") as ms, patch.object(d, "_send_im") as mf, \
             patch.object(d, "_log_notification") as ml:
            r = d.dispatch(alarm=_alarm(), channels=["email", "im_b", "sms", "im", "logger"])
        me.assert_called_once()
        mw.assert_called_once()
        ms.assert_called_once()
        mf.assert_called_once()
        ml.assert_called_once()
        assert r["status"] == "dispatched"
        assert len(r["channels"]) == 5
        assert all(c["status"] == "sent" for c in r["channels"])

    def test_unknown_channel_does_not_raise(self):
        d = _new_dispatcher()
        r = d.dispatch(alarm=_alarm(), channels=["carrier_pigeon"])
        # 未知渠道: 不算 sent, 标 unknown + error 说明
        assert r["status"] == "dispatched"
        assert r["channels"][0]["channel"] == "carrier_pigeon"
        assert r["channels"][0]["status"] != "sent"
        assert r["channels"][0]["status"] == "unknown"
        assert "unknown channel" in r["channels"][0]["error"].lower()

    def test_channel_exception_recorded_as_failed(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_email", side_effect=RuntimeError("smtp down")):
            r = d.dispatch(alarm=_alarm(), channels=["email"])
        assert r["channels"][0]["status"] == "failed"
        # 内部语义: error 直接反映真实异常, 不再用 C 端话术
        assert r["channels"][0]["error"] == "send failed: smtp down"
        assert "smtp down" in r["channels"][0]["error"]

    def test_sender_returning_false_marks_failed(self):
        # _send_* 返回 bool: False → failed, True → sent
        d = _new_dispatcher()
        with patch.object(d, "_send_email", return_value=False), \
             patch.object(d, "_log_notification"):
            r = d.dispatch(alarm=_alarm(), channels=["email", "logger"])
        statuses = {c["channel"]: c["status"] for c in r["channels"]}
        assert statuses["email"] == "failed"
        assert statuses["logger"] == "sent"

    def test_sender_returning_true_marks_sent(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_im_b", return_value=True):
            r = d.dispatch(alarm=_alarm(), channels=["im_b"])
        assert r["channels"][0]["status"] == "sent"

    def test_partial_failure_keeps_other_channels(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_email", side_effect=RuntimeError("boom")), \
             patch.object(d, "_log_notification"):
            r = d.dispatch(alarm=_alarm(), channels=["email", "logger"])
        statuses = {c["channel"]: c["status"] for c in r["channels"]}
        assert statuses["email"] == "failed"
        assert statuses["logger"] == "sent"

    def test_keyword_mode_builds_test_alarm(self):
        d = _new_dispatcher()
        with patch.object(d, "_log_notification") as ml:
            d.dispatch(alarm_id=99, level="critical", message="hi", channels=["logger"])
        built = ml.call_args.args[0]
        assert built.id == 99
        assert built.level == AlarmLevel.CRITICAL
        assert built.content == "hi"

    def test_keyword_mode_default_level_warning(self):
        d = _new_dispatcher()
        with patch.object(d, "_log_notification") as ml:
            d.dispatch(alarm_id=5, channels=["logger"])  # 未传 level
        assert ml.call_args.args[0].level == AlarmLevel.WARNING

    def test_keyword_mode_unknown_level_defaults_warning(self):
        d = _new_dispatcher()
        with patch.object(d, "_log_notification") as ml:
            d.dispatch(alarm_id=5, level="bogus", channels=["logger"])
        assert ml.call_args.args[0].level == AlarmLevel.WARNING

    def test_keyword_mode_all_levels_mapped(self):
        d = _new_dispatcher()
        for lvl in ("info", "warning", "critical", "fatal"):
            with patch.object(d, "_log_notification") as ml:
                d.dispatch(alarm_id=1, level=lvl, channels=["logger"])
            assert ml.call_args.args[0].level.value == lvl


# ═══════════════════════════════════════════════════════════════════
# 规则匹配 / 渠道扩展
# ═══════════════════════════════════════════════════════════════════
class TestRuleMatch:
    def test_disabled_rule_never_matches(self):
        d = _new_dispatcher()
        assert d._rule_matches(_rule(enabled=False), _alarm()) is False

    def test_level_mismatch(self):
        d = _new_dispatcher()
        assert d._rule_matches(_rule(level="critical"), _alarm(level=AlarmLevel.INFO)) is False

    def test_level_match(self):
        d = _new_dispatcher()
        assert d._rule_matches(_rule(level="warning"), _alarm(level=AlarmLevel.WARNING)) is True

    def test_rule_with_no_level_matches_all(self):
        d = _new_dispatcher()
        assert d._rule_matches(_rule(level=None), _alarm(level=AlarmLevel.FATAL)) is True


class TestRuleChannelsWithLevel:
    def test_normal_level_no_extension(self):
        d = _new_dispatcher()
        chs = d._get_rule_channels_with_level(_rule(channels=["email"]), _alarm(level=AlarmLevel.WARNING))
        assert chs == ["email"]  # WARNING 不在 URGENT_LEVELS

    def test_critical_level_extends_channels(self):
        d = _new_dispatcher()
        chs = d._get_rule_channels_with_level(_rule(channels=["email"]), _alarm(level=AlarmLevel.CRITICAL))
        # CRITICAL → LEVEL_CHANNEL_MAP 追加 im/logger, 无重复
        assert "email" in chs and "im" in chs and "logger" in chs

    def test_fatal_level_extends_channels(self):
        d = _new_dispatcher()
        chs = d._get_rule_channels_with_level(_rule(channels=[]), _alarm(level=AlarmLevel.FATAL))
        assert chs == LEVEL_CHANNEL_MAP[AlarmLevel.FATAL]

    def test_extension_has_no_duplicates(self):
        d = _new_dispatcher()
        chs = d._get_rule_channels_with_level(
            _rule(channels=["email", "im"]), _alarm(level=AlarmLevel.FATAL)
        )
        assert chs.count("email") == 1
        assert chs.count("im") == 1

    def test_empty_rule_channels_uses_empty_list(self):
        d = _new_dispatcher()
        # rule.channels=None → or [] → WARNING 不扩展 → []
        chs = d._get_rule_channels_with_level(_rule(channels=None), _alarm(level=AlarmLevel.WARNING))
        assert chs == []


# ═══════════════════════════════════════════════════════════════════
# dispatch_on_alarm
# ═══════════════════════════════════════════════════════════════════
class TestDispatchOnAlarm:
    def test_override_channels_takes_priority(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.CRITICAL)
        db = MagicMock()
        with patch.object(d, "dispatch") as mock_disp, \
             patch("app.services.notification_dispatcher.audit_service") as mock_audit:
            d.dispatch_on_alarm(alarm, db=db, override_channels=["sms"])
        # 卡 6ca6092d: db+team_id 注入 (MagicMock db 解析 team → None → 平台级凭证)
        mock_disp.assert_called_once_with(alarm, ["sms"], db=db, team_id=None)
        mock_audit.log_crud.assert_called_once()

    def test_matches_existing_rule(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.WARNING)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _rule(id=1, name="r1", level="warning", channels=["email"])
        ]
        with patch.object(d, "dispatch") as mock_disp, \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=db)
        mock_disp.assert_called_once()
        # 匹配的规则渠道 (WARNING 不扩展)
        assert mock_disp.call_args.args[1] == ["email"]

    def test_default_channels_when_no_rule_matches(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.CRITICAL)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        with patch.object(d, "dispatch") as mock_disp, \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=db)
        mock_disp.assert_called_once_with(
            alarm, LEVEL_CHANNEL_MAP[AlarmLevel.CRITICAL], db=db, team_id=None
        )

    def test_db_none_creates_and_closes_session(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.INFO)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        with patch("app.services.notification_dispatcher.SessionLocal", return_value=mock_db) as mock_sl, \
             patch.object(d, "dispatch"), \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=None)
        mock_sl.assert_called_once()
        mock_db.close.assert_called_once()

    def test_provided_db_not_closed(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.INFO)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        with patch.object(d, "dispatch"), \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=db)
        # 传入的 db 不应由 dispatch_on_alarm 关闭
        db.close.assert_not_called()

    def test_exception_swallowed(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.INFO)
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        with patch.object(d, "dispatch"), \
             patch("app.services.notification_dispatcher.audit_service"):
            # 关键: 内部异常被 except 吞掉, 不向上抛
            d.dispatch_on_alarm(alarm, db=db)

    def test_disabled_rule_not_matched_falls_to_default(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.WARNING)
        db = MagicMock()
        # query 返回 1 条禁用规则 → _rule_matches False → 视为未匹配 → 默认渠道
        db.query.return_value.filter.return_value.all.return_value = [
            _rule(enabled=False, level="warning", channels=["email"])
        ]
        with patch.object(d, "dispatch") as mock_disp, \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=db)
        # 默认渠道 WARNING → im/logger/email
        assert mock_disp.call_args.args[1] == LEVEL_CHANNEL_MAP[AlarmLevel.WARNING]


# ═══════════════════════════════════════════════════════════════════
# 便捷方法 / 别名
# ═══════════════════════════════════════════════════════════════════
class TestConvenienceMethods:
    def test_notify_sms_with_alarm(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_sms") as m:
            d.notify_sms(alarm=_alarm())
        m.assert_called_once()

    def test_notify_sms_without_alarm_logs_mock(self):
        d = _new_dispatcher()
        # 不抛异常即可 (走 [SMS MOCK] 日志分支)
        d.notify_sms(message="hi", phone="13800000000")

    def test_send_sms_alias_delegates(self):
        d = _new_dispatcher()
        with patch.object(d, "notify_sms") as m:
            d.send_sms(message="hi", phone="123")
        m.assert_called_once_with(alarm=None, message="hi", phone="123")

    def test_notify_email_with_alarm(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_email") as m:
            d.notify_email(alarm=_alarm())
        m.assert_called_once()

    def test_notify_email_without_alarm_logs_mock(self):
        d = _new_dispatcher()
        d.notify_email(message="hi", to="x@x.com")  # 不抛

    def test_send_email_alias_delegates(self):
        d = _new_dispatcher()
        with patch.object(d, "notify_email") as m:
            d.send_email(message="hi", to="y@y.com")
        m.assert_called_once_with(alarm=None, message="hi", to="y@y.com")

    def test_notify_im_with_alarm(self):
        d = _new_dispatcher()
        with patch.object(d, "_send_im") as m:
            d.notify_im(alarm=_alarm())
        m.assert_called_once()

    def test_send_im_alias_delegates(self):
        d = _new_dispatcher()
        with patch.object(d, "notify_im") as m:
            d.send_im(message="hi")
        m.assert_called_once_with(alarm=None, message="hi")

    def test_notify_webhook_logs(self):
        d = _new_dispatcher()
        d.notify_webhook(url="http://x", payload={"a": 1})  # 不抛

    def test_send_webhook_alias_delegates(self):
        d = _new_dispatcher()
        with patch.object(d, "notify_webhook") as m:
            d.send_webhook(url="u", payload={"k": 1})
        m.assert_called_once_with(alarm=None, url="u", payload={"k": 1})

    def test_get_history_returns_empty_list(self):
        d = _new_dispatcher()
        assert d.get_history() == []
        assert d.get_history(page=2, page_size=5) == []


# ═══════════════════════════════════════════════════════════════════
# 邮件正文构建
# ═══════════════════════════════════════════════════════════════════
class TestBuildEmail:
    def test_subject_level_label(self):
        d = _new_dispatcher()
        subj = d._build_email_subject(_alarm(level=AlarmLevel.CRITICAL, content="过温"))
        assert "严重" in subj
        assert "过温" in subj

    def test_subject_escalation_tag(self):
        d = _new_dispatcher()
        subj = d._build_email_subject(_alarm(escalated_from="warning", content="x"))
        assert "已升级" in subj

    def test_subject_truncates_long_content(self):
        d = _new_dispatcher()
        long_content = "A" * 200
        subj = d._build_email_subject(_alarm(content=long_content))
        assert subj.count("A") == 80  # content[:80]

    def test_subject_unknown_level_uses_value(self):
        d = _new_dispatcher()
        subj = d._build_email_subject(_alarm(level=AlarmLevel.INFO))
        assert "提示" in subj

    def test_body_basic_fields(self):
        d = _new_dispatcher()
        body = d._build_email_body(_alarm(device_id=10, station_id=20, fault_code="0x01"))
        assert "10" in body
        assert "0x01" in body
        assert "warning" in body

    def test_body_includes_aggregation_when_gt_one(self):
        d = _new_dispatcher()
        body = d._build_email_body(_alarm(aggregation_count=5))
        assert "聚合" in body and "5" in body

    def test_body_skips_aggregation_when_one(self):
        d = _new_dispatcher()
        body = d._build_email_body(_alarm(aggregation_count=1))
        assert "聚合" not in body

    def test_body_includes_escalation(self):
        d = _new_dispatcher()
        body = d._build_email_body(_alarm(escalated_from="warning", escalated_at=datetime(2026, 1, 2)))
        assert "升级来源" in body
        assert "warning" in body

    def test_html_body_structure(self):
        d = _new_dispatcher()
        html = d._build_email_html_body(_alarm(level=AlarmLevel.FATAL, content="短路"))
        assert "<html>" in html
        assert "</html>" in html
        assert "fatal" in html
        assert "短路" in html


# ═══════════════════════════════════════════════════════════════════
# 各通道发送 (mock 分支 / 真实分支 / 异常吞)
# ═══════════════════════════════════════════════════════════════════
class TestSenders:
    def test_send_email_no_smtp_logs_mock(self):
        """SMTP 未配置时走 mock 日志分支，不再写审计（与其它通道一致）。"""
        d = _new_dispatcher()
        d._email_config["smtp_host"] = None
        with patch("app.services.notification_dispatcher.audit_service") as mock_audit:
            d._send_email(_alarm())
        mock_audit.log_crud.assert_not_called()

    def test_send_email_with_smtp_sends(self):
        d = _new_dispatcher()
        d._email_config = {
            "smtp_host": "smtp.x.com", "smtp_port": 587,
            "smtp_user": "u", "smtp_pass": "p", "from_addr": "f@x.com", "to_addr": "x",
        }
        d._admin_emails = ["a@x.com"]
        with patch("app.services.notification_dispatcher.smtplib") as mock_smtp:
            server = MagicMock()
            mock_smtp.SMTP.return_value.__enter__.return_value = server
            d._send_email(_alarm(level=AlarmLevel.WARNING))
        mock_smtp.SMTP.assert_called_once_with("smtp.x.com", 587, timeout=10)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("u", "p")
        server.sendmail.assert_called_once()

    def test_send_email_smtp_failure_swallowed(self):
        d = _new_dispatcher()
        d._email_config = {
            "smtp_host": "smtp.x.com", "smtp_port": 587,
            "smtp_user": "u", "smtp_pass": "p", "from_addr": "f@x.com", "to_addr": "x",
        }
        d._admin_emails = ["a@x.com"]
        with patch("app.services.notification_dispatcher.smtplib") as mock_smtp:
            mock_smtp.SMTP.side_effect = RuntimeError("conn refused")
            d._send_email(_alarm())  # except 吞掉, 不抛

    def test_send_email_urgent_attaches_html(self):
        # URGENT 级别 → 走 _build_email_html_body 分支附加富文本
        d = _new_dispatcher()
        d._email_config = {
            "smtp_host": "smtp.x.com", "smtp_port": 587,
            "smtp_user": "u", "smtp_pass": "p", "from_addr": "f@x.com", "to_addr": "x",
        }
        d._admin_emails = ["a@x.com"]
        with patch("app.services.notification_dispatcher.smtplib") as mock_smtp, \
             patch.object(d, "_build_email_html_body", wraps=d._build_email_html_body) as mock_html:
            server = MagicMock()
            mock_smtp.SMTP.return_value.__enter__.return_value = server
            d._send_email(_alarm(level=AlarmLevel.FATAL))  # FATAL ∈ URGENT_LEVELS
        mock_html.assert_called_once()
        server.sendmail.assert_called_once()

    def test_send_email_non_urgent_skips_html(self):
        # 非 URGENT 级别 → 不构建 HTML 正文
        d = _new_dispatcher()
        d._email_config = {
            "smtp_host": "smtp.x.com", "smtp_port": 587,
            "smtp_user": "u", "smtp_pass": "p", "from_addr": "f@x.com", "to_addr": "x",
        }
        d._admin_emails = ["a@x.com"]
        with patch("app.services.notification_dispatcher.smtplib") as mock_smtp, \
             patch.object(d, "_build_email_html_body") as mock_html:
            server = MagicMock()
            mock_smtp.SMTP.return_value.__enter__.return_value = server
            d._send_email(_alarm(level=AlarmLevel.WARNING))  # WARNING ∉ URGENT_LEVELS
        mock_html.assert_not_called()

    def test_send_im_b_no_webhook_logs_mock(self):
        d = _new_dispatcher()
        d._im_b_webhook = None
        d._send_im_b(_alarm())  # 不抛

    def test_send_im_b_with_webhook_posts_markdown(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
            mock_req.post.return_value = mock_resp
            result = d._send_im_b(_alarm())
        assert result is True
        mock_req.post.assert_called_once()
        url = mock_req.post.call_args.args[0]
        payload = mock_req.post.call_args.kwargs["json"]
        assert url == "http://im_b.example/hook"
        assert payload["msgtype"] == "markdown"

    def test_send_im_b_http_4xx_returns_false(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_req.post.return_value = mock_resp
            result = d._send_im_b(_alarm())
        assert result is False

    def test_send_im_b_errcode_nonzero_returns_false(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"errcode": 40001, "errmsg": "invalid webhook url"}
            mock_req.post.return_value = mock_resp
            result = d._send_im_b(_alarm())
        assert result is False

    def test_send_im_b_request_failure_swallowed(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = RuntimeError("network")
            d._send_im_b(_alarm())  # 不抛

    def test_send_sms_no_api_logs_mock(self):
        d = _new_dispatcher()
        d._sms_api_url = None
        d._send_sms(_alarm())  # 不抛

    def test_send_sms_with_api_posts_payload(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_req.post.return_value = mock_resp
            result = d._send_sms(_alarm(content="逆变器短路"))
        assert result is True
        mock_req.post.assert_called_once()
        payload = mock_req.post.call_args.kwargs["json"]
        assert "逆变器短路" in payload["content"]
        assert mock_req.post.call_args.kwargs["timeout"] == 5

    def test_send_sms_http_4xx_returns_false(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_resp.text = "Forbidden"
            mock_req.post.return_value = mock_resp
            result = d._send_sms(_alarm())
        assert result is False

    def test_send_sms_http_5xx_returns_false(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.text = "Service Unavailable"
            mock_req.post.return_value = mock_resp
            result = d._send_sms(_alarm())
        assert result is False

    def test_send_im_exception_swallowed(self):
        d = _new_dispatcher()
        with patch("app.services.notification_dispatcher.im_notify_service") as mock_fns:
            # notify_system_alarm 抛异常 → run_until_complete 传播 → except 吞掉
            mock_fns.notify_system_alarm.side_effect = RuntimeError("im down")
            result = d._send_im(_alarm())  # 不抛
        assert result is False

    def test_send_im_no_manual_loop_success_path(self):
        """成功路径不自建 event loop (卡 9fbc00ce: a7bc9343 反模式漏改)。

        旧实现 new_event_loop+set_event_loop+run_until_complete: close 后线程
        loop policy 悬垂指向 closed loop; 协程执行必须交由
        im_notify_service._run_coro_sync 管理 (asyncio.run 自建自清)。"""
        import asyncio
        d = _new_dispatcher()
        with patch("app.services.notification_dispatcher.im_notify_service") as mock_fns, \
             patch("asyncio.new_event_loop",
                   side_effect=AssertionError("禁止自建 event loop (卡 9fbc00ce)")):
            mock_fns.notify_system_alarm.return_value = object()
            mock_fns._run_coro_sync.return_value = True
            result = d._send_im(_alarm())
        assert result is True
        mock_fns._run_coro_sync.assert_called_once()

    def test_send_im_no_manual_loop_exception_path(self):
        """异常路径同样不自建 event loop, 异常被吞返回 False。"""
        import asyncio
        d = _new_dispatcher()
        with patch("app.services.notification_dispatcher.im_notify_service") as mock_fns, \
             patch("asyncio.new_event_loop",
                   side_effect=AssertionError("禁止自建 event loop (卡 9fbc00ce)")):
            mock_fns.notify_system_alarm.side_effect = RuntimeError("im down")
            result = d._send_im(_alarm())  # 不抛
        assert result is False
        mock_fns._run_coro_sync.assert_not_called()  # 协程构造即抛, 未到执行层

    @pytest.mark.asyncio
    async def test_send_im_in_running_loop_no_runtime_error(self):
        """async 上下文 (FastAPI async worker 同型) 调用不抛 RuntimeError 不静默 False。

        旧实现 run_until_complete 在运行中的 loop 里直接 RuntimeError → except 吞
        → return False, 告警IM通知静默丢弃; _run_coro_sync (卡 a7bc9343) 独立
        线程执行协程, 运行中 loop 不受影响。"""
        import asyncio
        d = _new_dispatcher()
        loop_before = asyncio.get_running_loop()
        with patch.object(nd_mod.im_notify_service, "notify_system_alarm",
                          new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = True
            result = d._send_im(_alarm())
        assert result is True  # 旧实现: RuntimeError → except 吞 → False
        assert mock_notify.await_count == 1  # 协程真实执行, 非静默丢弃
        assert asyncio.get_running_loop() is loop_before  # 运行中 loop 未被污染
        await asyncio.sleep(0)  # loop 仍可正常调度

    def test_log_notification_no_extra(self):
        d = _new_dispatcher()
        d._log_notification(_alarm())  # 不抛

    def test_log_notification_with_aggregation_and_escalation(self):
        d = _new_dispatcher()
        d._log_notification(_alarm(aggregation_count=3, escalated_from="warning"))  # 不抛


# ═══════════════════════════════════════════════════════════════════
# 模块常量完整性
# ═══════════════════════════════════════════════════════════════════
class TestModuleConstants:
    def test_level_channel_map_covers_all_levels(self):
        for lvl in (AlarmLevel.INFO, AlarmLevel.WARNING, AlarmLevel.CRITICAL, AlarmLevel.FATAL):
            assert lvl in LEVEL_CHANNEL_MAP
            assert isinstance(LEVEL_CHANNEL_MAP[lvl], list)

    def test_urgent_levels_subset(self):
        assert URGENT_LEVELS == {AlarmLevel.CRITICAL, AlarmLevel.FATAL}


# ═══════════════════════════════════════════════════════════════════
# 卡 6ca6092d: 告警链路凭证源统一 (ChannelConfig) + 瞬时失败重试
#
# 缺陷: 告警链路 alarm_rule_service → dispatch_on_alarm → _send_im_b/
# _send_sms 单次 requests.post 零重试, 凭证只读 settings 全局值, 团队级
# ChannelConfig 对告警完全不生效 —— 与健康路径 (notification_sender →
# dispatch_real_channel → _post_with_retry) 分裂。
# ═══════════════════════════════════════════════════════════════════

class _Resp:
    """requests/httpx 响应替身 (双路径共用)。"""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.text = "fake-body"
        self._body = body if body is not None else {}

    def json(self):
        return self._body


class TestLegacySenderRetry:
    """兼容底线: legacy _send_im_b/_send_sms 加 5xx/网络异常重试。

    对齐 channel_providers._post_with_retry 语义: 5xx 与网络异常重试
    (默认 2 次, 指数退避), 2xx/4xx 不重试, 业务拒绝 (errcode!=0) 不重试。"""

    @pytest.fixture(autouse=True)
    def _zero_backoff(self, monkeypatch):
        # 退避归零: 重试语义测试不真睡 (常量 GREEN 后存在; raising=False 兼容 RED)
        monkeypatch.setattr(nd_mod, "_RETRY_BACKOFF", 0.0, raising=False)

    def test_sms_503_then_200_retries_and_succeeds(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [_Resp(503), _Resp(200)]
            result = d._send_sms(_alarm())
        assert result is True
        assert mock_req.post.call_count == 2  # 503 → 重试 → 200

    def test_sms_4xx_no_retry(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [_Resp(403)]
            result = d._send_sms(_alarm())
        assert result is False
        assert mock_req.post.call_count == 1  # 4xx 立即失败, 不重试

    def test_sms_network_exception_retries_then_succeeds(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [ConnectionError("network blip"), _Resp(200)]
            result = d._send_sms(_alarm())
        assert result is True
        assert mock_req.post.call_count == 2

    def test_sms_5xx_exhausted_returns_false(self):
        d = _new_dispatcher()
        d._sms_api_url = "http://sms.example/send"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [_Resp(503)] * 3
            result = d._send_sms(_alarm())
        assert result is False
        assert mock_req.post.call_count == 3  # 1 次 + 2 次重试耗尽

    def test_im_b_503_then_200_retries_and_succeeds(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [
                _Resp(503), _Resp(200, {"errcode": 0, "errmsg": "ok"})
            ]
            result = d._send_im_b(_alarm())
        assert result is True
        assert mock_req.post.call_count == 2

    def test_im_b_4xx_no_retry(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [_Resp(404)]
            result = d._send_im_b(_alarm())
        assert result is False
        assert mock_req.post.call_count == 1

    def test_im_b_network_exception_retries_then_succeeds(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [
                ConnectionError("network blip"),
                _Resp(200, {"errcode": 0, "errmsg": "ok"}),
            ]
            result = d._send_im_b(_alarm())
        assert result is True
        assert mock_req.post.call_count == 2

    def test_im_b_5xx_exhausted_returns_false(self):
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [_Resp(503)] * 3
            result = d._send_im_b(_alarm())
        assert result is False
        assert mock_req.post.call_count == 3

    def test_im_b_business_reject_no_retry(self):
        # 200 但 errcode!=0 = 业务拒绝, 不是瞬时故障, 不重试
        d = _new_dispatcher()
        d._im_b_webhook = "http://im_b.example/hook"
        with patch("app.services.notification_dispatcher.requests") as mock_req:
            mock_req.post.side_effect = [_Resp(200, {"errcode": 40001, "errmsg": "bad"})]
            result = d._send_im_b(_alarm())
        assert result is False
        assert mock_req.post.call_count == 1


# ─── 告警链路 ChannelConfig 路由的 db/行替身 ───

class _StationRow:
    def __init__(self, team_id):
        self.team_id = team_id


class _RouteQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _RouteDB:
    """query(Model) → filter().first() 按模型路由 (Station / ChannelConfig)。"""

    def __init__(self, station=None, channel_config=None):
        self._rows = {Station: station, ChannelConfig: channel_config}

    def query(self, model):
        return _RouteQuery(self._rows.get(model))


class TestAlarmChannelConfigRouting:
    """告警链路 (dispatch_on_alarm → dispatch) 的 im_b/sms 渠道优先读
    团队级 ChannelConfig (站点 → 团队), 未配置回退 legacy settings 路径;
    im/email/logger 保持 legacy 语义 (IM走 im_notify_service)。"""

    def test_sms_routes_to_team_channel_config(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.FATAL, station_id=20)
        db = _RouteDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel",
                   return_value={"status": "sent", "channel": "sms"}) as mock_real, \
             patch.object(d, "_send_sms") as legacy:
            d.dispatch_on_alarm(alarm, db=db, override_channels=["sms"])
        mock_real.assert_called_once()
        assert mock_real.call_args.args[0] == "sms"
        assert mock_real.call_args.args[1] == 7  # 站点 → 团队级凭证
        legacy.assert_not_called()

    def test_im_b_maps_to_wecom_channel_config(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.CRITICAL, station_id=20)
        db = _RouteDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel",
                   return_value={"status": "sent", "channel": "wecom"}) as mock_real, \
             patch.object(d, "_send_im_b") as legacy:
            d.dispatch_on_alarm(alarm, db=db, override_channels=["im_b"])
        mock_real.assert_called_once()
        assert mock_real.call_args.args[0] == "wecom"  # dispatcher 'im_b' → ChannelType 'wecom'
        assert mock_real.call_args.args[1] == 7
        legacy.assert_not_called()

    def test_no_channel_config_falls_back_to_legacy(self):
        # 团队/平台都未配置 → dispatch_real_channel skipped → 回退 legacy settings 路径
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.FATAL, station_id=20)
        db = _RouteDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel",
                   return_value={"status": "skipped", "channel": "sms",
                                 "reason": "no_config"}) as mock_real, \
             patch.object(d, "_send_sms") as legacy:
            d.dispatch_on_alarm(alarm, db=db, override_channels=["sms"])
        mock_real.assert_called_once()
        legacy.assert_called_once()

    def test_real_send_failed_marks_channel_failed(self):
        d = _new_dispatcher()
        db = _RouteDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel",
                   return_value={"status": "failed", "channel": "sms",
                                 "error": "http 503"}) as mock_real, \
             patch.object(d, "_send_sms") as legacy:
            r = d.dispatch(alarm=_alarm(), channels=["sms"], db=db, team_id=7)
        mock_real.assert_called_once()
        legacy.assert_not_called()  # 真实路径已配置, 失败不再回退 (避免双发)
        assert r["channels"][0]["channel"] == "sms"
        assert r["channels"][0]["status"] == "failed"
        assert "http 503" in r["channels"][0]["error"]

    def test_im_stays_on_im_notify_service(self):
        # IM已有官方签名路径 (im_notify_service), 不迁 ChannelConfig, 勿回退
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.WARNING, station_id=20)
        db = _RouteDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel") as mock_real, \
             patch.object(d, "_send_im") as mf:
            d.dispatch_on_alarm(alarm, db=db, override_channels=["im"])
        mock_real.assert_not_called()
        mf.assert_called_once()

    def test_email_and_logger_stay_legacy(self):
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.CRITICAL, station_id=20)
        db = _RouteDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel") as mock_real, \
             patch.object(d, "_send_email") as me, patch.object(d, "_log_notification") as ml:
            d.dispatch_on_alarm(alarm, db=db, override_channels=["email", "logger"])
        mock_real.assert_not_called()
        me.assert_called_once()
        ml.assert_called_once()

    def test_station_missing_resolves_team_none(self):
        # 站点行缺失 → team_id=None → 平台级凭证 (_lookup_channel_config 平台回退)
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.FATAL, station_id=999)
        db = _RouteDB(station=None)
        with patch("app.services.notification_dispatcher.dispatch_real_channel",
                   return_value={"status": "sent", "channel": "sms"}) as mock_real, \
             patch.object(d, "_send_sms"):
            d.dispatch_on_alarm(alarm, db=db, override_channels=["sms"])
        assert mock_real.call_args.args[1] is None

    def test_team_resolution_db_error_degrades_to_none(self):
        # Station 查询异常 → 团队解析降级 None, 告警派发本身不受影响
        class _PartialBoomDB(_RouteDB):
            def query(self, model):
                if model is Station:
                    raise RuntimeError("station table down")
                return super().query(model)

        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.FATAL, station_id=20)
        db = _PartialBoomDB(station=_StationRow(7))
        with patch("app.services.notification_dispatcher.dispatch_real_channel",
                   return_value={"status": "sent", "channel": "sms"}) as mock_real, \
             patch.object(d, "_send_sms"):
            d.dispatch_on_alarm(alarm, db=db, override_channels=["sms"])  # 不抛
        assert mock_real.call_args.args[1] is None


class _AsyncFakeClient:
    """httpx.AsyncClient 替身 (注入式, 同 test_channel_providers.FakeClient 形状)。

    responses 依次弹出; 记录全部 post 调用供断言。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []
        self.aclosed = False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self._responses.pop(0)

    async def aclose(self):
        self.aclosed = True


class TestAlarmRealChannelRetryIntegration:
    """告警链路 → dispatch_real_channel → _post_with_retry 端到端:
    FakeClient 模拟单次 503 后 200, 断言重试成功且凭证来自 ChannelConfig。"""

    @pytest.fixture(autouse=True)
    def _no_backoff(self, monkeypatch):
        from app.services import channel_providers as cp

        async def _no_sleep(_):
            return None

        monkeypatch.setattr(cp.asyncio, "sleep", _no_sleep)

    def test_wecom_503_then_200_retried_via_channel_config(self):
        from app.services import channel_providers as cp

        d = _new_dispatcher()
        cfg_row = SimpleNamespace(
            config={"webhook_url": "http://wecom.example/hook"},
            channel=ChannelType.WECOM, team_id=7, enabled=True,
        )
        db = _RouteDB(station=_StationRow(7), channel_config=cfg_row)
        fake = _AsyncFakeClient([_Resp(503), _Resp(200, {"errcode": 0, "errmsg": "ok"})])
        with patch.object(cp.httpx, "AsyncClient", return_value=fake):
            r = d.dispatch(
                alarm=_alarm(level=AlarmLevel.CRITICAL, station_id=20),
                channels=["im_b"], db=db, team_id=7,
            )
        assert r["channels"][0]["channel"] == "im_b"
        assert r["channels"][0]["status"] == "sent"
        assert len(fake.posts) == 2  # 503 → 重试 → 200
        assert fake.posts[0][0] == "http://wecom.example/hook"  # 凭证来自 ChannelConfig
        assert fake.aclosed is True
        payload = fake.posts[0][1]["json"]
        assert payload["msgtype"] == "markdown"
        assert "天链告警通知" in payload["markdown"]["content"]

    def test_sms_skipped_when_no_channel_config_falls_back_legacy(self):
        # 无 ChannelConfig → skipped → legacy mock 分支 (sms_api_url 未配置)
        d = _new_dispatcher()
        db = _RouteDB(station=_StationRow(7), channel_config=None)
        with patch.object(d, "_send_sms", return_value=True) as legacy:
            r = d.dispatch(
                alarm=_alarm(level=AlarmLevel.FATAL), channels=["sms"], db=db, team_id=7,
            )
        legacy.assert_called_once()
        assert r["channels"][0]["status"] == "sent"


class TestAlarmRealDBChannelConfig:
    """真库端到端: 告警站点团队 → ChannelConfig 命中 + 503 后 200 重试。"""

    @pytest.fixture(autouse=True)
    def _no_backoff(self, monkeypatch):
        from app.services import channel_providers as cp

        async def _no_sleep(_):
            return None

        monkeypatch.setattr(cp.asyncio, "sleep", _no_sleep)

    def test_team_level_channel_config_end_to_end(self, test_db):
        from app.services import channel_providers as cp
        from app.models.user import Team
        from app.models.station import StationStatus

        db = test_db["session"]
        team = Team(name="团队-6ca6092d")
        db.add(team)
        db.flush()
        station = Station(
            name="站点-6ca6092d", code="ST-6ca6092d",
            status=StationStatus.NORMAL, team_id=team.id,
        )
        db.add(station)
        db.flush()
        db.add(ChannelConfig(
            team_id=team.id, channel=ChannelType.WECOM,
            config={"webhook_url": "http://wecom.example/hook"}, enabled=True,
        ))
        db.commit()

        fake = _AsyncFakeClient([_Resp(503), _Resp(200, {"errcode": 0, "errmsg": "ok"})])
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.CRITICAL, station_id=station.id)
        with patch.object(cp.httpx, "AsyncClient", return_value=fake), \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=db, override_channels=["im_b"])

        assert len(fake.posts) == 2  # 503 重试后 200
        assert fake.posts[0][0] == "http://wecom.example/hook"  # 团队级凭证命中
        payload = fake.posts[0][1]["json"]
        assert payload["msgtype"] == "markdown"
        assert "天链告警通知" in payload["markdown"]["content"]

    def test_platform_level_fallback_when_station_has_no_team(self, test_db):
        from app.services import channel_providers as cp
        from app.models.station import StationStatus

        db = test_db["session"]
        station = Station(
            name="无团队站-6ca6092d", code="ST-NOTEAM-6ca6092d",
            status=StationStatus.NORMAL, team_id=None,
        )
        db.add(station)
        db.flush()
        db.add(ChannelConfig(
            team_id=None, channel=ChannelType.WECOM,
            config={"webhook_url": "http://wecom.example/platform-hook"}, enabled=True,
        ))
        db.commit()

        fake = _AsyncFakeClient([_Resp(503), _Resp(200, {"errcode": 0, "errmsg": "ok"})])
        d = _new_dispatcher()
        alarm = _alarm(level=AlarmLevel.CRITICAL, station_id=station.id)
        with patch.object(cp.httpx, "AsyncClient", return_value=fake), \
             patch("app.services.notification_dispatcher.audit_service"):
            d.dispatch_on_alarm(alarm, db=db, override_channels=["im_b"])

        assert len(fake.posts) == 2
        assert fake.posts[0][0] == "http://wecom.example/platform-hook"  # 平台级回退
