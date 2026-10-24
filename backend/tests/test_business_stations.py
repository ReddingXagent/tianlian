"""工作卡 5300ccc2 — 云端配套② C端场站入口 (契约 §1)

契约: backend/docs/contracts/user-client-contract.md §1 (场站响应 + branding)

覆盖:
- GET /business/stations: 列表 + 轻量 branding + 附近(lat/lon/radius)过滤排序 +
  keyword/city 过滤 + 分页 + Cache-Control + 不按 team 隔离(跨运营商浏览)
- GET /business/stations/{id}: 详情 + 全量 branding + 默认品牌降级(source=default) + 不存在 404
- 鉴权: C端只读(get_current_user, 无 station:edit 依赖) / 匿名 → 401

与管理侧 /stations 隔离: 本端点不挂 require_write_permission("station:edit"),
普通 operator/viewer 可读; 且不按 caller team 过滤(C端用户跨运营商浏览全部公开场站)。
"""
import bcrypt
import math
import pytest

from app.api.v1.business import _haversine_km
from app.models.station import Station, StationStatus
from app.models.tenant import Tenant
from app.models.tenant_brand import TenantBrand
from app.models.user import Team, User, UserRole


# ─── 测试脚手架 ───

def _seed_tenant(sesh, name="t_brand_a", code="TBRA"):
    t = Tenant(name=name, code=code)
    sesh.add(t)
    sesh.commit()
    sesh.refresh(t)
    return t


def _seed_brand(sesh, tenant_id, *, operator_name="某某新能源",
                theme_color="#00A86B", logo_url="https://cdn.tianlian.example/logo.png",
                service_phone="400-888-0001"):
    b = TenantBrand(
        tenant_id=tenant_id, operator_name=operator_name,
        theme_color=theme_color, logo_url=logo_url, service_phone=service_phone,
    )
    sesh.add(b)
    sesh.commit()
    sesh.refresh(b)
    return b


def _seed_station(sesh, *, name, code, tenant_id=None, team_id=None,
                  lat=None, lon=None, city=None, address=None,
                  status=StationStatus.NORMAL):
    st = Station(
        name=name, code=code, tenant_id=tenant_id, team_id=team_id,
        lat=lat, lon=lon, city=city, address=address, status=status,
    )
    sesh.add(st)
    sesh.commit()
    sesh.refresh(st)
    return st


def _seed_operator(sesh, username, team, pwd="op123456"):
    u = User(
        username=username, real_name=username, role=UserRole.OPERATOR,
        team_id=team.id, status="active",
        password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
    )
    sesh.add(u)
    sesh.commit()
    return pwd


