"""运营-互联互通 API 测试 (app/api/v1/operate/interconnect.py, 挂 /api/v1/operate 前缀)

覆盖 9 端点 (router-level require_permission("operate:manage")):
  配置 CRUD  GET/POST/PUT/DELETE /interconnect/configs, GET /interconnect/configs/{id}
  联调测试  POST /interconnect/configs/{id}/test
  订单管理  GET/POST /interconnect/orders, GET /interconnect/orders/{id}

权限门: admin/OPERATOR 持 operate:manage 通过; VIEWER 不持 → 403; 匿名 → 401。
team scoping (任务卡 708350b3):
  - team_scope(current_user): admin → None(全可见); 团队级 → user.team_id 仅本 team。
  - assert_team_access: 单资源 admin 豁免; 团队级 team_id 不匹配 → 404 (不泄露存在)。
  - 创建时 team_id = current_user.team_id or 0 (admin team_id=None → 0=平台模板)。

运营侧统一 success_response (code=200) / paginated_response (data.items)。
"""
import uuid

import bcrypt
import pytest

from app.models.admin_interconnect import InterconnectConfig, InterconnectOrder
from app.models.user import User, UserRole, Team

BASE = "/api/v1/operate/interconnect"


# ─── helpers ───

def _add_user(session, username, role=UserRole.OPERATOR, team_id=None, password="pw123456"):
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


def _valid_config_payload(**overrides):
    base = {
        "platform_name": "华为充电平台",
        "platform_code": "huawei",
        "api_base_url": "https://api.huawei.example.com",
        "auth_type": "apikey",
        "auth_params": {"key": "abc123"},
        "revenue_share_ratio": "0.7000",
        "data_sync_interval": 600,
        "sync_direction": "pull",
        "status": "active",
    }
    base.update(overrides)
    return base


def _seed_config(session, *, team_id=0, platform_code="huawei", api_base_url="https://api.x.com",
                 status="active", platform_name=None):
    cfg = InterconnectConfig(
        team_id=team_id,
        platform_name=platform_name or f"平台{uuid.uuid4().hex[:4]}",
        platform_code=platform_code,
        api_base_url=api_base_url,
        auth_type="apikey",
        revenue_share_ratio="0.7000",
        data_sync_interval=300,
        sync_direction="pull",
        status=status,
    )
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


