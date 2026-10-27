"""
app/api/v1/notification_configs.py 覆盖率补充测试（卡片 b1e258d2，60% → 100%）。

源码零改动。补齐既有 test_notification_configs.py 未触及的分支：
- Config CRUD：list 筛选/排序、update、delete、toggle、get 单条与 404
- Template CRUD：list 筛选、get/create/update/delete 与重复 code 400
- Logs 查询：event_type/channel/status 筛选 + 分页
- team scoping（任务卡 1c19b59a）：非 admin 用户的 _team_station_ids /
  _assert_config_scope_access / _assert_create_scope_access 各分支

fixture 风格参考 tests/test_notifications.py：用 conftest 的 ``client``（默认
注入 admin token），team scoping 场景通过 ``client._sesh`` 造 ENGINEER 用户与
站点/设备，登录拿 token 后以 per-request header 覆盖为该用户。
"""
import uuid

import bcrypt

from app.models.audit_log import AuditLog
from app.models.device import Device, DeviceType, DeviceStatus
from app.models.notification_config import NotificationLog
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

BASE = "/api/v1/notification-configs"


# ─── helpers ───

def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _create_user(sesh, role=UserRole.ENGINEER, team_id=None, password="eng123"):
    """造一个 active 用户绑定 team_id，返回 (user, username, password)。"""
    username = f"eng_{uuid.uuid4().hex[:8]}"
    u = User(
        username=username,
        password_hash=_hash(password),
        role=role,
        status="active",
        team_id=team_id,
    )
    sesh.add(u)
    sesh.commit()
    sesh.refresh(u)
    return u, username, password


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _make_station(sesh, team_id, code):
    st = Station(name=f"站{code}", code=code, team_id=team_id, status=StationStatus.NORMAL)
    sesh.add(st)
    sesh.commit()
    sesh.refresh(st)
    return st


def _make_device(sesh, station_id, sn):
    d = Device(
        sn=sn, name=f"设备{sn}", code=sn,
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=station_id,
    )
    sesh.add(d)
    sesh.commit()
    sesh.refresh(d)
    return d


