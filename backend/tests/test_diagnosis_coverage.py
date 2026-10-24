"""
diagnosis.py 覆盖率补充测试（67% → ≥70%）。

补 app/api/v1/diagnosis.py 未覆盖分支：
- diagnose_device: FAULT/OFFLINE 状态分支、critical/warning 规则、活跃告警分析、
  超期维护建议、预测故障、critical 成本档
- diagnose_batch: device_type / min_health_score 过滤、top_issues 收集、
  非 admin 的 station team 校验与 team join 过滤
- get_health_trend: 趋势记录迭代与摘要计算
- station_diagnosis_summary: 类型健康聚合、活跃告警/待处理工单统计、risk_devices

既有 tests/test_diagnosis.py 等四个文件覆盖鉴权拒绝与基础 happy path（ONLINE 无记录
设备），本文件专攻剩余条件分支。源码零改动；若发现源码 bug 在交付报告中详述，不自行修。
"""
from datetime import date, datetime, timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """复用 test_db：覆盖 SessionLocal + 种子 admin，使 module-level client 指向测试库。"""
    pass


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _make_device(db, station_id, *, sn, name, code, dtype, status,
                 health_score=None, last_maintenance=None):
    from app.models.device import Device
    d = Device(
        sn=sn, name=name, code=code, type=dtype, status=status,
        station_id=station_id, health_score=health_score,
        last_maintenance=last_maintenance,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@pytest.fixture
def station(test_db):
    from app.models.station import Station, StationStatus
    db = test_db["session"]
    s = Station(name="覆盖率测试站", code="COV-ST-001", status=StationStatus.NORMAL)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ────────────────────────── diagnose_device ──────────────────────────

def test_diagnose_device_critical_fault(auth_token, station, test_db):
    """FAULT 设备 + 低分健康记录 + 活跃严重告警 + 超期未维护 → critical 全链路。

    覆盖：L223-229(FAULT 分析项) / L254-261(critical 规则) / L278-287(活跃告警+critical 升级)
         / L292-298(维修建议) / L302-304(超期维护) / L317-321(预测故障) / L326(critical 成本档)。
    """
    from app.models.device import (
        DeviceType, DeviceStatus, DeviceHealthRecord,
    )
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus
    db = test_db["session"]

    device = _make_device(
        db, station.id, sn="COV-DEV-FAULT", name="故障电池柜", code="COVFLT",
        dtype=DeviceType.BATTERY, status=DeviceStatus.FAULT, health_score=40.0,
        last_maintenance=date.today() - timedelta(days=60),
    )
    # 电气安全 50(<60 触发 critical 规则)，其余维度高分不触发
    db.add(DeviceHealthRecord(
        device_id=device.id, electrical_safe_score=50, thermal_score=90,
        comm_score=90, power_quality_score=90, mechanical_score=90, total_score=50.0,
    ))
    # 活跃严重告警（驱动 alarm_stats + risk critical）
    db.add(Alarm(device_id=device.id, station_id=station.id, alarm_type="electrical",
                 level=AlarmLevel.CRITICAL, content="电气故障", status=AlarmStatus.ACTIVE))
    # 已解决告警（计入 total 不计入 active）
    db.add(Alarm(device_id=device.id, station_id=station.id, alarm_type="noise",
                 level=AlarmLevel.WARNING, content="历史告警", status=AlarmStatus.RESOLVED))
    # 工单：1 pending + 1 completed
    db.add(WorkOrder(id="WO-COV-1", device_id=device.id, station_id=station.id,
                     type=WorkOrderType.REPAIR, status=WorkOrderStatus.PENDING))
    db.add(WorkOrder(id="WO-COV-2", device_id=device.id, station_id=station.id,
                     type=WorkOrderType.REPAIR, status=WorkOrderStatus.COMPLETED))
    db.commit()

    resp = client.post("/api/v1/diagnosis/device", headers=_hdr(auth_token),
                       json={"device_id": device.id, "include_history": True})
    assert resp.status_code == 200
    d = resp.json()["data"]

    # 风险与整体健康度
    assert d["risk_level"] == "critical"
    assert d["overall_health"] == 40.0

    # FAULT 状态分析项
    status_items = [a for a in d["analysis"] if a.get("category") == "设备状态"]
    assert status_items and status_items[0]["issue"] == "设备处于故障状态"
    assert status_items[0]["severity"] == "critical"

    # 电气 critical 规则：condition 串不参与判定，只看 score<60，故 2 条 critical 规则全触发
    elec = [a for a in d["analysis"] if a.get("category") == "electrical"]
    assert len(elec) == 2
    assert all(e["severity"] == "critical" and e["score"] == 50 for e in elec)

    # 活跃严重告警分析项
    alarm_items = [a for a in d["analysis"] if a.get("category") == "告警"]
    assert alarm_items and alarm_items[0]["severity"] == "high"
    assert alarm_items[0]["count"] == 1 and alarm_items[0]["critical_count"] == 1

    # 预测故障：health_score<60 → 概率"高"；battery 共 4 类问题
    assert len(d["predicted_failures"]) == 4
    assert all(p["probability"] == "高" for p in d["predicted_failures"])

    # 超期维护建议存在
    assert any(r["category"] == "预防性维护" for r in d["recommendations"])
    # 维修建议 = 2 条电气 critical(带 action) + 1 条预防性维护
    assert len(d["recommendations"]) == 3

    # critical 成本档 = battery.major(50000) ~ major*2(100000)
    assert d["estimated_cost"] == {"min": 50000, "max": 100000}

    # 工单 / 告警统计强校验
    assert d["workorder_stats"] == {"total": 2, "pending": 1, "completed": 1}
    assert d["alarm_stats"] == {"total": 2, "active": 1, "critical": 1}


def test_diagnose_device_warning_medium(auth_token, station, test_db):
    """ONLINE + 各维度 70 分(60<=x<80) → warning 规则触发、风险升 medium、预测概率"中"。

    覆盖：L266-272(warning 规则) / L273-274(risk != critical → medium) / L317-321(预测)。
    """
    from app.models.device import DeviceType, DeviceStatus, DeviceHealthRecord
    db = test_db["session"]

    device = _make_device(
        db, station.id, sn="COV-DEV-WARN", name="亚健康逆变器", code="COVWRN",
        dtype=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, health_score=75.0,
    )
    db.add(DeviceHealthRecord(
        device_id=device.id, electrical_safe_score=70, thermal_score=70,
        comm_score=70, power_quality_score=70, mechanical_score=70, total_score=70.0,
    ))
    db.commit()

    resp = client.post("/api/v1/diagnosis/device", headers=_hdr(auth_token),
                       json={"device_id": device.id})
    assert resp.status_code == 200
    d = resp.json()["data"]

    assert d["risk_level"] == "medium"
    warnings = [a for a in d["analysis"] if a.get("severity") == "warning"]
    # electrical 有 2 条 warning 规则、其余维度各 1 条 → 共 6 条（condition 串不参与判定）
    assert len(warnings) == 6
    assert {a["category"] for a in warnings} == {
        "electrical", "thermal", "communication", "power_quality", "mechanical",
    }
    # 每条 warning 都带 action → 6 条维修建议，severity warning → priority medium
    assert len(d["recommendations"]) == 6
    assert all(r["priority"] == "medium" for r in d["recommendations"])
    # 预测故障：60<=health_score<80 → 概率"中"；pv_inverter 4 类问题
    assert len(d["predicted_failures"]) == 4
    assert all(p["probability"] == "中" for p in d["predicted_failures"])
    # medium 风险 → 成本 pv_inverter.minor(800) ~ medium(5000)
    assert d["estimated_cost"] == {"min": 800, "max": 5000}


def test_diagnose_device_offline_risk_escalation(auth_token, station, test_db):
    """OFFLINE 设备 → 离线分析项(severity=high)；风险按等级映射升级到 high。

    覆盖：L231-237(OFFLINE 分析项 + risk 等级升级) / L327-328(high 成本档)。
    """
    from app.models.device import DeviceType, DeviceStatus
    db = test_db["session"]

    device = _make_device(
        db, station.id, sn="COV-DEV-OFF", name="离线电表", code="COVOFF",
        dtype=DeviceType.METER, status=DeviceStatus.OFFLINE, health_score=90.0,
    )
    resp = client.post("/api/v1/diagnosis/device", headers=_hdr(auth_token),
                       json={"device_id": device.id})
    assert resp.status_code == 200
    d = resp.json()["data"]

    offline = [a for a in d["analysis"] if a.get("issue") == "设备离线"]
    assert offline and offline[0]["severity"] == "high"
    # OFFLINE 应升级到 high（等级映射比较，不再走字符串 max）
    assert d["risk_level"] == "high"
    # high → meter.medium(800) ~ major(2000)
    assert d["estimated_cost"] == {"min": 800, "max": 2000}


def test_diagnose_device_not_found(auth_token):
    """不存在设备 → 404。

    assert_device_team_access(L186) 对任意用户在设备不存在时即抛 404，
    先于 L188-190 的本地查询，故 L190 为不可达死代码（见交付报告）。
    """
    resp = client.post("/api/v1/diagnosis/device", headers=_hdr(auth_token),
                       json={"device_id": 999999})
    assert resp.status_code == 404


# ────────────────────────── get_health_trend ──────────────────────────

def test_health_trend_with_records(auth_token, station, test_db):
    """多记录趋势：覆盖 L457-489（assert / 查询 / 记录迭代 / 摘要计算）。"""
    from app.models.device import DeviceType, DeviceStatus, DeviceHealthRecord
    db = test_db["session"]

    device = _make_device(
        db, station.id, sn="COV-DEV-TREND", name="趋势设备", code="COVTR",
        dtype=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, health_score=60.0,
    )
    now = datetime.now()
    for i, total in enumerate([50.0, 55.0, 60.0]):
        db.add(DeviceHealthRecord(
            device_id=device.id, electrical_safe_score=80, thermal_score=80,
            comm_score=80, power_quality_score=80, mechanical_score=80,
            total_score=total, created_at=now - timedelta(days=2 - i),
        ))
    db.commit()

    resp = client.get(f"/api/v1/diagnosis/health-trend/{device.id}?days=30",
                      headers=_hdr(auth_token))
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["device_id"] == device.id
    assert d["device_name"] == "趋势设备"
    # 按 created_at 升序返回
    assert [t["total_score"] for t in d["trend_data"]] == [50.0, 55.0, 60.0]
    assert d["summary"]["start_score"] == 50.0
    assert d["summary"]["end_score"] == 60.0
    assert d["summary"]["change"] == 10.0


def test_health_trend_not_found(auth_token):
    """不存在设备 → 404（assert_device_team_access L457 先抛）。"""
    resp = client.get("/api/v1/diagnosis/health-trend/999999", headers=_hdr(auth_token))
    assert resp.status_code == 404


# ────────────────────────── diagnose_batch (admin) ──────────────────────────

@pytest.fixture
def batch_devices(test_db):
    """构造多类型/多健康度/带告警设备，供 batch 过滤与 top_issues 测试。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    db = test_db["session"]

    st = Station(name="批量站", code="COV-BATCH-ST", status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)

    d_bat = Device(sn="BAT-LOW", name="低分电池", code="BL1", type=DeviceType.BATTERY,
                   status=DeviceStatus.FAULT, station_id=st.id, health_score=40.0)
    d_pv = Device(sn="PV-HI", name="健康逆变", code="PH1", type=DeviceType.PV_INVERTER,
                  status=DeviceStatus.ONLINE, station_id=st.id, health_score=90.0)
    d_met = Device(sn="MET-LOW", name="低分电表", code="ML1", type=DeviceType.METER,
                   status=DeviceStatus.ONLINE, station_id=st.id, health_score=30.0)
    d_low = Device(sn="PV-MID", name="中分逆变", code="PM1", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=st.id, health_score=50.0)
    db.add_all([d_bat, d_pv, d_met, d_low])
    db.commit()
    for d in (d_bat, d_pv, d_met, d_low):
        db.refresh(d)

    # 仅 d_bat / d_met 各挂一条活跃告警（d_low 健康度<80 但无活跃告警）
    db.add(Alarm(device_id=d_bat.id, station_id=st.id, alarm_type="b",
                 level=AlarmLevel.CRITICAL, content="电池告警", status=AlarmStatus.ACTIVE))
    db.add(Alarm(device_id=d_met.id, station_id=st.id, alarm_type="m",
                 level=AlarmLevel.WARNING, content="电表告警", status=AlarmStatus.ACTIVE))
    db.commit()
    return {"station": st, "bat": d_bat, "pv": d_pv, "met": d_met, "low": d_low}


def test_batch_filter_device_type(auth_token, batch_devices):
    """device_type 过滤 → 仅返回该类型设备。覆盖 L394。"""
    resp = client.post("/api/v1/diagnosis/batch", headers=_hdr(auth_token),
                       json={"device_type": "battery"})
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["total_devices"] == 1
    assert d["critical_devices"] == 1  # health_score 40 < 50


def test_batch_filter_min_health_score(auth_token, batch_devices):
    """min_health_score 过滤 → health_score <= 阈值的设备。覆盖 L395-396。"""
    resp = client.post("/api/v1/diagnosis/batch", headers=_hdr(auth_token),
                       json={"min_health_score": 50})
    assert resp.status_code == 200
    d = resp.json()["data"]
    # bat(40) / met(30) / low(50) 命中；pv(90) 排除
    assert d["total_devices"] == 3
    assert d["healthy_devices"] == 0


def test_batch_top_issues(auth_token, batch_devices):
    """top_issues 收集 health_score<80 且有活跃告警的设备，按健康度升序。覆盖 L415-426。"""
    resp = client.post("/api/v1/diagnosis/batch", headers=_hdr(auth_token), json={})
    assert resp.status_code == 200
    d = resp.json()["data"]
    # 总数 4，健康度分布：healthy(>=90)=1, warning(70-90)=0, fault(50-70)=1(low=50), critical(<50)=2(bat,met)
    assert d["total_devices"] == 4
    assert d["healthy_devices"] == 1
    assert d["fault_devices"] == 1
    assert d["critical_devices"] == 2
    # top_issues：bat 与 met（low 无活跃告警被跳过），按 health_score 升序 → met(30) 在前
    names = [t["device_name"] for t in d["top_issues"]]
    assert names == ["低分电表", "低分电池"]
    assert d["top_issues"][0]["alarm_count"] == 1
    assert d["top_issues"][0]["status"] == "online"


# ────────────────────────── diagnose_batch (非 admin team scoping) ──────────────────────────

@pytest.fixture
def team_scenario(test_db):
    """两 team + 各一站点/设备 + team A engineer，验证非 admin 的 team 过滤。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    db = test_db["session"]

    ta = Team(name="COV团队A", code="CTA1")
    tb = Team(name="COV团队B", code="CTB1")
    db.add_all([ta, tb])
    db.commit()
    db.refresh(ta)
    db.refresh(tb)

    pwd = "cov123456"
    eng = User(
        username="cov_eng", real_name="A工程师", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    db.add(eng)
    db.commit()

    sa = Station(name="A站", code="COVSA", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="B站", code="COVSB", team_id=tb.id, status=StationStatus.NORMAL)
    db.add_all([sa, sb])
    db.commit()
    db.refresh(sa)
    db.refresh(sb)

    da = Device(sn="COV-DA", name="A设备", code="CDA1", type=DeviceType.PV_INVERTER,
                status=DeviceStatus.ONLINE, station_id=sa.id, health_score=60.0)
    da2 = Device(sn="COV-DA2", name="A设备2", code="CDA2", type=DeviceType.PV_INVERTER,
                 status=DeviceStatus.ONLINE, station_id=sa.id, health_score=70.0)
    db_ = Device(sn="COV-DB", name="B设备", code="CDB1", type=DeviceType.PV_INVERTER,
                 status=DeviceStatus.ONLINE, station_id=sb.id, health_score=80.0)
    db.add_all([da, da2, db_])
    db.commit()

    r = client.post("/api/v1/auth/login", data={"username": "cov_eng", "password": pwd})
    assert r.status_code == 200
    token = r.json().get("data", {}).get("token") or r.json().get("token")

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sa, "b": sb},
        "token": token,
    }


