"""
能耗报表三端点团队隔离测试 (卡 e61ac986)

/trend /summary /station-compare 团队级用户仅本 team 站点聚合;
显式跨团队 station_id → 404; admin 全量; 未登录 401。
"""
import bcrypt
import pytest
from datetime import datetime, timedelta, timezone

from app.models.device import Device, DeviceType
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry
from app.models.user import User, UserRole, Team

PWD = "e61ac986"


def _login(client, username):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": PWD})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("data", {}).get("token") or j.get("token")


@pytest.fixture(scope="function")
def scoped(client):
    """两团队两站点, 各一设备带 charger_kwh 累计遥测(充电量=差值)。"""
    s = client._sesh
    ta = Team(name="E61团队A", code="E61TA")
    tb = Team(name="E61团队B", code="E61TB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    hash_ = bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode()
    ua = User(username="e61_op_a", real_name="A运营", role=UserRole.OPERATOR,
              team_id=ta.id, status="active", password_hash=hash_)
    s.add(ua)
    s.commit()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    st_a = Station(name="E61-A站", code="E61SA", team_id=ta.id,
                   status=StationStatus.NORMAL)
    st_b = Station(name="E61-B站", code="E61SB", team_id=tb.id,
                   status=StationStatus.NORMAL)
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    d_a = Device(sn="E61-SN-A", name="A站桩", type=DeviceType.CHARGER_DC,
                 station_id=st_a.id)
    d_b = Device(sn="E61-SN-B", name="B站桩", type=DeviceType.CHARGER_DC,
                 station_id=st_b.id)
    s.add_all([d_a, d_b])
    s.commit()
    s.refresh(d_a)
    s.refresh(d_b)

    t0, t1 = now - timedelta(days=1), now - timedelta(days=1, seconds=-3600)
    s.add_all([
        Telemetry(device_id=d_a.id, timestamp=t0, charger_kwh=0.0),
        Telemetry(device_id=d_a.id, timestamp=t1, charger_kwh=10.0),
        Telemetry(device_id=d_b.id, timestamp=t0, charger_kwh=0.0),
        Telemetry(device_id=d_b.id, timestamp=t1, charger_kwh=99.0),
    ])
    s.commit()

    start = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    return {
        "stations": {"a": st_a, "b": st_b},
        "tokens": {"a": _login(client, "e61_op_a"), "admin": None},
        "admin": client,  # client 默认 admin 头
        "start": start, "end": end,
    }


class TestEnergyTrendScope:

    def test_trend_operator_only_own_team(self, scoped):
        h = {"Authorization": f"Bearer {scoped['tokens']['a']}"}
        r = scoped["admin"].get(
            "/api/v1/energy/trend", headers=h,
            params={"start_date": scoped["start"], "end_date": scoped["end"]})
        assert r.status_code == 200, r.text
        total_charge = sum(x["charging_amount"] for x in r.json()["data"]["trend"])
        assert total_charge == pytest.approx(10.0, abs=0.1)

    def test_trend_admin_sees_all(self, scoped):
        r = scoped["admin"].get(
            "/api/v1/energy/trend",
            params={"start_date": scoped["start"], "end_date": scoped["end"]})
        total_charge = sum(x["charging_amount"] for x in r.json()["data"]["trend"])
        assert total_charge == pytest.approx(109.0, abs=0.1)

    def test_trend_cross_team_station_404(self, scoped):
        h = {"Authorization": f"Bearer {scoped['tokens']['a']}"}
        r = scoped["admin"].get(
            "/api/v1/energy/trend", headers=h,
            params={"station_id": scoped["stations"]["b"].id,
                    "start_date": scoped["start"], "end_date": scoped["end"]})
        assert r.status_code == 404, r.text

    def test_trend_own_station_ok(self, scoped):
        h = {"Authorization": f"Bearer {scoped['tokens']['a']}"}
        r = scoped["admin"].get(
            "/api/v1/energy/trend", headers=h,
            params={"station_id": scoped["stations"]["a"].id,
                    "start_date": scoped["start"], "end_date": scoped["end"]})
        assert r.status_code == 200
        total_charge = sum(x["charging_amount"] for x in r.json()["data"]["trend"])
        assert total_charge == pytest.approx(10.0, abs=0.1)

    def test_trend_cumulative_delta_straddles_midnight_d386c813(self, scoped):
        """卡 d386c813: 累计计数器差值跨上海日界窗丢弃。

        样本对 15:30Z/16:30Z 分属上海 23:30 / 次日 00:30 两个日桶;
        先分桶再桶内取末-首差值会把跨桶区间电量归零。正确语义:
        相邻采样差值归属较晚样本所在桶, 周期总和须守恒 (=10)。
        固定时间戳使断言与运行时刻无关。
        """
        from app.models.telemetry import Telemetry as T
        s = scoped["admin"]._sesh
        d_a = s.query(Device).filter_by(sn="E61-SN-A").one()
        s.add_all([
            T(device_id=d_a.id, timestamp=datetime(2026, 1, 15, 15, 30),
              charger_kwh=0.0),
            T(device_id=d_a.id, timestamp=datetime(2026, 1, 15, 16, 30),
              charger_kwh=10.0),
        ])
        s.commit()
        r = scoped["admin"].get(
            "/api/v1/energy/trend",
            params={"start_date": "2026-01-14", "end_date": "2026-01-16"})
        assert r.status_code == 200, r.text
        trend = r.json()["data"]["trend"]
        by_date = {x["date"]: x["charging_amount"] for x in trend}
        assert sum(by_date.values()) == pytest.approx(10.0, abs=0.1)
        assert by_date.get("2026-01-16", 0.0) == pytest.approx(10.0, abs=0.1)

    def test_trend_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/energy/trend")
        assert r.status_code in (401, 403)


class TestEnergySummaryScope:

    def test_summary_operator_only_own_team(self, scoped):
        h = {"Authorization": f"Bearer {scoped['tokens']['a']}"}
        r = scoped["admin"].get("/api/v1/energy/summary", headers=h,
                                params={"period": "day"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["charging_amount"] == pytest.approx(0.0, abs=0.1)

    def test_summary_cross_team_station_404(self, scoped):
        h = {"Authorization": f"Bearer {scoped['tokens']['a']}"}
        r = scoped["admin"].get(
            "/api/v1/energy/summary", headers=h,
            params={"station_id": scoped["stations"]["b"].id})
        assert r.status_code == 404, r.text

    def test_summary_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/energy/summary")
        assert r.status_code in (401, 403)


class TestStationCompareScope:

    def test_compare_operator_only_own_team(self, scoped):
        h = {"Authorization": f"Bearer {scoped['tokens']['a']}"}
        r = scoped["admin"].get("/api/v1/energy/station-compare", headers=h)
        assert r.status_code == 200, r.text
        stations = r.json()["data"]["stations"]
        ids = [x["station_id"] for x in stations]
        assert scoped["stations"]["a"].id in ids
        assert scoped["stations"]["b"].id not in ids

    def test_compare_admin_sees_all(self, scoped):
        r = scoped["admin"].get("/api/v1/energy/station-compare")
        ids = [x["station_id"] for x in r.json()["data"]["stations"]]
        assert {scoped["stations"]["a"].id, scoped["stations"]["b"].id} <= set(ids)

    def test_compare_requires_auth(self, anon_client):
        r = anon_client.get("/api/v1/energy/station-compare")
        assert r.status_code in (401, 403)
