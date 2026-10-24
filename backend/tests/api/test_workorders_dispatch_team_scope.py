"""tests/api/test_workorders_dispatch_team_scope.py — 派单/转单工程师池跨团队水平越权 (卡 3ad52033)

缺陷 (修复前): routes_workflow.py 中
- dispatch_workorder 工程师池 `User.role == ENGINEER` 全局拉取, 无 team 过滤
  → 团队级用户可看到并指派所有团队工程师 (水平越权信息泄漏 + 跨团队派单)
- transfer_workorder 转单目标 `User.id == target, role == ENGINEER` 无 team 过滤
  → 团队级用户可把本团队工单转给其他团队工程师 (跨团队越权)

修复契约:
- 非 admin (团队级) 用户: 工程师池/转单目标必须 User.team_id == user.team_id
- admin 平台级豁免, 保持全量 (现状不变)
- 跨团队目标工程师 → 404 (与 _check_workorder_team 语义一致, 不泄露存在)
"""
import uuid

import bcrypt

from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
from app.models.workorder import WorkOrder, WorkOrderStatus
from tests.api._helpers import WO_URL, login_admin, login_as


def _uname(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _add_user(s, username, *, role=UserRole.DISPATCHER, team_id=None,
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


def _make_team_station(s, team_id: int) -> Station:
    sta = Station(
        name=f"团队站{team_id}",
        code=f"TM{team_id}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    s.add(sta)
    s.commit()
    s.refresh(sta)
    return sta


def _make_wo(s, *, station_id=None, assignee_id=None,
             status=WorkOrderStatus.PENDING) -> WorkOrder:
    wo = WorkOrder(
        id=f"WO-TS-{uuid.uuid4().hex[:12]}",
        fault_desc="跨团队工程师池测试",
        type="repair",
        level="warning",
        status=status,
        station_id=station_id,
        assignee_id=assignee_id,
    )
    s.add(wo)
    s.commit()
    s.refresh(wo)
    return wo


def test_dispatch_team_pool_scoped_to_own_team(client):
    """团队级用户派单: 工程师池仅本团队工程师, assignee 必落本团队 (跨团队不入池)。"""
    s = client._sesh
    team = 91001
    sta = _make_team_station(s, team)
    own_eng = _add_user(s, _uname("eng_own"), role=UserRole.ENGINEER, team_id=team)
    # 跨团队工程师 + 全局无团队工程师都存在, 修复前会被全局拉入池
    _add_user(s, _uname("eng_other"), role=UserRole.ENGINEER, team_id=9999)
    _add_user(s, _uname("eng_global"), role=UserRole.ENGINEER, team_id=None)
    dispatcher = _add_user(s, _uname("disp_team"), role=UserRole.DISPATCHER, team_id=team)
    wo = _make_wo(s, station_id=sta.id)

    try:
        login_as(client, dispatcher.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
        assert r.status_code == 200, f"派单失败: {r.status_code} {r.text[:300]}"
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.assignee_id == own_eng.id  # 池内唯一人选 = 本团队工程师
    finally:
        login_admin(client)


def test_dispatch_team_no_cross_team_engineer_404(client):
    """团队级用户派单: 本团队无工程师 (仅他团队有) → 404, 不跨团队指派。"""
    s = client._sesh
    team = 91002
    sta = _make_team_station(s, team)
    _add_user(s, _uname("eng_other2"), role=UserRole.ENGINEER, team_id=9999)
    dispatcher = _add_user(s, _uname("disp_team2"), role=UserRole.DISPATCHER, team_id=team)
    wo = _make_wo(s, station_id=sta.id)

    try:
        login_as(client, dispatcher.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
        assert r.status_code == 404  # 本团队池空 → 404, 绝不落跨团队工程师
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.assignee_id is None
    finally:
        login_admin(client)


def test_dispatch_admin_full_pool_not_regressed(client):
    """admin 派单保持全量池: 无团队身份仍可指派有团队工程师 (现状不回归)。"""
    s = client._sesh
    eng = _add_user(s, _uname("eng_admin_pool"), role=UserRole.ENGINEER, team_id=424242)
    wo = _make_wo(s, station_id=None)

    r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
    assert r.status_code == 200
    s.expire_all()
    wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
    assert wo_db.assignee_id == eng.id


def test_transfer_cross_team_target_404(client):
    """团队级用户转单给跨团队工程师 → 404 (与 _check_workorder_team 语义一致)。"""
    s = client._sesh
    team = 91003
    sta = _make_team_station(s, team)
    own_eng = _add_user(s, _uname("eng_from"), role=UserRole.ENGINEER, team_id=team)
    cross_eng = _add_user(s, _uname("eng_cross_target"), role=UserRole.ENGINEER, team_id=9999)
    dispatcher = _add_user(s, _uname("disp_team3"), role=UserRole.DISPATCHER, team_id=team)
    wo = _make_wo(s, station_id=sta.id, assignee_id=own_eng.id)

    try:
        login_as(client, dispatcher.username, "pass123")
        r = client.post(
            f"{WO_URL}/{wo.id}/transfer",
            json={"target_engineer_id": cross_eng.id, "reason": "测试跨团队转单"},
        )
        assert r.status_code == 404
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.assignee_id == own_eng.id  # 转单未生效
    finally:
        login_admin(client)


def test_transfer_same_team_target_ok(client):
    """团队级用户转单给本团队工程师 → 200 (对照, 不误伤正常流程)。"""
    s = client._sesh
    team = 91004
    sta = _make_team_station(s, team)
    eng_from = _add_user(s, _uname("eng_from2"), role=UserRole.ENGINEER, team_id=team)
    eng_to = _add_user(s, _uname("eng_to2"), role=UserRole.ENGINEER, team_id=team)
    dispatcher = _add_user(s, _uname("disp_team4"), role=UserRole.DISPATCHER, team_id=team)
    wo = _make_wo(s, station_id=sta.id, assignee_id=eng_from.id)

    try:
        login_as(client, dispatcher.username, "pass123")
        r = client.post(
            f"{WO_URL}/{wo.id}/transfer",
            json={"target_engineer_id": eng_to.id, "reason": "本团队正常转单"},
        )
        assert r.status_code == 200, f"转单失败: {r.status_code} {r.text[:300]}"
        s.expire_all()
        wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
        assert wo_db.assignee_id == eng_to.id
    finally:
        login_admin(client)


def test_transfer_admin_cross_team_not_regressed(client):
    """admin 转单保持全量: 无团队约束仍可转给任意工程师 (现状不回归)。"""
    s = client._sesh
    eng_from = _add_user(s, _uname("eng_from3"), role=UserRole.ENGINEER, team_id=111)
    eng_to = _add_user(s, _uname("eng_to3"), role=UserRole.ENGINEER, team_id=9999)
    wo = _make_wo(s, station_id=None, assignee_id=eng_from.id)

    r = client.post(
        f"{WO_URL}/{wo.id}/transfer",
        json={"target_engineer_id": eng_to.id, "reason": "admin 跨团队转单"},
    )
    assert r.status_code == 200
    s.expire_all()
    wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
    assert wo_db.assignee_id == eng_to.id
