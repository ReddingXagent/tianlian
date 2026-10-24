"""时段定义 CRUD API 测试 (工作卡 be1f5eb4)

覆盖 app/api/v1/pricing_management/time_slots.py (挂 /api/v1 前缀, 无额外 prefix):
- GET  /pricing/mgmt/time-slots            列表 (is_active 过滤 + 分页, 按 sort_order 升序)
- GET  /pricing/mgmt/time-slots/{id}       详情 (不存在 → 404)
- POST /pricing/mgmt/time-slots            创建 (无效 period_type → 400; name 空 → 422)
- PUT  /pricing/mgmt/time-slots/{id}       更新 (无效 period_type → 400; 不存在 → 404)
- DELETE /pricing/mgmt/time-slots/{id}     删除

注意: TimeSlotDefinition.period_type 列带 unique 约束, 同库 seed 多条须用不同 period_type
(peak/shoulder/flat/valley)。

权限门: router-level require_role("admin") —— admin 恒通过, operator/viewer → 403, 匿名 → 401。
"""
import uuid

import bcrypt
import pytest

from app.models.pricing_v2 import TimeSlotDefinition, PeriodType
from app.models.user import User, UserRole

URL = "/api/v1/pricing/mgmt/time-slots"


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


def _seed_slot(session, *, name="尖时段", period_type=PeriodType.PEAK,
               start="10:00", end="12:00", is_active=True, sort_order=0):
    """直接落一条 TimeSlotDefinition (绕过 API)。period_type unique, 调用方须确保唯一。"""
    from datetime import time as dt_time
    o = TimeSlotDefinition(
        name=name,
        period_type=period_type,
        start_time=dt_time(int(start.split(":")[0]), int(start.split(":")[1])),
        end_time=dt_time(int(end.split(":")[0]), int(end.split(":")[1])),
        is_active=is_active,
        sort_order=sort_order,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _payload(**overrides):
    p = {
        "name": "尖时段",
        "period_type": "peak",
        "start_time": "10:00",
        "end_time": "12:00",
        "description": "上午尖峰",
        "is_active": True,
        "sort_order": 1,
    }
    p.update(overrides)
    return p


# ═══════════════════════════════════════════════════════════════
# 1. 列表 (过滤 + 排序 + 分页)
# ═══════════════════════════════════════════════════════════════

class TestList:
    def test_list_empty(self, client):
        r = client.get(URL)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 0
        assert d["items"] == []

    def test_list_filter_by_is_active(self, client):
        s = client._sesh
        _seed_slot(s, name="峰", period_type=PeriodType.PEAK, is_active=True)
        _seed_slot(s, name="平", period_type=PeriodType.FLAT, is_active=False)
        r = client.get(URL, params={"is_active": True})
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["name"] == "峰"

    def test_list_sorted_by_sort_order(self, client):
        s = client._sesh
        _seed_slot(s, name="谷", period_type=PeriodType.VALLEY, sort_order=3)
        _seed_slot(s, name="尖", period_type=PeriodType.PEAK, sort_order=1)
        _seed_slot(s, name="平", period_type=PeriodType.FLAT, sort_order=2)
        r = client.get(URL)
        names = [i["name"] for i in r.json()["data"]["items"]]
        assert names == ["尖", "平", "谷"]  # 按 sort_order 升序

    def test_list_pagination(self, client):
        s = client._sesh
        for i, pt in enumerate((PeriodType.PEAK, PeriodType.FLAT, PeriodType.VALLEY, PeriodType.SHOULDER)):
            _seed_slot(s, name=f"时段{i}", period_type=pt, sort_order=i)
        r = client.get(URL, params={"page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 4
        assert len(d["items"]) == 2
        r2 = client.get(URL, params={"page": 2, "page_size": 2})
        assert len(r2.json()["data"]["items"]) == 2


# ═══════════════════════════════════════════════════════════════
# 2. 详情
# ═══════════════════════════════════════════════════════════════

class TestGet:
    def test_get_existing(self, client):
        s = client._sesh
        o = _seed_slot(s, name="尖", period_type=PeriodType.PEAK,
                       start="10:00", end="12:00", sort_order=5)
        r = client.get(f"{URL}/{o.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["id"] == o.id
        assert d["name"] == "尖"
        assert d["period_type"] == "peak"
        assert d["start_time"] == "10:00"
        assert d["end_time"] == "12:00"
        assert d["sort_order"] == 5
        assert d["is_active"] is True

    def test_get_not_found_404(self, client):
        r = client.get(f"{URL}/999999")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. 创建
# ═══════════════════════════════════════════════════════════════

class TestCreate:
    def test_create_success(self, client):
        r = client.post(URL, json=_payload(period_type="flat", name="平时段"))
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["name"] == "平时段"
        assert d["period_type"] == "flat"
        assert d["start_time"] == "10:00"
        assert d["description"] == "上午尖峰"

    def test_create_invalid_period_type_400(self, client):
        r = client.post(URL, json=_payload(period_type="bogus"))
        assert r.status_code == 400

    def test_create_empty_name_422(self, client):
        """name min_length=1 → Pydantic 422。"""
        r = client.post(URL, json=_payload(name="", period_type="valley"))
        assert r.status_code == 422

    def test_create_start_after_end_allowed(self, client):
        """时段定义无 start<end 校验, 当前允许 start_time > end_time (固化现状)。"""
        r = client.post(URL, json=_payload(
            period_type="shoulder", start_time="23:00", end_time="06:00"
        ))
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["start_time"] == "23:00"
        assert d["end_time"] == "06:00"

    def test_create_default_sort_order(self, client):
        r = client.post(URL, json={
            "name": "尖", "period_type": "peak",
            "start_time": "00:00", "end_time": "06:00",
        })
        assert r.status_code == 200
        assert r.json()["data"]["sort_order"] == 0  # schema 默认


# ═══════════════════════════════════════════════════════════════
# 4. 更新
# ═══════════════════════════════════════════════════════════════

class TestUpdate:
    def test_update_fields(self, client):
        s = client._sesh
        o = _seed_slot(s, name="尖", period_type=PeriodType.PEAK)
        r = client.put(f"{URL}/{o.id}", json={
            "name": "尖峰时段", "start_time": "14:00", "end_time": "17:00",
            "is_active": False, "sort_order": 9,
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["name"] == "尖峰时段"
        assert d["start_time"] == "14:00"
        assert d["end_time"] == "17:00"
        assert d["is_active"] is False
        assert d["sort_order"] == 9

    def test_update_not_found_404(self, client):
        r = client.put(f"{URL}/999999", json={"name": "x"})
        assert r.status_code == 404

    def test_update_invalid_period_type_400(self, client):
        s = client._sesh
        o = _seed_slot(s, name="尖", period_type=PeriodType.PEAK)
        r = client.put(f"{URL}/{o.id}", json={"period_type": "bogus"})
        assert r.status_code == 400

    def test_update_partial_no_change_to_others(self, client):
        s = client._sesh
        o = _seed_slot(s, name="尖", period_type=PeriodType.PEAK, start="10:00", end="12:00")
        r = client.put(f"{URL}/{o.id}", json={"description": "更新描述"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["description"] == "更新描述"
        assert d["name"] == "尖"  # 未传字段保持原值
        assert d["start_time"] == "10:00"


# ═══════════════════════════════════════════════════════════════
# 5. 删除
# ═══════════════════════════════════════════════════════════════

class TestDelete:
    def test_delete_success(self, client):
        s = client._sesh
        o = _seed_slot(s, name="尖", period_type=PeriodType.PEAK)
        r = client.delete(f"{URL}/{o.id}")
        assert r.status_code == 200
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
        _add_user(client._sesh, f"ts_op_{h}", UserRole.OPERATOR)
        return _login_token(client, f"ts_op_{h}")

    def test_operator_list_403(self, client, nonadmin_token):
        r = client.get(URL, headers=_auth(nonadmin_token))
        assert r.status_code == 403

    def test_operator_create_403(self, client, nonadmin_token):
        r = client.post(URL, json=_payload(period_type="valley"),
                        headers=_auth(nonadmin_token))
        assert r.status_code == 403

    def test_anonymous_401(self, anon_client):
        r = anon_client.get(URL)
        assert r.status_code == 401
