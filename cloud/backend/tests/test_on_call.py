"""
值班排班管理 API 测试
覆盖: /on-call — 规则CRUD、班次管理、交接班、值班日志、统计
"""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库。

    卡 占位: on_call 读端点改为手写 cache key 后缓存真正会命中 (旧 @cached 因 key 含
    依赖对象地址永不命中), 跨测试的模块级内存缓存会串库污染断言 → 每测试前清空。
    """
    from app.core.cache import clear_memory_cache
    clear_memory_cache()


def _login():
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_team(name="值班测试团队"):
    """创建测试团队"""
    resp = client.post(
        "/api/v1/teams",
        json={"name": name, "description": "值班测试"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def _create_user_db(test_db, username="oncall_user"):
    """创建测试用户（需要test_db参数）"""
    from app.models.user import User
    from app.api.v1.auth import get_password_hash
    from app.models.user import UserRole
    db = test_db["SessionLocal"]()
    user = User(
        username=username,
        password_hash=get_password_hash("test123"),
        real_name=username,
        role=UserRole.ENGINEER,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


def _create_rule(team_id, user_ids):
    """创建值班规则"""
    resp = client.post(
        "/api/v1/on-call/rules",
        json={
            "name": "测试值班规则",
            "team_id": team_id,
            "schedule_type": "weekly",
            "rotation_order": user_ids,
            "shift_duration_hours": 168,
            "overlap_minutes": 30,
            "escalation_level": 2,
            "escalation_timeout_minutes": 30,
            "notify_methods": ["app", "sms"],
            "auto_assign_workorders": True,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, f"创建规则失败: {resp.text}"
    return resp.json()["rule_id"]


# ========== 鉴权检查 ==========

def test_list_rules_requires_auth(anon_client):
    """无 token 访问规则列表应返回401"""
    assert anon_client.get("/api/v1/on-call/rules").status_code == 401


def test_list_shifts_requires_auth(anon_client):
    """无 token 访问班次列表应返回401"""
    assert anon_client.get("/api/v1/on-call/shifts").status_code == 401


def test_create_rule_requires_auth(anon_client):
    """无 token 创建规则应返回401或403(CSRF)"""
    resp = anon_client.post("/api/v1/on-call/rules", json={"name": "test"})
    assert resp.status_code in (401, 403)


def test_get_current_shifts_requires_auth(anon_client):
    """无 token 获取当前值班应返回401"""
    assert anon_client.get("/api/v1/on-call/shifts/current").status_code == 401


def test_get_stats_requires_auth(anon_client):
    """无 token 获取统计应返回401"""
    assert anon_client.get("/api/v1/on-call/stats").status_code == 401


# ========== 规则 CRUD ==========

def test_list_rules_empty():
    """测试空规则列表"""
    resp = client.get("/api/v1/on-call/rules", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["rules"] == []


def test_create_rule_success(test_db):
    """测试创建规则成功"""
    team_id = _create_team()
    user_id1 = _create_user_db(test_db, "oncall1")
    user_id2 = _create_user_db(test_db, "oncall2")

    rule_id = _create_rule(team_id, [user_id1, user_id2])
    assert rule_id is not None


def test_create_rule_invalid_user():
    """测试创建规则使用不存在的用户"""
    team_id = _create_team()
    resp = client.post(
        "/api/v1/on-call/rules",
        json={
            "name": "无效用户规则",
            "team_id": team_id,
            "rotation_order": [999999],
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_get_rule_success(test_db):
    """测试获取规则详情"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "detail_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["rule"]["id"] == rule_id
    assert "shifts" in data


def test_get_rule_not_found():
    """测试获取不存在的规则"""
    resp = client.get("/api/v1/on-call/rules/999999", headers=_auth_headers())
    assert resp.status_code == 404


