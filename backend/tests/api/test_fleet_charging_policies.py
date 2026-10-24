"""企业充电策略 CRUD API 测试 (工作卡 418bbeac)

覆盖 app/api/v1/fleet_charging_policies.py (挂 /api/v1/fleet 前缀):
- GET    /fleet/policies              列表 (enterprise_id 筛选 + 分页)
- POST   /fleet/policies              创建 (daily_kwh_limit<0 → 422; 企业不存在 → 404)
- PUT    /fleet/policies/{id}         更新 (仅覆盖传入字段; 不存在 → 404)
- DELETE /fleet/policies/{id}         删除 (不存在 → 404)
- GET    /fleet/policies/check        校验 (无策略放行 / 站点白名单 / 时段白名单 / 日限额 / 全满足 / 禁用忽略)

权限门: router-level require_write_permission("fleet:manage") —— GET 放行(仅认证),
POST/PUT/DELETE 委托 require_permission: admin 恒通过, viewer 无 fleet:manage → 写 403, 匿名 → 401。
team scoping: assert_enterprise_team_access —— admin 豁免, 企业不存在/跨团队 → 404。
"""
import uuid

import bcrypt
import pytest

from app.models.enterprise import Enterprise
from app.models.fleet_charging_policy import FleetChargingPolicy
from app.models.user import User, UserRole

BASE = "/api/v1/fleet/policies"


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


def _seed_enterprise(session, code=None):
    cx = code or f"E{uuid.uuid4().hex[:6]}"
    ent = Enterprise(name=f"策略企业{cx}", code=cx, balance=10000.0)
    session.add(ent)
    session.commit()
    session.refresh(ent)
    return ent


def _payload(enterprise_id, **overrides):
    p = {
        "enterprise_id": enterprise_id,
        "daily_kwh_limit": 100.0,
        "allowed_time_slots": ["谷", "平"],
        "allowed_station_ids": [1, 2],
        "enable": True,
    }
    p.update(overrides)
    return p


# ═══════════════════════════════════════════════════════════════
# 1. 列表 (企业筛选 + 分页)
# ═══════════════════════════════════════════════════════════════

