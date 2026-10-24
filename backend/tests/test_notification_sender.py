"""
NotificationSender 单元测试

被测文件: app/services/notification_sender.py

设计要点:
- DB 用 MagicMock 隔离; db.query(Model) 按模型分发到独立 chain
- sender._dispatcher 替换为 MagicMock, 隔离短信/邮件/IM底层发送
- _is_quiet_time 依赖模块级 datetime.now(), 用 monkeypatch 固定时刻保证确定性
- _find_configs 对同一 model 最多两次 .all() (精确命中 / 全局兜底), 用 side_effect 按次序区分
- send(db=None) 路径 patch 模块 SessionLocal, 验证 close / rollback
"""
from unittest.mock import MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.notification_sender import (
    NotificationSender,
    EVENT_CHANNEL_MAP,
)
from app.models.notification_config import NotificationConfig, NotificationTemplate
from app.models.alarm_notification import AlarmNotification
from app.models.user import User
import app.services.notification_sender as ns


# ─── DB chain mock 辅助 ───

def make_db():
    db = MagicMock()
    by_model = {}

    def _query(model, *args, **kwargs):
        return by_model.setdefault(model, MagicMock(name=f"q[{getattr(model, '__name__', repr(model))}]"))

    db.query.side_effect = _query
    db._by_model = by_model
    return db


def cfg_chain(db):
    return db._by_model.setdefault(NotificationConfig, MagicMock())


def tpl_chain(db):
    return db._by_model.setdefault(NotificationTemplate, MagicMock())


def user_chain(db):
    return db._by_model.setdefault(User, MagicMock())


# ─── 业务对象工厂 ───

def make_config(cid=1, *, enabled=True, trigger_events=None, scope_type="tenant", priority=0,
                sms_enabled=False, email_enabled=False, app_push_enabled=False,
                im_b_enabled=False, im_enabled=False,
                quiet_start=None, quiet_end=None, receivers=None, receiver_roles=None,
                timezone="Asia/Shanghai"):
    c = MagicMock()
    c.id = cid
    c.enabled = enabled
    c.trigger_events = trigger_events if trigger_events is not None else ["workorder_dispatch"]
    c.scope_type = scope_type
    c.priority = priority
    c.sms_enabled = sms_enabled
    c.email_enabled = email_enabled
    c.app_push_enabled = app_push_enabled
    c.im_b_enabled = im_b_enabled
    c.im_enabled = im_enabled
    c.quiet_start = quiet_start
    c.quiet_end = quiet_end
    c.timezone = timezone  # 卡 ac0a7aa7: _is_quiet_time 读 per-config timezone
    c.receivers = receivers if receivers is not None else []
    c.receiver_roles = receiver_roles if receiver_roles is not None else []
    return c


def make_template(tid=1, *, enabled=True, event_type="workorder_dispatch", channel="sms",
                  content="工单 {workorder_id}", subject="主题 {workorder_id}", code="TPL_A"):
    t = MagicMock()
    t.id = tid
    t.enabled = enabled
    t.event_type = event_type
    t.channel = channel
    t.content = content
    t.subject = subject
    t.code = code
    return t


def make_user(uid=1, *, role="engineer", is_active=True, name="张三", username="zhang",
              phone="13800000000", email="z@x.com"):
    u = MagicMock()
    u.id = uid
    u.role = role
    u.is_active = is_active
    u.name = name
    u.username = username
    u.phone = phone
    u.email = email
    return u


def fresh_sender():
    s = NotificationSender()
    s._dispatcher = MagicMock()
    return s


# (卡 ac0a7aa7) _is_quiet_time 改为 now= 注入; 旧 _freeze_now monkeypatch naive
# datetime 已移除 —— 见 TestQuietTime 各用例直接传 now= aware/naive datetime。


# ═══════════════════════════════════════════════════════════
# 模板渲染 / 默认内容
# ═══════════════════════════════════════════════════════════

