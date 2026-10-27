"""设备详情读取 + 更新 API 测试 (工作卡 be1f5eb4)

覆盖 app/api/v1/devices/crud.py (挂 /api/v1 前缀 + router prefix /devices):
- GET  /devices/{device_id}    设备详情 (含最近5条维护记录 + 入网/维护计划字段)
- PUT  /devices/{device_id}    更新 (name / status / rated_power)

权限门: router-level require_write_permission("device:edit"):
  - GET 仅认证 (读放行); PUT 需 device:edit, admin 恒通过, viewer/auditor → 403, 匿名 → 401。
team scoping: device 经 station.team_id 归属; admin 平台级豁免, 跨 team → 404 (不泄露存在)。
"""
import uuid

import bcrypt
import pytest

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.maintenance_record import (
    MaintenanceRecord, MaintenanceType, MaintenanceStatus,
)
from app.models.station import Station
from app.models.user import User, UserRole, Team

URL = "/api/v1/devices"


# ─── helpers ───

def _add_user(session, username, role, team_id=None, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, team_id=None, suffix=None):
    sx = suffix or uuid.uuid4().hex[:6]
    st = Station(name=f"电站{sx}", code=f"ST{sx}", team_id=team_id)
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_device(session, station_id, *, name="测试桩", dev_type=DeviceType.CHARGER_DC,
                 status=DeviceStatus.ONLINE, rated_power=120.0, code=None, sn=None):
    sx = uuid.uuid4().hex[:8]
    d = Device(
        sn=sn or f"SN-{sx}",
        name=name,
        code=code or f"DEV{sx}",
        type=dev_type,
        station_id=station_id,
        status=status,
        rated_power=rated_power,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def _seed_maint(session, device_id, *, title="例行保养", status=MaintenanceStatus.COMPLETED,
                mtype=MaintenanceType.PREVENTIVE, cost=100.0):
    m = MaintenanceRecord(
        device_id=device_id,
        type=mtype,
        status=status,
        title=title,
        cost=cost,
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


# ═══════════════════════════════════════════════════════════════
# 1. 详情 GET
# ═══════════════════════════════════════════════════════════════

class TestGetDevice:
    def test_get_basic_fields(self, client):
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, name="A桩", rated_power=150.0)
        r = client.get(f"{URL}/{d.id}")
        assert r.status_code == 200, r.text[:300]
        body = r.json()["data"]
        assert body["id"] == d.id
        assert body["name"] == "A桩"
        assert body["sn"] == d.sn
        assert body["station_id"] == st.id
        assert body["status"] == "online"
        assert body["rated_power"] == 150.0
        assert body["type"] == "charger_dc"

    def test_get_includes_provision_and_maintenance_plan(self, client):
        """详情暴露 provision_status / 维护计划字段 (b26e8e60 §3)。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id)
        r = client.get(f"{URL}/{d.id}")
        body = r.json()["data"]
        for key in (
            "provision_status", "charge_box_id", "mqtt_username",
            "maintenance_interval_days", "last_maintenance", "next_maintenance",
            "maintenance_records", "maintenance_record_count",
        ):
            assert key in body, f"详情缺字段 {key}"
        assert body["maintenance_records"] == []
        assert body["maintenance_record_count"] == 0

    def test_get_with_maintenance_records(self, client):
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id)
        _seed_maint(s, d.id, title="保养1", status=MaintenanceStatus.COMPLETED)
        _seed_maint(s, d.id, title="保养2", status=MaintenanceStatus.PLANNED)
        r = client.get(f"{URL}/{d.id}")
        body = r.json()["data"]
        assert body["maintenance_record_count"] == 2
        titles = [rec["title"] for rec in body["maintenance_records"]]
        assert set(titles) == {"保养1", "保养2"}
        # 记录结构
        rec = body["maintenance_records"][0]
        assert "id" in rec and "type" in rec and "status" in rec and "cost" in rec

    def test_get_not_found_404(self, client):
        r = client.get(f"{URL}/999999")
        assert r.status_code == 404

    def test_get_cross_team_404(self, client):
        """非 admin team 用户 GET 跨 team 设备 → 404 (不泄露存在)。"""
        s = client._sesh
        # 两个 team + 各自 station/device
        ta = Team(name=f"团队A{uuid.uuid4().hex[:4]}", code=f"TA{uuid.uuid4().hex[:6]}")
        tb = Team(name=f"团队B{uuid.uuid4().hex[:4]}", code=f"TB{uuid.uuid4().hex[:6]}")
        s.add_all([ta, tb]); s.commit(); s.refresh(ta); s.refresh(tb)
        st_b = _seed_station(s, team_id=tb.id)
        dev_b = _seed_device(s, st_b.id)
        # A 队 viewer 登录
        viewer = _add_user(s, f"dev_v_{uuid.uuid4().hex[:6]}", UserRole.VIEWER, team_id=ta.id)
        tok = _login_token(client, viewer.username)
        r = client.get(f"{URL}/{dev_b.id}", headers=_auth(tok))
        assert r.status_code == 404

    def test_get_own_team_ok(self, client):
        """非 admin team 用户 GET 本 team 设备 → 200。"""
        s = client._sesh
        ta = Team(name=f"团队A{uuid.uuid4().hex[:4]}", code=f"TA{uuid.uuid4().hex[:6]}")
        s.add(ta); s.commit(); s.refresh(ta)
        st_a = _seed_station(s, team_id=ta.id)
        dev_a = _seed_device(s, st_a.id)
        viewer = _add_user(s, f"dev_v2_{uuid.uuid4().hex[:6]}", UserRole.VIEWER, team_id=ta.id)
        tok = _login_token(client, viewer.username)
        r = client.get(f"{URL}/{dev_a.id}", headers=_auth(tok))
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# 2. 更新 PUT
# ═══════════════════════════════════════════════════════════════

class TestUpdateDevice:
    def test_update_name(self, client):
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, name="旧名")
        r = client.put(f"{URL}/{d.id}", json={"name": "新名"})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["data"]["name"] == "新名"

    def test_update_status(self, client):
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, status=DeviceStatus.ONLINE)
        r = client.put(f"{URL}/{d.id}", json={"status": "fault"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "fault"

    def test_update_rated_power(self, client):
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, rated_power=60.0)
        r = client.put(f"{URL}/{d.id}", json={"rated_power": 250.5})
        assert r.status_code == 200
        assert r.json()["data"]["rated_power"] == 250.5

    def test_update_rated_power_zero(self, client):
        """rated_power=0 (is not None) 应被写入 (边界: if data.rated_power is not None)。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, rated_power=60.0)
        r = client.put(f"{URL}/{d.id}", json={"rated_power": 0})
        assert r.status_code == 200
        assert r.json()["data"]["rated_power"] == 0.0

    def test_update_empty_body_keeps_values(self, client):
        """PUT 传空更新 (所有字段 None) → 200 且不改动任何字段。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, name="原名", status=DeviceStatus.ONLINE, rated_power=90.0)
        r = client.put(f"{URL}/{d.id}", json={})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["name"] == "原名"
        assert body["status"] == "online"
        assert body["rated_power"] == 90.0

    def test_update_not_found_404(self, client):
        r = client.put(f"{URL}/999999", json={"name": "x"})
        assert r.status_code == 404

    def test_update_writes_audit_log(self, client):
        """PUT 成功后调用 audit_service.log_crud。"""
        from app.services.audit_service import audit_service
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id)
        called = {}
        orig = audit_service.log_crud
        audit_service.log_crud = lambda *a, **k: called.setdefault("ok", (a, k))
        try:
            client.put(f"{URL}/{d.id}", json={"name": "审计名"})
        finally:
            audit_service.log_crud = orig
        assert called.get("ok") is not None
        args = called["ok"][0]
        assert args[2] == "update" and args[3] == "devices" and args[4] == str(d.id)


# ═══════════════════════════════════════════════════════════════
# 3. 权限门 (router-level require_write_permission("device:edit"))
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    @pytest.fixture
    def viewer_token(self, client):
        h = uuid.uuid4().hex[:6]
        _add_user(client._sesh, f"dev_viewer_{h}", UserRole.VIEWER)
        return _login_token(client, f"dev_viewer_{h}")

    def test_viewer_get_ok(self, client, viewer_token):
        """GET 只读放行: viewer 仅认证即可读本 team 设备 (require_write_permission 对 GET 放行)。"""
        s = client._sesh
        # viewer 无 team_id (fixture 未设) → 把 station 也设为无 team 才会被豁免?
        # 否则: viewer.team_id=None 且 station 无 team → _check_device_team 走 tid is None → 404。
        # 故给 viewer 建一个 team 并把 station 归属之, 证明读端点只认证不查 device:edit。
        ta = Team(name=f"团队V{uuid.uuid4().hex[:4]}", code=f"TV{uuid.uuid4().hex[:6]}")
        s.add(ta); s.commit(); s.refresh(ta)
        st = _seed_station(s, team_id=ta.id)
        d = _seed_device(s, st.id)
        # 重新建一个归属该 team 的 viewer
        v = _add_user(s, f"dev_v_own_{uuid.uuid4().hex[:6]}", UserRole.VIEWER, team_id=ta.id)
        tok = _login_token(client, v.username)
        r = client.get(f"{URL}/{d.id}", headers=_auth(tok))
        assert r.status_code == 200

    def test_viewer_put_403(self, client, viewer_token):
        """viewer 无 device:edit → PUT 403 (router 级守卫在 body 解析前拦截)。"""
        r = client.put(f"{URL}/1", json={"name": "x"}, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_anonymous_401(self, anon_client):
        r = anon_client.get(f"{URL}/1")
        assert r.status_code == 401
