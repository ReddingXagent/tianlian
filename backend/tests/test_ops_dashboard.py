#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运维大屏 API 测试
覆盖: /topology, /event-stream, /health-scores, /overview
"""
import bcrypt
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，并暴露其 session 供数据插入 helper 使用。

    本文件用 module-level `client = TestClient(app.main.app)`（不经 conftest 的
    client fixture，故无 _sesh），改为通过 test_db["session"] 写入测试数据。
    端点经 get_db() 读模块级 SessionLocal，已被 test_db override 指向同一测试库。
    """
    _setup_test_db.session = test_db["session"]


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ========== 数据插入 helper（共享 test_db 的同一 session）==========

def _add_station(s, **kw):
    from app.models.station import Station, StationStatus
    defaults = dict(name="测试电站", code="STA-T", status=StationStatus.NORMAL, health_score=90.0)
    defaults.update(kw)
    sta = Station(**defaults)
    s.add(sta)
    s.commit()
    s.refresh(sta)
    return sta


def _add_gateway(s, station_id, **kw):
    from app.models.gateway import Gateway
    defaults = dict(name="测试网关", sn="GW-T", status="online")
    defaults.update(kw)
    defaults["station_id"] = station_id
    gw = Gateway(**defaults)
    s.add(gw)
    s.commit()
    s.refresh(gw)
    return gw


def _add_device(s, station_id, **kw):
    from app.models.device import Device, DeviceType, DeviceStatus
    defaults = dict(
        name="测试设备", sn="DEV-T", type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE, health_score=90.0,
    )
    defaults.update(kw)
    defaults["station_id"] = station_id
    dev = Device(**defaults)
    s.add(dev)
    s.commit()
    s.refresh(dev)
    return dev


# ========== 鉴权检查 ==========

def test_topology_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/ops-dashboard/topology")
    assert resp.status_code == 401


def test_overview_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/ops-dashboard/overview")
    assert resp.status_code == 401


def test_health_scores_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/ops-dashboard/health-scores")
    assert resp.status_code == 401


def test_event_stream_requires_auth():
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/ops-dashboard/event-stream")
    assert resp.status_code == 401


# ========== Topology 拓扑测试 ==========

