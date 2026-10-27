"""
monitor 遥测监控族团队隔离测试 (卡 dc4e094b)

团队级用户: /monitor/realtime、/monitor/history 仅本 team 设备/遥测;
admin 全量; 未登录 401。
"""
import bcrypt
import pytest
from datetime import datetime, timedelta, timezone

from app.models.device import Device, DeviceType
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry
from app.models.user import User, UserRole, Team

PWD = "dcm4mon"


def _login(client, username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": PWD})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


@pytest.fixture(scope="function")
def mon(client):
    """两团队两站点各一设备, 各带一条遥测 (区分度: grid_power_total A=10, B=99)。"""
    s = client._sesh
    ta = Team(name="D4M团队A", code="D4MTA")
    tb = Team(name="D4M团队B", code="D4MTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    hash_ = bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()
    ua = User(username="d4m_op_a", real_name="A运维", role=UserRole.OPERATOR,
              team_id=ta.id, status="active", password_hash=hash_)
    s.add(ua)
    s.commit()

    st_a = Station(name="D4M-A站", code="D4MSA", team_id=ta.id,
                   status=StationStatus.NORMAL)
    st_b = Station(name="D4M-B站", code="D4MSB", team_id=tb.id,
                   status=StationStatus.NORMAL)
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    d_a = Device(sn="D4M-SN-A", name="A站桩", type=DeviceType.CHARGER_DC,
                 station_id=st_a.id)
    d_b = Device(sn="D4M-SN-B", name="B站桩", type=DeviceType.CHARGER_DC,
                 station_id=st_b.id)
    s.add_all([d_a, d_b])
    s.commit()
    s.refresh(d_a)
    s.refresh(d_b)

    ts = datetime.now(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    s.add_all([
        Telemetry(device_id=d_a.id, timestamp=ts - timedelta(minutes=30),
                  grid_power_total=10.0),
        Telemetry(device_id=d_a.id, timestamp=ts,
                  grid_power_total=10.0),
        Telemetry(device_id=d_b.id, timestamp=ts - timedelta(minutes=30),
                  grid_power_total=99.0),
        Telemetry(device_id=d_b.id, timestamp=ts,
                  grid_power_total=99.0),
    ])
    s.commit()

    return {
        "devices": {"a": d_a, "b": d_b},
        "token_a": _login(client, "d4m_op_a"),
        "client": client,
    }


class TestMonitorTeamScope:

    def test_operator_realtime_isolated(self, mon):
        r = mon["client"].get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {mon['token_a']}"
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        ids = [d["id"] for d in data["devices"]]
        assert ids == [mon["devices"]["a"].id]
        # 聚合仅含 A 设备功率 10, 不含 B 的 99
        assert data["totalPower"] == 10.0

    def test_operator_history_isolated(self, mon):
        r = mon["client"].get("/api/v1/monitor/history", headers={
            "Authorization": f"Bearer {mon['token_a']}"
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["data"], "应至少有一个小时 bucket"
        for bucket in data["data"]:
            assert bucket["power"] == 10.0

    def test_admin_realtime_all(self, mon):
        r = mon["client"].get("/api/v1/monitor/realtime")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        ids = {d["id"] for d in data["devices"]}
        assert ids == {mon["devices"]["a"].id, mon["devices"]["b"].id}
        assert data["totalPower"] == 109.0

    def test_admin_history_all(self, mon):
        r = mon["client"].get("/api/v1/monitor/history")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["data"]
        for bucket in data["data"]:
            assert bucket["power"] == 54.5  # (10+99)/2

    def test_realtime_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/monitor/realtime")
        assert r.status_code in (401, 403)

    def test_history_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/monitor/history")
        assert r.status_code in (401, 403)
