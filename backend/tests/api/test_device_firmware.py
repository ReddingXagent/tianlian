"""设备固件升级 (OTA) API 测试 (卡 43b26421)

覆盖 app/api/v1/devices/firmware.py (挂 /api/v1 前缀 + router prefix /devices):
- GET  /devices/{id}/firmware          当前版本 + 可升级 released 固件列表
- POST /devices/{id}/firmware/upgrade  下发设备级升级任务 (DeviceUpgradeTask)
- GET  /devices/{id}/firmware/status   最近一条升级任务状态

权限门: router 级 require_write_permission("device:edit") —— 认证必须, 匿名 → 401。
team scoping: device 经 station.team_id 归属; admin 平台级豁免, 跨 team → 404。
"""
import uuid

import bcrypt

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.gateway import Firmware
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


def _seed_team(session, name="团队"):
    t = Team(name=f"{name}{uuid.uuid4().hex[:4]}", code=f"T{uuid.uuid4().hex[:8]}")
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def _seed_station(session, team_id=None):
    sx = uuid.uuid4().hex[:6]
    st = Station(name=f"电站{sx}", code=f"ST{sx}", team_id=team_id)
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_device(session, station_id, *, model="EAHI5-20K", firmware_version="1.0.0"):
    sx = uuid.uuid4().hex[:8]
    d = Device(
        sn=f"SN-{sx}",
        name=f"桩{sx}",
        code=f"DEV{sx}",
        type=DeviceType.CHARGER_DC,
        station_id=station_id,
        status=DeviceStatus.ONLINE,
        model=model,
        firmware_version=firmware_version,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def _seed_firmware(session, version, model="EAHI5-20K", status="released"):
    f = Firmware(version=version, model=model, status=status)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f


# ═══════════════════════════════════════════════════════════════
# 1. GET /{id}/firmware — 检查可升级版本
# ═══════════════════════════════════════════════════════════════

class TestCheckFirmware:
    def test_anon_401(self, anon_client):
        r = anon_client.get(f"{URL}/1/firmware")
        assert r.status_code == 401

    def test_check_own_team_released_list(self, client):
        """本团队 GET 200: 当前版本 + released 且 model 匹配的固件列表。"""
        s = client._sesh
        ta = _seed_team(s)
        st = _seed_station(s, team_id=ta.id)
        d = _seed_device(s, st.id, firmware_version="1.0.0")
        _seed_firmware(s, "1.1.0", model="EAHI5-20K", status="released")
        _seed_firmware(s, "1.2.0", model="EAHI5-20K", status="released")
        _seed_firmware(s, "0.9.0", model="EAHI5-20K", status="deprecated")  # 非 released 排除
        _seed_firmware(s, "9.9.9", model="OTHER-MODEL", status="released")  # model 不匹配排除
        viewer = _add_user(s, f"fw_v_{uuid.uuid4().hex[:6]}", UserRole.VIEWER, team_id=ta.id)
        tok = _login_token(client, viewer.username)
        r = client.get(f"{URL}/{d.id}/firmware", headers=_auth(tok))
        assert r.status_code == 200, r.text[:300]
        data = r.json()["data"]
        assert data["current_version"] == "1.0.0"
        versions = [u["version"] for u in data["upgrades"]]
        assert sorted(versions) == ["1.1.0", "1.2.0"]

    def test_check_admin_all_teams(self, client):
        """admin 平台级豁免: 任意团队设备可见。"""
        s = client._sesh
        tb = _seed_team(s, "他队")
        st = _seed_station(s, team_id=tb.id)
        d = _seed_device(s, st.id, firmware_version="2.0.0")
        r = client.get(f"{URL}/{d.id}/firmware")
        assert r.status_code == 200
        assert r.json()["data"]["current_version"] == "2.0.0"

    def test_check_cross_team_404(self, client):
        s = client._sesh
        ta, tb = _seed_team(s, "A"), _seed_team(s, "B")
        st_b = _seed_station(s, team_id=tb.id)
        d = _seed_device(s, st_b.id)
        viewer = _add_user(s, f"fw_x_{uuid.uuid4().hex[:6]}", UserRole.VIEWER, team_id=ta.id)
        tok = _login_token(client, viewer.username)
        r = client.get(f"{URL}/{d.id}/firmware", headers=_auth(tok))
        assert r.status_code == 404

    def test_check_device_not_found_404(self, client):
        r = client.get(f"{URL}/999999/firmware")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 2. POST /{id}/firmware/upgrade — 下发升级任务
# ═══════════════════════════════════════════════════════════════

class TestUpgradeFirmware:
    def test_anon_401(self, anon_client):
        r = anon_client.post(f"{URL}/1/firmware/upgrade", json={"target_version": "1.1.0"})
        assert r.status_code == 401

    def test_upgrade_valid_version_pending(self, client):
        """有效 released 版本 → 200, 任务落库 pending。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, firmware_version="1.0.0")
        _seed_firmware(s, "1.1.0", status="released")
        r = client.post(f"{URL}/{d.id}/firmware/upgrade", json={"target_version": "1.1.0"})
        assert r.status_code == 200, r.text[:300]
        data = r.json()["data"]
        assert data["device_id"] == d.id
        assert data["target_version"] == "1.1.0"
        assert data["status"] == "pending"
        assert data["progress"] == 0
        # 落库断言
        from app.models.device_upgrade_task import DeviceUpgradeTask
        task = s.query(DeviceUpgradeTask).filter(
            DeviceUpgradeTask.device_id == d.id).first()
        assert task is not None
        assert task.target_version == "1.1.0"
        assert task.status == "pending"

    def test_upgrade_empty_version_rejected(self, client):
        """target_version 非空校验 → 422。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id)
        r = client.post(f"{URL}/{d.id}/firmware/upgrade", json={"target_version": ""})
        assert r.status_code == 422

    def test_upgrade_invalid_version_rejected(self, client):
        """无对应 released 固件记录 → 拒。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, model="EAHI5-20K")
        _seed_firmware(s, "1.1.0", model="OTHER")  # model 不匹配
        r = client.post(f"{URL}/{d.id}/firmware/upgrade", json={"target_version": "1.1.0"})
        assert r.status_code == 400
        # 未落库
        from app.models.device_upgrade_task import DeviceUpgradeTask
        assert s.query(DeviceUpgradeTask).filter(
            DeviceUpgradeTask.device_id == d.id).count() == 0

    def test_upgrade_force_skips_validation_still_saved(self, client):
        """force=true 跳过版本匹配校验, 任务仍落库。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, model="EAHI5-20K")
        r = client.post(
            f"{URL}/{d.id}/firmware/upgrade",
            json={"target_version": "9.9.9-rc", "force": True},
        )
        assert r.status_code == 200, r.text[:300]
        from app.models.device_upgrade_task import DeviceUpgradeTask
        task = s.query(DeviceUpgradeTask).filter(
            DeviceUpgradeTask.device_id == d.id).first()
        assert task is not None
        assert task.target_version == "9.9.9-rc"
        assert bool(task.force) is True

    def test_upgrade_cross_team_404(self, client):
        s = client._sesh
        ta, tb = _seed_team(s, "A"), _seed_team(s, "B")
        st_b = _seed_station(s, team_id=tb.id)
        d = _seed_device(s, st_b.id)
        # engineer 持有 device:edit (通过 router 权限门), 才能测到 team scope 404;
        # viewer 会在权限门就被 403, 测不到本层
        eng = _add_user(s, f"fw_u_{uuid.uuid4().hex[:6]}", UserRole.ENGINEER, team_id=ta.id)
        tok = _login_token(client, eng.username)
        r = client.post(
            f"{URL}/{d.id}/firmware/upgrade",
            json={"target_version": "1.1.0"},
            headers=_auth(tok),
        )
        assert r.status_code == 404

    def test_upgrade_device_not_found_404(self, client):
        r = client.post(f"{URL}/999999/firmware/upgrade", json={"target_version": "1.1.0"})
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. GET /{id}/firmware/status — 最近任务状态
# ═══════════════════════════════════════════════════════════════