class TestRender:
    def setup_method(self):
        self.s = fresh_sender()

    def test_format_template_substitution(self):
        out = self.s._format_template("a={a}, b={b}", {"a": 1, "b": "x", "c": "ignored"})
        assert out == "a=1, b=x"

    def test_render_content_uses_template(self):
        tpl = {"sms": make_template(content="hi {name}")}
        assert self.s._render_content(tpl, "sms", {"name": "L"}) == "hi L"

    def test_render_content_falls_back_to_default(self):
        # 无模板 → 默认内容
        out = self.s._render_content({}, "sms", {"workorder_id": "WO1", "device_name": "D", "station_name": "S"})
        assert "WO1" in out and "D" in out and "S" in out

    def test_render_subject_uses_template(self):
        tpl = {"sms": make_template(subject="S {workorder_id}")}
        assert self.s._render_subject(tpl, "sms", {"workorder_id": "W1"}) == "S W1"

    def test_render_subject_none_when_no_template(self):
        assert self.s._render_subject({}, "sms", {}) is None

    def test_default_content_workorder(self):
        out = self.s._default_content("sms", {"workorder_id": "WO9", "device_name": "inv", "station_name": "ST"})
        assert "WO9" in out and "inv" in out and "ST" in out

    def test_default_content_alarm(self):
        out = self.s._default_content("sms", {"level": "critical", "alarm_content": "过温", "device_id": 7})
        assert "critical" in out and "过温" in out and "7" in out

    def test_default_content_fallback(self):
        out = self.s._default_content("sms", {"foo": "bar"})
        assert "foo" in out  # 未知事件 → 兜底打印整个 dict


# ═══════════════════════════════════════════════════════════
# 静默时间 (含跨天 / 非法格式)
# ═══════════════════════════════════════════════════════════

