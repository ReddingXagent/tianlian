"""运营-平台服务费配置 API 测试 (工作卡 05a0e2bb — 4 路由零测试补全)

覆盖 /api/v1/ops/platform-fee:
- CRUD happy path (创建→查询→更新→删除)
- 权限门: 无 operate:manage → 403; 无 token → 401
- rate_bp 边界 [0, 3000] (Pydantic Field ge/le 拦截)
- enabled 本期固定 false (契约 §4: POST 传 true 仍存 false)
- team scoping: 跨 team 不可见 / 不可改 / 不可删 (404 不泄露存在)
- 更新指定字段 (model_dump exclude_unset, 未传字段保持不变)

权限矩阵: viewer/auditor 不持 operate:manage → 403; engineer 持有但非平台 admin → team 级。
"""
import bcrypt

from app.models.user import User, UserRole, Team

PLATFORM_FEE = "/api/v1/ops/platform-fee"


# ─── seed helpers ───

def _seed_team(session, team_id, name):
    t = Team(id=team_id, name=name)
    session.add(t)
    session.commit()
    return t


def _seed_user(session, username, role, team_id=None, password="pass123"):
    u = User(
        username=username,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        role=role,
        team_id=team_id,
        status="active",
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login(client, username, password="pass123"):
    r = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _as(client, username, password="pass123"):
    """切换 client 认证身份 (覆盖默认 admin token)。"""
    client.headers["Authorization"] = f"Bearer {_login(client, username, password)}"


def _create(client, **payload):
    """便捷创建, 返回 data dict。"""
    body = {"rate_bp": 0}
    body.update(payload)
    r = client.post(PLATFORM_FEE, json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ==================== CRUD happy path ====================

class TestPlatformFeeCRUD:
    """平台服务费配置 CRUD 全流程"""

    def test_create_with_defaults(self, client):
        r = client.post(PLATFORM_FEE, json={"rate_bp": 0})
        assert r.status_code == 201
        d = r.json()["data"]
        assert d["id"] > 0
        assert d["enabled"] is False
        assert d["rate_bp"] == 0
        assert d["scope"] == "all"
        assert d["user_ids"] == []
        assert d["note"] is None

    def test_list_configs(self, client):
        _create(client, rate_bp=10, note="cfg-a")
        _create(client, rate_bp=20, note="cfg-b")
        r = client.get(PLATFORM_FEE)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] >= 2
        assert len(d["items"]) >= 2
        # 按 id desc 排序, 最新创建在前
        assert d["items"][0]["id"] > d["items"][1]["id"]

    def test_update_config(self, client):
        cfg = _create(client, rate_bp=10)
        r = client.put(f"{PLATFORM_FEE}/{cfg['id']}", json={"rate_bp": 50, "note": "updated"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["rate_bp"] == 50
        assert d["note"] == "updated"

    def test_delete_config(self, client):
        cfg = _create(client, rate_bp=10)
        r = client.delete(f"{PLATFORM_FEE}/{cfg['id']}")
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] == cfg["id"]
        items = client.get(PLATFORM_FEE).json()["data"]["items"]
        assert all(it["id"] != cfg["id"] for it in items)

    def test_update_not_found_404(self, client):
        assert client.put(f"{PLATFORM_FEE}/99999", json={"note": "x"}).status_code == 404

    def test_delete_not_found_404(self, client):
        assert client.delete(f"{PLATFORM_FEE}/99999").status_code == 404

    def test_full_crud_flow(self, client):
        """创建 → 查询 → 更新 → 删除 全流程"""
        # 创建
        cfg = _create(client, rate_bp=100, scope="whitelist", user_ids=[1, 2], note="flow")
        assert cfg["rate_bp"] == 100
        # 查询可见
        items = client.get(PLATFORM_FEE).json()["data"]["items"]
        assert any(it["id"] == cfg["id"] for it in items)
        # 更新
        updated = client.put(
            f"{PLATFORM_FEE}/{cfg['id']}", json={"rate_bp": 200, "note": "flow2"}
        ).json()["data"]
        assert updated["rate_bp"] == 200
        assert updated["note"] == "flow2"
        # 删除
        assert client.delete(f"{PLATFORM_FEE}/{cfg['id']}").status_code == 200
        assert client.delete(f"{PLATFORM_FEE}/{cfg['id']}").status_code == 404


# ==================== 权限门 ====================

class TestPlatformFeeAuth:
    """权限门: require_permission('operate:manage') + 认证"""

    def test_anon_list_denied_401(self, anon_client):
        assert anon_client.get(PLATFORM_FEE).status_code == 401

    def test_anon_create_denied_401(self, anon_client):
        assert anon_client.post(PLATFORM_FEE, json={"rate_bp": 0}).status_code == 401

    def test_viewer_no_perm_list_403(self, client):
        # viewer 不持 operate:manage → 403
        _seed_user(client._sesh, "viewer_fee", UserRole.VIEWER)
        _as(client, "viewer_fee")
        assert client.get(PLATFORM_FEE).status_code == 403

    def test_viewer_no_perm_create_403(self, client):
        _seed_user(client._sesh, "viewer_fee2", UserRole.VIEWER)
        _as(client, "viewer_fee2")
        assert client.post(PLATFORM_FEE, json={"rate_bp": 0}).status_code == 403

    def test_auditor_no_perm_403(self, client):
        # auditor 同样不持 operate:manage → 403
        _seed_user(client._sesh, "auditor_fee", UserRole.AUDITOR)
        _as(client, "auditor_fee")
        assert client.post(PLATFORM_FEE, json={"rate_bp": 0}).status_code == 403

    def test_engineer_has_perm_allowed(self, client):
        # engineer 持 operate:manage (非平台 admin) → 放行 (200, 非 403)
        _seed_team(client._sesh, 300, "team-eng")
        _seed_user(client._sesh, "eng_fee", UserRole.ENGINEER, team_id=300)
        _as(client, "eng_fee")
        assert client.get(PLATFORM_FEE).status_code == 200


# ==================== rate_bp 边界 ====================

class TestPlatformFeeRateBoundary:
    """rate_bp ∈ [0, 3000], Pydantic Field(ge=0, le=3000) 拦截"""

    def test_rate_bp_zero_ok(self, client):
        d = _create(client, rate_bp=0)
        assert d["rate_bp"] == 0

    def test_rate_bp_max_3000_ok(self, client):
        d = _create(client, rate_bp=3000)
        assert d["rate_bp"] == 3000

    def test_rate_bp_over_3000_rejected(self, client):
        r = client.post(PLATFORM_FEE, json={"rate_bp": 3001})
        assert r.status_code == 422

    def test_rate_bp_negative_rejected(self, client):
        r = client.post(PLATFORM_FEE, json={"rate_bp": -1})
        assert r.status_code == 422

    def test_update_rate_bp_boundary(self, client):
        cfg = _create(client, rate_bp=0)
        # 边界内更新成功
        assert client.put(f"{PLATFORM_FEE}/{cfg['id']}", json={"rate_bp": 3000}).status_code == 200
        # 超上限拒绝
        assert client.put(f"{PLATFORM_FEE}/{cfg['id']}", json={"rate_bp": 3001}).status_code == 422


# ==================== enabled 本期固定 false (契约 §4) ====================

class TestPlatformFeeEnabledFixed:
    """契约 §4: 本期 enabled 固定 false, 忽略请求体, 保证端侧零感知。

    源码 create_fee_config 必须 *强制* enabled=False 而非透传 body.enabled,
    否则任何持 operate:manage 的用户可 POST enabled=true 启用平台服务费抽佣。
    """

    def test_create_enabled_default_false(self, client):
        d = _create(client, rate_bp=0)
        assert d["enabled"] is False

    def test_create_enabled_true_stored_false(self, client):
        """POST 传 enabled=true 仍存为 false (本期固定不启用)。"""
        r = client.post(PLATFORM_FEE, json={"enabled": True, "rate_bp": 100})
        assert r.status_code == 201
        assert r.json()["data"]["enabled"] is False


# ==================== team scoping ====================

class TestPlatformFeeTeamScoping:
    """team 级用户仅可见/可改/可删本 team 配置; 跨 team → 404 (不泄露存在)。"""

    def _seed_two_teams(self, client):
        s = client._sesh
        _seed_team(s, 100, "ops-team-a")
        _seed_team(s, 200, "ops-team-b")
        _seed_user(s, "eng_a", UserRole.ENGINEER, team_id=100)
        _seed_user(s, "eng_b", UserRole.ENGINEER, team_id=200)

    def test_list_isolation(self, client):
        self._seed_two_teams(client)
        # eng_a 创建 team_a 配置
        _as(client, "eng_a")
        cfg = _create(client, rate_bp=10, note="team-a-only")
        # eng_b list 看不到 team_a 的配置
        _as(client, "eng_b")
        items = client.get(PLATFORM_FEE).json()["data"]["items"]
        assert all(it["id"] != cfg["id"] for it in items)

    def test_cross_team_update_denied_404(self, client):
        self._seed_two_teams(client)
        _as(client, "eng_a")
        cfg = _create(client, rate_bp=10)
        # eng_b 改 team_a 配置 → 404
        _as(client, "eng_b")
        r = client.put(f"{PLATFORM_FEE}/{cfg['id']}", json={"note": "hack"})
        assert r.status_code == 404

    def test_cross_team_delete_denied_404(self, client):
        self._seed_two_teams(client)
        _as(client, "eng_a")
        cfg = _create(client, rate_bp=10)
        # eng_b 删 team_a 配置 → 404
        _as(client, "eng_b")
        r = client.delete(f"{PLATFORM_FEE}/{cfg['id']}")
        assert r.status_code == 404
        # 原配置仍在 (eng_a 仍可见)
        _as(client, "eng_a")
        items = client.get(PLATFORM_FEE).json()["data"]["items"]
        assert any(it["id"] == cfg["id"] for it in items)

    def test_same_team_allowed(self, client):
        self._seed_two_teams(client)
        _as(client, "eng_a")
        cfg = _create(client, rate_bp=10)
        # 同 team eng_a 可改可删
        assert client.put(f"{PLATFORM_FEE}/{cfg['id']}", json={"note": "ok"}).status_code == 200
        assert client.delete(f"{PLATFORM_FEE}/{cfg['id']}").status_code == 200

    def test_admin_sees_all_teams(self, client):
        """平台 admin (team_scope=None) 跨 team 全可见。"""
        self._seed_two_teams(client)
        _as(client, "eng_a")
        _create(client, rate_bp=10)
        _as(client, "eng_b")
        _create(client, rate_bp=20)
        # admin (conftest 默认身份) 切回
        _as(client, "admin", "admin123")
        items = client.get(PLATFORM_FEE).json()["data"]["items"]
        team_ids = {it["team_id"] for it in items}
        assert {100, 200} <= team_ids


# ==================== 更新指定字段 (exclude_unset) ====================

class TestPlatformFeePartialUpdate:
    """model_dump(exclude_unset=True): 只传的字段更新, 其余保持不变。"""

    def test_update_only_note_keeps_others(self, client):
        cfg = _create(client, rate_bp=100, scope="all", note="orig")
        r = client.put(f"{PLATFORM_FEE}/{cfg['id']}", json={"note": "new-note"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["note"] == "new-note"
        # 未传字段保持不变
        assert d["rate_bp"] == 100
        assert d["scope"] == "all"

    def test_update_scope_and_user_ids(self, client):
        cfg = _create(client, rate_bp=0)
        r = client.put(
            f"{PLATFORM_FEE}/{cfg['id']}",
            json={"scope": "whitelist", "user_ids": [1, 2, 3]},
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["scope"] == "whitelist"
        assert d["user_ids"] == [1, 2, 3]
        assert d["rate_bp"] == 0  # 未传保持
