"""列表 API 可选 team_id 查询参数测试（卡 2285f54a）。

覆盖 stations / devices / work-orders 三个列表端点：
- admin + team_id → 仅返回该团队数据（可指定任意团队）；
- admin + 不存在 team_id → 404（与 GET /teams/{team_id}/members 语义一致）；
- 团队级用户 + 本团队 team_id → 与其默认 scoping 等价；
- 团队级用户 + 他团队 team_id → 403；
- 不传 team_id → 原 caller-based scoping 行为零变化（admin 全量，团队级仅本团队）。
"""
import pytest

from tests._test_helpers import _fast_hash


def _token(client, username="admin", password="admin123"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login 失败: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def setup(client, seed_users):
    """构造双团队场景：team_a / team_b 各 1 站点 + 1 设备 + 1 工单，外加 1 个 team_a 工程师。"""
    from app.models.user import User, UserRole, Team
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderStatus

    s = client._sesh

    team_a = Team(name="团队A", code="TQA")
    team_b = Team(name="团队B", code="TQB")
    s.add_all([team_a, team_b])
    s.commit()
    s.refresh(team_a)
    s.refresh(team_b)

    st_a = Station(name="A站", code="QASTAA", status=StationStatus.NORMAL, team_id=team_a.id)
    st_b = Station(name="B站", code="QASTAB", status=StationStatus.NORMAL, team_id=team_b.id)
    s.add_all([st_a, st_b])
    s.commit()
    s.refresh(st_a)
    s.refresh(st_b)

    dev_a = Device(sn="SN-QA-A", name="A设备", code="QADEVA",
                   type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                   station_id=st_a.id, rated_power=60.0)
    dev_b = Device(sn="SN-QA-B", name="B设备", code="QADEVB",
                   type=DeviceType.CHARGER_AC, status=DeviceStatus.OFFLINE,
                   station_id=st_b.id, rated_power=7.0)
    s.add_all([dev_a, dev_b])
    s.commit()

    wo_a = WorkOrder(id="WO-QA-A", station_id=st_a.id, device_id=dev_a.id,
                     type=WorkOrderType.REPAIR, status=WorkOrderStatus.PENDING,
                     fault_desc="A团队工单")
    wo_b = WorkOrder(id="WO-QA-B", station_id=st_b.id, device_id=dev_b.id,
                     type=WorkOrderType.INSPECTION, status=WorkOrderStatus.COMPLETED,
                     fault_desc="B团队工单")
    s.add_all([wo_a, wo_b])

    s.add(User(username="eng_qa", password_hash=_fast_hash("eng123"),
               role=UserRole.ENGINEER, team_id=team_a.id, status="active"))
    s.commit()

    return {
        "team_a": team_a, "team_b": team_b,
        "st_a": st_a, "st_b": st_b,
        "wo_a_id": wo_a.id, "wo_b_id": wo_b.id,
    }


# ════════════════════════════════════════════════════════════
# admin 视角
# ════════════════════════════════════════════════════════════

class TestAdminTeamFilter:
    def test_admin_filter_stations_by_team(self, client, seed_users, setup):
        token = _token(client)
        resp = client.get(f"/api/v1/stations?team_id={setup['team_a'].id}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        names = [it["name"] for it in resp.json()["data"]["items"]]
        assert names == ["A站"]

    def test_admin_filter_devices_by_team(self, client, seed_users, setup):
        token = _token(client)
        resp = client.get(f"/api/v1/devices?team_id={setup['team_b'].id}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        assert [it["name"] for it in items] == ["B设备"]

    def test_admin_filter_workorders_by_team(self, client, seed_users, setup):
        token = _token(client)
        resp = client.get(f"/api/v1/work-orders?team_id={setup['team_a'].id}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        ids = [it["id"] for it in resp.json()["data"]["items"]]
        assert ids == [setup["wo_a_id"]]

    def test_admin_nonexistent_team_404(self, client, seed_users, setup):
        token = _token(client)
        for path in ("/api/v1/stations", "/api/v1/devices", "/api/v1/work-orders"):
            resp = client.get(f"{path}?team_id=987654", headers=_auth(token))
            assert resp.status_code == 404, f"{path}: {resp.status_code} {resp.text}"
            assert "不存在" in resp.json()["detail"]

    def test_admin_no_team_id_sees_all(self, client, seed_users, setup):
        """不传 team_id：admin 行为零变化（全量可见）。"""
        token = _token(client)
        resp = client.get("/api/v1/stations", headers=_auth(token))
        assert resp.status_code == 200
        names = [it["name"] for it in resp.json()["data"]["items"]]
        assert "A站" in names and "B站" in names


# ════════════════════════════════════════════════════════════
# 团队级用户视角
# ════════════════════════════════════════════════════════════

class TestTeamUserTeamFilter:
    def _eng_token(self, client):
        return _token(client, "eng_qa", "eng123")

    def test_own_team_id_equivalent_to_default_scoping(self, client, seed_users, setup):
        token = self._eng_token(client)
        for path in ("/api/v1/stations", "/api/v1/devices", "/api/v1/work-orders"):
            with_team = client.get(f"{path}?team_id={setup['team_a'].id}", headers=_auth(token))
            without = client.get(path, headers=_auth(token))
            assert with_team.status_code == 200, f"{path}: {with_team.text}"
            assert without.status_code == 200
            assert with_team.json()["data"]["items"] == without.json()["data"]["items"], path

    def test_other_team_id_403(self, client, seed_users, setup):
        token = self._eng_token(client)
        for path in ("/api/v1/stations", "/api/v1/devices", "/api/v1/work-orders"):
            resp = client.get(f"{path}?team_id={setup['team_b'].id}", headers=_auth(token))
            assert resp.status_code == 403, f"{path}: {resp.status_code} {resp.text}"

    def test_nonexistent_team_404_even_for_team_user(self, client, seed_users, setup):
        """团队存在性校验先于归属校验（404 优先于 403）。"""
        token = self._eng_token(client)
        resp = client.get("/api/v1/stations?team_id=987654", headers=_auth(token))
        assert resp.status_code == 404

    def test_existing_filters_still_compose(self, client, seed_users, setup):
        """team_id 与既有 status 过滤可组合。"""
        token = _token(client)
        resp = client.get(
            f"/api/v1/devices?team_id={setup['team_b'].id}&status=online",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []  # B设备是 offline