def test_batch_team_join_filters_other_team(auth_token, team_scenario):
    """非 admin 无 station_id → team join 过滤，仅见本 team 设备。覆盖 L397-400。"""
    t = team_scenario
    resp = client.post("/api/v1/diagnosis/batch", headers=_hdr(t["token"]), json={})
    assert resp.status_code == 200
    d = resp.json()["data"]
    # team A 有 2 台，B 的设备被过滤掉
    assert d["total_devices"] == 2


def test_batch_own_station_team_access(auth_token, team_scenario):
    """非 admin 传本 team station_id → assert_station_team_access 放行。覆盖 L385-387。"""
    t = team_scenario
    resp = client.post("/api/v1/diagnosis/batch", headers=_hdr(t["token"]),
                       json={"station_id": t["stations"]["a"].id})
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["total_devices"] == 2


def test_batch_other_station_denied(auth_token, team_scenario):
    """非 admin 传别 team station_id → assert_station_team_access 抛 404。覆盖 L386-387 拒绝路径。"""
    t = team_scenario
    resp = client.post("/api/v1/diagnosis/batch", headers=_hdr(t["token"]),
                       json={"station_id": t["stations"]["b"].id})
    assert resp.status_code == 404


# ────────────────────────── station_diagnosis_summary ──────────────────────────

