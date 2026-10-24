"""
运营平台 - 租户品牌 CRUD API 测试 (工作卡 ea5adbe5)

覆盖端点前缀: /api/v1/operate/tenant-brands
  - POST   /tenant-brands            upsert (按 tenant_id 创建或更新)
  - GET    /tenant-brands            列表 (按 team 过滤)
  - GET    /tenant-brands/{tenant_id} 详情 (team scoping, 跨 team → 404)
  - DELETE /tenant-brands/{tenant_id} 删除 (team scoping, 跨 team → 404)

契约: backend/docs/contracts/user-client-contract.md §1 (品牌录入: ops 运营后台, 团队级)
  branding 字段: operator_name / logo_url / service_phone / theme_color

测试矩阵 (6 维度):
  ① upsert 正常流程 (创建默认值 / 更新 / team_id 服务端强制 / 契约§1 字段完整性)
  ② 格式校验 (theme_color 非法 hex → 400 / 合法 hex 通过;
     logo_url 非 http(s) → 400 / 空串与合法 URL 通过;
     必填缺失 → 422; 租户不存在 → 404)
  ③ 列表读 (空库 / 分页 / id 倒序)
  ④ 单资源读删 (详情 / 不存在 404 / 时间戳 isoformat / 删除)
  ⑤ 权限门 (router 级 operate:manage: viewer 全端点 403; 匿名 401)
  ⑥ team scoping (列表 team_scope 隔离 / admin 全见 / 创建服务端强制 team_id /
     更新·详情·删除跨 team → 404; admin 豁免; 同 team 放行)

异常保护 (维度⑦): handler 体内 try/except 兜底, DB/序列化异常 → 500 不泄露。
注入方式: monkeypatch 模块内 response 包装函数抛 SQLAlchemyError (与 supervision
卡 76d1d4d1 同源), 验证 handler 不把异常 traceback 直接外抛。

与 tests/api/test_supervision.py 同源 mock 风格: client fixture 默认 admin
(team_id=None, 平台级, team_scope=None); team 级用例经 _add_user + _login_token
注入 ENGINEER token, 直接 seed ORM 到 client._sesh (与端点 get_db 共享同一测试库)。
"""
import bcrypt
import pytest
import sqlalchemy.exc
from datetime import datetime

from app.models.user import User, UserRole, Team
from app.models.tenant import Tenant
from app.models.tenant_brand import TenantBrand


# ─── seed helpers (与 test_supervision.py 同源) ───

