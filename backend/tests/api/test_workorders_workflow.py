"""tests/api/test_workorders_workflow.py — 工单工作流状态机收口 + 行锁防双接单 + 自验收拦截

夜班审计回归保护: app/api/v1/workorders/routes_workflow.py 三处缺陷修复的 RED→GREEN。
被测端点: accept / start / complete / verify / reject / dispatch / transfer / urge。

覆盖:
① A套状态机全路径 (pending→accepted→processing→pending_verify→completed + 驳回回退环)
② B套遗留状态 (assigned/in_progress/resolved/closed) 对各 workflow 端点 → 显式 400
   (消息点名"遗留/外部同步状态", 非静默卡死单)
③ 双接单并发: 2 线程同时 accept 同一 pending 单 → 恰一个成功, 一个 409
   (原子条件 UPDATE WHERE status=pending 兜底; SQLite 写锁串行化 UPDATE)
④ 自验收: assignee 验收自己工单 → 400 (对照: assignee≠验收人 → 200)
⑤ 非 assignee 完成 → 403 (同团队但非指派人; 对照: assignee 本人 → 200)
⑥ team scoping 跨团队 → 404 不回归

工程要点:
- SessionLocal 取值必须经 ``app.core.database`` 模块属性运行时获取 (client fixture 已
  override 模块级 SessionLocal 指向本测试库); 顶层 ``from ... import SessionLocal``
  会绑定生产库 → 子线程连错库 (记忆 service-sessionlocal-import-binding-test-pitfall)。
- 并发测试铁律: threading.Barrier(N) 的 N 严格等于实际调用 wait() 的线程数 (见
  tests/core/test_station_router_concurrency.py)。本文件 Barrier(2) == 2 worker。
- 双接单并发用 admin (平台管理员) 跳过 team scoping/assignee 校验, 孤立并发机制本身。
- 现有 admin 驱动的流转 (test_workorders.py) assignee_id 恒为空 → actor 守卫不误伤。
"""
import threading
import uuid

import bcrypt
import pytest

import app.core.database as db_module
from app.api.v1.workorders.routes_workflow import accept_workorder
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
from app.models.workorder import WorkOrder, WorkOrderStatus
from fastapi import HTTPException
from tests.api._helpers import WO_URL, advance_wo, create_wo, login_admin, login_as


# ─── 共用 setup helpers (经 client._sesh 直接控 status/assignee/station, 绕过 API) ───


