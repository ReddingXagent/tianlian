#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reports.py 覆盖率补充测试 (任务卡 36407650)
补未覆盖大块: report_faults(故障分析) / report_v2g(V2G运营,空数据) /
              _generate_pdf(PDF导出) / team scoping(非admin隔离) /
              站点健康分布边界 / health fair 分桶
参考 test_reports.py 的模块级 client + autouse test_db 模式。
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

from tests._test_helpers import _fast_hash  # 卡17354607: 复用进程级 bcrypt hash 缓存

@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """覆盖 SessionLocal，使模块级 client 走测试库"""
    pass


def _login_as(username="admin", password="admin123"):
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"login {username} failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _data(resp):
    return resp.json().get("data", resp.json())


# ═══════════════════════════════════════════════
# seed: 故障分析数据 (alarm warning/critical + completed workorder)
# ═══════════════════════════════════════════════
def _seed_fault_data(test_db):
    from app.models.user import Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    s = test_db["session"]
    now = datetime.now(timezone.utc)

    team = Team(name="故障运维组", code="FT001", description="故障分析")
    s.add(team)
    s.flush()
    st = Station(name="故障测试站", code="FSTA001", address="测试地址",
                 status=StationStatus.NORMAL, team_id=team.id)
    s.add(st)
    s.flush()
    dev = Device(sn="FSD001", name="故障设备#1", code="FSD001",
                 type=DeviceType.PCS, status=DeviceStatus.FAULT,
                 station_id=st.id, health_score=40.0, rated_power=50.0)
    s.add(dev)
    s.flush()

    # completed workorder — 供 MTBF/MTTR 计算
    base = now - timedelta(days=5)
    s.add(WorkOrder(
        id="FWO-001", type=WorkOrderType.REPAIR, level=WorkOrderLevel.CRITICAL,
        device_id=dev.id, station_id=st.id, status=WorkOrderStatus.COMPLETED,
        fault_desc="PCS通讯中断", create_time=base,
        accept_time=base + timedelta(hours=1),
        finish_time=base + timedelta(hours=4),
    ))

    # 故障类告警 (warning + critical，排除 info)
    alarm_t = now - timedelta(days=3)
    s.add_all([
        Alarm(device_id=dev.id, station_id=st.id, alarm_type="comm_fault",
              level=AlarmLevel.CRITICAL, content="通讯中断", status=AlarmStatus.ACTIVE,
              created_at=alarm_t),
        Alarm(device_id=dev.id, station_id=st.id, alarm_type="over_temp",
              level=AlarmLevel.WARNING, content="过温预警", status=AlarmStatus.RESOLVED,
              created_at=alarm_t + timedelta(days=1),
              resolved_at=alarm_t + timedelta(days=1, hours=2)),
    ])
    s.commit()
    return {"station": st, "device": dev, "team": team}