def _login(client, username, pwd):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": pwd})
    assert r.status_code == 200, f"登录失败 {username}: {r.text}"
    return r.json()["data"]["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ─── 列表 GET /business/stations ───

class TestBusinessStationList:
    def test_list_lightweight_branding_and_default_degrade(self, client):
        """有租户品牌 → source=tenant 轻量(仅 operator_name/theme_color);
        无租户 → source=default 降级。"""
        s = client._sesh
        tenant = _seed_tenant(s)
        _seed_brand(s, tenant.id)
        _seed_station(s, name="品牌站", code="BIZ001", tenant_id=tenant.id,
                      city="北京", address="朝阳区A路")
        _seed_station(s, name="裸站", code="BIZ002", city="上海", address="浦东B路")

        r = client.get("/api/v1/business/stations")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        items = body["data"]["items"]
        by_name = {it["name"]: it for it in items}

        # 轻量 branding: 仅 operator_name/theme_color + source, 不含 logo_url/service_phone
        biz = by_name["品牌站"]["branding"]
        assert biz["source"] == "tenant"
        assert biz["operator_name"] == "某某新能源"
        assert biz["theme_color"] == "#00A86B"
        assert "logo_url" not in biz
        assert "service_phone" not in biz

        # 默认降级
        naked = by_name["裸站"]["branding"]
        assert naked["source"] == "default"
        assert naked["operator_name"]  # 非空(天链默认品牌)

    def test_list_envelope_code0_and_cache_control(self, client):
        _seed_station(client._sesh, name="缓存站", code="BIZC01")
        r = client.get("/api/v1/business/stations")
        assert r.status_code == 200
        assert r.json()["code"] == 0
        # 契约 §1: Cache-Control: public, max-age=300
        assert r.headers.get("Cache-Control") == "public, max-age=300"

    def test_list_no_team_scoping(self, client):
        """C端用户跨 team 看到全部公开场站(异于管理侧 /stations 的 team 隔离)。"""
        s = client._sesh
        t1 = Team(name="C端T1", code="CBI1")
        t2 = Team(name="C端T2", code="CBI2")
        s.add_all([t1, t2])
        s.commit()
        s.refresh(t1)
        s.refresh(t2)
        _seed_station(s, name="T1站", code="BIZT1", team_id=t1.id)
        _seed_station(s, name="T2站", code="BIZT2", team_id=t2.id)
        _seed_operator(s, "cbiz_op", t1)
        token = _login(client, "cbiz_op", "op123456")  # operator 归属 T1

        r = client.get("/api/v1/business/stations", headers=_h(token))
        assert r.status_code == 200
        names = {it["name"] for it in r.json()["data"]["items"]}
        # T1 operator 也能看到 T2 的站 —— 证明无 team 隔离
        assert {"T1站", "T2站"}.issubset(names)

    def test_list_nearby_filter_and_sort(self, client):
        """lat/lon/radius 过滤附近 + 按距离升序 + 携带 distance_km。"""
        s = client._sesh
        near = _seed_station(s, name="近站", code="BIZN1", lat=30.001, lon=120.0)
        mid = _seed_station(s, name="中站", code="BIZN2", lat=30.01, lon=120.0)
        _seed_station(s, name="远站", code="BIZN3", lat=31.0, lon=121.0)  # ~130km
        _seed_station(s, name="无坐标站", code="BIZN4")  # nearby 模式应排除

        r = client.get("/api/v1/business/stations",
                       params={"lat": 30.0, "lon": 120.0, "radius": 5.0})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        names = [it["name"] for it in items]
        assert names == ["近站", "中站"]  # 远站>5km 排除, 无坐标站排除
        assert items[0]["distance_km"] < items[1]["distance_km"]
        assert all(it["distance_km"] < 5.0 for it in items)

    def test_list_keyword_and_city_filter(self, client):
        s = client._sesh
        _seed_station(s, name="朝阳站", code="BIZK1", city="北京", address="朝阳区")
        _seed_station(s, name="浦东站", code="BIZK2", city="上海", address="浦东新区")

        # keyword
        r = client.get("/api/v1/business/stations", params={"keyword": "朝阳"})
        names = {it["name"] for it in r.json()["data"]["items"]}
        assert names == {"朝阳站"}

        # city
        r = client.get("/api/v1/business/stations", params={"city": "上海"})
        names = {it["name"] for it in r.json()["data"]["items"]}
        assert names == {"浦东站"}

    def test_list_pagination(self, client):
        s = client._sesh
        for i in range(5):
            _seed_station(s, name=f"分页站{i}", code=f"BIZP{i}")
        r = client.get("/api/v1/business/stations", params={"page": 1, "page_size": 2})
        body = r.json()["data"]
        assert body["total"] >= 5
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_list_anonymous_401(self, anon_client):
        r = anon_client.get("/api/v1/business/stations")
        assert r.status_code == 401


# ─── 详情 GET /business/stations/{station_id} ───

class TestBusinessStationDetail:
    def test_detail_full_branding(self, client):
        """详情返回全量 branding(含 logo_url/service_phone)。"""
        s = client._sesh
        tenant = _seed_tenant(s, name="t_brand_d", code="TBRD")
        _seed_brand(s, tenant.id)
        st = _seed_station(s, name="详情站", code="BIZD1", tenant_id=tenant.id)

        r = client.get(f"/api/v1/business/stations/{st.id}")
        assert r.status_code == 200
        assert r.headers.get("Cache-Control") == "public, max-age=300"
        data = r.json()["data"]
        assert data["id"] == st.id
        assert data["tenant_id"] == tenant.id  # 契约 §1.1 示例字段
        branding = data["branding"]
        assert branding["source"] == "tenant"
        assert branding["logo_url"] == "https://cdn.tianlian.example/logo.png"
        assert branding["service_phone"] == "400-888-0001"
        assert branding["operator_name"] == "某某新能源"
        assert branding["theme_color"] == "#00A86B"

    def test_detail_default_brand_when_no_tenant(self, client):
        st = _seed_station(client._sesh, name="裸详情站", code="BIZD2")
        r = client.get(f"/api/v1/business/stations/{st.id}")
        assert r.status_code == 200
        branding = r.json()["data"]["branding"]
        assert branding["source"] == "default"
        # 全量字段均在(非 null), 端侧无需判空
        for k in ("operator_name", "logo_url", "service_phone", "theme_color"):
            assert k in branding

    def test_detail_not_found_biz_error(self, client):
        """场站不存在 → HTTP 200 + code!=0 STATION_NOT_FOUND (卡 418a675a)。"""
        r = client.get("/api/v1/business/stations/9999999")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "STATION_NOT_FOUND"
        assert body["data"] is None

    def test_detail_anonymous_401(self, anon_client):
        r = anon_client.get("/api/v1/business/stations/1")
        assert r.status_code == 401


# ─── _haversine_km 浮点 clamp (卡 bf8d01aa) ───

class TestHaversineClamp:
    def test_haversine_same_point(self):
        """同点距离 = 0。"""
        assert _haversine_km(30.0, 120.0, 30.0, 120.0) == 0.0

    def test_haversine_extreme_coords(self):
        """极端坐标(近对跖点/极地): a 的浮点 round-off 可能使 a 略超 1.0,
        clamp 到 [0,1] 后 asin 不抛 ValueError —— 与 dispatch_engine 同公式对齐。"""
        # 对跖点对: lat2=-lat1, lon2=lon1±180 是 round-off 溢出高发输入
        pairs = [
            (89.99, 0.0, -89.99, 180.0),        # 近极地 + 经度差 180
            (13.878376545252522, -37.195029125719145,
             -13.878376545252522, 142.80497087428085),  # 实测 a=1+2ULP 的对跖点
            (90.0, 0.0, -90.0, 180.0),          # 正极 ↔ 反极
            (45.0, -180.0, -45.0, 0.0),         # 中纬对跖
        ]
        for lat1, lon1, lat2, lon2 in pairs:
            d = _haversine_km(lat1, lon1, lat2, lon2)
            # 对跖点球面距离 ≈ 半个地球周长 (π·R ≈ 20015km), 必有限非 NaN
            assert math.isfinite(d)
            assert 0.0 <= d <= 20016.0

    def test_haversine_non_negative(self):
        """距离恒非负, clamp 下界保证。"""
        assert _haversine_km(0.0, 0.0, 0.0, 90.0) > 0.0


# ─── nearby 异常防护: _haversine_km 抛错时跳过该站不 500 (卡 bf8d01aa) ───

class TestNearbyDistanceErrorHandling:
    def test_nearby_skips_station_on_distance_error(self, client, monkeypatch):
        """_haversine_km 对某站抛异常 → log.warning + 跳过该站, 整体接口仍 200。
        模拟方式: 让 _haversine_km 对带坐标的站抛 ValueError。"""
        import app.api.v1.business as biz

        s = client._sesh
        _seed_station(s, name="坏坐标站", code="BIZHE1", lat=13.878, lon=-37.195)
        _seed_station(s, name="正常站", code="BIZHE2", lat=30.001, lon=120.0)

        real = biz._haversine_km
        calls = {"n": 0}

        def boom(lat1, lon1, lat2, lon2):
            calls["n"] += 1
            # 第二个被调用(坏坐标站, 按查询顺序)的算距离时抛错
            if abs(lat2 - 13.878) < 0.01:
                raise ValueError("asin domain error")
            return real(lat1, lon1, lat2, lon2)

        monkeypatch.setattr(biz, "_haversine_km", boom)

        r = client.get("/api/v1/business/stations",
                       params={"lat": 30.0, "lon": 120.0, "radius": 1000.0})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        names = {it["name"] for it in body["data"]["items"]}
        assert "正常站" in names
        assert "坏坐标站" not in names  # 抛错站被跳过, 不 500
        assert calls["n"] >= 1