def _add_user(session, username, role, team_id=None, password="pw123456"):
    """创建并提交用户, 返回 ORM (供 team scoping 用例复用)。"""
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
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json().get("data", {}).get("token") or r.json().get("token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_tenant(session, name="测试租户", code="TENANT1"):
    """直接 seed 一条租户 (品牌必须挂在已存在租户上)。"""
    t = Tenant(name=name, code=code)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def _seed_brand(session, tenant_id, team_id=0, **overrides):
    """直接 seed 一条租户品牌 (绕过 API, 供列表/详情/删除/跨 team 用例使用)。"""
    b = TenantBrand(
        tenant_id=tenant_id,
        team_id=team_id,
        operator_name=overrides.get("operator_name", "测试运营商"),
        logo_url=overrides.get("logo_url", ""),
        service_phone=overrides.get("service_phone", ""),
        theme_color=overrides.get("theme_color", "#00A86B"),
    )
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


def _payload(tenant_id, **overrides):
    """upsert 请求体 (tenant_id + operator_name 必填, 其余带合法默认值)。"""
    return {
        "tenant_id": tenant_id,
        "operator_name": "天链新能源",
        "logo_url": "",
        "service_phone": "400-123-4567",
        "theme_color": "#00A86B",
        **overrides,
    }


MODULE = "app.api.v1.operate.tenant_brands"


def _boom(*_a, **_k):
    """模拟 handler 内部 DB/序列化阶段异常 (供异常保护注入)。"""
    raise sqlalchemy.exc.SQLAlchemyError("simulated db failure")


# ==================== upsert: 创建 / 更新 / 契约字段 ====================

class TestTenantBrandUpsert:
    """upsert 创建默认值 / 更新 / team_id 服务端强制 / 契约§1 字段完整性。"""

    def test_upsert_create_applies_defaults(self, client):
        """仅传必填 → schema 默认值 (theme_color=#00A86B / logo_url='' / service_phone='');
        admin(team_id=None) 创建 → team_id 服务端补 0; message='租户品牌已创建'。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json={"tenant_id": t.id, "operator_name": "天链"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["tenant_id"] == t.id
        assert d["theme_color"] == "#00A86B"
        assert d["logo_url"] == ""
        assert d["service_phone"] == ""
        assert d["team_id"] == 0  # admin → 0
        assert r.json()["message"] == "租户品牌已创建"

    def test_upsert_branding_fields_complete_contract_s1(self, client):
        """契约 §1: 四个 branding 字段完整入参 → 完整返回 (均非 null)。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands", json=_payload(
            t.id, operator_name="绿能充电",
            logo_url="https://cdn.example.com/logo.png",
            service_phone="400-100-2000", theme_color="#1A2B3C"))
        assert r.status_code == 200
        d = r.json()["data"]
        # 契约 §1 branding 四字段齐全
        for field in ("operator_name", "logo_url", "service_phone", "theme_color"):
            assert field in d and d[field] is not None
        assert d["operator_name"] == "绿能充电"
        assert d["logo_url"] == "https://cdn.example.com/logo.png"
        assert d["service_phone"] == "400-100-2000"
        assert d["theme_color"] == "#1A2B3C"

    def test_upsert_update_existing(self, client):
        """同 tenant_id 二次 upsert → 更新 (非新建), message='租户品牌已更新'。"""
        t = _seed_tenant(client._sesh)
        first = client.post("/api/v1/operate/tenant-brands", json=_payload(t.id))
        assert first.status_code == 200
        assert first.json()["message"] == "租户品牌已创建"

        r = client.post("/api/v1/operate/tenant-brands", json=_payload(
            t.id, operator_name="新名称", theme_color="#abcdef"))
        assert r.status_code == 200
        assert r.json()["message"] == "租户品牌已更新"
        d = r.json()["data"]
        assert d["operator_name"] == "新名称"
        assert d["theme_color"] == "#abcdef"
        # tenant_id 不变 (仍是同一品牌)
        assert d["tenant_id"] == t.id


# ==================== upsert: 格式校验 ====================