# ═══════════════════════════════════════════════
# seed: 两 team 隔离数据 (各1站1设备1告警 + t1 engineer + t1 workorder)
# ═══════════════════════════════════════════════
def _seed_team_scoped(test_db):
    from app.models.user import User, UserRole, EngineerLevel, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

    s = test_db["session"]
    now = datetime.now(timezone.utc)

    t1 = Team(name="甲队", code="TM_A", description="A")
    t2 = Team(name="乙队", code="TM_B", description="B")
    s.add_all([t1, t2])
    s.flush()
    s1 = Station(name="甲站", code="S_A", status=StationStatus.NORMAL, team_id=t1.id)
    s2 = Station(name="乙站", code="S_B", status=StationStatus.NORMAL, team_id=t2.id)
    s.add_all([s1, s2])
    s.flush()
    d1 = Device(sn="D_A", name="甲设备", code="D_A", type=DeviceType.PV_INVERTER,
                status=DeviceStatus.ONLINE, station_id=s1.id, health_score=90.0)
    d2 = Device(sn="D_B", name="乙设备", code="D_B", type=DeviceType.PV_INVERTER,
                status=DeviceStatus.ONLINE, station_id=s2.id, health_score=80.0)
    s.add_all([d1, d2])
    s.flush()

    # t1 工程师 (非平台级，触发 team scoping)
    eng_a = User(
        username="eng_a",
        password_hash=_fast_hash("eng123"),
        real_name="甲工程师", role=UserRole.ENGINEER, level=EngineerLevel.SENIOR,
        team_id=t1.id, status="active",
    )
    s.add(eng_a)
    s.flush()

    # t1 工单 (assignee=eng_a，使 workorders 端点 engineer_performance 非空)
    s.add(WorkOrder(
        id="WO_A1", type=WorkOrderType.REPAIR, level=WorkOrderLevel.WARNING,
        device_id=d1.id, station_id=s1.id, assignee_id=eng_a.id,
        status=WorkOrderStatus.PENDING,
        fault_desc="甲工单", create_time=now - timedelta(days=1),
    ))
    # 甲站 + 乙站各一条告警
    s.add_all([
        Alarm(device_id=d1.id, station_id=s1.id, alarm_type="over_temp",
              level=AlarmLevel.WARNING, content="甲告警", status=AlarmStatus.ACTIVE,
              created_at=now - timedelta(days=1)),
        Alarm(device_id=d2.id, station_id=s2.id, alarm_type="comm_fault",
              level=AlarmLevel.CRITICAL, content="乙告警", status=AlarmStatus.ACTIVE,
              created_at=now - timedelta(days=1)),
    ])
    s.commit()
    return {"t1": t1, "t2": t2, "s1": s1, "s2": s2, "d1": d1, "d2": d2}


# ═══════════════════════════════════════════════
# seed: 站点健康分布边界 (offline/critical/normal) + 设备 health fair 桶
# ═══════════════════════════════════════════════
def _seed_station_health(test_db):
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = test_db["session"]
    # 1) 无设备站点 → offline 分支 (device_count==0)
    s_empty = Station(name="空站点", code="SH_EMPTY", status=StationStatus.NORMAL)
    # 2) 多数设备离线站点 → critical 分支 (offline_count > device_count*0.5)
    s_crit = Station(name="严重站点", code="SH_CRIT", status=StationStatus.NORMAL)
    # 3) 正常站点 → normal 分支
    s_norm = Station(name="正常站点", code="SH_NORM", status=StationStatus.NORMAL)
    s.add_all([s_empty, s_crit, s_norm])
    s.flush()

    # 严重站点: 3 设备 2 离线 (2 > 1.5)
    s.add_all([
        Device(sn="C1", name="crit-1", code="C1", type=DeviceType.PV_INVERTER,
               status=DeviceStatus.OFFLINE, station_id=s_crit.id, health_score=10.0),
        Device(sn="C2", name="crit-2", code="C2", type=DeviceType.PV_INVERTER,
               status=DeviceStatus.OFFLINE, station_id=s_crit.id, health_score=10.0),
        Device(sn="C3", name="crit-3", code="C3", type=DeviceType.PV_INVERTER,
               status=DeviceStatus.ONLINE, station_id=s_crit.id, health_score=85.0),
    ])
    # 正常站点: health=60(fair) + health=30(poor) 设备，均 ONLINE 保持站点 normal
    # (OFFLINE 设备走 unknown 桶不走 poor，故 poor 需 ONLINE 且 hs<50)
    s.add_all([
        Device(sn="N1", name="norm-1", code="N1", type=DeviceType.PV_INVERTER,
               status=DeviceStatus.ONLINE, station_id=s_norm.id, health_score=60.0),
        Device(sn="N2", name="norm-2", code="N2", type=DeviceType.PV_INVERTER,
               status=DeviceStatus.ONLINE, station_id=s_norm.id, health_score=30.0),
    ])
    s.commit()
    return {"empty": s_empty, "critical": s_crit, "normal": s_norm}