def test_station_summary(auth_token, test_db):
    """站点摘要：类型健康聚合 / 活跃告警 / 待处理工单 / risk_devices。覆盖 L503-547。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus
    db = test_db["session"]

    st = Station(name="摘要站", code="COV-SUM-ST", status=StationStatus.NORMAL)
    db.add(st)
    db.commit()
    db.refresh(st)

    d1 = Device(sn="SUM-D1", name="逆变器A", code="SI1", type=DeviceType.PV_INVERTER,
                status=DeviceStatus.ONLINE, station_id=st.id, health_score=95.0)
    d2 = Device(sn="SUM-D2", name="电池B", code="SB1", type=DeviceType.BATTERY,
                status=DeviceStatus.FAULT, station_id=st.id, health_score=45.0)
    d3 = Device(sn="SUM-D3", name="电表C", code="SM1", type=DeviceType.METER,
                status=DeviceStatus.ONLINE, station_id=st.id, health_score=85.0)
    d4 = Device(sn="SUM-D4", name="逆变器D", code="SI2", type=DeviceType.PV_INVERTER,
                status=DeviceStatus.ONLINE, station_id=st.id, health_score=85.0)
    db.add_all([d1, d2, d3, d4])
    db.commit()
    for d in (d1, d2, d3, d4):
        db.refresh(d)

    # 站点活跃告警 1（CRITICAL）+ 已解决告警 1（不计入 active）
    db.add(Alarm(device_id=d2.id, station_id=st.id, alarm_type="bat",
                 level=AlarmLevel.CRITICAL, content="电池告警", status=AlarmStatus.ACTIVE))
    db.add(Alarm(device_id=d1.id, station_id=st.id, alarm_type="n",
                 level=AlarmLevel.WARNING, content="历史", status=AlarmStatus.RESOLVED))
    # 站点工单：1 pending + 1 completed（completed 不计入 pending）
    db.add(WorkOrder(id="WO-SUM-1", station_id=st.id, type=WorkOrderType.REPAIR,
                     status=WorkOrderStatus.PENDING))
    db.add(WorkOrder(id="WO-SUM-2", station_id=st.id, type=WorkOrderType.REPAIR,
                     status=WorkOrderStatus.COMPLETED))
    db.commit()

    resp = client.get(f"/api/v1/diagnosis/station-summary/{st.id}",
                      headers=_hdr(auth_token))
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["station_id"] == st.id
    assert d["station_name"] == "摘要站"
    assert d["total_devices"] == 4

    th = d["type_health"]
    # 逆变器聚合：(95+85)/2 = 90.0
    assert th["pv_inverter"]["total"] == 2
    assert th["pv_inverter"]["avg_health"] == 90.0
    assert th["battery"]["total"] == 1 and th["battery"]["avg_health"] == 45.0
    assert th["meter"]["total"] == 1 and th["meter"]["avg_health"] == 85.0

    assert d["active_alarms"] == 1
    assert d["pending_workorders"] == 1
    # overall_health = (95+45+85+85)/4 = 77.5
    assert d["overall_health"] == 77.5
    # risk_devices：health_score<80 → 仅电池(45)；投影为 {id,name,health_score,status} 精简字段
    assert len(d["risk_devices"]) == 1
    assert d["risk_devices"][0]["name"] == "电池B"
    assert d["risk_devices"][0]["health_score"] == 45.0
