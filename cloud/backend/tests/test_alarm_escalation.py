"""AlarmEscalationTracker 测试 (卡 36fea797)

覆盖: trigger 状态登记 / check_escalation 升级路径 (now 注入) / ack / get_state /
_default_notifier 异常吞噬 / _get_setting 缺省回退。
通知器与 on-call 解析全部 mock, 不触真实渠道。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import alarm_escalation as mod
from app.services.alarm_escalation import AlarmEscalationTracker

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_tracker(**kw):
    sent = []
    def notifier(level, channel, alarm_id, message, receiver):
        sent.append({"level": level, "channel": channel, "alarm_id": alarm_id,
                     "message": message, "receiver": receiver})
    resolved = []
    def resolver(team_id):
        resolved.append(team_id)
        return {"phone": "13800000000", "name": "oncall"}
    t = AlarmEscalationTracker(notifier=notifier, oncall_resolver=resolver, **kw)
    return t, sent, resolved


# ─── trigger ───

def test_trigger_registers_state_and_sends_immediate():
    t, sent, _ = make_tracker()
    actions = t.trigger("a1", message="过压", team_id=7, receiver={"name": "ops"}, now=T0)
    assert [a["channel"] for a in actions] == ["im", "wecom"]
    assert all(a["level"] == 1 for a in actions)
    assert len(sent) == 2
    st = t.get_state("a1")
    assert st["triggered_at"] == T0
    assert st["acked"] is False and st["acked_at"] is None
    assert st["level"] == 1
    assert st["message"] == "过压" and st["team_id"] == 7
    assert st["receiver"] == {"name": "ops"}
    for s in sent:
        assert s["message"] == "过压" and s["receiver"] == {"name": "ops"}


def test_trigger_custom_channels():
    t, sent, _ = make_tracker()
    t.trigger("a2", message="m", immediate_channels=("sms",), now=T0)
    assert [s["channel"] for s in sent] == ["sms"]


def test_trigger_overwrites_existing_state():
    t, _, _ = make_tracker()
    t.trigger("a3", message="first", now=T0)
    t.trigger("a3", message="second", now=T0 + timedelta(minutes=5))
    assert t.get_state("a3")["message"] == "second"


# ─── check_escalation ───

def test_no_escalation_before_sms_threshold():
    t, sent, _ = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a", message="m", team_id=1, now=T0)
    acts = t.check_escalation(now=T0 + timedelta(minutes=14))
    assert acts == [] and len(sent) == 2  # 仅初始即时通知
    assert t.get_state("a")["level"] == 1


def test_sms_escalation_after_timeout():
    t, sent, resolved = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a", message="m", team_id=9, now=T0)
    acts = t.check_escalation(now=T0 + timedelta(minutes=15))
    assert acts == [{"level": 2, "channel": "sms", "alarm_id": "a",
                     "receiver": {"phone": "13800000000", "name": "oncall"}}]
    assert sent[-1]["level"] == 2 and sent[-1]["channel"] == "sms"
    assert resolved == [9]  # on-call 解析收到 team_id
    assert t.get_state("a")["level"] == 2


def test_sms_level_guard_no_repeat():
    t, sent, _ = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a", message="m", now=T0)
    t.check_escalation(now=T0 + timedelta(minutes=16))
    n = len(sent)
    acts = t.check_escalation(now=T0 + timedelta(minutes=17))
    assert acts == [] and len(sent) == n  # level 2 不重复发


def test_voice_escalation_and_cross_level_sms():
    t, sent, _ = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a", message="m", team_id=1, now=T0)
    # 未经历中间巡检, 直接到 voice 阈值: 补发 sms + voice
    acts = t.check_escalation(now=T0 + timedelta(minutes=30))
    assert [(a["level"], a["channel"]) for a in acts] == [(2, "sms"), (3, "voice")]
    assert t.get_state("a")["level"] == 3
    # level 3 后不再升级
    n = len(sent)
    assert t.check_escalation(now=T0 + timedelta(minutes=60)) == []
    assert len(sent) == n


def test_acked_alarm_not_escalated_and_cleaned_after_retention():
    t, sent, _ = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a", message="m", now=T0)
    t.ack("a", now=T0 + timedelta(minutes=5))
    acts = t.check_escalation(now=T0 + timedelta(minutes=40))
    assert acts == [] and t.get_state("a") is not None
    # ack 后超 ACK_RETENTION(24h) 清理
    t.check_escalation(now=T0 + timedelta(minutes=5) + mod.ACK_RETENTION)
    assert t.get_state("a") is None


def test_clock_skew_clamped_no_false_escalation():
    t, sent, _ = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a", message="m", now=T0)
    # now 早于 triggered_at (时钟回拨): 不升级不崩溃
    assert t.check_escalation(now=T0 - timedelta(minutes=30)) == []


def test_multiple_alarms_independent_state():
    t, sent, _ = make_tracker(sms_escalate_min=15, voice_escalate_min=30)
    t.trigger("a1", message="m1", team_id=1, now=T0)
    t.trigger("a2", message="m2", team_id=2, now=T0 + timedelta(minutes=20))
    t.ack("a1", now=T0 + timedelta(minutes=1))
    acts = t.check_escalation(now=T0 + timedelta(minutes=40))  # a2 elapsed=20min ≥ sms 15
    # a1 已 ack 不升级; a2 已过 sms 阈值 → 升级
    assert [(a["alarm_id"], a["level"]) for a in acts] == [("a2", 2)]
    assert t.get_state("a1")["level"] == 1
    assert t.get_state("a2")["level"] == 2


# ─── ack ───

def test_ack_success_first_time_true():
    t, _, _ = make_tracker()
    t.trigger("a", message="m", now=T0)
    assert t.ack("a", now=T0 + timedelta(minutes=3)) is True
    st = t.get_state("a")
    assert st["acked"] is True and st["acked_at"] == T0 + timedelta(minutes=3)


def test_ack_repeat_returns_false():
    t, _, _ = make_tracker()
    t.trigger("a", message="m", now=T0)
    assert t.ack("a", now=T0) is True
    assert t.ack("a", now=T0 + timedelta(minutes=1)) is False


def test_ack_unknown_alarm_returns_false():
    t, _, _ = make_tracker()
    assert t.ack("nope", now=T0) is False


# ─── get_state ───

def test_get_state_missing_returns_none():
    t, _, _ = make_tracker()
    assert t.get_state("missing") is None


# ─── _default_notifier 异常吞噬 ───

def test_default_notifier_swallows_exception(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("channel down")
    monkeypatch.setattr(mod, "dispatch_real_channel", boom)
    t = AlarmEscalationTracker()  # 无注入 notifier → 走默认
    t.trigger("a", message="m", now=T0)  # 不应抛
    assert t.get_state("a") is not None


def test_default_notifier_passes_state_fields(monkeypatch):
    calls = []
    def fake_dispatch(channel, team_id, db, receiver, message, extra):
        calls.append((channel, team_id, db, receiver, message, extra))
    monkeypatch.setattr(mod, "dispatch_real_channel", fake_dispatch)
    t = AlarmEscalationTracker()
    t.trigger("a", message="mm", team_id=5, now=T0)
    assert len(calls) == 2
    assert calls[0] == ("im", 5, None, {}, "mm", None)


def test_oncall_resolver_exception_returns_none():
    def bad(team_id):
        raise ValueError("db down")
    t = AlarmEscalationTracker(
        notifier=lambda *a: None, oncall_resolver=bad,
        sms_escalate_min=15, voice_escalate_min=30,
    )
    t.trigger("a", message="m", now=T0)
    acts = t.check_escalation(now=T0 + timedelta(minutes=20))
    assert acts[0]["receiver"] is None  # 解析失败不外抛, receiver=None


# ─── _get_setting ───

def test_get_setting_fallback_on_missing_attr():
    assert mod._get_setting("NO_SUCH_SETTING_XYZ", 42) == 42


def test_get_setting_fallback_on_none_value(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "ALARM_SMS_ESCALATE_MIN", None, raising=False)
    assert mod._get_setting("ALARM_SMS_ESCALATE_MIN", 7) == 7


def test_get_setting_reads_settings_value(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "ALARM_SMS_ESCALATE_MIN", 22)
    assert mod._get_setting("ALARM_SMS_ESCALATE_MIN", 15) == 22
    # 阈值从 settings 读入
    t = AlarmEscalationTracker(notifier=lambda *a: None)
    assert t.sms_escalate_min == 22 and t.voice_escalate_min == 44
