"""NotificationSender 单元测试 (卡 a32fb821)

被测模块: app/services/notification_sender.py (486 行)

双轨覆盖:
  A. 纯逻辑 helper (SimpleNamespace 构造 config/template，不依赖 DB):
     _format_template / _is_quiet_time / _default_content / _is_channel_enabled /
     _resolve_channels / _render_content / _render_subject /
     _resolve_receivers (固定接收人去重 + 角色解析) /
     _find_configs / _find_templates / _dispatch_channel / _log_notification
  B. send 主流程 (真实 test_db + seed config/template + mock dispatcher):
     no_config / 正常 sent / quiet 静默 / dispatch failed / channel 跳过 /
     no_channels / error 分支 / db=None 自管 session /
     send_workorder_dispatch / send_workorder_urge / send_alarm_notification (落 alarm_notifications)
  C. _record_alarm_notifications: 空短路 / 正常持久化 / db=None 自管 / 异常吞掉
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import notification_sender as ns_module
from app.services.notification_sender import (
    NotificationSender,
    EVENT_CHANNEL_MAP,
)
from app.models.notification_config import (
    NotificationConfig, NotificationTemplate, NotificationLog,
)
from app.models.alarm_notification import AlarmNotification


# ========== helpers ==========

def _cfg(**kw):
    """构造一个内存 config (SimpleNamespace)，纯逻辑测试用。"""
    defaults = dict(
        id=1,
        sms_enabled=False, email_enabled=False, app_push_enabled=False,
        im_b_enabled=False, im_enabled=False,
        receivers=[], receiver_roles=[],
        quiet_start=None, quiet_end=None,
        timezone="Asia/Shanghai",  # 卡 ac0a7aa7: _is_quiet_time 读 per-config timezone
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _seed_config(db, **kw):
    """向真实 test_db 插入一条 NotificationConfig。"""
    defaults = dict(
        name="cfg", scope_type="tenant",
        sms_enabled=False, email_enabled=False, app_push_enabled=False,
        im_b_enabled=False, im_enabled=False,
        trigger_events=["workorder_dispatch"], receivers=[], receiver_roles=[],
        quiet_start=None, quiet_end=None, priority=1, enabled=True,
    )
    defaults.update(kw)
    cfg = NotificationConfig(**defaults)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def _seed_template(db, channel, event_type, content, subject=None):
    tpl = NotificationTemplate(
        name=f"t-{channel}", code=f"{event_type}_{channel}",
        channel=channel, event_type=event_type, subject=subject,
        content=content, enabled=True,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@pytest.fixture
def sender():
    """独立 sender 实例，dispatcher 已 mock。"""
    s = NotificationSender()
    s._dispatcher = MagicMock()
    return s


# ========== EVENT_CHANNEL_MAP ==========

def test_event_channel_map_constants():
    assert "workorder_dispatch" in EVENT_CHANNEL_MAP
    assert EVENT_CHANNEL_MAP["alarm_trigger"] == ["sms", "email", "app_push", "im"]
    # 未知事件 fallback 由 _resolve_channels 处理


# ========== _format_template ==========

def test_format_template_basic(sender):
    assert sender._format_template("hello {name}", {"name": "石猴"}) == "hello 石猴"


def test_format_template_multiple_and_missing_kept(sender):
    out = sender._format_template("{a}+{b}+{c}", {"a": 1, "b": 2})
    assert out == "1+2+{c}"  # 缺失变量原样保留


def test_format_template_non_string_value(sender):
    assert sender._format_template("id={x}", {"x": 99}) == "id=99"


# ========== _is_quiet_time (卡 ac0a7aa7: now= 注入替代 monkeypatch naive datetime) ==========

def test_is_quiet_time_no_window(sender):
    assert sender._is_quiet_time(_cfg()) is False
    assert sender._is_quiet_time(_cfg(quiet_start="10:00")) is False  # 缺 quiet_end


def test_is_quiet_time_within_same_day(sender):
    cfg = _cfg(quiet_start="10:00", quiet_end="12:00")
    # 注入 naive 11:00 (在 10:00-12:00 内), 按表面时分判定
    assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 11, 0)) is True


def test_is_quiet_time_outside_same_day(sender):
    cfg = _cfg(quiet_start="10:00", quiet_end="12:00")
    assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 13, 0)) is False


def test_is_quiet_time_overnight_window(sender):
    # 跨天窗口 22:00-08:00
    cfg = _cfg(quiet_start="22:00", quiet_end="08:00")
    # 23:30 >= 22:00 → quiet
    assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 23, 30)) is True


def test_is_quiet_time_overnight_outside(sender):
    cfg = _cfg(quiet_start="22:00", quiet_end="08:00")
    # 14:00 既 <22:00 又 >08:00 → 不静默
    assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 14, 0)) is False


def test_is_quiet_time_bad_format_returns_false(sender):
    # quiet_start 非法格式 → split/int 失败 → 异常捕获返回 False
    cfg = _cfg(quiet_start="bad", quiet_end="12:00")
    assert sender._is_quiet_time(cfg, now=datetime(2026, 1, 1, 11, 0)) is False


# ========== _is_channel_enabled ==========

@pytest.mark.parametrize("channel,attr", [
    ("sms", "sms_enabled"),
    ("email", "email_enabled"),
    ("app_push", "app_push_enabled"),
    ("im_b", "im_b_enabled"),
    ("im", "im_enabled"),
])
def test_is_channel_enabled_truthy_and_falsy(sender, channel, attr):
    assert sender._is_channel_enabled(_cfg(**{attr: True}), channel) is True
    assert sender._is_channel_enabled(_cfg(), channel) is False


def test_is_channel_enabled_unknown_channel(sender):
    assert sender._is_channel_enabled(_cfg(), "telegram") is False


# ========== _resolve_channels ==========

def test_resolve_channels_from_configs(sender):
    cfg = _cfg(sms_enabled=True, im_enabled=True)
    assert set(sender._resolve_channels([cfg], "workorder_dispatch")) == {"sms", "im"}


def test_resolve_channels_default_when_none_configured(sender):
    # config 无任何渠道 → 走 EVENT_CHANNEL_MAP 默认
    out = set(sender._resolve_channels([_cfg()], "alarm_trigger"))
    assert out == {"sms", "email", "app_push", "im"}


def test_resolve_channels_default_app_push_for_unknown_event(sender):
    out = sender._resolve_channels([_cfg()], "totally_unknown_event")
    assert out == ["app_push"]  # fallback


# ========== _render_content / _render_subject ==========

def test_render_content_with_template(sender):
    tpl = SimpleNamespace(content="hi {name}", subject=None)
    assert sender._render_content({"sms": tpl}, "sms", {"name": "张三"}) == "hi 张三"


def test_render_content_default_when_no_template(sender):
    out = sender._render_content({}, "sms", {
        "_event_type": "workorder_dispatch",
        "workorder_id": "WO1", "device_name": "d", "station_name": "s",
    })
    assert "WO1" in out and "工单" in out


def test_render_subject_with_template(sender):
    tpl = SimpleNamespace(subject="主题 {id}", content="x")
    assert sender._render_subject({"email": tpl}, "email", {"id": 9}) == "主题 9"


def test_render_subject_none_when_no_template(sender):
    assert sender._render_subject({}, "email", {}) is None


# ========== _default_content ==========

def test_default_content_workorder_branch(sender):
    out = sender._default_content("sms", {
        "_event_type": "workorder_dispatch",
        "workorder_id": "WO1", "device_name": "d", "station_name": "s",
    })
    assert "工单" in out and "WO1" in out and "d" in out


def test_default_content_alarm_branch(sender):
    out = sender._default_content("sms", {
        "alarm_id": "alarm-1", "level": "critical",
        "alarm_content": "过温", "device_id": 7,
    })
    assert "告警" in out and "过温" in out


def test_default_content_fallback_branch(sender):
    out = sender._default_content("sms", {"foo": "bar"})
    assert "通知" in out


# ========== _resolve_receivers ==========

def test_resolve_receivers_fixed_dict_and_string(sender):
    cfg = _cfg(receivers=[
        {"type": "user", "id": "1", "name": "u1"},
        "13800000000",  # 字符串接收人
    ])
    out = sender._resolve_receivers([cfg], {}, MagicMock())
    assert len(out) == 2
    ids = {r["id"] for r in out}
    assert ids == {"1", "13800000000"}
    # 字符串接收人转成 phone 类型
    phone_recv = [r for r in out if r["id"] == "13800000000"][0]
    assert phone_recv["type"] == "phone"


def test_resolve_receivers_dedup_by_id(sender):
    cfg = _cfg(receivers=[
        {"type": "user", "id": "1", "name": "u1"},
        {"type": "user", "id": "1", "name": "dup"},
    ])
    db = MagicMock()
    out = sender._resolve_receivers([cfg], {}, db)
    assert len(out) == 1
    assert out[0]["name"] == "u1"
    db.query.assert_not_called()  # 无 receiver_roles 不查 User


def test_resolve_receivers_with_roles(monkeypatch, sender):
    # 假扮 User 类: role 列需支持 .in_() (批量查询用), 用 MagicMock 充当列对象;
    # User 模型只有 status 列 (无 is_active), 故 status 用真实字段名。
    fake_user_cls = SimpleNamespace(role=MagicMock(), status="active")
    monkeypatch.setattr(ns_module, "User", fake_user_cls)

    db = MagicMock()
    fake_user = SimpleNamespace(
        id=5, role="engineer", name="李四", username="lisi", phone="139", email="l@x.com"
    )
    db.query.return_value.filter.return_value.all.return_value = [fake_user]

    cfg = _cfg(
        receivers=[{"type": "user", "id": "1", "name": "u1"}],
        receiver_roles=["engineer"],
    )
    out = sender._resolve_receivers([cfg], {}, db)
    # 1 固定 + 1 角色 = 2
    assert len(out) == 2
    role_user = [r for r in out if r.get("id") == "5"][0]
    assert role_user["type"] == "user"
    assert role_user["phone"] == "139"
    assert role_user["name"] == "李四"


# ========== _find_configs / _find_templates ==========

def test_find_configs_match_event(sender):
    db = MagicMock()
    matched = [SimpleNamespace(id=1)]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = matched
    out = sender._find_configs(db, "workorder_dispatch")
    assert out == matched


def test_find_configs_fallback_tenant_when_no_match(sender):
    db = MagicMock()
    main_q = MagicMock()
    main_q.filter.return_value.order_by.return_value.all.return_value = []
    fallback_q = MagicMock()
    fallback_cfg = SimpleNamespace(id=9)
    fallback_q.filter.return_value.order_by.return_value.all.return_value = [fallback_cfg]
    db.query.side_effect = [main_q, fallback_q]  # 主匹配空 → fallback
    out = sender._find_configs(db, "no_such_event")
    assert out == [fallback_cfg]


def test_find_templates_indexes_by_channel(sender):
    db = MagicMock()
    tpl_sms = SimpleNamespace(id=1, code="c1", channel="sms", content="hi", subject="s")
    tpl_email = SimpleNamespace(id=2, code="c2", channel="email", content="hi", subject="s")
    db.query.return_value.filter.return_value.all.return_value = [tpl_sms, tpl_email]
    out = sender._find_templates(db, "workorder_dispatch", ["sms", "email"])
    assert set(out.keys()) == {"sms", "email"}
    assert out["sms"] is tpl_sms
    assert out["email"] is tpl_email


def test_find_templates_missing_returns_empty(sender):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    assert sender._find_templates(db, "x", ["sms"]) == {}


# ========== _dispatch_channel ==========

def test_dispatch_sms_uses_phone(sender):
    sender._dispatch_channel("sms", {"phone": "138", "id": "138"}, "msg", None, {})
    sender._dispatcher.notify_sms.assert_called_once_with(message="msg", phone="138")


def test_dispatch_sms_fallback_to_id_when_no_phone(sender):
    sender._dispatch_channel("sms", {"id": "x"}, "msg", None, {})
    sender._dispatcher.notify_sms.assert_called_once_with(message="msg", phone="x")


def test_dispatch_email(sender):
    sender._dispatch_channel("email", {"email": "a@b.com"}, "msg", "subj", {})
    sender._dispatcher.notify_email.assert_called_once_with(message="msg", to="a@b.com")


def test_dispatch_im(sender):
    sender._dispatch_channel("im", {}, "msg", None, {})
    sender._dispatcher.notify_im.assert_called_once_with(message="msg")


def test_dispatch_mock_only_channels_do_not_call_dispatcher(sender):
    # app_push / im_b / 未知渠道 仅 logger.info，不触达 dispatcher
    sender._dispatch_channel("app_push", {"name": "u"}, "msg", None, {})
    sender._dispatch_channel("im_b", {"name": "u"}, "msg", None, {})
    sender._dispatch_channel("telegram", {"name": "u"}, "msg", None, {})
    sender._dispatcher.notify_sms.assert_not_called()
    sender._dispatcher.notify_email.assert_not_called()
    sender._dispatcher.notify_im.assert_not_called()


# ========== _log_notification ==========

def test_log_notification_sent_sets_sent_at(sender):
    db = MagicMock()
    tpl = SimpleNamespace(id=3, code="c1")
    sender._log_notification(
        db, 10, "workorder_dispatch", "WO1", {"k": "v"}, "sms", tpl,
        {"type": "user", "id": "138", "name": "张三"}, "subj", "content", "sent",
    )
    db.add.assert_called_once()
    log = db.add.call_args[0][0]
    assert isinstance(log, NotificationLog)
    assert log.config_id == 10
    assert log.channel == "sms"
    assert log.template_id == 3
    assert log.status == "sent"
    assert log.sent_at is not None


def test_log_notification_failed_no_sent_at(sender):
    db = MagicMock()
    sender._log_notification(
        db, None, "evt", "id", {}, "sms", None,
        {"type": "phone", "id": "x"}, None, "c", "failed", "err",
    )
    log = db.add.call_args[0][0]
    assert log.sent_at is None
    assert log.error_message == "err"
    assert log.template_id is None  # 无模板


# ========== _record_alarm_notifications ==========

def test_record_alarm_notifications_noop_on_empty(sender):
    db = MagicMock()
    sender._record_alarm_notifications(db, 1, {"results": []})
    sender._record_alarm_notifications(db, 1, None)
    db.add.assert_not_called()


def test_record_alarm_notifications_persists(test_db):
    sender = NotificationSender()
    db = test_db["session"]
    result = {"results": [
        {"channel": "sms", "receiver": "138", "status": "sent"},
        {"channel": "sms", "receiver": "139", "status": "failed", "error": "boom"},
    ]}
    sender._record_alarm_notifications(db, 77, result)
    db.commit()
    rows = db.query(AlarmNotification).filter(AlarmNotification.alarm_id == 77).all()
    assert len(rows) == 2
    assert {r.status for r in rows} == {"sent", "failed"}
    failed = [r for r in rows if r.status == "failed"][0]
    assert failed.result == "boom"  # failed 的 error 落到 result
    assert failed.channel == "sms"


def test_record_alarm_notifications_creates_session_when_db_none(monkeypatch, test_db):
    # db=None → 内部 SessionLocal() (notification_sender 模块级名字，手动 patch 指向测试库)
    monkeypatch.setattr(ns_module, "SessionLocal", test_db["SessionLocal"])
    sender = NotificationSender()
    sender._record_alarm_notifications(None, 88, {
        "results": [{"channel": "sms", "receiver": "x", "status": "sent"}]
    })
    rows = test_db["session"].query(AlarmNotification).filter(
        AlarmNotification.alarm_id == 88
    ).all()
    assert len(rows) == 1


def test_record_alarm_notifications_swallows_exception():
    # 写库失败不影响主流程 (仅记日志)，传入的 db 非 None → 不 rollback
    sender = NotificationSender()
    db = MagicMock()
    db.commit.side_effect = RuntimeError("db down")
    sender._record_alarm_notifications(db, 1, {
        "results": [{"channel": "sms", "status": "sent"}]
    })  # 不抛异常


# ========== send 主流程 (真实 DB) ==========

def test_send_no_config_returns_no_config(test_db):
    sender = NotificationSender()
    result = sender.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"},
                         db=test_db["session"])
    assert result["status"] == "no_config"
    assert result["results"] == []


def test_send_normal_flow_sent_and_logs(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    db = test_db["session"]
    cfg = _seed_config(db, sms_enabled=True, trigger_events=["workorder_dispatch"])
    _seed_template(db, "sms", "workorder_dispatch",
                   "工单 {workorder_id} 派给 {engineer_name}")
    result = sender.send(
        "workorder_dispatch", "WO-001",
        {"workorder_id": "WO-001", "engineer_name": "张三",
         "device_name": "inv", "station_name": "st"},
        db=db,
        override_channels=["sms"],
        override_receivers=[{"type": "user", "id": "138", "name": "张三", "phone": "13800000000"}],
    )
    assert result["status"] == "ok"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "sent"
    sender._dispatcher.notify_sms.assert_called_once()
    msg = sender._dispatcher.notify_sms.call_args.kwargs["message"]
    assert "WO-001" in msg and "张三" in msg
    # NotificationLog 落库
    logs = db.query(NotificationLog).all()
    assert len(logs) == 1
    assert logs[0].status == "sent"
    assert logs[0].config_id == cfg.id


def test_send_quiet_time_blocks(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    db = test_db["session"]
    _seed_config(db, sms_enabled=True, trigger_events=["workorder_dispatch"],
                 quiet_start="00:00", quiet_end="23:59")  # 全天静默
    result = sender.send(
        "workorder_dispatch", "WO1", {"workorder_id": "WO1"},
        db=db, override_channels=["sms"],
        override_receivers=[{"type": "user", "id": "138", "name": "x", "phone": "138"}],
    )
    assert result["status"] == "ok"
    assert result["results"][0]["status"] == "quiet"
    sender._dispatcher.notify_sms.assert_not_called()


def test_send_dispatch_failed_records_error(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    sender._dispatcher.notify_sms.side_effect = RuntimeError("sms gateway down")
    db = test_db["session"]
    _seed_config(db, sms_enabled=True, trigger_events=["workorder_dispatch"])
    result = sender.send(
        "workorder_dispatch", "WO1", {"workorder_id": "WO1"},
        db=db, override_channels=["sms"],
        override_receivers=[{"type": "user", "id": "138", "name": "x", "phone": "138"}],
    )
    assert result["status"] == "ok"
    assert result["results"][0]["status"] == "failed"
    assert "服务内部错误" in result["results"][0]["error"]
    logs = db.query(NotificationLog).all()
    assert any(l.status == "failed" for l in logs)


def test_send_skips_channel_not_enabled_in_config(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    db = test_db["session"]
    # config 只启 sms；override 含 email → email 无 channel_configs → continue
    _seed_config(db, sms_enabled=True, email_enabled=False,
                 trigger_events=["workorder_dispatch"])
    result = sender.send(
        "workorder_dispatch", "WO1", {"workorder_id": "WO1"}, db=db,
        override_channels=["sms", "email"],
        override_receivers=[{"type": "user", "id": "138", "name": "x", "phone": "138"}],
    )
    channels = [r["channel"] for r in result["results"]]
    assert "sms" in channels
    assert "email" not in channels


def test_send_no_channels_returns_no_channels(test_db, monkeypatch):
    sender = NotificationSender()
    db = test_db["session"]
    _seed_config(db, sms_enabled=True, trigger_events=["workorder_dispatch"])
    monkeypatch.setattr(sender, "_resolve_channels", lambda *a, **k: [])
    result = sender.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"}, db=db)
    assert result["status"] == "no_channels"


def test_send_error_branch(test_db, monkeypatch):
    sender = NotificationSender()
    monkeypatch.setattr(sender, "_find_configs",
                        MagicMock(side_effect=RuntimeError("db explode")))
    result = sender.send("workorder_dispatch", "WO1", {}, db=test_db["session"])
    assert result["status"] == "error"
    # error 字段须脱敏，原始异常文本不得泄露（仅 ERROR 日志保留原始信息）
    assert result["error"] == "服务内部错误，请稍后重试"
    assert "db explode" not in result["error"]


def test_send_db_none_manages_own_session(monkeypatch, test_db):
    # db=None → 内部 SessionLocal(); 无 config → no_config，验证 session 正常开关
    monkeypatch.setattr(ns_module, "SessionLocal", test_db["SessionLocal"])
    sender = NotificationSender()
    result = sender.send("workorder_dispatch", "WO1", {})
    assert result["status"] == "no_config"


# ========== 包装方法 ==========

def test_send_workorder_dispatch_wraps_and_sends(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    db = test_db["session"]
    _seed_config(db, sms_enabled=True, trigger_events=["workorder_dispatch"])
    _seed_template(db, "sms", "workorder_dispatch", "新工单 {workorder_id}")
    result = sender.send_workorder_dispatch(
        workorder_id="WO-9", engineer_name="张三", engineer_phone="13800000000",
        device_name="逆变器", station_name="站点A", db=db,
    )
    assert result["status"] == "ok"
    sender._dispatcher.notify_sms.assert_called_once()
    # override_receivers 注入工程师，phone 落到发送参数
    assert sender._dispatcher.notify_sms.call_args.kwargs["phone"] == "13800000000"


def test_send_workorder_urge_wraps_and_sends(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    db = test_db["session"]
    _seed_config(db, sms_enabled=True, trigger_events=["workorder_urge"])
    result = sender.send_workorder_urge(
        workorder_id="WO-3", engineer_name="李四", engineer_phone="13900000000",
        device_name="储能", db=db,
    )
    assert result["status"] == "ok"
    sender._dispatcher.notify_sms.assert_called_once()


def test_send_alarm_notification_persists_records(test_db):
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    db = test_db["session"]
    _seed_config(
        db, sms_enabled=True, trigger_events=["alarm_trigger"],
        receivers=[{"type": "user", "id": "138", "name": "x", "phone": "13800000000"}],
    )
    result = sender.send_alarm_notification(
        alarm_id=555, alarm_content="过温", device_id=7,
        station_id=3, level="critical", db=db,
    )
    assert result["status"] == "ok"
    rows = db.query(AlarmNotification).filter(AlarmNotification.alarm_id == 555).all()
    assert len(rows) >= 1
    assert all(r.alarm_id == 555 for r in rows)
    assert all(r.channel == "sms" for r in rows)


# ========== 边缘分支补全 ==========

def test_resolve_channels_all_five_channels(sender):
    cfg = _cfg(sms_enabled=True, email_enabled=True, app_push_enabled=True,
               im_b_enabled=True, im_enabled=True)
    assert set(sender._resolve_channels([cfg], "x")) == {
        "sms", "email", "app_push", "im_b", "im"
    }


def test_send_error_with_db_none_rolls_back(monkeypatch):
    # db=None → 内部自建 session；send 走到 commit 抛异常 → rollback + close
    mock_session = MagicMock()
    mock_session.commit.side_effect = RuntimeError("commit boom")
    monkeypatch.setattr(ns_module, "SessionLocal", lambda: mock_session)
    sender = NotificationSender()
    sender._dispatcher = MagicMock()
    monkeypatch.setattr(sender, "_find_configs",
                        lambda db, et: [_cfg(sms_enabled=True, id=1)])
    monkeypatch.setattr(sender, "_find_templates", lambda *a, **k: {})
    result = sender.send(
        "workorder_dispatch", "WO1", {"workorder_id": "WO1"},
        override_channels=["sms"],
        override_receivers=[{"type": "user", "id": "138", "name": "x", "phone": "138"}],
    )
    assert result["status"] == "error"
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_record_alarm_notifications_db_none_exception_rolls_back(monkeypatch):
    # db=None + commit 异常 → should_close=True → rollback + close (不抛出)
    mock_session = MagicMock()
    mock_session.commit.side_effect = RuntimeError("commit boom")
    monkeypatch.setattr(ns_module, "SessionLocal", lambda: mock_session)
    sender = NotificationSender()
    sender._record_alarm_notifications(None, 1, {
        "results": [{"channel": "sms", "status": "sent"}]
    })
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


# ========== 卡 a7bc9343: 日志写入 savepoint 隔离 + naive 时区修复 ==========

def test_log_notification_savepoint_rollback(test_db):
    """卡 a7bc9343 Bug1 (line545): _log_notification 单条日志写入失败只回滚
    savepoint, 不再清空同一事务内已写入的其他日志。旧实现 except 内 db.rollback()
    会把 send() 循环里整批已写入日志一起回滚。"""
    sender = NotificationSender()
    db = test_db["session"]

    recv_a = {"type": "user", "id": "A", "name": "A"}
    recv_b = {"type": "user", "id": "B", "name": "B"}

    # 让第二次 db.add 抛错, 模拟第二条日志写入流程失败 (db.add 每条日志恰一次,
    # 不受 begin_nested 隐式 flush 干扰)。savepoint 隔离: 只丢第二条, 第一条存活。
    real_add = db.add
    add_calls = {"n": 0}

    def flaky_add(obj):
        add_calls["n"] += 1
        if add_calls["n"] == 2:
            raise RuntimeError("simulated log write failure")
        return real_add(obj)

    db.add = flaky_add
    try:
        sender._log_notification(
            db, None, "evt", "EID", {}, "sms", None, recv_a, None, "content-a", "sent")
        sender._log_notification(
            db, None, "evt", "EID", {}, "sms", None, recv_b, None, "content-b", "sent")
    finally:
        db.add = real_add  # 还原, 让 commit 用真实 add

    db.commit()
    contents = {l.content for l in
                db.query(NotificationLog).filter(NotificationLog.event_id == "EID").all()}
    assert "content-a" in contents      # 关键: 第一条存活 (旧实现被一起 rollback 清空)
    assert "content-b" not in contents  # 失败条目被 savepoint 隔离丢弃


def test_record_alarm_notifications_savepoint_isolates_poison_row(test_db):
    """卡 a7bc9343 Bug1 (line579): _record_alarm_notifications 单行写库失败只
    回滚该行 savepoint, 其余行正常落库。旧实现整批 add 后单次 commit, 一行毒
    全批丢失。"""
    sender = NotificationSender()
    db = test_db["session"]

    real_add = db.add
    add_calls = {"n": 0}

    def flaky_add(obj):
        add_calls["n"] += 1
        if add_calls["n"] == 2:  # 第二行(email/bad) add 失败
            raise RuntimeError("simulated poison row")
        return real_add(obj)

    db.add = flaky_add
    try:
        sender._record_alarm_notifications(db, 200, {"results": [
            {"channel": "sms", "receiver": "ok-1", "status": "sent"},
            {"channel": "email", "receiver": "bad", "status": "sent"},
            {"channel": "im", "receiver": "ok-2", "status": "sent"},
        ]})
    finally:
        db.add = real_add

    rows = db.query(AlarmNotification).filter(AlarmNotification.alarm_id == 200).all()
    recipients = {r.recipient for r in rows}
    assert "ok-1" in recipients       # 首行存活
    assert "ok-2" in recipients       # 末行存活 (毒行被隔离不影响)
    assert "bad" not in recipients    # 毒行被丢弃


def test_naive_datetime_fixed(monkeypatch):
    """卡 a7bc9343 Bug2: 3 处 datetime.now().strftime 无时区, UTC 容器显示错时。
    注入固定 UTC 时刻, 验证 event_data['time'] 按 Asia/Shanghai(+08:00) 渲染。"""
    fixed_utc = datetime(2026, 8, 8, 6, 30, 0, tzinfo=timezone.utc)  # → 上海 14:30:00

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_utc.astimezone(tz) if tz else fixed_utc.replace(tzinfo=None)

    monkeypatch.setattr(ns_module, "datetime", FakeDateTime)

    captured = []

    def fake_send(self, event_type, event_id, event_data, db=None, **kw):
        captured.append(event_data.get("time"))
        return {"status": "ok", "results": []}  # 空结果 → _record_alarm_notifications 早退, 不触 DB

    monkeypatch.setattr(NotificationSender, "send", fake_send)

    sender = NotificationSender()
    sender.send_workorder_dispatch("WO-1", "张三", "138", "inv", "st")
    sender.send_workorder_urge("WO-2", "李四", "139", "inv")
    sender.send_alarm_notification(
        alarm_id=1, alarm_content="x", device_id=1, station_id=1, level="critical")

    # 三处 time 均为上海 14:30:00, 而非 naive UTC 06:30:00
    assert captured == ["2026-08-08 14:30:00"] * 3
    assert captured[0] != "2026-08-08 06:30:00"
