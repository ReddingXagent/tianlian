"""
alert_workflow.py 越权收紧回归测试 (卡 7fd8f66 / 审计 #5)

修复前: router 级 require_role("admin","operator") 即放行, operator 可
为他队设备创建 Alarm+WorkOrder、读/改写他队工单 (diagnosis/repair/verify)、
篡改他队设备 health_score, stats 端点为全平台口径 (跨队数据泄漏)。

修复后契约 (对齐 digital_twin._check_device_team / deps.assert_team_access):
  - trigger/status/diagnosis/repair/verify: 跨队 → 404 (不泄露存在),
    本队 → 200, platform admin 全通
  - verify 被跨队拒绝后, 他队设备 health_score 不被篡改
  - stats: 团队级仅本队口径, platform admin 全平台口径
"""
import bcrypt
import pytest

from app.models.user import User, UserRole, Team
from app.models.station import Station, StationStatus
from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.workorder import WorkOrder, WorkOrderStatus, WorkOrderType, WorkOrderLevel


@pytest.fixture
def env(client):
    """seed 两队各一站一设备一告警一工单 + 本队 operator"""
    s = client._sesh

    team_a = Team(name="卡7fd8f66_A队", type="ops_company")
    team_b = Team(name="卡7fd8f66_B队", type="ops_company")
    s.add_all([team_a, team_b])
    s.flush()

    st_a = Station(name="A站", code="AWF-A-001", status=StationStatus.NORMAL, team_id=team_a.id)
    st_b = Station(name="B站", code="AWF-B-001", status=StationStatus.NORMAL, team_id=team_b.id)
    s.add_all([st_a, st_b])
    s.flush()

    dev_a = Device(sn="AWF-DEV-A", name="A队设备", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=st_a.id,
                   protocol_type=ProtocolType.MODBUS_RTU, health_score=95.0)
    dev_b = Device(sn="AWF-DEV-B", name="B队设备", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=st_b.id,
                   protocol_type=ProtocolType.MODBUS_RTU, health_score=90.0)
    s.add_all([dev_a, dev_b])
    s.flush()

    op = User(
        username="awf_op_7fd8f66",
        password_hash=bcrypt.hashpw(b"op123456", bcrypt.gensalt()).decode(),
        real_name="A队operator", role=UserRole.OPERATOR,
        team_id=team_a.id, status="active", phone="13900000001",
    )
    s.add(op)
    s.flush()

    alarm_a = Alarm(device_id=dev_a.id, station_id=st_a.id, content="A队告警",
                    level=AlarmLevel.CRITICAL, status=AlarmStatus.ACTIVE)
    alarm_b = Alarm(device_id=dev_b.id, station_id=st_b.id, content="B队告警",
                    level=AlarmLevel.CRITICAL, status=AlarmStatus.ACTIVE)
    s.add_all([alarm_a, alarm_b])
    s.flush()

    wo_a = WorkOrder(id="AWF-WO-A-0001", device_id=dev_a.id, station_id=st_a.id,
                     type=WorkOrderType.REPAIR, level=WorkOrderLevel.WARNING,
                     status=WorkOrderStatus.PENDING, fault_desc="A队工单")
    wo_b = WorkOrder(id="AWF-WO-B-0001", device_id=dev_b.id, station_id=st_b.id,
                     type=WorkOrderType.REPAIR, level=WorkOrderLevel.WARNING,
                     status=WorkOrderStatus.PENDING, fault_desc="B队工单")
    s.add_all([wo_a, wo_b])
    s.commit()

    yield {
        "client": client, "team_a": team_a.id, "team_b": team_b.id,
        "dev_a": dev_a.id, "dev_b": dev_b.id,
        "alarm_a": alarm_a.id, "alarm_b": alarm_b.id,
        "wo_a": wo_a.id, "wo_b": wo_b.id,
        "wo_b_device": dev_b.id,
    }


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _op_hdr(client):
    return {"Authorization": f"Bearer {_login(client, 'awf_op_7fd8f66', 'op123456')}"}


def _admin_hdr(client):
    return {"Authorization": f"Bearer {_login(client, 'admin', 'admin123')}"}


# ===== trigger: 跨队创建 Alarm+WorkOrder → 404 =====

def test_operator_cannot_trigger_alert_for_other_team_device(env):
    e = env
    r = e["client"].post("/api/v1/alert-workflow/trigger", headers=_op_hdr(e["client"]), json={
        "device_id": e["dev_b"], "alert_type": "predictive",
        "severity": "critical", "message": "跨队投毒",
    })
    assert r.status_code == 404, f"跨队 trigger 未拒: {r.status_code} {r.text}"


def test_operator_triggers_alert_for_own_team_device(env):
    e = env
    r = e["client"].post("/api/v1/alert-workflow/trigger", headers=_op_hdr(e["client"]), json={
        "device_id": e["dev_a"], "alert_type": "predictive",
        "severity": "critical", "message": "本队告警",
    })
    assert r.status_code == 200, r.text
    assert r.json()["data"]["auto_workorder"] is True