def _uname(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _make_wo(s, *, station_id=None, assignee_id=None, status=WorkOrderStatus.PENDING,
             wo_id=None) -> WorkOrder:
    """直接在 session s 建工单, 精确控制 status/assignee/station (跳过 API 流转)。"""
    wo = WorkOrder(
        id=wo_id or f"WO-TEST-{uuid.uuid4().hex[:12]}",
        fault_desc="测试故障",
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


def _add_user(s, username, *, role=UserRole.ENGINEER, team_id=None,
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


# ════════════════════════════════════════════════════════════════════
# ① A套状态机全路径
# ════════════════════════════════════════════════════════════════════


def test_a_set_full_lifecycle_green(client):
    """A套完整流转: pending→accepted→processing→pending_verify→completed 全绿。"""
    wo_id = create_wo(client, fault_desc="全路径流转")
    # 初始 pending
    r = client.get(f"{WO_URL}/{wo_id}")
    assert r.json()["data"]["status"] == "pending"

    advance_wo(client, wo_id, "accept", "start", "complete=修好了", "verify")
    r = client.get(f"{WO_URL}/{wo_id}")
    assert r.json()["data"]["status"] == "completed"


def test_a_set_reject_loop_green(client):
    """驳回回退环: pending_verify → reject → processing, 可再次 complete/verify。"""
    wo_id = create_wo(client)
    advance_wo(client, wo_id, "accept", "start", "complete")
    r = client.post(f"{WO_URL}/{wo_id}/reject", params={"reason": "不合格"})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "processing"
    # 回到 processing 后可再次 complete → verify
    advance_wo(client, wo_id, "complete=整改", "verify")
    r = client.get(f"{WO_URL}/{wo_id}")
    assert r.json()["data"]["status"] == "completed"


# ════════════════════════════════════════════════════════════════════
# ② B套遗留状态显式拒绝 (状态机收口·缺陷1)
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("legacy_status", [
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.RESOLVED,
    WorkOrderStatus.CLOSED,
])
def test_b_set_legacy_status_rejected_explicit_400(client, legacy_status):
    """B套遗留状态对各 workflow 端点 → 显式 400 (点名遗留状态, 非静默死单)。

    RED(修复前): 这些状态因不满足 A套前置态返回泛 400 ("当前状态不允许X"),
        等同静默卡死。GREEN: _reject_legacy_status 点名"遗留/外部同步状态"。
    """
    s = client._sesh
    wo = _make_wo(s, status=legacy_status)

    for action in ("accept", "start", "complete", "verify", "dispatch"):
        r = client.post(f"{WO_URL}/{wo.id}/{action}")
        assert r.status_code == 400, (
            f"{action} 命中遗留状态 {legacy_status.value}: 期望 400, 实际 {r.status_code} {r.text[:200]}"
        )
        detail = r.json()["detail"]
        assert "遗留" in detail or "外部同步" in detail, (
            f"{action} 未点名遗留状态, detail={detail!r}"
        )


# ════════════════════════════════════════════════════════════════════
# ③ 双接单并发 (行锁防双接单·缺陷2)
# ════════════════════════════════════════════════════════════════════


def test_double_accept_concurrent_exactly_one_wins(client):
    """双接单并发: 2 线程同时 accept 同一 pending 单 → 恰一个成功, 一个 409。

    GREEN(修复后): accept 在 with_for_update 之外叠加原子条件 UPDATE
        (WHERE status=pending); SQLite 写锁串行化 UPDATE 语句, 败者匹配 0 行 → 409,
        跨后端保证"恰一个工程师接单成功"。
    RED(修复前证据见验收报告): 无条件 read-check-assign-commit 旧逻辑, 两线程都过
        PENDING 检查 → 都成功 (双接单)。

    并发铁律: Barrier(2) == 2 个 worker 的 wait() 调用数 (主线程不参与)。
    用 admin 跳过 team scoping/assignee 校验, 孤立双接单机制本身。
    """
    wo_id = create_wo(client)  # admin 建单, pending, assignee_id=None (抢单池)

    # 确认初始 pending (新 session, 避开 client._sesh 缓存)
    chk = db_module.SessionLocal()
    try:
        assert chk.query(WorkOrder).filter(WorkOrder.id == wo_id).one().status == WorkOrderStatus.PENDING
    finally:
        chk.close()

    barrier = threading.Barrier(2)  # 严格 == worker 线程数
    outcomes: list = []
    outcomes_lock = threading.Lock()

    def worker():
        sess = db_module.SessionLocal()  # 运行时取 override 后的测试库 sessionmaker
        try:
            admin = sess.query(User).filter(User.username == "admin").one()
            barrier.wait()  # 两线程同时放行, 最大化 check-then-set 竞态窗口
            try:
                accept_workorder(workorder_id=wo_id, db=sess, user=admin)
                with outcomes_lock:
                    outcomes.append("ok")
            except HTTPException as e:
                with outcomes_lock:
                    outcomes.append(e.status_code)
        finally:
            sess.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert all(not t.is_alive() for t in threads), "并发 accept 线程未在超时内结束 → 死锁"

    # 恰一个接单成功
    assert outcomes.count("ok") == 1, f"期望恰一个接单成功, 实际 outcomes={outcomes}"
    # 败者 409 (并发抢输)
    assert outcomes.count(409) == 1, f"期望败者 409, 实际 outcomes={outcomes}"

    # 终态: accepted (无双接单)
    fin = db_module.SessionLocal()
    try:
        wo = fin.query(WorkOrder).filter(WorkOrder.id == wo_id).one()
        assert wo.status == WorkOrderStatus.ACCEPTED
    finally:
        fin.close()


def test_accept_sequential_wrong_status_still_400(client):
    """顺序二次接单 (非并发) → 仍 400 (状态校验), 不误触 409 路径。

    回归保护: 原子条件 UPDATE 仅在并发败者(读检查与 UPDATE 之间被他事务改状态)时 409;
    顺序场景第二次接单时 status 已 accepted, 走前置状态校验 → 400。
    """
    wo_id = create_wo(client)
    r1 = client.post(f"{WO_URL}/{wo_id}/accept")
    assert r1.status_code == 200
    r2 = client.post(f"{WO_URL}/{wo_id}/accept")
    assert r2.status_code == 400, f"顺序二次接单应 400, 实际 {r2.status_code} {r2.text[:200]}"


# ════════════════════════════════════════════════════════════════════
# ④ 自验收拦截 (越权·缺陷3)
# ════════════════════════════════════════════════════════════════════


def test_self_verify_blocked_400(client):
    """自验收 → 400: assignee_id == 验收人。

    admin 既是 assignee 又验收 → 400。自验收守卫无管理员豁免 (站长不应验收自己处理的工单)。
    """
    s = client._sesh
    admin = s.query(User).filter(User.username == "admin").one()
    wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY, assignee_id=admin.id)

    r = client.post(f"{WO_URL}/{wo.id}/verify")
    assert r.status_code == 400
    assert "自验收" in r.json()["detail"]


def test_other_assignee_verify_ok_contrast(client):
    """对照: assignee_id ≠ 验收人 → 正常验收 200 (证明 400 源于 assignee==verifier)。"""
    s = client._sesh
    other = _add_user(s, _uname("eng_assignee_other"))  # assignee 是别人 (非当前 admin)
    wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY, assignee_id=other.id)

    r = client.post(f"{WO_URL}/{wo.id}/verify")  # admin 验收, admin != other
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "completed"


# ════════════════════════════════════════════════════════════════════
# ⑤ 非 assignee 完成 (越权·缺陷3)
# ════════════════════════════════════════════════════════════════════


def test_non_assignee_complete_blocked_403(client):
    """非 assignee 完成 → 403: 同团队、有 workorder:edit 权限, 但非指派人。

    setup: 团队站 + 两同团队工程师 (E1=assignee, E2≠assignee) + 工单 processing/assignee=E1。
    E2 完成 → 403; 对照 E1 完成 → 200。
    """
    s = client._sesh
    team = 7001
    sta = _make_team_station(s, team)
    e1 = _add_user(s, _uname("eng_assignee"), team_id=team)     # 指派人
    e2 = _add_user(s, _uname("eng_other"), team_id=team)        # 非指派人
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, assignee_id=e1.id, station_id=sta.id)

    try:
        # E2 (同团队, 非指派) 完成 → 403
        login_as(client, e2.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/complete", params={"solution": "替人完成"})
        assert r.status_code == 403, f"非 assignee 完成应 403, 实际 {r.status_code} {r.text[:200]}"
        assert "指派工程师" in r.json()["detail"]

        # E1 (指派人本人) 完成 → 200
        login_as(client, e1.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/complete", params={"solution": "本人完成"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "pending_verify"
    finally:
        login_admin(client)


def test_admin_can_complete_others_wo(client):
    """管理员豁免: admin 可完成任意工单 (即使 assignee 是别人), 支持代完成。"""
    s = client._sesh
    team = 7002
    sta = _make_team_station(s, team)
    e1 = _add_user(s, _uname("eng_a"), team_id=team)
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, assignee_id=e1.id, station_id=sta.id)

    # admin 完成 (assignee=e1 ≠ admin, 但 is_platform_admin 豁免)
    r = client.post(f"{WO_URL}/{wo.id}/complete", params={"solution": "管理员代办"})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "pending_verify"


# ════════════════════════════════════════════════════════════════════
# ⑥ team scoping 跨团队 → 404 不回归
# ════════════════════════════════════════════════════════════════════


def test_team_scoping_cross_team_404(client):
    """team scoping 不回归: 跨团队用户访问有团队工单 → 404 (不泄露存在)。

    team 校验先于 legacy/状态校验, 跨团队一律 404。
    """
    s = client._sesh
    team = 8001
    sta = _make_team_station(s, team)
    e_other_team = _add_user(s, _uname("eng_other_team"), team_id=9999)  # 不同团队
    wo = _make_wo(s, status=WorkOrderStatus.PENDING, station_id=sta.id)

    try:
        login_as(client, e_other_team.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/accept")
        assert r.status_code == 404  # 跨团队 → 404 (不泄露存在)
    finally:
        login_admin(client)


# ═════════════════════════════════════════════════════════════════════
# ⑦ dispatch 派单端点 (独立覆盖: 成功 / 无工程师 / 非 pending / 不存在)
# ═════════════════════════════════════════════════════════════════════


def test_dispatch_happy_assigns_engineer(client):
    """派单成功: pending 工单 + 存在 ENGINEER → status=processing, assignee 落定。

    无站点工单路径 (station_id=None): 验证派单核心逻辑 (工程师评分/指派/状态流转) 成立。
    """
    s = client._sesh
    eng = _add_user(s, _uname("eng_dispatch"))  # ENGINEER 角色, 入工程师池
    wo = _make_wo(s, status=WorkOrderStatus.PENDING, station_id=None)

    r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
    assert r.status_code == 200, f"派单失败: {r.status_code} {r.text[:300]}"
    d = r.json()["data"]
    assert d["engineer"]["id"] == eng.id
    assert "score" in d
    # 落库: processing + assignee
    s.expire_all()
    wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
    assert wo_db.status == WorkOrderStatus.PROCESSING
    assert wo_db.assignee_id == eng.id


def test_dispatch_happy_with_station_assigns_engineer(client):
    """带站点工单派单成功: station.lat/lon 正确读取, 不再 AttributeError → 500。

    RED(修复前): routes_workflow.py L141 读 station.latitude/longitude, 但 Station 模型
        列名是 lat/lon (无 latitude/longitude 列), 带 station_id 的工单派单触发
        AttributeError → 500。GREEN: 改读 station.lat/lon → 200。
    """
    s = client._sesh
    eng = _add_user(s, _uname("eng_dispatch_st"))  # ENGINEER 角色, 入工程师池
    sta = _make_team_station(s, 7401)
    wo = _make_wo(s, status=WorkOrderStatus.PENDING, station_id=sta.id)

    r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
    assert r.status_code == 200, f"带站点工单派单失败: {r.status_code} {r.text[:300]}"
    d = r.json()["data"]
    assert d["engineer"]["id"] == eng.id
    # 落库: processing + assignee
    s.expire_all()
    wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
    assert wo_db.status == WorkOrderStatus.PROCESSING
    assert wo_db.assignee_id == eng.id


def test_dispatch_no_engineer_available_404(client):
    """无可用工程师 → 404 (DB 清空 ENGINEER 角色用户)。"""
    s = client._sesh
    # 删除所有 ENGINEER 角色用户, 使工程师池为空
    s.query(User).filter(User.role == UserRole.ENGINEER).delete(synchronize_session=False)
    s.commit()
    wo_id = create_wo(client)  # admin 建单 (pending)

    r = client.post(f"{WO_URL}/{wo_id}/dispatch", json={"auto": True})
    assert r.status_code == 404
    assert "工程师" in r.json()["detail"]


def test_dispatch_non_pending_400(client):
    """非 pending 工单派单 → 400 (状态不允许)。"""
    s = client._sesh
    _add_user(s, _uname("eng_disp2"))
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
    r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
    assert r.status_code == 400


def test_dispatch_not_found_404(client):
    """派单不存在的工单 → 404。"""
    r = client.post(f"{WO_URL}/WO-NOPE-9999/dispatch", json={"auto": True})
    assert r.status_code == 404


# ─── 卡 d9076d31: 智能派单绩效聚合下推 + avg_hours 分母修复 ───


def _score_details_for(client, wo, username):
    """dispatch 200 后, 从 workorder 指派结果反查 score_details 不直接暴露 →
    用绩效路径单工程师断言: 直接调端点, 返回 details.performance 即该工程师评分。"""
    r = client.post(f"{WO_URL}/{wo.id}/dispatch", json={"auto": True})
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()["data"]["details"]


def _expected_perf_score(completion_rate: float, avg_hours: float) -> float:
    """按 dispatch_engine._score_performance 公式手工推演绩效分 (0-100)。"""
    score1 = completion_rate * 0.4
    score2 = (4.5 / 5) * 40  # satisfaction 硬编码 4.5
    score3 = max(0, min(20, 20 - avg_hours))
    return score1 + score2 + score3


@pytest.mark.parametrize("at,ft,expected_avg,expected_cr", [
    # 双时间戳齐全: 均值只算有效样本 (2h+4h → 3.0, 非 1.5)
    (True, True, 3.0, 66.7),
    # 全缺时间戳: 回退 3.5; 完成率仍按 completed/总数
    (False, False, 3.5, 66.7),
])
def test_dispatch_avg_hours_denominator_fixed(client, at, ft, expected_avg, expected_cr):
    """RED(修复前): avg_hours 分母=全部 completed (含缺时间戳样本) → 低估;
    全缺时间戳时 avg=0 误导。GREEN: 分母只计 accept+finish 均非空样本;
    有效样本=0 回退 3.5。单工程师池 → details.performance 即该工程师绩效分,
    用公式反推 avg_hours/completion_rate 是否落在修复后口径。
    """
    s = client._sesh
    eng = _add_user(s, _uname("eng_avgh"))
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)

    def _ts(offset_h):
        return base + timedelta(hours=offset_h) if offset_h is not None else None

    _at = _ts(0) if at else None
    _ft1 = _ts(2) if ft else None
    _ft2 = _ts(4) if ft else None
    # 2 completed (2h / 4h) + 1 pending → completion_rate = 2/3
    for i, (st, ft_) in enumerate([
        (WorkOrderStatus.COMPLETED, _ft1),
        (WorkOrderStatus.COMPLETED, _ft2),
        (WorkOrderStatus.PENDING, None),
    ]):
        s.add(WorkOrder(
            id=f"WO-AVGH-{uuid.uuid4().hex[:10]}",
            fault_desc="绩效", type="repair", level="warning",
            status=st, assignee_id=eng.id,
            accept_time=_at, finish_time=ft_,
        ))
    s.commit()
    wo = _make_wo(s, status=WorkOrderStatus.PENDING, station_id=None)

    d = _score_details_for(client, wo, eng.username)
    # 单工程师: 绩效评分必须与修复后口径 (expected_avg/cr) 推演值一致
    expected_perf = _expected_perf_score(expected_cr, expected_avg)
    assert d["performance"] == pytest.approx(expected_perf, abs=0.05)
    # 修复前口径推演值应不同 (防退化锚)
    if at and ft:
        buggy_avg = 6.0 / 3  # 分母含缺时间戳样本
        assert d["performance"] != pytest.approx(
            _expected_perf_score(expected_cr, buggy_avg), abs=0.05)


def test_dispatch_zero_orders_fallback(client):
    """零工单工程师: completion_rate 回退 85, avg_hours 回退 3.5。"""
    s = client._sesh
    eng = _add_user(s, _uname("eng_zero"))
    wo = _make_wo(s, status=WorkOrderStatus.PENDING, station_id=None)

    d = _score_details_for(client, wo, eng.username)
    expected_perf = _expected_perf_score(85, 3.5)
    assert d["performance"] == pytest.approx(expected_perf, abs=0.05)


# ═════════════════════════════════════════════════════════════════════
# ⑧ transfer 转单端点 (成功 / 转自己 / 目标不存在 / 非法状态 / 不存在)
# ═════════════════════════════════════════════════════════════════════


def test_transfer_happy_resets_to_pending(client):
    """转单成功: processing 单转给另一工程师 → status 重置 pending + assignee 换人。"""
    s = client._sesh
    sta = _make_team_station(s, 7201)
    e1 = _add_user(s, _uname("eng_from"))
    e2 = _add_user(s, _uname("eng_to"))
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, assignee_id=e1.id, station_id=sta.id)

    r = client.post(f"{WO_URL}/{wo.id}/transfer",
                    json={"target_engineer_id": e2.id, "reason": "工作量调整"})
    assert r.status_code == 200, f"转单失败: {r.status_code} {r.text[:300]}"
    d = r.json()["data"]
    assert d["status"] == "pending"
    assert d["new_engineer"] == e2.username
    s.expire_all()
    wo_db = s.query(WorkOrder).filter(WorkOrder.id == wo.id).one()
    assert wo_db.status == WorkOrderStatus.PENDING
    assert wo_db.assignee_id == e2.id