def _create_config(client, **overrides):
    """以 admin（client 默认 token）建 config，返回响应 data。"""
    payload = {"name": f"cfg-{uuid.uuid4().hex[:6]}", "scope_type": "tenant"}
    payload.update(overrides)
    r = client.post(BASE, json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _patch_audit_to_test_db(client, monkeypatch):
    """让 audit_service 的 SessionLocal 指向当前测试库（与 client._sesh 同 engine），
    使 log_crud 真写库、可被 client._sesh 查到。

    client fixture 仅 override ``get_db`` 依赖、不覆盖模块级 ``SessionLocal``，
    而 audit_service.log_crud 不传 db 时走 ``SessionLocal()`` → 会写默认模板库，
    client._sesh 查不到且污染模板。此处 monkeypatch 修正（任务卡 5b22d9f7）。
    """
    from sqlalchemy.orm import sessionmaker

    from app.services import audit_service as audit_mod

    monkeypatch.setattr(
        audit_mod, "SessionLocal", sessionmaker(bind=client._sesh.get_bind())
    )


# ─── Config CRUD（admin 视角）───

class TestConfigCRUD:
    def test_list_empty(self, client):
        r = client.get(BASE)
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_list_filter_and_priority_order(self, client):
        _create_config(client, name="low", scope_type="tenant", priority=1)
        _create_config(client, name="high", scope_type="station", scope_id=999, priority=10)
        # scope_type 筛选
        r = client.get(BASE, params={"scope_type": "station"})
        names = [c["name"] for c in r.json()["data"]]
        assert names == ["high"]
        # scope_id 筛选
        r2 = client.get(BASE, params={"scope_id": 999})
        assert all(c["scope_id"] == 999 for c in r2.json()["data"])
        # 全量按 priority 降序
        allc = client.get(BASE).json()["data"]
        assert allc == sorted(allc, key=lambda c: c["priority"], reverse=True)

    def test_create_full_fields(self, client):
        r = client.post(BASE, json={
            "name": "全字段", "scope_type": "tenant",
            "sms_enabled": True, "email_enabled": True, "app_push_enabled": True,
            "im_b_enabled": True, "im_enabled": True,
            "receivers": ["a@x.com"], "receiver_roles": ["engineer"],
            "trigger_events": ["alarm_trigger"],
            "quiet_start": "22:00", "quiet_end": "07:00", "timezone": "UTC",
            "rate_limit_per_hour": 5, "rate_limit_per_day": 50,
            "enabled": True, "priority": 3,
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["sms_enabled"] is True
        assert d["im_enabled"] is True
        assert d["receivers"] == ["a@x.com"]
        assert d["trigger_events"] == ["alarm_trigger"]
        assert d["priority"] == 3

    def test_update_success(self, client):
        cfg = _create_config(client, name="待更新")
        r = client.put(f"{BASE}/{cfg['id']}", json={"name": "已更新", "enabled": False, "priority": 9})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "已更新"
        assert d["enabled"] is False
        assert d["priority"] == 9

    def test_update_not_found(self, client):
        assert client.put(f"{BASE}/99999", json={"name": "x"}).status_code == 404

    def test_delete_success(self, client):
        cfg = _create_config(client, name="待删除")
        r = client.delete(f"{BASE}/{cfg['id']}")
        assert r.status_code == 200
        assert "已删除" in r.json()["message"]
        assert client.get(f"{BASE}/{cfg['id']}").status_code == 404

    def test_delete_not_found(self, client):
        assert client.delete(f"{BASE}/99999").status_code == 404

    def test_toggle_success(self, client):
        cfg = _create_config(client, enabled=True)
        r1 = client.put(f"{BASE}/{cfg['id']}/toggle")
        assert r1.status_code == 200
        assert r1.json()["data"]["enabled"] is False
        r2 = client.put(f"{BASE}/{cfg['id']}/toggle")
        assert r2.json()["data"]["enabled"] is True

    def test_toggle_not_found(self, client):
        assert client.put(f"{BASE}/99999/toggle").status_code == 404

    def test_get_success(self, client):
        cfg = _create_config(client, name="单查")
        r = client.get(f"{BASE}/{cfg['id']}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == cfg["id"]

    def test_get_not_found(self, client):
        assert client.get(f"{BASE}/99999").status_code == 404


# ─── Template CRUD ───

class TestTemplateCRUD:
    def _create(self, client, code=None, channel="sms", event_type="alarm_trigger"):
        code = code or f"tpl_{uuid.uuid4().hex[:6]}"
        r = client.post(f"{BASE}/templates", json={
            "name": f"模板{code}", "code": code, "channel": channel,
            "event_type": event_type, "content": "hello {name}",
        })
        assert r.status_code == 200, r.text
        return r.json()["data"]

    def test_list_empty(self, client):
        r = client.get(f"{BASE}/templates")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_list_filter(self, client):
        self._create(client, channel="sms", event_type="alarm_trigger")
        self._create(client, channel="email", event_type="workorder_dispatch")
        r = client.get(f"{BASE}/templates", params={"channel": "sms"})
        assert all(t["channel"] == "sms" for t in r.json()["data"])
        r2 = client.get(f"{BASE}/templates", params={"event_type": "workorder_dispatch"})
        assert all(t["event_type"] == "workorder_dispatch" for t in r2.json()["data"])

    def test_get_success(self, client):
        t = self._create(client)
        r = client.get(f"{BASE}/templates/{t['id']}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == t["id"]

    def test_get_not_found(self, client):
        assert client.get(f"{BASE}/templates/99999").status_code == 404

    def test_create_success(self, client):
        t = self._create(client, code="unique_code_1")
        assert t["code"] == "unique_code_1"
        assert t["content"] == "hello {name}"

    def test_create_duplicate_code(self, client):
        self._create(client, code="dup_code")
        r = client.post(f"{BASE}/templates", json={
            "name": "重复", "code": "dup_code", "channel": "sms",
            "event_type": "alarm_trigger", "content": "x",
        })
        assert r.status_code == 400
        assert "dup_code" in r.json()["detail"]

    def test_update_success(self, client):
        t = self._create(client)
        r = client.put(f"{BASE}/templates/{t['id']}", json={"name": "改名", "enabled": False})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["name"] == "改名"
        assert d["enabled"] is False

    def test_update_not_found(self, client):
        assert client.put(f"{BASE}/templates/99999", json={"name": "x"}).status_code == 404

    def test_delete_success(self, client):
        t = self._create(client)
        r = client.delete(f"{BASE}/templates/{t['id']}")
        assert r.status_code == 200
        assert "已删除" in r.json()["message"]
        assert client.get(f"{BASE}/templates/{t['id']}").status_code == 404

    def test_delete_not_found(self, client):
        assert client.delete(f"{BASE}/templates/99999").status_code == 404

    def test_update_produces_audit_log(self, client, monkeypatch):
        """INFO-2: update_template 必须产生审计记录（任务卡 5b22d9f7）。"""
        _patch_audit_to_test_db(client, monkeypatch)
        t = self._create(client)
        r = client.put(f"{BASE}/templates/{t['id']}", json={"name": "改名", "enabled": False})
        assert r.status_code == 200
        logs = (
            client._sesh.query(AuditLog)
            .filter(AuditLog.module == "notification_templates", AuditLog.action == "update")
            .all()
        )
        assert any(log.target_id == str(t["id"]) for log in logs)

    def test_delete_produces_audit_log(self, client, monkeypatch):
        """INFO-2: delete_template 必须产生审计记录（任务卡 5b22d9f7）。"""
        _patch_audit_to_test_db(client, monkeypatch)
        t = self._create(client)
        r = client.delete(f"{BASE}/templates/{t['id']}")
        assert r.status_code == 200
        logs = (
            client._sesh.query(AuditLog)
            .filter(AuditLog.module == "notification_templates", AuditLog.action == "delete")
            .all()
        )
        assert any(log.target_id == str(t["id"]) for log in logs)


# ─── Logs 查询 ───

class TestLogs:
    def _make_log(self, sesh, event_type="alarm_trigger", channel="sms", status="sent"):
        log = NotificationLog(
            event_type=event_type, channel=channel, status=status,
            receiver_type="user", receiver_id="u1", content="c",
        )
        sesh.add(log)
        sesh.commit()
        sesh.refresh(log)
        return log

    def test_list_empty(self, client):
        r = client.get(f"{BASE}/logs")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["items"] == []

    def test_list_filters_and_pagination(self, client):
        s = client._sesh
        self._make_log(s, event_type="alarm_trigger", channel="sms", status="sent")
        self._make_log(s, event_type="alarm_trigger", channel="email", status="failed")
        self._make_log(s, event_type="workorder_dispatch", channel="sms", status="sent")
        # 全量
        assert client.get(f"{BASE}/logs").json()["data"]["total"] == 3
        # event_type 筛
        assert client.get(f"{BASE}/logs", params={"event_type": "alarm_trigger"}).json()["data"]["total"] == 2
        # channel 筛
        assert client.get(f"{BASE}/logs", params={"channel": "sms"}).json()["data"]["total"] == 2
        # status 筛
        assert client.get(f"{BASE}/logs", params={"status": "failed"}).json()["data"]["total"] == 1
        # 分页：page1 取 2 条，page2 取 1 条
        p1 = client.get(f"{BASE}/logs", params={"page": 1, "page_size": 2}).json()["data"]
        assert p1["total"] == 3 and len(p1["items"]) == 2
        p2 = client.get(f"{BASE}/logs", params={"page": 2, "page_size": 2}).json()["data"]
        assert len(p2["items"]) == 1


# ─── Team scoping（非 admin 分支，任务卡 1c19b59a）───

class TestTeamScoping:
    """非 admin（ENGINEER）用户的 team scoping 分支覆盖。"""

    def _seed_two_teams(self, client):
        """造 team 100（本 team：站+用户）与 team 200（跨 team：站+设备），返回种子数据 + ENGINEER token。"""
        s = client._sesh
        station_own = _make_station(s, team_id=100, code="OWN")
        station_other = _make_station(s, team_id=200, code="OTHER")
        device_other = _make_device(s, station_other.id, "SN-OTHER-1")
        _, uname, pw = _create_user(s, role=UserRole.ENGINEER, team_id=100)
        token = _login(client, uname, pw)
        return {
            "station_own": station_own, "station_other": station_other,
            "device_other": device_other, "token": token,
        }

    def test_list_filters_cross_team_station_config(self, client):
        seed = self._seed_two_teams(client)
        _create_config(client, name="own-station", scope_type="station", scope_id=seed["station_own"].id)
        _create_config(client, name="other-station", scope_type="station", scope_id=seed["station_other"].id)
        _create_config(client, name="tenant", scope_type="tenant")
        # ENGINEER(team=100)：本 team station + tenant 可见，跨 team station 被过滤
        names = {c["name"] for c in client.get(BASE, headers=_hdr(seed["token"])).json()["data"]}
        assert "own-station" in names
        assert "tenant" in names
        assert "other-station" not in names

    def test_list_filters_cross_team_device_config(self, client):
        """INFO-1: 非 admin 的 list 必须过滤跨 team 的 device scope config（任务卡 5b22d9f7）。
        device 归属经 device.station_id→station.team_id 判定，与 get/update/delete/toggle/
        create 的 _assert_config_scope_access 同源；旧实现仅过滤 station scope，device 全放行。"""
        s = client._sesh
        station_own = _make_station(s, team_id=100, code="OWN_DEV")
        station_other = _make_station(s, team_id=200, code="OTHER_DEV")
        device_own = _make_device(s, station_own.id, "SN-OWN-DEV")
        device_other = _make_device(s, station_other.id, "SN-OTHER-DEV")
        _, uname, pw = _create_user(s, role=UserRole.ENGINEER, team_id=100)
        token = _login(client, uname, pw)
        _create_config(client, name="own-device", scope_type="device", scope_id=device_own.id)
        _create_config(client, name="other-device", scope_type="device", scope_id=device_other.id)
        _create_config(client, name="tenant", scope_type="tenant")
        # ENGINEER(team=100)：本 team device + tenant 可见，跨 team device 被过滤
        names = {c["name"] for c in client.get(BASE, headers=_hdr(token)).json()["data"]}
        assert "own-device" in names
        assert "tenant" in names
        assert "other-device" not in names

    def test_list_no_team_stations_returns_placeholder(self, client):
        """本 team 无任何 station → _team_station_ids 返回 [0]，所有 station 配置被过滤。"""
        s = client._sesh
        st = _make_station(s, team_id=999, code="LONE")  # 属 team 999
        _, uname, pw = _create_user(s, role=UserRole.ENGINEER, team_id=100)  # 用户 team 100 无站
        token = _login(client, uname, pw)
        _create_config(client, name="station-999", scope_type="station", scope_id=st.id)
        _create_config(client, name="tenant-cfg", scope_type="tenant")
        names = {c["name"] for c in client.get(BASE, headers=_hdr(token)).json()["data"]}
        assert "tenant-cfg" in names
        assert "station-999" not in names

    def test_get_station_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        cfg = _create_config(client, scope_type="station", scope_id=seed["station_other"].id)
        assert client.get(f"{BASE}/{cfg['id']}", headers=_hdr(seed["token"])).status_code == 404

    def test_get_device_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        cfg = _create_config(client, scope_type="device", scope_id=seed["device_other"].id)
        assert client.get(f"{BASE}/{cfg['id']}", headers=_hdr(seed["token"])).status_code == 404

    def test_update_station_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        cfg = _create_config(client, scope_type="station", scope_id=seed["station_other"].id)
        r = client.put(f"{BASE}/{cfg['id']}", json={"name": "x"}, headers=_hdr(seed["token"]))
        assert r.status_code == 404

    def test_delete_station_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        cfg = _create_config(client, scope_type="station", scope_id=seed["station_other"].id)
        assert client.delete(f"{BASE}/{cfg['id']}", headers=_hdr(seed["token"])).status_code == 404

    def test_toggle_station_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        cfg = _create_config(client, scope_type="station", scope_id=seed["station_other"].id)
        assert client.put(f"{BASE}/{cfg['id']}/toggle", headers=_hdr(seed["token"])).status_code == 404

    def test_create_station_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        r = client.post(BASE, json={
            "name": "x", "scope_type": "station", "scope_id": seed["station_other"].id,
        }, headers=_hdr(seed["token"]))
        assert r.status_code == 404

    def test_create_device_config_cross_team_404(self, client):
        seed = self._seed_two_teams(client)
        r = client.post(BASE, json={
            "name": "x", "scope_type": "device", "scope_id": seed["device_other"].id,
        }, headers=_hdr(seed["token"]))
        assert r.status_code == 404

    def test_access_own_team_resources_ok(self, client):
        """非 admin 访问本 team station 配置（get/update/toggle/delete）与 tenant scope 创建均放行。"""
        seed = self._seed_two_teams(client)
        h = _hdr(seed["token"])
        own_id = seed["station_own"].id
        cfg = _create_config(client, name="own", scope_type="station", scope_id=own_id)
        assert client.get(f"{BASE}/{cfg['id']}", headers=h).status_code == 200
        assert client.put(f"{BASE}/{cfg['id']}", json={"name": "own2"}, headers=h).status_code == 200
        assert client.put(f"{BASE}/{cfg['id']}/toggle", headers=h).status_code == 200
        assert client.delete(f"{BASE}/{cfg['id']}", headers=h).status_code == 200
        # tenant scope：_assert_create_scope_access 不校验，非 admin 可建
        r = client.post(BASE, json={"name": "tenant-by-eng", "scope_type": "tenant"}, headers=h)
        assert r.status_code == 200


# ─── quiet_start/quiet_end 校验（卡 6259ac0d）───

class TestQuietTimeValidation:
    """HH:MM 格式 + 成对出现；坏值/单只 → 422，不入库。"""

    def test_create_bad_format_422(self, client):
        for bad in ("25:99", "abc", "0800", "8:00"):
            r = client.post(BASE, json={"name": "x", "scope_type": "tenant", "quiet_start": bad, "quiet_end": "09:00"})
            assert r.status_code == 422, bad

    def test_create_unpaired_422(self, client):
        r = client.post(BASE, json={"name": "x", "scope_type": "tenant", "quiet_start": "22:00"})
        assert r.status_code == 422
        r2 = client.post(BASE, json={"name": "x", "scope_type": "tenant", "quiet_end": "07:00"})
        assert r2.status_code == 422

    def test_create_valid_pair_ok(self, client):
        cfg = _create_config(client, quiet_start="22:00", quiet_end="07:00")
        assert cfg["quiet_start"] == "22:00"

    def test_update_bad_format_422(self, client):
        cfg = _create_config(client)
        r = client.put(f"{BASE}/{cfg['id']}", json={"quiet_start": "25:99", "quiet_end": "09:00"})
        assert r.status_code == 422

    def test_update_unpaired_422(self, client):
        cfg = _create_config(client)
        r = client.put(f"{BASE}/{cfg['id']}", json={"quiet_start": "22:00"})
        assert r.status_code == 422

    def test_update_valid_pair_ok(self, client):
        cfg = _create_config(client)
        r = client.put(f"{BASE}/{cfg['id']}", json={"quiet_start": "23:00", "quiet_end": "06:00"})
        assert r.status_code == 200
        assert r.json()["data"]["quiet_start"] == "23:00"
