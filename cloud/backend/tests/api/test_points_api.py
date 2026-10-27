"""积分管理 API 测试 (app/api/v1/operate/points_api.py, 挂 /api/v1/operate 前缀)

覆盖 8 端点:
  规则 CRUD  POST/GET /points, GET/PUT/DELETE /points/{rule_id}
  积分流水    GET/POST /points/records
  积分统计    GET /points/stats

权限分层:
  - 写端点 (create/update/delete rule, create record) 经 require_platform_admin:
      admin/super_admin 通过; OPERATOR/engineer/viewer → 403。
  - 读端点 (list/get rule, records, stats) 仅 get_current_user: 任意 active 用户可见。

team scoping (任务卡 ab5c5f17): 积分规则为平台级配置 (全可见); 积分流水按 user→team
归属过滤, 非 admin 仅返回本 team 用户的流水。
balance_after 未显式传入时 = balance_before + points (service 推导)。
"""
import uuid

import bcrypt
import pytest

from app.models.points import PointsRule, PointsRecord, PointsRuleType, PointsRecordType
from app.models.user import User, UserRole, Team

BASE = "/api/v1/operate/points"


# ─── helpers ───

def _add_user(session, username, role=UserRole.VIEWER, team_id=None, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _rule_payload(**overrides):
    base = {
        "name": "充电积分规则",
        "rule_type": "charge",
        "points": 10,
        "unit": "每消费1元",
        "daily_limit": 100,
        "is_active": True,
    }
    base.update(overrides)
    return base


def _seed_rule(session, *, name=None, rule_type=PointsRuleType.CHARGE, points=10,
               is_active=True):
    r = PointsRule(
        name=name or f"规则{uuid.uuid4().hex[:4]}",
        rule_type=rule_type,
        points=points,
        is_active=is_active,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def _seed_record(session, *, user_id, points=10, record_type=PointsRecordType.EARN,
                 balance_before=0, balance_after=None, team_user=None):
    """落一条积分流水。team_user 仅为文档说明 (PointsRecord 本身无 team_id, 经 user 关联)。"""
    if balance_after is None:
        balance_after = balance_before + points
    rec = PointsRecord(
        user_id=user_id,
        record_type=record_type,
        points=points,
        balance_before=balance_before,
        balance_after=balance_after,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ─── 脚手架: 两团队 + 各 team 一普通用户 + OPERATOR + VIEWER ───

@pytest.fixture
def teams(client):
    s = client._sesh
    h = uuid.uuid4().hex[:6]
    ta = Team(name=f"积分团队A{h}", code=f"PTA{h}")
    tb = Team(name=f"积分团队B{h}", code=f"PTB{h}")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    cu_a = _add_user(s, f"pt_cu_a_{h}", UserRole.VIEWER, team_id=ta.id)  # A 队 C 端用户
    cu_b = _add_user(s, f"pt_cu_b_{h}", UserRole.VIEWER, team_id=tb.id)  # B 队 C 端用户
    operator = _add_user(s, f"pt_op_{h}", UserRole.OPERATOR, team_id=ta.id)  # 无 platform_admin
    viewer = _add_user(s, f"pt_v_{h}", UserRole.VIEWER, team_id=ta.id)
    return {
        "s": s, "ta": ta, "tb": tb, "cu_a": cu_a, "cu_b": cu_b,
        "operator": operator, "viewer": viewer, "h": h,
        "token_cu_a": _login_token(client, f"pt_cu_a_{h}"),
        "token_cu_b": _login_token(client, f"pt_cu_b_{h}"),
        "token_op": _login_token(client, f"pt_op_{h}"),
        "token_v": _login_token(client, f"pt_v_{h}"),
    }


# ════════════════════════════════════════════════════════════════════
# 规则 CRUD
# ════════════════════════════════════════════════════════════════════

class TestRuleCRUD:
    def test_create_rule_admin_ok(self, client):
        r = client.post(BASE, json=_rule_payload())
        assert r.status_code == 200, r.text
        assert r.json()["data"]["name"] == "充电积分规则"

    def test_create_rule_operator_403(self, client, teams):
        """require_platform_admin: OPERATOR → 403。"""
        r = client.post(BASE, json=_rule_payload(), headers=_auth(teams["token_op"]))
        assert r.status_code == 403

    def test_create_rule_invalid_points_422(self, client):
        """points < 0 → 422 (Pydantic ge=0)。"""
        r = client.post(BASE, json=_rule_payload(points=-1))
        assert r.status_code == 422

    def test_create_rule_empty_name_422(self, client):
        r = client.post(BASE, json=_rule_payload(name=""))
        assert r.status_code == 422

    def test_list_rules_any_user_ok(self, client, teams):
        """读端点仅需认证: VIEWER 也能列规则 (平台级配置)。"""
        _seed_rule(teams["s"], name="可见规则")
        r = client.get(BASE, headers=_auth(teams["token_v"]))
        assert r.status_code == 200
        names = {i["name"] for i in r.json()["data"]["items"]}
        assert "可见规则" in names

    def test_list_filter_is_active(self, client):
        _seed_rule(client._sesh, name="启用", is_active=True)
        _seed_rule(client._sesh, name="停用", is_active=False)
        r = client.get(BASE, params={"is_active": True})
        names = {i["name"] for i in r.json()["data"]["items"]}
        assert "启用" in names and "停用" not in names

    def test_list_filter_rule_type(self, client):
        _seed_rule(client._sesh, name="充电", rule_type=PointsRuleType.CHARGE)
        _seed_rule(client._sesh, name="签到", rule_type=PointsRuleType.SIGN_IN)
        r = client.get(BASE, params={"rule_type": "sign_in"})
        names = {i["name"] for i in r.json()["data"]["items"]}
        assert names == {"签到"}

    def test_get_rule_detail(self, client, teams):
        rule = _seed_rule(teams["s"], name="详情规则")
        r = client.get(f"{BASE}/{rule.id}", headers=_auth(teams["token_v"]))
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "详情规则"

    def test_get_rule_not_exist_404(self, client):
        r = client.get(f"{BASE}/999999")
        assert r.status_code == 404

    def test_update_rule_ok(self, client):
        rule = _seed_rule(client._sesh, name="待改")
        r = client.put(f"{BASE}/{rule.id}", json={"points": 99, "is_active": False})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "待改"  # 更新成功回显

    def test_update_rule_operator_403(self, client, teams):
        rule = _seed_rule(teams["s"], name="X")
        r = client.put(f"{BASE}/{rule.id}", json={"points": 5}, headers=_auth(teams["token_op"]))
        assert r.status_code == 403

    def test_update_rule_not_exist_404(self, client):
        r = client.put(f"{BASE}/999999", json={"points": 5})
        assert r.status_code == 404

    def test_delete_rule_ok(self, client):
        rule = _seed_rule(client._sesh, name="待删")
        r = client.delete(f"{BASE}/{rule.id}")
        assert r.status_code == 200
        client._sesh.expire_all()
        assert client._sesh.query(PointsRule).filter(PointsRule.id == rule.id).first() is None

    def test_delete_rule_operator_403(self, client, teams):
        rule = _seed_rule(teams["s"], name="X")
        r = client.delete(f"{BASE}/{rule.id}", headers=_auth(teams["token_op"]))
        assert r.status_code == 403

    def test_delete_rule_not_exist_404(self, client):
        r = client.delete(f"{BASE}/999999")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# 积分流水 (records)
# ════════════════════════════════════════════════════════════════════

class TestPointsRecords:
    def test_create_record_derives_balance_after(self, client):
        """balance_after 缺省 → balance_before + points。"""
        r = client.post(f"{BASE}/records", json={
            "user_id": 1, "points": 50, "balance_before": 100,
        })
        assert r.status_code == 200, r.text
        rid = r.json()["data"]["id"]
        rec = client._sesh.query(PointsRecord).filter(PointsRecord.id == rid).one()
        assert rec.balance_after == 150

    def test_create_record_explicit_balance_after(self, client):
        r = client.post(f"{BASE}/records", json={
            "user_id": 1, "points": 50, "balance_before": 100, "balance_after": 999,
        })
        assert r.status_code == 200
        rid = r.json()["data"]["id"]
        rec = client._sesh.query(PointsRecord).filter(PointsRecord.id == rid).one()
        assert rec.balance_after == 999  # 显式值不被覆盖

    def test_create_record_operator_403(self, client, teams):
        r = client.post(f"{BASE}/records", json={"user_id": 1, "points": 5},
                        headers=_auth(teams["token_op"]))
        assert r.status_code == 403

    def test_list_records_admin_sees_all(self, client, teams):
        _seed_record(teams["s"], user_id=teams["cu_a"].id, points=10)
        _seed_record(teams["s"], user_id=teams["cu_b"].id, points=20)
        r = client.get(f"{BASE}/records")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 2

    def test_list_records_team_scoping(self, client, teams):
        """非 admin 仅见本 team 用户流水: A 队 viewer 只看到 cu_a 的。"""
        _seed_record(teams["s"], user_id=teams["cu_a"].id, points=10)  # A 队
        _seed_record(teams["s"], user_id=teams["cu_b"].id, points=20)  # B 队
        r = client.get(f"{BASE}/records", headers=_auth(teams["token_v"]))  # A 队 viewer
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["user_id"] == teams["cu_a"].id

    def test_list_records_filter_user_id(self, client, teams):
        _seed_record(teams["s"], user_id=teams["cu_a"].id, points=10)
        _seed_record(teams["s"], user_id=teams["cu_a"].id, points=5)
        r = client.get(f"{BASE}/records", params={"user_id": teams["cu_a"].id},
                       headers=_auth(teams["token_v"]))
        assert r.json()["data"]["total"] == 2

    def test_list_records_filter_record_type(self, client, teams):
        _seed_record(teams["s"], user_id=teams["cu_a"].id, points=10,
                     record_type=PointsRecordType.EARN)
        _seed_record(teams["s"], user_id=teams["cu_a"].id, points=-5,
                     record_type=PointsRecordType.REDEEM)
        r = client.get(f"{BASE}/records", params={"record_type": "redeem"},
                       headers=_auth(teams["token_v"]))
        items = r.json()["data"]["items"]
        assert len(items) == 1 and items[0]["record_type"] == "redeem"


# ════════════════════════════════════════════════════════════════════
# 积分统计
# ════════════════════════════════════════════════════════════════════

class TestPointsStats:
    def test_stats_counts(self, client):
        _seed_rule(client._sesh, is_active=True)
        _seed_rule(client._sesh, is_active=False)
        _seed_record(client._sesh, user_id=1, points=30)
        _seed_record(client._sesh, user_id=1, points=20)
        r = client.get(f"{BASE}/stats")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_rules"] == 2
        assert d["active_rules"] == 1
        assert d["total_earned"] == 50  # sum(points>0)
        assert d["total_records"] == 2

    def test_stats_empty(self, client):
        r = client.get(f"{BASE}/stats")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_rules"] == 0 and d["total_earned"] == 0


# ════════════════════════════════════════════════════════════════════
# 路由顺序保护: /points/records 与 /points/stats 不被 /points/{id} 吞掉
# ════════════════════════════════════════════════════════════════════

class TestRouteOrdering:
    def test_records_route_not_swallowed(self, client, teams):
        """/points/records 是独立路由, 不被 GET /points/{rule_id:int} 抢匹配。

        FastAPI 参数 rule_id:int → "records" 非 int → 422; 但因 records 先注册, 走对的。
        """
        r = client.get(f"{BASE}/records", headers=_auth(teams["token_v"]))
        assert r.status_code == 200  # 走 list records, 非 422/404

    def test_stats_route_not_swallowed(self, client, teams):
        r = client.get(f"{BASE}/stats", headers=_auth(teams["token_v"]))
        assert r.status_code == 200
