"""
团队归属校验（team scoping）回归测试 — 任务卡 1f13817b。

第二层鉴权：角色授权（require_role）之后，团队级用户只能读写本 team 的
station / device / 孪生配置；跨团队访问一律 404（不泄露资源存在）。
admin/super_admin 为平台级，豁免 team 过滤，跨团队仍可见。

覆盖首批治理文件：stations.py + digital_twin.py。
"""
import bcrypt
import pytest
from datetime import datetime, timedelta, timezone


# ─── 跨团队脚手架 ───

@pytest.fixture(scope="function")
def cross_team(client):
    """构造两团队 + 两团队级用户(engineer) + 两站点(分属两团队) + 各一设备。

    返回:
        teams:    {a, b}   Team ORM
        stations: {a, b}   Station ORM（team_id 已绑定）
        devices:  {a, b}   Device ORM（分别挂在 a/b 站点）
        tokens:   {a, b, admin}  各自登录 token
    """
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus

    s = client._sesh
    ta = Team(name="XT团队A", code="XTA1")
    tb = Team(name="XT团队B", code="XTB1")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "xt123456"
    ua = User(
        username="xt_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="xt_eng_b", real_name="B工程师", role=UserRole.ENGINEER,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    sa = Station(name="XT-A站", code="XTSA1", team_id=ta.id, status=StationStatus.NORMAL)
    sb = Station(name="XT-B站", code="XTSB1", team_id=tb.id, status=StationStatus.NORMAL)
    s.add_all([sa, sb])
    s.commit()
    s.refresh(sa)
    s.refresh(sb)

    da = Device(sn="XT-DEV-A1", name="A逆变器", code="XTINVA",
                type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=sa.id)
    db = Device(sn="XT-DEV-B1", name="B逆变器", code="XTINVB",
                type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=sb.id)
    s.add_all([da, db])
    s.commit()
    s.refresh(da)
    s.refresh(db)

    # ── 二批资源种子（任务卡 ed509541）：gateway/SN/workorder/alarm/healing_execution ──
    from app.models.gateway import Gateway, GatewaySN
    from app.models.workorder import (
        WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus,
    )
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    from app.models.healing_execution import HealingExecution

    gwa = Gateway(sn="XT-GW-A1", name="A网关", station_id=sa.id, status="online")
    gwb = Gateway(sn="XT-GW-B1", name="B网关", station_id=sb.id, status="online")
    s.add_all([gwa, gwb]); s.commit(); s.refresh(gwa); s.refresh(gwb)

    sna = GatewaySN(sn="XT-SN-A1", model="TL-GW-100", team_id=ta.id, status="generated")
    snb = GatewaySN(sn="XT-SN-B1", model="TL-GW-100", team_id=tb.id, status="generated")
    s.add_all([sna, snb]); s.commit(); s.refresh(sna); s.refresh(snb)

    woa = WorkOrder(id="WO-XT-A-1", fault_desc="A工单", type=WorkOrderType.REPAIR,
                    level=WorkOrderLevel.WARNING, station_id=sa.id, status=WorkOrderStatus.PENDING)
    wob = WorkOrder(id="WO-XT-B-1", fault_desc="B工单", type=WorkOrderType.REPAIR,
                    level=WorkOrderLevel.WARNING, station_id=sb.id, status=WorkOrderStatus.PENDING)
    s.add_all([woa, wob]); s.commit()

    ala = Alarm(device_id=da.id, station_id=sa.id, alarm_type="over_temp",
                level=AlarmLevel.WARNING, content="A告警", status=AlarmStatus.ACTIVE)
    alb = Alarm(device_id=db.id, station_id=sb.id, alarm_type="comm_fault",
                level=AlarmLevel.CRITICAL, content="B告警", status=AlarmStatus.ACTIVE)
    s.add_all([ala, alb]); s.commit(); s.refresh(ala); s.refresh(alb)

    hea = HealingExecution(rule_id=1, rule_name="A自愈", alarm_id=ala.id,
                           device_id=da.id, station_id=sa.id, status="pending_approval")
    heb = HealingExecution(rule_id=1, rule_name="B自愈", alarm_id=alb.id,
                           device_id=db.id, station_id=sb.id, status="pending_approval")
    s.add_all([hea, heb]); s.commit(); s.refresh(hea); s.refresh(heb)

    # ── 协议实例种子（任务卡 ed509541）：经 gateway→station→team 三跳归属 ──
    # protocol_instances 表无 ORM model、不在 Base.metadata，create_all 不建，
    # 需在此显式建表（与 tests/test_protocol_instances.py 同构）。
    from sqlalchemy import text
    s.execute(text("""
        CREATE TABLE IF NOT EXISTS protocol_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            protocol_type TEXT NOT NULL,
            gateway_id INTEGER,
            device_type TEXT,
            config TEXT,
            parser_schema TEXT,
            status TEXT NOT NULL DEFAULT 'stopped',
            connection_status TEXT NOT NULL DEFAULT 'disconnected',
            last_connected DATETIME,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    s.execute(text("""
        CREATE TABLE IF NOT EXISTS parser_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL,
            protocol TEXT NOT NULL,
            parser_schema TEXT,
            config TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    s.execute(text(
        "INSERT INTO protocol_instances (name, protocol_type, gateway_id, status) "
        "VALUES (:name, :ptype, :gid, 'stopped')"
    ), [
        {"name": "A实例", "ptype": "mqtt", "gid": gwa.id},
        {"name": "B实例", "ptype": "rest", "gid": gwb.id},
    ])
    s.commit()
    pia = s.execute(text("SELECT id FROM protocol_instances WHERE gateway_id = :g"),
                    {"g": gwa.id}).first()
    pib = s.execute(text("SELECT id FROM protocol_instances WHERE gateway_id = :g"),
                    {"g": gwb.id}).first()

    def _tok(username, password):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        j = r.json()
        return j.get("data", {}).get("token") or j.get("token")

    return {
        "teams": {"a": ta, "b": tb},
        "stations": {"a": sa, "b": sb},
        "devices": {"a": da, "b": db},
        "gateways": {"a": gwa, "b": gwb},
        "sns": {"a": sna, "b": snb},
        "workorders": {"a": woa, "b": wob},
        "alarms": {"a": ala, "b": alb},
        "executions": {"a": hea, "b": heb},
        "instances": {"a": pia.id, "b": pib.id},
        "tokens": {
            "a": _tok("xt_eng_a", pwd),
            "b": _tok("xt_eng_b", pwd),
            "admin": _tok("admin", "admin123"),
        },
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ─── stations.py 团队归属校验 ───

class TestStationTeamScoping:
    """团队级用户只能访问本 team 站点；admin 跨团队可见。"""

    def test_user_reads_own_team_station(self, client, cross_team):
        r = client.get(f"/api/v1/stations/{cross_team['stations']['a'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_read_other_team_station(self, client, cross_team):
        """用户A读团队B站点 → 404（不泄露存在）。"""
        r = client.get(f"/api/v1/stations/{cross_team['stations']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_reads_other_team_station(self, client, cross_team):
        """admin 平台级，跨团队可见。"""
        r = client.get(f"/api/v1/stations/{cross_team['stations']['b'].id}",
                       headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200

    def test_list_filters_by_team(self, client, cross_team):
        """列表只返回本 team 站点，不串他队。"""
        r = client.get("/api/v1/stations", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["stations"]["a"].id in ids
        assert cross_team["stations"]["b"].id not in ids

    def test_list_admin_sees_all(self, client, cross_team):
        """admin 列表可见全部团队站点（不被 team 过滤裁剪）。"""
        r = client.get("/api/v1/stations", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["stations"]["a"].id in ids
        assert cross_team["stations"]["b"].id in ids

    def test_list_cache_does_not_leak_across_users(self, client, cross_team):
        """A 先查列表（缓存写入），B 紧接查列表 — B 不得命中 A 的缓存而看到 A 的站点。"""
        ra = client.get("/api/v1/stations", headers=_h(cross_team["tokens"]["a"]))
        assert ra.status_code == 200
        ids_a = [it["id"] for it in ra.json()["data"]["items"]]
        assert cross_team["stations"]["b"].id not in ids_a  # A 看不到 B
        # B 紧接查（若按 URL 缓存串数据，B 会拿到 A 的列表）
        rb = client.get("/api/v1/stations", headers=_h(cross_team["tokens"]["b"]))
        assert rb.status_code == 200
        ids_b = [it["id"] for it in rb.json()["data"]["items"]]
        assert cross_team["stations"]["a"].id not in ids_b  # B 看不到 A
        assert cross_team["stations"]["b"].id in ids_b

    def test_user_cannot_update_other_team_station(self, client, cross_team):
        r = client.put(f"/api/v1/stations/{cross_team['stations']['b'].id}",
                       json={"name": "被篡改"}, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_station(self, client, cross_team):
        r = client.delete(f"/api/v1/stations/{cross_team['stations']['b'].id}",
                          headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_non_admin_cannot_assign_station(self, client, cross_team):
        """分配站点给团队是平台级操作，团队级用户 → 403。"""
        r = client.put(f"/api/v1/stations/{cross_team['stations']['a'].id}/assign",
                       json={"team_id": cross_team["teams"]["b"].id},
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 403


# ─── digital_twin.py 团队归属校验（经 device→station 间接）───

class TestDigitalTwinTeamScoping:
    """孪生配置经 device→station 间接归属 team；跨团队读写 → 404。"""

    def test_user_creates_model_on_own_device(self, client, cross_team):
        r = client.post("/api/v1/digital-twin/models",
                        json={"device_id": cross_team["devices"]["a"].id,
                              "model_type": "solar_inverter"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 201

    def test_user_cannot_create_model_on_other_team_device(self, client, cross_team):
        """用户A在团队B设备上建孪生配置 → 404。"""
        r = client.post("/api/v1/digital-twin/models",
                        json={"device_id": cross_team["devices"]["b"].id,
                              "model_type": "solar_inverter"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_creates_model_on_any_device(self, client, cross_team):
        r = client.post("/api/v1/digital-twin/models",
                        json={"device_id": cross_team["devices"]["b"].id,
                              "model_type": "solar_inverter"},
                        headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 201

    def test_user_cannot_read_other_team_model(self, client, cross_team):
        """B 在自己设备建配置，A 读该配置 → 404。"""
        client.post("/api/v1/digital-twin/models",
                    json={"device_id": cross_team["devices"]["b"].id,
                          "model_type": "solar_inverter"},
                    headers=_h(cross_team["tokens"]["admin"]))
        # 取 B 设备的 model id
        mid = client.get(f"/api/v1/digital-twin/models?device_id={cross_team['devices']['b'].id}",
                         headers=_h(cross_team["tokens"]["admin"])).json()["data"]["items"][0]["id"]
        r = client.get(f"/api/v1/digital-twin/models/{mid}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_model(self, client, cross_team):
        client.post("/api/v1/digital-twin/models",
                    json={"device_id": cross_team["devices"]["b"].id,
                          "model_type": "solar_inverter"},
                    headers=_h(cross_team["tokens"]["admin"]))
        mid = client.get(f"/api/v1/digital-twin/models?device_id={cross_team['devices']['b'].id}",
                         headers=_h(cross_team["tokens"]["admin"])).json()["data"]["items"][0]["id"]
        r = client.delete(f"/api/v1/digital-twin/models/{mid}",
                          headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_creates_scene_on_own_station(self, client, cross_team):
        r = client.post("/api/v1/digital-twin/scenes",
                        json={"station_id": cross_team["stations"]["a"].id, "name": "A场景"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 201

    def test_user_cannot_create_scene_on_other_team_station(self, client, cross_team):
        r = client.post("/api/v1/digital-twin/scenes",
                        json={"station_id": cross_team["stations"]["b"].id, "name": "越权场景"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_realtime_other_team_station_404(self, client, cross_team):
        """用户A拉取团队B站点实时聚合 → 404。"""
        r = client.get(f"/api/v1/digital-twin/realtime?station_id={cross_team['stations']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_realtime_own_station_ok(self, client, cross_team):
        r = client.get(f"/api/v1/digital-twin/realtime?station_id={cross_team['stations']['a'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200

    def test_init_default_other_team_station_404(self, client, cross_team):
        """用户A为团队B站点初始化默认孪生 → 404。"""
        r = client.post(f"/api/v1/digital-twin/init-default?station_id={cross_team['stations']['b'].id}",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_init_default_any_station(self, client, cross_team):
        r = client.post(f"/api/v1/digital-twin/init-default?station_id={cross_team['stations']['b'].id}",
                        headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200


# ─── devices.py 团队归属校验（device→station→team）───

class TestDeviceTeamScoping:
    """设备经 station 间接归属 team；跨团队读写 → 404。"""

    def test_list_filters_by_team(self, client, cross_team):
        r = client.get("/api/v1/devices?page_size=100", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["devices"]["a"].id in ids
        assert cross_team["devices"]["b"].id not in ids

    def test_list_admin_sees_all(self, client, cross_team):
        r = client.get("/api/v1/devices?page_size=100", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["devices"]["a"].id in ids
        assert cross_team["devices"]["b"].id in ids

    def test_list_no_cache_leak_across_users(self, client, cross_team):
        """A 先查（缓存），B 紧接查 — B 不得命中 A 的缓存而看到 A 的设备。"""
        ra = client.get("/api/v1/devices?page_size=100", headers=_h(cross_team["tokens"]["a"]))
        assert cross_team["devices"]["b"].id not in [it["id"] for it in ra.json()["data"]["items"]]
        rb = client.get("/api/v1/devices?page_size=100", headers=_h(cross_team["tokens"]["b"]))
        assert cross_team["devices"]["a"].id not in [it["id"] for it in rb.json()["data"]["items"]]
        assert cross_team["devices"]["b"].id in [it["id"] for it in rb.json()["data"]["items"]]

    def test_user_gets_own_device(self, client, cross_team):
        r = client.get(f"/api/v1/devices/{cross_team['devices']['a'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_team_device(self, client, cross_team):
        r = client.get(f"/api/v1/devices/{cross_team['devices']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_gets_other_team_device(self, client, cross_team):
        r = client.get(f"/api/v1/devices/{cross_team['devices']['b'].id}",
                       headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_update_other_team_device(self, client, cross_team):
        r = client.put(f"/api/v1/devices/{cross_team['devices']['b'].id}",
                       json={"name": "被篡改"}, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_device(self, client, cross_team):
        r = client.delete(f"/api/v1/devices/{cross_team['devices']['b'].id}",
                          headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_control_other_team_device(self, client, cross_team):
        r = client.post(f"/api/v1/devices/{cross_team['devices']['b'].id}/control",
                        json={"action": "start"}, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_get_other_team_efficiency(self, client, cross_team):
        r = client.get(f"/api/v1/devices/{cross_team['devices']['b'].id}/efficiency",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_with_own_station_ok(self, client, cross_team):
        r = client.post("/api/v1/devices",
                        json={"sn": "XT-NEW-A", "code": "XTNEWA", "name": "新A设备",
                              "type": "charger_dc", "station_id": str(cross_team["stations"]["a"].id)},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_create_with_other_team_station_404(self, client, cross_team):
        """非 admin 用他团站点建设备 → 404（不泄露站点存在）。"""
        r = client.post("/api/v1/devices",
                        json={"sn": "XT-LEAK", "code": "XTLEAK", "name": "越权设备",
                              "type": "charger_dc", "station_id": str(cross_team["stations"]["b"].id)},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_devices_401(self, anon_client):
        """匿名访问设备列表 → 401（用 anon_client，勿用认证 client）。"""
        assert anon_client.get("/api/v1/devices").status_code == 401


# ─── gateways.py 团队归属校验（gateway→station→team；SN 自身 team_id）───

class TestGatewayTeamScoping:
    """网关经 station 归属 team；SN 自身带 team_id；跨团队读写 → 404。"""

    def test_list_filters_by_team(self, client, cross_team):
        r = client.get("/api/v1/gateways", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["gateways"]["a"].id in ids
        assert cross_team["gateways"]["b"].id not in ids

    def test_list_admin_sees_all(self, client, cross_team):
        r = client.get("/api/v1/gateways", headers=_h(cross_team["tokens"]["admin"]))
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["gateways"]["a"].id in ids
        assert cross_team["gateways"]["b"].id in ids

    def test_user_cannot_get_other_team_gateway(self, client, cross_team):
        r = client.get(f"/api/v1/gateways/{cross_team['gateways']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_update_other_team_gateway(self, client, cross_team):
        r = client.put(f"/api/v1/gateways/{cross_team['gateways']['b'].id}",
                       json={"name": "被篡改"}, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_gateway(self, client, cross_team):
        r = client.delete(f"/api/v1/gateways/{cross_team['gateways']['b'].id}",
                          headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_with_other_team_station_404(self, client, cross_team):
        r = client.post("/api/v1/gateways",
                        json={"sn": "XT-GW-LEAK", "name": "越权网关",
                              "station_id": cross_team["stations"]["b"].id},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_sn_list_filters_by_team(self, client, cross_team):
        """GatewaySN 自身 team_id：非 admin 只见本团队 SN。"""
        r = client.get("/api/v1/gateways/sn?page_size=100", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["sns"]["a"].id in ids
        assert cross_team["sns"]["b"].id not in ids

    def test_user_cannot_lock_other_team_sn(self, client, cross_team):
        r = client.post(f"/api/v1/gateways/sn/{cross_team['sns']['b'].id}/lock",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_create_upgrade_task_other_team_gateway(self, client, cross_team):
        """非 admin 为他团网关建升级任务 → 404（gateway 归属先于 firmware 校验）。"""
        r = client.post("/api/v1/gateways/upgrade-tasks",
                        json={"gateway_id": cross_team["gateways"]["b"].id, "firmware_id": 1},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_gateways_401(self, anon_client):
        assert anon_client.get("/api/v1/gateways").status_code == 401


# ─── workorders.py 团队归属校验（workorder→station→team）───

class TestWorkorderTeamScoping:
    """工单经 station 归属 team；跨团队读写 → 404。"""

    def test_list_filters_by_team(self, client, cross_team):
        r = client.get("/api/v1/work-orders?page_size=100", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["workorders"]["a"].id in ids
        assert cross_team["workorders"]["b"].id not in ids

    def test_list_admin_sees_all(self, client, cross_team):
        r = client.get("/api/v1/work-orders?page_size=100", headers=_h(cross_team["tokens"]["admin"]))
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["workorders"]["a"].id in ids
        assert cross_team["workorders"]["b"].id in ids

    def test_list_no_cache_leak_across_users(self, client, cross_team):
        ra = client.get("/api/v1/work-orders?page_size=100", headers=_h(cross_team["tokens"]["a"]))
        assert cross_team["workorders"]["b"].id not in [it["id"] for it in ra.json()["data"]["items"]]
        rb = client.get("/api/v1/work-orders?page_size=100", headers=_h(cross_team["tokens"]["b"]))
        assert cross_team["workorders"]["a"].id not in [it["id"] for it in rb.json()["data"]["items"]]

    def test_user_cannot_get_other_team_workorder(self, client, cross_team):
        r = client.get(f"/api/v1/work-orders/{cross_team['workorders']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_accept_other_team_workorder(self, client, cross_team):
        r = client.post(f"/api/v1/work-orders/{cross_team['workorders']['b'].id}/accept",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_update_other_team_workorder(self, client, cross_team):
        r = client.put(f"/api/v1/work-orders/{cross_team['workorders']['b'].id}",
                       json={"fault_desc": "被篡改"}, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_workorder(self, client, cross_team):
        r = client.delete(f"/api/v1/work-orders/{cross_team['workorders']['b'].id}",
                          headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_with_other_team_station_404(self, client, cross_team):
        r = client.post("/api/v1/work-orders",
                        json={"fault_desc": "越权工单", "station_id": cross_team["stations"]["b"].id},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_workorders_401(self, anon_client):
        assert anon_client.get("/api/v1/work-orders").status_code == 401


# ─── protocol_instances.py 团队归属校验（经 gateway→station→team 三跳）───

class TestProtocolInstanceTeamScoping:
    """协议实例经 gateway→station→team 三跳归属；跨团队读写 → 404。
    gateway_id 为空的实例无法判定归属，仅平台 admin 可见。"""

    def test_user_lists_own_team_only(self, client, cross_team):
        r = client.get("/api/v1/protocol-instances", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["instances"]["a"] in ids
        assert cross_team["instances"]["b"] not in ids

    def test_admin_lists_all(self, client, cross_team):
        r = client.get("/api/v1/protocol-instances", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["instances"]["a"] in ids
        assert cross_team["instances"]["b"] in ids

    def test_user_cannot_read_other_team_instance(self, client, cross_team):
        r = client.get(f"/api/v1/protocol-instances/{cross_team['instances']['b']}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_reads_other_team_instance(self, client, cross_team):
        r = client.get(f"/api/v1/protocol-instances/{cross_team['instances']['b']}",
                       headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_update_other_team_instance(self, client, cross_team):
        r = client.put(f"/api/v1/protocol-instances/{cross_team['instances']['b']}",
                       json={"name": "被篡改"}, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_instance(self, client, cross_team):
        r = client.delete(f"/api/v1/protocol-instances/{cross_team['instances']['b']}",
                          headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_connect_other_team_instance(self, client, cross_team):
        r = client.post(f"/api/v1/protocol-instances/{cross_team['instances']['b']}/connect",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_disconnect_other_team_instance(self, client, cross_team):
        r = client.post(f"/api/v1/protocol-instances/{cross_team['instances']['b']}/disconnect",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_on_other_team_gateway_404(self, client, cross_team):
        """B 传 A 的 gateway_id 创建实例 → 404（网关不归属 B）。"""
        r = client.post("/api/v1/protocol-instances",
                        json={"name": "越权实例", "protocol_type": "mqtt",
                              "gateway_id": cross_team["gateways"]["a"].id},
                        headers=_h(cross_team["tokens"]["b"]))
        assert r.status_code == 404

    def test_user_create_on_own_gateway_ok(self, client, cross_team):
        r = client.post("/api/v1/protocol-instances",
                        json={"name": "B新实例", "protocol_type": "mqtt",
                              "gateway_id": cross_team["gateways"]["b"].id},
                        headers=_h(cross_team["tokens"]["b"]))
        assert r.status_code in (200, 201)

    def test_user_create_without_gateway_rejected(self, client, cross_team):
        """非 admin 创建无 gateway_id 实例（无法判定归属）→ 拒绝。"""
        r = client.post("/api/v1/protocol-instances",
                        json={"name": "游离实例", "protocol_type": "mqtt"},
                        headers=_h(cross_team["tokens"]["b"]))
        assert r.status_code == 400

    def test_user_dashboard_counts_own_team_only(self, client, cross_team):
        """连接仪表板非 admin 仅统计本 team 实例。"""
        r = client.get("/api/v1/connection-dashboard", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        stats = r.json()["data"]["stats"]
        assert stats["total"] == 1  # A 团队仅 A实例

    def test_admin_dashboard_counts_all(self, client, cross_team):
        r = client.get("/api/v1/connection-dashboard", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        stats = r.json()["data"]["stats"]
        assert stats["total"] == 2  # A + B

    def test_anon_list_instances_401(self, anon_client):
        assert anon_client.get("/api/v1/protocol-instances").status_code == 401


# ─── alarms.py 团队归属校验（经 alarm.station_id→team）───

class TestAlarmTeamScoping:
    """告警经 station→team 归属；跨团队读写 → 404。
    ack/resolve/ignore/delete 受 require_permission 先拦（403），其 team 逻辑
    与 alarm_notices 共用 assert_alarm_team_access，由 TestAlarmNoticeTeamScoping 覆盖。"""

    def test_user_lists_own_team_only(self, client, cross_team):
        r = client.get("/api/v1/alarms", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["alarms"]["a"].id in ids
        assert cross_team["alarms"]["b"].id not in ids

    def test_admin_lists_all(self, client, cross_team):
        r = client.get("/api/v1/alarms", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["alarms"]["a"].id in ids
        assert cross_team["alarms"]["b"].id in ids

    def test_user_cannot_read_other_team_alarm(self, client, cross_team):
        r = client.get(f"/api/v1/alarms/{cross_team['alarms']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_see_other_team_notifications(self, client, cross_team):
        r = client.get(f"/api/v1/alarms/{cross_team['alarms']['b'].id}/notifications",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_on_other_team_device_404(self, client, cross_team):
        r = client.post("/api/v1/alarms",
                        json={"device_id": cross_team["devices"]["b"].id,
                              "alarm_type": "over_temp", "content": "越权告警"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_on_own_device_ok(self, client, cross_team):
        r = client.post("/api/v1/alarms",
                        json={"device_id": cross_team["devices"]["a"].id,
                              "alarm_type": "over_temp", "content": "A新告警"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code in (200, 201)

    def test_user_stats_counts_own_team_only(self, client, cross_team):
        r = client.get("/api/v1/alarms/stats/summary", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1  # A 团队仅 A告警

    def test_admin_stats_counts_all(self, client, cross_team):
        r = client.get("/api/v1/alarms/stats/summary", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2  # A + B

    def test_anon_list_alarms_401(self, anon_client):
        assert anon_client.get("/api/v1/alarms").status_code == 401


# ─── alarm_notices.py 团队归属校验（经 alarm→station→team）───

class TestAlarmNoticeTeamScoping:
    """告警通知经 alarm→station→team；跨团队读写 → 404。
    alarm_notices 端点无 require_permission，团队级用户直达 team 校验。"""

    def test_user_lists_own_team_only(self, client, cross_team):
        r = client.get("/api/v1/alarm-notices", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["alarms"]["a"].id in ids
        assert cross_team["alarms"]["b"].id not in ids

    def test_user_cannot_read_other_team_notice(self, client, cross_team):
        r = client.put(f"/api/v1/alarm-notices/{cross_team['alarms']['b'].id}/read",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_resolve_other_team_notice(self, client, cross_team):
        r = client.put(f"/api/v1/alarm-notices/{cross_team['alarms']['b'].id}/resolve",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_ignore_other_team_notice(self, client, cross_team):
        r = client.put(f"/api/v1/alarm-notices/{cross_team['alarms']['b'].id}/ignore",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_read_own_notice_ok(self, client, cross_team):
        r = client.put(f"/api/v1/alarm-notices/{cross_team['alarms']['a'].id}/read",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_stats_own_team_only(self, client, cross_team):
        r = client.get("/api/v1/alarm-notices/stats", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total_unread"] == 1  # A 团队仅 A告警(未处理)

    def test_mark_all_read_only_affects_own_team(self, client, cross_team):
        """A 全部已读不得影响 B 团队告警状态。"""
        r = client.put("/api/v1/alarm-notices/read-all", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        # B 告警仍 ACTIVE（未被 A 的 read-all 触及）
        rb = client.get(f"/api/v1/alarms/{cross_team['alarms']['b'].id}",
                        headers=_h(cross_team["tokens"]["admin"]))
        assert rb.json()["data"]["status"] == "active"

    def test_anon_list_notices_401(self, anon_client):
        assert anon_client.get("/api/v1/alarm-notices").status_code == 401


# ─── healing.py 团队归属校验（经 execution.station_id→team / trigger 经 alarm→team）───

class TestHealingTeamScoping:
    """自愈执行经 station→team 归属；跨团队读写 → 404。trigger 经 alarm→team。
    HealingRule 平台级（无 team_id），不在 team scoping 范围。"""

    def test_user_lists_own_team_only(self, client, cross_team):
        r = client.get("/api/v1/healing/executions", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["executions"]["a"].id in ids
        assert cross_team["executions"]["b"].id not in ids

    def test_admin_lists_all(self, client, cross_team):
        r = client.get("/api/v1/healing/executions", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team["executions"]["a"].id in ids
        assert cross_team["executions"]["b"].id in ids

    def test_user_cannot_read_other_team_execution(self, client, cross_team):
        r = client.get(f"/api/v1/healing/executions/{cross_team['executions']['b'].id}",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_approve_other_team_execution(self, client, cross_team):
        r = client.post(f"/api/v1/healing/executions/{cross_team['executions']['b'].id}/approve",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_reject_other_team_execution(self, client, cross_team):
        r = client.post(f"/api/v1/healing/executions/{cross_team['executions']['b'].id}/reject",
                        json={"reason": "越权"},
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_retry_other_team_execution(self, client, cross_team):
        r = client.post(f"/api/v1/healing/executions/{cross_team['executions']['b'].id}/retry",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_verify_other_team_execution(self, client, cross_team):
        r = client.post(f"/api/v1/healing/executions/{cross_team['executions']['b'].id}/verify",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_trigger_other_team_alarm(self, client, cross_team):
        """trigger 保持 healing 的 error_response 契约：跨团队 → 200 + body code=404。"""
        r = client.post(f"/api/v1/healing/trigger/{cross_team['alarms']['b'].id}",
                        headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["code"] == 404

    def test_anon_list_executions_401(self, anon_client):
        assert anon_client.get("/api/v1/healing/executions").status_code == 401


# ═══════════════════════════════════════════════════════════════════
# 三批（任务卡 b640bdd9）：核心交易域 team scoping
# charging_orders / analytics / reports —— 订单经 station→team，analytics 按
# device/station 归属，reports 聚合按本 team 站点集合过滤。
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(scope="function")
def cross_team_orders(client, cross_team):
    """三批资源种子：在 cross_team 两站两设备基础上，各加一充电订单 + 若干遥测行，
    供 charging_orders / analytics 越权回归用。返回 cross_team 全部键 + orders。"""
    from app.models.charging_order import (
        ChargingOrder, OrderStatus, OrderPaymentStatus,
    )
    from app.models.telemetry import Telemetry
    from datetime import datetime, timedelta, timezone

    s = client._sesh
    sa, sb = cross_team["stations"]["a"], cross_team["stations"]["b"]
    da, db_ = cross_team["devices"]["a"], cross_team["devices"]["b"]

    oa = ChargingOrder(
        order_no="CO-XT-A-1", station_id=sa.id, device_id=da.id,
        charged_kwh=10, order_status=OrderStatus.PENDING,
        payment_status=OrderPaymentStatus.UNPAID,
    )
    ob = ChargingOrder(
        order_no="CO-XT-B-1", station_id=sb.id, device_id=db_.id,
        charged_kwh=20, order_status=OrderStatus.PENDING,
        payment_status=OrderPaymentStatus.UNPAID,
    )
    s.add_all([oa, ob]); s.commit(); s.refresh(oa); s.refresh(ob)

    # 无告警的干净设备（analytics health-score 正向验证用：cross_team 的设备各挂一条
    # alarm，会触发 analytics.py 预存的 alarm.severity 缺字段崩溃，与 team scoping 无关）。
    from app.models.device import Device, DeviceType, DeviceStatus
    da_clean = Device(sn="XT-DEV-A-CLN", name="A干净设备", code="XTCLNA",
                     type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=sa.id)
    db_clean = Device(sn="XT-DEV-B-CLN", name="B干净设备", code="XTCLNB",
                     type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=sb.id)
    s.add_all([da_clean, db_clean]); s.commit(); s.refresh(da_clean); s.refresh(db_clean)

    ts = datetime.now(timezone.utc) - timedelta(hours=2)
    for dev in (da, db_, da_clean, db_clean):
        for k in range(3):
            s.add(Telemetry(device_id=dev.id, timestamp=ts, grid_power_total=10.0 + k))
    s.commit()

    return {**cross_team, "orders": {"a": oa, "b": ob},
            "devices_clean": {"a": da_clean, "b": db_clean}}


# ─── charging_orders.py 团队归属校验（订单经 station→team）───

class TestChargingOrderTeamScoping:
    """团队级用户只能读写本 team 站点的订单；admin 跨团队可见。"""

    def test_user_lists_only_own_team_orders(self, client, cross_team_orders):
        """A 列表只见本 team 订单，不见 B 的。"""
        r = client.get("/api/v1/charging-orders", headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team_orders["orders"]["a"].id in ids
        assert cross_team_orders["orders"]["b"].id not in ids

    def test_admin_lists_all_orders(self, client, cross_team_orders):
        r = client.get("/api/v1/charging-orders", headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert cross_team_orders["orders"]["a"].id in ids
        assert cross_team_orders["orders"]["b"].id in ids

    def test_user_cannot_read_other_team_order(self, client, cross_team_orders):
        """A 读 B 的订单 → 404（不泄露存在）。"""
        r = client.get(f"/api/v1/charging-orders/{cross_team_orders['orders']['b'].id}",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_can_read_any_order(self, client, cross_team_orders):
        r = client.get(f"/api/v1/charging-orders/{cross_team_orders['orders']['b'].id}",
                       headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_update_other_team_order_status(self, client, cross_team_orders):
        """A 改 B 订单状态 → 404。"""
        r = client.put(f"/api/v1/charging-orders/{cross_team_orders['orders']['b'].id}/status",
                       json={"status": "cancelled"}, headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_create_order_on_other_team_station(self, client, cross_team_orders):
        """A 在 B 站点建单 → 404。"""
        sb = cross_team_orders["stations"]["b"]
        da = cross_team_orders["devices"]["a"]
        r = client.post("/api/v1/charging-orders",
                        json={"station_id": sb.id, "device_id": da.id, "charged_kwh": 5},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_creates_order_on_own_station(self, client, cross_team_orders):
        """A 在本 team 站点建单 → 200。"""
        sa = cross_team_orders["stations"]["a"]
        da = cross_team_orders["devices"]["a"]
        r = client.post("/api/v1/charging-orders",
                        json={"station_id": sa.id, "device_id": da.id, "charged_kwh": 5},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200


# ─── analytics.py 团队归属校验（device/station 归属）───

class TestAnalyticsTeamScoping:
    """analytics 端点按 device/station 归属本 team；跨团队 device/station → 404。"""

    def test_user_cannot_score_other_team_device(self, client, cross_team_orders):
        r = client.post("/api/v1/analytics/health-score",
                        json={"device_id": cross_team_orders["devices"]["b"].id, "days": 7},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_scores_own_device(self, client, cross_team_orders):
        # 用无告警的干净设备（cross_team 设备挂告警会触发 analytics 预存崩溃，与本批无关）
        r = client.post("/api/v1/analytics/health-score",
                        json={"device_id": cross_team_orders["devices_clean"]["a"].id, "days": 7},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200

    def test_admin_scores_any_device(self, client, cross_team_orders):
        r = client.post("/api/v1/analytics/health-score",
                        json={"device_id": cross_team_orders["devices_clean"]["b"].id, "days": 7},
                        headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_analyze_other_team_device_ids(self, client, cross_team_orders):
        from datetime import datetime, timedelta
        end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        r = client.post("/api/v1/analytics/efficiency-analysis",
                        json={"device_ids": [cross_team_orders["devices"]["b"].id],
                              "start_date": start, "end_date": end},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_analyze_other_team_station(self, client, cross_team_orders):
        from datetime import datetime, timedelta
        end = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        r = client.post("/api/v1/analytics/efficiency-analysis",
                        json={"station_id": cross_team_orders["stations"]["b"].id,
                              "start_date": start, "end_date": end},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_detect_other_team_device(self, client, cross_team_orders):
        r = client.post("/api/v1/analytics/anomaly-detection",
                        json={"device_id": cross_team_orders["devices"]["b"].id, "hours": 24},
                        headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404


# ─── reports.py 团队归属校验（聚合按本 team 站点集合过滤）───

class TestReportTeamScoping:
    """报表聚合非 admin 仅本 team 站点派生资源；station_id 越权 → 404。"""

    def test_user_devices_report_only_own(self, client, cross_team):
        """A 设备报表只统计本 team 设备（1 台），不见 B 的。"""
        r = client.get("/api/v1/reports/devices", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total_devices"] == 1
        ids = {s["station_id"] for s in r.json()["data"]["station_distribution"]}
        assert cross_team["stations"]["a"].id in ids
        assert cross_team["stations"]["b"].id not in ids

    def test_admin_devices_report_all(self, client, cross_team):
        r = client.get("/api/v1/reports/devices", headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["total_devices"] == 2

    def test_user_summary_only_own(self, client, cross_team):
        """A 汇总报表只算本 team 站点（1）/设备（1）/工单/告警。"""
        r = client.get("/api/v1/reports/summary", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        ov = r.json()["data"]["overview"]
        assert ov["total_stations"] == 1
        assert ov["total_devices"] == 1

    def test_user_alarms_report_only_own(self, client, cross_team):
        """A 告警报表只见本 team 告警（1 条 ACTIVE）。"""
        r = client.get("/api/v1/reports/alarms", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total_alarms"] == 1
        assert r.json()["data"]["active_alarms"] == 1

    def test_user_workorders_report_only_own(self, client, cross_team):
        r = client.get("/api/v1/reports/workorders", headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total_workorders"] == 1

    def test_user_cannot_query_other_team_station(self, client, cross_team):
        """A 传 B 站点 station_id 查报表 → 404。"""
        sid = cross_team["stations"]["b"].id
        for path in ("devices", "workorders", "alarms", "faults", "v2g"):
            r = client.get(f"/api/v1/reports/{path}?station_id={sid}",
                           headers=_h(cross_team["tokens"]["a"]))
            assert r.status_code == 404, f"{path} 应拒绝跨团队 station_id"

    def test_admin_can_query_any_station(self, client, cross_team):
        sid = cross_team["stations"]["b"].id
        r = client.get(f"/api/v1/reports/devices?station_id={sid}",
                       headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200

    def test_anon_summary_401(self, anon_client):
        assert anon_client.get("/api/v1/reports/summary").status_code == 401


# ─── efficiency.py 团队归属校验（报表按 Station.team_id 过滤）───
# 任务卡 e1f0e6d5（四批）：utilization/efficiency/v2g/generation 四只读端点。

class TestEfficiencyTeamScoping:
    """效率报表非 admin 仅本 team 设备派生；station_id 越权 → 404；admin 全见。"""

    def test_user_utilization_only_own_team(self, client, cross_team_orders):
        """A 利用率报表只见本 team 设备，不见 B 的。"""
        r = client.get("/api/v1/reports/utilization", headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200
        sids = {it["station_id"] for it in r.json()["data"]["items"]}
        assert cross_team_orders["stations"]["a"].id in sids
        assert cross_team_orders["stations"]["b"].id not in sids

    def test_admin_utilization_sees_all(self, client, cross_team_orders):
        r = client.get("/api/v1/reports/utilization", headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200
        sids = {it["station_id"] for it in r.json()["data"]["items"]}
        assert cross_team_orders["stations"]["a"].id in sids
        assert cross_team_orders["stations"]["b"].id in sids

    def test_user_generation_only_own_team(self, client, cross_team_orders):
        """A 光伏 PR 报表只见本 team 逆变器。"""
        r = client.get("/api/v1/reports/generation", headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200
        sids = {it["station_id"] for it in r.json()["data"]["items"]}
        assert cross_team_orders["stations"]["a"].id in sids
        assert cross_team_orders["stations"]["b"].id not in sids

    def test_user_cannot_query_other_team_station(self, client, cross_team_orders):
        """A 传 B station_id 查报表 → 404（不泄露站点存在）。"""
        sid = cross_team_orders["stations"]["b"].id
        for path in ("utilization", "efficiency", "generation"):
            r = client.get(f"/api/v1/reports/{path}?station_id={sid}",
                           headers=_h(cross_team_orders["tokens"]["a"]))
            assert r.status_code == 404, f"{path} 应拒绝跨团队 station_id"

    def test_user_queries_own_station_ok(self, client, cross_team_orders):
        """A 传本 team station_id 查报表 → 200（负向 404 的正向对照，防前缀假阳性）。"""
        sid = cross_team_orders["stations"]["a"].id
        for path in ("utilization", "efficiency", "generation"):
            r = client.get(f"/api/v1/reports/{path}?station_id={sid}",
                           headers=_h(cross_team_orders["tokens"]["a"]))
            assert r.status_code == 200, f"{path} 本团队 station 应放行"

    def test_admin_queries_any_station(self, client, cross_team_orders):
        sid = cross_team_orders["stations"]["b"].id
        r = client.get(f"/api/v1/reports/utilization?station_id={sid}",
                       headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_v2g_report_only_own_team(self, client, cross_team_orders):
        """A 的 V2G 报表只统计本 team V2G 桩（1 台），不见 B 的。"""
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        sa, sb = cross_team_orders["stations"]["a"], cross_team_orders["stations"]["b"]
        s.add_all([
            Device(sn="XT-V2G-A", name="A-V2G", code="XTV2GA",
                   type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE, station_id=sa.id),
            Device(sn="XT-V2G-B", name="B-V2G", code="XTV2GB",
                   type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE, station_id=sb.id),
        ])
        s.commit()
        r = client.get("/api/v1/reports/v2g", headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["device_count"] == 1

    def test_admin_v2g_report_all(self, client, cross_team_orders):
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        sa, sb = cross_team_orders["stations"]["a"], cross_team_orders["stations"]["b"]
        s.add_all([
            Device(sn="XT-V2G-A2", name="A-V2G", code="XTV2GA2",
                   type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE, station_id=sa.id),
            Device(sn="XT-V2G-B2", name="B-V2G", code="XTV2GB2",
                   type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE, station_id=sb.id),
        ])
        s.commit()
        r = client.get("/api/v1/reports/v2g", headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["device_count"] == 2

    def test_anon_utilization_401(self, anon_client):
        assert anon_client.get("/api/v1/reports/utilization").status_code == 401


# ─── v2g.py 团队归属校验（device→station→team）───
# 任务卡 e1f0e6d5（四批）：dispatch 写 / history 读 / active 列表。

@pytest.fixture(scope="function")
def cross_team_v2g(client, cross_team_orders):
    """四批：在 cross_team_orders 基础上，两站各挂一台 V2G_CHARGER，供 v2g 越权回归。
    返回 cross_team_orders 全部键 + v2g_devices。"""
    from app.models.device import Device, DeviceType, DeviceStatus
    s = client._sesh
    sa, sb = cross_team_orders["stations"]["a"], cross_team_orders["stations"]["b"]
    va = Device(sn="XT-V2GQA-A", name="A-V2G桩", code="XTV2QA",
                type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE, station_id=sa.id)
    vb = Device(sn="XT-V2GQA-B", name="B-V2G桩", code="XTV2QB",
                type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE, station_id=sb.id)
    s.add_all([va, vb]); s.commit(); s.refresh(va); s.refresh(vb)
    return {**cross_team_orders, "v2g_devices": {"a": va, "b": vb}}


class TestV2GTeamScoping:
    """V2G 调度按 device→station→team 归属；跨团队读/写 → 404；admin 豁免。"""

    def test_user_cannot_dispatch_other_team_device(self, client, cross_team_v2g):
        """A 对 B 的 V2G 桩下发调度 → 404（先于类型校验，不泄露存在）。"""
        r = client.post(
            f"/api/v1/devices/{cross_team_v2g['v2g_devices']['b'].id}/v2g/dispatch",
            json={"dispatch_type": "charge", "target_power_kw": 10},
            headers=_h(cross_team_v2g["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_dispatch_own_v2g_device(self, client, cross_team_v2g):
        """A 对本 team V2G 桩下发调度 → 200（负向 404 的正向对照）。"""
        r = client.post(
            f"/api/v1/devices/{cross_team_v2g['v2g_devices']['a'].id}/v2g/dispatch",
            json={"dispatch_type": "charge", "target_power_kw": 10},
            headers=_h(cross_team_v2g["tokens"]["a"]))
        assert r.status_code == 200

    def test_admin_dispatch_any_v2g_device(self, client, cross_team_v2g):
        r = client.post(
            f"/api/v1/devices/{cross_team_v2g['v2g_devices']['b'].id}/v2g/dispatch",
            json={"dispatch_type": "discharge", "target_power_kw": 5},
            headers=_h(cross_team_v2g["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_read_other_team_history(self, client, cross_team_v2g):
        """A 读 B 设备 V2G 调度历史 → 404。"""
        r = client.get(
            f"/api/v1/devices/{cross_team_v2g['v2g_devices']['b'].id}/v2g/dispatch/history",
            headers=_h(cross_team_v2g["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_reads_own_history(self, client, cross_team_v2g):
        r = client.get(
            f"/api/v1/devices/{cross_team_v2g['v2g_devices']['a'].id}/v2g/dispatch/history",
            headers=_h(cross_team_v2g["tokens"]["a"]))
        assert r.status_code == 200

    def test_admin_reads_any_history(self, client, cross_team_v2g):
        r = client.get(
            f"/api/v1/devices/{cross_team_v2g['v2g_devices']['b'].id}/v2g/dispatch/history",
            headers=_h(cross_team_v2g["tokens"]["admin"]))
        assert r.status_code == 200

    def test_active_list_filters_by_team(self, client, cross_team_v2g):
        """两 team 各造一条 pending 调度，A 的 active 列表只见本 team（1 条）。"""
        from app.models.v2g_dispatch import V2GDispatchLog
        from datetime import datetime, timezone
        s = client._sesh
        va, vb = cross_team_v2g["v2g_devices"]["a"], cross_team_v2g["v2g_devices"]["b"]
        now = datetime.now(timezone.utc)
        s.add_all([
            V2GDispatchLog(device_id=va.id, dispatch_type="charge",
                           target_power_kw=10, actual_power_kw=0, status="pending", start_at=now),
            V2GDispatchLog(device_id=vb.id, dispatch_type="discharge",
                           target_power_kw=5, actual_power_kw=0, status="pending", start_at=now),
        ])
        s.commit()
        r = client.get("/api/v1/devices/v2g/dispatch/active",
                       headers=_h(cross_team_v2g["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1
        assert r.json()["data"]["items"][0]["device_id"] == va.id

    def test_admin_active_list_all(self, client, cross_team_v2g):
        from app.models.v2g_dispatch import V2GDispatchLog
        from datetime import datetime, timezone
        s = client._sesh
        va, vb = cross_team_v2g["v2g_devices"]["a"], cross_team_v2g["v2g_devices"]["b"]
        now = datetime.now(timezone.utc)
        s.add_all([
            V2GDispatchLog(device_id=va.id, dispatch_type="charge",
                           target_power_kw=10, actual_power_kw=0, status="pending", start_at=now),
            V2GDispatchLog(device_id=vb.id, dispatch_type="discharge",
                           target_power_kw=5, actual_power_kw=0, status="pending", start_at=now),
        ])
        s.commit()
        r = client.get("/api/v1/devices/v2g/dispatch/active",
                       headers=_h(cross_team_v2g["tokens"]["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2


# ─── telemetry.py 团队归属校验（device/station→team；网关上报豁免）───
# 任务卡 e1f0e6d5（四批）：latest/history/stats/overview/simulate 五读端点。
# 网关（X-API-Key）属 M2M 上报，豁免 team scoping；仅用户态 caller 做归属校验。

class TestTelemetryTeamScoping:
    """遥测读端点按 device/station→team 归属；跨团队 → 404；网关上报豁免。"""

    def test_user_reads_own_device_latest(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['a'].id}/latest",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_read_other_team_latest(self, client, cross_team_orders):
        """A 读 B 设备最新遥测 → 404。"""
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['b'].id}/latest",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_reads_any_latest(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['b'].id}/latest",
                       headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_reads_own_device_history(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['a'].id}/history",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_read_other_team_history(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['b'].id}/history",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_reads_own_device_stats(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['a'].id}/stats",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_read_other_team_stats(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/device/{cross_team_orders['devices']['b'].id}/stats",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_reads_own_station_overview(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/station/{cross_team_orders['stations']['a'].id}/overview",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_read_other_team_station_overview(self, client, cross_team_orders):
        """A 读 B 站点遥测概览 → 404。"""
        r = client.get(f"/api/v1/telemetry/station/{cross_team_orders['stations']['b'].id}/overview",
                       headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_reads_any_station_overview(self, client, cross_team_orders):
        r = client.get(f"/api/v1/telemetry/station/{cross_team_orders['stations']['b'].id}/overview",
                       headers=_h(cross_team_orders["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_simulates_own_device(self, client, cross_team_orders):
        """A 为本 team 设备生成模拟遥测 → 200（负向 404 的正向对照）。"""
        r = client.post(
            f"/api/v1/telemetry/device/{cross_team_orders['devices']['a'].id}/simulate?hours=1&interval_seconds=3600",
            headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_simulate_other_team_device(self, client, cross_team_orders):
        """A 为 B 设备生成模拟遥测 → 404（不泄露存在）。"""
        r = client.post(
            f"/api/v1/telemetry/device/{cross_team_orders['devices']['b'].id}/simulate?hours=1&interval_seconds=3600",
            headers=_h(cross_team_orders["tokens"]["a"]))
        assert r.status_code == 404


# ─── charging_queue.py 团队归属校验（queue/rule 经 station→team）───
# 任务卡 e1f0e6d5（四批）：queue 4 端点 + rule 4 端点，全端点首次注入认证。

@pytest.fixture(scope="function")
def cross_team_queue(client, cross_team_orders):
    """四批：在 cross_team_orders 基础上，两 team 各加 enterprise/2vehicle/queue/rule，
    供 charging_queue 越权回归。返回 cross_team_orders 全部键 + 以下种子。"""
    from app.models.enterprise import Enterprise
    from app.models.enterprise_vehicle import EnterpriseVehicle
    from app.models.charging_queue import ChargingQueue, ChargingQueueRule, ChargingQueueStatus
    from datetime import datetime

    s = client._sesh
    ta, tb = cross_team_orders["teams"]["a"], cross_team_orders["teams"]["b"]
    sa, sb = cross_team_orders["stations"]["a"], cross_team_orders["stations"]["b"]

    ea = Enterprise(name="XT企业A", code="XTEAQ1", owner_team_id=ta.id)
    eb = Enterprise(name="XT企业B", code="XTEBQ1", owner_team_id=tb.id)
    s.add_all([ea, eb]); s.commit(); s.refresh(ea); s.refresh(eb)

    va1 = EnterpriseVehicle(enterprise_id=ea.id, plate_number="XTAQ11", vin="XTVINAQ11")
    va2 = EnterpriseVehicle(enterprise_id=ea.id, plate_number="XTAQ12", vin="XTVINAQ12")
    vb1 = EnterpriseVehicle(enterprise_id=eb.id, plate_number="XTBQ11", vin="XTVINBQ11")
    vb2 = EnterpriseVehicle(enterprise_id=eb.id, plate_number="XTBQ12", vin="XTVINBQ12")
    s.add_all([va1, va2, vb1, vb2]); s.commit()
    for v in (va1, va2, vb1, vb2):
        s.refresh(v)

    now = datetime.now(timezone.utc)
    qa = ChargingQueue(station_id=sa.id, vehicle_id=va1.id, enterprise_id=ea.id,
                       status=ChargingQueueStatus.WAITING.value, arrival_time=now)
    qb = ChargingQueue(station_id=sb.id, vehicle_id=vb1.id, enterprise_id=eb.id,
                       status=ChargingQueueStatus.WAITING.value, arrival_time=now)
    s.add_all([qa, qb]); s.commit(); s.refresh(qa); s.refresh(qb)

    ra = ChargingQueueRule(enterprise_id=ea.id, station_id=sa.id, rule_name="A规则")
    rb = ChargingQueueRule(enterprise_id=eb.id, station_id=sb.id, rule_name="B规则")
    s.add_all([ra, rb]); s.commit(); s.refresh(ra); s.refresh(rb)

    return {**cross_team_orders,
            "enterprises": {"a": ea, "b": eb},
            "vehicles": {"a1": va1, "a2": va2, "b1": vb1, "b2": vb2},
            "queues": {"a": qa, "b": qb},
            "rules": {"a": ra, "b": rb}}


class TestChargingQueueTeamScoping:
    """充电队列/规则经 station→team 归属；跨团队读/写 → 404；admin 豁免。"""

    # ── queue ──

    def test_user_get_own_station_queue(self, client, cross_team_queue):
        r = client.get(f"/api/v1/fleet/charging/queue?station_id={cross_team_queue['stations']['a'].id}",
                       headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_team_station_queue(self, client, cross_team_queue):
        """A 拉 B 站点充电队列 → 404。"""
        r = client.get(f"/api/v1/fleet/charging/queue?station_id={cross_team_queue['stations']['b'].id}",
                       headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_get_any_station_queue(self, client, cross_team_queue):
        r = client.get(f"/api/v1/fleet/charging/queue?station_id={cross_team_queue['stations']['b'].id}",
                       headers=_h(cross_team_queue["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_enqueue_own_station(self, client, cross_team_queue):
        r = client.post("/api/v1/fleet/charging/queue/enqueue",
                        json={"station_id": cross_team_queue["stations"]["a"].id,
                              "vehicle_id": cross_team_queue["vehicles"]["a2"].id,
                              "enterprise_id": cross_team_queue["enterprises"]["a"].id},
                        headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_enqueue_other_team_station(self, client, cross_team_queue):
        """A 入队 B 站点 → 404。"""
        r = client.post("/api/v1/fleet/charging/queue/enqueue",
                        json={"station_id": cross_team_queue["stations"]["b"].id,
                              "vehicle_id": cross_team_queue["vehicles"]["a2"].id,
                              "enterprise_id": cross_team_queue["enterprises"]["a"].id},
                        headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_dequeue_own_queue(self, client, cross_team_queue):
        r = client.delete(f"/api/v1/fleet/charging/queue/{cross_team_queue['queues']['a'].id}/dequeue",
                          headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_dequeue_other_team_queue(self, client, cross_team_queue):
        """A 离队 B 的队列条目 → 404。"""
        r = client.delete(f"/api/v1/fleet/charging/queue/{cross_team_queue['queues']['b'].id}/dequeue",
                          headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_change_other_team_priority(self, client, cross_team_queue):
        """A 改 B 队列条目优先级 → 404。"""
        r = client.patch(f"/api/v1/fleet/charging/queue/{cross_team_queue['queues']['b'].id}/priority",
                         json={"priority": 1}, headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    # ── rules ──

    def test_user_lists_only_own_team_rules(self, client, cross_team_queue):
        """A 规则列表只见本 team，不见 B 的。"""
        r = client.get("/api/v1/fleet/charging/rules", headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]]
        assert cross_team_queue["rules"]["a"].id in ids
        assert cross_team_queue["rules"]["b"].id not in ids

    def test_admin_lists_all_rules(self, client, cross_team_queue):
        r = client.get("/api/v1/fleet/charging/rules", headers=_h(cross_team_queue["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]]
        assert cross_team_queue["rules"]["a"].id in ids
        assert cross_team_queue["rules"]["b"].id in ids

    def test_user_create_own_rule(self, client, cross_team_queue):
        r = client.post("/api/v1/fleet/charging/rules",
                        json={"enterprise_id": cross_team_queue["enterprises"]["a"].id,
                              "station_id": cross_team_queue["stations"]["a"].id,
                              "rule_name": "A新规则"},
                        headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_create_rule_on_other_team_station(self, client, cross_team_queue):
        """A 用 B 站点建规则 → 404。"""
        r = client.post("/api/v1/fleet/charging/rules",
                        json={"enterprise_id": cross_team_queue["enterprises"]["a"].id,
                              "station_id": cross_team_queue["stations"]["b"].id,
                              "rule_name": "越权规则"},
                        headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_update_own_rule(self, client, cross_team_queue):
        r = client.put(f"/api/v1/fleet/charging/rules/{cross_team_queue['rules']['a'].id}",
                       json={"rule_name": "A改名"}, headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_update_other_team_rule(self, client, cross_team_queue):
        """A 改 B 规则 → 404。"""
        r = client.put(f"/api/v1/fleet/charging/rules/{cross_team_queue['rules']['b'].id}",
                       json={"rule_name": "被篡改"}, headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_rule(self, client, cross_team_queue):
        """A 删 B 规则 → 404。"""
        r = client.delete(f"/api/v1/fleet/charging/rules/{cross_team_queue['rules']['b'].id}",
                          headers=_h(cross_team_queue["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_rules_401(self, anon_client):
        assert anon_client.get("/api/v1/fleet/charging/rules").status_code == 401


# ─── 五批（任务卡 ab5c5f17）：diagnosis/fault/maintenance/fleet/carbon 越权回归 ───

@pytest.fixture(scope="function")
def cross_team_diag_fleet(client, cross_team_queue):
    """五批：在 cross_team_queue 基础上，两 team 各加 driver/maintenance/carbon 种子
    + operator 用户（fleet_vehicle_profiles 要求 admin/operator 角色，engineer → 403）。
    返回 cross_team_queue 全部键 + 以下种子 + operator tokens。"""
    from app.models.user import User, UserRole
    from app.models.fleet_driver import FleetDriver, LicenseType
    from app.models.maintenance_record import (
        MaintenanceRecord, MaintenanceType, MaintenanceStatus,
    )
    from app.models.carbon_emission import CarbonReductionRecord, CarbonReductionSummary
    from datetime import date
    from decimal import Decimal

    s = client._sesh
    ta, tb = cross_team_queue["teams"]["a"], cross_team_queue["teams"]["b"]
    ea, eb = cross_team_queue["enterprises"]["a"], cross_team_queue["enterprises"]["b"]
    da, db = cross_team_queue["devices"]["a"], cross_team_queue["devices"]["b"]
    va1, vb1 = cross_team_queue["vehicles"]["a1"], cross_team_queue["vehicles"]["b1"]
    sa, sb = cross_team_queue["stations"]["a"], cross_team_queue["stations"]["b"]

    # operator 用户（fleet_vehicle_profiles router 级 require_role admin/operator）
    pwd = "xt123456"
    opa = User(username="xt_op_a", real_name="A运维", role=UserRole.OPERATOR,
               team_id=ta.id, status="active",
               password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    opb = User(username="xt_op_b", real_name="B运维", role=UserRole.OPERATOR,
               team_id=tb.id, status="active",
               password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    s.add_all([opa, opb]); s.commit()

    fda = FleetDriver(enterprise_id=ea.id, name="A司机", phone="13800000001",
                      license_no="LICA001", license_type=LicenseType.C1)
    fdb = FleetDriver(enterprise_id=eb.id, name="B司机", phone="13800000002",
                      license_no="LICB001", license_type=LicenseType.C1)
    s.add_all([fda, fdb]); s.commit(); s.refresh(fda); s.refresh(fdb)

    mra = MaintenanceRecord(device_id=da.id, station_id=sa.id,
                            type=MaintenanceType.PREVENTIVE, status=MaintenanceStatus.PLANNED,
                            title="A维护")
    mrb = MaintenanceRecord(device_id=db.id, station_id=sb.id,
                            type=MaintenanceType.PREVENTIVE, status=MaintenanceStatus.PLANNED,
                            title="B维护")
    s.add_all([mra, mrb]); s.commit(); s.refresh(mra); s.refresh(mrb)

    cra = CarbonReductionRecord(vehicle_id=va1.id, enterprise_id=ea.id,
                                record_date=date(2026, 1, 15), charge_energy_kwh=Decimal("100"),
                                grid_factor=Decimal("0.5703"), fuel_factor=Decimal("1.211"),
                                carbon_reduction_kg=Decimal("64.07"),
                                equivalent_fuel_saved_liters=Decimal("56"))
    crb = CarbonReductionRecord(vehicle_id=vb1.id, enterprise_id=eb.id,
                                record_date=date(2026, 1, 15), charge_energy_kwh=Decimal("100"),
                                grid_factor=Decimal("0.5703"), fuel_factor=Decimal("1.211"),
                                carbon_reduction_kg=Decimal("64.07"),
                                equivalent_fuel_saved_liters=Decimal("56"))
    s.add_all([cra, crb]); s.commit()

    csa = CarbonReductionSummary(enterprise_id=ea.id, report_year=2026, report_month=1,
                                 total_charge_kwh=Decimal("100"), total_reduction_kg=Decimal("64.07"),
                                 total_fuel_saved_liters=Decimal("56"), vehicle_count=1, verified=False)
    csb = CarbonReductionSummary(enterprise_id=eb.id, report_year=2026, report_month=1,
                                 total_charge_kwh=Decimal("100"), total_reduction_kg=Decimal("64.07"),
                                 total_fuel_saved_liters=Decimal("56"), vehicle_count=1, verified=False)
    s.add_all([csa, csb]); s.commit(); s.refresh(csa); s.refresh(csb)

    def _tok(username, password):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        j = r.json()
        return j.get("data", {}).get("token") or j.get("token")

    return {**cross_team_queue,
            "drivers": {"a": fda, "b": fdb},
            "maintenance": {"a": mra, "b": mrb},
            "carbon_summaries": {"a": csa, "b": csb},
            "tokens": {**cross_team_queue["tokens"],
                       "op_a": _tok("xt_op_a", pwd),
                       "op_b": _tok("xt_op_b", pwd)}}


# ─── charging_schedule.py（enterprise→team）─────────────────────

class TestChargingScheduleTeamScoping:
    """智能充电调度经 enterprise→team 归属；跨团队读/写 → 404。"""

    def test_user_get_own_enterprise_current(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/charging/schedule/current?enterprise_id={t['enterprises']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_enterprise_current(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/charging/schedule/current?enterprise_id={t['enterprises']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_get_any_enterprise_current(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/charging/schedule/current?enterprise_id={t['enterprises']['b'].id}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_generate_other_enterprise(self, client, cross_team_diag_fleet):
        """A 为 B 企业生成调度 → 404（assert 先于业务）。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fleet/charging/schedule/generate",
                        json={"enterprise_id": t["enterprises"]["b"].id,
                              "vehicle_states": [{"vehicle_id": t["vehicles"]["a1"].id,
                                                  "current_soc": 0.2, "target_soc": 0.9,
                                                  "max_power_kw": 7.0}],
                              "available_power_kw": 50.0,
                              "time_window_start": "2026-01-15T10:00:00",
                              "time_window_end": "2026-01-15T18:00:00"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_schedule_401(self, anon_client):
        assert anon_client.get("/api/v1/fleet/charging/schedule/current?enterprise_id=1").status_code == 401


# ─── charging_strategy.py（station→team，指定站点时）──────────

class TestChargingStrategyTeamScoping:
    """充电策略指定站点时经 station→team 归属；跨团队 → 404。forecast/storage 无 station 维度，仅登录。"""

    def test_user_get_own_station_strategy(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/charging/strategy/current?station_id={t['stations']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_station_strategy(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/charging/strategy/current?station_id={t['stations']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_get_any_station_strategy(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/charging/strategy/current?station_id={t['stations']['b'].id}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_strategies_global_login_ok(self, client, cross_team_diag_fleet):
        """GET /charging/strategies 为平台级模式枚举，仅需登录。"""
        t = cross_team_diag_fleet
        r = client.get("/api/v1/charging/strategies", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_anon_strategy_401(self, anon_client):
        assert anon_client.get("/api/v1/charging/strategies").status_code == 401


# ─── diagnosis.py（device/station→team）────────────────────────

class TestDiagnosisTeamScoping:
    """智能诊断经 device/station→team 归属；跨团队 → 404。"""

    def test_user_diagnose_own_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/diagnosis/device",
                        json={"device_id": t["devices"]["a"].id},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_diagnose_other_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/diagnosis/device",
                        json={"device_id": t["devices"]["b"].id},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_diagnose_any_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/diagnosis/device",
                        json={"device_id": t["devices"]["b"].id},
                        headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_batch_other_station(self, client, cross_team_diag_fleet):
        """A 批量诊断 B 站点 → 404。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/diagnosis/batch",
                        json={"station_id": t["stations"]["b"].id},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_station_summary_own(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/diagnosis/station-summary/{t['stations']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_station_summary_other(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/diagnosis/station-summary/{t['stations']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_diagnosis_401(self, anon_client):
        assert anon_client.get("/api/v1/diagnosis/station-summary/1").status_code == 401


# ─── fault_diagnosis.py（alarm/device→team；init-fault-codes admin）───

class TestFaultDiagnosisTeamScoping:
    """故障诊断经 alarm→device→team 归属；跨团队 → 404；init-fault-codes 仅平台 admin。"""

    def test_user_alarm_diagnosis_own(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fault-diagnosis/alarm-diagnosis",
                        json={"alarm_id": t["alarms"]["a"].id},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_alarm_diagnosis_other(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fault-diagnosis/alarm-diagnosis",
                        json={"alarm_id": t["alarms"]["b"].id},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_alarm_diagnosis_any(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fault-diagnosis/alarm-diagnosis",
                        json={"alarm_id": t["alarms"]["b"].id},
                        headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_remote_fix_other(self, client, cross_team_diag_fleet):
        """A 远程修复 B 告警 → 404。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fault-diagnosis/remote-fix-attempt",
                        json={"alarm_id": t["alarms"]["b"].id, "fix_type": "reset"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_fault_codes_global_login_ok(self, client, cross_team_diag_fleet):
        """故障码为平台级知识库，仅需登录。"""
        t = cross_team_diag_fleet
        r = client.get("/api/v1/fault-diagnosis/fault-codes", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_init_fault_codes_admin_only(self, client, cross_team_diag_fleet):
        """初始化故障码库为平台级写操作，非 admin → 403。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fault-diagnosis/init-fault-codes",
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 403

    def test_anon_fault_diagnosis_401(self, anon_client):
        assert anon_client.get("/api/v1/fault-diagnosis/fault-codes").status_code == 401


# ─── smart_diagnosis.py（device→team）──────────────────────────

class TestSmartDiagnosisTeamScoping:
    """智能故障诊断经 device→team 归属；跨团队 → 404。"""

    def test_user_analyze_own_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/smart-diagnosis/analyze",
                        json={"device_id": t["devices"]["a"].id, "fault_desc": "异常噪音"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_analyze_other_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/smart-diagnosis/analyze",
                        json={"device_id": t["devices"]["b"].id, "fault_desc": "异常噪音"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_analyze_any_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/smart-diagnosis/analyze",
                        json={"device_id": t["devices"]["b"].id, "fault_desc": "异常噪音"},
                        headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_history_login_ok(self, client, cross_team_diag_fleet):
        """诊断历史按 team 过滤，仅需登录返回 200。"""
        t = cross_team_diag_fleet
        r = client.get("/api/v1/smart-diagnosis/history", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_anon_smart_diagnosis_401(self, anon_client):
        assert anon_client.get("/api/v1/smart-diagnosis/history").status_code == 401


# ─── health_monitor.py（device→team）───────────────────────────

class TestHealthMonitorTeamScoping:
    """健康度监控经 device→team 归属；跨团队 → 404。"""

    def test_user_trend_own_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/health/trend/{t['devices']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_trend_other_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/health/trend/{t['devices']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_trend_any_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/health/trend/{t['devices']['b'].id}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_calculate_other_device(self, client, cross_team_diag_fleet):
        """A 计算 B 设备健康度 → 404。"""
        t = cross_team_diag_fleet
        r = client.post(f"/api/v1/health/calculate/{t['devices']['b'].id}",
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_devices_list_login_ok(self, client, cross_team_diag_fleet):
        """健康设备列表按 team 过滤，仅需登录返回 200。"""
        t = cross_team_diag_fleet
        r = client.get("/api/v1/health/devices", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_anon_health_401(self, anon_client):
        assert anon_client.get("/api/v1/health/devices").status_code == 401


# ─── maintenance_records.py（device→team）──────────────────────

class TestMaintenanceRecordsTeamScoping:
    """维护记录经 device→team 归属；跨团队读/写 → 404；列表按 team 过滤。"""

    def test_user_list_filters_by_team(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get("/api/v1/maintenance-records", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["maintenance"]["a"].id in ids
        assert t["maintenance"]["b"].id not in ids

    def test_user_get_own_record(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/maintenance-records/{t['maintenance']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_record(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/maintenance-records/{t['maintenance']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_update_other_record(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.put(f"/api/v1/maintenance-records/{t['maintenance']['b'].id}",
                       json={"title": "被篡改"}, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_record(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.delete(f"/api/v1/maintenance-records/{t['maintenance']['b'].id}",
                          headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_create_own_device(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/maintenance-records",
                        json={"device_id": t["devices"]["a"].id, "title": "A新维护"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_create_other_device(self, client, cross_team_diag_fleet):
        """A 为 B 设备建维护记录 → 404。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/maintenance-records",
                        json={"device_id": t["devices"]["b"].id, "title": "越权维护"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_maintenance_401(self, anon_client):
        assert anon_client.get("/api/v1/maintenance-records").status_code == 401


# ─── enterprise_transactions.py（enterprise→team）──────────────

class TestEnterpriseTransactionsTeamScoping:
    """企业资金池交易经 enterprise→team 归属；跨团队读/写 → 404。"""

    def test_user_list_own_enterprise(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/enterprises/{t['enterprises']['a'].id}/transactions",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_list_other_enterprise(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/enterprises/{t['enterprises']['b'].id}/transactions",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_list_any_enterprise(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/enterprises/{t['enterprises']['b'].id}/transactions",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_create_other_enterprise(self, client, cross_team_diag_fleet):
        """A 为 B 企业创建交易 → 404。"""
        t = cross_team_diag_fleet
        r = client.post(f"/api/v1/enterprises/{t['enterprises']['b'].id}/transactions",
                        json={"type": "recharge", "amount": 100.0},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_transactions_401(self, anon_client):
        assert anon_client.get("/api/v1/enterprises/1/transactions").status_code == 401


# ─── enterprise_vehicles.py（enterprise→team）──────────────────

class TestEnterpriseVehiclesTeamScoping:
    """企业车辆经 enterprise→team 归属；跨团队读/绑定 → 404。"""

    def test_user_list_own_enterprise_vehicles(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/enterprises/{t['enterprises']['a'].id}/vehicles",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_list_other_enterprise_vehicles(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/enterprises/{t['enterprises']['b'].id}/vehicles",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_list_any_enterprise_vehicles(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/enterprises/{t['enterprises']['b'].id}/vehicles",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_bind_other_enterprise(self, client, cross_team_diag_fleet):
        """A 向 B 企业绑定车辆 → 404。"""
        t = cross_team_diag_fleet
        r = client.post(f"/api/v1/enterprises/{t['enterprises']['b'].id}/vehicles",
                        json={"plate_number": "XTTEST1", "vin": "XTVINCTEST0000AB1"},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_vehicles_401(self, anon_client):
        assert anon_client.get("/api/v1/enterprises/1/vehicles").status_code == 401


# ─── fleet_attendance.py（driver→enterprise→team）──────────────

class TestFleetAttendanceTeamScoping:
    """司机考勤经 driver→enterprise→team 归属；跨团队读/写 → 404。"""

    def test_user_batch_own_driver(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fleet/attendance/batch",
                        json={"driver_id": t["drivers"]["a"].id, "month": "2026-01",
                              "records": [{"date": "2026-01-15", "shift_type": "day",
                                           "hours": 8.0, "status": "normal"}]},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_batch_other_driver(self, client, cross_team_diag_fleet):
        """A 录入 B 司机考勤 → 404。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fleet/attendance/batch",
                        json={"driver_id": t["drivers"]["b"].id, "month": "2026-01",
                              "records": [{"date": "2026-01-15", "shift_type": "day",
                                           "hours": 8.0, "status": "normal"}]},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_summary_own_driver(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/attendance/summary?driver_id={t['drivers']['a'].id}&month=2026-01",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_summary_other_driver(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/attendance/summary?driver_id={t['drivers']['b'].id}&month=2026-01",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_summary_any_driver(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/attendance/summary?driver_id={t['drivers']['b'].id}&month=2026-01",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_anon_attendance_401(self, anon_client):
        assert anon_client.get("/api/v1/fleet/attendance/summary?driver_id=1&month=2026-01").status_code == 401


# ─── fleet_vehicle_profiles.py（vehicle→enterprise→team；operator 角色）───

class TestFleetVehicleProfilesTeamScoping:
    """车辆维保/保险档案经 vehicle→enterprise→team 归属；跨团队 → 404。
    router 级 require_role(admin/operator)，故用 operator token 验证团队级隔离。"""

    def test_op_list_own_vehicle_maintenance(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/vehicles/{t['vehicles']['a1'].id}/maintenance",
                       headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 200

    def test_op_cannot_list_other_vehicle_maintenance(self, client, cross_team_diag_fleet):
        """A 运维查 B 车辆维保 → 404。"""
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/vehicles/{t['vehicles']['b1'].id}/maintenance",
                       headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 404

    def test_op_profile_own_vehicle(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/vehicles/{t['vehicles']['a1'].id}/profile",
                       headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 200

    def test_op_cannot_profile_other_vehicle(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/vehicles/{t['vehicles']['b1'].id}/profile",
                       headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 404

    def test_admin_profile_any_vehicle(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/vehicles/{t['vehicles']['b1'].id}/profile",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_anon_profiles_401(self, anon_client):
        assert anon_client.get("/api/v1/fleet/vehicles/1/profile").status_code == 401


# ─── carbon_emission.py（enterprise/vehicle→team；factors 平台级）───

class TestCarbonEmissionTeamScoping:
    """碳减排经 enterprise/vehicle→team 归属；跨团队 → 404；排放因子平台级（写仅 admin）。"""

    def test_user_overview_own_enterprise(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/carbon/overview?enterprise_id={t['enterprises']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_overview_other_enterprise(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/carbon/overview?enterprise_id={t['enterprises']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_overview_any_enterprise(self, client, cross_team_diag_fleet):
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/carbon/overview?enterprise_id={t['enterprises']['b'].id}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_details_other_enterprise(self, client, cross_team_diag_fleet):
        """A 查 B 企业碳明细 → 404。"""
        t = cross_team_diag_fleet
        r = client.get(f"/api/v1/fleet/carbon/details?enterprise_id={t['enterprises']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_calculate_other_vehicle(self, client, cross_team_diag_fleet):
        """A 为 B 车辆计算减排 → 404。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fleet/carbon/calculate",
                        json={"vehicle_id": t["vehicles"]["b1"].id,
                              "record_date": "2026-01-15", "charge_energy_kwh": 50.0},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_verify_other_report(self, client, cross_team_diag_fleet):
        """A 审核 B 企业碳报告 → 404。"""
        t = cross_team_diag_fleet
        r = client.post(f"/api/v1/fleet/carbon/reports/{t['carbon_summaries']['b'].id}/verify",
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_factors_list_login_ok(self, client, cross_team_diag_fleet):
        """排放因子为平台级知识库，仅需登录。"""
        t = cross_team_diag_fleet
        r = client.get("/api/v1/fleet/carbon/factors", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_create_factor_admin_only(self, client, cross_team_diag_fleet):
        """创建排放因子为平台级写操作，非 admin → 403。"""
        t = cross_team_diag_fleet
        r = client.post("/api/v1/fleet/carbon/factors",
                        json={"year": 2026, "region": "全国",
                              "factor_type": "grid", "emission_factor": 0.5703},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 403

    def test_anon_carbon_401(self, anon_client):
        assert anon_client.get("/api/v1/fleet/carbon/factors").status_code == 401


# ═══════════════════════════════════════════════════════════════════
# 五批下半（任务卡 ab5c5f17）：operate 11 域 team scoping 越权回归
# 订单/财务/营收/日结 经 station→team；用户/券流水/积分流水/抬头/企业账单/充值申请
# 经 user|enterprise→team；券/折扣/积分规则/发票/对账/互联 写操作为平台级（require_platform_admin）。
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(scope="function")
def cross_team_operate(client, cross_team):
    """五批下半：在 cross_team 两站两用户基础上，各 team 种子 enterprise/PAID订单/
    coupon+usage/积分流水/发票抬头/日结/企业账单，供 operate 11 域越权回归。
    返回 cross_team 全部键 + users/enterprises/orders_paid/daily。"""
    from app.models.user import User
    from app.models.enterprise import Enterprise
    from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
    from app.models.coupon import Coupon, CouponUsage, CouponType, CouponStatus
    from app.models.points import PointsRecord, PointsRecordType
    from app.models.ops_settlement.invoice_title import InvoiceTitle, TitleType
    from app.models.ops_settlement.daily_settlement import DailySettlement, SettlementStatus
    from app.models.settlement.bill import FleetSettlementBill, BillStatus
    from datetime import datetime, date
    from decimal import Decimal

    s = client._sesh
    ta, tb = cross_team["teams"]["a"], cross_team["teams"]["b"]
    sa, sb = cross_team["stations"]["a"], cross_team["stations"]["b"]
    da, db = cross_team["devices"]["a"], cross_team["devices"]["b"]

    # cross_team 未直接返回 user ORM，按 username 取（用于 user→team 归属种子）
    ua = s.query(User).filter(User.username == "xt_eng_a").one()
    ub = s.query(User).filter(User.username == "xt_eng_b").one()

    ea = Enterprise(name="XT企业OPA", code="XTOPA1", owner_team_id=ta.id)
    eb = Enterprise(name="XT企业OPB", code="XTOPB1", owner_team_id=tb.id)
    s.add_all([ea, eb]); s.commit(); s.refresh(ea); s.refresh(eb)

    now = datetime.now(timezone.utc)
    oa = ChargingOrder(order_no="CO-OP-A-1", station_id=sa.id, device_id=da.id,
                       charged_kwh=10, paid_amount=Decimal("100.00"), created_at=now,
                       order_status=OrderStatus.COMPLETED, payment_status=OrderPaymentStatus.PAID)
    ob = ChargingOrder(order_no="CO-OP-B-1", station_id=sb.id, device_id=db.id,
                       charged_kwh=20, paid_amount=Decimal("200.00"), created_at=now,
                       order_status=OrderStatus.COMPLETED, payment_status=OrderPaymentStatus.PAID)
    s.add_all([oa, ob]); s.commit(); s.refresh(oa); s.refresh(ob)

    cpn = Coupon(name="XT券", coupon_type=CouponType.FIXED, face_value=Decimal("10"),
                 total_stock=100, remaining_stock=100, valid_days=30,
                 start_time=now, end_time=now, is_active=True)
    s.add(cpn); s.commit(); s.refresh(cpn)
    s.add_all([
        CouponUsage(coupon_id=cpn.id, user_id=ua.id, coupon_code="XTCPN-A-001",
                    status=CouponStatus.ACTIVE, expires_at=now),
        CouponUsage(coupon_id=cpn.id, user_id=ub.id, coupon_code="XTCPN-B-001",
                    status=CouponStatus.USED, discount_amount=Decimal("10"), expires_at=now),
    ]); s.commit()

    s.add_all([
        PointsRecord(user_id=ua.id, record_type=PointsRecordType.EARN, points=10, description="XT-PTS-A"),
        PointsRecord(user_id=ub.id, record_type=PointsRecordType.EARN, points=20, description="XT-PTS-B"),
    ]); s.commit()

    s.add_all([
        InvoiceTitle(user_id=ua.id, title_type=TitleType.PERSONAL, title_name="XT抬头A"),
        InvoiceTitle(user_id=ub.id, title_type=TitleType.PERSONAL, title_name="XT抬头B"),
    ]); s.commit()

    dsa = DailySettlement(settlement_date=date(2026, 7, 20), station_id=sa.id,
                          total_orders=1, total_amount=Decimal("100"),
                          status=SettlementStatus.PENDING, remark="XT-DS-A")
    dsb = DailySettlement(settlement_date=date(2026, 7, 20), station_id=sb.id,
                          total_orders=1, total_amount=Decimal("200"),
                          status=SettlementStatus.PENDING, remark="XT-DS-B")
    s.add_all([dsa, dsb]); s.commit(); s.refresh(dsa); s.refresh(dsb)

    s.add_all([
        FleetSettlementBill(bill_no="XT-BILL-A", enterprise_id=ea.id, bill_period="2026-07",
                            total_amount=Decimal("100"), status=BillStatus.PENDING),
        FleetSettlementBill(bill_no="XT-BILL-B", enterprise_id=eb.id, bill_period="2026-07",
                            total_amount=Decimal("200"), status=BillStatus.PENDING),
    ]); s.commit()

    return {**cross_team,
            "users": {"a": ua, "b": ub},
            "enterprises": {"a": ea, "b": eb},
            "orders_paid": {"a": oa, "b": ob},
            "daily": {"a": dsa, "b": dsb}}


# ─── orders.py（订单经 station→team）──────────────────────────────

class TestOperateOrdersTeamScoping:
    """运营订单经 station→team 归属；跨团队读 → 404；列表/站点查询按 team 过滤。"""

    def test_list_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/orders", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "CO-OP-A-1" in r.text and "CO-OP-B-1" not in r.text

    def test_admin_list_sees_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/orders", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "CO-OP-A-1" in r.text and "CO-OP-B-1" in r.text

    def test_user_get_own_order(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/orders/{t['orders_paid']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_team_order(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/orders/{t['orders_paid']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_get_any_order(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/orders/{t['orders_paid']['b'].id}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_curve_other_team_order(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/orders/{t['orders_paid']['b'].id}/charge-curve",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_query_other_team_station(self, client, cross_team_operate):
        """A 传 B station_id 查订单 → 404（不泄露站点存在）。"""
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/orders?station_id={t['stations']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_orders_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/orders").status_code == 401


# ─── financial.py（充电费等经 station→team）──────────────────────

class TestOperateFinancialTeamScoping:
    """财务管理经 station→team 归属；列表按 team 过滤；station_id 越权 → 404。"""

    def test_list_charges_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/financial/charges", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "CO-OP-A-1" in r.text and "CO-OP-B-1" not in r.text

    def test_admin_list_charges_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/financial/charges", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "CO-OP-B-1" in r.text

    def test_user_cannot_query_other_station_charges(self, client, cross_team_operate):
        """A 传 B station_id 查充电费 → 404。"""
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/financial/charges?station_id={t['stations']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_charges_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/financial/charges").status_code == 401


# ─── overview.py（站/桩/订单聚合经 station→team）─────────────────

class TestOperateOverviewTeamScoping:
    """运营概览聚合非 admin 仅统计本 team；admin 全量。"""

    def test_user_overview_own_team_only(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/overview", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ov = r.json()["data"]
        assert ov["station_count"] == 1
        assert ov["device_count"] == 1
        assert ov["total_revenue"] == 100.0  # 仅 oa_paid（本 team）

    def test_admin_overview_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/overview", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        ov = r.json()["data"]
        assert ov["station_count"] == 2
        assert ov["device_count"] == 2
        assert ov["total_revenue"] == 300.0  # oa + ob

    def test_anon_overview_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/overview").status_code == 401


# ─── users_api.py（用户经 user.team_id）──────────────────────────

class TestOperateUsersApiTeamScoping:
    """用户管理按 user.team_id 过滤；非 admin 仅本 team 用户。"""

    def test_list_users_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/users", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "xt_eng_a" in r.text and "xt_eng_b" not in r.text

    def test_admin_list_users_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/users", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "xt_eng_b" in r.text

    def test_user_stats_login_ok(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/users/stats", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_anon_users_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/users").status_code == 401


# ─── coupon_api.py（券流水 user→team；券本体/写 平台级）──────────

class TestOperateCouponApiTeamScoping:
    """券使用记录按 user→team 过滤；券本体读登录可见；写仅 platform admin。"""

    def test_usages_filter_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/coupon/usages", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "XTCPN-A-001" in r.text and "XTCPN-B-001" not in r.text

    def test_admin_usages_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/coupon/usages", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "XTCPN-B-001" in r.text

    def test_coupon_list_login_ok(self, client, cross_team_operate):
        """券本体为平台级配置，仅需登录可见。"""
        t = cross_team_operate
        r = client.get("/api/v1/operate/coupon", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_create_coupon_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"name": "X", "face_value": 1, "total_stock": 1,
                "start_time": "2026-01-01T00:00:00", "end_time": "2026-12-31T00:00:00"}
        assert client.post("/api/v1/operate/coupon", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403
        assert client.post("/api/v1/operate/coupon", json=body,
                           headers=_h(t["tokens"]["admin"])).status_code == 200

    def test_anon_coupon_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/coupon").status_code == 401


# ─── discount.py（折扣配置平台级：读登录/写 admin）───────────────

class TestOperateDiscountTeamScoping:
    """折扣为平台级配置，读登录可见，写仅 platform admin。"""

    def test_discount_list_login_ok(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/discount", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_create_discount_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"name": "X", "discount_rate": 0.1,
                "start_time": "2026-01-01T00:00:00", "end_time": "2026-12-31T00:00:00"}
        assert client.post("/api/v1/operate/discount", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403
        assert client.post("/api/v1/operate/discount", json=body,
                           headers=_h(t["tokens"]["admin"])).status_code == 200

    def test_anon_discount_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/discount").status_code == 401


# ─── points_api.py（积分流水 user→team；规则平台级写）────────────

class TestOperatePointsApiTeamScoping:
    """积分流水按 user→team 过滤；规则读写仅 platform admin。"""

    def test_records_filter_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/points/records", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "XT-PTS-A" in r.text and "XT-PTS-B" not in r.text

    def test_admin_records_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/points/records", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "XT-PTS-B" in r.text

    def test_create_rule_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"name": "X", "points": 1}
        assert client.post("/api/v1/operate/points", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403
        assert client.post("/api/v1/operate/points", json=body,
                           headers=_h(t["tokens"]["admin"])).status_code == 200

    def test_anon_points_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/points/records").status_code == 401


# ─── enterprise_recharge.py（充值申请 enterprise→team）───────────
# 注：GET /applications 非空时直接序列化 ORM 致 500（预存 bug，见
# test_operate_enterprise_recharge 文档），与本批 team scoping 无关、且修它需改响应
# 格式（任务禁止）。team 过滤代码已就位（enterprise join，同 fleet 模式）；
# 此处用「仅存他队申请 → 本队过滤后空列表 200」干净验证过滤生效，规避序列化 bug。

class TestOperateEnterpriseRechargeTeamScoping:
    """企业充值申请按 enterprise→team 过滤；他队申请对本队不可见。"""

    def test_user_list_excludes_other_team(self, client, cross_team):
        """仅存 team-B 申请时，A 列表过滤后为空（200, items=[]）。"""
        from app.models.enterprise import Enterprise
        from app.models.enterprise_recharge import RechargeApplication
        s = client._sesh
        eb = Enterprise(name="XT企业RCB", code="XTRCB1",
                        owner_team_id=cross_team["teams"]["b"].id)
        s.add(eb); s.commit(); s.refresh(eb)
        s.add(RechargeApplication(enterprise_id=eb.id, applicant="XT-RC-B")); s.commit()
        r = client.get("/api/v1/operate/recharge/applications",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["items"] == []

    def test_anon_applications_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/recharge/applications").status_code == 401


# ─── ops_invoice.py（抬头 user→team；发票本体平台级 admin）───────

class TestOperateOpsInvoiceTeamScoping:
    """发票抬头按 user→team 过滤；发票本体/写仅 platform admin。"""

    def test_titles_filter_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/invoices/titles", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "XT抬头A" in r.text and "XT抬头B" not in r.text

    def test_admin_titles_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/invoices/titles", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "XT抬头B" in r.text

    def test_invoices_list_admin_only(self, client, cross_team_operate):
        """发票本体为平台级，列表/写仅 admin：非 admin → 403。"""
        t = cross_team_operate
        assert client.get("/api/v1/operate/invoices",
                          headers=_h(t["tokens"]["a"])).status_code == 403
        assert client.get("/api/v1/operate/invoices",
                          headers=_h(t["tokens"]["admin"])).status_code == 200

    def test_create_invoice_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"title_name": "X", "amount": "10"}
        assert client.post("/api/v1/operate/invoices", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403
        assert client.post("/api/v1/operate/invoices", json=body,
                           headers=_h(t["tokens"]["admin"])).status_code == 200

    def test_anon_invoices_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/invoices/titles").status_code == 401


# ─── ops_settlement.py（日结 station→team；企业账单 enterprise→team；对账/互联平台级）───

class TestOperateOpsSettlementTeamScoping:
    """日结经 station→team；企业账单经 enterprise→team；对账/互联/生成写仅 admin。"""

    def test_daily_list_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/settlement/daily", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "XT-DS-A" in r.text and "XT-DS-B" not in r.text

    def test_admin_daily_list_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/settlement/daily", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "XT-DS-B" in r.text

    def test_user_get_own_daily(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/settlement/daily/{t['daily']['a'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_get_other_daily(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get(f"/api/v1/operate/settlement/daily/{t['daily']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_confirm_other_daily(self, client, cross_team_operate):
        """A 确认 B 站点日结 → 404（归属校验先于状态流转）。"""
        t = cross_team_operate
        r = client.put(f"/api/v1/operate/settlement/daily/{t['daily']['b'].id}/confirm",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_enterprise_list_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/settlement/enterprise", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "XT-BILL-A" in r.text and "XT-BILL-B" not in r.text

    def test_admin_enterprise_list_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/settlement/enterprise", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "XT-BILL-B" in r.text

    def test_generate_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"settlement_date": "2026-07-25"}
        assert client.post("/api/v1/operate/settlement/daily/generate", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403

    def test_reconciliation_create_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"settlement_date": "2026-07-20", "payment_channel": "im_b"}
        assert client.post("/api/v1/operate/settlement/reconciliation", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403

    def test_interconnect_create_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        body = {"platform_id": "p1", "start_date": "2026-07-01", "end_date": "2026-07-07"}
        assert client.post("/api/v1/operate/settlement/interconnect", json=body,
                           headers=_h(t["tokens"]["a"])).status_code == 403

    def test_anon_settlement_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/settlement/daily").status_code == 401


# ─── revenue_stats.py（营收经 station→team；聚合触发平台级）───────

class TestOperateRevenueStatsTeamScoping:
    """营收统计经 station→team；按站/汇总非 admin 仅本 team；聚合触发仅 admin。"""

    def test_by_station_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/revenue/by-station", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert "XT-A站" in r.text and "XT-B站" not in r.text

    def test_admin_by_station_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/operate/revenue/by-station", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert "XT-B站" in r.text

    def test_summary_filters_by_team(self, client, cross_team_operate):
        """A 营收概览只计本 team 订单实付（100），不见 B 的（200）。"""
        t = cross_team_operate
        ra = client.get("/api/v1/operate/revenue/summary", headers=_h(t["tokens"]["a"]))
        assert ra.status_code == 200
        assert ra.json()["data"]["total_revenue"] == 100.0
        rb = client.get("/api/v1/operate/revenue/summary", headers=_h(t["tokens"]["admin"]))
        assert rb.status_code == 200
        assert rb.json()["data"]["total_revenue"] == 300.0

    def test_aggregate_admin_only(self, client, cross_team_operate):
        t = cross_team_operate
        assert client.post("/api/v1/operate/revenue/aggregate",
                           headers=_h(t["tokens"]["a"])).status_code == 403

    def test_anon_revenue_401(self, anon_client):
        assert anon_client.get("/api/v1/operate/revenue/summary").status_code == 401


# ═══════════════════════════════════════════════════════════════════
# 六批（任务卡 1c19b59a）：顶层业务域 team scoping 扫尾
# station_vin_whitelist / parking / order_fees / knowledge / report_mgmt /
# predictive_maintenance / runbook / log_analysis / operations_analytics /
# ops_dashboard / notification_configs / runbook_approval
#
# 治理模式沿用前五批：
# - admin/super_admin 显式短路豁免（is_platform_admin）
# - 越权统一 404（不泄露资源存在）
# - scoping 校验置 try 块外（避免被 except 吞成 500）
# - NULL 外键视为平台级记录，仅 admin 可见
# - 复用 deps.py 现有 helper（assert_station/device/order/alarm_team_access）
# ═══════════════════════════════════════════════════════════════════


# ─── station_vin_whitelist.py（VIN 白名单经 station→team）───

class TestStationVinWhitelistTeamScoping:
    """场站 VIN 白名单经 station_id→team；跨团队读写 → 404。"""

    def test_user_lists_own_station_vin(self, client, cross_team):
        """A 列表本 team 站点 VIN 白名单 → 200（即便空列表）。"""
        r = client.get(f"/api/v1/stations/{cross_team['stations']['a'].id}/vin-whitelist",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_list_other_team_station_vin(self, client, cross_team):
        """A 读 B 站点 VIN 白名单 → 404（不泄露站点存在）。"""
        r = client.get(f"/api/v1/stations/{cross_team['stations']['b'].id}/vin-whitelist",
                       headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_lists_any_station_vin(self, client, cross_team):
        """admin 平台级，跨团队站点可见。"""
        r = client.get(f"/api/v1/stations/{cross_team['stations']['b'].id}/vin-whitelist",
                       headers=_h(cross_team["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_add_vin_to_other_team_station(self, client, cross_team):
        """A 向 B 站点添加 VIN → 404。"""
        body = {"vin": "LSGAB52L7DF000001", "enterprise_id": 1}
        r = client.post(f"/api/v1/stations/{cross_team['stations']['b'].id}/vin-whitelist",
                        json=body, headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_station_vin(self, client, cross_team):
        """A 删 B 站点 VIN → 404（站点越权先于 VIN 查找）。"""
        r = client.delete(
            f"/api/v1/stations/{cross_team['stations']['b'].id}/vin-whitelist/LSGAB52L7DF000002",
            headers=_h(cross_team["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_vin_401(self, anon_client):
        assert anon_client.get("/api/v1/stations/1/vin-whitelist").status_code == 401


# ─── order_fees.py（订单费用/退款经 order→station→team）───

class TestOrderFeesTeamScoping:
    """订单费用明细/退款经 order_id→station→team；跨团队 → 404。"""

    def test_user_lists_own_order_fee_items(self, client, cross_team_orders):
        t = cross_team_orders
        r = client.get(f"/api/v1/orders/{t['orders']['a'].id}/fee-items",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_cannot_list_other_team_order_fee_items(self, client, cross_team_orders):
        """A 查 B 订单费用明细 → 404。"""
        t = cross_team_orders
        r = client.get(f"/api/v1/orders/{t['orders']['b'].id}/fee-items",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_lists_any_order_fee_items(self, client, cross_team_orders):
        t = cross_team_orders
        r = client.get(f"/api/v1/orders/{t['orders']['b'].id}/fee-items",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_user_cannot_settle_other_team_order(self, client, cross_team_orders):
        """A 结算 B 订单 → 404。"""
        t = cross_team_orders
        body = {"peak_energy": 10, "peak_price": 1.0}
        r = client.post(f"/api/v1/orders/{t['orders']['b'].id}/settle",
                        json=body, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_fee_items_401(self, anon_client):
        assert anon_client.get("/api/v1/orders/1/fee-items").status_code == 401


# ─── parking.py（停车折扣经 station→team）───

@pytest.fixture(scope="function")
def cross_team_parking(client, cross_team):
    """六批：parking 折扣种子，各队站点一条。"""
    from app.models.parking import ParkingDiscount
    s = client._sesh
    sa, sb = cross_team["stations"]["a"], cross_team["stations"]["b"]
    pa = ParkingDiscount(station_id=sa.id, merchant_name="A商户",
                         discount_type="free_minutes", free_minutes=30, is_active=True)
    pb = ParkingDiscount(station_id=sb.id, merchant_name="B商户",
                         discount_type="percentage", is_active=True)
    s.add_all([pa, pb]); s.commit(); s.refresh(pa); s.refresh(pb)
    return {**cross_team, "discounts": {"a": pa, "b": pb}}


class TestParkingTeamScoping:
    """停车折扣经 station_id→team；跨团队读写 → 404。"""

    def test_user_lists_only_own_team_discounts(self, client, cross_team_parking):
        t = cross_team_parking
        r = client.get("/api/v1/parking/discounts", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["discounts"]["a"].id in ids
        assert t["discounts"]["b"].id not in ids

    def test_admin_lists_all_discounts(self, client, cross_team_parking):
        t = cross_team_parking
        r = client.get("/api/v1/parking/discounts", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["discounts"]["b"].id in ids

    def test_user_cannot_read_other_team_discount(self, client, cross_team_parking):
        """A 读 B 折扣详情 → 404。"""
        t = cross_team_parking
        r = client.get(f"/api/v1/parking/discounts/{t['discounts']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_create_on_other_team_station(self, client, cross_team_parking):
        """A 在 B 站点建折扣 → 404。"""
        t = cross_team_parking
        body = {"station_id": t["stations"]["b"].id, "discount_type": "free_minutes"}
        r = client.post("/api/v1/parking/discounts", json=body, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_discount(self, client, cross_team_parking):
        """A 删 B 折扣 → 404。"""
        t = cross_team_parking
        r = client.delete(f"/api/v1/parking/discounts/{t['discounts']['b'].id}",
                          headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_parking_401(self, anon_client):
        assert anon_client.get("/api/v1/parking/discounts").status_code == 401


# ─── knowledge.py（知识文章 team_id 直接归属，0=平台共享）───

@pytest.fixture(scope="function")
def cross_team_knowledge(client, cross_team):
    """六批：knowledge 种子——A专属/B专属/平台共享(team_id=0)各一篇。"""
    from app.models.knowledge import KnowledgeArticle
    s = client._sesh
    ta, tb = cross_team["teams"]["a"], cross_team["teams"]["b"]
    art_a = KnowledgeArticle(title="A专属文档", content="A企业内部内容", category="ops",
                             team_id=ta.id, published=True)
    art_b = KnowledgeArticle(title="B专属文档", content="B企业内部内容", category="ops",
                             team_id=tb.id, published=True)
    art_shared = KnowledgeArticle(title="平台共享文档", content="全平台可见", category="ops",
                                  team_id=0, published=True)
    s.add_all([art_a, art_b, art_shared]); s.commit()
    for x in (art_a, art_b, art_shared):
        s.refresh(x)
    return {**cross_team, "articles": {"a": art_a, "b": art_b, "shared": art_shared}}


class TestKnowledgeTeamScoping:
    """知识文章 team_id 直接归属：企业仅见本企业+平台共享(0)；跨企业 → 404。"""

    def test_user_lists_own_and_shared_only(self, client, cross_team_knowledge):
        """A 列表只见 A专属 + 共享，不见 B专属。"""
        t = cross_team_knowledge
        r = client.get("/api/v1/knowledge/articles", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["articles"]["a"].id in ids
        assert t["articles"]["shared"].id in ids
        assert t["articles"]["b"].id not in ids

    def test_admin_lists_all_articles(self, client, cross_team_knowledge):
        t = cross_team_knowledge
        r = client.get("/api/v1/knowledge/articles", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["articles"]["b"].id in ids

    def test_user_cannot_read_other_team_article(self, client, cross_team_knowledge):
        """A 读 B 专属文章 → 404。"""
        t = cross_team_knowledge
        r = client.get(f"/api/v1/knowledge/articles/{t['articles']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_can_read_shared_article(self, client, cross_team_knowledge):
        """共享文章(team_id=0) 全平台可见。"""
        t = cross_team_knowledge
        r = client.get(f"/api/v1/knowledge/articles/{t['articles']['shared'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_user_create_assigns_own_team(self, client, cross_team_knowledge):
        """A 创建文章默认归本 team（team_id=A.team_id），B 不可见。"""
        t = cross_team_knowledge
        body = {"title": "A新建文档", "content": "测试内容", "category": "ops"}
        r = client.post("/api/v1/knowledge/articles", json=body, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        la = client.get("/api/v1/knowledge/articles", headers=_h(t["tokens"]["a"]))
        assert any(it["title"] == "A新建文档" for it in la.json()["data"]["items"])
        lb = client.get("/api/v1/knowledge/articles", headers=_h(t["tokens"]["b"]))
        assert all(it["title"] != "A新建文档" for it in lb.json()["data"]["items"])

    def test_user_cannot_delete_other_team_article(self, client, cross_team_knowledge):
        """A 删 B 专属文章 → 404。"""
        t = cross_team_knowledge
        r = client.delete(f"/api/v1/knowledge/articles/{t['articles']['b'].id}",
                          headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_articles_401(self, anon_client):
        assert anon_client.get("/api/v1/knowledge/articles").status_code == 401


# ─── report_mgmt.py（报告经 station_id→team；raw SQL 表）───

@pytest.fixture(scope="function")
def cross_team_reports(client, cross_team):
    """六批：report_mgmt 种子，各队站点一条报告（表由 conftest 建）。"""
    from sqlalchemy import text
    s = client._sesh
    sa, sb = cross_team["stations"]["a"], cross_team["stations"]["b"]
    s.execute(text(
        "INSERT INTO report_mgmt (title, type, station_id, author, status, content) "
        "VALUES (:t,:ty,:sid,:a,:st,:c)"), [
        {"t": "A站报告", "ty": "daily", "sid": sa.id, "a": "A", "st": "published", "c": "{}"},
        {"t": "B站报告", "ty": "daily", "sid": sb.id, "a": "B", "st": "published", "c": "{}"},
    ])
    s.commit()
    ra = s.execute(text("SELECT id FROM report_mgmt WHERE station_id=:sid ORDER BY id DESC LIMIT 1"),
                   {"sid": sa.id}).first()
    rb = s.execute(text("SELECT id FROM report_mgmt WHERE station_id=:sid ORDER BY id DESC LIMIT 1"),
                   {"sid": sb.id}).first()
    return {**cross_team, "reports": {"a": ra[0], "b": rb[0]}}


class TestReportMgmtTeamScoping:
    """报告经 station_id→team；跨团队读写 → 404。"""

    def test_user_lists_only_own_team_reports(self, client, cross_team_reports):
        """A 列表只见本队报告，不见 B 的。"""
        t = cross_team_reports
        r = client.get("/api/v1/report-mgmt", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["reports"]["a"] in ids
        assert t["reports"]["b"] not in ids

    def test_admin_lists_all_reports(self, client, cross_team_reports):
        t = cross_team_reports
        r = client.get("/api/v1/report-mgmt", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["reports"]["b"] in ids

    def test_user_cannot_read_other_team_report(self, client, cross_team_reports):
        """A 读 B 报告详情 → 404。"""
        t = cross_team_reports
        r = client.get(f"/api/v1/report-mgmt/{t['reports']['b']}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_create_on_other_team_station(self, client, cross_team_reports):
        """A 在 B 站点建报告 → 404。"""
        t = cross_team_reports
        body = {"title": "越权报告", "type": "daily", "station_id": t["stations"]["b"].id,
                "author": "A", "status": "draft", "content": "{}"}
        r = client.post("/api/v1/report-mgmt", json=body, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_user_cannot_delete_other_team_report(self, client, cross_team_reports):
        """A 删 B 报告 → 404。"""
        t = cross_team_reports
        r = client.delete(f"/api/v1/report-mgmt/{t['reports']['b']}",
                          headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_list_reports_401(self, anon_client):
        assert anon_client.get("/api/v1/report-mgmt").status_code == 401


# ─── predictive_maintenance.py（device→station→team；operator 角色）───

@pytest.fixture(scope="function")
def cross_team_predictive(client, cross_team):
    """六批：cross_team 基础上加 operator 用户（predictive_maintenance router 级
    require_role admin/operator，engineer → 403）。复用 cross_team 的 devices 链路。
    username 用 xt_predop_* 避免与 cross_team_diag_fleet 的 xt_op_a 冲突。"""
    from app.models.user import User, UserRole
    s = client._sesh
    pwd = "xt123456"
    opa = User(username="xt_predop_a", real_name="A运维", role=UserRole.OPERATOR,
               team_id=cross_team["teams"]["a"].id, status="active",
               password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    opb = User(username="xt_predop_b", real_name="B运维", role=UserRole.OPERATOR,
               team_id=cross_team["teams"]["b"].id, status="active",
               password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode())
    s.add_all([opa, opb]); s.commit()

    def _tok(username, password):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        j = r.json()
        return j.get("data", {}).get("token") or j.get("token")

    cross_team["tokens"]["op_a"] = _tok("xt_predop_a", pwd)
    cross_team["tokens"]["op_b"] = _tok("xt_predop_b", pwd)
    return cross_team


class TestPredictiveMaintenanceTeamScoping:
    """预测性维护经 device→station→team 归属；跨团队预测/训练/读历史 → 404；
    dashboard 列表按 team 过滤；admin 平台级豁免。"""

    def test_user_cannot_predict_other_team_device(self, client, cross_team_predictive):
        """A 预测 B 设备 → 404（assert 先于 service/遥测查询）。"""
        t = cross_team_predictive
        r = client.post("/api/v1/predictive-maintenance/predict",
                        json={"device_id": t["devices"]["b"].id, "hours": 24},
                        headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 404

    def test_user_cannot_train_other_team_device(self, client, cross_team_predictive):
        """A 训练 B 设备模型 → 404。"""
        t = cross_team_predictive
        r = client.post("/api/v1/predictive-maintenance/train",
                        json={"device_id": t["devices"]["b"].id, "days": 30},
                        headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 404

    def test_user_cannot_read_other_team_device_history(self, client, cross_team_predictive):
        """A 查 B 设备预测历史 → 404。"""
        t = cross_team_predictive
        r = client.get(
            f"/api/v1/predictive-maintenance/device/{t['devices']['b'].id}/history",
            headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 404

    def test_user_reads_own_device_history(self, client, cross_team_predictive):
        """A 查本队设备历史 → 200。"""
        t = cross_team_predictive
        r = client.get(
            f"/api/v1/predictive-maintenance/device/{t['devices']['a'].id}/history",
            headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 200

    def test_admin_reads_any_device_history(self, client, cross_team_predictive):
        """admin 查 B 设备历史 → 200（平台级豁免）。"""
        t = cross_team_predictive
        r = client.get(
            f"/api/v1/predictive-maintenance/device/{t['devices']['b'].id}/history",
            headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_dashboard_filters_by_team(self, client, cross_team_predictive):
        """A dashboard 仅本队设备（total_devices==1，只见 da 不见 db）。"""
        t = cross_team_predictive
        r = client.get("/api/v1/predictive-maintenance/dashboard",
                       headers=_h(t["tokens"]["op_a"]))
        assert r.status_code == 200
        data = r.json()
        assert data["total_devices"] == 1
        pred_ids = [p["device_id"] for p in data.get("predictions", [])]
        assert t["devices"]["b"].id not in pred_ids

    def test_admin_dashboard_sees_all(self, client, cross_team_predictive):
        """admin dashboard 见全部设备（total_devices>=2）。"""
        t = cross_team_predictive
        r = client.get("/api/v1/predictive-maintenance/dashboard",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert r.json()["total_devices"] >= 2

    def test_anon_predictive_dashboard_401(self, anon_client):
        """匿名访问 dashboard → 401。"""
        assert anon_client.get("/api/v1/predictive-maintenance/dashboard").status_code == 401


# ─── ops_dashboard.py（station→team；全大屏可视化）───

class TestOpsDashboardTeamScoping:
    """运维大屏经 station→team 归属；非 admin 仅本队站点/设备/告警/工单。"""

    def test_topology_filters_by_team(self, client, cross_team):
        t = cross_team
        r = client.get("/api/v1/ops-dashboard/topology", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        sta_ids = [int(n["id"].split("-")[1]) for n in r.json()["nodes"]["stations"]]
        assert t["stations"]["a"].id in sta_ids
        assert t["stations"]["b"].id not in sta_ids

    def test_admin_topology_sees_all(self, client, cross_team):
        t = cross_team
        r = client.get("/api/v1/ops-dashboard/topology", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        sta_ids = [int(n["id"].split("-")[1]) for n in r.json()["nodes"]["stations"]]
        assert t["stations"]["b"].id in sta_ids

    def test_overview_stats_by_team(self, client, cross_team):
        t = cross_team
        r = client.get("/api/v1/ops-dashboard/overview", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["stats"]["stations"] == 1  # A 仅本队 1 站

    def test_event_stream_other_team_station_404(self, client, cross_team):
        """A 查 B 站点事件流 → 404。"""
        t = cross_team
        r = client.get(f"/api/v1/ops-dashboard/event-stream?station_id={t['stations']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_event_stream_filters_by_team(self, client, cross_team):
        t = cross_team
        r = client.get("/api/v1/ops-dashboard/event-stream", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        alarm_ids = [int(e["id"].split("-")[1]) for e in r.json()["events"] if e["type"] == "alarm"]
        assert t["alarms"]["b"].id not in alarm_ids

    def test_anon_dashboard_401(self, anon_client):
        assert anon_client.get("/api/v1/ops-dashboard/topology").status_code == 401


# ─── operations_analytics.py（ChargingOrder.station_id→team；6 大报表）───

class TestOperationsAnalyticsTeamScoping:
    """运营分析报表经 ChargingOrder.station_id→team；非 admin 仅本队订单/券。"""

    def test_revenue_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/analytics/revenue", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        assert r.json()["data"]["summary"]["total_orders"] == 1  # A 仅 oa

    def test_revenue_admin_sees_all(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/analytics/revenue", headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200
        assert r.json()["data"]["summary"]["total_orders"] >= 2

    def test_station_rank_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/analytics/station-rank", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [row["station_id"] for row in r.json()["data"]["ranking"]]
        assert t["stations"]["a"].id in ids
        assert t["stations"]["b"].id not in ids

    def test_coupon_effect_filters_by_team(self, client, cross_team_operate):
        t = cross_team_operate
        r = client.get("/api/v1/analytics/coupon-effect", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        # A 仅本队领取人(ua)的券
        assert r.json()["data"]["summary"]["total_coupons_issued"] == 1

    def test_anon_analytics_401(self, anon_client):
        assert anon_client.get("/api/v1/analytics/revenue").status_code == 401


# ─── runbook.py（alarm/station→team；自动化执行）───

@pytest.fixture(scope="function")
def cross_team_runbook(client, cross_team):
    """六批：cross_team 基础上各队建一条 RunbookExecutionRecord（执行记录经 station→team）。
    注意：cross_team 自带的 executions 是 HealingExecution（自愈记录，不同表），
    runbook 的 list/get_execution 查的是 RunbookExecutionRecord，故需单独种子。"""
    from app.models.runbook_execution import RunbookExecutionRecord
    from datetime import datetime
    s = client._sesh
    ra = RunbookExecutionRecord(runbook_id="RB-EXEC-A", alarm_id=cross_team["alarms"]["a"].id,
                                device_id=cross_team["devices"]["a"].id,
                                station_id=cross_team["stations"]["a"].id,
                                fault_type="over_temp", status="completed",
                                steps_json=[], start_time=datetime.now(timezone.utc))
    rb = RunbookExecutionRecord(runbook_id="RB-EXEC-B", alarm_id=cross_team["alarms"]["b"].id,
                                device_id=cross_team["devices"]["b"].id,
                                station_id=cross_team["stations"]["b"].id,
                                fault_type="comm_fault", status="completed",
                                steps_json=[], start_time=datetime.now(timezone.utc))
    s.add_all([ra, rb]); s.commit(); s.refresh(ra); s.refresh(rb)
    return {**cross_team, "rb_executions": {"a": ra.id, "b": rb.id}}


class TestRunbookTeamScoping:
    """Runbook 经 alarm/station→team；跨团队执行/读记录 → 404/列表过滤。"""

    def test_execute_other_team_alarm_404(self, client, cross_team):
        """A 执行 B 告警 runbook → 404（assert 先于 service）。"""
        t = cross_team
        r = client.post(f"/api/v1/runbook/execute/{t['alarms']['b'].id}?dry_run=true",
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_list_executions_filters_by_team(self, client, cross_team_runbook):
        t = cross_team_runbook
        r = client.get("/api/v1/runbook/executions", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["rb_executions"]["a"] in ids
        assert t["rb_executions"]["b"] not in ids

    def test_get_other_team_execution_404(self, client, cross_team_runbook):
        t = cross_team_runbook
        r = client.get(f"/api/v1/runbook/executions/{t['rb_executions']['b']}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_get_any_execution(self, client, cross_team_runbook):
        """admin 读 B 执行记录 → 200（平台级豁免）。"""
        t = cross_team_runbook
        r = client.get(f"/api/v1/runbook/executions/{t['rb_executions']['b']}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_anon_runbook_401(self, anon_client):
        assert anon_client.get("/api/v1/runbook/executions").status_code == 401


# ─── log_analysis.py（device/alarm→team；AI 诊断）───

class TestLogAnalysisTeamScoping:
    """日志分析经 device/alarm→team；跨团队分析/读诊断 → 404（assert 先于 AI service）。"""

    def test_analyze_other_team_device_404(self, client, cross_team):
        """A 分析 B 设备 → 404（assert 先于 AI service）。"""
        t = cross_team
        r = client.post("/api/v1/log-analysis/analyze",
                        json={"device_id": t["devices"]["b"].id, "logs": ["err"]},
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_get_alarm_analysis_other_team_404(self, client, cross_team):
        t = cross_team
        r = client.get(f"/api/v1/log-analysis/alarm/{t['alarms']['b'].id}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_trigger_other_team_alarm_404(self, client, cross_team):
        """A 触发 B 告警诊断 → 404（assert 先于 trigger_diagnosis）。"""
        t = cross_team
        r = client.post(f"/api/v1/log-analysis/trigger/{t['alarms']['b'].id}",
                        headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_admin_get_any_alarm_analysis(self, client, cross_team):
        """admin 查 B 告警诊断 → 200（has_diagnosis False 也算 200）。"""
        t = cross_team
        r = client.get(f"/api/v1/log-analysis/alarm/{t['alarms']['b'].id}",
                       headers=_h(t["tokens"]["admin"]))
        assert r.status_code == 200

    def test_anon_log_analysis_401(self, anon_client):
        assert anon_client.get("/api/v1/log-analysis").status_code == 401


# ─── notification_configs.py（scope_type=station→team；Config CRUD）───

@pytest.fixture(scope="function")
def cross_team_notif(client, cross_team):
    """六批：cross_team 基础上各队建一个 scope_type=station 的通知配置。"""
    from app.models.notification_config import NotificationConfig
    s = client._sesh
    ca = NotificationConfig(name="XT-A通知", scope_type="station",
                            scope_id=cross_team["stations"]["a"].id)
    cb = NotificationConfig(name="XT-B通知", scope_type="station",
                            scope_id=cross_team["stations"]["b"].id)
    s.add_all([ca, cb]); s.commit(); s.refresh(ca); s.refresh(cb)
    return {**cross_team, "notif_configs": {"a": ca.id, "b": cb.id}}


class TestNotificationConfigsTeamScoping:
    """通知配置经 scope(station)→team；跨团队 CRUD station 配置 → 404/列表过滤；
    Template 全局豁免。"""

    def test_list_filters_by_team(self, client, cross_team_notif):
        t = cross_team_notif
        r = client.get("/api/v1/notification-configs", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["data"]]
        assert t["notif_configs"]["a"] in ids
        assert t["notif_configs"]["b"] not in ids

    def test_get_other_team_station_config_404(self, client, cross_team_notif):
        t = cross_team_notif
        r = client.get(f"/api/v1/notification-configs/{t['notif_configs']['b']}",
                       headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_create_on_other_team_station_404(self, client, cross_team_notif):
        t = cross_team_notif
        body = {"name": "越权", "scope_type": "station", "scope_id": t["stations"]["b"].id}
        r = client.post("/api/v1/notification-configs", json=body, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_delete_other_team_station_config_404(self, client, cross_team_notif):
        t = cross_team_notif
        r = client.delete(f"/api/v1/notification-configs/{t['notif_configs']['b']}",
                          headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_anon_notif_configs_401(self, anon_client):
        assert anon_client.get("/api/v1/notification-configs").status_code == 401


# ─── runbook_approval.py（approval→alarm→station→team；审批流）───

@pytest.fixture(scope="function")
def cross_team_approval(client, cross_team):
    """六批：cross_team 基础上各队建一个 pending RunbookApproval（关联本队 alarm，
    auto_execute=False 避免 approve 触发 subprocess）。"""
    from app.models.runbook_approval import RunbookApproval
    from datetime import datetime, timedelta
    s = client._sesh
    # 与端点 datetime.now()（本地 naive）保持同时区，避免被 expires_at>now 过滤误删。
    exp = datetime.now() + timedelta(hours=1)
    aa = RunbookApproval(runbook_id="RB-A-1", alarm_id=cross_team["alarms"]["a"].id,
                         step_index=0, step_description="A步骤", action_type="ssh",
                         command_preview="echo A", risk_level="medium",
                         status="pending", required_level="operator",
                         auto_execute_after_approval=False, expires_at=exp)
    ab = RunbookApproval(runbook_id="RB-B-1", alarm_id=cross_team["alarms"]["b"].id,
                         step_index=0, step_description="B步骤", action_type="ssh",
                         command_preview="echo B", risk_level="medium",
                         status="pending", required_level="operator",
                         auto_execute_after_approval=False, expires_at=exp)
    s.add_all([aa, ab]); s.commit(); s.refresh(aa); s.refresh(ab)
    return {**cross_team, "approvals": {"a": aa.id, "b": ab.id}}


class TestRunbookApprovalTeamScoping:
    """审批经 approval→alarm→station→team；跨团队 approve/reject → 404/列表过滤。"""

    def test_list_pending_filters_by_team(self, client, cross_team_approval):
        t = cross_team_approval
        r = client.get("/api/v1/runbook/approvals/pending", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert t["approvals"]["a"] in ids
        assert t["approvals"]["b"] not in ids

    def test_approve_other_team_404(self, client, cross_team_approval):
        """A approve B 审批 → can_approve 通过(ENGINEER≥operator) → team 校验 404。"""
        t = cross_team_approval
        r = client.post(f"/api/v1/runbook/approvals/{t['approvals']['b']}/approve",
                        json={"comment": "越权"}, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_reject_other_team_404(self, client, cross_team_approval):
        t = cross_team_approval
        r = client.post(f"/api/v1/runbook/approvals/{t['approvals']['b']}/reject",
                        json={"reason": "越权"}, headers=_h(t["tokens"]["a"]))
        assert r.status_code == 404

    def test_stats_filters_by_team(self, client, cross_team_approval):
        t = cross_team_approval
        r = client.get("/api/v1/runbook/approvals/stats", headers=_h(t["tokens"]["a"]))
        assert r.status_code == 200

    def test_anon_approval_401(self, anon_client):
        assert anon_client.get("/api/v1/runbook/approvals/pending").status_code == 401