# ═══════════════════════════════════════════════
# 5. 故障分析报表 report_faults (501-614)
# ═══════════════════════════════════════════════
def test_faults_empty():
    token = _login_as()
    resp = client.get("/api/v1/reports/faults?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    data = _data(resp)
    assert data["total_faults"] == 0
    assert data["mtbf_hours"] == 0.0
    assert data["mttr_hours"] == 0.0
    assert data["fault_type_distribution"] == {}
    assert data["top_fault_devices"] == []
    assert data["fault_trend"] == []


def test_faults_with_data(test_db):
    _seed_fault_data(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/faults?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    data = _data(resp)
    # warning + critical (info 被排除)
    assert data["total_faults"] >= 2
    assert "comm_fault" in data["fault_type_distribution"]
    fld = data["fault_level_distribution"]
    assert fld["critical"] >= 1
    assert fld["warning"] >= 1
    # 有 completed workorder → MTTR > 0；有故障 → MTBF > 0
    assert data["mttr_hours"] > 0
    assert data["mtbf_hours"] > 0
    assert len(data["top_fault_devices"]) > 0
    assert data["top_fault_devices"][0]["station_name"]  # 含站点名
    assert len(data["fault_trend"]) > 0
    assert len(data["fault_trend_by_type"]) > 0


def test_faults_export_csv(test_db):
    _seed_fault_data(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/faults?format=csv", headers=_hdr(token))
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "")
    assert "faults.csv" in resp.headers.get("content-disposition", "")


def test_faults_export_xlsx(test_db):
    _seed_fault_data(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/faults?format=xlsx", headers=_hdr(token))
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers.get("content-type", "")


def test_faults_export_pdf(test_db):
    """PDF 导出 — 触发 _generate_pdf 有数据路径"""
    _seed_fault_data(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/faults?format=pdf", headers=_hdr(token))
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "") == "application/pdf"
    assert "faults.pdf" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 0


def test_faults_station_id_filter(test_db):
    """station_id 过滤 — 本站存在，admin 放行"""
    seeds = _seed_fault_data(test_db)
    token = _login_as()
    resp = client.get(f"/api/v1/reports/faults?station_id={seeds['station'].id}", headers=_hdr(token))
    assert resp.status_code == 200
    assert _data(resp)["total_faults"] >= 2


# ═══════════════════════════════════════════════
# 6. V2G 运营报表 report_v2g (639-750)
# V2GDispatchLog 已补 actual_energy_kwh 列 (任务卡 0840f884), reports.py 访问
# 改防御性 getattr 兜底旧数据; 覆盖: 空数据 / 有数据(charge+discharge统计) / 旧数据兜底
# ═══════════════════════════════════════════════
def test_v2g_empty():
    token = _login_as()
    resp = client.get("/api/v1/reports/v2g?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    data = _data(resp)
    assert data["device_count"] == 0
    assert data["energy"]["total_charge_kwh"] == 0
    assert data["dispatch"]["total_dispatches"] == 0
    assert data["efficiency"]["avg_charge_efficiency"] == 0.0
    assert data["device_details"] == []
    assert data["daily_trend"] == []
    assert data["revenue"]["estimated_revenue"] == 0


def test_v2g_export_csv_empty():
    """空数据 V2G csv 导出 — 覆盖 v2g format 分支"""
    token = _login_as()
    resp = client.get("/api/v1/reports/v2g?format=csv", headers=_hdr(token))
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "")
    assert "v2g.csv" in resp.headers.get("content-disposition", "")


# seed: V2G 运营数据 (1 V2G桩 + charge/discharge 调度日志)
def _seed_v2g_data(test_db):
    from app.models.user import Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.v2g_dispatch import V2GDispatchLog

    s = test_db["session"]
    now = datetime.now(timezone.utc)

    team = Team(name="V2G运维组", code="V2G001", description="V2G测试")
    s.add(team)
    s.flush()
    st = Station(name="V2G测试站", code="VSTA001", status=StationStatus.NORMAL, team_id=team.id)
    s.add(st)
    s.flush()
    dev = Device(sn="V2GD001", name="V2G桩#1", code="V2GD001",
                 type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE,
                 station_id=st.id, health_score=90.0, rated_power=50.0)
    s.add(dev)
    s.flush()

    base = now - timedelta(days=1)
    s.add_all([
        V2GDispatchLog(device_id=dev.id, dispatch_type="charge",
                       target_power_kw=10.0, actual_power_kw=9.5,
                       actual_energy_kwh=20.0, status="completed", start_at=base),
        V2GDispatchLog(device_id=dev.id, dispatch_type="charge",
                       target_power_kw=10.0, actual_power_kw=8.0,
                       actual_energy_kwh=10.0, status="completed", start_at=base),
        V2GDispatchLog(device_id=dev.id, dispatch_type="discharge",
                       target_power_kw=10.0, actual_power_kw=9.0,
                       actual_energy_kwh=15.0, status="failed", start_at=base),
    ])
    s.commit()
    return {"station": st, "device": dev}


def test_v2g_with_data(test_db):
    """有数据 V2G 报表 — charge/discharge 调度日志统计值正确 (修复前因 AttributeError 必崩)"""
    _seed_v2g_data(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/v2g?days=30", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    data = _data(resp)

    # 设备数
    assert data["device_count"] >= 1

    # 充放电量: 20 + 10 (charge) / 15 (discharge)
    assert data["energy"]["total_charge_kwh"] == 30.0
    assert data["energy"]["total_discharge_kwh"] == 15.0
    assert data["energy"]["net_energy_kwh"] == -15.0

    # 调度统计: 3 条, 2 completed, 1 failed
    disp = data["dispatch"]
    assert disp["total_dispatches"] == 3
    assert disp["completed_dispatches"] == 2
    assert disp["failed_dispatches"] == 1
    assert disp["success_rate"] == 66.7
    assert disp["grid_response_count"] == 3

    # 收益估算: 15*0.5 - 30*0.3 = -1.5
    assert data["revenue"]["estimated_revenue"] == -1.5
    assert data["revenue"]["discharge_revenue"] == 7.5
    assert data["revenue"]["charge_cost"] == 9.0

    # 效率日志缺失 → 均为 0
    eff = data["efficiency"]
    assert eff["avg_charge_efficiency"] == 0.0
    assert eff["avg_discharge_efficiency"] == 0.0

    # 设备详情
    details = data["device_details"]
    assert len(details) == 1
    d0 = details[0]
    assert d0["total_charge_kwh"] == 30.0
    assert d0["total_discharge_kwh"] == 15.0
    assert d0["dispatch_count"] == 3
    assert d0["dispatch_success_rate"] == 66.7
    assert d0["station_name"]  # 含站点名

    # 日趋势: 同一天聚合
    trend = data["daily_trend"]
    assert len(trend) == 1
    assert trend[0]["charge_kwh"] == 30.0
    assert trend[0]["discharge_kwh"] == 15.0
    assert trend[0]["dispatch_count"] == 3


def test_v2g_legacy_null_energy(test_db):
    """旧数据 actual_energy_kwh=None — getattr 兜底按 0, 端点不崩 (迁移前旧行兼容)"""
    from app.models.v2g_dispatch import V2GDispatchLog
    seeds = _seed_v2g_data(test_db)
    s = test_db["session"]
    # 追加一条 actual_energy_kwh 未赋值(None)的 charge log, 模拟迁移前旧数据
    s.add(V2GDispatchLog(
        device_id=seeds["device"].id, dispatch_type="charge",
        target_power_kw=10.0, actual_power_kw=5.0,
        status="completed", start_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    s.commit()
    token = _login_as()
    resp = client.get("/api/v1/reports/v2g?days=30", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    data = _data(resp)
    # None 行按 0 计, 不影响原有 30.0 charge / 15.0 discharge; 调度总数 +1
    assert data["energy"]["total_charge_kwh"] == 30.0
    assert data["energy"]["total_discharge_kwh"] == 15.0
    assert data["dispatch"]["total_dispatches"] == 4


# seed: 两 team V2G 隔离数据 (各1 V2G桩 + dispatch log + t1 engineer)
def _seed_v2g_team_scoped(test_db):
    from app.models.user import User, UserRole, EngineerLevel, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.v2g_dispatch import V2GDispatchLog

    s = test_db["session"]
    now = datetime.now(timezone.utc)

    t1 = Team(name="V2G甲队", code="V2A", description="A")
    t2 = Team(name="V2G乙队", code="V2B", description="B")
    s.add_all([t1, t2])
    s.flush()
    s1 = Station(name="V2G甲站", code="V2SA", status=StationStatus.NORMAL, team_id=t1.id)
    s2 = Station(name="V2G乙站", code="V2SB", status=StationStatus.NORMAL, team_id=t2.id)
    s.add_all([s1, s2])
    s.flush()
    d1 = Device(sn="V2A1", name="甲V2G桩", code="V2A1", type=DeviceType.V2G_CHARGER,
                status=DeviceStatus.ONLINE, station_id=s1.id, health_score=90.0)
    d2 = Device(sn="V2B1", name="乙V2G桩", code="V2B1", type=DeviceType.V2G_CHARGER,
                status=DeviceStatus.ONLINE, station_id=s2.id, health_score=80.0)
    s.add_all([d1, d2])
    s.flush()

    eng_a = User(
        username="v2g_eng",
        password_hash=_fast_hash("eng123"),
        real_name="V2G工程师", role=UserRole.ENGINEER, level=EngineerLevel.SENIOR,
        team_id=t1.id, status="active",
    )
    s.add(eng_a)
    s.flush()

    base = now - timedelta(days=1)
    s.add_all([
        V2GDispatchLog(device_id=d1.id, dispatch_type="charge",
                       target_power_kw=10.0, actual_power_kw=9.0,
                       actual_energy_kwh=12.0, status="completed", start_at=base),
        V2GDispatchLog(device_id=d2.id, dispatch_type="discharge",
                       target_power_kw=10.0, actual_power_kw=9.0,
                       actual_energy_kwh=8.0, status="completed", start_at=base),
    ])
    s.commit()
    return {"t1": t1, "s1": s1, "s2": s2, "d1": d1, "d2": d2}


def test_v2g_team_scoping(test_db):
    """非 admin V2G 仅本 team — 覆盖 own!=None station scoping 分支 (L649)"""
    _seed_v2g_team_scoped(test_db)
    token = _login_as("v2g_eng", "eng123")
    resp = client.get("/api/v1/reports/v2g?days=30", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    data = _data(resp)
    assert data["device_count"] == 1              # 仅甲队 V2G 桩
    assert data["energy"]["total_charge_kwh"] == 12.0   # 仅甲队 charge log
    assert data["energy"]["total_discharge_kwh"] == 0   # 乙队 discharge 不可见
    assert data["dispatch"]["total_dispatches"] == 1


def test_v2g_station_id_filter(test_db):
    """station_id 过滤 — admin 限定本站 (L651)"""
    seeds = _seed_v2g_data(test_db)
    token = _login_as()
    resp = client.get(f"/api/v1/reports/v2g?station_id={seeds['station'].id}", headers=_hdr(token))
    assert resp.status_code == 200, resp.text
    data = _data(resp)
    assert data["device_count"] >= 1
    assert data["energy"]["total_charge_kwh"] == 30.0


def test_v2g_with_data_export_csv(test_db):
    """有数据 V2G csv 导出 — 覆盖 device_details 导出循环 (L742)"""
    _seed_v2g_data(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/v2g?format=csv", headers=_hdr(token))
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "")
    assert "v2g.csv" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 0


# ═══════════════════════════════════════════════
# PDF 导出 _generate_pdf (903-984)
# ═══════════════════════════════════════════════
def test_pdf_summary():
    """summary PDF — summary 必有 data(全局指标行)"""
    token = _login_as()
    resp = client.get("/api/v1/reports/summary?format=pdf", headers=_hdr(token))
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "") == "application/pdf"
    assert "summary.pdf" in resp.headers.get("content-disposition", "")


def test_pdf_no_data_branch():
    """空告警 PDF — data=[] 触发 _generate_pdf 的「没有数据可导出」else 分支"""
    token = _login_as()
    resp = client.get("/api/v1/reports/alarms?format=pdf", headers=_hdr(token))
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "") == "application/pdf"


def test_pdf_workorders():
    token = _login_as()
    resp = client.get("/api/v1/reports/workorders?format=pdf", headers=_hdr(token))
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "") == "application/pdf"


def test_pdf_devices():
    token = _login_as()
    resp = client.get("/api/v1/reports/devices?format=pdf", headers=_hdr(token))
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "") == "application/pdf"


# ═══════════════════════════════════════════════
# team scoping (非 admin 隔离) — 45/52/74-76/99/190/192/215-216/287/289/314/410/412/790
# ═══════════════════════════════════════════════
def test_summary_team_scoping(test_db):
    """非 admin summary 仅本 team 资源"""
    _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get("/api/v1/reports/summary?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    data = _data(resp)
    ov = data["overview"]
    assert ov["total_stations"] == 1   # 仅甲站
    assert ov["total_devices"] == 1    # 仅甲设备
    assert ov["total_workorders"] == 1
    assert ov["total_alarms"] == 1     # 仅甲告警
    # team_performance 仅本 team 工程师
    assert data["team_performance"]["total_engineers"] == 1


def test_devices_team_scoping(test_db):
    """非 admin devices 仅本 team"""
    _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get("/api/v1/reports/devices", headers=_hdr(token))
    assert resp.status_code == 200
    data = _data(resp)
    assert data["total_devices"] == 1
    assert len(data["station_distribution"]) == 1


def test_devices_cross_station_404(test_db):
    """非 admin 传他队 station_id → 404 (不泄露存在)"""
    seeds = _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get(f"/api/v1/reports/devices?station_id={seeds['s2'].id}", headers=_hdr(token))
    assert resp.status_code == 404


def test_devices_own_station_ok(test_db):
    """非 admin 传本队 station_id → 正常"""
    seeds = _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get(f"/api/v1/reports/devices?station_id={seeds['s1'].id}", headers=_hdr(token))
    assert resp.status_code == 200
    assert _data(resp)["total_devices"] == 1


def test_workorders_team_scoping(test_db):
    _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get("/api/v1/reports/workorders?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    data = _data(resp)
    assert data["total_workorders"] == 1
    # engineer_stats 仅本 team 工程师
    assert len(data["engineer_performance"]) == 1


def test_alarms_team_scoping(test_db):
    _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get("/api/v1/reports/alarms?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    assert _data(resp)["total_alarms"] == 1


def test_faults_team_scoping(test_db):
    _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get("/api/v1/reports/faults?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    # 甲告警 warning + 乙告警 critical；eng_a 仅见甲(warning)
    data = _data(resp)
    assert data["total_faults"] == 1


def test_faults_cross_station_404(test_db):
    seeds = _seed_team_scoped(test_db)
    token = _login_as("eng_a", "eng123")
    resp = client.get(f"/api/v1/reports/faults?station_id={seeds['s2'].id}", headers=_hdr(token))
    assert resp.status_code == 404


def test_workorders_station_id_admin(test_db):
    """admin 传 station_id 过滤 (覆盖 workorders station_id 分支)"""
    seeds = _seed_team_scoped(test_db)
    token = _login_as()
    resp = client.get(f"/api/v1/reports/workorders?station_id={seeds['s1'].id}", headers=_hdr(token))
    assert resp.status_code == 200
    assert _data(resp)["total_workorders"] == 1


def test_alarms_station_id_admin(test_db):
    """admin 传 station_id 过滤 (覆盖 alarms station_id 分支)"""
    seeds = _seed_team_scoped(test_db)
    token = _login_as()
    resp = client.get(f"/api/v1/reports/alarms?station_id={seeds['s1'].id}", headers=_hdr(token))
    assert resp.status_code == 200
    assert _data(resp)["total_alarms"] == 1


# ═══════════════════════════════════════════════
# 站点健康分布边界 + health fair 桶 (112/114/236)
# ═══════════════════════════════════════════════
def test_summary_station_health_dist(test_db):
    """summary 站点健康分布: offline/critical/normal 三分支"""
    _seed_station_health(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/summary?days=30", headers=_hdr(token))
    assert resp.status_code == 200
    dist = _data(resp)["station_health"]["distribution"]
    assert dist["offline"] >= 1   # 空设备站点
    assert dist["critical"] >= 1  # 多数离线站点
    assert dist["normal"] >= 1    # 正常站点


def test_devices_health_fair_bucket(test_db):
    """devices health 分桶 fair (50<=hs<70)"""
    _seed_station_health(test_db)
    token = _login_as()
    resp = client.get("/api/v1/reports/devices", headers=_hdr(token))
    assert resp.status_code == 200
    dist = _data(resp)["health_score"]["distribution"]
    assert dist["fair"] >= 1   # health=60 设备
    assert dist["poor"] >= 1   # health=10 设备 (严重站点)
    assert dist["excellent"] >= 1