def test_transfer_to_self_400(client):
    """转给自己 → 400。"""
    s = client._sesh
    sta = _make_team_station(s, 7202)
    e1 = _add_user(s, _uname("eng_self"))
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, assignee_id=e1.id, station_id=sta.id)
    r = client.post(f"{WO_URL}/{wo.id}/transfer",
                    json={"target_engineer_id": e1.id, "reason": "x"})
    assert r.status_code == 400
    assert "自己" in r.json()["detail"]


def test_transfer_target_not_engineer_404(client):
    """目标工程师不存在 (或非 ENGINEER 角色) → 404。"""
    s = client._sesh
    sta = _make_team_station(s, 7203)
    e1 = _add_user(s, _uname("eng_host"))
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING, assignee_id=e1.id, station_id=sta.id)
    r = client.post(f"{WO_URL}/{wo.id}/transfer",
                    json={"target_engineer_id": 99999, "reason": "x"})
    assert r.status_code == 404


def test_transfer_illegal_status_400(client):
    """pending_verify 工单 (不在 [pending/accepted/processing]) 转单 → 400。"""
    s = client._sesh
    e1 = _add_user(s, _uname("eng_pv"))
    wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY, assignee_id=e1.id)
    e2 = _add_user(s, _uname("eng_pv_target"))
    r = client.post(f"{WO_URL}/{wo.id}/transfer",
                    json={"target_engineer_id": e2.id, "reason": "x"})
    assert r.status_code == 400