class TestFirmwareStatus:
    def test_anon_401(self, anon_client):
        r = anon_client.get(f"{URL}/1/firmware/status")
        assert r.status_code == 401

    def test_status_returns_latest_task(self, client):
        """多次升级后 status 返回最近一条。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id, firmware_version="1.0.0")
        for v in ("1.1.0", "1.2.0"):
            _seed_firmware(s, v, status="released")
            r = client.post(f"{URL}/{d.id}/firmware/upgrade", json={"target_version": v})
            assert r.status_code == 200
        r = client.get(f"{URL}/{d.id}/firmware/status")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["task"]["target_version"] == "1.2.0"
        assert data["task"]["status"] == "pending"
        assert data["device_id"] == d.id

    def test_status_no_task(self, client):
        """无任务 → 200, task 为 None。"""
        s = client._sesh
        st = _seed_station(s)
        d = _seed_device(s, st.id)
        r = client.get(f"{URL}/{d.id}/firmware/status")
        assert r.status_code == 200
        assert r.json()["data"]["task"] is None

    def test_status_cross_team_404(self, client):
        s = client._sesh
        ta, tb = _seed_team(s, "A"), _seed_team(s, "B")
        st_b = _seed_station(s, team_id=tb.id)
        d = _seed_device(s, st_b.id)
        viewer = _add_user(s, f"fw_s_{uuid.uuid4().hex[:6]}", UserRole.VIEWER, team_id=ta.id)
        tok = _login_token(client, viewer.username)
        r = client.get(f"{URL}/{d.id}/firmware/status", headers=_auth(tok))
        assert r.status_code == 404