def test_admin_triggers_alert_for_any_team_device(env):
    e = env
    r = e["client"].post("/api/v1/alert-workflow/trigger", headers=_admin_hdr(e["client"]), json={
        "device_id": e["dev_b"], "alert_type": "predictive",
        "severity": "critical", "message": "admin跨队",
    })
    assert r.status_code == 200, r.text


# ===== status: 跨队告警状态 → 404 =====

def test_operator_cannot_read_other_team_workflow_status(env):
    e = env
    r = e["client"].get(f"/api/v1/alert-workflow/status/{e['alarm_b']}",
                        headers=_op_hdr(e["client"]))
    assert r.status_code == 404, f"跨队 status 未拒: {r.status_code} {r.text}"


def test_operator_reads_own_team_workflow_status(env):
    e = env
    r = e["client"].get(f"/api/v1/alert-workflow/status/{e['alarm_a']}",
                        headers=_op_hdr(e["client"]))
    assert r.status_code == 200, r.text


# ===== diagnosis / repair / verify: 跨队工单改写 → 404 =====

DIAGNOSIS_BODY = {"diagnosis_type": "manual", "findings": ["f1"],
                  "root_cause": "rc", "suggested_actions": ["a1"]}
REPAIR_BODY = {"repair_type": "manual", "actions_taken": ["a"],
               "duration_minutes": 10}
VERIFY_BODY = {"verification_type": "manual", "checks_passed": ["c1"],
               "health_score_after": 10.0}


@pytest.mark.parametrize("path,body", [
    ("/diagnosis", DIAGNOSIS_BODY),
    ("/repair", REPAIR_BODY),
    ("/verify", VERIFY_BODY),
])
def test_operator_cannot_mutate_other_team_workorder(env, path, body):
    e = env
    payload = {"workorder_id": e["wo_b"], **body}
    r = e["client"].post(f"/api/v1/alert-workflow{path}",
                         headers=_op_hdr(e["client"]), json=payload)
    assert r.status_code == 404, f"跨队 {path} 未拒: {r.status_code} {r.text}"


@pytest.mark.parametrize("path,body", [
    ("/diagnosis", DIAGNOSIS_BODY),
    ("/repair", REPAIR_BODY),
    ("/verify", VERIFY_BODY),
])
def test_operator_mutates_own_team_workorder(env, path, body):
    e = env
    payload = {"workorder_id": e["wo_a"], **body}
    r = e["client"].post(f"/api/v1/alert-workflow{path}",
                         headers=_op_hdr(e["client"]), json=payload)
    assert r.status_code == 200, f"本队 {path} 被拒: {r.status_code} {r.text}"


@pytest.mark.parametrize("path,body", [
    ("/diagnosis", DIAGNOSIS_BODY),
    ("/repair", REPAIR_BODY),
    ("/verify", VERIFY_BODY),
])
def test_admin_mutates_any_team_workorder(env, path, body):
    e = env
    payload = {"workorder_id": e["wo_b"], **body}
    r = e["client"].post(f"/api/v1/alert-workflow{path}",
                         headers=_admin_hdr(e["client"]), json=payload)
    assert r.status_code == 200, f"admin {path} 被拒: {r.status_code} {r.text}"


# ===== verify 拒绝后他队设备 health_score 不被篡改 =====

def test_cross_team_verify_rejected_health_score_intact(env):
    e = env
    s = e["client"]._sesh
    # 给 B 队告警挂上工单, 让 verify 命中 health_score 更新路径
    alarm_b = s.query(Alarm).filter(Alarm.id == e["alarm_b"]).first()
    alarm_b.workorder_id = e["wo_b"]
    s.commit()

    r = e["client"].post("/api/v1/alert-workflow/verify",
                         headers=_op_hdr(e["client"]),
                         json={"workorder_id": e["wo_b"], **VERIFY_BODY})
    assert r.status_code == 404, r.text

    s.expire_all()
    dev_b = s.query(Device).filter(Device.id == e["wo_b_device"]).first()
    assert dev_b.health_score == 90.0, f"跨队 verify 被拒后 health_score 仍被篡改: {dev_b.health_score}"


# ===== stats: 团队级仅本队口径 / admin 全平台 =====

def test_operator_stats_only_own_team(env):
    e = env
    r = e["client"].get("/api/v1/alert-workflow/stats", headers=_op_hdr(e["client"]))
    assert r.status_code == 200, r.text
    stats = r.json()["data"]
    # seed: A队 1告警1工单 / B队 1告警1工单; 本 test 独立 DB 无其他数据
    assert stats["alerts"]["total"] == 1, f"operator stats 泄漏他队告警: {stats['alerts']}"
    assert stats["workorders"]["total"] == 1, f"operator stats 泄漏他队工单: {stats['workorders']}"


def test_admin_stats_platform_wide(env):
    e = env
    r = e["client"].get("/api/v1/alert-workflow/stats", headers=_admin_hdr(e["client"]))
    assert r.status_code == 200, r.text
    stats = r.json()["data"]
    assert stats["alerts"]["total"] >= 2, stats
    assert stats["workorders"]["total"] >= 2, stats
