"""告警升级链 AlarmEscalationTracker 测试 (卡 8d98ebe3)

被测模块: app/services/alarm_escalation.py
触发 → ① IM/企微即时 → N分钟未ack → ② 短信on_call → 再N分钟 → ③ 语音桩
ack 终止升级链。时钟可注入 (now=) 做确定性验证。
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.services.alarm_escalation import AlarmEscalationTracker


def _t0():
    return datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def _recorder():
    """记录 notifier 调用 (level, channel, alarm_id)。"""
    calls = []

    def notifier(level, channel, alarm_id, message, receiver=None):
        calls.append({
            "level": level, "channel": channel, "alarm_id": alarm_id,
            "receiver": receiver,
        })

    return notifier, calls


# ========== trigger 即时通知 ==========

def test_trigger_fires_immediate_im_wecom():
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    actions = tracker.trigger(101, message="过温", team_id=1,
                              receiver={"name": "张三"}, now=_t0())
    # ① 即时: im + wecom
    channels = {a["channel"] for a in actions}
    assert channels == {"im", "wecom"}
    assert all(a["level"] == 1 for a in actions)
    recorded_channels = {c["channel"] for c in calls}
    assert recorded_channels == {"im", "wecom"}
    state = tracker.get_state(101)
    assert state["level"] == 1
    assert state["acked"] is False


def test_trigger_records_triggered_at():
    tracker = AlarmEscalationTracker(notifier=lambda *a, **k: None, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    assert tracker.get_state(1)["triggered_at"] == _t0()


# ========== ack 终止 ==========

def test_ack_terminates_chain():
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(101, message="过温", now=_t0())
    assert tracker.ack(101, now=_t0() + timedelta(minutes=5)) is True
    # 升级检查不应再触发 (已 ack)
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=20))
    assert actions == []
    assert tracker.get_state(101)["acked"] is True


def test_ack_returns_false_when_no_state():
    tracker = AlarmEscalationTracker(notifier=lambda *a, **k: None)
    assert tracker.ack(999) is False


def test_ack_idempotent_returns_false_second_time():
    tracker = AlarmEscalationTracker(notifier=lambda *a, **k: None, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    assert tracker.ack(1) is True
    assert tracker.ack(1) is False  # 已 ack


# ========== 短信升级 (level 2) ==========

def test_sms_escalation_after_window():
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda team_id: {"phone": "13900000000", "name": "值班人"},
    )
    tracker.trigger(101, message="过温", team_id=1, now=_t0())
    # +16min (>15min 阈值, 未 ack) → 升级短信
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=16))
    sms = [a for a in actions if a["channel"] == "sms"]
    assert len(sms) == 1
    assert sms[0]["level"] == 2
    # 短信接收人 = on_call 值班人
    assert sms[0]["receiver"]["phone"] == "13900000000"
    assert tracker.get_state(101)["level"] == 2


def test_no_sms_escalation_before_window():
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=10))
    assert actions == []  # 未到阈值


def test_sms_does_not_refire_on_recheck():
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    tracker.check_escalation(now=_t0() + timedelta(minutes=16))  # 首次升级 sms
    # 再次检查 (仍在 sms 阶段) → 不重复发短信
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=20))
    assert [a for a in actions if a["channel"] == "sms"] == []


# ========== 语音升级 (level 3) ==========

def test_voice_escalation_after_double_window():
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda team_id: {"phone": "13900000000"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    # +31min (>2*15=30min, 未 ack) → 直升语音 (level 3)
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=31))
    voice = [a for a in actions if a["channel"] == "voice"]
    assert len(voice) == 1
    assert voice[0]["level"] == 3
    assert tracker.get_state(1)["level"] == 3


def test_progressive_levels_sms_then_voice():
    """先到 sms 阶段, 再到 voice 阶段, 层级递进不跳级重复。"""
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda team_id: {"phone": "139"},
    )
    tracker.trigger(1, message="x", now=_t0())
    a1 = tracker.check_escalation(now=_t0() + timedelta(minutes=16))
    assert {a["channel"] for a in a1} == {"sms"}
    assert tracker.get_state(1)["level"] == 2
    a2 = tracker.check_escalation(now=_t0() + timedelta(minutes=31))
    assert {a["channel"] for a in a2} == {"voice"}
    assert tracker.get_state(1)["level"] == 3


def test_no_escalation_after_level3():
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda team_id: {"phone": "139"},
    )
    tracker.trigger(1, message="x", now=_t0())
    tracker.check_escalation(now=_t0() + timedelta(minutes=31))  # 到 level 3
    # 再检查不再升级
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=60))
    assert actions == []


# ========== check_escalation 多告警 ==========

def test_check_escalation_iterates_multiple_alarms():
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda team_id: {"phone": "139"},
    )
    tracker.trigger(1, message="a", now=_t0())
    tracker.trigger(2, message="b", now=_t0())
    tracker.ack(2, now=_t0() + timedelta(minutes=1))  # 告警2已确认
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=16))
    # 只有告警1升级短信, 告警2已ack跳过
    alarm_ids = {a["alarm_id"] for a in actions}
    assert alarm_ids == {1}


# ========== 配置默认值 ==========

def test_default_sms_escalate_min_from_settings(monkeypatch):
    """未显式传 sms_escalate_min → 读 settings.ALARM_SMS_ESCALATE_MIN。"""
    from app.services import alarm_escalation as ae
    monkeypatch.setattr(ae, "_get_setting", lambda name, default: 20 if name == "ALARM_SMS_ESCALATE_MIN" else default)
    tracker = AlarmEscalationTracker()
    assert tracker.sms_escalate_min == 20
    assert tracker.voice_escalate_min == 40  # = 2 * sms


def test_explicit_voice_escalate_min_overrides_double():
    tracker = AlarmEscalationTracker(
        notifier=lambda *a, **k: None,
        sms_escalate_min=15, voice_escalate_min=60,
    )
    assert tracker.voice_escalate_min == 60


# ========== 真实发送接线 (notifier 调真实 channel_providers) ==========

def test_default_notifier_calls_real_dispatch(test_db, monkeypatch):
    """默认 notifier 走真实 channel_providers.dispatch_real_channel (mock 之验证接线)。"""
    from app.services import alarm_escalation as ae
    sent = []
    monkeypatch.setattr(ae, "dispatch_real_channel",
                        lambda ch, tid, db, recv, content, subject=None: sent.append(ch) or {"status": "sent"})
    db = test_db["session"]
    tracker = AlarmEscalationTracker(sms_escalate_min=15,
                                     oncall_resolver=lambda tid: {"phone": "139"})
    tracker.trigger(5, message="过温", team_id=1, db=db, now=_t0())
    assert set(sent) == {"im", "wecom"}


# ========== BUG1 (卡 f80b9844): ack 后内存泄漏 — 保留 24h 后清理 ==========

def test_acked_state_purged_after_retention():
    """ack 后保留 24h, 超过则 check_escalation 清理 (状态不无限堆积)。"""
    tracker = AlarmEscalationTracker(notifier=lambda *a, **k: None, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    acked_at = _t0() + timedelta(minutes=5)
    assert tracker.ack(1, now=acked_at) is True
    # 保留期内状态仍在
    assert tracker.get_state(1) is not None
    # 超 24h 后巡检 → 清理
    tracker.check_escalation(now=acked_at + timedelta(hours=24, seconds=1))
    assert tracker.get_state(1) is None


def test_acked_state_retained_within_24h():
    """ack 后未满 24h 不清理 (保留窗口内仍可查 ack 记录)。"""
    tracker = AlarmEscalationTracker(notifier=lambda *a, **k: None, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    acked_at = _t0() + timedelta(minutes=5)
    tracker.ack(1, now=acked_at)
    tracker.check_escalation(now=acked_at + timedelta(hours=23))
    assert tracker.get_state(1) is not None


def test_active_unacked_state_never_purged():
    """未 ack 的活动告警即使过 24h 也不清理 (避免误清正在升级的告警)。"""
    tracker = AlarmEscalationTracker(
        notifier=lambda *a, **k: None, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    tracker.check_escalation(now=_t0() + timedelta(hours=48))
    assert tracker.get_state(1) is not None


# ========== BUG2 (卡 f80b9844): 线程安全 — _states 加锁 ==========

def test_state_access_holds_lock_during_notify():
    """trigger/check_escalation 的 _notify 在 _lock 持有期内执行 (线程安全契约)。"""
    held = []
    tracker = AlarmEscalationTracker(
        notifier=lambda *a, **k: held.append(tracker._lock.locked()),
        sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", now=_t0())
    tracker.check_escalation(now=_t0() + timedelta(minutes=31))
    assert held, "notifier 未被调用"
    assert all(held), "存在 _states 访问未持锁"


def test_concurrent_check_escalation_no_duplicate_voice():
    """并发 check_escalation 同一告警, 加锁后 voice 升级只触发一次。"""
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())

    def slow_notify(level, channel, alarm_id, message, receiver=None):
        # 放大 check(level<3) 与 act(level=3) 之间的竞态窗口
        time.sleep(0.02)
        calls.append({"level": level, "channel": channel, "alarm_id": alarm_id})

    tracker._notifier = slow_notify

    now = _t0() + timedelta(minutes=31)  # 超 voice 阈值
    n = 8
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        tracker.check_escalation(now=now)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    voice = [c for c in calls if c["channel"] == "voice"]
    assert len(voice) == 1, f"voice 应只升级一次, 实际 {len(voice)} 次 (锁失效)"


# ========== BUG3 (卡 f80b9844): 跨级跳 SMS — voice 升级补发 sms ==========

def test_cross_level_voice_also_sends_sms():
    """sms+voice 阈值同时满足时, voice 升级同时补发 sms, 不跳过 sms 层。"""
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    # +31min 同时超 sms(15) 与 voice(30)
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=31))
    channels = {a["channel"] for a in actions}
    assert "voice" in channels
    assert "sms" in channels  # 跨级补发
    sms = [a for a in actions if a["channel"] == "sms"]
    voice = [a for a in actions if a["channel"] == "voice"]
    assert len(sms) == 1 and sms[0]["level"] == 2
    assert len(voice) == 1 and voice[0]["level"] == 3
    assert tracker.get_state(1)["level"] == 3


def test_cross_level_no_duplicate_sms_when_already_level2():
    """渐进升级 (先 sms 再 voice) 时, voice 不重复补发 sms。"""
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    tracker.check_escalation(now=_t0() + timedelta(minutes=16))  # 先到 level2 (sms)
    calls.clear()
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=31))  # 再到 voice
    sms = [a for a in actions if a["channel"] == "sms"]
    assert len(sms) == 0  # 已发过 sms, 不补发
    voice = [a for a in actions if a["channel"] == "voice"]
    assert len(voice) == 1


# ========== BUG4 (卡 f80b9844): clock skew — elapsed 为负钳位 0 ==========

def test_negative_elapsed_does_not_escalate():
    """时钟回拨 (now 早于 triggered_at) 时 elapsed 钳位 0, 不误升级到高级。"""
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    # now 早于 triggered_at 10min (clock skew)
    actions = tracker.check_escalation(now=_t0() - timedelta(minutes=10))
    assert actions == []
    assert tracker.get_state(1)["level"] == 1  # 不升级


def test_clock_skew_then_normal_escalation_still_works():
    """clock skew 不破坏后续正常升级 (回拨后再到阈值仍能升级)。"""
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    tracker.check_escalation(now=_t0() - timedelta(minutes=10))  # skew, 不升级
    assert tracker.get_state(1)["level"] == 1
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=16))  # 正常到 sms
    assert [a for a in actions if a["channel"] == "sms"]
    assert tracker.get_state(1)["level"] == 2


# ========== 异常兜底 / 默认时钟分支 (补 92%→~100% 缺口) ==========
#
# 覆盖 _default_notifier 异常路径 / _resolve_oncall 异常路径 / _get_setting except /
# trigger & check_escalation 未传 now 走真实时钟 —— 均为「外部依赖失败不拖垮升级链」
# 的真实异常契约, 非死分支。

def test_default_notifier_swallows_dispatch_exception(monkeypatch):
    """默认 notifier: dispatch_real_channel 抛异常被吞, 不向 trigger 调用方冒泡。"""
    from app.services import alarm_escalation as ae
    monkeypatch.setattr(
        ae, "dispatch_real_channel",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("channel down")),
    )
    # 不注入 notifier → 走 _default_notifier
    tracker = AlarmEscalationTracker(sms_escalate_min=15)
    # trigger 内部 _notify 不应抛
    actions = tracker.trigger(1, message="过温", team_id=1, now=_t0())
    assert {a["channel"] for a in actions} == {"im", "wecom"}


def test_resolve_oncall_swallows_resolver_exception():
    """oncall_resolver 抛异常 → _resolve_oncall 回退 None, 不影响升级流程。"""
    def boom(team_id):
        raise RuntimeError("oncall lookup failed")
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(
        notifier=notifier, sms_escalate_min=15, oncall_resolver=boom,
    )
    tracker.trigger(1, message="x", team_id=1, now=_t0())
    # 到 sms 阈值, resolver 抛错但升级照常 (receiver=None)
    actions = tracker.check_escalation(now=_t0() + timedelta(minutes=16))
    sms = [a for a in actions if a["channel"] == "sms"]
    assert len(sms) == 1
    assert sms[0]["receiver"] is None  # resolver 异常回退 None


def test_resolve_oncall_none_when_no_resolver():
    """未注入 oncall_resolver → _resolve_oncall 直接返回 None。"""
    tracker = AlarmEscalationTracker(sms_escalate_min=15)
    assert tracker._resolve_oncall(1) is None


def test_get_setting_falls_back_on_exception(monkeypatch):
    """_get_setting: import app.core.config 失败时 except 兜底回退 default。

    _get_setting 函数体内 `from app.core.config import settings`, 让该 import 抛
    ImportError 即命中 except 分支 (卡: settings 不可达不拖垮升级链初始化)。
    """
    from app.services import alarm_escalation as ae
    import sys

    real_config = sys.modules.get("app.core.config")
    monkeypatch.setitem(sys.modules, "app.core.config", None)  # import 触发 TypeError
    try:
        assert ae._get_setting("ALARM_SMS_ESCALATE_MIN", 15) == 15
    finally:
        if real_config is not None:
            sys.modules["app.core.config"] = real_config


def test_get_setting_returns_default_when_attr_none(monkeypatch):
    """_get_setting: settings 字段值为 None 时回退 default。"""
    from app.services import alarm_escalation as ae
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "ALARM_SMS_ESCALATE_MIN", None, raising=False)
    assert ae._get_setting("ALARM_SMS_ESCALATE_MIN", 42) == 42


def test_trigger_defaults_now_to_utc_when_omitted():
    """trigger 未传 now → 用 datetime.now(timezone.utc), state.triggered_at 为 aware UTC。"""
    tracker = AlarmEscalationTracker(notifier=lambda *a, **k: None, sms_escalate_min=15)
    before = datetime.now(timezone.utc)
    tracker.trigger(1, message="x")
    triggered = tracker.get_state(1)["triggered_at"]
    assert triggered.tzinfo is not None
    assert before <= triggered <= datetime.now(timezone.utc) + timedelta(seconds=1)


def test_check_escalation_defaults_now_when_omitted():
    """check_escalation 未传 now → 用真实时钟; 对一个很早触发且无阈值注入的告警,
    默认 sms=15min 下不会立即升级 (此刻 elapsed 不足), 不抛即可。"""
    tracker = AlarmEscalationTracker(
        notifier=lambda *a, **k: None, sms_escalate_min=15,
        oncall_resolver=lambda tid: {"phone": "139"},
    )
    tracker.trigger(1, message="x", team_id=1)  # now=真实此刻
    # 立即巡检, elapsed≈0 < 15min, 无升级动作, 但不抛
    actions = tracker.check_escalation()
    assert [a for a in actions if a["channel"] == "sms"] == []


# ========== 重复 trigger 覆盖语义 (卡 28a05a81) ==========
# trigger 对同一 alarm_id 是整体覆盖: state 重建为 level=1 / acked=False /
# triggered_at=now, 非去重跳过。以下钉住该语义, 防止后续改动无意改变重触发行为。

def test_retrigger_overwrites_state_fields():
    """重触发: message/team_id/receiver/triggered_at 刷新为新值, level 重置 1。"""
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(1, message="旧消息", team_id=1, receiver={"name": "旧"}, now=_t0())
    t1 = _t0() + timedelta(minutes=3)
    tracker.trigger(1, message="新消息", team_id=2, receiver={"name": "新"}, now=t1)
    st = tracker.get_state(1)
    assert st["message"] == "新消息"
    assert st["team_id"] == 2
    assert st["receiver"] == {"name": "新"}
    assert st["triggered_at"] == t1
    assert st["level"] == 1
    assert st["acked"] is False
    assert st["acked_at"] is None


def test_retrigger_restarts_escalation_window():
    """重触发以新 triggered_at 重算升级窗口: 旧窗口视角已近阈值, 新窗口未到 → 不升级。"""
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    t1 = _t0() + timedelta(minutes=10)  # 旧窗口 elapsed=10 < 15
    tracker.trigger(1, message="x", now=t1)
    # t1+4min: 旧窗口视角 14min 仍 < 15, 新窗口 4min → 无 sms
    assert tracker.check_escalation(now=t1 + timedelta(minutes=4)) == []
    # t1+15min: 新窗口到阈值 → sms 升级
    actions = tracker.check_escalation(now=t1 + timedelta(minutes=15))
    assert [a["channel"] for a in actions] == ["sms"]


def test_retrigger_refires_immediate_channels():
    """重触发不去重即时通知: 每次都发 im+wecom level-1 动作。"""
    notifier, calls = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    a1 = tracker.trigger(1, message="x", now=_t0())
    a2 = tracker.trigger(1, message="y", now=_t0() + timedelta(minutes=1))
    assert len(a1) == 2 and len(a2) == 2
    assert [c["channel"] for c in calls] == ["im", "wecom", "im", "wecom"]


def test_retrigger_after_escalation_resets_level_and_refires_sms():
    """已升到 level 2 后重触发 → level 重置 1 (level 守卫复位), 新窗口到点 sms 再升级。"""
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    tracker.check_escalation(now=_t0() + timedelta(minutes=15))  # → level 2
    assert tracker.get_state(1)["level"] == 2
    t1 = _t0() + timedelta(minutes=20)
    tracker.trigger(1, message="x", now=t1)  # 覆盖 → level 1
    assert tracker.get_state(1)["level"] == 1
    # 新窗口 15min 后再次 sms 升级 (每轮触发的升级守卫互相独立)
    actions = tracker.check_escalation(now=t1 + timedelta(minutes=15))
    assert [a["channel"] for a in actions] == ["sms"]


def test_retrigger_revives_acked_chain():
    """ack 后重触发 → acked 复位 False, 升级链复活, 新窗口到点恢复升级。

    注: 这是覆盖语义的自然结果 —— 适用于复发告警重开升级链;
    若上游对同一 alarm_id 重复 trigger, ack 会被冲掉 (钉住现状, 改动需有意识为之)。
    """
    notifier, _ = _recorder()
    tracker = AlarmEscalationTracker(notifier=notifier, sms_escalate_min=15)
    tracker.trigger(1, message="x", now=_t0())
    assert tracker.ack(1, now=_t0() + timedelta(minutes=2)) is True
    t1 = _t0() + timedelta(minutes=30)
    tracker.trigger(1, message="x", now=t1)
    st = tracker.get_state(1)
    assert st["acked"] is False and st["acked_at"] is None
    # ack 后本不再升级; 重触发后新窗口到点恢复升级
    actions = tracker.check_escalation(now=t1 + timedelta(minutes=15))
    assert [a["channel"] for a in actions] == ["sms"]
