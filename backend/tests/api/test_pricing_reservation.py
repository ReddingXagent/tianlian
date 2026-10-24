"""预约费定价 CRUD API 测试 (app/api/v1/pricing_management/reservation.py, 卡 96f676b3)

覆盖端点 (挂 /api/v1 前缀, pricing_management 无额外 prefix):
- GET    /pricing/mgmt/reservation            列表 (station_id / is_active 过滤 + 分页)
- GET    /pricing/mgmt/reservation/{id}       详情 (不存在 → 404)
- POST   /pricing/mgmt/reservation            创建 (无效 reservation_policy → 400)
- PUT    /pricing/mgmt/reservation/{id}       更新 (无效策略 → 400; 不存在 → 404)
- DELETE /pricing/mgmt/reservation/{id}       删除 (不存在 → 404)

权限门: router-level require_role("admin") —— admin 恒通过, operator/viewer → 403, 匿名 → 401。
"""
import uuid

import bcrypt
import pytest

from app.models.pricing_v2 import ReservationFeePrice, ReservationPolicy
from app.models.station import Station
from app.models.user import User, UserRole

URL = "/api/v1/pricing/mgmt/reservation"


# ─── helpers ───

def _add_user(session, username, role=UserRole.OPERATOR, password="pw123456"):
    u = User(
        username=username, real_name=username, role=role, status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session):
    sx = uuid.uuid4().hex[:6]
    st = Station(name=f"预约站{sx}", code=f"RFP{sx}")
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _create_via_api(client, station_id, **overrides):
    body = {
        "station_id": station_id,
        "deposit_amount": 100.0,
        "reservation_policy": "flat",
        "fee_amount": 5.0,
        "no_show_penalty": 20.0,
        "effective_date": "2026-01-01",
        "is_active": True,
    }
    body.update(overrides)
    r = client.post(URL, json=body)
    assert r.status_code == 200, f"创建失败: {r.status_code} {r.text[:300]}"
    return r.json()["data"]


# ═══════════════════════════════════════════════════════════════
# 1. 列表 + 详情
# ═══════════════════════════════════════════════════════════════

class TestListAndGet:
    def test_empty_list(self, client):
        r = client.get(URL)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["items"] == []

    def test_list_fields(self, client):
        s = client._sesh
        st = _seed_station(s)
        _create_via_api(client, st.id, fee_amount=8.0)
        r = client.get(URL)
        item = r.json()["data"]["items"][0]
        assert item["station_id"] == st.id
        assert item["reservation_policy"] == "flat"
        assert item["fee_amount"] == 8.0
        assert item["deposit_amount"] == 100.0
        assert item["is_active"] is True

    def test_list_filter_by_station(self, client):
        s = client._sesh
        sa = _seed_station(s)
        sb = _seed_station(s)
        _create_via_api(client, sa.id)
        _create_via_api(client, sb.id)
        r = client.get(URL, params={"station_id": sa.id})
        d = r.json()["data"]
        assert d["total"] == 1
        assert d["items"][0]["station_id"] == sa.id

    def test_list_filter_by_active(self, client):
        s = client._sesh
        st = _seed_station(s)
        _create_via_api(client, st.id, is_active=True)
        _create_via_api(client, st.id, is_active=False)
        r = client.get(URL, params={"is_active": True})
        assert r.json()["data"]["total"] == 1

    def test_list_pagination(self, client):
        s = client._sesh
        st = _seed_station(s)
        for _ in range(3):
            _create_via_api(client, st.id)
        r = client.get(URL, params={"page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2

    def test_get_detail(self, client):
        s = client._sesh
        st = _seed_station(s)
        created = _create_via_api(client, st.id)
        r = client.get(f"{URL}/{created['id']}")
        assert r.status_code == 200
        assert r.json()["data"]["id"] == created["id"]

    def test_get_detail_not_found_404(self, client):
        r = client.get(f"{URL}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 2. 创建 + 更新
# ═══════════════════════════════════════════════════════════════

class TestCreateAndUpdate:
    def test_create_slot_based(self, client):
        s = client._sesh
        st = _seed_station(s)
        d = _create_via_api(client, st.id, reservation_policy="slot_based")
        assert d["reservation_policy"] == "slot_based"

    def test_create_invalid_policy_400(self, client):
        s = client._sesh
        st = _seed_station(s)
        body = {
            "station_id": st.id, "reservation_policy": "invalid_policy",
            "effective_date": "2026-01-01",
        }
        r = client.post(URL, json=body)
        assert r.status_code == 400
        assert "预约策略" in r.json()["detail"]

    def test_update_fields(self, client):
        s = client._sesh
        st = _seed_station(s)
        created = _create_via_api(client, st.id)
        r = client.put(f"{URL}/{created['id']}", json={"fee_amount": 99.0, "is_active": False})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["fee_amount"] == 99.0
        assert d["is_active"] is False

    def test_update_not_found_404(self, client):
        r = client.put(f"{URL}/999999", json={"fee_amount": 1.0})
        assert r.status_code == 404

    def test_update_invalid_policy_400(self, client):
        s = client._sesh
        st = _seed_station(s)
        created = _create_via_api(client, st.id)
        r = client.put(f"{URL}/{created['id']}", json={"reservation_policy": "bad"})
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# 3. 删除
# ═══════════════════════════════════════════════════════════════

class TestDelete:
    def test_delete_success(self, client):
        s = client._sesh
        st = _seed_station(s)
        created = _create_via_api(client, st.id)
        r = client.delete(f"{URL}/{created['id']}")
        assert r.status_code == 200
        assert s.query(ReservationFeePrice).filter_by(id=created["id"]).first() is None

    def test_delete_not_found_404(self, client):
        assert client.delete(f"{URL}/999999").status_code == 404


# ═══════════════════════════════════════════════════════════════
# 4. 权限门 (router-level require_role("admin"))
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_anonymous_401(self, anon_client):
        assert anon_client.get(URL).status_code == 401

    def test_operator_403(self, client):
        s = client._sesh
        _add_user(s, "rfp_op", role=UserRole.OPERATOR)
        s.commit()
        token = _login_token(client, "rfp_op")
        r = client.get(URL, headers=_auth(token))
        assert r.status_code == 403
