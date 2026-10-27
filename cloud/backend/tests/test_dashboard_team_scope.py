"""
数据大屏 large-screen 团队隔离测试 (卡 e61ac986)

团队级用户: 设备/站点/告警/工单/站点健康/最近告警/设备类型统计仅本 team;
admin 全量; 未登录 401。
"""
import bcrypt
import pytest
from datetime import datetime, timedelta, timezone

from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.device import Device, DeviceType
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole, Team
from app.models.workorder import WorkOrder, WorkOrderStatus

PWD = "e61dash"


def _login(client, username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": PWD})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


@pytest.fixture(scope="function")
def dash(client):
    """两团队两站点各一设备; B 团队站点再挂一条活跃告警+一张 pending 工单。"""
    s = client._sesh
    ta = Team(name="D61团队A", code="D61TA")
    tb = Team(name="D61团队B", code="D61TB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    hash_ = bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()
    ua = User(username="d61_op_a", real_name="A运营", role=UserRole.OPERATOR,
              team_id=ta.id, status="active", password_hash=hash_)
    s.add(ua)
    s.commit()

    now = datetime.now(timezone.utc)
    st_a = Station(name="D61-A站", code="D61SA", team_id=ta.id,
                   status=StationStatus.NORMAL)
    st_b = Station(name="D61-B站", code="D61SB", team_id=tb.id,
                   status=StationStatus.NORMAL)
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    d_a = Device(sn="D61-SN-A", name="A站桩", type=DeviceType.CHARGER_DC,
                 station_id=st_a.id)
    d_b = Device(sn="D61-SN-B", name="B站桩", type=DeviceType.PV_INVERTER,
                 station_id=st_b.id)
    s.add_all([d_a, d_b])
    s.commit()
    s.refresh(d_a)
    s.refresh(d_b)

    s.add_all([
        Alarm(device_id=d_b.id, station_id=st_b.id, level=AlarmLevel.CRITICAL,
              status=AlarmStatus.ACTIVE, created_at=now - timedelta(minutes=5)),
        WorkOrder(id="D61-WO-B-1", fault_desc="B站工单", station_id=st_b.id,
                  device_id=d_b.id, status=WorkOrderStatus.PENDING,
                  creator_id=ua.id),
    ])
    s.commit()

    return {
        "stations": {"a": st_a, "b": st_b},
        "token_a": _login(client, "d61_op_a"),
        "client": client,
    }


def _get(client, token):
    r = client.get("/api/v1/dashboard/large-screen",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


class TestLargeScreenScope:

    def test_operator_isolated(self, dash):
        data = _get(dash["client"], dash["token_a"])
        cm = data["core_metrics"]
        assert cm["total_devices"] == 1
        assert cm["total_stations"] == 1
        assert cm["active_alarms"] == 0
        assert cm["pending_workorders"] == 0
        # 站点健康仅本团队站点
        assert [h["station_id"] for h in data["station_health"]] == \
            [dash["stations"]["a"].id]
        # 最近告警不含跨团队
        assert data["recent_alarms"] == []
        # 设备类型统计仅本团队设备类型
        types = [t["type"] for t in data["device_type_stats"]]
        assert "charger_dc" in types
        assert "pv_inverter" not in types

    def test_admin_sees_all(self, dash):
        r = dash["client"].get("/api/v1/dashboard/large-screen")
        assert r.status_code == 200, r.text
        cm = r.json()["core_metrics"]
        assert cm["total_devices"] == 2
        assert cm["total_stations"] == 2
        assert cm["active_alarms"] == 1
        assert cm["pending_workorders"] == 1

    def test_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/dashboard/large-screen")
        assert r.status_code in (401, 403)
