"""工单生命周期端点测试 — app/api/v1/workorders/routes_lifecycle.py

覆盖：list / stats / get / create / update / delete / logs
维度：正常路径 × 分页&过滤参数 × team scoping × CRUD 404 × 匿名401 × 非admin创建校验
"""
import pytest

from tests.api._helpers import WO_URL, login_as, create_wo
from app.models.workorder import (
    WorkOrder, WorkOrderStatus, WorkOrderType, WorkOrderLevel, WorkOrderLog,
)


def _seed_wo(session, wo_id, *, status="pending", level="warning", type_="repair",
             station_id=None, fault_desc="种子工单"):
    """直接 ORM 插入单条工单（绕过 API 秒级 id 冲突），返回 id。"""
    wo = WorkOrder(
        id=wo_id,
        fault_desc=fault_desc,
        type=WorkOrderType(type_),
        level=WorkOrderLevel(level),
        status=WorkOrderStatus(status),
        station_id=station_id,
    )
    session.add(wo)
    session.commit()
    return wo.id


class TestList:
    def test_list_empty(self, client):
        r = client.get(WO_URL)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0
        assert r.json()["data"]["items"] == []

    def test_list_with_data(self, client, db_session):
        _seed_wo(db_session, "WO-L-001", status="pending")
        _seed_wo(db_session, "WO-L-002", status="completed")
        r = client.get(WO_URL)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2

    def test_list_filter_status(self, client, db_session):
        _seed_wo(db_session, "WO-L-010", status="pending")
        _seed_wo(db_session, "WO-L-011", status="completed")
        r = client.get(WO_URL, params={"status": "completed"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "completed"

    def test_list_filter_level_type(self, client, db_session):
        _seed_wo(db_session, "WO-L-020", level="critical", type_="emergency")
        _seed_wo(db_session, "WO-L-021", level="warning", type_="repair")
        r = client.get(WO_URL, params={"level": "critical", "type": "emergency"})
        assert r.json()["data"]["total"] == 1

    def test_list_pagination(self, client, db_session):
        for i in range(5):
            _seed_wo(db_session, f"WO-P-{i:03d}")
        r = client.get(WO_URL, params={"page": 1, "page_size": 2})
        assert r.status_code == 200
        assert len(r.json()["data"]["items"]) == 2
        assert r.json()["data"]["total"] == 5

    def test_list_invalid_page(self, client):
        """page < 1 → 422"""
        r = client.get(WO_URL, params={"page": 0})
        assert r.status_code == 422

    def test_list_invalid_page_size(self, client):
        """page_size > 100 → 422"""
        r = client.get(WO_URL, params={"page_size": 200})
        assert r.status_code == 422

    def test_list_team_scoped(self, client, db_session, seed_users, seed_stations):
        """非 admin 仅见本 team 工单"""
        s = db_session
        eng = seed_users["engineer1"]
        eng.team_id = 5
        sta_own = seed_stations["station_a"]
        sta_own.team_id = 5
        sta_other = seed_stations["station_b"]
        sta_other.team_id = 999
        s.commit()
        _seed_wo(db_session, "WO-T-001", station_id=sta_own.id)
        _seed_wo(db_session, "WO-T-002", station_id=sta_other.id)
        login_as(client, "engineer1", "eng123")
        r = client.get(WO_URL)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1  # 仅本 team


class TestStats:
    def test_stats_empty(self, client):
        r = client.get(f"{WO_URL}/stats")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert "status_distribution" in data

    def test_stats_with_data(self, client, db_session):
        _seed_wo(db_session, "WO-S-001", status="pending")
        _seed_wo(db_session, "WO-S-002", status="completed")
        _seed_wo(db_session, "WO-S-003", status="completed")
        r = client.get(f"{WO_URL}/stats")
        data = r.json()["data"]
        assert data["total"] == 3
        assert data["status_distribution"]["completed"] == 2

    def test_stats_group_by(self, client, db_session):
        _seed_wo(db_session, "WO-G-001", level="critical")
        _seed_wo(db_session, "WO-G-002", level="warning")
        for gb in ("status", "level", "type", "date"):
            r = client.get(f"{WO_URL}/stats", params={"group_by": gb})
            assert r.status_code == 200
            assert "groups" in r.json()["data"]


class TestGet:
    def test_get_ok(self, client, db_session):
        _seed_wo(db_session, "WO-G-100")
        r = client.get(f"{WO_URL}/WO-G-100")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == "WO-G-100"

    def test_get_not_found(self, client):
        r = client.get(f"{WO_URL}/WO-NONEXIST")
        assert r.status_code == 404

    def test_get_cross_team_404(self, client, db_session, seed_users, seed_stations):
        s = db_session
        eng = seed_users["engineer1"]
        eng.team_id = 5
        sta = seed_stations["station_a"]
        sta.team_id = 999
        s.commit()
        _seed_wo(db_session, "WO-X-001", station_id=sta.id)
        login_as(client, "engineer1", "eng123")
        r = client.get(f"{WO_URL}/WO-X-001")
        assert r.status_code == 404


class TestCreate:
    def test_create_ok_admin(self, client):
        wid = create_wo(client)
        assert wid.startswith("WO-")

    def test_create_missing_fault_desc(self, client):
        """fault_desc 必填 → 422"""
        r = client.post(WO_URL, json={"type": "repair", "level": "warning"})
        assert r.status_code == 422

    def test_create_non_admin_no_station(self, client, seed_users):
        """非 admin 不指定 station_id → 400"""
        seed_users
        login_as(client, "engineer1", "eng123")
        r = client.post(WO_URL, json={"fault_desc": "x", "type": "repair", "level": "warning"})
        assert r.status_code == 400
        assert "station_id" in r.json()["detail"]

    def test_create_non_admin_other_team_station(self, client, seed_users, seed_stations):
        """非 admin 指定他团站点 → 404"""
        s = client._sesh
        eng = seed_users["engineer1"]
        eng.team_id = 5
        sta = seed_stations["station_a"]
        sta.team_id = 999
        s.commit()
        login_as(client, "engineer1", "eng123")
        r = client.post(WO_URL, json={
            "fault_desc": "x", "type": "repair", "level": "warning",
            "station_id": sta.id,
        })
        assert r.status_code == 404

    def test_create_non_admin_own_station_ok(self, client, seed_users, seed_stations):
        """非 admin 指定本 team 站点 → 200"""
        s = client._sesh
        eng = seed_users["engineer1"]
        eng.team_id = 5
        sta = seed_stations["station_a"]
        sta.team_id = 5
        s.commit()
        login_as(client, "engineer1", "eng123")
        r = client.post(WO_URL, json={
            "fault_desc": "本团工单", "type": "repair", "level": "warning",
            "station_id": sta.id,
        })
        assert r.status_code == 200


class TestUpdate:
    def test_update_ok(self, client):
        wid = create_wo(client)
        r = client.put(f"{WO_URL}/{wid}", json={
            "fault_desc": "更新描述", "level": "critical", "status": "accepted",
            "solution": "已处理",
        })
        assert r.status_code == 200
        assert r.json()["data"]["fault_desc"] == "更新描述"

    def test_update_not_found(self, client):
        r = client.put(f"{WO_URL}/WO-NOPE", json={"fault_desc": "x"})
        assert r.status_code == 404

    def test_update_status_sets_timestamps(self, client):
        """status=accepted 自动设 accept_time"""
        wid = create_wo(client)
        client.put(f"{WO_URL}/{wid}", json={"status": "accepted"})
        r = client.get(f"{WO_URL}/{wid}")
        assert r.json()["data"]["accept_time"] is not None


class TestDelete:
    def test_delete_ok(self, client):
        wid = create_wo(client)
        r = client.delete(f"{WO_URL}/{wid}")
        assert r.status_code == 200
        # 删除后查不到
        assert client.get(f"{WO_URL}/{wid}").status_code == 404

    def test_delete_not_found(self, client):
        r = client.delete(f"{WO_URL}/WO-NOPE")
        assert r.status_code == 404


class TestLogs:
    def test_logs_ok(self, client, db_session):
        wid = _seed_wo(db_session, "WO-LG-001")
        db_session.add(WorkOrderLog(order_id=wid, action="created", description="创建"))
        db_session.commit()
        r = client.get(f"{WO_URL}/{wid}/logs")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1
        assert r.json()["data"]["items"][0]["action"] == "created"

    def test_logs_empty(self, client, db_session):
        wid = _seed_wo(db_session, "WO-LG-002")
        r = client.get(f"{WO_URL}/{wid}/logs")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0


class TestAuth:
    def test_anon_denied(self, anon_client):
        r = anon_client.get(WO_URL)
        assert r.status_code == 401

    def test_viewer_create_forbidden(self, client, seed_users):
        """viewer 无 workorder:edit 写权限 → 403"""
        seed_users
        login_as(client, "viewer1", "view123")
        r = client.post(WO_URL, json={"fault_desc": "x"})
        assert r.status_code == 403
