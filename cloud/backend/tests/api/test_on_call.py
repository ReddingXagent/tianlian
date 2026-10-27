# -*- coding: utf-8 -*-
"""值班排班 & On-Call API 测试 — /api/v1/on-call (14 路由)

被测: app/api/v1/on_call.py (全代码库最大零测试 API 文件)。

覆盖:
- 值班规则 CRUD (创建自动生成排班 / 列表 / 详情 / 更新 / 删除)
- team scoping (团队级仅见本 team; 跨 team → 404; admin 平台级全见; 创建锁本人 team)
- 排班: 重新生成 / 当前值班 / 列表筛选 / 手动创建 / 状态更新
- 交接班状态流转 + 幂等守卫 (重复交接 → 400)
- 值班日志 创建/列表
- 统计报表结构 + 数据反映
- 权限门 (anon → 401; viewer 写 → 403; viewer 读放行)
- 参数校验边界 (空轮换 / 零时长 / 用户不存在 / 团队级无归属 / 路由 404)

响应契约 (与 operate/* 的 {code,data} 包裹不同):
- 成功响应直接返回 dict (message 键), 如 {"rule_id":..,"shifts_generated":..};
- 错误用 HTTPException(detail=...), 中文文案。
- 写操作 require_write_permission("workorder:edit"): GET 放行 (仅认证),
  POST/PUT/DELETE 需 workorder:edit; admin 恒通过, viewer/auditor → 403。
"""
import bcrypt
import pytest

from app.models.user import User, UserRole, Team

ONCALL = "/api/v1/on-call"


# ─── 共享 helpers (模块级普通函数, 自包含) ───

def _h(token):
    """Bearer 认证头。team/权限测试中多 token 并存, 用显式 header 而非改 client 默认。"""
    return {"Authorization": f"Bearer {token}"}


def _uid(s, username):
    u = s.query(User).filter(User.username == username).first()
    assert u is not None, f"用户 {username} 不存在, 请先 seed"
    return u.id