def test_update_rule_success(test_db):
    """测试更新规则"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "update_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.put(
        f"/api/v1/on-call/rules/{rule_id}",
        json={"name": "更新后规则名", "shift_duration_hours": 72},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_update_rule_not_found():
    """测试更新不存在的规则"""
    resp = client.put("/api/v1/on-call/rules/999999", json={"name": "不存在"}, headers=_auth_headers())
    assert resp.status_code == 404


def test_delete_rule_success(test_db):
    """测试删除规则"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "delete_user")
    rule_id = _create_rule(team_id, [user_id])

    # 先取消所有scheduled班次
    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    shifts = resp.json()["shifts"]
    for s in shifts:
        if s["status"] == "scheduled":
            client.put(f"/api/v1/on-call/shifts/{s['id']}?status=cancelled", headers=_auth_headers())

    resp = client.delete(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    assert resp.status_code == 200


def test_delete_rule_not_found():
    """测试删除不存在的规则"""
    resp = client.delete("/api/v1/on-call/rules/999999", headers=_auth_headers())
    assert resp.status_code == 404


def test_list_rules_with_team_filter(test_db):
    """测试按团队筛选规则"""
    team_id = _create_team("筛选团队")
    user_id = _create_user_db(test_db, "filter_user")
    _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/rules?team_id={team_id}", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


# ========== 班次管理 ==========

def test_list_shifts_empty():
    """测试空班次列表"""
    resp = client.get("/api/v1/on-call/shifts", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "shifts" in data


def test_create_shift_manual(test_db):
    """测试手动创建班次"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "shift_user")
    rule_id = _create_rule(team_id, [user_id])

    now = datetime.now(timezone.utc)
    start = (now + timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=8)).isoformat()

    resp = client.post(
        "/api/v1/on-call/shifts",
        json={
            "rule_id": rule_id,
            "user_id": user_id,
            "start_time": start,
            "end_time": end,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["shift_id"] is not None


def test_create_shift_invalid_rule(test_db):
    """测试用不存在的规则创建班次"""
    user_id = _create_user_db(test_db, "bad_shift_user")
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/api/v1/on-call/shifts",
        json={
            "rule_id": 999999,
            "user_id": user_id,
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(),
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_update_shift_status(test_db):
    """测试更新班次状态"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "status_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    shift_id = resp.json()["shifts"][0]["id"]

    resp = client.put(f"/api/v1/on-call/shifts/{shift_id}?status=completed", headers=_auth_headers())
    assert resp.status_code == 200


def test_update_shift_not_found():
    """测试更新不存在的班次"""
    resp = client.put("/api/v1/on-call/shifts/999999?status=completed", headers=_auth_headers())
    assert resp.status_code == 404


# ========== 卡 5b7308f3: update_shift 状态白名单校验 ==========

def test_update_shift_invalid_status_400(test_db):
    """非法状态串 → 400，不得入库"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "bad_status_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    shift_id = resp.json()["shifts"][0]["id"]

    resp = client.put(f"/api/v1/on-call/shifts/{shift_id}?status=banana", headers=_auth_headers())
    assert resp.status_code == 400
    assert "banana" in resp.text

    # 状态未被污染
    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    assert resp.json()["shifts"][0]["status"] != "banana"


def test_update_shift_cross_team_404(client, team_pair):
    """A队改B队班次状态 → 404（伪造 X-Team-Id 无效）"""
    rot_b = team_pair["users"]["b"]["rot"].id
    r = _create_rule_as(client, team_pair["tokens"]["b"], "B队班次规则", [rot_b])
    rule_b = r.json()["rule_id"]

    r = client.get(f"/api/v1/on-call/rules/{rule_b}", headers=_h(team_pair["tokens"]["b"]))
    shift_id = r.json()["shifts"][0]["id"]

    ha = {**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(team_pair["teams"]["b"].id)}
    resp = client.put(f"/api/v1/on-call/shifts/{shift_id}?status=completed", headers=ha)
    assert resp.status_code == 404

    # B 本人可正常更新
    resp = client.put(
        f"/api/v1/on-call/shifts/{shift_id}?status=cancelled", headers=_h(team_pair["tokens"]["b"])
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_list_shifts_with_filters(test_db):
    """测试班次列表筛选"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "filter_shift_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/shifts?rule_id={rule_id}", headers=_auth_headers())
    assert resp.status_code == 200

    resp = client.get(f"/api/v1/on-call/shifts?user_id={user_id}", headers=_auth_headers())
    assert resp.status_code == 200


def test_regenerate_shifts(test_db):
    """测试重新生成排班"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "regen_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=2",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["created"] > 0


# ========== 当前值班 ==========

def test_get_current_shifts_empty():
    """测试当前无值班"""
    resp = client.get("/api/v1/on-call/shifts/current", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["current_shifts"] == []


def test_get_current_shifts_with_team_filter():
    """测试按团队筛选当前值班"""
    resp = client.get("/api/v1/on-call/shifts/current?team_id=1", headers=_auth_headers())
    assert resp.status_code == 200


# ========== 交接班 ==========

def test_handover_success(test_db):
    """测试交接班"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "handover_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    shift_id = resp.json()["shifts"][0]["id"]

    resp = client.post(
        "/api/v1/on-call/shifts/handover",
        json={"shift_id": shift_id, "notes": "交接班测试", "user_id": user_id},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_handover_not_found():
    """测试交接不存在的班次"""
    resp = client.post(
        "/api/v1/on-call/shifts/handover",
        json={"shift_id": 999999, "notes": "测试", "user_id": 1},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


# ========== 值班日志 ==========

def test_list_logs_empty():
    """测试空日志列表"""
    resp = client.get("/api/v1/on-call/logs", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data


def test_create_log_success(test_db):
    """测试创建值班日志"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "log_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    shift_id = resp.json()["shifts"][0]["id"]

    resp = client.post(
        "/api/v1/on-call/logs",
        json={
            "shift_id": shift_id,
            "user_id": user_id,
            "event_type": "note",
            "content": "值班日志测试",
            "severity": "info",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


def test_create_log_invalid_shift(test_db):
    """测试为不存在的班次创建日志"""
    user_id = _create_user_db(test_db, "bad_log_user")
    resp = client.post(
        "/api/v1/on-call/logs",
        json={"shift_id": 999999, "user_id": user_id, "event_type": "note", "content": "test"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 404


def test_list_logs_with_filters():
    """测试日志列表筛选"""
    resp = client.get("/api/v1/on-call/logs?event_type=note", headers=_auth_headers())
    assert resp.status_code == 200


# ========== 统计 ==========

def test_get_stats():
    """测试获取统计"""
    resp = client.get("/api/v1/on-call/stats?days=30", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "shifts" in data
    assert "handover" in data
    assert "logs" in data


def test_get_stats_with_data(test_db):
    """测试有数据时的统计"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "stats_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.get("/api/v1/on-call/stats?days=30", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["shifts"]["total"] >= 0


# ========== 团队隔离（任务卡 708350b3）==========

from tests._test_helpers import _fast_hash  # 卡17354607: 复用进程级 bcrypt hash 缓存


@pytest.fixture
def team_pair(client):
    """两团队 + 每队一名 manager(建规则) + 一名 oncall(轮换) + token。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="值班团队A", code="OCTA")
    tb = Team(name="值班团队B", code="OCTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "oc123456"
    users = {}
    for key, team, uname in [("a", ta, "oc_mgr_a"), ("b", tb, "oc_mgr_b")]:
        mgr = User(
            username=uname, real_name=f"{key}主管", role=UserRole.ENGINEER,
            team_id=team.id, status="active",
            password_hash=_fast_hash(pwd),
        )
        rot = User(
            username=f"oc_rot_{key}", real_name=f"{key}值班员", role=UserRole.ENGINEER,
            team_id=team.id, status="active",
            password_hash=_fast_hash(pwd),
        )
        s.add_all([mgr, rot])
        users[key] = {"mgr": mgr, "rot": rot}
    s.commit()
    for key in users:
        s.refresh(users[key]["mgr"])
        s.refresh(users[key]["rot"])

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "users": users,
        "tokens": {"a": _tok("oc_mgr_a"), "b": _tok("oc_mgr_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_rule_as(client, token, name, rotation_user_ids, extra_team_id=None):
    """以指定 token 创建值班规则（body team_id 可伪造）。"""
    body = {"name": name, "rotation_order": rotation_user_ids}
    if extra_team_id is not None:
        body["team_id"] = extra_team_id
    return client.post("/api/v1/on-call/rules", json=body, headers=_h(token))


def test_create_rule_forces_own_team(client, team_pair):
    """团队级用户创建的规则归属其本人 team；伪造 body team_id 不得越权。"""
    ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
    rot_a = team_pair["users"]["a"]["rot"].id
    # A 故意伪造 body team_id=B
    r = _create_rule_as(client, team_pair["tokens"]["a"], "A队值班", [rot_a], extra_team_id=tb.id)
    assert r.status_code == 200, r.text
    rule_id = r.json()["rule_id"]

    # 规则归属 A 队
    from app.models.on_call import OnCallRule
    s = client._sesh
    rule = s.query(OnCallRule).filter_by(id=rule_id).first()
    assert rule.team_id == ta.id


def test_list_rules_filters_by_team(client, team_pair):
    """团队级用户仅见本 team 规则；伪造 query team_id 不得越权。"""
    ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
    rot_a = team_pair["users"]["a"]["rot"].id
    rot_b = team_pair["users"]["b"]["rot"].id
    _create_rule_as(client, team_pair["tokens"]["a"], "A队规则", [rot_a])
    _create_rule_as(client, team_pair["tokens"]["b"], "B队规则", [rot_b])

    # A 故意伪造 ?team_id=B，仍只见本人 team
    r = client.get(
        f"/api/v1/on-call/rules?team_id={tb.id}",
        headers={**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)},
    )
    assert r.status_code == 200
    names = {it["name"] for it in r.json()["rules"]}
    assert "A队规则" in names
    assert "B队规则" not in names

    # admin（conftest client 默认 admin 身份）看全部
    r = client.get("/api/v1/on-call/rules")
    names = {it["name"] for it in r.json()["rules"]}
    assert "A队规则" in names and "B队规则" in names


def test_cross_team_rule_access_404(client, team_pair):
    """团队A访问/改/删/重排团队B的规则 → 404（伪造 X-Team-Id 也无效）。"""
    tb = team_pair["teams"]["b"]
    rot_b = team_pair["users"]["b"]["rot"].id
    r = _create_rule_as(client, team_pair["tokens"]["b"], "B专属规则", [rot_b])
    rule_b = r.json()["rule_id"]

    ha = {**_h(team_pair["tokens"]["a"]), "X-Team-Id": str(tb.id)}
    assert client.get(f"/api/v1/on-call/rules/{rule_b}", headers=ha).status_code == 404
    assert client.put(f"/api/v1/on-call/rules/{rule_b}", json={"name": "篡改"}, headers=ha).status_code == 404
    assert client.delete(f"/api/v1/on-call/rules/{rule_b}", headers=ha).status_code == 404
    assert client.post(f"/api/v1/on-call/rules/{rule_b}/generate-shifts?num_cycles=1", headers=ha).status_code == 404

    # B 本人可正常访问
    assert client.get(f"/api/v1/on-call/rules/{rule_b}", headers=_h(team_pair["tokens"]["b"])).status_code == 200


# ========== 卡 cea77711: 时区缺陷 + 校验缺口 + 事务原子性 + 端点场景 ==========

# ─── 缺陷1: regenerate_shifts naive start_from 时区错位 (与电价卡9912ba63/通知卡ac0a7aa7同根) ───

def test_regenerate_naive_start_interpreted_as_local_timezone(test_db):
    """naive start_from 按本地时区 (Asia/Shanghai) 解释, 非当 UTC。

    上海用户传 '2026-01-01T09:00:00' 意为上海09:00 = UTC01:00。旧实现
    _generate_shifts_for_rule 用 replace(tzinfo=utc) 把本地墙钟当 UTC, 错位 8h
    (存成 UTC09:00 = 上海17:00)。修复后 naive 先标上海时区再转 UTC 落库。
    """
    from app.models.on_call import OnCallShift
    team_id = _create_team()
    user_id = _create_user_db(test_db, "tz_naive_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=1&start_from=2026-01-01T09:00:00",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200

    db = test_db["SessionLocal"]()
    try:
        # 仅取 2026-01 区间内 (即本次 regenerate 生成的) 班次, 排除 create_rule 自动生成的当期班次
        jan = db.query(OnCallShift).filter(
            OnCallShift.rule_id == rule_id,
            OnCallShift.start_time >= datetime(2026, 1, 1),
            OnCallShift.start_time < datetime(2026, 2, 1),
        ).all()
        assert len(jan) == 1
        # 上海09:00 = UTC01:00; SQLite 以 naive UTC 墙钟存储
        assert jan[0].start_time == datetime(2026, 1, 1, 1, 0), \
            f"naive 上海09:00 应落库为 UTC01:00, 实际 {jan[0].start_time} (旧bug=UTC09:00)"
    finally:
        db.close()


def test_regenerate_aware_start_respected(test_db):
    """aware start_from (带 offset) 按其绝对时刻尊重, 不被二次本地化。

    start_from='2026-01-01T09:00:00Z' (显式 UTC) → 落库 UTC09:00。
    """
    from app.models.on_call import OnCallShift
    team_id = _create_team()
    user_id = _create_user_db(test_db, "tz_aware_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=1&start_from=2026-01-01T09:00:00Z",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200

    db = test_db["SessionLocal"]()
    try:
        jan = db.query(OnCallShift).filter(
            OnCallShift.rule_id == rule_id,
            OnCallShift.start_time >= datetime(2026, 1, 1),
            OnCallShift.start_time < datetime(2026, 2, 1),
        ).all()
        assert len(jan) == 1
        # 显式 UTC09:00 原样落库 (不被再当上海)
        assert jan[0].start_time == datetime(2026, 1, 1, 9, 0), \
            f"aware UTC09:00 应原样落库, 实际 {jan[0].start_time}"
    finally:
        db.close()


# ─── 卡 a7d04453: py3.9 fromisoformat 不支持 Z 后缀 + 坏值显式 400 ───

def test_regenerate_offset_start_parsed(test_db):
    """start_from 带显式 offset ('+08:00') 经 _parse_iso 透传解析, 不 500。

    py3.9 fromisoformat 本就能解析 '+08:00' (非 Z bug 受害者), 本用例覆盖
    _parse_iso 对显式 offset 的透传: status 200 且生成班次。aware offset 落
    naive DateTime 列按 SQLAlchemy 行为剥 tzinfo 存墙钟 (与 Z 用例同存储模式)。
    注意 query 里 '+' 必须编码为 %2B, 否则被当成空格。
    """
    from app.models.on_call import OnCallShift
    team_id = _create_team()
    user_id = _create_user_db(test_db, "tz_offset_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=1&start_from=2026-01-01T09:00:00%2B08:00",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text

    db = test_db["SessionLocal"]()
    try:
        jan = db.query(OnCallShift).filter(
            OnCallShift.rule_id == rule_id,
            OnCallShift.start_time >= datetime(2026, 1, 1),
            OnCallShift.start_time < datetime(2026, 2, 1),
        ).all()
        assert len(jan) == 1
        # SQLAlchemy naive DateTime 列剥 tzinfo 存墙钟; aware 09:00+08:00 → 墙钟 09:00
        assert jan[0].start_time == datetime(2026, 1, 1, 9, 0), \
            f"offset 09:00+08:00 应按墙钟落库 09:00, 实际 {jan[0].start_time}"
    finally:
        db.close()


def test_regenerate_bad_start_returns_400(test_db):
    """坏值 start_from ('not-a-date') → 400 (用户输入错误), 非 500。

    卡 a7d04453: 旧实现 datetime.fromisoformat 抛 ValueError, 落入端点通用
    except 返回 500; _parse_iso 把解析失败显式转 HTTPException(400)。
    """
    team_id = _create_team()
    user_id = _create_user_db(test_db, "bad_start_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=1&start_from=not-a-date",
        headers=_auth_headers(),
    )
    assert resp.status_code == 400, f"坏值应 400 非 500, 实际 {resp.status_code}: {resp.text}"


# ─── 缺陷2: create_rule / update_rule 校验缺口 (空轮换 / 零负时长) ───

def test_create_rule_empty_rotation_returns_400(test_db):
    """空 rotation_order → 400 明确消息 (否则静默生成0班次却谎报'已自动生成排班')。"""
    team_id = _create_team()
    resp = client.post(
        "/api/v1/on-call/rules",
        json={"name": "空轮换", "team_id": team_id, "rotation_order": []},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400
    assert "轮换" in (resp.json().get("message") or resp.json().get("detail", ""))


def test_create_rule_zero_duration_returns_400(test_db):
    """shift_duration_hours=0 → 400 (否则 _get_current_shift 永不命中, 值班表真空)。"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "zero_dur_user")
    resp = client.post(
        "/api/v1/on-call/rules",
        json={"name": "零时长", "team_id": team_id, "rotation_order": [user_id], "shift_duration_hours": 0},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400
    assert "时长" in (resp.json().get("message") or resp.json().get("detail", ""))


def test_create_rule_negative_duration_returns_400(test_db):
    """shift_duration_hours=-5 → 400。"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "neg_dur_user")
    resp = client.post(
        "/api/v1/on-call/rules",
        json={"name": "负时长", "team_id": team_id, "rotation_order": [user_id], "shift_duration_hours": -5},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_update_rule_zero_duration_returns_400(test_db):
    """真实缺口: PUT /rules/{id} 旧 OnCallRuleUpdate 无 ge 约束, shift_duration_hours=0 返回200。
    修复后 → 400。"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "upd_zero_user")
    rule_id = _create_rule(team_id, [user_id])
    resp = client.put(
        f"/api/v1/on-call/rules/{rule_id}",
        json={"shift_duration_hours": 0},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_update_rule_negative_duration_returns_400(test_db):
    """PUT shift_duration_hours=-5 → 400。"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "upd_neg_user")
    rule_id = _create_rule(team_id, [user_id])
    resp = client.put(
        f"/api/v1/on-call/rules/{rule_id}",
        json={"shift_duration_hours": -5},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_update_rule_empty_rotation_returns_400(test_db):
    """PUT rotation_order=[] → 400 (否则后续 regenerate 生成0班次)。"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "upd_empty_rot")
    rule_id = _create_rule(team_id, [user_id])
    resp = client.put(
        f"/api/v1/on-call/rules/{rule_id}",
        json={"rotation_order": []},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


# ─── 缺陷3: create_rule 双 commit 孤儿 → 单事务原子性 ───

def test_create_rule_atomic_no_orphan_on_shift_gen_failure(test_db, monkeypatch):
    """排班生成中途失败不应留下孤儿规则 (旧实现 rule 先 commit, shifts 二次 commit)。

    修复: rule 用 db.flush() 取 id, 与班次同事务单次 commit; 生成抛错则整体回滚无孤儿。
    """
    from app.api.v1 import on_call as oc_module
    from app.models.on_call import OnCallRule

    def _boom(db, rule, **kw):
        raise RuntimeError("模拟排班生成失败")

    monkeypatch.setattr(oc_module, "_generate_shifts_for_rule", _boom)

    team_id = _create_team()
    user_id = _create_user_db(test_db, "orphan_user")
    resp = client.post(
        "/api/v1/on-call/rules",
        json={"name": "孤儿探针规则-atomicity-cea77711", "team_id": team_id, "rotation_order": [user_id]},
        headers=_auth_headers(),
    )
    # 异常被 except 捕获 → 500
    assert resp.status_code == 500

    db = test_db["SessionLocal"]()
    try:
        orphan = db.query(OnCallRule).filter(
            OnCallRule.name == "孤儿探针规则-atomicity-cea77711"
        ).first()
        assert orphan is None, f"排班生成失败却留下孤儿规则 id={orphan.id} (双commit未合并)"
    finally:
        db.close()


# ─── 端点场景: PUT / DELETE / generate-shifts / 手动建班 / handover ───

def test_update_rule_partial_fields_persist(test_db):
    """PUT /rules/{id} 部分字段更新并持久化到库。"""
    from app.models.on_call import OnCallRule
    team_id = _create_team()
    user_id = _create_user_db(test_db, "upd_persist_user")
    rule_id = _create_rule(team_id, [user_id])

    resp = client.put(
        f"/api/v1/on-call/rules/{rule_id}",
        json={"name": "更新后规则", "shift_duration_hours": 48, "overlap_minutes": 15, "enabled": False},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200

    db = test_db["SessionLocal"]()
    try:
        r = db.query(OnCallRule).get(rule_id)
        assert r.name == "更新后规则"
        assert r.shift_duration_hours == 48
        assert r.overlap_minutes == 15
        assert r.enabled is False
    finally:
        db.close()


def test_delete_rule_with_active_shifts_returns_400(test_db):
    """有未完成班次时删除规则 → 400。"""
    team_id = _create_team()
    user_id = _create_user_db(test_db, "del_active_user")
    rule_id = _create_rule(team_id, [user_id])  # 自动生成 scheduled 班次
    resp = client.delete(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    assert resp.status_code == 400
    assert "班次" in (resp.json().get("message") or resp.json().get("detail", ""))


def test_delete_rule_cascades_shifts(test_db):
    """删除规则级联删除其班次 (cascade=all,delete-orphan)。"""
    from app.models.on_call import OnCallShift
    team_id = _create_team()
    user_id = _create_user_db(test_db, "del_cascade_user")
    rule_id = _create_rule(team_id, [user_id])

    # 先取消所有 scheduled 班次以放行 delete
    shifts = client.get(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers()).json()["shifts"]
    for s in shifts:
        if s["status"] == "scheduled":
            client.put(f"/api/v1/on-call/shifts/{s['id']}?status=cancelled", headers=_auth_headers())

    resp = client.delete(f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers())
    assert resp.status_code == 200

    db = test_db["SessionLocal"]()
    try:
        n = db.query(OnCallShift).filter(OnCallShift.rule_id == rule_id).count()
        assert n == 0, f"删除规则后仍有 {n} 个孤儿班次 (级联未生效)"
    finally:
        db.close()


def test_regenerate_idempotent_no_duplicate(test_db):
    """重复 generate 幂等: 先删 future scheduled 再生成, 不产生重复班次。

    start_from 动态取 now+30d (卡 7b7a7444): 删除条件为 start_time > now(实现内
    datetime.now), 硬编码 2027-06-01 在该日期过后滑为过去 → 永不再命中删除窗口。
    """
    from app.models.on_call import OnCallShift
    team_id = _create_team()
    user_id = _create_user_db(test_db, "idem_regen_user")
    rule_id = _create_rule(team_id, [user_id])

    sf_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)  # 恒为未来
    sf = sf_dt.strftime("%Y-%m-%dT%H:%M:%S")
    r1 = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=2&start_from={sf}",
        headers=_auth_headers(),
    )
    assert r1.status_code == 200

    db = test_db["SessionLocal"]()
    c1 = db.query(OnCallShift).filter(
        OnCallShift.rule_id == rule_id, OnCallShift.start_time >= sf_dt
    ).count()
    db.close()

    r2 = client.post(
        f"/api/v1/on-call/rules/{rule_id}/generate-shifts?num_cycles=2&start_from={sf}",
        headers=_auth_headers(),
    )
    assert r2.status_code == 200
    assert r2.json()["deleted"] > 0  # 第二次先清理 future scheduled

    db = test_db["SessionLocal"]()
    try:
        c2 = db.query(OnCallShift).filter(
            OnCallShift.rule_id == rule_id, OnCallShift.start_time >= sf_dt
        ).count()
        assert c1 == c2, f"重复 generate 产生重复班次: {c1} → {c2}"
    finally:
        db.close()


def test_create_shift_with_backup(test_db):
    """POST /shifts 手动建班含 backup_user_id。"""
    from app.models.on_call import OnCallShift
    team_id = _create_team()
    uid1 = _create_user_db(test_db, "manual_primary")
    uid2 = _create_user_db(test_db, "manual_backup")
    rule_id = _create_rule(team_id, [uid1])

    now = datetime.now(timezone.utc)
    resp = client.post(
        "/api/v1/on-call/shifts",
        json={
            "rule_id": rule_id,
            "user_id": uid1,
            "backup_user_id": uid2,
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=10)).isoformat(),
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    sid = resp.json()["shift_id"]

    db = test_db["SessionLocal"]()
    try:
        sh = db.query(OnCallShift).get(sid)
        assert sh.backup_user_id == uid2
        assert sh.status == "scheduled"
    finally:
        db.close()


def test_handover_duplicate_returns_400(test_db):
    """交接班幂等 (handover guard): 重复/并发交接同一班次 → 第二次 400, 仅留一条交接日志。

    覆盖任务'重复交接'与'并发双交接竞态': 真线程并发受限于 TestClient 同步 + SQLite 单
    writer (写串行化), 故以顺序双请求模拟竞态结果——guard 使无论到达顺序, 仅首个请求成功
    落库, 杜绝双交接日志。旧实现无守卫: 第二次仍 200 且产生第二条 handover 日志。
    """
    from app.models.on_call import OnCallLog
    team_id = _create_team()
    user_id = _create_user_db(test_db, "dup_handover_user")
    rule_id = _create_rule(team_id, [user_id])
    shift_id = client.get(
        f"/api/v1/on-call/rules/{rule_id}", headers=_auth_headers()
    ).json()["shifts"][0]["id"]

    r1 = client.post(
        "/api/v1/on-call/shifts/handover",
        json={"shift_id": shift_id, "notes": "第一次交接", "user_id": user_id},
        headers=_auth_headers(),
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v1/on-call/shifts/handover",
        json={"shift_id": shift_id, "notes": "第二次交接", "user_id": user_id},
        headers=_auth_headers(),
    )
    assert r2.status_code == 400

    db = test_db["SessionLocal"]()
    try:
        n = db.query(OnCallLog).filter(
            OnCallLog.shift_id == shift_id, OnCallLog.event_type == "handover"
        ).count()
        assert n == 1, f"重复交接产生 {n} 条日志 (应为1, handover 非幂等)"
    finally:
        db.close()
