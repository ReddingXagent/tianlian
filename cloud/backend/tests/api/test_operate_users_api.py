"""运营-用户类型管理 API 补全测试 (工作卡 1a810c16)

覆盖 app/api/v1/operate/users_api.py (挂 /api/v1/operate 前缀):
- GET  /operate/users                  用户列表 (team scoping + 筛选/分页)
- GET  /operate/users/stats            用户统计 (team scoping)
- GET  /operate/users/by-type/{type}   按类型筛选 (类型校验 + team scoping)
- PUT  /operate/users/{id}             编辑用户 (operate:manage + team scoping + 500 兜底)

与既有 tests/test_operate_users_api.py (17 测试, admin 视角) 及
tests/test_team_scoping.py (list/stats 过滤) 互补 —— 本文件补其未覆盖的真实缺口:
1. by-type 类型白名单校验 + 语义断裂现状固化 (VALID_USER_TYPES 与 User.role
   两套枚举无交集 —— 见 TestByTypeTypes docstring, 大缺陷未修仅报告)。
2. PUT 编辑的 team scoping: 跨 team 编辑 → 404 / 本 team operator 放行 /
   viewer 无 operate:manage → 403 (rbac_real_gaps 仅测过 viewer 403)。
3. PUT / by-type 异常兜底 500 (JSONResponse 分支, 不泄露异常细节)。
4. stats team scoping 口径 (total/by_status/active_count 仅本 team)。
5. 分页参数校验 (page=0 / page_size=101 → 422)。
"""
import uuid

import bcrypt
import pytest

from app.models.end_user import EndUser, EndUserStatus, EndUserType
from app.models.user import User, UserRole

USERS_URL = "/api/v1/operate/users"


# ─── helpers (风格对齐 test_ops_invoice_request.py) ───