def _seed_order(session, *, team_id=0, platform_id=1, outer_order_id=None, status="synced",
                platform_code="huawei"):
    o = InterconnectOrder(
        team_id=team_id,
        platform_id=platform_id,
        platform_code=platform_code,
        outer_order_id=outer_order_id or f"OUT-{uuid.uuid4().hex[:8]}",
        status=status,
        total_amount="10.00",
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


# ─── 脚手架: 两团队 + 两 OPERATOR + 一 VIEWER ───

@pytest.fixture
def teams(client):
    s = client._sesh
    h = uuid.uuid4().hex[:6]
    ta = Team(name=f"互联团队A{h}", code=f"ICA{h}")
    tb = Team(name=f"互联团队B{h}", code=f"ICB{h}")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    op_a = _add_user(s, f"ic_op_a_{h}", UserRole.OPERATOR, team_id=ta.id)
    op_b = _add_user(s, f"ic_op_b_{h}", UserRole.OPERATOR, team_id=tb.id)
    viewer = _add_user(s, f"ic_viewer_{h}", UserRole.VIEWER)  # 无 operate:manage
    return {
        "s": s, "ta": ta, "tb": tb, "op_a": op_a, "op_b": op_b, "viewer": viewer, "h": h,
        "token_a": _login_token(client, f"ic_op_a_{h}"),
        "token_b": _login_token(client, f"ic_op_b_{h}"),
        "token_viewer": _login_token(client, f"ic_viewer_{h}"),
    }


# ════════════════════════════════════════════════════════════════════
# 配置列表 (team scoping + 过滤)
# ════════════════════════════════════════════════════════════════════

class TestListConfigs:
    def test_admin_sees_all_teams(self, client, teams):
        t = teams
        _seed_config(t["s"], team_id=t["ta"].id, platform_name="A队华为")
        _seed_config(t["s"], team_id=t["tb"].id, platform_name="B队国网", platform_code="sgcc")
        r = client.get(f"{BASE}/configs")  # admin
        assert r.status_code == 200
        assert r.json()["code"] == 200
        names = {i["platform_name"] for i in r.json()["data"]["items"]}
        assert {"A队华为", "B队国网"} <= names

    def test_team_user_sees_only_own_team(self, client, teams):
        t = teams
        _seed_config(t["s"], team_id=t["ta"].id, platform_name="A队配置")
        _seed_config(t["s"], team_id=t["tb"].id, platform_name="B队配置")
        r = client.get(f"{BASE}/configs", headers=_auth(t["token_a"]))
        names = {i["platform_name"] for i in r.json()["data"]["items"]}
        assert "A队配置" in names
        assert "B队配置" not in names

    def test_filter_by_platform_code(self, client, teams):
        t = teams
        _seed_config(t["s"], team_id=t["ta"].id, platform_code="huawei", platform_name="华为A")
        _seed_config(t["s"], team_id=t["ta"].id, platform_code="sgcc", platform_name="国网A")
        r = client.get(f"{BASE}/configs", params={"platform_code": "huawei"},
                       headers=_auth(t["token_a"]))
        items = r.json()["data"]["items"]
        assert len(items) == 1 and items[0]["platform_code"] == "huawei"

    def test_filter_by_keyword(self, client, teams):
        t = teams
        _seed_config(t["s"], team_id=t["ta"].id, platform_name="华为特来电A")
        _seed_config(t["s"], team_id=t["ta"].id, platform_name="国网B")
        r = client.get(f"{BASE}/configs", params={"keyword": "华为"},
                       headers=_auth(t["token_a"]))
        names = {i["platform_name"] for i in r.json()["data"]["items"]}
        assert names == {"华为特来电A"}

    def test_pagination(self, client, teams):
        for i in range(3):
            _seed_config(teams["s"], team_id=teams["ta"].id, platform_name=f"P{i}")
        r = client.get(f"{BASE}/configs", params={"page": 1, "page_size": 2},
                       headers=_auth(teams["token_a"]))
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2


# ════════════════════════════════════════════════════════════════════
# 创建配置
# ════════════════════════════════════════════════════════════════════

class TestCreateConfig:
    def test_admin_create_ok(self, client):
        r = client.post(f"{BASE}/configs", json=_valid_config_payload())
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["platform_code"] == "huawei"
        assert d["auth_params"] == {"key": "abc123"}  # JSON 往返
        assert d["team_id"] == 0  # admin team_id=None → 0 平台模板

    def test_team_user_create_stamps_team(self, client, teams):
        r = client.post(f"{BASE}/configs", json=_valid_config_payload(),
                        headers=_auth(teams["token_a"]))
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == teams["ta"].id

    def test_invalid_platform_code_400(self, client):
        r = client.post(f"{BASE}/configs", json=_valid_config_payload(platform_code="foobar"))
        assert r.status_code == 400

    def test_invalid_auth_type_400(self, client):
        """auth_type Literal 前置 → 422 (卡 6031add1)"""
        r = client.post(f"{BASE}/configs", json=_valid_config_payload(auth_type="basic"))
        assert r.status_code == 422

    def test_invalid_protocol_version_400(self, client):
        r = client.post(f"{BASE}/configs",
                        json=_valid_config_payload(protocol_version="V9.9"))
        assert r.status_code == 400

    def test_missing_required_field_422(self, client):
        """缺必填 platform_name → 422 (Pydantic)。"""
        body = _valid_config_payload()
        body.pop("platform_name")
        r = client.post(f"{BASE}/configs", json=body)
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════
# 配置详情 / 更新 / 删除 (team 归属校验)
# ════════════════════════════════════════════════════════════════════

class TestConfigDetailUpdateDelete:
    def test_get_detail_ok(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.get(f"{BASE}/configs/{cfg.id}", headers=_auth(t["token_a"]))
        assert r.status_code == 200
        assert r.json()["data"]["id"] == cfg.id

    def test_get_cross_team_404(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.get(f"{BASE}/configs/{cfg.id}", headers=_auth(t["token_b"]))
        assert r.status_code == 404

    def test_get_not_exist_404(self, client):
        r = client.get(f"{BASE}/configs/999999")
        assert r.status_code == 404

    def test_update_ok(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.put(f"{BASE}/configs/{cfg.id}", json={"status": "inactive", "remark": "停用"},
                       headers=_auth(t["token_a"]))
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "inactive"
        assert r.json()["data"]["remark"] == "停用"

    def test_update_cross_team_404(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.put(f"{BASE}/configs/{cfg.id}", json={"status": "inactive"},
                       headers=_auth(t["token_b"]))
        assert r.status_code == 404

    def test_update_invalid_status_400(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.put(f"{BASE}/configs/{cfg.id}", json={"status": "frozen"},
                       headers=_auth(t["token_a"]))
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)

    def test_delete_ok(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.delete(f"{BASE}/configs/{cfg.id}", headers=_auth(t["token_a"]))
        assert r.status_code == 200
        t["s"].expire_all()
        assert t["s"].query(InterconnectConfig).filter(InterconnectConfig.id == cfg.id).first() is None

    def test_delete_cross_team_404(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.delete(f"{BASE}/configs/{cfg.id}", headers=_auth(t["token_b"]))
        assert r.status_code == 404

    def test_delete_not_exist_404(self, client):
        r = client.delete(f"{BASE}/configs/999999")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# 联调测试 (模拟)
# ════════════════════════════════════════════════════════════════════

class TestConnectivity:
    def test_reachable_http_url(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id, api_base_url="https://api.huawei.com")
        r = client.post(f"{BASE}/configs/{cfg.id}/test", headers=_auth(t["token_a"]))
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["reachable"] is True
        assert d["auth_ok"] is True

    def test_not_reachable_bad_url(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id, api_base_url="ftp://bad.url")
        r = client.post(f"{BASE}/configs/{cfg.id}/test", headers=_auth(t["token_a"]))
        assert r.status_code == 200
        assert r.json()["data"]["reachable"] is False

    def test_test_cross_team_404(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.post(f"{BASE}/configs/{cfg.id}/test", headers=_auth(t["token_b"]))
        assert r.status_code == 404

    def test_test_not_exist_404(self, client):
        r = client.post(f"{BASE}/configs/999999/test")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# 订单列表 / 详情 / 手动录入
# ════════════════════════════════════════════════════════════════════

class TestOrders:
    def test_list_team_scoping(self, client, teams):
        t = teams
        _seed_order(t["s"], team_id=t["ta"].id)
        _seed_order(t["s"], team_id=t["tb"].id)
        # admin 全可见
        assert len(client.get(f"{BASE}/orders").json()["data"]["items"]) == 2
        # A 队只 1 条
        r = client.get(f"{BASE}/orders", headers=_auth(t["token_a"]))
        assert len(r.json()["data"]["items"]) == 1

    def test_get_order_detail(self, client, teams):
        t = teams
        o = _seed_order(t["s"], team_id=t["ta"].id)
        r = client.get(f"{BASE}/orders/{o.id}", headers=_auth(t["token_a"]))
        assert r.status_code == 200
        assert r.json()["data"]["id"] == o.id

    def test_get_order_cross_team_404(self, client, teams):
        t = teams
        o = _seed_order(t["s"], team_id=t["ta"].id)
        r = client.get(f"{BASE}/orders/{o.id}", headers=_auth(t["token_b"]))
        assert r.status_code == 404

    def test_get_order_not_exist_404(self, client):
        r = client.get(f"{BASE}/orders/999999")
        assert r.status_code == 404

    def test_create_order_ok(self, client, teams):
        """手动录入: 平台配置存在 + 同团队 → 落单 team_id=当前用户 team。"""
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.post(f"{BASE}/orders", json={
            "platform_id": cfg.id, "platform_code": "huawei",
            "outer_order_id": f"EXT-{uuid.uuid4().hex[:6]}",
            "total_amount": "12.50", "our_share": "8.75",
        }, headers=_auth(t["token_a"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["team_id"] == t["ta"].id
        assert r.json()["data"]["total_amount"] == 12.5

    def test_create_order_platform_not_exist_404(self, client, teams):
        r = client.post(f"{BASE}/orders", json={
            "platform_id": 999999, "platform_code": "huawei",
            "outer_order_id": "X1",
        }, headers=_auth(teams["token_a"]))
        assert r.status_code == 404

    def test_create_order_cross_team_platform_404(self, client, teams):
        """平台配置属 B 队, A 队 operator 不能往别人平台录单 → 404。"""
        t = teams
        cfg = _seed_config(t["s"], team_id=t["tb"].id)
        r = client.post(f"{BASE}/orders", json={
            "platform_id": cfg.id, "platform_code": "huawei",
            "outer_order_id": "X2",
        }, headers=_auth(t["token_a"]))
        assert r.status_code == 404

    def test_create_order_invalid_status_400(self, client, teams):
        t = teams
        cfg = _seed_config(t["s"], team_id=t["ta"].id)
        r = client.post(f"{BASE}/orders", json={
            "platform_id": cfg.id, "platform_code": "huawei",
            "outer_order_id": "X3", "status": "garbage",
        }, headers=_auth(t["token_a"]))
        assert r.status_code == 422  # Literal 前置 (卡 6031add1)


# ════════════════════════════════════════════════════════════════════
# 权限门 (router-level operate:manage)
# ════════════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_viewer_list_configs_403(self, client, teams):
        r = client.get(f"{BASE}/configs", headers=_auth(teams["token_viewer"]))
        assert r.status_code == 403

    def test_viewer_create_config_403(self, client, teams):
        r = client.post(f"{BASE}/configs", json=_valid_config_payload(),
                        headers=_auth(teams["token_viewer"]))
        assert r.status_code == 403

    def test_anonymous_list_configs_401(self, client):
        client.headers.pop("Authorization", None)
        assert client.get(f"{BASE}/configs").status_code == 401
