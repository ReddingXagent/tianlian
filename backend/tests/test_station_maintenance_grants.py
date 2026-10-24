"""运维分离架构 — 三权分离 (任务卡 00d7d49a)。

运营公司 (OPS_COMPANY) 可两种模式运维自家场站:
- 模式①: 运营+运维同一团队自运维 (默认, 现有 assert_station_team_access 已覆盖)
- 模式②: 仅运营, 把运维权授权给独立第三方运维团队 (MAINTENANCE_TEAM)

本卡新增:
1. StationMaintenanceGrant 授权表 (station ↔ maintenance_team, 带 scope/status)
2. POST/GET/DELETE /station-maintenance-grants + GET /stations/maintained
3. assert_maintenance_access: OPS_COMPANY 自运维 OR MAINTENANCE_TEAM 有 active grant
4. 设备控制端点改用 assert_maintenance_access (action=control)

越权一律 404 (不泄露存在), 与 deps.assert_*_team_access 同源。
"""
import pytest

from app.models.user import Team, TeamType, User, UserRole
from tests._test_helpers import _fast_hash  # 卡17354607: 复用进程级 bcrypt hash 缓存

# 化解 deps↔v1 循环导入 (同 test_multi_tenant_config.py)
import app.api.v1  # noqa: F401


# ─── 多租户脚手架 ───────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def maint_env(client, seed_devices):
    """构造两层组织 + 场站 + 设备 + 授权主体:

    - ops_team (ops_company): 拥有 station_a (seed_devices 的 STA001)
      └─ mt_team (maintenance_team, parent=ops_team): 第三方运维团队
    - mt_team2 (maintenance_team, 独立): 另一家运维团队 (用于测跨团队越权)

    ops_user (ENGINEER, ops_team) — 运营公司操作员
    mt_user  (ENGINEER, mt_team)  — 被授权运维团队成员
    mt_user2 (ENGINEER, mt_team2) — 未被授权的运维团队成员

    station_a.team_id = ops_team (运营公司自有)
    seed_devices['chg001'] 是挂在 station_a 的充电桩 (CHARGER_DC), 供控制端点测试。

    返回 dict: teams/users/tokens + station_a + device。
    """
    from app.models.station import Station

    s = client._sesh

    ops_team = Team(name="运营公司G", code="GOps1", type=TeamType.OPS_COMPANY, owner_subject_id=2001)
    mt_team = Team(name="运维团队G", code="GMt1", type=TeamType.MAINTENANCE_TEAM, owner_subject_id=2001)
    mt_team2 = Team(name="运维团队H", code="GMt2", type=TeamType.MAINTENANCE_TEAM, owner_subject_id=2002)
    s.add_all([ops_team, mt_team, mt_team2])
    s.commit()
    for t in (ops_team, mt_team, mt_team2):
        s.refresh(t)

    mt_team.parent_team_id = ops_team.id
    mt_team2.parent_team_id = ops_team.id  # 同挂一个运营公司下但未授权
    s.commit()

    # 把 seed_devices 的 station_a 归属 ops_team (运营公司自有, 非运维团队)
    station_a = s.query(Station).filter(Station.code == "STA001").first()
    station_a.team_id = ops_team.id
    s.commit()
    s.refresh(station_a)

    device = seed_devices["chg001"]  # CHARGER_DC, 挂 station_a

    pwd = "g123456"

    def _make_user(username, team):
        return User(
            username=username,
            real_name=username,
            role=UserRole.OPERATOR,  # 含 device:edit / maintenance:manage 写权限
            team_id=team.id,
            status="active",
            password_hash=_fast_hash(pwd),
        )

    ops_user = _make_user("g_ops_user", ops_team)
    mt_user = _make_user("g_mt_user", mt_team)
    mt_user2 = _make_user("g_mt_user2", mt_team2)
    s.add_all([ops_user, mt_user, mt_user2])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json().get("data", {}).get("token") or r.json().get("token")

    def _admin_tok():
        r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        return r.json().get("data", {}).get("token") or r.json().get("token")

    return {
        "teams": {"ops": ops_team, "mt": mt_team, "mt2": mt_team2},
        "users": {"ops": ops_user, "mt": mt_user, "mt2": mt_user2},
        "tokens": {"ops": _tok("g_ops_user"), "mt": _tok("g_mt_user"),
                   "mt2": _tok("g_mt_user2"), "admin": _admin_tok()},
        "station_a": station_a,
        "device": device,
        "pwd": pwd,
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _grant_payload(maint_env, scope="full", maintenance_team_id=None):
    """构造授权请求体。"""
    mt_id = maintenance_team_id if maintenance_team_id is not None else maint_env["teams"]["mt"].id
    return {
        "station_id": maint_env["station_a"].id,
        "maintenance_team_id": mt_id,
        "scope": scope,
        "remark": "测试授权",
    }


# ─── 1. 授权 (POST /station-maintenance-grants) ─────────────────────────────

class TestCreateGrant:
    def test_ops_company_can_grant_full(self, client, maint_env):
        """运营公司可向运维团队授予 full 权限。"""
        r = client.post("/api/v1/station-maintenance-grants",
                        json=_grant_payload(maint_env, "full"), headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["station_id"] == maint_env["station_a"].id
        assert data["maintenance_team_id"] == maint_env["teams"]["mt"].id
        assert data["scope"] == "full"
        assert data["status"] == "active"
        assert data["granted_by_team_id"] == maint_env["teams"]["ops"].id
        assert data["id"] is not None

    def test_maintenance_team_cannot_grant(self, client, maint_env):
        """运维团队不可发起授权 (仅 ops_company)。→ 403。"""
        r = client.post("/api/v1/station-maintenance-grants",
                        json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 403

    def test_cannot_grant_station_not_owned_by_team(self, client, maint_env):
        """运营公司不能授权不属于自己的场站。→ 404 (不泄露存在)。"""
        # 用 admin 先造一个不属于 ops_team 的场站
        from app.models.station import Station, StationStatus
        s = client._sesh
        other = Station(name="他人电站", code="STA_OTHER", status=StationStatus.NORMAL,
                        team_id=maint_env["teams"]["mt2"].id)
        s.add(other)
        s.commit()
        s.refresh(other)
        payload = {
            "station_id": other.id,
            "maintenance_team_id": maint_env["teams"]["mt"].id,
            "scope": "full",
        }
        r = client.post("/api/v1/station-maintenance-grants",
                        json=payload, headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code == 404

    def test_grant_target_must_be_maintenance_team(self, client, maint_env):
        """授权目标必须是 MAINTENANCE_TEAM 类型。→ 400。"""
        payload = {
            "station_id": maint_env["station_a"].id,
            "maintenance_team_id": maint_env["teams"]["mt2"].id,  # mt2 也是 maintenance_team, 合法
            "scope": "full",
        }
        r = client.post("/api/v1/station-maintenance-grants",
                        json=payload, headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code == 200  # mt2 是合法运维团队

    def test_duplicate_grant_rejected(self, client, maint_env):
        """同 (station, maintenance_team) 重复授权。→ 409。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.post("/api/v1/station-maintenance-grants",
                        json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code == 409


# ─── 2. 列表 (GET /station-maintenance-grants) ──────────────────────────────

class TestListGrants:
    def test_ops_sees_grants_they_issued(self, client, maint_env):
        """运营公司看自己发出的授权。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.get("/api/v1/station-maintenance-grants", headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["granted_by_team_id"] == maint_env["teams"]["ops"].id

    def test_mt_sees_grants_they_received(self, client, maint_env):
        """运维团队看自己被授予的授权。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.get("/api/v1/station-maintenance-grants", headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["maintenance_team_id"] == maint_env["teams"]["mt"].id

    def test_unauthorized_mt_sees_nothing(self, client, maint_env):
        """未被授权的运维团队 (mt2) 看不到授权。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.get("/api/v1/station-maintenance-grants", headers=_h(maint_env["tokens"]["mt2"]))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items == []


# ─── 3. 撤销 (DELETE /station-maintenance-grants/{id}) ───────────────────────

class TestRevokeGrant:
    def test_grantor_can_revoke(self, client, maint_env):
        """授权方可撤销。"""
        created = client.post("/api/v1/station-maintenance-grants",
                              json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        gid = created.json()["data"]["id"]
        r = client.delete(f"/api/v1/station-maintenance-grants/{gid}",
                          headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code == 200
        # 撤销后状态变 revoked
        listing = client.get("/api/v1/station-maintenance-grants",
                             headers=_h(maint_env["tokens"]["ops"])).json()["data"]["items"]
        assert listing[0]["status"] == "revoked"

    def test_maintenance_team_cannot_revoke(self, client, maint_env):
        """运维团队不能撤销自己被授予的权限。→ 404 (不泄露存在)。"""
        created = client.post("/api/v1/station-maintenance-grants",
                              json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        gid = created.json()["data"]["id"]
        r = client.delete(f"/api/v1/station-maintenance-grants/{gid}",
                          headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 404

    def test_access_lost_after_revoke(self, client, maint_env):
        """撤销后运维团队失去对该站设备的控制权。→ 404。"""
        created = client.post("/api/v1/station-maintenance-grants",
                              json=_grant_payload(maint_env, "full"),
                              headers=_h(maint_env["tokens"]["ops"]))
        gid = created.json()["data"]["id"]
        # 先撤销
        client.delete(f"/api/v1/station-maintenance-grants/{gid}",
                      headers=_h(maint_env["tokens"]["ops"]))
        # 再尝试控制 → 404
        r = client.post(f"/api/v1/devices/{maint_env['device'].id}/control",
                        json={"action": "restart", "reset_type": "soft"},
                        headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 404


# ─── 4. 运维视角 (GET /stations/maintained) ─────────────────────────────────

class TestMaintainedStations:
    def test_mt_sees_granted_stations(self, client, maint_env):
        """运维团队看到自己被授权的站点。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.get("/api/v1/stations/maintained", headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 200
        items = r.json()["data"]
        assert len(items) == 1
        assert items[0]["id"] == maint_env["station_a"].id

    def test_unauthorized_mt_sees_no_stations(self, client, maint_env):
        """未被授权的运维团队 (mt2) 看不到任何站点。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.get("/api/v1/stations/maintained", headers=_h(maint_env["tokens"]["mt2"]))
        assert r.status_code == 200
        assert r.json()["data"] == []


# ─── 5. 设备控制 — assert_maintenance_access 接入 ────────────────────────────

class TestMaintenanceAccessOnControl:
    def test_granted_mt_full_scope_passes_auth(self, client, maint_env, monkeypatch):
        """运维团队有 full 授权时, 控制被授权站点的设备: 通过鉴权 (不再 404/403)。

        send_control 会真实发 modbus 失败, 故 mock 之; 仅断言「鉴权放行」(≠ 404)。
        """
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env, "full"), headers=_h(maint_env["tokens"]["ops"]))
        # mock DeviceControlService.send_control 返回成功, 隔离 modbus
        from app.services.device_control_service import DeviceControlService
        async def _fake_send(self, device_id, command):
            return {"success": True}
        monkeypatch.setattr(DeviceControlService, "send_control", _fake_send)

        r = client.post(f"/api/v1/devices/{maint_env['device'].id}/control",
                        json={"action": "restart", "reset_type": "soft"},
                        headers=_h(maint_env["tokens"]["mt"]))
        # 通过鉴权 = 不是 404 (无授权) 也不是 403 (越权)
        assert r.status_code != 404, "被授权运维团队不应 404"
        assert r.status_code != 403, "被授权运维团队不应 403"

    def test_monitoring_only_scope_cannot_control(self, client, maint_env, monkeypatch):
        """scope=monitoring_only 的运维团队只能监控, 不能控制设备。→ 404。"""
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env, "monitoring_only"),
                    headers=_h(maint_env["tokens"]["ops"]))
        from app.services.device_control_service import DeviceControlService
        async def _fake_send(self, device_id, command):
            return {"success": True}
        monkeypatch.setattr(DeviceControlService, "send_control", _fake_send)

        r = client.post(f"/api/v1/devices/{maint_env['device'].id}/control",
                        json={"action": "restart", "reset_type": "soft"},
                        headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 404

    def test_ungranted_mt_cannot_control(self, client, maint_env):
        """未被授权的运维团队 (mt2) 控制设备。→ 404。"""
        # 给 mt 授权, 但 mt2 没被授权
        client.post("/api/v1/station-maintenance-grants",
                    json=_grant_payload(maint_env), headers=_h(maint_env["tokens"]["ops"]))
        r = client.post(f"/api/v1/devices/{maint_env['device'].id}/control",
                        json={"action": "restart", "reset_type": "soft"},
                        headers=_h(maint_env["tokens"]["mt2"]))
        assert r.status_code == 404

    def test_expired_grant_blocks_control(self, client, maint_env, monkeypatch):
        """status=active 但 expires_at 已过 → 视为失效, 控制 → 404。"""
        from datetime import datetime, timedelta, timezone
        # 直接造一条 active 但已过期的 grant
        from app.models.station_maintenance_grant import (
            StationMaintenanceGrant, GrantScope, GrantStatus,
        )
        s = client._sesh
        s.add(StationMaintenanceGrant(
            station_id=maint_env["station_a"].id,
            maintenance_team_id=maint_env["teams"]["mt"].id,
            granted_by_team_id=maint_env["teams"]["ops"].id,
            scope=GrantScope.FULL,
            status=GrantStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # 一小时前过期
        ))
        s.commit()
        from app.services.device_control_service import DeviceControlService
        async def _fake_send(self, device_id, command):
            return {"success": True}
        monkeypatch.setattr(DeviceControlService, "send_control", _fake_send)
        r = client.post(f"/api/v1/devices/{maint_env['device'].id}/control",
                        json={"action": "restart", "reset_type": "soft"},
                        headers=_h(maint_env["tokens"]["mt"]))
        assert r.status_code == 404

    def test_ops_company_self_maintains(self, client, maint_env, monkeypatch):
        """运营公司 (OPS_COMPANY) 自运维: 不需 grant 即可控制自有站点设备。"""
        from app.services.device_control_service import DeviceControlService
        async def _fake_send(self, device_id, command):
            return {"success": True}
        monkeypatch.setattr(DeviceControlService, "send_control", _fake_send)
        r = client.post(f"/api/v1/devices/{maint_env['device'].id}/control",
                        json={"action": "restart", "reset_type": "soft"},
                        headers=_h(maint_env["tokens"]["ops"]))
        assert r.status_code != 404
        assert r.status_code != 403