class TestQuietTime:
    """(卡 ac0a7aa7) now= 注入 aware datetime 替代 monkeypatch naive datetime。

    make_config 默认 timezone=Asia/Shanghai; 注入 aware 上海时刻验证窗口逻辑。
    """

    def setup_method(self):
        self.s = fresh_sender()

    def test_no_window_returns_false(self):
        assert self.s._is_quiet_time(make_config()) is False

    def test_within_window(self):
        # 上海 10:30 在 09:00-12:00 内
        cfg = make_config(quiet_start="09:00", quiet_end="12:00")
        now = datetime(2026, 1, 1, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=now) is True

    def test_outside_window(self):
        cfg = make_config(quiet_start="09:00", quiet_end="12:00")
        now = datetime(2026, 1, 1, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=now) is False

    def test_cross_midnight_late_night(self):
        # 22:00-08:00 跨天; 上海 23:30 在静默期
        cfg = make_config(quiet_start="22:00", quiet_end="08:00")
        now = datetime(2026, 1, 1, 23, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=now) is True

    def test_cross_midnight_early_morning(self):
        # 上海 03:00 也在 22:00-08:00 内
        cfg = make_config(quiet_start="22:00", quiet_end="08:00")
        now = datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=now) is True

    def test_cross_midnight_outside(self):
        # 上海 12:00 不在 22:00-08:00
        cfg = make_config(quiet_start="22:00", quiet_end="08:00")
        now = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=now) is False

    def test_invalid_format_returns_false(self):
        # int("xx") 抛错 → except → False
        cfg = make_config(quiet_start="xx:yy", quiet_end="09:00")
        now = datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=now) is False

    # (卡 6259ac0d) 坏值 fail-open 但必须留 warning 痕迹, 不再静默击穿免打扰
    def test_bad_values_fail_open_with_warning(self, caplog):
        import logging as _logging
        for bad in ("25:99", "abc", "0800"):
            cfg = make_config(cid=77, quiet_start=bad, quiet_end="09:00")
            now = datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            with caplog.at_level(_logging.WARNING, logger="app.services.notification_sender"):
                assert self.s._is_quiet_time(cfg, now=now) is False
            assert any("77" in r.message and bad in r.message for r in caplog.records)
            caplog.clear()

    def test_boundary_inclusive(self):
        # 恰好 08:00 / 22:00 均含端点 (现有 <= 语义)
        cfg = make_config(quiet_start="08:00", quiet_end="22:00")
        t0 = datetime(2026, 1, 1, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        t1 = datetime(2026, 1, 1, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert self.s._is_quiet_time(cfg, now=t0) is True
        assert self.s._is_quiet_time(cfg, now=t1) is True


# ═══════════════════════════════════════════════════════════
# 渠道 / 接收人解析
# ═══════════════════════════════════════════════════════════

class TestResolveChannelsReceivers:
    def setup_method(self):
        self.s = fresh_sender()

    def test_resolve_channels_from_config_flags(self):
        cfg = make_config(sms_enabled=True, email_enabled=True, im_enabled=True)
        ch = self.s._resolve_channels([cfg], "workorder_dispatch")
        assert set(ch) == {"sms", "email", "im"}

    def test_resolve_channels_default_when_no_flags(self):
        cfg = make_config()  # 全 False
        ch = self.s._resolve_channels([cfg], "alarm_trigger")
        assert set(ch) == set(EVENT_CHANNEL_MAP["alarm_trigger"])

    def test_resolve_channels_default_for_unknown_event(self):
        cfg = make_config()
        ch = self.s._resolve_channels([cfg], "unknown_event")
        assert ch == ["app_push"]  # 兜底默认

    def test_resolve_receivers_fixed_dicts_and_strings(self):
        db = make_db()
        cfg = make_config(receivers=[
            {"type": "user", "id": "1", "name": "A", "phone": "111"},
            "13800000000",  # 字符串接收人
        ])
        out = self.s._resolve_receivers([cfg], {}, db)
        assert len(out) == 2
        assert out[0]["id"] == "1"
        assert out[1] == {"type": "phone", "id": "13800000000", "name": "13800000000"}

    def test_resolve_receivers_dedup(self):
        db = make_db()
        cfg = make_config(receivers=[
            {"type": "user", "id": "1", "name": "A"},
            {"type": "user", "id": "1", "name": "A"},  # 重复
        ])
        out = self.s._resolve_receivers([cfg], {}, db)
        assert len(out) == 1

    def test_resolve_receivers_by_role(self, monkeypatch):
        # NOTE: 源码 _resolve_receivers 引用 User.is_active, 但 User 模型只有 status 列,
        # 属源码潜在 bug (运行时 AttributeError)。此处 monkeypatch 补齐属性以隔离测试,
        # 专注验证角色→用户解析逻辑本身。
        monkeypatch.setattr(User, "is_active", MagicMock(), raising=False)
        db = make_db()
        user_chain(db).filter.return_value.all.return_value = [make_user(uid=5, role="engineer")]
        cfg = make_config(receiver_roles=["engineer"])
        out = self.s._resolve_receivers([cfg], {}, db)
        assert len(out) == 1
        assert out[0]["id"] == "5"
        assert out[0]["phone"] == "13800000000"

    def test_resolve_receivers_batch_roles_single_query(self):
        """多 config × 多 role(含重复) → 单次 User 查询; 结果与逐角色循环等价。

        回归 N+1: 原实现每个 (config, role) 一次查询; 这里 2 config × 3 role 声明
        (含重复 engineer) 应只查 1 次, 且跨 config 按 user_id 去重、顺序按 config→role→DB序。
        """
        db = make_db()
        user_chain(db).filter.return_value.all.return_value = [
            make_user(uid=5, role="engineer", name="E5", phone="555"),
            make_user(uid=6, role="engineer", name="E6", phone="666"),
            make_user(uid=7, role="manager", name="M7", phone="777"),
        ]
        cfg_a = make_config(receiver_roles=["engineer", "manager"])
        cfg_b = make_config(receiver_roles=["engineer"])  # 重复 engineer
        out = self.s._resolve_receivers([cfg_a, cfg_b], {}, db)

        # 3 个不同用户; cfg_b 的 engineer 已见过 → 去重; 顺序按 config→role→DB序
        assert [r["id"] for r in out] == ["5", "6", "7"]
        # 批量查询: User 链只 .all() 一次 (修复 N+1)
        assert user_chain(db).filter.return_value.all.call_count == 1

    def test_resolve_receivers_no_roles_no_user_query(self):
        """无 receiver_roles 时不查 User (短路)。"""
        db = make_db()
        cfg = make_config(receivers=[{"type": "user", "id": "1", "name": "A"}])
        out = self.s._resolve_receivers([cfg], {}, db)
        assert len(out) == 1
        # User 链从未被 .all()
        assert user_chain(db).filter.return_value.all.call_count == 0

    def test_is_channel_enabled_various(self):
        cfg = make_config(sms_enabled=True, im_enabled=True)
        assert self.s._is_channel_enabled(cfg, "sms") is True
        assert self.s._is_channel_enabled(cfg, "im") is True
        assert self.s._is_channel_enabled(cfg, "email") is False
        assert self.s._is_channel_enabled(cfg, "unknown_channel") is False


# ═══════════════════════════════════════════════════════════
# _find_configs (精确命中 / 全局兜底)
# ═══════════════════════════════════════════════════════════

class TestFindConfigs:
    def setup_method(self):
        self.s = fresh_sender()

    def test_exact_match_returns_configs(self):
        db = make_db()
        cfg = make_config(trigger_events=["workorder_dispatch"])
        cfg_chain(db).filter.return_value.order_by.return_value.all.return_value = [cfg]
        out = self.s._find_configs(db, "workorder_dispatch")
        assert out == [cfg]

    def test_fallback_to_tenant_scope_when_no_exact(self):
        db = make_db()
        fb = make_config(scope_type="tenant")
        # 第一次精确查询返回 [], 第二次兜底查询返回 [fb]
        cfg_chain(db).filter.return_value.order_by.return_value.all.side_effect = [[], [fb]]
        out = self.s._find_configs(db, "workorder_dispatch")
        assert out == [fb]

    def test_no_config_at_all_returns_empty(self):
        db = make_db()
        cfg_chain(db).filter.return_value.order_by.return_value.all.side_effect = [[], []]
        assert self.s._find_configs(db, "workorder_dispatch") == []


# ═══════════════════════════════════════════════════════════
# _find_templates (批量查询)
# ═══════════════════════════════════════════════════════════

class TestFindTemplates:
    def setup_method(self):
        self.s = fresh_sender()

    def test_batch_channels_single_query(self):
        """多渠道(含缺失) → 单次查询; 按渠道索引, 与逐渠道 .first() 等价。

        回归 N+1: 原实现每渠道一次 .first() 查询; 4 渠道应只查 1 次。
        """
        db = make_db()
        tpl_sms = make_template(tid=1, channel="sms", content="c1")
        tpl_email = make_template(tid=2, channel="email", content="c2")
        tpl_im = make_template(tid=3, channel="im", content="c3")
        tpl_chain(db).filter.return_value.all.return_value = [tpl_sms, tpl_email, tpl_im]

        out = self.s._find_templates(db, "alarm_trigger", ["sms", "email", "im", "im_b"])

        assert set(out.keys()) == {"sms", "email", "im"}  # im_b 缺模板不出现
        assert out["sms"] is tpl_sms
        assert out["email"] is tpl_email
        assert out["im"] is tpl_im
        # 批量查询: 只 .all() 一次, 不管几个渠道 (修复 N+1)
        assert tpl_chain(db).filter.return_value.all.call_count == 1

    def test_first_per_channel_semantics(self):
        """同渠道多条模板 → 取首条 (与原 per-channel .first() 的 DB 默认序一致)。"""
        db = make_db()
        first_sms = make_template(tid=10, channel="sms", content="first")
        dup_sms = make_template(tid=11, channel="sms", content="dup")
        tpl_chain(db).filter.return_value.all.return_value = [first_sms, dup_sms, make_template(tid=12, channel="email")]
        out = self.s._find_templates(db, "workorder_dispatch", ["sms", "email"])
        assert out["sms"] is first_sms  # 取首条, 非 dup
        assert "email" in out

    def test_empty_channels_no_query(self):
        db = make_db()
        assert self.s._find_templates(db, "x", []) == {}
        assert tpl_chain(db).filter.return_value.all.call_count == 0


# ═══════════════════════════════════════════════════════════
# send() 主流程
# ═══════════════════════════════════════════════════════════

class TestSend:
    def _wire_configs(self, db, configs):
        cfg_chain(db).filter.return_value.order_by.return_value.all.return_value = configs

    def test_no_config_returns_no_config(self):
        s = fresh_sender()
        db = make_db()
        self._wire_configs(db, [])
        res = s.send("workorder_dispatch", "WO1", {}, db=db)
        assert res["status"] == "no_config"
        assert res["results"] == []

    def test_success_sms_logs_and_dispatches(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True)
        self._wire_configs(db, [cfg])
        tpl_chain(db).filter.return_value.all.return_value = [make_template(channel="sms", content="工单 {workorder_id}")]
        receiver = {"type": "user", "id": "138", "name": "张三", "phone": "13800000000"}

        res = s.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"},
                     db=db, override_channels=["sms"], override_receivers=[receiver])

        assert res["status"] == "ok"
        assert len(res["results"]) == 1
        assert res["results"][0]["status"] == "sent"
        s._dispatcher.notify_sms.assert_called_once()
        db.commit.assert_called_once()
        # 至少记录了一条日志
        assert db.add.call_count >= 1

    def test_failed_receiver_logs_failed(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True)
        self._wire_configs(db, [cfg])
        tpl_chain(db).filter.return_value.all.return_value = []  # 默认内容
        s._dispatcher.notify_sms.side_effect = RuntimeError("sms gateway down")
        receiver = {"type": "user", "id": "138", "name": "张三", "phone": "13800000000"}

        res = s.send("workorder_dispatch", "WO1", {"workorder_id": "WO1", "device_name": "d", "station_name": "s"},
                     db=db, override_channels=["sms"], override_receivers=[receiver])

        assert res["status"] == "ok"
        assert res["results"][0]["status"] == "failed"
        # result 字段须脱敏，原始异常文本不得泄露（仅 ERROR 日志保留原始信息）
        assert res["results"][0]["error"] == "服务内部错误，请稍后重试"
        assert "sms gateway down" not in res["results"][0]["error"]

    def test_quiet_time_skips_channel(self):
        # 全天静默窗口 (00:00-23:59) → 任意时刻都 quiet; send 跳过渠道不调度
        # (卡 ac0a7aa7: send 内部 _is_quiet_time 用 datetime.now(tz), 不再 monkeypatch)
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True, quiet_start="00:00", quiet_end="23:59")
        self._wire_configs(db, [cfg])
        receiver = {"type": "user", "id": "1", "name": "X", "phone": "111"}

        res = s.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"},
                     db=db, override_channels=["sms"], override_receivers=[receiver])

        assert res["results"][0]["status"] == "quiet"
        s._dispatcher.notify_sms.assert_not_called()

    def test_multiple_receivers_each_get_sent(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True)
        self._wire_configs(db, [cfg])
        tpl_chain(db).filter.return_value.all.return_value = []
        receivers = [
            {"type": "user", "id": "1", "name": "A", "phone": "111"},
            {"type": "user", "id": "2", "name": "B", "phone": "222"},
        ]
        res = s.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"},
                     db=db, override_channels=["sms"], override_receivers=receivers)
        assert len(res["results"]) == 2
        assert all(r["status"] == "sent" for r in res["results"])
        assert s._dispatcher.notify_sms.call_count == 2

    def test_multiple_channels_dispatch(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True, email_enabled=True, im_enabled=True)
        self._wire_configs(db, [cfg])
        tpl_chain(db).filter.return_value.all.return_value = []
        receiver = {"type": "user", "id": "1", "name": "A", "phone": "111", "email": "a@b.com"}
        res = s.send("alarm_trigger", "A1", {"alarm_id": 1, "level": "critical", "alarm_content": "x", "device_id": 1},
                     db=db, override_channels=["sms", "email", "im"], override_receivers=[receiver])
        s._dispatcher.notify_sms.assert_called_once()
        s._dispatcher.notify_email.assert_called_once()
        s._dispatcher.notify_im.assert_called_once()
        assert len(res["results"]) == 3

    def test_channel_disabled_in_config_is_skipped(self):
        # config 只启用 sms, 但 override_channels 含 email → email 被跳过
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True, email_enabled=False)
        self._wire_configs(db, [cfg])
        tpl_chain(db).filter.return_value.all.return_value = []
        receiver = {"type": "user", "id": "1", "name": "A", "phone": "111", "email": "a@b.com"}
        res = s.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"},
                     db=db, override_channels=["sms", "email"], override_receivers=[receiver])
        channels_sent = [r["channel"] for r in res["results"]]
        assert "sms" in channels_sent and "email" not in channels_sent

    def test_send_db_none_closes_session(self, monkeypatch):
        s = fresh_sender()
        inner_db = make_db()
        cfg = make_config(sms_enabled=True)
        cfg_chain(inner_db).filter.return_value.order_by.return_value.all.return_value = [cfg]
        tpl_chain(inner_db).filter.return_value.all.return_value = []
        monkeypatch.setattr(ns, "SessionLocal", lambda: inner_db)

        res = s.send("workorder_dispatch", "WO1", {"workorder_id": "WO1"},
                     db=None, override_channels=["sms"],
                     override_receivers=[{"type": "user", "id": "1", "name": "A", "phone": "111"}])
        assert res["status"] == "ok"
        inner_db.close.assert_called_once()
        inner_db.commit.assert_called_once()

    def test_send_db_none_rolls_back_on_error(self, monkeypatch):
        s = fresh_sender()
        inner_db = make_db()
        # _find_configs 抛错 → 进 except → should_close → rollback + close
        inner_db.query.side_effect = RuntimeError("db down")
        monkeypatch.setattr(ns, "SessionLocal", lambda: inner_db)
        res = s.send("workorder_dispatch", "WO1", {}, db=None)
        assert res["status"] == "error"
        inner_db.rollback.assert_called_once()
        inner_db.close.assert_called_once()

    def test_send_exception_with_external_db_no_rollback(self):
        # db 由外部传入 → 异常时不 rollback, 仅返回 error
        s = fresh_sender()
        db = make_db()
        db.query.side_effect = RuntimeError("boom")
        res = s.send("workorder_dispatch", "WO1", {}, db=db)
        assert res["status"] == "error"
        db.rollback.assert_not_called()


