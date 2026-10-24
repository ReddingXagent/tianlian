"""
工作卡 28546b66 — 云端配套① 租户品牌服务 (契约驱动)
契约: backend/docs/contracts/user-client-contract.md §1 (场站响应 + branding)

覆盖:
- GET /stations/{id} branding: source=tenant (租户已配置) / source=default (降级)
- 所有 branding 字段不为 null (端侧无需判空)
- Cache-Control: public, max-age=300 (详情 + 列表)
- GET /stations 列表携带轻量版 branding (operator_name + theme_color + source，无 logo_url)
- ops 品牌 CRUD (upsert / 查询 / 删除): happy path + hex/url 校验 + 404
- team 隔离: 跨团队读写 → 404；admin 平台级全可见
- 权限拒绝: VIEWER (无 operate:manage) → 403
"""
import bcrypt
import pytest


CACHE_HEADER = "public, max-age=300"


# ─── 测试脚手架 ───

def _seed_tenant(client, code="TLT001", name="某某新能源"):
    from app.models.tenant import Tenant
    s = client._sesh
    t = Tenant(name=name, code=code, status="active", is_active=True)
    s.add(t)
    s.commit()
    s.refresh(t)
    return t


def _seed_station(client, *, tenant_id=None, team_id=None, code, name):
    from app.models.station import Station, StationStatus
    s = client._sesh
    st = Station(name=name, code=code, status=StationStatus.NORMAL,
                 tenant_id=tenant_id, team_id=team_id)
    s.add(st)
    s.commit()
    s.refresh(st)
    return st


def _seed_brand(client, tenant_id, *, team_id=None, operator_name="某某新能源",
                logo_url="https://cdn.tianlian.example/brands/t_001/logo.png",
                service_phone="400-888-0001", theme_color="#00A86B"):
    from app.models.tenant_brand import TenantBrand
    s = client._sesh
    b = TenantBrand(tenant_id=tenant_id, team_id=team_id, operator_name=operator_name,
                    logo_url=logo_url, service_phone=service_phone, theme_color=theme_color)
    s.add(b)
    s.commit()
    s.refresh(b)
    return b


