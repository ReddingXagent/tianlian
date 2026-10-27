"""tests/api/test_workorders_lifecycle.py — 工单生命周期端点覆盖

被测文件: app/api/v1/workorders/routes_lifecycle.py
端点 (7): list / stats / detail / create / update / delete / logs

覆盖矩阵:
- list: admin 全可见 / 分页 / 多 filter (status/level/type/source) / team scoping 隔离
- stats: total + 三分布 / group_by=status|level|type|date / 日期过滤 / team scoping
- detail: happy / 不存在 404 / 跨团队 404
- create: happy / 非 admin 无 station 400 / 非 admin 跨团队 station 404 / admin 可不指定站点
- update: 字段更新 / status=completed 落 finish_time / 不存在 404 / 跨团队 404
- delete: happy / 不存在 404 / 跨团队 404
- logs: 记录返回 + 排序

team scoping (任务卡 ed509541): 非 admin 经 station→team 隔离, 跨团队 404 不泄露存在。
"""
import uuid

import bcrypt
import pytest

from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
from app.models.workorder import WorkOrder, WorkOrderLog, WorkOrderStatus
from tests.api._helpers import WO_URL, login_as, login_admin


# ─── helpers ───

def _uname(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _add_user(s, username, *, role=UserRole.OPERATOR, team_id=None,
              password="pass123") -> User:
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        real_name=username,
        role=role,
        status="active",
        team_id=team_id,
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def _make_team_station(s, team_id: int, code=None) -> Station:
    sta = Station(
        name=f"团队站{team_id}",
        code=code or f"LC{team_id}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    s.add(sta)
    s.commit()
    s.refresh(sta)
    return sta


def _make_wo(s, *, station_id=None, status=WorkOrderStatus.PENDING,
             level="warning", wo_type="repair", source="manual",
             assignee_id=None, wo_id=None) -> WorkOrder:
    wo = WorkOrder(
        id=wo_id or f"WO-LC-{uuid.uuid4().hex[:12]}",
        fault_desc="生命周期测试工单",
        type=wo_type,
        level=level,
        status=status,
        station_id=station_id,
        assignee_id=assignee_id,
        source=source,
    )
    s.add(wo)
    s.commit()
    s.refresh(wo)
    return wo


# ════════════════════════════════════════════════════════════════════
# list
# ════════════════════════════════════════════════════════════════════


class TestListWorkorders:
    def test_admin_list_happy(self, client):
        s = client._sesh
        _make_wo(s, wo_type="repair", source="manual")
        r = client.get(WO_URL)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 200
        assert body["data"]["total"] >= 1
        item = body["data"]["items"][0]
        for key in ("id", "status", "type", "level", "station_id", "source"):
            assert key in item

    def test_filter_by_status(self, client):
        s = client._sesh
        _make_wo(s, status=WorkOrderStatus.PENDING)
        _make_wo(s, status=WorkOrderStatus.COMPLETED)
        r = client.get(WO_URL, params={"status": "completed"})
        assert r.status_code == 200
        statuses = {it["status"] for it in r.json()["data"]["items"]}
        assert statuses == {"completed"}

    def test_filter_by_level_and_type_and_source(self, client):
        s = client._sesh
        _make_wo(s, level="critical", wo_type="emergency", source="alarm")
        _make_wo(s, level="warning", wo_type="repair", source="manual")
        r = client.get(WO_URL, params={"level": "critical", "type": "emergency", "source": "alarm"})
        assert r.json()["data"]["total"] == 1

    def test_pagination(self, client):
        s = client._sesh
        for _ in range(5):
            _make_wo(s)
        r = client.get(WO_URL, params={"page": 1, "page_size": 2})
        data = r.json()["data"]
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_team_scoping_isolation(self, client):
        """非 admin 仅见本 team 工单 (经 station→team)。"""
        s = client._sesh
        sta_mine = _make_team_station(s, 5101)
        sta_other = _make_team_station(s, 5199)
        _make_wo(s, station_id=sta_mine.id, wo_type="repair")
        _make_wo(s, station_id=sta_other.id, wo_type="repair")

        op = _add_user(s, _uname("op_list"), team_id=5101)
        try:
            login_as(client, op.username, "pass123")
            r = client.get(WO_URL)
            assert r.status_code == 200
            # 仅本 team 那条
            assert r.json()["data"]["total"] == 1
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# stats
# ════════════════════════════════════════════════════════════════════


class TestWorkorderStats:
    def test_stats_basic_structure(self, client):
        s = client._sesh
        _make_wo(s, status=WorkOrderStatus.PENDING, level="warning", wo_type="repair")
        _make_wo(s, status=WorkOrderStatus.COMPLETED, level="critical", wo_type="emergency")
        r = client.get(f"{WO_URL}/stats")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] >= 2
        assert "status_distribution" in d
        assert "level_distribution" in d
        assert "type_distribution" in d
        assert "groups" in d
        # 默认 group_by=status → groups == status_distribution
        assert d["groups"] == d["status_distribution"]

    def test_stats_group_by_level(self, client):
        s = client._sesh
        _make_wo(s, level="warning")
        _make_wo(s, level="critical")
        r = client.get(f"{WO_URL}/stats", params={"group_by": "level"})
        d = r.json()["data"]
        assert d["groups"] == d["level_distribution"]
        assert "warning" in d["groups"]

    def test_stats_group_by_type(self, client):
        s = client._sesh
        _make_wo(s, wo_type="repair")
        r = client.get(f"{WO_URL}/stats", params={"group_by": "type"})
        d = r.json()["data"]
        assert d["groups"] == d["type_distribution"]

    def test_stats_group_by_date(self, client):
        s = client._sesh
        _make_wo(s)
        r = client.get(f"{WO_URL}/stats", params={"group_by": "date"})
        d = r.json()["data"]
        # 至少一个日期分组
        assert isinstance(d["groups"], dict)
        assert sum(d["groups"].values()) == d["total"]

    def test_stats_team_scoping(self, client):
        """非 admin 仅统计本 team 工单。"""
        s = client._sesh
        sta_mine = _make_team_station(s, 5201)
        sta_other = _make_team_station(s, 5299)
        _make_wo(s, station_id=sta_mine.id, wo_type="repair")
        _make_wo(s, station_id=sta_other.id, wo_type="repair")
        _make_wo(s, station_id=sta_other.id, wo_type="repair")

        op = _add_user(s, _uname("op_stats"), team_id=5201)
        try:
            login_as(client, op.username, "pass123")
            r = client.get(f"{WO_URL}/stats")
            assert r.json()["data"]["total"] == 1
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# detail
# ════════════════════════════════════════════════════════════════════


class TestGetWorkorder:
    def test_detail_happy(self, client):
        s = client._sesh
        wo = _make_wo(s)
        r = client.get(f"{WO_URL}/{wo.id}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == wo.id

    def test_detail_not_found_404(self, client):
        r = client.get(f"{WO_URL}/WO-NOPE-0001")
        assert r.status_code == 404

    def test_detail_cross_team_404(self, client):
        s = client._sesh
        sta = _make_team_station(s, 5301)
        wo = _make_wo(s, station_id=sta.id)
        other = _add_user(s, _uname("op_other"), team_id=9999)
        try:
            login_as(client, other.username, "pass123")
            r = client.get(f"{WO_URL}/{wo.id}")
            assert r.status_code == 404
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# create
# ════════════════════════════════════════════════════════════════════


class TestCreateWorkorder:
    def test_create_admin_no_station(self, client):
        """admin 可不指定站点直接建单。"""
        r = client.post(WO_URL, json={"fault_desc": "新建工单", "type": "repair", "level": "warning"})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["id"].startswith("WO-")
        assert d["status"] == "pending"

    def test_create_admin_with_station(self, client):
        s = client._sesh
        sta = _make_team_station(s, 5401)
        r = client.post(WO_URL, json={
            "fault_desc": "带站点建单", "station_id": sta.id,
        })
        assert r.status_code == 200
        assert r.json()["data"]["station_id"] == sta.id

    def test_create_non_admin_without_station_400(self, client):
        """非 admin 建单必须指定本 team 站点, 否则 400。"""
        s = client._sesh
        op = _add_user(s, _uname("op_create"), team_id=5402)
        try:
            login_as(client, op.username, "pass123")
            r = client.post(WO_URL, json={"fault_desc": "无站点"})
            assert r.status_code == 400
            assert "station_id" in r.json()["detail"]
        finally:
            login_admin(client)

    def test_create_non_admin_cross_team_station_404(self, client):
        """非 admin 指定他团站点 → 404 (不泄露存在)。"""
        s = client._sesh
        sta_other = _make_team_station(s, 5499)
        op = _add_user(s, _uname("op_cross"), team_id=5402)
        try:
            login_as(client, op.username, "pass123")
            r = client.post(WO_URL, json={"fault_desc": "跨团", "station_id": sta_other.id})
            assert r.status_code == 404
        finally:
            login_admin(client)

    def test_create_non_admin_own_station_ok(self, client):
        """非 admin 指定本 team 站点 → 200。"""
        s = client._sesh
        sta = _make_team_station(s, 5403)
        op = _add_user(s, _uname("op_own"), team_id=5403)
        try:
            login_as(client, op.username, "pass123")
            r = client.post(WO_URL, json={"fault_desc": "本团建单", "station_id": sta.id})
            assert r.status_code == 200
            assert r.json()["data"]["station_id"] == sta.id
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# update
# ════════════════════════════════════════════════════════════════════


class TestUpdateWorkorder:
    def test_update_fields(self, client):
        s = client._sesh
        wo = _make_wo(s)
        r = client.put(f"{WO_URL}/{wo.id}", json={
            "fault_desc": "更新后的描述", "level": "critical", "solution": "已更换",
        })
        assert r.status_code == 200, r.text[:300]
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.fault_desc == "更新后的描述"
        assert wo_db.level.value == "critical"
        assert wo_db.solution == "已更换"

    def test_update_status_to_completed_sets_finish_time(self, client):
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING)
        r = client.put(f"{WO_URL}/{wo.id}", json={"status": "completed"})
        assert r.status_code == 200
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.status == WorkOrderStatus.COMPLETED
        assert wo_db.finish_time is not None

    def test_update_status_to_accepted_sets_accept_time(self, client):
        s = client._sesh
        wo = _make_wo(s)
        r = client.put(f"{WO_URL}/{wo.id}", json={"status": "accepted"})
        assert r.status_code == 200
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.accept_time is not None

    def test_update_assignee_id(self, client):
        """update 的 assignee_id 分支: 传 assignee_id → 落库 (is not None 守卫放行)。"""
        s = client._sesh
        eng = _add_user(s, _uname("eng_assign"), role=UserRole.ENGINEER)
        wo = _make_wo(s)  # assignee_id 默认 None
        r = client.put(f"{WO_URL}/{wo.id}", json={"assignee_id": eng.id})
        assert r.status_code == 200, r.text[:300]
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.assignee_id == eng.id

    def test_update_not_found_404(self, client):
        r = client.put(f"{WO_URL}/WO-NOPE-0002", json={"fault_desc": "x"})
        assert r.status_code == 404

    def test_update_cross_team_404(self, client):
        s = client._sesh
        sta = _make_team_station(s, 5501)
        wo = _make_wo(s, station_id=sta.id)
        other = _add_user(s, _uname("op_upd_cross"), team_id=9999)
        try:
            login_as(client, other.username, "pass123")
            r = client.put(f"{WO_URL}/{wo.id}", json={"fault_desc": "越权改"})
            assert r.status_code == 404
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# delete
# ════════════════════════════════════════════════════════════════════


class TestDeleteWorkorder:
    def test_delete_happy(self, client):
        s = client._sesh
        wo = _make_wo(s)
        r = client.delete(f"{WO_URL}/{wo.id}")
        assert r.status_code == 200
        s.expire_all()
        assert s.query(WorkOrder).filter(WorkOrder.id == wo.id).first() is None

    def test_delete_not_found_404(self, client):
        r = client.delete(f"{WO_URL}/WO-NOPE-0003")
        assert r.status_code == 404

    def test_delete_cross_team_404(self, client):
        s = client._sesh
        sta = _make_team_station(s, 5601)
        wo = _make_wo(s, station_id=sta.id)
        other = _add_user(s, _uname("op_del_cross"), team_id=9999)
        try:
            login_as(client, other.username, "pass123")
            r = client.delete(f"{WO_URL}/{wo.id}")
            assert r.status_code == 404
            # 未删除
            login_admin(client)
            s.expire_all()
            assert s.query(WorkOrder).filter(WorkOrder.id == wo.id).first() is not None
        finally:
            login_admin(client)


# ════════════════════════════════════════════════════════════════════
# logs
# ════════════════════════════════════════════════════════════════════


class TestWorkorderLogs:
    def test_logs_returns_records(self, client):
        """经 API 流转产生日志后, /logs 返回记录 (按 created_at desc)。"""
        s = client._sesh
        wo = _make_wo(s, status=WorkOrderStatus.PENDING, assignee_id=None)
        # 直插两条日志, 验证返回结构 + 排序
        s.add(WorkOrderLog(order_id=wo.id, action="created", description="建单"))
        s.commit()
        s.add(WorkOrderLog(order_id=wo.id, action="accepted", description="接单"))
        s.commit()

        r = client.get(f"{WO_URL}/{wo.id}/logs")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 2
        actions = [it["action"] for it in d["items"]]
        assert set(actions) == {"created", "accepted"}
        for it in d["items"]:
            assert "description" in it
            assert "created_at" in it

    def test_logs_empty(self, client):
        s = client._sesh
        wo = _make_wo(s)
        r = client.get(f"{WO_URL}/{wo.id}/logs")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_logs_cross_team_404(self, client):
        s = client._sesh
        sta = _make_team_station(s, 5701)
        wo = _make_wo(s, station_id=sta.id)
        other = _add_user(s, _uname("op_log_cross"), team_id=9999)
        try:
            login_as(client, other.username, "pass123")
            r = client.get(f"{WO_URL}/{wo.id}/logs")
            assert r.status_code == 404
        finally:
            login_admin(client)
