"""POST /api/v1/alerts/{alarm_id}/ack 端点测试 (卡 8d98ebe3)

端点确认告警 (AlarmStatus.ACKNOWLEDGED) 并同步终止告警升级链。
"""
from datetime import datetime, timezone

from app.models.alarm import Alarm, AlarmStatus
from app.services.alarm_escalation import AlarmEscalationTracker


def test_ack_alert_success(client, seed_alarms):
    alarm = seed_alarms["over_temp"]
    r = client.post(f"/api/v1/alerts/{alarm.id}/ack")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "acknowledged"
    assert data["alarm_id"] == alarm.id
    # DB 状态已落库
    db = client._sesh
    fresh = db.query(Alarm).filter(Alarm.id == alarm.id).one()
    assert fresh.status == AlarmStatus.ACKNOWLEDGED
    assert fresh.handler_id is not None
    assert fresh.handled_at is not None


def test_ack_alert_404_unknown(client):
    r = client.post("/api/v1/alerts/999999/ack")
    assert r.status_code == 404


def test_ack_alert_requires_auth(anon_client, seed_alarms):
    alarm = seed_alarms["over_temp"]
    r = anon_client.post(f"/api/v1/alerts/{alarm.id}/ack")
    assert r.status_code == 401


def test_ack_alert_terminates_escalation(client, seed_alarms, monkeypatch):
    """端点确认 → 同步终止升级链 (注入独立 tracker 验证)。"""
    from app.api.v1 import alert_ack
    alarm = seed_alarms["comm_fault"]
    tracker = AlarmEscalationTracker(sms_escalate_min=15)
    monkeypatch.setattr(alert_ack, "alarm_escalation_tracker", tracker)
    # 先触发该告警升级链 (未确认)
    tracker.trigger(
        alarm.id, message="通讯中断", team_id=None,
        now=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
    )
    assert tracker.get_state(alarm.id)["acked"] is False

    r = client.post(f"/api/v1/alerts/{alarm.id}/ack")
    assert r.status_code == 200
    assert r.json()["data"]["escalation_terminated"] is True
    # 升级链已终止
    assert tracker.get_state(alarm.id)["acked"] is True


def test_ack_alert_no_active_chain_terminated_false(client, seed_alarms, monkeypatch):
    """告警未触发升级链 → 确认仍成功, escalation_terminated=False (无链可终止)。"""
    from app.api.v1 import alert_ack
    alarm = seed_alarms["over_temp"]
    tracker = AlarmEscalationTracker(sms_escalate_min=15)
    monkeypatch.setattr(alert_ack, "alarm_escalation_tracker", tracker)

    r = client.post(f"/api/v1/alerts/{alarm.id}/ack")
    assert r.status_code == 200
    assert r.json()["data"]["escalation_terminated"] is False