class TestList:
    def test_list_empty(self, client):
        r = client.get(BASE)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["items"] == []

    def test_list_filter_by_enterprise(self, client):
        s = client._sesh
        ea = _seed_enterprise(s, "AA")
        eb = _seed_enterprise(s, "BB")
        s.add(FleetChargingPolicy(enterprise_id=ea.id, daily_kwh_limit=10.0, enable=True))
        s.add(FleetChargingPolicy(enterprise_id=eb.id, daily_kwh_limit=20.0, enable=True))
        s.commit()
        r = client.get(BASE, params={"enterprise_id": ea.id})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["enterprise_id"] == ea.id

    def test_list_pagination(self, client):
        s = client._sesh
        ent = _seed_enterprise(s)
        for _ in range(3):
            s.add(FleetChargingPolicy(enterprise_id=ent.id, daily_kwh_limit=5.0, enable=True))
        s.commit()
        r = client.get(BASE, params={"enterprise_id": ent.id, "page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2
        # id desc 排序
        assert d["items"][0]["id"] > d["items"][1]["id"]


# ═══════════════════════════════════════════════════════════════
# 2. 创建 (正常 + 校验 + team scoping 404)
# ═══════════════════════════════════════════════════════════════

class TestCreate:
    def test_create_success(self, client):
        s = client._sesh
        ent = _seed_enterprise(s)
        r = client.post(BASE, json=_payload(ent.id, daily_kwh_limit=250.0))
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["enterprise_id"] == ent.id
        assert d["daily_kwh_limit"] == 250.0
        assert d["allowed_time_slots"] == ["谷", "平"]
        assert d["allowed_station_ids"] == [1, 2]
        assert d["enable"] is True

    def test_create_defaults_when_optional_omitted(self, client):
        """allowed_time_slots/station_ids 缺省 + enable 默认 True。"""
        s = client._sesh
        ent = _seed_enterprise(s)
        r = client.post(BASE, json={"enterprise_id": ent.id})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["allowed_time_slots"] == []
        assert d["allowed_station_ids"] == []
        assert d["enable"] is True
        assert d["daily_kwh_limit"] == 0.0  # Field 默认 0.0

    def test_create_negative_limit_422(self, client):
        """daily_kwh_limit ge=0 → Pydantic 校验 422。"""
        s = client._sesh
        ent = _seed_enterprise(s)
        r = client.post(BASE, json=_payload(ent.id, daily_kwh_limit=-1))
        assert r.status_code == 422

    def test_create_enterprise_not_found_404(self, client):
        """企业不存在 → assert_enterprise_team_access 404 (admin 也走企业存在性)。"""
        r = client.post(BASE, json=_payload(999999))
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. 更新 + 删除
# ═══════════════════════════════════════════════════════════════

class TestUpdateDelete:
    def _seed_policy(self, session):
        ent = _seed_enterprise(session)
        p = FleetChargingPolicy(
            enterprise_id=ent.id, daily_kwh_limit=50.0,
            allowed_time_slots=["峰"], allowed_station_ids=[1], enable=True,
        )
        session.add(p)
        session.commit()
        session.refresh(p)
        return p

    def test_update_partial_fields(self, client):
        s = client._sesh
        p = self._seed_policy(s)
        r = client.put(f"{BASE}/{p.id}", json={"daily_kwh_limit": 80.0, "enable": False})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["daily_kwh_limit"] == 80.0
        assert d["enable"] is False
        # 未传字段保持原值
        assert d["allowed_time_slots"] == ["峰"]

    def test_update_not_found_404(self, client):
        r = client.put(f"{BASE}/999999", json={"daily_kwh_limit": 1.0})
        assert r.status_code == 404

    def test_update_negative_limit_422(self, client):
        s = client._sesh
        p = self._seed_policy(s)
        r = client.put(f"{BASE}/{p.id}", json={"daily_kwh_limit": -5})
        assert r.status_code == 422

    def test_delete_success(self, client):
        s = client._sesh
        p = self._seed_policy(s)
        r = client.delete(f"{BASE}/{p.id}")
        assert r.status_code == 200
        # 删除后查不到
        assert s.query(FleetChargingPolicy).filter_by(id=p.id).first() is None

    def test_delete_not_found_404(self, client):
        r = client.delete(f"{BASE}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 4. check 校验逻辑
# ═══════════════════════════════════════════════════════════════

class TestCheck:
    def test_check_no_policy_allowed(self, client):
        """无启用策略 → 放行 allowed=True。"""
        s = client._sesh
        ent = _seed_enterprise(s)
        r = client.get(f"{BASE}/check", params={
            "enterprise_id": ent.id, "station_id": 9, "time_slot": "峰",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["allowed"] is True
        assert d["policy_id"] is None

    def test_check_all_satisfied_allowed(self, client):
        """站点/时段都在白名单, 未达限额 → 放行。"""
        s = client._sesh
        ent = _seed_enterprise(s)
        s.add(FleetChargingPolicy(
            enterprise_id=ent.id, daily_kwh_limit=100.0,
            allowed_time_slots=["峰", "平"], allowed_station_ids=[1, 2], enable=True,
        ))
        s.commit()
        r = client.get(f"{BASE}/check", params={
            "enterprise_id": ent.id, "station_id": 2, "time_slot": "峰",
        })
        assert r.status_code == 200
        assert r.json()["data"]["allowed"] is True

    def test_check_station_not_in_whitelist_denied(self, client):
        s = client._sesh
        ent = _seed_enterprise(s)
        s.add(FleetChargingPolicy(
            enterprise_id=ent.id, daily_kwh_limit=100.0,
            allowed_station_ids=[1, 2], enable=True,
        ))
        s.commit()
        r = client.get(f"{BASE}/check", params={
            "enterprise_id": ent.id, "station_id": 99, "time_slot": "峰",
        })
        d = r.json()["data"]
        assert d["allowed"] is False
        assert "站点" in d["reason"]

    def test_check_disabled_policy_ignored(self, client):
        """enable=False 的策略被 _active_policy 跳过 → 视同无策略放行。"""
        s = client._sesh
        ent = _seed_enterprise(s)
        s.add(FleetChargingPolicy(
            enterprise_id=ent.id, daily_kwh_limit=1.0,
            allowed_station_ids=[1], enable=False,
        ))
        s.commit()
        r = client.get(f"{BASE}/check", params={
            "enterprise_id": ent.id, "station_id": 99, "time_slot": "峰",
        })
        d = r.json()["data"]
        assert d["allowed"] is True
        assert d["policy_id"] is None

    def test_check_missing_required_query_422(self, client):
        """check 三个 query 均 required (...) → 缺参 422。"""
        s = client._sesh
        ent = _seed_enterprise(s)
        r = client.get(f"{BASE}/check", params={"enterprise_id": ent.id})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 5. 权限门 (router-level require_write_permission("fleet:manage"))
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    @pytest.fixture
    def viewer_token(self, client):
        """viewer 无 fleet:manage 权限。"""
        h = uuid.uuid4().hex[:6]
        _add_user(client._sesh, f"fcp_view_{h}", UserRole.VIEWER)
        return _login_token(client, f"fcp_view_{h}")

    def test_viewer_write_create_403(self, client, viewer_token):
        r = client.post(BASE, json=_payload(1), headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_write_delete_403(self, client, viewer_token):
        r = client.delete(f"{BASE}/1", headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_anonymous_401(self, anon_client):
        r = anon_client.get(BASE)
        assert r.status_code == 401
