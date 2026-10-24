"""
数据看板 /stats 团队隔离测试 (卡 820cf187)

团队级用户: overview/health-trend/alarm-stats/workorder-stats/engineer-performance
仅统计本 team (站点→设备/告警/工单; User.team_id 过滤工程师); admin 全量; 未登录 401。
"""
import bcrypt
import pytest
from datetime import datetime, timedelta, timezone

from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.device import Device, DeviceType
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole, Team
from app.models.workorder import WorkOrder, WorkOrderStatus

PWD = "statst882"


def _login(client, username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": PWD})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


@pytest.fixture(scope="function")
def stats_env(client):
    """teamA/teamB 各一站点+一设备; B 侧活跃 critical 告警 + pending 工单;
    两 team 各一名 engineer (B 侧已完工工单挂 B engineer)。"""
    s = client._sesh
    ta = Team(name="S82团队A", code="S82TA")
    tb = Team(name="S82团队B", code="S82TB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    hash_ = bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()
    ua = User(username="s82_op_a", real_name="A运营", role=UserRole.OPERATOR,
              team_id=ta.id, status="active", password_hash=hash_)
    eng_a = User(username="s82_eng_a", real_name="A工程师", role=UserRole.ENGINEER,
                 team_id=ta.id, status="active", password_hash=hash_)
    eng_b = User(username="s82_eng_b", real_name="B工程师", role=UserRole.ENGINEER,
                 team_id=tb.id, status="active", password_hash=hash_)
    s.add_all([ua, eng_a, eng_b])
    s.commit()

    now = datetime.now(timezone.utc)
    st_a = Station(name="S82-A站", code="S82SA", team_id=ta.id,
                   status=StationStatus.NORMAL)
    st_b = Station(name="S82-B站", code="S82SB", team_id=tb.id,
                   status=StationStatus.NORMAL)
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    d_a = Device(sn="S82-SN-A", name="A站桩", type=DeviceType.CHARGER_DC,
                 station_id=st_a.id, status="online", health_score=90)
    d_b = Device(sn="S82-SN-B", name="B站桩", type=DeviceType.PV_INVERTER,
                 station_id=st_b.id, status="fault", health_score=50)
    s.add_all([d_a, d_b])
    s.commit()
    s.refresh(d_a)
    s.refresh(d_b)

    s.add_all([
        Alarm(device_id=d_b.id, station_id=st_b.id, level=AlarmLevel.CRITICAL,
              status=AlarmStatus.ACTIVE, created_at=now - timedelta(minutes=5)),
        WorkOrder(id="S82-WO-B-1", fault_desc="B站工单", station_id=st_b.id,
                  device_id=d_b.id, status=WorkOrderStatus.PENDING,
                  creator_id=ua.id),
        WorkOrder(id="S82-WO-B-2", fault_desc="B站完工单", station_id=st_b.id,
                  device_id=d_b.id, status=WorkOrderStatus.COMPLETED,
                  assignee_id=eng_b.id, creator_id=ua.id,
                  accept_time=now - timedelta(hours=2),
                  finish_time=now - timedelta(hours=1)),
    ])
    s.commit()

    return {"client": client, "token_a": _login(client, "s82_op_a"),
            "team_a": ta, "eng_a": eng_a, "eng_b": eng_b}


class TestOverviewScope:

    def test_operator_isolated(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/overview",
                                    headers={"Authorization": f"Bearer {stats_env['token_a']}"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["stations"]["total"] == 1
        assert d["devices"]["total"] == 1
        assert d["devices"]["fault"] == 0
        assert d["alarms"]["active"] == 0
        assert d["workorders"]["pending"] == 0

    def test_admin_sees_all(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/overview")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["stations"]["total"] == 2
        assert d["devices"]["total"] == 2
        assert d["devices"]["fault"] == 1
        assert d["alarms"]["active"] == 1
        assert d["workorders"]["pending"] == 1

    def test_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/stats/overview")
        assert r.status_code in (401, 403)


class TestHealthTrendScope:

    def test_operator_isolated(self, stats_env):
        client = stats_env["client"]
        s = client._sesh
        from app.models.device import DeviceHealthRecord
        # 跨 team 设备的健康快照: A 用户不应看到它影响趋势
        s.add(DeviceHealthRecord(device_id=2, total_score=10.0,
                                 created_at=datetime.now(timezone.utc)))
        s.commit()
        r = client.get("/api/v1/stats/health-trend?days=1",
                       headers={"Authorization": f"Bearer {stats_env['token_a']}"})
        assert r.status_code == 200, r.text
        trend = r.json()["data"]
        assert len(trend) == 1
        assert trend[0]["score"] != 10.0

    def test_admin_sees_all(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/health-trend?days=1")
        assert r.status_code == 200, r.text


class TestAlarmStatsScope:

    def test_operator_isolated(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/alarm-stats?days=7",
                                    headers={"Authorization": f"Bearer {stats_env['token_a']}"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["total"] == 0

    def test_admin_sees_all(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/alarm-stats?days=7")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["total"] == 1


class TestWorkorderStatsScope:

    def test_operator_isolated(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/workorder-stats?days=7",
                                    headers={"Authorization": f"Bearer {stats_env['token_a']}"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["total"] == 0

    def test_admin_sees_all(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/workorder-stats?days=7")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["total"] == 2


class TestEngineerPerformanceScope:

    def test_operator_isolated(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/engineer-performance",
                                    headers={"Authorization": f"Bearer {stats_env['token_a']}"})
        assert r.status_code == 200, r.text
        names = [e["name"] for e in r.json()["data"]]
        assert "A工程师" in names
        assert "B工程师" not in names

    def test_admin_sees_all(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/engineer-performance")
        assert r.status_code == 200, r.text
        names = [e["name"] for e in r.json()["data"]]
        assert "A工程师" in names
        assert "B工程师" in names


class TestExistingScopedEndpointsAdmin:

    def test_admin_devices_health_full(self, stats_env):
        """admin.team_id 可能为 None, 旧 SQL 强制 WHERE team_id=:tid 会漏 — admin 应全量"""
        r = stats_env["client"].get("/api/v1/stats/devices/health")
        assert r.status_code == 200, r.text
        vals = {d["name"]: d["value"] for d in r.json()["data"]["devices"]}
        assert vals["正常"] + vals["警告"] + vals["故障"] == 2

    def test_admin_station_rank_full(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/stations/rank")
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]["rank"]) == 2

    def test_operator_station_rank_isolated(self, stats_env):
        r = stats_env["client"].get("/api/v1/stats/stations/rank",
                                    headers={"Authorization": f"Bearer {stats_env['token_a']}"})
        assert r.status_code == 200, r.text
        rank = r.json()["data"]["rank"]
        assert len(rank) == 1
