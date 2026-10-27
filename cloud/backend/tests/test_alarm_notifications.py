"""
告警通知发送记录持久化测试 (maint-platform-spec §2.1)
覆盖:
- 发送成功 → alarm_notifications 写入 sent 记录
- 发送失败 → 写入 failed 记录 + 错误信息
- GET /api/v1/alarms/{id}/notifications 查询（有数据 / 空 / 告警隔离）
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.alarm_notification import AlarmNotification
from app.services.notification_sender import notification_sender

client = TestClient(app)


# ─── fake notification config：绕过 SQLite JSON contains 兼容性 ───
class _FakeConfig:
    id = 1
    scope_type = "tenant"
    sms_enabled = True
    email_enabled = False
    app_push_enabled = False
    im_b_enabled = False
    im_enabled = False
    receivers = [{
        "type": "phone", "id": "13800000000",
        "name": "测试值班员", "phone": "13800000000",
    }]
    receiver_roles = []
    quiet_start = None
    quiet_end = None
    priority = 10
    trigger_events = ["alarm_trigger"]


@pytest.fixture(autouse=True)
def _setup_test_db(test_db, monkeypatch):
    """自动注入 test_db fixture（建表 + 覆盖 SessionLocal）

    额外把 notification_sender 模块的 SessionLocal 指向测试库：
    notification_sender 顶部 `from app.core.database import SessionLocal` 是
    import 时绑定，conftest 覆盖模块属性对它失效，需在此显式 patch，
    否则 send(db=None) 会写入生产库（缺 alarm_notifications 表）。
    """
    monkeypatch.setattr(
        "app.services.notification_sender.SessionLocal",
        test_db["SessionLocal"],
    )
    yield


@pytest.fixture
def auth_token(test_db):
    response = client.post("/api/v1/auth/login", data={
        "username": "admin", "password": "admin123",
    })
    assert response.status_code == 200
    data = response.json()
    return data.get("token") or data.get("data", {}).get("token")


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(name="测试站点", code="TEST-STATION-NOTIF", status=StationStatus.NORMAL)
    db.add(station); db.commit(); db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="TEST-DEV-NOTIF", name="测试设备",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=test_station.id, protocol_type=ProtocolType.MODBUS_RTU,
    )
    db.add(device); db.commit(); db.refresh(device)
    return device


@pytest.fixture
def test_alarm(test_db, test_device):
    db = test_db["session"]
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    alarm = Alarm(
        device_id=test_device.id, station_id=test_device.station_id,
        alarm_type="temperature_high", level=AlarmLevel.WARNING,
        content="温度超过阈值", status=AlarmStatus.ACTIVE,
    )
    db.add(alarm); db.commit(); db.refresh(alarm)
    return alarm


def _reload_session(test_db):
    """强制刷新 session 缓存，看到服务层在另一 session 写入并 commit 的数据"""
    db = test_db["session"]
    db.commit()
    db.expire_all()
    return db


# ════════════════════════════════════════════
# 服务层：发送 → 记录写入
# ════════════════════════════════════════════

class TestSendAlarmNotificationWritesRecord:
    """send_alarm_notification 发送后必须写入 alarm_notifications"""

    def test_send_success_records_sent(self, test_db, test_alarm, monkeypatch):
        """发送成功 → 写入 status=sent 记录"""
        # 绕过配置查找 + mock 底层分发器
        monkeypatch.setattr(notification_sender, "_find_configs",
                            lambda db, et: [_FakeConfig()])
        monkeypatch.setattr(notification_sender._dispatcher, "notify_sms",
                            lambda **kw: None)

        result = notification_sender.send_alarm_notification(
            alarm_id=test_alarm.id, alarm_content="温度超过阈值",
            device_id=test_alarm.device_id, station_id=test_alarm.station_id,
            level="warning", db=None,
        )
        assert result["status"] == "ok"

        db = _reload_session(test_db)
        records = db.query(AlarmNotification).filter_by(alarm_id=test_alarm.id).all()
        assert len(records) == 1
        rec = records[0]
        assert rec.channel == "sms"
        assert rec.status == "sent"
        assert rec.recipient == "13800000000"
        assert rec.sent_at is not None

    def test_send_failure_records_failed_with_error(self, test_db, test_alarm, monkeypatch):
        """发送失败 → 写入 status=failed 记录，result 含错误信息"""
        monkeypatch.setattr(notification_sender, "_find_configs",
                            lambda db, et: [_FakeConfig()])
        def _boom(**kw):
            raise RuntimeError("短信网关超时")
        monkeypatch.setattr(notification_sender._dispatcher, "notify_sms", _boom)

        result = notification_sender.send_alarm_notification(
            alarm_id=test_alarm.id, alarm_content="温度超过阈值",
            device_id=test_alarm.device_id, station_id=test_alarm.station_id,
            level="warning", db=None,
        )
        assert result["status"] == "ok"

        db = _reload_session(test_db)
        records = db.query(AlarmNotification).filter_by(alarm_id=test_alarm.id).all()
        assert len(records) == 1
        rec = records[0]
        assert rec.status == "failed"
        # result 字段须脱敏，原始异常文本不得泄露（仅 ERROR 日志保留原始信息）
        assert (rec.result or "") == "服务内部错误，请稍后重试"
        assert "短信网关超时" not in (rec.result or "")

    def test_no_config_no_record(self, test_db, test_alarm, monkeypatch):
        """无匹配配置 → 不产生发送记录"""
        monkeypatch.setattr(notification_sender, "_find_configs",
                            lambda db, et: [])

        notification_sender.send_alarm_notification(
            alarm_id=test_alarm.id, alarm_content="温度超过阈值",
            device_id=test_alarm.device_id, station_id=test_alarm.station_id,
            level="warning", db=None,
        )

        db = _reload_session(test_db)
        records = db.query(AlarmNotification).filter_by(alarm_id=test_alarm.id).all()
        assert records == []


# ════════════════════════════════════════════
# API 层：GET /api/v1/alarms/{id}/notifications
# ════════════════════════════════════════════

class TestAlarmNotificationsAPI:

    def _insert_record(self, db, alarm_id, channel="sms", recipient="13800000000",
                       status="sent", result=None):
        rec = AlarmNotification(
            alarm_id=alarm_id, channel=channel, recipient=recipient,
            status=status, result=result,
        )
        db.add(rec); db.commit(); db.refresh(rec)
        return rec

    def test_get_notifications_returns_records(self, auth_token, test_db, test_alarm):
        """查询告警通知记录 — 返回该告警下的全部记录"""
        db = test_db["session"]
        self._insert_record(db, test_alarm.id, channel="sms", status="sent")
        self._insert_record(db, test_alarm.id, channel="email", recipient="a@b.com",
                            status="failed", result="SMTP 拒绝")

        response = client.get(
            f"/api/v1/alarms/{test_alarm.id}/notifications",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        items = data.get("items", data) if isinstance(data, dict) else data
        channels = {it["channel"] for it in items}
        assert channels == {"sms", "email"}

    def test_get_notifications_empty(self, auth_token, test_alarm):
        """告警无通知记录 → 返回空列表"""
        response = client.get(
            f"/api/v1/alarms/{test_alarm.id}/notifications",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        items = data.get("items", data) if isinstance(data, dict) else data
        assert items == []

    def test_get_notifications_isolated_by_alarm(self, auth_token, test_db, test_alarm):
        """不同告警的通知记录互不干扰"""
        db = test_db["session"]
        # 另一条告警的记录
        self._insert_record(db, alarm_id=999_999, channel="sms", status="sent")
        # 当前告警的记录
        self._insert_record(db, test_alarm.id, channel="email", status="sent")

        response = client.get(
            f"/api/v1/alarms/{test_alarm.id}/notifications",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) == 1
        assert items[0]["alarm_id"] == test_alarm.id

    def test_get_notifications_unauthorized(self, anon_client, test_alarm):
        """无 token → 401"""
        response = anon_client.get(f"/api/v1/alarms/{test_alarm.id}/notifications")
        assert response.status_code in (401, 403)