# ═══════════════════════════════════════════════════════════
# _dispatch_channel 路由
# ═══════════════════════════════════════════════════════════

class TestDispatchChannel:
    def setup_method(self):
        self.s = fresh_sender()

    def test_sms_uses_phone(self):
        self.s._dispatch_channel("sms", {"phone": "111", "id": "x"}, "c", None, {})
        self.s._dispatcher.notify_sms.assert_called_once_with(message="c", phone="111")

    def test_sms_falls_back_to_id_when_no_phone(self):
        self.s._dispatch_channel("sms", {"id": "111"}, "c", None, {})
        self.s._dispatcher.notify_sms.assert_called_once_with(message="c", phone="111")

    def test_email_uses_email(self):
        self.s._dispatcher.notify_email  # 确认属性存在
        self.s._dispatch_channel("email", {"email": "a@b.com"}, "c", "s", {})
        self.s._dispatcher.notify_email.assert_called_once_with(message="c", to="a@b.com")

    def test_im_no_receiver_arg(self):
        self.s._dispatch_channel("im", {}, "c", None, {})
        self.s._dispatcher.notify_im.assert_called_once_with(message="c")

    def test_app_push_and_unknown_channel_no_dispatcher_call(self):
        # app_push / im_b / 未知渠道 仅记日志, 不调 dispatcher
        self.s._dispatch_channel("app_push", {"name": "A"}, "c", None, {})
        self.s._dispatch_channel("im_b", {"name": "B"}, "c", None, {})
        self.s._dispatch_channel("unknown", {"name": "C"}, "c", None, {})
        self.s._dispatcher.notify_sms.assert_not_called()
        self.s._dispatcher.notify_email.assert_not_called()
        self.s._dispatcher.notify_im.assert_not_called()


