"""
V2G 调度记录 team 隔离测试 — 任务卡 9e9e8f96

GET /api/v1/fleet/v2g/records 此前只校验 enterprise 归属但不按 team 过滤
query 主体, 团队级用户传本 team enterprise_id 即可全表读取所有团队的
V2G 调度日志(水平越权)。修复后:
- 团队 A 用户传 enterprise_id=A → 只见 A team 设备(station.team_id=A)的日志;
- admin(平台级) → 全量可见。

范式参考 test_fleet_default_scope_isolation.py。
"""
import bcrypt
import pytest


@pytest.fixture
def v2g_scope_pair(client):
    """两团队 + 两 OPERATOR + 两企业(各归属一团队) + 各团队一套 station/device/dispatch_log + token。"""
    from datetime import datetime, timezone, timedelta
    from app.models.user import User, UserRole, Team
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.v2g_dispatch import V2GDispatchLog
    s = client._sesh

    out = {"teams": {}, "users": {}, "enterprises": {}, "devices": {}, "logs": {}, "tokens": {}}
    pwd = "v2gscope123456"
    for key, tname, tcode, uname in [
        ("a", "V2G隔离团队A", "V2GA", "v2g_scope_op_a"),
        ("b", "V2G隔离团队B", "V2GB", "v2g_scope_op_b"),
    ]:
        t = Team(name=tname, code=tcode)
        s.add(t)
        s.commit()
        s.refresh(t)
        out["teams"][key] = t

        u = User(
            username=uname, real_name=f"{key}运营", role=UserRole.OPERATOR,
            team_id=t.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(u)
        s.commit()

        ent = Enterprise(name=f"V2G隔离企业{key}", code=f"V2GENT{key}",
                         status=EnterpriseStatus.ACTIVE, owner_team_id=t.id)
        s.add(ent)
        s.commit()
        s.refresh(ent)
        out["enterprises"][key] = ent

        station = Station(name=f"V2G隔离站{key}", code=f"STA_V2G_ISO_{key.upper()}",
                          address="隔离测试地址", status=StationStatus.NORMAL, team_id=t.id)
        s.add(station)
        s.commit()
        s.refresh(station)

        device = Device(
            sn=f"SN-V2G-ISO-{key.upper()}", name=f"V2G隔离桩{key}", code=f"V2GISO{key.upper()}",
            type=DeviceType.V2G_CHARGER, status=DeviceStatus.ONLINE,
            station_id=station.id, rated_power=120.0,
        )
        s.add(device)
        s.commit()
        s.refresh(device)
        out["devices"][key] = device

        log = V2GDispatchLog(
            device_id=device.id, dispatch_type="discharge",
            target_power_kw=50.0, actual_power_kw=48.5, status="completed",
            start_at=datetime.now(timezone.utc),
            end_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        s.add(log)
        s.commit()
        s.refresh(log)
        out["logs"][key] = log

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    out["tokens"] = {"a": _tok("v2g_scope_op_a"), "b": _tok("v2g_scope_op_b")}
    return out


class TestV2GRecordsTeamIsolation:
    def test_team_a_user_only_sees_own_team_logs(self, client, v2g_scope_pair):
        """团队 A 用户传本 team enterprise → 只见 A 团队设备日志, B 团队被过滤"""
        ent_a = v2g_scope_pair["enterprises"]["a"]
        r = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_a.id}",
            headers={"Authorization": f"Bearer {v2g_scope_pair['tokens']['a']}"},
        )
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        device_ids = {it["device_id"] for it in items}
        assert device_ids == {v2g_scope_pair["devices"]["a"].id}
        assert v2g_scope_pair["devices"]["b"].id not in device_ids

    def test_team_b_user_only_sees_own_team_logs(self, client, v2g_scope_pair):
        """团队 B 用户对称: 只见 B 团队设备日志"""
        ent_b = v2g_scope_pair["enterprises"]["b"]
        r = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_b.id}",
            headers={"Authorization": f"Bearer {v2g_scope_pair['tokens']['b']}"},
        )
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        device_ids = {it["device_id"] for it in items}
        assert device_ids == {v2g_scope_pair["devices"]["b"].id}

    def test_cross_team_enterprise_still_404(self, client, v2g_scope_pair):
        """跨团队 enterprise 仍 404, 不破坏 assert_enterprise_team_access 语义"""
        ent_b = v2g_scope_pair["enterprises"]["b"]
        r = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_b.id}",
            headers={"Authorization": f"Bearer {v2g_scope_pair['tokens']['a']}"},
        )
        assert r.status_code == 404

    def test_admin_sees_all_teams_logs(self, client, v2g_scope_pair):
        """admin 不受限: 同一 enterprise 下 join 不生效, 可见全量(两团队)日志"""
        ent_a = v2g_scope_pair["enterprises"]["a"]
        r = client.get(f"/api/v1/fleet/v2g/records?enterprise_id={ent_a.id}")
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        device_ids = {it["device_id"] for it in items}
        assert device_ids == {
            v2g_scope_pair["devices"]["a"].id,
            v2g_scope_pair["devices"]["b"].id,
        }
