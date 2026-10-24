#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据分析报表 API 测试 (SPEC第9章)
覆盖: /reports/summary, /reports/devices, /reports/workorders, /reports/alarms
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture — 覆盖 SessionLocal 使 client 使用测试库"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    if resp.status_code != 200:
        pytest.fail(f"Login failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _seed_test_data(test_db):
    """使用 test_db session 注入测试数据"""
    import bcrypt
    from app.models.user import User, UserRole, EngineerLevel, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    s = test_db["session"]

    # 创建团队
    team = Team(name="运维一组", code="T001", description="核心运维团队")
    s.add(team)
    s.flush()

    # 创建工程师用户
    for uname, pwd, rname, role, lvl, tid in [
        ("eng1", "eng123", "张工", UserRole.ENGINEER, EngineerLevel.SENIOR, team.id),
        ("eng2", "eng123", "李工", UserRole.ENGINEER, EngineerLevel.MIDDLE, team.id),
        ("eng3", "eng123", "王工", UserRole.ENGINEER, EngineerLevel.JUNIOR, team.id),
    ]:
        s.add(User(
            username=uname,
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
            real_name=rname, role=role, level=lvl, team_id=tid,
            status="active",
        ))
    s.flush()
    eng1, eng2, eng3 = [s.query(User).filter(User.username == u).first() for u in ("eng1", "eng2", "eng3")]

    # 创建站点
    now = datetime.now(timezone.utc)
    s1 = Station(name="朝阳电站", code="STA001", address="北京朝阳",
                 status=StationStatus.NORMAL, health_score=92.0, team_id=team.id)
    s2 = Station(name="浦东电站", code="STA002", address="上海浦东",
                 status=StationStatus.NORMAL, health_score=78.0, team_id=team.id)
    s.add_all([s1, s2])
    s.flush()

    # 创建设备
    dev_online = Device(
        sn="SN-001", name="逆变器#1", code="INV001", type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE, station_id=s1.id, health_score=95.0, rated_power=50.0,
    )
    dev_charging = Device(
        sn="SN-002", name="充电桩#1", code="CHG001", type=DeviceType.CHARGER_DC,
        status=DeviceStatus.CHARGING, station_id=s1.id, health_score=88.0, rated_power=120.0,
    )
    dev_fault = Device(
        sn="SN-003", name="储能PCS#1", code="PCS001", type=DeviceType.PCS,
        status=DeviceStatus.FAULT, station_id=s2.id, health_score=45.0, rated_power=50.0,
    )
    dev_offline = Device(
        sn="SN-004", name="离线设备#1", code="OFF001", type=DeviceType.BATTERY_INVERTER,
        status=DeviceStatus.OFFLINE, station_id=s2.id, health_score=None, rated_power=30.0,
    )
    dev_maint = Device(
        sn="SN-005", name="维护设备#1", code="MAINT001", type=DeviceType.METER,
        status=DeviceStatus.MAINTENANCE, station_id=s1.id, health_score=75.0, rated_power=None,
    )
    s.add_all([dev_online, dev_charging, dev_fault, dev_offline, dev_maint])
    s.flush()

    # 创建工单
    base_time = now - timedelta(days=10)
    s.add_all([
        WorkOrder(id="WO-001", type=WorkOrderType.REPAIR, level=WorkOrderLevel.CRITICAL,
                  device_id=dev_fault.id, station_id=s2.id, assignee_id=eng1.id,
                  status=WorkOrderStatus.COMPLETED, fault_desc="PCS通讯中断",
                  create_time=base_time, accept_time=base_time + timedelta(hours=1),
                  finish_time=base_time + timedelta(hours=5)),
        WorkOrder(id="WO-002", type=WorkOrderType.EMERGENCY, level=WorkOrderLevel.WARNING,
                  device_id=dev_fault.id, station_id=s2.id, assignee_id=eng1.id,
                  status=WorkOrderStatus.COMPLETED, fault_desc="电池温度异常",
                  create_time=base_time + timedelta(days=1),
                  accept_time=base_time + timedelta(days=1, hours=2),
                  finish_time=base_time + timedelta(days=1, hours=8)),
        WorkOrder(id="WO-003", type=WorkOrderType.PREVENTIVE, level=WorkOrderLevel.INFO,
                  device_id=dev_online.id, station_id=s1.id, assignee_id=eng2.id,
                  status=WorkOrderStatus.PENDING, fault_desc="定期巡检",
                  create_time=base_time + timedelta(days=2)),
        WorkOrder(id="WO-004", type=WorkOrderType.REPAIR, level=WorkOrderLevel.CRITICAL,
                  device_id=dev_charging.id, station_id=s1.id, assignee_id=eng2.id,
                  status=WorkOrderStatus.PROCESSING, fault_desc="充电桩急停",
                  create_time=base_time + timedelta(days=3),
                  accept_time=base_time + timedelta(days=3, hours=1)),
        WorkOrder(id="WO-005", type=WorkOrderType.PLAN, level=WorkOrderLevel.WARNING,
                  device_id=dev_maint.id, station_id=s1.id, assignee_id=eng3.id,
                  status=WorkOrderStatus.PENDING_VERIFY, fault_desc="设备维护",
                  create_time=base_time + timedelta(days=4),
                  accept_time=base_time + timedelta(days=4, hours=3),
                  finish_time=base_time + timedelta(days=4, hours=10)),
    ])
    s.flush()

    # 创建告警
    alarm_time = now - timedelta(days=5)
    s.add_all([
        Alarm(device_id=dev_fault.id, station_id=s2.id, alarm_type="comm_fault",
              level=AlarmLevel.CRITICAL, content="通讯中断", status=AlarmStatus.ACTIVE,
              created_at=alarm_time),
        Alarm(device_id=dev_fault.id, station_id=s2.id, alarm_type="over_temp",
              level=AlarmLevel.WARNING, content="温度过高预警", status=AlarmStatus.ACTIVE,
              created_at=alarm_time + timedelta(hours=2)),
        Alarm(device_id=dev_fault.id, station_id=s2.id, alarm_type="over_temp",
              level=AlarmLevel.WARNING, content="温度过高预警", status=AlarmStatus.RESOLVED,
              created_at=alarm_time + timedelta(days=1),
              resolved_at=alarm_time + timedelta(days=1, hours=3)),
        Alarm(device_id=dev_charging.id, station_id=s1.id, alarm_type="emergency_stop",
              level=AlarmLevel.CRITICAL, content="急停触发", status=AlarmStatus.PROCESSING,
              created_at=alarm_time + timedelta(days=2)),
        Alarm(device_id=dev_online.id, station_id=s1.id, alarm_type="grid_voltage",
              level=AlarmLevel.INFO, content="电网电压波动", status=AlarmStatus.ACKNOWLEDGED,
              created_at=alarm_time + timedelta(days=3)),
        Alarm(device_id=dev_maint.id, station_id=s1.id, alarm_type="over_temp",
              level=AlarmLevel.WARNING, content="温度偏高", status=AlarmStatus.RESOLVED,
              created_at=alarm_time + timedelta(hours=6),
              resolved_at=alarm_time + timedelta(hours=10)),
    ])
    s.commit()


# ═══════════════════════════════════════════════
# 鉴权测试
# ═══════════════════════════════════════════════

def test_summary_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/reports/summary")
    assert resp.status_code in (401, 403)


def test_devices_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/reports/devices")
    assert resp.status_code in (401, 403)


def test_workorders_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/reports/workorders")
    assert resp.status_code in (401, 403)


def test_alarms_requires_auth(anon_client):
    resp = anon_client.get("/api/v1/reports/alarms")
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════
# 空数据测试
# ═══════════════════════════════════════════════

def test_summary_empty():
    """空数据库的汇总报表"""
    token = _login()
    resp = client.get("/api/v1/reports/summary?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert "overview" in data
    assert data["overview"]["total_devices"] == 0
    assert data["overview"]["total_stations"] == 0
    assert data["overview"]["total_workorders"] == 0
    assert data["overview"]["total_alarms"] == 0
    assert "station_health" in data
    assert "team_performance" in data


def test_devices_empty():
    token = _login()
    resp = client.get("/api/v1/reports/devices", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert data["total_devices"] == 0
    assert data["type_distribution"] == {}
    assert data["online_rate"] == 0


def test_workorders_empty():
    token = _login()
    resp = client.get("/api/v1/reports/workorders?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert data["total_workorders"] == 0
    assert data["completion_rate"] == 0


def test_alarms_empty():
    token = _login()
    resp = client.get("/api/v1/reports/alarms?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert data["total_alarms"] == 0
    assert data["resolved_rate"] == 0
    assert data["top_fault_devices"] == []


# ═══════════════════════════════════════════════
# 有数据测试
# ═══════════════════════════════════════════════

def test_summary_with_data(test_db):
    """有数据时的汇总报表验证"""
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/summary?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())

    overview = data["overview"]
    assert overview["total_devices"] == 5
    assert overview["total_stations"] == 2
    assert overview["total_workorders"] == 5
    assert overview["total_alarms"] == 6

    sh = data["station_health"]
    assert sh["distribution"]["normal"] >= 0
    assert sh["healthy_rate"] > 0

    tp = data["team_performance"]
    assert tp["total_engineers"] >= 3
    assert len(tp["engineers"]) >= 3
    assert len(tp["top_engineers"]) > 0
    eng_with_orders = [e for e in tp["engineers"] if e["assigned"] > 0]
    assert len(eng_with_orders) > 0
    for e in eng_with_orders:
        assert e["performance_score"] > 0


def test_devices_with_data(test_db):
    """有数据时的设备报表验证"""
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/devices?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())

    assert data["total_devices"] == 5
    assert sum(data["type_distribution"].values()) == 5
    sd = data["status_distribution"]
    assert sd.get("online", 0) >= 1
    assert sd.get("fault", 0) >= 1
    assert sd.get("offline", 0) >= 1
    assert len(data["station_distribution"]) == 2
    assert data["health_score"]["average"] > 0
    assert sum(data["health_score"]["distribution"].values()) == 5


def test_workorders_with_data(test_db):
    """有数据时的工单报表验证"""
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/workorders?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())

    assert data["total_workorders"] == 5
    assert data["completion_rate"] > 0
    assert sum(data["type_distribution"].values()) == 5
    assert "completed" in data["status_distribution"]
    assert "pending" in data["status_distribution"]
    eff = data["efficiency"]
    assert eff["avg_response_hours"] > 0
    assert eff["avg_completion_hours"] > 0
    eps = data["engineer_performance"]
    assert len(eps) > 0
    working = [e for e in eps if e["assigned"] > 0]
    assert len(working) >= 1


def test_alarms_with_data(test_db):
    """有数据时的告警报表验证"""
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/alarms?days=30", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())

    assert data["total_alarms"] == 6
    assert data["resolved_rate"] > 0
    ld = data["level_distribution"]
    assert ld.get("critical", 0) >= 1
    assert ld.get("warning", 0) >= 1
    assert ld.get("info", 0) >= 1
    assert sum(data["type_distribution"].values()) == 6
    assert data["active_alarms"] > 0
    assert len(data["top_fault_devices"]) > 0
    assert len(data["daily_trend"]) > 0


# ═══════════════════════════════════════════════
# CSV/XLSX 导出测试
# ═══════════════════════════════════════════════

def test_export_summary_csv(test_db):
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/summary?format=csv", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    assert ct.startswith("text/csv")
    cd = resp.headers.get("content-disposition", "").lower()
    assert "summary.csv" in cd


def test_export_devices_xlsx(test_db):
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/devices?format=xlsx", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers.get("content-type", "")
    assert "devices.xlsx" in resp.headers.get("content-disposition", "")


def test_export_workorders_csv(test_db):
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/workorders?format=csv", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "")


def test_export_alarms_csv(test_db):
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/alarms?format=csv", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "")


# ═══════════════════════════════════════════════
# 边界测试
# ═══════════════════════════════════════════════

def test_summary_days_over_limit_rejected():
    """days 超上限(>90)被拒 — 安全修复:days 边界验证(旧测试断言 200 固化了无校验漏洞,翻转)"""
    token = _login()
    resp = client.get("/api/v1/reports/summary?days=365", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_alarms_short_days(test_db):
    """短周期"""
    _seed_test_data(test_db)
    token = _login()
    resp = client.get("/api/v1/reports/alarms?days=1", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert data["total_alarms"] >= 0


def test_workorders_negative_days_rejected():
    """days 为负被拒 — 安全修复:days 边界验证(旧测试断言 200 固化了无校验漏洞,翻转)"""
    token = _login()
    resp = client.get("/api/v1/reports/workorders?days=-1", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422