def _make_team(s, name, code):
    t = Team(name=name, code=code)
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _make_user(s, username, role, team_id=None, password="pass1234", real_name=None):
    u = User(
        username=username,
        real_name=real_name or username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def _login(client, username, password):
    """登录拿 token。登录端点在白名单 (无需认证头), 不污染 client 默认 admin header。"""
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"登录 {username} 失败: {r.status_code} {r.text[:200]}"
    return r.json()["data"]["token"]


def _default_team_id(s):
    """取/建默认值班团队。

    OnCallRule.team_id 为 nullable=False 且业务层强制非空 —— 即便 admin (平台级)
    创建规则也必须显式指定归属团队, 故 helper 默认提供一个团队。
    """
    t = s.query(Team).first()
    if t is None:
        t = Team(name="默认值班团队", code="OCDEF")
        s.add(t)
        s.commit()
        s.refresh(t)
    return t.id


def _create_rule(client, s, *, name="测试值班规则", uids=None, team_id=None, **overrides):
    """经 API (admin 身份) 创建规则, 返回 rule_id。

    uids 默认 [admin]; team_id 默认取/建默认团队 (admin 亦须指定归属)。
    """
    if uids is None:
        uids = [_uid(s, "admin")]
    if team_id is None:
        team_id = _default_team_id(s)
    body = {"name": name, "rotation_order": uids, "team_id": team_id}
    body.update(overrides)
    r = client.post(f"{ONCALL}/rules", json=body)
    assert r.status_code == 200, f"创建规则失败: {r.status_code} {r.text[:300]}"
    return r.json()["rule_id"]


def _shift_ids_of(client, rule_id):
    """经详情端点取某规则下全部班次 id (按 start_time 升序)。"""
    r = client.get(f"{ONCALL}/rules/{rule_id}")
    assert r.status_code == 200, f"取详情失败: {r.status_code} {r.text[:300]}"
    return [s["id"] for s in r.json()["shifts"]]


@pytest.fixture
def team_pair(client):
    """两团队 + 各一名 ENGINEER (持 workorder:edit) + token, 用于 team_id 隔离测试。

    ENGINEER 同时作为本团队的值班人员 (rotation_order 用本人 id)。
    """
    s = client._sesh
    ta = _make_team(s, "值班团队A", "OCTA")
    tb = _make_team(s, "值班团队B", "OCTB")
    ua = _make_user(s, "oc_eng_a", UserRole.ENGINEER, team_id=ta.id, real_name="A工程师")
    ub = _make_user(s, "oc_eng_b", UserRole.ENGINEER, team_id=tb.id, real_name="B工程师")
    return {
        "teams": {"a": ta, "b": tb},
        "users": {"a": ua, "b": ub},
        "tokens": {"a": _login(client, "oc_eng_a", "pass1234"),
                   "b": _login(client, "oc_eng_b", "pass1234")},
    }


# ════════════════════════════════════════════════════════════════════
# 值班规则 CRUD
# ════════════════════════════════════════════════════════════════════

class TestOnCallRulesCRUD:
    """值班规则 CRUD 正常流程"""

    def test_create_rule_autogen_shifts(self, client, db_session):
        """创建规则自动生成排班 (默认 4 cycles × 1 人 = 4 班次)。"""
        rid = _create_rule(client, db_session, name="一线轮值")
        assert rid > 0

        detail = client.get(f"{ONCALL}/rules/{rid}").json()
        assert detail["rule"]["name"] == "一线轮值"
        assert detail["rule"]["enabled"] is True
        assert len(detail["shifts"]) == 4  # 4 cycles × 1 人
        # 每班默认 scheduled
        assert all(s["status"] == "scheduled" for s in detail["shifts"])

    def test_create_rule_multi_person_rotation(self, client, db_session):
        """2 人轮换: 4 cycles → 8 班次; 多人轮换时 backup 非空。"""
        u1 = _make_user(db_session, "oc_eng_m1", UserRole.ENGINEER)
        u2 = _make_user(db_session, "oc_eng_m2", UserRole.ENGINEER)
        rid = _create_rule(client, db_session, uids=[u1.id, u2.id],
                           shift_duration_hours=24, name="双人轮值")

        detail = client.get(f"{ONCALL}/rules/{rid}").json()
        assert len(detail["shifts"]) == 8  # 4 cycles × 2 人
        # 多人轮换 → backup_user_id 应被填充
        assert any(s["backup_user_id"] is not None for s in detail["shifts"])

    def test_list_rules_with_stats(self, client, db_session):
        """列表返回 + 每条带 total_shifts / upcoming_shifts / current_oncall 统计。"""
        _create_rule(client, db_session, name="规则A")
        _create_rule(client, db_session, name="规则B")

        data = client.get(f"{ONCALL}/rules").json()
        assert data["total"] >= 2
        names = {r["name"] for r in data["rules"]}
        assert {"规则A", "规则B"} <= names
        r0 = data["rules"][0]
        assert "total_shifts" in r0 and "upcoming_shifts" in r0 and "current_oncall" in r0

    def test_list_rules_enabled_filter(self, client, db_session):
        """enabled_only=True (默认) 过滤掉 disabled 规则; =false 全见。"""
        rid = _create_rule(client, db_session, name="待禁用规则")
        client.put(f"{ONCALL}/rules/{rid}", json={"enabled": False})

        enabled = client.get(f"{ONCALL}/rules").json()
        assert all(r["name"] != "待禁用规则" for r in enabled["rules"])

        all_rules = client.get(f"{ONCALL}/rules?enabled_only=false").json()
        assert any(r["name"] == "待禁用规则" for r in all_rules["rules"])

    def test_get_rule_detail(self, client, db_session):
        """详情含 rule 元数据 + shifts 列表 (带 user/backup/状态)。"""
        rid = _create_rule(client, db_session, name="详情规则", shift_duration_hours=12)
        body = client.get(f"{ONCALL}/rules/{rid}").json()
        assert body["rule"]["id"] == rid
        assert body["rule"]["shift_duration_hours"] == 12
        assert len(body["shifts"]) == 4
        s0 = body["shifts"][0]
        assert {"id", "user_id", "user", "backup_user_id",
                "start_time", "end_time", "status", "handover_completed"} <= set(s0.keys())

    def test_get_rule_404(self, client):
        assert client.get(f"{ONCALL}/rules/99999").status_code == 404

    def test_update_rule(self, client, db_session):
        """更新 name / shift_duration_hours 生效。"""
        rid = _create_rule(client, db_session, name="原名")
        r = client.put(f"{ONCALL}/rules/{rid}",
                       json={"name": "新名", "shift_duration_hours": 48})
        assert r.status_code == 200
        assert r.json()["rule_id"] == rid

        detail = client.get(f"{ONCALL}/rules/{rid}").json()
        assert detail["rule"]["name"] == "新名"
        assert detail["rule"]["shift_duration_hours"] == 48

    def test_delete_rule_blocked_by_active_shifts(self, client, db_session):
        """规则仍有 scheduled/active 班次 → 拒绝删除 (400)。"""
        rid = _create_rule(client, db_session, name="有班次规则")
        r = client.delete(f"{ONCALL}/rules/{rid}")
        assert r.status_code == 400
        assert "未完成班次" in r.json()["detail"]

    def test_delete_rule_after_shifts_done(self, client, db_session):
        """所有班次置 completed 后允许删除; 删除后详情 404。"""
        rid = _create_rule(client, db_session, name="可删规则")
        for sid in _shift_ids_of(client, rid):
            client.put(f"{ONCALL}/shifts/{sid}?status=completed")

        r = client.delete(f"{ONCALL}/rules/{rid}")
        assert r.status_code == 200
        assert client.get(f"{ONCALL}/rules/{rid}").status_code == 404

    def test_regenerate_shifts(self, client, db_session):
        """重新生成排班: created = num_cycles × len(order)。"""
        u1 = _make_user(db_session, "oc_re_a", UserRole.ENGINEER)
        u2 = _make_user(db_session, "oc_re_b", UserRole.ENGINEER)
        rid = _create_rule(client, db_session, uids=[u1.id, u2.id],
                           shift_duration_hours=24, name="重排规则")

        r = client.post(f"{ONCALL}/rules/{rid}/generate-shifts?num_cycles=3")
        assert r.status_code == 200
        body = r.json()
        assert body["created"] == 6  # 3 cycles × 2 人

    def test_regenerate_shifts_404(self, client):
        assert client.post(f"{ONCALL}/rules/99999/generate-shifts").status_code == 404


# ════════════════════════════════════════════════════════════════════
# team scoping (第二层鉴权)
# ════════════════════════════════════════════════════════════════════

class TestOnCallTeamIsolation:
    """团队隔离: 团队级仅见/仅写本 team; 跨 team → 404; admin 全见。"""

    def test_team_isolation_list(self, client, team_pair):
        """A/B 各建规则, 互相列表不可见。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        tok_a, tok_b = team_pair["tokens"]["a"], team_pair["tokens"]["b"]
        ua_id, ub_id = team_pair["users"]["a"].id, team_pair["users"]["b"].id

        client.post(f"{ONCALL}/rules", json={"name": "A规则", "rotation_order": [ua_id]},
                    headers=_h(tok_a))
        client.post(f"{ONCALL}/rules", json={"name": "B规则", "rotation_order": [ub_id]},
                    headers=_h(tok_b))

        a_view = client.get(f"{ONCALL}/rules", headers=_h(tok_a)).json()
        a_names = {r["name"] for r in a_view["rules"]}
        assert "A规则" in a_names and "B规则" not in a_names

        b_view = client.get(f"{ONCALL}/rules", headers=_h(tok_b)).json()
        b_names = {r["name"] for r in b_view["rules"]}
        assert "B规则" in b_names and "A规则" not in b_names

    def test_team_create_locked_to_own(self, client, team_pair):
        """团队级用户 body 指定他队 team_id 仍被强制锁本人 team。"""
        ta, tb = team_pair["teams"]["a"], team_pair["teams"]["b"]
        tok_a = team_pair["tokens"]["a"]
        ua_id = team_pair["users"]["a"].id

        r = client.post(f"{ONCALL}/rules",
                        json={"name": "越权尝试", "rotation_order": [ua_id], "team_id": tb.id},
                        headers=_h(tok_a))
        assert r.status_code == 200
        rid = r.json()["rule_id"]

        detail = client.get(f"{ONCALL}/rules/{rid}", headers=_h(tok_a)).json()
        assert detail["rule"]["team_id"] == ta.id  # 锁本人 team, 伪造 team_id 被忽略

    def test_cross_team_get_returns_404(self, client, team_pair):
        """团队级用户读他队规则 → 404 (不泄露存在)。"""
        tok_a, tok_b = team_pair["tokens"]["a"], team_pair["tokens"]["b"]
        ub_id = team_pair["users"]["b"].id

        rid = client.post(f"{ONCALL}/rules",
                          json={"name": "B私有", "rotation_order": [ub_id]},
                          headers=_h(tok_b)).json()["rule_id"]

        # A 读 B 的规则 → 404
        assert client.get(f"{ONCALL}/rules/{rid}", headers=_h(tok_a)).status_code == 404

    def test_cross_team_write_returns_404(self, client, team_pair):
        """团队级用户往他队规则手动建班次 → 404。"""
        tok_a, tok_b = team_pair["tokens"]["a"], team_pair["tokens"]["b"]
        ua_id, ub_id = team_pair["users"]["a"].id, team_pair["users"]["b"].id

        rid = client.post(f"{ONCALL}/rules",
                          json={"name": "A私有", "rotation_order": [ua_id]},
                          headers=_h(tok_a)).json()["rule_id"]

        r = client.post(f"{ONCALL}/shifts",
                        json={"rule_id": rid, "user_id": ub_id,
                              "start_time": "2026-01-01T00:00:00+00:00",
                              "end_time": "2026-01-02T00:00:00+00:00"},
                        headers=_h(tok_b))
        assert r.status_code == 404

    def test_admin_sees_all_teams(self, client, team_pair):
        """admin 平台级, 跨团队可见全部规则。"""
        tok_a, tok_b = team_pair["tokens"]["a"], team_pair["tokens"]["b"]
        ua_id, ub_id = team_pair["users"]["a"].id, team_pair["users"]["b"].id
        client.post(f"{ONCALL}/rules", json={"name": "A规则", "rotation_order": [ua_id]},
                    headers=_h(tok_a))
        client.post(f"{ONCALL}/rules", json={"name": "B规则", "rotation_order": [ub_id]},
                    headers=_h(tok_b))

        # client 默认 admin token
        data = client.get(f"{ONCALL}/rules").json()
        names = {r["name"] for r in data["rules"]}
        assert {"A规则", "B规则"} <= names

    def test_team_isolation_list_shifts(self, client, team_pair):
        """list_shifts 团队级仅见本 team 班次 (经 OnCallRule.team_id 过滤), 不泄露他队工程师。"""
        tok_a, tok_b = team_pair["tokens"]["a"], team_pair["tokens"]["b"]
        ua_id, ub_id = team_pair["users"]["a"].id, team_pair["users"]["b"].id

        client.post(f"{ONCALL}/rules", json={"name": "A规则", "rotation_order": [ua_id]},
                    headers=_h(tok_a))
        client.post(f"{ONCALL}/rules", json={"name": "B规则", "rotation_order": [ub_id]},
                    headers=_h(tok_b))

        a_view = client.get(f"{ONCALL}/shifts?page_size=100", headers=_h(tok_a)).json()
        assert a_view["total"] > 0
        a_uids = {s["user_id"] for s in a_view["shifts"]}
        assert a_uids == {ua_id}  # 不含 B 团队工程师

        b_view = client.get(f"{ONCALL}/shifts?page_size=100", headers=_h(tok_b)).json()
        b_uids = {s["user_id"] for s in b_view["shifts"]}
        assert b_uids == {ub_id}

    def test_team_isolation_stats(self, client, team_pair):
        """get_stats 团队级统计只计本 team 班次/by_user, 不计他队。"""
        tok_a, tok_b = team_pair["tokens"]["a"], team_pair["tokens"]["b"]
        ua_id, ub_id = team_pair["users"]["a"].id, team_pair["users"]["b"].id

        rid_a = client.post(f"{ONCALL}/rules",
                            json={"name": "A规则", "rotation_order": [ua_id],
                                  "shift_duration_hours": 24, "num_cycles": 1},
                            headers=_h(tok_a)).json()["rule_id"]
        rid_b = client.post(f"{ONCALL}/rules",
                            json={"name": "B规则", "rotation_order": [ub_id],
                                  "shift_duration_hours": 24},
                            headers=_h(tok_b)).json()["rule_id"]
        assert rid_a and rid_b

        # A 只统计到本人班次, 不含 B
        stats_a = client.get(f"{ONCALL}/stats", headers=_h(tok_a)).json()
        a_uids = {row["user_id"] for row in stats_a["by_user"]}
        assert a_uids == {ua_id}
        a_total = stats_a["shifts"]["total"]
        assert a_total > 0

        # B 同理; 两团队 total 相加 <= admin 全量 (admin 不受过滤)
        stats_b = client.get(f"{ONCALL}/stats", headers=_h(tok_b)).json()
        b_uids = {row["user_id"] for row in stats_b["by_user"]}
        assert b_uids == {ub_id}

        stats_admin = client.get(f"{ONCALL}/stats").json()  # client 默认 admin
        admin_uids = {row["user_id"] for row in stats_admin["by_user"]}
        assert admin_uids >= {ua_id, ub_id}


# ════════════════════════════════════════════════════════════════════
# 班次 (排班)
# ════════════════════════════════════════════════════════════════════

class TestOnCallShifts:
    """当前值班 / 班次列表 / 手动创建 / 状态更新"""

    def test_current_shifts_after_create(self, client, db_session):
        """创建规则后, 自动生成的首个班次覆盖当前 → current_shifts 命中。"""
        rid = _create_rule(client, db_session, name="当前值班规则")
        data = client.get(f"{ONCALL}/shifts/current").json()
        assert any(s["rule_id"] == rid for s in data["current_shifts"])
        cs = data["current_shifts"][0]
        assert {"shift_id", "rule_id", "rule_name", "primary", "backup",
                "start_time", "end_time", "remaining_hours"} <= set(cs.keys())

    def test_current_shifts_empty(self, client):
        """无规则时 current_shifts 为空。"""
        data = client.get(f"{ONCALL}/shifts/current").json()
        assert data["current_shifts"] == []

    def test_list_shifts_filter(self, client, db_session):
        """班次列表按 rule_id / status 过滤。"""
        u1 = _make_user(db_session, "oc_lst1", UserRole.ENGINEER)
        rid = _create_rule(client, db_session, uids=[u1.id], name="列表规则")

        by_rule = client.get(f"{ONCALL}/shifts?rule_id={rid}").json()
        assert by_rule["total"] == 4
        assert all(s["rule_id"] == rid for s in by_rule["shifts"])

        scheduled = client.get(f"{ONCALL}/shifts?rule_id={rid}&status=scheduled").json()
        assert scheduled["total"] == 4
        completed = client.get(f"{ONCALL}/shifts?rule_id={rid}&status=completed").json()
        assert completed["total"] == 0

    def test_create_shift_manual(self, client, db_session):
        """手动创建一个覆盖当前时段的班次, current 立即命中。"""
        from datetime import datetime, timezone, timedelta
        u1 = _make_user(db_session, "oc_manual1", UserRole.ENGINEER)
        rid = _create_rule(client, db_session, uids=[u1.id], name="手动班次规则")
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        r = client.post(f"{ONCALL}/shifts",
                        json={"rule_id": rid, "user_id": u1.id,
                              "start_time": start, "end_time": end})
        assert r.status_code == 200
        sid = r.json()["shift_id"]

        current = client.get(f"{ONCALL}/shifts/current").json()
        assert any(s["shift_id"] == sid for s in current["current_shifts"])

    def test_create_shift_rule_not_found(self, client, db_session):
        u1 = _make_user(db_session, "oc_manual2", UserRole.ENGINEER)
        r = client.post(f"{ONCALL}/shifts",
                        json={"rule_id": 99999, "user_id": u1.id,
                              "start_time": "2026-01-01T00:00:00+00:00",
                              "end_time": "2026-01-02T00:00:00+00:00"})
        assert r.status_code == 404

    def test_update_shift_status(self, client, db_session):
        """PUT ?status= 更新班次状态, 列表可查。"""
        rid = _create_rule(client, db_session, name="状态规则")
        sid = _shift_ids_of(client, rid)[0]

        r = client.put(f"{ONCALL}/shifts/{sid}?status=completed")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

        data = client.get(f"{ONCALL}/shifts?status=completed").json()
        assert any(s["id"] == sid for s in data["shifts"])

    def test_update_shift_404(self, client):
        assert client.put(f"{ONCALL}/shifts/99999?status=active").status_code == 404


# ════════════════════════════════════════════════════════════════════
# 交接班
# ════════════════════════════════════════════════════════════════════

class TestOnCallHandover:
    """交接班状态流转 + 幂等守卫"""

    def test_handover_success(self, client, db_session):
        """交接成功 → shift.handover_completed=True。"""
        rid = _create_rule(client, db_session, name="交接规则")
        sid = _shift_ids_of(client, rid)[0]
        admin_id = _uid(db_session, "admin")

        r = client.post(f"{ONCALL}/shifts/handover",
                        json={"shift_id": sid, "notes": "正常交接", "user_id": admin_id})
        assert r.status_code == 200

        detail = client.get(f"{ONCALL}/rules/{rid}").json()
        target = next(s for s in detail["shifts"] if s["id"] == sid)
        assert target["handover_completed"] is True

    def test_handover_idempotent_400(self, client, db_session):
        """已交接的班次再次交接 → 400 (防双交接日志)。"""
        rid = _create_rule(client, db_session, name="幂等交接")
        sid = _shift_ids_of(client, rid)[0]
        admin_id = _uid(db_session, "admin")
        client.post(f"{ONCALL}/shifts/handover",
                    json={"shift_id": sid, "notes": "第一次", "user_id": admin_id})

        r = client.post(f"{ONCALL}/shifts/handover",
                        json={"shift_id": sid, "notes": "第二次", "user_id": admin_id})
        assert r.status_code == 400
        assert "已完成交接" in r.json()["detail"]

    def test_handover_shift_not_found(self, client, db_session):
        admin_id = _uid(db_session, "admin")
        r = client.post(f"{ONCALL}/shifts/handover",
                        json={"shift_id": 99999, "notes": "x", "user_id": admin_id})
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# 值班日志
# ════════════════════════════════════════════════════════════════════

class TestOnCallLogs:
    """日志创建 / 列表过滤"""

    def test_create_log(self, client, db_session):
        rid = _create_rule(client, db_session, name="日志规则")
        sid = _shift_ids_of(client, rid)[0]
        admin_id = _uid(db_session, "admin")

        r = client.post(f"{ONCALL}/logs", json={
            "shift_id": sid, "user_id": admin_id,
            "event_type": "alarm", "content": "告警处理", "severity": "warning",
        })
        assert r.status_code == 200
        assert r.json()["log_id"] > 0

    def test_list_logs_filter(self, client, db_session):
        rid = _create_rule(client, db_session, name="日志列表规则")
        sid = _shift_ids_of(client, rid)[0]
        admin_id = _uid(db_session, "admin")
        client.post(f"{ONCALL}/logs", json={
            "shift_id": sid, "user_id": admin_id, "event_type": "note", "content": "备注",
        })
        client.post(f"{ONCALL}/logs", json={
            "shift_id": sid, "user_id": admin_id, "event_type": "alarm", "content": "告警",
        })

        by_shift = client.get(f"{ONCALL}/logs?shift_id={sid}").json()
        assert by_shift["total"] == 2

        by_type = client.get(f"{ONCALL}/logs?event_type=alarm").json()
        assert by_type["total"] >= 1
        assert all(l["event_type"] == "alarm" for l in by_type["logs"])

    def test_create_log_shift_not_found(self, client, db_session):
        admin_id = _uid(db_session, "admin")
        r = client.post(f"{ONCALL}/logs", json={
            "shift_id": 99999, "user_id": admin_id, "content": "x",
        })
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# 统计报表
# ════════════════════════════════════════════════════════════════════

class TestOnCallStats:
    """统计报表结构 + 数据反映"""

    def test_stats_structure_empty(self, client):
        """无数据时 stats 结构完整, 计数为 0。"""
        data = client.get(f"{ONCALL}/stats").json()
        assert data["period_days"] == 30
        assert {"shifts", "handover", "logs", "by_user"} <= set(data.keys())
        assert data["shifts"]["total"] == 0
        assert data["shifts"]["completion_rate"] == 0

    def test_stats_reflects_data(self, client, db_session):
        """统计反映: 班次总数 / 完成 / 交接 / 日志。"""
        rid = _create_rule(client, db_session, name="统计规则")
        sids = _shift_ids_of(client, rid)
        admin_id = _uid(db_session, "admin")

        # 完成 2 个班次
        for sid in sids[:2]:
            client.put(f"{ONCALL}/shifts/{sid}?status=completed")
        # 交接 1 个
        client.post(f"{ONCALL}/shifts/handover",
                    json={"shift_id": sids[0], "notes": "交接", "user_id": admin_id})
        # 记 1 条日志
        client.post(f"{ONCALL}/logs", json={
            "shift_id": sids[0], "user_id": admin_id, "event_type": "note", "content": "统计日志",
        })

        data = client.get(f"{ONCALL}/stats?days=30").json()
        assert data["shifts"]["total"] >= 4
        assert data["shifts"]["completed"] >= 2
        assert data["handover"]["completed"] >= 1
        assert data["logs"]["total"] >= 1
        assert "note" in data["logs"]["by_event_type"]

    def test_stats_days_param(self, client):
        """days 参数控制窗口 (默认 30, 可指定)。"""
        d7 = client.get(f"{ONCALL}/stats?days=7").json()
        assert d7["period_days"] == 7


# ════════════════════════════════════════════════════════════════════
# 权限门
# ════════════════════════════════════════════════════════════════════

class TestOnCallPermission:
    """认证 (401) 与授权 (403) 门"""

    def test_anon_write_401(self, anon_client):
        """无 token 写 → 401。"""
        r = anon_client.post(f"{ONCALL}/rules", json={"name": "x", "rotation_order": [1]})
        assert r.status_code == 401

    def test_anon_read_401(self, anon_client):
        """无 token 读 → 401 (get_current_user 强制认证)。"""
        assert anon_client.get(f"{ONCALL}/rules").status_code == 401

    def test_anon_shifts_current_401(self, anon_client):
        assert anon_client.get(f"{ONCALL}/shifts/current").status_code == 401

    def test_viewer_write_403(self, client, db_session):
        """viewer 无 workorder:edit → 写操作 403 (在 body 解析前拦截)。"""
        v = _make_user(db_session, "oc_viewer1", UserRole.VIEWER)
        tok = _login(client, "oc_viewer1", "pass1234")
        r = client.post(f"{ONCALL}/rules",
                        json={"name": "x", "rotation_order": [v.id]}, headers=_h(tok))
        assert r.status_code == 403

    def test_viewer_read_ok(self, client, db_session):
        """viewer 读放行 (require_write_permission 对 GET 仅认证不查权限)。"""
        _make_user(db_session, "oc_viewer2", UserRole.VIEWER)
        tok = _login(client, "oc_viewer2", "pass1234")
        r = client.get(f"{ONCALL}/rules", headers=_h(tok))
        assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════
# 参数校验边界
# ════════════════════════════════════════════════════════════════════

class TestOnCallValidation:
    """业务层校验 (schema 仅约束类型, 长度/范围下沉业务层返回明确 400 中文)"""

    def test_create_empty_rotation_400(self, client):
        r = client.post(f"{ONCALL}/rules", json={"name": "空轮换", "rotation_order": []})
        assert r.status_code == 400
        assert "至少需要 1 名" in r.json()["detail"]

    def test_create_zero_duration_400(self, client, db_session):
        admin_id = _uid(db_session, "admin")
        r = client.post(f"{ONCALL}/rules", json={
            "name": "零时长", "rotation_order": [admin_id], "shift_duration_hours": 0,
        })
        assert r.status_code == 400
        assert "大于 0" in r.json()["detail"]

    def test_create_user_not_exist_400(self, client):
        r = client.post(f"{ONCALL}/rules", json={"name": "鬼用户", "rotation_order": [99999]})
        assert r.status_code == 400
        assert "不存在" in r.json()["detail"]

    def test_create_teamless_user_400(self, client, db_session):
        """团队级用户无 team_id → 创建规则 400 (规则必须归属某团队)。"""
        u = _make_user(db_session, "oc_noteam", UserRole.ENGINEER, team_id=None)
        tok = _login(client, "oc_noteam", "pass1234")
        r = client.post(f"{ONCALL}/rules",
                        json={"name": "无归属", "rotation_order": [u.id]}, headers=_h(tok))
        assert r.status_code == 400
        assert "归属" in r.json()["detail"]

    def test_update_empty_rotation_400(self, client, db_session):
        rid = _create_rule(client, db_session, name="更新空轮换")
        r = client.put(f"{ONCALL}/rules/{rid}", json={"rotation_order": []})
        assert r.status_code == 400
        assert "至少需要 1 名" in r.json()["detail"]

    def test_update_zero_duration_400(self, client, db_session):
        rid = _create_rule(client, db_session, name="更新零时长")
        r = client.put(f"{ONCALL}/rules/{rid}", json={"shift_duration_hours": 0})
        assert r.status_code == 400
        assert "大于 0" in r.json()["detail"]

    def test_update_rule_404(self, client):
        assert client.put(f"{ONCALL}/rules/99999", json={"name": "x"}).status_code == 404

    def test_delete_rule_404(self, client):
        assert client.delete(f"{ONCALL}/rules/99999").status_code == 404