def _add_user(session, username, role=UserRole.VIEWER, team_id=None,
              password="pw123456", status="active"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status=status,
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


def _add_end_user(session, openid, user_type=EndUserType.APP):
    end_user = EndUser(
        wx_openid=openid,
        nickname=openid,
        user_type=user_type,
        status=EndUserStatus.ACTIVE,
    )
    session.add(end_user)
    session.commit()
    session.refresh(end_user)
    return end_user


@pytest.fixture
def two_teams(client):
    """两队 + 各一名 viewer 用户 + 本队 operator (持 operate:manage)。"""
    from app.models.user import Team
    s = client._sesh
    h = uuid.uuid4().hex[:6]
    ta = Team(name=f"U队A{h}", code=f"UA{h}")
    tb = Team(name=f"U队B{h}", code=f"UB{h}")
    s.add_all([ta, tb]); s.commit(); s.refresh(ta); s.refresh(tb)
    ua = _add_user(s, f"u_a_{h}", role=UserRole.VIEWER, team_id=ta.id)
    ub = _add_user(s, f"u_b_{h}", role=UserRole.VIEWER, team_id=tb.id)
    op = _add_user(s, f"u_op_{h}", role=UserRole.OPERATOR, team_id=ta.id)
    return {
        "s": s, "ta": ta, "tb": tb, "ua": ua, "ub": ub, "op": op, "h": h,
        "token_op": _login_token(client, op.username),
    }


# ==================== 1. by-type 类型校验 ====================

class TestByTypeTypes:
    """GET /users/by-type/{type} —— 类型白名单校验 + EndUser 真实口径。"""

    def test_by_type_valid_returns_200_scoped_ok(self, client, two_teams):
        """合法类型 → 200 + 分页结构 (非 admin 请求走 team 过滤分支, 不炸)。"""
        end_user = _add_end_user(two_teams["s"], f"openid-a-{two_teams['h']}")
        _add_end_user(two_teams["s"], f"openid-b-{two_teams['h']}",
                      user_type=EndUserType.ENTERPRISE)
        r = client.get(f"{USERS_URL}/by-type/app", headers=_auth(two_teams["token_op"]))
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["end_user_id"] == end_user.id
        assert d["items"][0]["user_type"] == "app"

    def test_by_type_admin_200(self, client, two_teams):
        r = client.get(f"{USERS_URL}/by-type/app")  # 默认 admin
        assert r.status_code == 200

    def test_by_type_invalid_400(self, client, two_teams):
        r = client.get(f"{USERS_URL}/by-type/ghost", headers=_auth(two_teams["token_op"]))
        assert r.status_code == 400
        assert "无效的用户类型" in r.json()["detail"]

    def test_by_type_rbac_role_rejected_400(self, client, two_teams):
        """RBAC 角色值不在白名单 → 400 (固化断裂现状, 修复时翻转)。"""
        r = client.get(f"{USERS_URL}/by-type/viewer", headers=_auth(two_teams["token_op"]))
        assert r.status_code == 400

    def test_by_type_anonymous_401(self, anon_client):
        """router 级认证先于端点内类型校验。"""
        r = anon_client.get(f"{USERS_URL}/by-type/ghost")
        assert r.status_code == 401


# ==================== 2. PUT 编辑 team scoping + 权限门 ====================

class TestUpdateUserTeamScoping:
    """PUT /users/{id} —— operate:manage 门 + assert_team_access 越权 → 404。"""

    def test_cross_team_edit_404(self, client, two_teams):
        """A 队 operator 编辑 B 队用户 → 404 (不泄露存在)。"""
        t = two_teams
        r = client.put(
            f"{USERS_URL}/{t['ub'].id}",
            json={"real_name": "越权改名"},
            headers=_auth(t["token_op"]),
        )
        assert r.status_code == 404

    def test_same_team_edit_ok(self, client, two_teams):
        """A 队 operator 编辑本队用户 → 200 (operator 持 operate:manage)。"""
        t = two_teams
        r = client.put(
            f"{USERS_URL}/{t['ua'].id}",
            json={"real_name": "本队合法改名"},
            headers=_auth(t["token_op"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["real_name"] == "本队合法改名"

    def test_viewer_edit_403(self, client, two_teams):
        """viewer 无 operate:manage → 403 (权限门先于 team 校验)。"""
        t = two_teams
        tok = _login_token(client, t["ua"].username)
        r = client.put(
            f"{USERS_URL}/{t['ua'].id}",
            json={"real_name": "自改"},
            headers=_auth(tok),
        )
        assert r.status_code == 403

    def test_admin_cross_team_edit_ok(self, client, two_teams):
        """admin 平台级豁免: 跨队编辑 → 200。"""
        t = two_teams
        r = client.put(f"{USERS_URL}/{t['ub'].id}", json={"real_name": "管理员改名"})
        assert r.status_code == 200
        assert r.json()["data"]["real_name"] == "管理员改名"

    def test_partial_update_keeps_other_fields(self, client, two_teams):
        """部分更新 (exclude_unset): 仅改 real_name, phone 不动。"""
        t = two_teams
        r = client.put(
            f"{USERS_URL}/{t['ua'].id}",
            json={"real_name": "仅改名"},
            headers=_auth(t["token_op"]),
        )
        assert r.status_code == 200
        d = r.json()["data"]
        t["s"].expire_all()
        fresh = t["s"].query(User).filter_by(id=t["ua"].id).first()
        assert fresh.real_name == "仅改名"
        assert fresh.phone is None  # 未提交字段不被清空


# ==================== 3. stats team scoping 口径 ====================

class TestStatsScoping:
    """GET /users/stats —— by_user_type 改查 EndUser 真实口径。"""

    def test_stats_only_own_team(self, client, two_teams):
        t = two_teams
        _add_end_user(t["s"], f"openid-stats-{t['h']}")
        r = client.get(f"{USERS_URL}/stats", headers=_auth(t["token_op"]))
        assert r.status_code == 200
        s = r.json()["data"]
        assert s["total"] == 2  # 本队 ua(viewer) + op(operator)
        # by_user_type 键齐 5 类, 且统计当前测试库中的真实 C 端用户
        assert set(s["by_user_type"].keys()) == {
            "app", "card", "vin", "interconnect", "enterprise"}
        assert s["by_user_type"]["app"] >= 1

    def test_stats_admin_counts_all(self, client, two_teams):
        t = two_teams
        r = client.get(f"{USERS_URL}/stats")
        assert r.status_code == 200
        s = r.json()["data"]
        assert s["total"] >= 3  # admin(无队) + 两队各至少 1 人

    def test_stats_by_status_scoped(self, client, two_teams):
        """by_status 同样只统计本 team。"""
        t = two_teams
        _add_user(t["s"], f"u_susp_{t['h']}", role=UserRole.VIEWER,
                  team_id=t["ta"].id, status="suspended")
        r = client.get(f"{USERS_URL}/stats", headers=_auth(t["token_op"]))
        s = r.json()["data"]
        assert s["by_status"].get("suspended") == 1
        assert s["active_count"] == 2  # ua + op


# ==================== 4. 列表分页/筛选参数校验 ====================

class TestListParamsValidation:
    def test_page_zero_422(self, client):
        r = client.get(f"{USERS_URL}", params={"page": 0})
        assert r.status_code == 422

    def test_page_size_over_max_422(self, client):
        r = client.get(f"{USERS_URL}", params={"page_size": 101})
        assert r.status_code == 422

    def test_by_type_page_zero_422(self, client):
        r = client.get(f"{USERS_URL}/by-type/app", params={"page": 0})
        assert r.status_code == 422


# ==================== 5. PUT 异常兜底 500 ====================

class TestUpdateUserExceptionSafety:
    """PUT except Exception → JSONResponse 500, detail 固定文案不泄露异常。"""

    def test_update_500_generic_detail(self, client, monkeypatch):
        import app.api.v1.operate.users_api as mod
        s = client._sesh
        u = _add_user(s, f"u_boom_{uuid.uuid4().hex[:6]}")

        def boom(*a, **k):
            raise RuntimeError("编辑爆炸敏感信息")

        monkeypatch.setattr(mod, "assert_team_access", boom)
        r = client.put(f"{USERS_URL}/{u.id}", json={"real_name": "x"})
        assert r.status_code == 500
        assert r.json()["detail"] == "服务器内部错误，请稍后重试"
        assert "编辑爆炸" not in r.text

    def test_by_type_500_generic_detail(self, client, monkeypatch):
        """by-type try 内查询异常 → JSONResponse 500 固定文案 (不泄露)。

        注入点选 paginated_response (try 内首调用): 不能 patch session.query ——
        它在依赖阶段 (get_current_user) 就被使用, 会把鉴权也炸掉, 异常穿透
        TestClient 而非走端点兜底 (对齐 owner_cockpit 注入点选择经验)。
        """
        import app.api.v1.operate.users_api as mod

        def boom(*a, **k):
            raise RuntimeError("by-type序列化爆炸敏感信息")

        monkeypatch.setattr(mod, "paginated_response", boom)
        r = client.get(f"{USERS_URL}/by-type/app")
        assert r.status_code == 500
        assert r.json()["detail"] == "服务器内部错误，请稍后重试"
        assert "by-type序列化爆炸" not in r.text