class TestTenantBrandValidation:
    """theme_color hex / logo_url http(s) / 必填 / 租户存在性 校验。"""

    @pytest.mark.parametrize("color", [
        "not-a-color", "#12", "#12345", "#GGGGGG", "red",
        "#1234567", "##fff", "abc", "#",
    ])
    def test_upsert_invalid_theme_color_400(self, client, color):
        """theme_color 非 #RGB/#RRGGBB → 400 (服务端 _HEX_RE 校验, 非 422)。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id, theme_color=color))
        assert r.status_code == 400, f"{color} 应 400, 实际 {r.status_code}: {r.text}"

    @pytest.mark.parametrize("color", ["#abc", "#ABC", "#00A86B", "#000", "#ffffff", "#FfF"])
    def test_upsert_valid_theme_color(self, client, color):
        """合法 #RGB/#RRGGBB (大小写不敏感) → 200 原样存。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id, theme_color=color))
        assert r.status_code == 200, f"{color} 应 200: {r.text}"
        assert r.json()["data"]["theme_color"] == color

    @pytest.mark.parametrize("url", [
        "ftp://x.com/l.png",          # 非 http(s) scheme
        "javascript:alert(1)",        # 危险 scheme
        "/relative/path",             # 相对路径 (无 netloc)
        "not a url",                  # 纯文本
        "://noscheme",                # 无 scheme
    ])
    def test_upsert_invalid_logo_url_400(self, client, url):
        """logo_url 非空且非 http(s) 绝对 URL → 400。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id, logo_url=url))
        assert r.status_code == 400, f"{url} 应 400, 实际 {r.status_code}: {r.text}"

    def test_upsert_empty_logo_url_ok(self, client):
        """logo_url='' → 200 (空串允许, 表示无 logo)。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id, logo_url=""))
        assert r.status_code == 200
        assert r.json()["data"]["logo_url"] == ""

    @pytest.mark.parametrize("url", [
        "https://cdn.example.com/logo.png",
        "http://x.com/l.svg",
    ])
    def test_upsert_valid_logo_url_ok(self, client, url):
        """合法 http(s) 绝对 URL → 200 原样存。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id, logo_url=url))
        assert r.status_code == 200
        assert r.json()["data"]["logo_url"] == url

    def test_upsert_tenant_not_found_404(self, client):
        """品牌必须挂在已存在租户上; tenant_id 不存在 → 404。"""
        r = client.post("/api/v1/operate/tenant-brands", json=_payload(999999))
        assert r.status_code == 404
        assert "租户" in r.json()["detail"]

    @pytest.mark.parametrize("missing", ["tenant_id", "operator_name"])
    def test_upsert_missing_required_field_422(self, client, missing):
        """必填字段 (tenant_id / operator_name) 缺失 → pydantic 422。"""
        t = _seed_tenant(client._sesh)
        payload = _payload(t.id)
        payload.pop(missing)
        r = client.post("/api/v1/operate/tenant-brands", json=payload)
        assert r.status_code == 422

    def test_upsert_empty_operator_name_422(self, client):
        """operator_name min_length=1 → 空串 422。"""
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id, operator_name=""))
        assert r.status_code == 422


# ==================== 列表 / 详情 / 删除 ====================

class TestTenantBrandReadDelete:
    """列表分页/排序、详情、时间戳序列化、删除。"""

    def test_list_empty(self, client):
        """空库 → 200, items=[], total=0。"""
        r = client.get("/api/v1/operate/tenant-brands")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["items"] == []
        assert d["total"] == 0

    def test_list_pagination(self, client):
        for i in range(3):
            t = _seed_tenant(client._sesh, code=f"TBRPG{i}")
            _seed_brand(client._sesh, tenant_id=t.id, operator_name=f"运营{i}")
        r = client.get("/api/v1/operate/tenant-brands?page=1&page_size=2")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2
        assert d["page"] == 1
        assert d["page_size"] == 2

    def test_list_invalid_pagination_422(self, client):
        """page<1 / page_size<1 → 422。"""
        assert client.get("/api/v1/operate/tenant-brands?page=0").status_code == 422
        assert client.get("/api/v1/operate/tenant-brands?page_size=0").status_code == 422

    def test_list_ordered_by_id_desc(self, client):
        """列表按 id 倒序 (最新优先)。"""
        t1 = _seed_tenant(client._sesh, code="TBRORD1")
        _seed_brand(client._sesh, tenant_id=t1.id, operator_name="旧")
        t2 = _seed_tenant(client._sesh, code="TBRORD2")
        _seed_brand(client._sesh, tenant_id=t2.id, operator_name="新")
        r = client.get("/api/v1/operate/tenant-brands")
        names = [i["operator_name"] for i in r.json()["data"]["items"]]
        assert names == ["新", "旧"]

    def test_get_detail_ok(self, client):
        t = _seed_tenant(client._sesh)
        _seed_brand(client._sesh, tenant_id=t.id, operator_name="详情商")
        r = client.get(f"/api/v1/operate/tenant-brands/{t.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["tenant_id"] == t.id
        assert d["operator_name"] == "详情商"

    def test_get_detail_not_found_404(self, client):
        r = client.get("/api/v1/operate/tenant-brands/999999")
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]

    def test_get_detail_isoformat_timestamps(self, client):
        """created_at / updated_at 序列化为 isoformat (可 fromisoformat 还原)。"""
        t = _seed_tenant(client._sesh)
        _seed_brand(client._sesh, tenant_id=t.id)
        r = client.get(f"/api/v1/operate/tenant-brands/{t.id}")
        d = r.json()["data"]
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)
        assert datetime.fromisoformat(d["created_at"]) is not None

    def test_delete_ok(self, client):
        t = _seed_tenant(client._sesh)
        _seed_brand(client._sesh, tenant_id=t.id)
        r = client.delete(f"/api/v1/operate/tenant-brands/{t.id}")
        assert r.status_code == 200
        # 删除后查不到
        assert client.get(f"/api/v1/operate/tenant-brands/{t.id}").status_code == 404

    def test_delete_not_found_404(self, client):
        assert client.delete("/api/v1/operate/tenant-brands/999999").status_code == 404


# ==================== 鉴权: router 级 operate:manage ====================

class TestTenantBrandPermissionGate:
    """router 级 require_permission('operate:manage') 覆盖全部端点 (含 GET);
    viewer 无该权限 → 403; admin 通过 (team scoping 见下)。"""

    @pytest.fixture
    def viewer_token(self, client):
        _add_user(client._sesh, "brand_viewer", UserRole.VIEWER)
        return _login_token(client, "brand_viewer")

    def test_viewer_upsert_forbidden(self, client, viewer_token):
        t = _seed_tenant(client._sesh)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(t.id), headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_list_forbidden(self, client, viewer_token):
        r = client.get("/api/v1/operate/tenant-brands", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_detail_forbidden(self, client, viewer_token):
        r = client.get("/api/v1/operate/tenant-brands/1", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_delete_forbidden(self, client, viewer_token):
        r = client.delete("/api/v1/operate/tenant-brands/1", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_anonymous_unauthorized(self, anon_client):
        """无 token → 全局 enforce_auth 拦 401。"""
        r = anon_client.get("/api/v1/operate/tenant-brands")
        assert r.status_code == 401


# ==================== team scoping 矩阵 ====================

class TestTenantBrandTeamScoping:
    """team_id 服务端隔离矩阵:

      ① 列表经 team_scope 过滤, 跨 team 记录不出现; admin 全见
      ② 创建时 team_id 服务端强制 = 用户 team_id (admin → 0)
      ③ 更新·详情·删除跨 team → 404 (不泄露存在); admin 豁免; 同 team 放行
    """

    @pytest.fixture
    def two_teams(self, client):
        s = client._sesh
        ta = Team(name="品牌团队A", code="BRDSCTA")
        tb = Team(name="品牌团队B", code="BRDSCTB")
        s.add_all([ta, tb])
        s.commit()
        s.refresh(ta)
        s.refresh(tb)

        t1 = Tenant(name="租户A", code="BRDSCTNA")
        t2 = Tenant(name="租户B", code="BRDSCTNB")
        s.add_all([t1, t2])
        s.commit()
        s.refresh(t1)
        s.refresh(t2)

        _add_user(s, "brand_eng_a", UserRole.ENGINEER, team_id=ta.id)
        _add_user(s, "brand_eng_b", UserRole.ENGINEER, team_id=tb.id)
        return {
            "ta": ta, "tb": tb, "t1": t1, "t2": t2,
            "eng_a_token": _login_token(client, "brand_eng_a"),
            "eng_b_token": _login_token(client, "brand_eng_b"),
        }

    # ── 列表隔离 (team_scope) ──

    def test_list_team_user_sees_only_own_team(self, client, two_teams):
        _seed_brand(client._sesh, tenant_id=two_teams["t1"].id,
                    team_id=two_teams["ta"].id, operator_name="A商")
        _seed_brand(client._sesh, tenant_id=two_teams["t2"].id,
                    team_id=two_teams["tb"].id, operator_name="B商")
        r = client.get("/api/v1/operate/tenant-brands",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200
        names = {i["operator_name"] for i in r.json()["data"]["items"]}
        assert names == {"A商"}  # 仅本 team

    def test_list_admin_sees_all_teams(self, client, two_teams):
        _seed_brand(client._sesh, tenant_id=two_teams["t1"].id,
                    team_id=two_teams["ta"].id, operator_name="A商")
        _seed_brand(client._sesh, tenant_id=two_teams["t2"].id,
                    team_id=two_teams["tb"].id, operator_name="B商")
        r = client.get("/api/v1/operate/tenant-brands")  # admin 默认头
        assert r.status_code == 200
        names = {i["operator_name"] for i in r.json()["data"]["items"]}
        assert {"A商", "B商"} <= names

    # ── 创建: team_id 服务端强制 ──

    def test_upsert_create_assigns_user_team(self, client, two_teams):
        """team 级用户创建品牌 → team_id = 用户 team_id (服务端强制, 不可伪造)。"""
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(two_teams["t1"].id),
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == two_teams["ta"].id

    # ── 单资源 / 更新: assert_team_access ──

    def test_upsert_update_cross_team_404(self, client, two_teams):
        """他 team 已建的品牌, eng_a 再 upsert (更新分支) → assert_team_access 404。"""
        _seed_brand(client._sesh, tenant_id=two_teams["t2"].id,
                    team_id=two_teams["tb"].id)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(two_teams["t2"].id, operator_name="劫持"),
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_upsert_update_same_team_ok(self, client, two_teams):
        """同 team 品牌更新 → 200 (更新分支放行)。"""
        _seed_brand(client._sesh, tenant_id=two_teams["t1"].id,
                    team_id=two_teams["ta"].id)
        r = client.post("/api/v1/operate/tenant-brands",
                        json=_payload(two_teams["t1"].id, operator_name="改名"),
                        headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200
        assert r.json()["data"]["operator_name"] == "改名"

    def test_get_detail_cross_team_404(self, client, two_teams):
        _seed_brand(client._sesh, tenant_id=two_teams["t2"].id,
                    team_id=two_teams["tb"].id)
        r = client.get(f"/api/v1/operate/tenant-brands/{two_teams['t2'].id}",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404

    def test_get_detail_same_team_ok(self, client, two_teams):
        _seed_brand(client._sesh, tenant_id=two_teams["t1"].id,
                    team_id=two_teams["ta"].id)
        r = client.get(f"/api/v1/operate/tenant-brands/{two_teams['t1'].id}",
                       headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 200

    def test_get_detail_admin_exempt_cross_team(self, client, two_teams):
        """admin 平台级豁免: 跨 team 详情仍可见。"""
        _seed_brand(client._sesh, tenant_id=two_teams["t2"].id,
                    team_id=two_teams["tb"].id)
        r = client.get(f"/api/v1/operate/tenant-brands/{two_teams['t2'].id}")  # admin
        assert r.status_code == 200

    def test_delete_cross_team_404(self, client, two_teams):
        _seed_brand(client._sesh, tenant_id=two_teams["t2"].id,
                    team_id=two_teams["tb"].id)
        r = client.delete(f"/api/v1/operate/tenant-brands/{two_teams['t2'].id}",
                          headers=_auth(two_teams["eng_a_token"]))
        assert r.status_code == 404


# ==================== 异常保护: handler try/except 兜底 500 ====================

class TestTenantBrandExceptionSafety:
    """handler 体内 try/except 兜底: 内部异常 → HTTPException(500), 不外抛 traceback。

    注入: monkeypatch 模块内 response 包装函数抛 SQLAlchemyError。该调用位于 handler
    return 处 (在 try 块内), 用以模拟 DB 写入/响应构建阶段异常。未加 try/except 时,
    TestClient 会把异常外抛 (test error); 加后转为 500 响应 (test green) —— 绿即证明
    兜底生效。500 detail 含 '租户品牌' 以区别默认 'Internal Server Error'。
    """

    def test_upsert_exception_500(self, client, monkeypatch):
        t = _seed_tenant(client._sesh)
        monkeypatch.setattr(f"{MODULE}.success_response", _boom)
        r = client.post("/api/v1/operate/tenant-brands", json=_payload(t.id))
        assert r.status_code == 500
        assert "租户品牌" in r.json()["detail"]

    def test_list_exception_500(self, client, monkeypatch):
        monkeypatch.setattr(f"{MODULE}.paginated_response", _boom)
        r = client.get("/api/v1/operate/tenant-brands")
        assert r.status_code == 500
        assert "租户品牌" in r.json()["detail"]

    def test_get_detail_exception_500(self, client, monkeypatch):
        t = _seed_tenant(client._sesh)
        _seed_brand(client._sesh, tenant_id=t.id)
        monkeypatch.setattr(f"{MODULE}.success_response", _boom)
        r = client.get(f"/api/v1/operate/tenant-brands/{t.id}")
        assert r.status_code == 500
        assert "租户品牌" in r.json()["detail"]

    def test_delete_exception_500(self, client, monkeypatch):
        t = _seed_tenant(client._sesh)
        _seed_brand(client._sesh, tenant_id=t.id)
        monkeypatch.setattr(f"{MODULE}.action_response", _boom)
        r = client.delete(f"/api/v1/operate/tenant-brands/{t.id}")
        assert r.status_code == 500
        assert "租户品牌" in r.json()["detail"]
