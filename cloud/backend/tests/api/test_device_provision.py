"""建站加设备自助闭环 - 接入凭证与入网状态测试（任务卡 1256e7fa）

覆盖：
- create_device 未传 sn → 自动生成 TLLN-<station_code前4位>-<6位hex大写>
- 创建后返回接入凭证（charge_box_id/mqtt_username/mqtt_password/auth_token），
  provision_status=provisioning
- 新建设备默认 unprovisioned；凭证生成后转 provisioning
- 跨团队 create/update/delete → 404（不泄露存在，与现有 team scoping 契约一致）

实现侧约定（app/api/v1/devices/__init__.py create_device）：
- sn 缺省：TLLN-<code前4位大写>-<6位hex>；admin 无 station 时用 DEFAULT 站点(code=DEFAULT→DEFA)
- 凭证：charge_box_id=sn；mqtt_username=gw-<sn[:12]>；mqtt_password=token_urlsafe(24)；
  auth_token=token_urlsafe(16)
"""
import re

import pytest


def _token(client, username="admin", password="admin123"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login 失败: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_team(client, code="PV"):
    """构造团队级 ENGINEER + 本/他队站点（他队 team_id 指向不存在团队）。"""
    import bcrypt
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus

    s = client._sesh
    team = Team(name=f"团队{code}", code=f"T{code}")
    s.add(team)
    s.commit()
    s.refresh(team)

    st_own = Station(name="本队站", code=f"{code}OWN", status=StationStatus.NORMAL, team_id=team.id)
    st_other = Station(name="他队站", code=f"{code}OTH", status=StationStatus.NORMAL, team_id=999_222)
    s.add_all([st_own, st_other])
    s.commit()
    s.refresh(st_own)
    s.refresh(st_other)

    username = f"eng_{code}"
    s.add(User(
        username=username,
        password_hash=bcrypt.hashpw(b"eng123", bcrypt.gensalt()).decode(),
        role=UserRole.ENGINEER,
        team_id=team.id,
        status="active",
    ))
    s.commit()

    token = _token(client, username, "eng123")
    client.headers["Authorization"] = f"Bearer {token}"
    return {"token": token, "team_id": team.id, "station_own": st_own, "station_other": st_other}


# ════════════════════════════════════════════════════════════
# create_device：自动生成 sn + 接入凭证
# ════════════════════════════════════════════════════════════
class TestCreateDeviceProvision:
    def test_create_device_auto_gen_sn(self, client, seed_users):
        """未传 sn → 自动生成 TLLN-<code前4位>-<6位hex大写>。

        admin 无 station_id 走 DEFAULT 站点(code=DEFAULT→前4位 DEFA)。
        """
        token = _token(client)
        resp = client.post("/api/v1/devices", json={
            "code": "PV0001", "name": "光伏逆变器", "type": "pv_inverter",
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        sn = resp.json()["data"]["sn"]
        # TLLN-DEFA-<6位大写hex>
        assert re.fullmatch(r"TLLN-DEFA-[0-9A-F]{6}", sn), f"sn 格式错误: {sn}"

    def test_create_device_auto_gen_sn_uses_station_code(self, client, seed_users, seed_stations):
        """传 station_id 时，sn 前缀取该站点 code 前4位（STA001→STA0）。"""
        token = _token(client)
        sid = seed_stations["station_a"].id  # code=STA001
        resp = client.post("/api/v1/devices", json={
            "code": "DEV01", "name": "设备", "type": "charger_dc",
            "station_id": str(sid),
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        sn = resp.json()["data"]["sn"]
        assert re.fullmatch(r"TLLN-STA0-[0-9A-F]{6}", sn), f"sn 前缀应为 STA0: {sn}"

    def test_create_device_with_credentials(self, client, seed_users):
        """创建后返回接入凭证，provision_status=provisioning。"""
        token = _token(client)
        resp = client.post("/api/v1/devices", json={
            "code": "PV0002", "name": "凭证设备", "type": "pv_inverter",
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        cred = d["credentials"]
        sn = d["sn"]

        # charge_box_id 默认等于 sn
        assert cred["charge_box_id"] == sn
        # mqtt_username = gw-<sn[:12]>
        assert cred["mqtt_username"] == f"gw-{sn[:12]}"
        # password / token 非空且足够长（token_urlsafe(24)→32, token_urlsafe(16)→22）
        assert len(cred["mqtt_password"]) >= 30
        assert len(cred["auth_token"]) >= 20
        # 一次性返回标注
        assert "仅此" in resp.json()["message"] or "一次性" in resp.json().get("message", "")
        # provision_status
        assert d["provision_status"] == "provisioning"

    def test_device_provision_status_default_unprovisioned(self, client, seed_users, seed_stations):
        """新建设备（无凭证生成路径前的 ORM 默认）= unprovisioned。

        通过直接读 DB 验证 Device.provision_status 列默认值。
        """
        from app.models.device import Device, DeviceType, DeviceStatus, ProvisionStatus
        s = client._sesh
        dev = Device(
            sn="SN-RAW-DEF", name="裸设备", code="RAWDEF",
            type=DeviceType.METER, status=DeviceStatus.ONLINE,
            station_id=seed_stations["station_a"].id,
        )
        s.add(dev)
        s.commit()
        s.refresh(dev)
        assert dev.provision_status == ProvisionStatus.UNPROVISIONED

    def test_create_device_provisioning_persisted(self, client, seed_users):
        """凭证生成后 provision_status/provision 字段落库。"""
        from app.models.device import Device, ProvisionStatus
        token = _token(client)
        resp = client.post("/api/v1/devices", json={
            "code": "PV0003", "name": "落库校验", "type": "pv_inverter",
        }, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        dev_id = resp.json()["data"]["id"]

        s = client._sesh
        dev = s.query(Device).filter(Device.id == dev_id).first()
        assert dev is not None
        assert dev.provision_status == ProvisionStatus.PROVISIONING
        assert dev.charge_box_id == dev.sn
        assert dev.mqtt_username == f"gw-{dev.sn[:12]}"
        assert dev.mqtt_password
        assert dev.auth_token


# ════════════════════════════════════════════════════════════
# 跨团队隔离：create / update / delete
# ════════════════════════════════════════════════════════════
class TestDeviceProvisionCrossTeam:
    def test_create_device_cross_team_404(self, client, seed_users):
        info = _setup_team(client)
        resp = client.post("/api/v1/devices", json={
            "sn": "SN-XT", "code": "XT", "name": "跨队", "type": "charger_dc",
            "station_id": str(info["station_other"].id),
        }, headers=_auth(info["token"]))
        assert resp.status_code == 404, resp.text

    def test_update_device_cross_team_404(self, client, seed_users):
        from app.models.device import Device, DeviceType, DeviceStatus
        info = _setup_team(client)
        # 在他队站点建一台设备
        s = client._sesh
        dev = Device(
            sn="SN-XT-UPD", name="他队设备", code="XTUPD",
            type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
            station_id=info["station_other"].id,
        )
        s.add(dev); s.commit(); s.refresh(dev)
        # 团队级用户改他队设备 → 404
        resp = client.put(f"/api/v1/devices/{dev.id}", json={"name": "篡改"},
                          headers=_auth(info["token"]))
        assert resp.status_code == 404, resp.text

    def test_delete_device_cross_team_404(self, client, seed_users):
        from app.models.device import Device, DeviceType, DeviceStatus
        info = _setup_team(client)
        s = client._sesh
        dev = Device(
            sn="SN-XT-DEL", name="他队设备", code="XTDEL",
            type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
            station_id=info["station_other"].id,
        )
        s.add(dev); s.commit(); s.refresh(dev)
        resp = client.delete(f"/api/v1/devices/{dev.id}", headers=_auth(info["token"]))
        assert resp.status_code == 404, resp.text


# ════════════════════════════════════════════════════════════
# 入网状态可见：列表 + 详情接口
# ════════════════════════════════════════════════════════════
class TestProvisionStatusVisibility:
    def test_list_devices_exposes_provision_status(self, client, seed_users):
        """设备列表项含 provision_status（任务清单 §3 入网状态可见）。"""
        token = _token(client)
        client.post("/api/v1/devices", json={
            "code": "PV-LIST", "name": "列表入网", "type": "pv_inverter",
        }, headers=_auth(token))
        resp = client.get("/api/v1/devices", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        target = [i for i in items if i["code"] == "PV-LIST"]
        assert target, "未找到刚创建设备"
        assert target[0]["provision_status"] == "provisioning"

    def test_get_device_detail_exposes_provision_status(self, client, seed_users):
        """详情接口返回 provision_status + charge_box_id（接入标识可见，
        但 mqtt_password/auth_token 凭证明文不得在详情暴露）。"""
        token = _token(client)
        create = client.post("/api/v1/devices", json={
            "code": "PV-DET", "name": "详情入网", "type": "pv_inverter",
        }, headers=_auth(token))
        dev_id = create.json()["data"]["id"]

        resp = client.get(f"/api/v1/devices/{dev_id}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        # 入网状态可见
        assert d["provision_status"] == "provisioning"
        # charge_box_id 作为接入标识可见
        assert d["charge_box_id"] == d["sn"]
        # 凭证明文绝不回显（仅创建时一次性返回）
        assert "credentials" not in d
        assert "mqtt_password" not in d
        assert "auth_token" not in d


# ════════════════════════════════════════════════════════════
# 入网状态流转：provisioning → online（网关首次连接钩子）
# ════════════════════════════════════════════════════════════
class TestProvisionStatusTransition:
    def test_gateway_first_connect_promotes_to_online(self, client, seed_users):
        """端到端：create_device(provisioning) → 网关 mark_device_online → online。

        任务清单 §3「网关侧设备首次连接成功→置 online」。
        模拟设备带 charge_point_id=sn 走 OCPP connect 钩子，验证 DB 与
        列表/详情一致转 online。
        """
        from app.gateway.ocpp import mark_device_online

        token = _token(client)
        create = client.post("/api/v1/devices", json={
            "code": "PV-CONN", "name": "首次连接", "type": "charger_dc",
        }, headers=_auth(token))
        assert create.status_code == 200, create.text
        d = create.json()["data"]
        assert d["provision_status"] == "provisioning"

        # 设备带 sn（=charge_box_id）首次连接
        promoted = mark_device_online(d["sn"])
        assert promoted is True

        # DB 已转 online
        from app.models.device import Device, ProvisionStatus
        s = client._sesh
        dev = s.query(Device).filter(Device.id == d["id"]).first()
        assert dev.provision_status == ProvisionStatus.ONLINE

        # 详情接口可见 online
        detail = client.get(f"/api/v1/devices/{d['id']}", headers=_auth(token))
        assert detail.json()["data"]["provision_status"] == "online"

        # 列表项可见 online
        lst = client.get("/api/v1/devices", headers=_auth(token))
        target = [i for i in lst.json()["data"]["items"] if i["id"] == d["id"]]
        assert target and target[0]["provision_status"] == "online"

    def test_gateway_connect_idempotent_when_already_online(self, client, seed_users):
        """已 online 设备再次连接 → 幂等，不报错。"""
        from app.gateway.ocpp import mark_device_online
        from app.models.device import Device, ProvisionStatus

        token = _token(client)
        create = client.post("/api/v1/devices", json={
            "code": "PV-IDEM", "name": "幂等连接", "type": "charger_dc",
        }, headers=_auth(token))
        sn = create.json()["data"]["sn"]

        assert mark_device_online(sn) is True   # 首次 → online
        assert mark_device_online(sn) is True   # 再次 → 幂等仍是 True
        s = client._sesh
        dev = s.query(Device).filter(Device.sn == sn).first()
        assert dev.provision_status == ProvisionStatus.ONLINE