def test_transfer_not_found_404(client):
    """转单不存在的工单 → 404。"""
    s = client._sesh
    e2 = _add_user(s, _uname("eng_nf"))
    r = client.post(f"{WO_URL}/WO-NOPE-8888/transfer",
                    json={"target_engineer_id": e2.id, "reason": "x"})
    assert r.status_code == 404


# ═════════════════════════════════════════════════════════════════════
# ⑨ urge 催单端点 (成功 / 非法状态 / 不存在)
# ═════════════════════════════════════════════════════════════════════


def test_urge_happy_logs_message(client):
    """催单成功: processing 单 → 200, 记日志, 不改 status。"""
    wo_id = create_wo(client)
    advance_wo(client, wo_id, "accept", "start")  # → processing
    r = client.post(f"{WO_URL}/{wo_id}/urge", json={"message": "抓紧"})
    assert r.status_code == 200
    assert "催单成功" in r.json()["message"]
    # status 不变
    assert client.get(f"{WO_URL}/{wo_id}").json()["data"]["status"] == "processing"


def test_urge_default_message(client):
    """催单不传 body (data=None 默认) → 用默认消息, 仍 200。"""
    wo_id = create_wo(client)
    r = client.post(f"{WO_URL}/{wo_id}/urge")  # 不带 json body
    assert r.status_code == 200


