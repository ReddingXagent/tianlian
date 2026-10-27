"""服务费定价 CRUD API 测试 (工作卡 be1f5eb4)

覆盖 app/api/v1/pricing_management/service_fee.py (挂 /api/v1 前缀, 无额外 prefix):
- GET  /pricing/mgmt/service-fee            列表 (station_id / is_active 过滤 + 分页)
- GET  /pricing/mgmt/service-fee/{id}       详情 (不存在 → 404)
- POST /pricing/mgmt/service-fee            创建 (无效 user_type/fee_type → 400; 同 station+user_type
                                                生效期重叠且 is_active → 409, 卡 a311a5b0 缺陷1)
- PUT  /pricing/mgmt/service-fee/{id}       更新 (重叠校验排除自身; 无效枚举 → 400; 不存在 → 404)
- DELETE /pricing/mgmt/service-fee/{id}     删除

权限门: router-level require_role("admin") —— admin 恒通过, operator/viewer → 403, 匿名 → 401。
"""
import uuid

import bcrypt
import pytest

from app.models.pricing_v2 import ServiceFeePrice, UserType, FeeType
from app.models.station import Station
from app.models.user import User, UserRole

URL = "/api/v1/pricing/mgmt/service-fee"


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
    r = client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, suffix=None):
    sx = suffix or uuid.uuid4().hex[:6]
    st = Station(name=f"服务费站{sx}", code=f"SFS{sx}")
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_fee(
    session, *, station_id, user_type=UserType.APP, fee_type=FeeType.FIXED,
    fee_value="1.5000", effective="2026-01-01", expire=None, is_active=True,
):
    """直接落一条 ServiceFeePrice (绕过 API, 模拟任意生效期/状态)。"""
    from datetime import date
    from decimal import Decimal
    o = ServiceFeePrice(
        station_id=station_id,
        user_type=user_type,
        fee_type=fee_type,
        fee_value=Decimal(str(fee_value)),
        effective_date=date.fromisoformat(effective),
        expire_date=date.fromisoformat(expire) if expire else None,
        is_active=is_active,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _payload(station_id, **overrides):
    p = {
        "station_id": station_id,
        "user_type": "app",
        "fee_type": "fixed",
        "fee_value": 1.5,
        "effective_date": "2026-01-01",
        "expire_date": None,
        "is_active": True,
    }
    p.update(overrides)
    return p


# ═══════════════════════════════════════════════════════════════
# 1. 列表 (过滤 + 分页)
# ═══════════════════════════════════════════════════════════════

class TestList:
    def test_list_empty(self, client):
        r = client.get(URL)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["items"] == []

    def test_list_filter_by_station(self, client):
        s = client._sesh
        st_a = _seed_station(s, "AA")
        st_b = _seed_station(s, "BB")
        _seed_fee(s, station_id=st_a.id)
        _seed_fee(s, station_id=st_b.id)
        r = client.get(URL, params={"station_id": st_a.id})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["station_id"] == st_a.id

    def test_list_filter_by_is_active(self, client):
        s = client._sesh
        st = _seed_station(s)
        _seed_fee(s, station_id=st.id, is_active=True)
        _seed_fee(s, station_id=st.id, user_type=UserType.CARD, is_active=False)
        r = client.get(URL, params={"is_active": False})
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["is_active"] is False

    def test_list_pagination(self, client):
        s = client._sesh
        st = _seed_station(s)
        # 3 个不同 user_type (同 station_id) 避免重叠校验在 seed 时其实不触发 (seed 直插)
        for ut in (UserType.APP, UserType.CARD, UserType.VIN):
            _seed_fee(s, station_id=st.id, user_type=ut)
        r = client.get(URL, params={"station_id": st.id, "page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2
        # id desc 排序
        assert d["items"][0]["id"] > d["items"][1]["id"]


# ═══════════════════════════════════════════════════════════════
# 2. 详情
# ═══════════════════════════════════════════════════════════════

class TestGet:
    def test_get_existing(self, client):
        s = client._sesh
        st = _seed_station(s)
        o = _seed_fee(s, station_id=st.id, fee_value="2.5000")
        r = client.get(f"{URL}/{o.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["id"] == o.id
        assert d["fee_value"] == 2.5
        assert d["user_type"] == "app"
        assert d["fee_type"] == "fixed"
        assert d["effective_date"] == "2026-01-01"
        assert d["expire_date"] is None

    def test_get_not_found_404(self, client):
        r = client.get(f"{URL}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. 创建 (含重叠校验 409 + 无效枚举 400 + 边界)
# ═══════════════════════════════════════════════════════════════

class TestCreate:
    def test_create_success(self, client):
        s = client._sesh
        st = _seed_station(s)
        r = client.post(URL, json=_payload(st.id, fee_value=3.25))
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["fee_value"] == 3.25
        assert d["is_active"] is True
        assert d["expire_date"] is None

    def test_create_with_expire(self, client):
        s = client._sesh
        st = _seed_station(s)
        r = client.post(URL, json=_payload(
            st.id, effective_date="2026-02-01", expire_date="2026-03-01"
        ))
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["effective_date"] == "2026-02-01"
        assert d["expire_date"] == "2026-03-01"

    def test_create_invalid_user_type_400(self, client):
        s = client._sesh
        st = _seed_station(s)
        r = client.post(URL, json=_payload(st.id, user_type="bogus"))
        assert r.status_code == 400

    def test_create_invalid_fee_type_400(self, client):
        s = client._sesh
        st = _seed_station(s)
        r = client.post(URL, json=_payload(st.id, fee_type="bogus"))
        assert r.status_code == 400

    def test_create_negative_fee_value_422(self, client):
        """fee_value ge=0 → Pydantic 校验 422。"""
        s = client._sesh
        st = _seed_station(s)
        r = client.post(URL, json=_payload(st.id, fee_value=-1))
        assert r.status_code == 422

    def test_create_overlap_active_409(self, client):
        """同 station+user_type 生效期重叠且都 is_active → 409 (缺陷1)。"""
        s = client._sesh
        st = _seed_station(s)
        _seed_fee(s, station_id=st.id, user_type=UserType.APP,
                  effective="2026-01-01", expire=None, is_active=True)
        r = client.post(URL, json=_payload(
            st.id, effective_date="2026-06-01"  # 与既有 [2026-01-01, +∞) 重叠
        ))
        assert r.status_code == 409

    def test_create_overlap_inactive_no_409(self, client):
        """失效行不参与重叠校验 → 非 active 既有行不阻断新建。"""
        s = client._sesh
        st = _seed_station(s)
        _seed_fee(s, station_id=st.id, user_type=UserType.APP,
                  effective="2026-01-01", expire=None, is_active=False)
        r = client.post(URL, json=_payload(st.id, effective_date="2026-06-01"))
        assert r.status_code == 200

    def test_create_non_overlap_allowed(self, client):
        """不同 station_id 同 user_type, 或不交叠区间 → 允许。"""
        s = client._sesh
        st = _seed_station(s)
        _seed_fee(s, station_id=st.id, user_type=UserType.APP,
                  effective="2025-01-01", expire="2025-12-31", is_active=True)
        r = client.post(URL, json=_payload(st.id, effective_date="2026-01-01"))
        assert r.status_code == 200  # 既有 2025 段已结束, 不重叠

    def test_create_inactive_skips_overlap_check(self, client):
        """is_active=False 时跳过重叠校验 (源码 if body.is_active 分支)。"""
        s = client._sesh
        st = _seed_station(s)
        _seed_fee(s, station_id=st.id, user_type=UserType.APP, is_active=True)
        r = client.post(URL, json=_payload(
            st.id, effective_date="2026-06-01", is_active=False
        ))
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# 4. 更新
# ═══════════════════════════════════════════════════════════════

class TestUpdate:
    def test_update_fields(self, client):
        s = client._sesh
        st = _seed_station(s)
        o = _seed_fee(s, station_id=st.id, is_active=False)  # seed 非 active 避免重叠校验
        r = client.put(f"{URL}/{o.id}", json={
            "fee_value": 9.9, "fee_type": "percent", "is_active": False,
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["fee_value"] == 9.9
        assert d["fee_type"] == "percent"

    def test_update_not_found_404(self, client):
        r = client.put(f"{URL}/999999", json={"fee_value": 1.0})
        assert r.status_code == 404

    def test_update_invalid_user_type_400(self, client):
        s = client._sesh
        st = _seed_station(s)
        o = _seed_fee(s, station_id=st.id, is_active=False)
        r = client.put(f"{URL}/{o.id}", json={"user_type": "bogus"})
        assert r.status_code == 400

    def test_update_overlap_excludes_self(self, client):
        """更新自身生效期不应与自身冲突 (item_id 排除自身)。"""
        s = client._sesh
        st = _seed_station(s)
        o = _seed_fee(s, station_id=st.id, is_active=True,
                      effective="2026-01-01", expire="2026-03-31")
        # 改自身的 expire_date, 仍落在自身区间内 —— 必须排除自身不报 409
        r = client.put(f"{URL}/{o.id}", json={"expire_date": "2026-02-28", "is_active": True})
        assert r.status_code == 200, r.text[:300]

    def test_update_activate_overlap_other_409(self, client):
        """把 inactive 行激活, 与另一 active 行生效期重叠 → 409。"""
        s = client._sesh
        st = _seed_station(s)
        _seed_fee(s, station_id=st.id, user_type=UserType.APP,
                  effective="2026-01-01", expire=None, is_active=True)
        # o2 seed 为开放区间 inactive, 改 effective 落入既有 active 开放区间即重叠
        o2 = _seed_fee(s, station_id=st.id, user_type=UserType.APP,
                       effective="2025-01-01", expire=None, is_active=False)
        r = client.put(f"{URL}/{o2.id}", json={
            "effective_date": "2026-06-01", "is_active": True,
        })
        assert r.status_code == 409


# ═══════════════════════════════════════════════════════════════
# 5. 删除
# ═══════════════════════════════════════════════════════════════

class TestDelete:
    def test_delete_success(self, client):
        s = client._sesh
        st = _seed_station(s)
        o = _seed_fee(s, station_id=st.id)
        r = client.delete(f"{URL}/{o.id}")
        assert r.status_code == 200
        # 删除后查不到
        assert client.get(f"{URL}/{o.id}").status_code == 404

    def test_delete_not_found_404(self, client):
        r = client.delete(f"{URL}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 6. 权限门 (router-level require_role("admin"))
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    @pytest.fixture
    def nonadmin_token(self, client):
        h = uuid.uuid4().hex[:6]
        _add_user(client._sesh, f"sf_op_{h}", UserRole.OPERATOR)
        return _login_token(client, f"sf_op_{h}")

    def test_operator_list_403(self, client, nonadmin_token):
        r = client.get(URL, headers=_auth(nonadmin_token))
        assert r.status_code == 403

    def test_operator_create_403(self, client, nonadmin_token):
        r = client.post(URL, json=_payload(1), headers=_auth(nonadmin_token))
        assert r.status_code == 403

    def test_anonymous_401(self, anon_client):
        r = anon_client.get(URL)
        assert r.status_code == 401