# ═══════════════════════════════════════════════════════════
# 便捷方法 / 告警通知持久化
# ═══════════════════════════════════════════════════════════

class TestConvenienceAndAlarmPersist:
    def test_send_workorder_dispatch_builds_event_data(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True)
        cfg_chain(db).filter.return_value.order_by.return_value.all.return_value = [cfg]
        tpl_chain(db).filter.return_value.all.return_value = []
        res = s.send_workorder_dispatch("WO1", "张三", "138", "逆变器", "虹桥站", db=db)
        assert res["status"] == "ok"
        # 派单便捷方法用 override_receivers, receiver.id = 工程师手机号
        sent_args = s._dispatcher.notify_sms.call_args
        assert sent_args.kwargs["phone"] == "138"
        assert "WO1" in sent_args.kwargs["message"]

    def test_send_workorder_urge_builds_event_data(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True)
        cfg_chain(db).filter.return_value.order_by.return_value.all.return_value = [cfg]
        tpl_chain(db).filter.return_value.all.return_value = []
        res = s.send_workorder_urge("WO1", "李四", "139", "逆变器", db=db)
        assert res["status"] == "ok"

    def test_send_alarm_notification_persists(self):
        s = fresh_sender()
        db = make_db()
        cfg = make_config(sms_enabled=True, im_enabled=True)
        cfg_chain(db).filter.return_value.order_by.return_value.all.return_value = [cfg]
        tpl_chain(db).filter.return_value.all.return_value = []
        res = s.send_alarm_notification(alarm_id=99, alarm_content="过温", device_id=7,
                                         station_id=100, level="critical", db=db)
        assert res["status"] == "ok"
        # _record_alarm_notifications 应为每条 result 落一条 AlarmNotification
        added = [c.args[0] for c in db.add.call_args_list]
        alarm_rows = [a for a in added if isinstance(a, AlarmNotification)]
        assert len(alarm_rows) == len(res["results"])
        assert all(a.alarm_id == 99 for a in alarm_rows)

    def test_record_alarm_notifications_skips_empty_results(self):
        s = fresh_sender()
        db = make_db()
        # send_result 无 results → 直接 return, 不写库
        s._record_alarm_notifications(db, 1, {"status": "no_config", "results": []})
        db.add.assert_not_called()

    def test_record_alarm_notifications_db_none_uses_sessionlocal(self, monkeypatch):
        s = fresh_sender()
        inner_db = make_db()
        monkeypatch.setattr(ns, "SessionLocal", lambda: inner_db)
        s._record_alarm_notifications(
            None, 5,
            {"results": [{"channel": "sms", "receiver": "1", "status": "sent"}]},
        )
        inner_db.add.assert_called_once()
        inner_db.commit.assert_called_once()
        inner_db.close.assert_called_once()

    def test_record_alarm_notifications_swallows_db_error(self, monkeypatch):
        s = fresh_sender()
        inner_db = make_db()
        inner_db.commit.side_effect = RuntimeError("write fail")
        monkeypatch.setattr(ns, "SessionLocal", lambda: inner_db)
        # 不应抛出
        s._record_alarm_notifications(
            None, 5,
            {"results": [{"channel": "sms", "receiver": "1", "status": "sent"}]},
        )
        inner_db.rollback.assert_called_once()
        inner_db.close.assert_called_once()