def test_urge_illegal_status_400(client):
    """completed 工单催单 → 400 (状态不允许催单)。"""
    wo_id = create_wo(client)
    advance_wo(client, wo_id, "accept", "start", "complete", "verify")  # → completed
    r = client.post(f"{WO_URL}/{wo_id}/urge", json={"message": "x"})
    assert r.status_code == 400


def test_urge_not_found_404(client):
    """催单不存在的工单 → 404。"""
    r = client.post(f"{WO_URL}/WO-NOPE-7777/urge", json={"message": "x"})
    assert r.status_code == 404


# ═════════════════════════════════════════════════════════════════════
# ⑩ accept 已指派他人 → 403 (缺陷3 assignee 守卫, 独立于非 assignee 完成)
# ═════════════════════════════════════════════════════════════════════


def test_accept_assigned_to_other_engineer_403(client):
    """已指派给特定工程师 (pending+assignee_id) 的工单, 其他工程师接单 → 403。

    对照 accept 抢单池 (assignee=None): 任何同团队工程师可接 (现有流转测试覆盖)。
    """
    s = client._sesh
    team = 7301
    sta = _make_team_station(s, team)
    holder = _add_user(s, _uname("eng_holder"), team_id=team)   # 工单已指派给它
    grabber = _add_user(s, _uname("eng_grabber"), team_id=team)  # 同团队另一工程师
    wo = _make_wo(s, status=WorkOrderStatus.PENDING,
                  assignee_id=holder.id, station_id=sta.id)
    try:
        login_as(client, grabber.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/accept")
        assert r.status_code == 403
        assert "其他工程师" in r.json()["detail"]
    finally:
        login_admin(client)


def test_accept_assigned_engineer_self_ok(client):
    """对照: 被指派的工程师本人接单 → 200 (assignee==user)。"""
    s = client._sesh
    team = 7302
    sta = _make_team_station(s, team)
    holder = _add_user(s, _uname("eng_self_accept"), team_id=team)
    wo = _make_wo(s, status=WorkOrderStatus.PENDING,
                  assignee_id=holder.id, station_id=sta.id)
    try:
        login_as(client, holder.username, "pass123")
        r = client.post(f"{WO_URL}/{wo.id}/accept")
        assert r.status_code == 200
    finally:
        login_admin(client)


def test_start_wrong_status_400(client):
    """start 从非法状态 (completed) → 400。"""
    s = client._sesh
    wo = _make_wo(s, status=WorkOrderStatus.COMPLETED)
    r = client.post(f"{WO_URL}/{wo.id}/start")
    assert r.status_code == 400


def test_reject_wrong_status_400(client):
    """reject 仅 pending_verify 可驳; processing 单驳回 → 400。"""
    wo_id = create_wo(client)
    advance_wo(client, wo_id, "accept", "start")  # → processing
    r = client.post(f"{WO_URL}/{wo_id}/reject", params={"reason": "不合格"})
    assert r.status_code == 400


def test_reject_reason_required_422(client):
    """reason 是必填 query param, 缺失 → 422 (FastAPI 参数校验, 非 400/500)。"""
    s = client._sesh
    wo = _make_wo(s, status=WorkOrderStatus.PENDING_VERIFY)
    r = client.post(f"{WO_URL}/{wo.id}/reject")  # 不传 reason
    assert r.status_code == 422


def test_verify_wrong_status_400(client):
    """verify 仅 pending_verify 可验收; processing 单验收 → 400。"""
    s = client._sesh
    wo = _make_wo(s, status=WorkOrderStatus.PROCESSING)
    r = client.post(f"{WO_URL}/{wo.id}/verify")
    assert r.status_code == 400
    assert "验收" in r.json()["detail"]


def test_complete_wrong_status_400(client):
    """complete 仅 processing 可完成; pending 单完成 → 400。"""
    s = client._sesh
    wo = _make_wo(s, status=WorkOrderStatus.PENDING)
    r = client.post(f"{WO_URL}/{wo.id}/complete", params={"solution": "x"})
    assert r.status_code == 400