def test_topology_empty():
    """空数据库拓扑"""
    token = _login()
    resp = client.get("/api/v1/ops-dashboard/topology", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "summary" in data
    assert data["summary"]["total_stations"] == 0
    assert data["summary"]["total_devices"] == 0


# ========== Overview 概览测试 ==========

def test_overview_empty():
    """空数据库概览"""
    token = _login()
    resp = client.get("/api/v1/ops-dashboard/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert "alarms" in data
    assert "workorders" in data
    assert "healing" in data
    assert "timestamp" in data
    # 空数据库各项为0
    assert data["stats"]["stations"] == 0
    assert data["stats"]["devices"] == 0
    assert data["stats"]["online_rate"] == 0
    assert data["alarms"]["active"] == 0
    assert data["workorders"]["pending"] == 0


# ========== Health Scores 健康度测试 ==========

def test_health_scores_empty():
    """空数据库健康度"""
    token = _login()
    resp = client.get("/api/v1/ops-dashboard/health-scores", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_score" in data
    assert "stations" in data
    assert "distribution" in data
    assert len(data["stations"]) == 0


# ========== Event Stream 事件流测试 ==========

def test_event_stream_empty():
    """空数据库事件流"""
    token = _login()
    resp = client.get("/api/v1/ops-dashboard/event-stream", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert data["total"] == 0


def test_event_stream_with_limit():
    """指定limit"""
    token = _login()
    resp = client.get("/api/v1/ops-dashboard/event-stream?limit=10", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


def test_event_stream_with_station():
    """按站点筛选"""
    token = _login()
    resp = client.get(
        "/api/v1/ops-dashboard/event-stream?station_id=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data


# ========== Topology 带数据测试 ==========

def test_topology_with_data():
    """插入 Station+Gateway+Device，验证 nodes 结构、edges 连接、summary 统计"""
    from app.models.device import DeviceStatus
    token = _login()
    s = _setup_test_db.session

    sta = _add_station(s, name="拓扑站A", code="TOPO-A")
    # 网关：挂在站点下
    gw = _add_gateway(s, station_id=sta.id, sn="GW-TOPO-1", name="网关1", status="online")
    # 设备1：挂在网关下 → 产生 gateway-device 边
    dev_gw = _add_device(
        s, station_id=sta.id, sn="DEV-TOPO-1", name="挂网关设备",
        status=DeviceStatus.ONLINE, gateway_id=gw.id, health_score=95.0,
    )
    # 设备2：无网关（gateway_id=None）→ 产生 station-device 边
    dev_fault = _add_device(
        s, station_id=sta.id, sn="DEV-TOPO-2", name="直挂站点设备",
        status=DeviceStatus.FAULT, gateway_id=None, health_score=40.0,
    )

    resp = client.get("/api/v1/ops-dashboard/topology", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()

    nodes = data["nodes"]
    # —— nodes 结构正确 ——
    assert len(nodes["stations"]) == 1
    assert len(nodes["gateways"]) == 1
    assert len(nodes["devices"]) == 2

    # 站点节点字段
    sta_node = nodes["stations"][0]
    assert sta_node["id"] == f"station-{sta.id}"
    assert sta_node["type"] == "station"
    assert sta_node["name"] == "拓扑站A"
    assert sta_node["device_count"] == 2      # 两台设备
    assert sta_node["gateway_count"] == 1
    assert sta_node["online_count"] == 1      # DEV-TOPO-1 online
    assert sta_node["fault_count"] == 1       # DEV-TOPO-2 fault
    # 故障设备数 <=2 → status=warning
    assert sta_node["status"] == "warning"

    # 网关节点字段
    gw_node = nodes["gateways"][0]
    assert gw_node["id"] == f"gateway-{gw.id}"
    assert gw_node["type"] == "gateway"
    assert gw_node["device_count"] == 1       # 仅 dev_gw 挂此网关
    assert gw_node["online_count"] == 1

    # 设备节点字段
    dev_ids = {d["id"]: d for d in nodes["devices"]}
    assert dev_ids[f"device-{dev_gw.id}"]["gateway_id"] == gw.id
    assert dev_ids[f"device-{dev_fault.id}"]["gateway_id"] is None

    # —— edges 连接关系 ——
    edge_set = {(e["source"], e["target"], e["type"]) for e in data["edges"]}
    # station-gateway
    assert (f"station-{sta.id}", f"gateway-{gw.id}", "station-gateway") in edge_set
    # gateway-device（挂网关的设备）
    assert (f"gateway-{gw.id}", f"device-{dev_gw.id}", "gateway-device") in edge_set
    # station-device（无网关的设备）
    assert (f"station-{sta.id}", f"device-{dev_fault.id}", "station-device") in edge_set
    # 总边数 = 1(站→网关) + 1(网关→设备) + 1(站→设备) = 3
    assert len(data["edges"]) == 3

    # —— summary 统计 ——
    assert data["summary"]["total_stations"] == 1
    assert data["summary"]["total_gateways"] == 1
    assert data["summary"]["total_devices"] == 2
    assert data["summary"]["online_devices"] == 1
    assert data["summary"]["fault_devices"] == 1


# ========== Health Scores 带数据测试 ==========

def test_health_scores_with_data():
    """插入带不同 status 的设备，验证 composite_score、distribution、status 判定"""
    from app.models.device import DeviceStatus
    token = _login()
    s = _setup_test_db.session

    # 站点1：2台 online(health 100) → 高分(走 excellent/normal)
    # 站点2：1台 online(health 60) + 1台 fault(health 30) → 中低分(走 warning/fault)
    sta1 = _add_station(s, name="健康站", code="HS-A")
    _add_device(s, station_id=sta1.id, sn="H-D1", status=DeviceStatus.ONLINE, health_score=100.0)
    _add_device(s, station_id=sta1.id, sn="H-D2", status=DeviceStatus.ONLINE, health_score=100.0)

    sta2 = _add_station(s, name="故障站", code="HS-B")
    _add_device(s, station_id=sta2.id, sn="H-D3", status=DeviceStatus.ONLINE, health_score=60.0)
    _add_device(s, station_id=sta2.id, sn="H-D4", status=DeviceStatus.FAULT, health_score=30.0)

    resp = client.get("/api/v1/ops-dashboard/health-scores", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_stations"] == 2
    assert data["total_devices"] == 4
    assert data["total_online"] == 3      # H-D1,H-D2,H-D3 online
    assert data["total_fault"] == 1       # H-D4 fault

    stations = {st["station_id"]: st for st in data["stations"]}

    # —— 站点1 复合分：avg_health=100, online_rate=100, fault=0 → fault_penalty=0
    #   composite = 100*0.6 + 100*0.3 - 0*0.1 + 10 = 100 (clamp 上限)
    s1 = stations[sta1.id]
    assert s1["device_health_avg"] == 100.0
    assert s1["online_rate"] == 100.0
    assert s1["health_score"] == 100.0
    assert s1["status"] == "normal"       # >=80 normal

    # —— 站点2 复合分：avg_health=(60+30)/2=45, online_rate=1/2*100=50, fault=1 → penalty=5
    #   composite = 45*0.6 + 50*0.3 - 5*0.1 + 10 = 27 + 15 - 0.5 + 10 = 51.5 → <60 fault
    s2 = stations[sta2.id]
    assert s2["device_health_avg"] == 45.0
    assert s2["online_rate"] == 50.0
    assert s2["health_score"] == 51.5
    assert s2["status"] == "fault"        # <60 fault

    # —— overall_score = 两站复合分均值 ≈ (100 + 51.5)/2 = 75.75
    # 注：源码 total_health 累加未 round 的 composite（浮点尾差，如 0.3*50=15.000...2），
    # 故 overall 经 round 后可能与手算差 0.05，用 approx 容差。
    assert data["overall_score"] == pytest.approx(75.75, abs=0.1)

    # —— distribution 分布 ——
    dist = data["distribution"]
    assert dist["excellent"] == 1         # 站1 health=100 >=90
    assert dist["good"] == 0              # 无 80-89
    assert dist["warning"] == 0           # 无 60-79
    assert dist["fault"] == 1             # 站2 health=51.5 <60


def test_health_scores_status_thresholds():
    """status 判定边界：>=80 normal, >=60 warning, <60 fault（含边界值）"""
    from app.models.device import DeviceStatus
    token = _login()
    s = _setup_test_db.session

    # 精确构造三档 health_score，使 composite 落在 80/60 边界附近
    # composite = avg*0.6 + online_rate*0.3 - penalty*0.1 + 10
    # 单台 online、无 fault：online_rate=100, penalty=0 → composite = avg*0.6 + 30 + 10 = avg*0.6 + 40
    #   normal(>=80):  avg=100 → composite=100
    #   warning(60-79): avg=70 → composite=82... 落 normal 区，需更小。avg=66.67→80 边界
    # 用 avg 让 composite 分别落入三档：
    #   avg=100 → 100.0  (normal)
    #   avg=70  → 82.0   → 仍 normal，故 warning 取 avg=60 → 76.0
    #   avg=40  → 64.0   → warning
    #   avg=30  → 58.0   → fault
    cases = [
        ("NORMAL", 100.0, "normal"),   # composite 100.0
        ("WARN", 60.0, "warning"),     # composite 76.0
        ("FAULT", 30.0, "fault"),      # composite 58.0
    ]
    codes = {"NORMAL": "ST", "WARN": "SW", "FAULT": "SF"}
    for i, (tag, hs, _exp) in enumerate(cases):
        sta = _add_station(s, name=f"档站{tag}", code=f"{codes[tag]}-{i}")
        _add_device(s, station_id=sta.id, sn=f"DEV-{tag}-{i}",
                    status=DeviceStatus.ONLINE, health_score=hs)

    resp = client.get("/api/v1/ops-dashboard/health-scores", headers=_h(token))
    assert resp.status_code == 200
    by_name = {st["station_name"]: st for st in resp.json()["stations"]}
    assert by_name["档站NORMAL"]["status"] == "normal"
    assert by_name["档站WARN"]["status"] == "warning"
    assert by_name["档站FAULT"]["status"] == "fault"


# ========== Event Stream 混合事件测试 ==========

def test_event_stream_mixed():
    """插入 Alarm+WorkOrder+HealingExecution 各一条，验证倒序、三类 type、station_id 过滤"""
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus, WorkOrderLevel
    from app.models.healing_execution import HealingExecution
    from datetime import datetime, timezone, timedelta
    token = _login()
    s = _setup_test_db.session

    # 建站点 + 设备（Alarm 需 device_id, station_id）
    sta = _add_station(s, name="事件站", code="EV-A")
    dev = _add_device(s, station_id=sta.id, sn="EV-DEV", status="online")

    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # 三条事件时间递增：alarm 最早 → workorder 中 → healing 最新（倒序应为 healing→workorder→alarm）
    s.add(Alarm(
        device_id=dev.id, station_id=sta.id, alarm_type="over_temp",
        level=AlarmLevel.WARNING, content="温度告警", status=AlarmStatus.ACTIVE,
        created_at=base,
    ))
    s.add(WorkOrder(
        id="WO-EV-001", type=WorkOrderType.REPAIR, level=WorkOrderLevel.INFO,
        station_id=sta.id, device_id=dev.id, status=WorkOrderStatus.PENDING,
        fault_desc="工单事件", create_time=base + timedelta(hours=1),
    ))
    s.add(HealingExecution(
        rule_id=1, rule_name="自愈规则X", alarm_id=1, device_id=dev.id, station_id=sta.id,
        status="success", result="自愈成功", created_at=base + timedelta(hours=2),
    ))
    s.commit()

    # —— 不带 station_id：全部返回 ——
    resp = client.get("/api/v1/ops-dashboard/event-stream", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3

    events = data["events"]
    types = {e["type"] for e in events}
    assert types == {"alarm", "workorder", "healing"}

    # —— 时间倒序：healing(newest) → workorder → alarm(oldest) ——
    assert [e["type"] for e in events] == ["healing", "workorder", "alarm"]
    # 倒序：timestamp 单调递减
    ts = [e["timestamp"] for e in events]
    assert ts == sorted(ts, reverse=True)

    # —— station_id 过滤：命中本站返回全部 ——
    resp2 = client.get(
        f"/api/v1/ops-dashboard/event-stream?station_id={sta.id}", headers=_h(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 3

    # —— station_id 过滤：不存在的站点 → 空事件（不泄露存在性）——
    resp3 = client.get(
        "/api/v1/ops-dashboard/event-stream?station_id=999999", headers=_h(token),
    )
    assert resp3.status_code == 200
    assert resp3.json()["total"] == 0


# ========== Overview 带数据测试 ==========

def test_overview_with_data():
    """插入多站点+设备+告警+工单+自愈，验证聚合统计与 success_rate"""
    from app.models.device import DeviceStatus
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus, WorkOrderLevel
    from app.models.healing_execution import HealingExecution
    from datetime import datetime, timezone
    token = _login()
    s = _setup_test_db.session

    sta1 = _add_station(s, name="概览站A", code="OV-A")
    sta2 = _add_station(s, name="概览站B", code="OV-B")
    # 设备：A 站 2台(1 online+1 fault)，B 站 1台 online → 总3台/2 online/1 fault
    d1 = _add_device(s, station_id=sta1.id, sn="OV-D1", status=DeviceStatus.ONLINE)
    d2 = _add_device(s, station_id=sta1.id, sn="OV-D2", status=DeviceStatus.FAULT)
    d3 = _add_device(s, station_id=sta2.id, sn="OV-D3", status=DeviceStatus.ONLINE)

    # 告警：2 active(其中1 critical) + 1 resolved(不计入 active)
    s.add(Alarm(device_id=d1.id, station_id=sta1.id, alarm_type="t1",
                level=AlarmLevel.CRITICAL, status=AlarmStatus.ACTIVE, content="严重"))
    s.add(Alarm(device_id=d2.id, station_id=sta1.id, alarm_type="t2",
                level=AlarmLevel.WARNING, status=AlarmStatus.ACTIVE, content="警告"))
    s.add(Alarm(device_id=d3.id, station_id=sta2.id, alarm_type="t3",
                level=AlarmLevel.CRITICAL, status=AlarmStatus.RESOLVED, content="已解决"))

    # 工单：1 pending + 1 in_progress + 1 completed(不计入)
    s.add(WorkOrder(id="WO-OV-1", type=WorkOrderType.REPAIR, level=WorkOrderLevel.INFO,
                    station_id=sta1.id, status=WorkOrderStatus.PENDING))
    s.add(WorkOrder(id="WO-OV-2", type=WorkOrderType.REPAIR, level=WorkOrderLevel.INFO,
                    station_id=sta2.id, status=WorkOrderStatus.IN_PROGRESS))
    s.add(WorkOrder(id="WO-OV-3", type=WorkOrderType.REPAIR, level=WorkOrderLevel.INFO,
                    station_id=sta1.id, status=WorkOrderStatus.COMPLETED))

    # 自愈(近24h)：2 条 success + 1 条 failed → success_rate = 2/3*100 = 66.7
    now = datetime.now(timezone.utc)
    s.add(HealingExecution(rule_name="h1", device_id=d1.id, station_id=sta1.id,
                           status="success", created_at=now))
    s.add(HealingExecution(rule_name="h2", device_id=d2.id, station_id=sta1.id,
                           status="success", created_at=now))
    s.add(HealingExecution(rule_name="h3", device_id=d3.id, station_id=sta2.id,
                           status="failed", created_at=now))
    s.commit()

    resp = client.get("/api/v1/ops-dashboard/overview", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()

    # —— stats 聚合 ——
    assert data["stats"]["stations"] == 2
    assert data["stats"]["devices"] == 3
    assert data["stats"]["online"] == 2
    assert data["stats"]["fault"] == 1
    # online_rate = 2/3*100 = 66.666... → round 66.7
    assert data["stats"]["online_rate"] == 66.7

    # —— alarms：active 2(1 critical + 1 warning active)，critical 仅 1（resolved critical 不计）——
    assert data["alarms"]["active"] == 2
    assert data["alarms"]["critical"] == 1

    # —— workorders ——
    assert data["workorders"]["pending"] == 1
    assert data["workorders"]["in_progress"] == 1

    # —— healing success_rate ——
    assert data["healing"]["total_24h"] == 3
    assert data["healing"]["success_24h"] == 2
    assert data["healing"]["success_rate"] == 66.7


# ========== Team Scoping 团队隔离测试 ==========

def test_team_scoping():
    """非 admin 用户（team_id 不同）只能看到本 team 站点数据"""
    from app.models.user import User, UserRole, Team
    token_admin = _login()
    s = _setup_test_db.session

    # 建 team + team 级用户
    team_a = Team(name="团队A", code="TMA")
    team_b = Team(name="团队B", code="TMB")
    s.add_all([team_a, team_b])
    s.commit()
    s.refresh(team_a)
    s.refresh(team_b)

    pwd = "team123456"
    ua = User(
        username="team_a_user", real_name="A队员", role=UserRole.ENGINEER,
        team_id=team_a.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(ua)
    s.commit()

    def _team_token(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败: {r.text}"
        return r.json()["data"]["token"]

    tok_a = _team_token("team_a_user")

    # 站点：team_a 名下1个 + team_b 名下1个；各挂一台设备
    sta_a = _add_station(s, name="A站", code="TS-A", team_id=team_a.id)
    sta_b = _add_station(s, name="B站", code="TS-B", team_id=team_b.id)
    from app.models.device import DeviceStatus
    _add_device(s, station_id=sta_a.id, sn="TS-D1", status=DeviceStatus.ONLINE)
    _add_device(s, station_id=sta_b.id, sn="TS-D2", status=DeviceStatus.FAULT)

    # —— admin 视角：两站都可见 ——
    resp_admin = client.get("/api/v1/ops-dashboard/topology", headers=_h(token_admin))
    assert resp_admin.status_code == 200
    admin_summary = resp_admin.json()["summary"]
    assert admin_summary["total_stations"] == 2
    assert admin_summary["total_devices"] == 2

    # —— team_a 用户视角：仅本 team 站点 ——
    resp = client.get("/api/v1/ops-dashboard/topology", headers=_h(tok_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_stations"] == 1
    assert data["summary"]["total_devices"] == 1
    # 只剩 A 站
    sta_names = {n["name"] for n in data["nodes"]["stations"]}
    assert sta_names == {"A站"}

    # —— overview 同样隔离：team_a 只统计本 team ——
    resp_ov = client.get("/api/v1/ops-dashboard/overview", headers=_h(tok_a))
    assert resp_ov.status_code == 200
    ov = resp_ov.json()
    assert ov["stats"]["stations"] == 1
    # A 站唯一设备是 ONLINE → online=1, fault=0
    assert ov["stats"]["devices"] == 1
    assert ov["stats"]["online"] == 1
    assert ov["stats"]["fault"] == 0
    assert ov["stats"]["online_rate"] == 100.0