@pytest.fixture
def brand_team_pair(client):
    """两团队 + 两团队级 OPERATOR 用户(具 operate:manage) + token，用于品牌 CRUD team 隔离测试。"""
    from app.models.user import User, UserRole, Team
    s = client._sesh
    ta = Team(name="品牌团队A", code="BRDTA")
    tb = Team(name="品牌团队B", code="BRDTB")
    s.add_all([ta, tb])
    s.commit()
    s.refresh(ta)
    s.refresh(tb)

    pwd = "brand123456"
    ua = User(
        username="brand_op_a", real_name="A运营", role=UserRole.OPERATOR,
        team_id=ta.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    ub = User(
        username="brand_op_b", real_name="B运营", role=UserRole.OPERATOR,
        team_id=tb.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    s.add_all([ua, ub])
    s.commit()

    def _tok(username):
        r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return {
        "teams": {"a": ta, "b": tb},
        "tokens": {"a": _tok("brand_op_a"), "b": _tok("brand_op_b")},
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _viewer_token(client):
    """VIEWER 用户 (无 operate:manage) 的 token，用于权限拒绝测试。"""
    from app.models.user import User, UserRole
    s = client._sesh
    if not s.query(User).filter(User.username == "brand_viewer").first():
        s.add(User(
            username="brand_viewer", real_name="只读", role=UserRole.VIEWER,
            status="active",
            password_hash=bcrypt.hashpw(b"view123456", bcrypt.gensalt()).decode(),
        ))
        s.commit()
    r = client.post("/api/v1/auth/login", data={"username": "brand_viewer", "password": "view123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


# ─── 场站响应 branding (契约 §1) ───

class TestStationBranding:
    """GET /stations/{id} 与 GET /stations 的 branding 注入"""

    def test_branding_source_tenant(self, client):
        """租户已配置品牌 → source=tenant，字段取自 TenantBrand。"""
        t = _seed_tenant(client)
        st = _seed_station(client, tenant_id=t.id, code="BR_STA_001", name="BRANDTEST_TENANT")
        _seed_brand(client, t.id, operator_name="某某新能源",
                    logo_url="https://cdn.tianlian.example/logo.png",
                    service_phone="400-888-0001", theme_color="#00A86B")

        resp = client.get(f"/api/v1/stations/{st.id}")
        assert resp.status_code == 200
        branding = resp.json()["data"]["branding"]
        assert branding["source"] == "tenant"
        assert branding["operator_name"] == "某某新能源"
        assert branding["logo_url"] == "https://cdn.tianlian.example/logo.png"
        assert branding["service_phone"] == "400-888-0001"
        assert branding["theme_color"] == "#00A86B"

    def test_branding_source_default_when_unconfigured(self, client):
        """租户未配置品牌 → source=default，所有字段非 null (端侧无需判空)。"""
        # station 无 tenant_id
        st = _seed_station(client, tenant_id=None, code="BR_STA_002", name="BRANDTEST_DEFAULT")
        resp = client.get(f"/api/v1/stations/{st.id}")
        assert resp.status_code == 200
        branding = resp.json()["data"]["branding"]
        assert branding["source"] == "default"
        for k in ("operator_name", "logo_url", "service_phone", "theme_color"):
            assert branding[k] is not None, f"{k} 不得为 null"
        assert branding["operator_name"] == "天链"
        assert branding["theme_color"].startswith("#")

    def test_branding_source_default_when_tenant_has_no_brand(self, client):
        """tenant 存在但未配品牌 → 仍降级 default。"""
        t = _seed_tenant(client, code="TLT002")
        st = _seed_station(client, tenant_id=t.id, code="BR_STA_003", name="BRANDTEST_TENANT_NOBRAND")
        resp = client.get(f"/api/v1/stations/{st.id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["branding"]["source"] == "default"

    def test_detail_cache_control_header(self, client):
        """详情响应带 Cache-Control: public, max-age=300。"""
        st = _seed_station(client, tenant_id=None, code="BR_STA_004", name="BRANDTEST_CACHE_DETAIL")
        resp = client.get(f"/api/v1/stations/{st.id}")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == CACHE_HEADER

    def test_list_carries_lightweight_branding_and_cache(self, client):
        """列表携带轻量版 branding (operator_name + theme_color + source，无 logo_url) + Cache-Control。"""
        t = _seed_tenant(client, code="TLT003")
        _seed_station(client, tenant_id=t.id, code="BR_STA_010", name="BRANDTEST_LIST_A")
        _seed_station(client, tenant_id=t.id, code="BR_STA_011", name="BRANDTEST_LIST_A2")
        _seed_brand(client, t.id, operator_name="某某新能源", theme_color="#00A86B",
                    logo_url="https://cdn.tianlian.example/logo.png",
                    service_phone="400-888-0001")
        _seed_station(client, tenant_id=None, code="BR_STA_012", name="BRANDTEST_LIST_B")

        resp = client.get("/api/v1/stations?keyword=BRANDTEST_LIST")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == CACHE_HEADER
        items = resp.json()["data"]["items"]
        assert len(items) >= 3
        by_code = {it["code"]: it for it in items}

        # 已配置租户的站点 → 轻量版 (source=tenant)
        a = by_code["BR_STA_010"]
        assert a["branding"]["source"] == "tenant"
        assert a["branding"]["operator_name"] == "某某新能源"
        assert a["branding"]["theme_color"] == "#00A86B"
        # 轻量版: 不含 logo_url / service_phone
        assert "logo_url" not in a["branding"]
        assert "service_phone" not in a["branding"]

        # 未配置站点 → default 轻量版
        b = by_code["BR_STA_012"]
        assert b["branding"]["source"] == "default"
        assert "logo_url" not in b["branding"]


# ─── ops 品牌 CRUD (团队级) ───

class TestOpsTenantBrandCRUD:
    """运营平台 - 租户品牌 CRUD"""

    def _payload(self, tenant_id, **over):
        p = {
            "tenant_id": tenant_id,
            "operator_name": "某某新能源",
            "logo_url": "https://cdn.tianlian.example/logo.png",
            "service_phone": "400-888-0001",
            "theme_color": "#00A86B",
        }
        p.update(over)
        return p

    def test_upsert_create_then_update(self, client):
        t = _seed_tenant(client, code="TLT_CRUD_01")
        # create
        r = client.post("/api/v1/operate/tenant-brands", json=self._payload(t.id))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["tenant_id"] == t.id
        assert data["operator_name"] == "某某新能源"
        assert data["theme_color"] == "#00A86B"
        # update (same tenant_id → upsert)
        r2 = client.post("/api/v1/operate/tenant-brands",
                         json=self._payload(t.id, operator_name="新名称", theme_color="#123456"))
        assert r2.status_code == 200
        data2 = r2.json()["data"]
        assert data2["operator_name"] == "新名称"
        assert data2["theme_color"] == "#123456"
        assert data2["id"] == data["id"]  # 同一条记录

    def test_get_and_list(self, client):
        t1 = _seed_tenant(client, code="TLT_CRUD_02")
        t2 = _seed_tenant(client, code="TLT_CRUD_03", name="另一租户")
        client.post("/api/v1/operate/tenant-brands", json=self._payload(t1.id))
        client.post("/api/v1/operate/tenant-brands",
                    json=self._payload(t2.id, operator_name="另一运营商"))

        # detail
        r = client.get(f"/api/v1/operate/tenant-brands/{t1.id}")
        assert r.status_code == 200
        assert r.json()["data"]["operator_name"] == "某某新能源"

        # list
        r = client.get("/api/v1/operate/tenant-brands")
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 2

    def test_delete(self, client):
        t = _seed_tenant(client, code="TLT_CRUD_04")
        client.post("/api/v1/operate/tenant-brands", json=self._payload(t.id))
        assert client.delete(f"/api/v1/operate/tenant-brands/{t.id}").status_code == 200
        assert client.get(f"/api/v1/operate/tenant-brands/{t.id}").status_code == 404

    def test_get_404(self, client):
        assert client.get("/api/v1/operate/tenant-brands/99999").status_code == 404

    def test_upsert_tenant_not_found(self, client):
        """品牌必须挂在已存在的租户上 → 404。"""
        r = client.post("/api/v1/operate/tenant-brands", json=self._payload(99999))
        assert r.status_code == 404

    def test_invalid_theme_color(self, client):
        t = _seed_tenant(client, code="TLT_CRUD_05")
        for bad in ("red", "00A86B", "#GGGGGG", "#1234567"):
            r = client.post("/api/v1/operate/tenant-brands",
                            json=self._payload(t.id, theme_color=bad))
            assert r.status_code == 400, f"应拒绝非法 theme_color={bad}: {r.text}"

    def test_invalid_logo_url(self, client):
        t = _seed_tenant(client, code="TLT_CRUD_06")
        for bad in ("not-a-url", "/brands/logo.png", "ftp://x/y", "http://"):
            r = client.post("/api/v1/operate/tenant-brands",
                            json=self._payload(t.id, logo_url=bad))
            assert r.status_code == 400, f"应拒绝非法 logo_url={bad}: {r.text}"

    def test_valid_3digit_hex_and_uppercase(self, client):
        t = _seed_tenant(client, code="TLT_CRUD_07")
        for good in ("#abc", "#ABCDEF", "#00A86B"):
            r = client.post("/api/v1/operate/tenant-brands",
                            json=self._payload(t.id, theme_color=good))
            assert r.status_code == 200, f"应接受合法 theme_color={good}: {r.text}"


class TestOpsTenantBrandTeamIsolation:
    """运营平台 - 租户品牌 team 隔离 + 权限"""

    def test_team_isolation_and_cross_team_404(self, client, brand_team_pair):
        ta = brand_team_pair["teams"]["a"]
        t = _seed_tenant(client, code="TLT_ISO_01")
        # A 创建品牌 (归属 team A)
        r = client.post(
            "/api/v1/operate/tenant-brands",
            json={
                "tenant_id": t.id, "operator_name": "A品牌",
                "logo_url": "https://cdn.tianlian.example/a.png",
                "service_phone": "400-000-0001", "theme_color": "#00A86B",
            },
            headers=_h(brand_team_pair["tokens"]["a"]),
        )
        assert r.status_code == 200
        assert r.json()["data"]["team_id"] == ta.id

        # A 自己可读
        r = client.get(f"/api/v1/operate/tenant-brands/{t.id}",
                       headers=_h(brand_team_pair["tokens"]["a"]))
        assert r.status_code == 200

        # B 跨团队读 → 404 (不泄露存在)
        r = client.get(f"/api/v1/operate/tenant-brands/{t.id}",
                       headers=_h(brand_team_pair["tokens"]["b"]))
        assert r.status_code == 404

        # B 跨团队删 → 404
        r = client.delete(f"/api/v1/operate/tenant-brands/{t.id}",
                          headers=_h(brand_team_pair["tokens"]["b"]))
        assert r.status_code == 404

        # B 列表只看到本 team (空)
        r = client.get("/api/v1/operate/tenant-brands",
                       headers=_h(brand_team_pair["tokens"]["b"]))
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_admin_sees_all(self, client, brand_team_pair):
        t = _seed_tenant(client, code="TLT_ISO_02")
        client.post(
            "/api/v1/operate/tenant-brands",
            json={"tenant_id": t.id, "operator_name": "A品牌",
                  "logo_url": "https://cdn.tianlian.example/a.png",
                  "service_phone": "400-000-0001", "theme_color": "#00A86B"},
            headers=_h(brand_team_pair["tokens"]["a"]),
        )
        # admin (默认 client) 平台级可见
        r = client.get(f"/api/v1/operate/tenant-brands/{t.id}")
        assert r.status_code == 200
        assert r.json()["data"]["operator_name"] == "A品牌"

    def test_viewer_forbidden(self, client):
        """VIEWER 无 operate:manage → 403。"""
        t = _seed_tenant(client, code="TLT_PERM_01")
        tok = _viewer_token(client)
        r = client.post(
            "/api/v1/operate/tenant-brands",
            json={"tenant_id": t.id, "operator_name": "X",
                  "logo_url": "https://cdn.tianlian.example/x.png",
                  "service_phone": "400-000-0000", "theme_color": "#00A86B"},
            headers=_h(tok),
        )
        assert r.status_code == 403
