"""司机考勤/工时管理 CRUD API 测试 (工作卡 418bbeac)

覆盖 app/api/v1/fleet_attendance.py (挂 /api/v1/fleet/attendance 前缀):
- POST /fleet/attendance/batch    批量录入 (新建 / upsert / 非法枚举 400 / 月份格式不校验仅透传 /
                                    司机不存在 404)
- GET  /fleet/attendance/summary  月度汇总 (总工时 / 各状态天数 / 出勤率 / rest 分离)
- GET  /fleet/attendance          查询 (按司机+月份, 日期升序 + 分页 + 月份格式 400)
- PUT  /fleet/attendance/{id}     修正 (字段覆盖 / 不存在 404 / 非法枚举 400)

权限门: router-level require_write_permission("fleet:manage") —— GET 放行(仅认证),
POST/PUT 委托 require_permission: admin 恒通过, viewer 无 fleet:manage → 写 403, 匿名 → 401。
team scoping: assert_driver_team_access —— admin 豁免, 司机不存在/跨团队 → 404。
"""
import uuid

import bcrypt
import pytest

from app.models.enterprise import Enterprise
from app.models.fleet_driver import FleetDriver, DriverStatus
from app.models.fleet_driver_attendance import FleetDriverAttendance
from app.models.user import User, UserRole

BASE = "/api/v1/fleet/attendance"


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


def _seed_driver(session, idx=0):
    ent = Enterprise(name=f"考勤企业{idx}-{uuid.uuid4().hex[:4]}", code=f"ATT{uuid.uuid4().hex[:6]}", balance=10000.0)
    session.add(ent)
    session.commit()
    session.refresh(ent)
    d = FleetDriver(
        enterprise_id=ent.id,
        name=f"司机{idx}",
        phone=f"138000000{idx:02d}",
        license_no=f"LIC-ATT-{idx}",
        status=DriverStatus.ACTIVE,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return d


def _batch(records):
    return {"driver_id": None, "month": "2026-07", "records": records}


# ═══════════════════════════════════════════════════════════════
# 1. 批量录入 (新建 / upsert / 校验 / team scoping)
# ═══════════════════════════════════════════════════════════════

class TestBatchImport:
    def test_batch_create_new(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        r = client.post(f"{BASE}/batch", json=_batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
            {"date": "2026-07-02", "shift_type": "night", "hours": 7.5, "status": "late"},
        ]) | {"driver_id": drv.id})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["created"] == 2
        assert d["updated"] == 0
        assert d["total"] == 2

    def test_batch_upsert_existing(self, client):
        """同 (driver_id, date) 重复录入 → update 而非新建。"""
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        client.post(f"{BASE}/batch", json=payload)
        # 第二次同 date → updated
        payload["records"][0]["hours"] = 9.0
        r = client.post(f"{BASE}/batch", json=payload)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["created"] == 0
        assert d["updated"] == 1
        # 工时被覆盖
        rec = s.query(FleetDriverAttendance).filter_by(driver_id=drv.id, date="2026-07-01").first()
        assert rec.hours == 9.0

    def test_batch_invalid_shift_type_400(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "bogus", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        r = client.post(f"{BASE}/batch", json=payload)
        # 343baf02f Literal收紧后非法shift_type由Pydantic前置422拦截
        assert r.status_code == 422

    def test_batch_invalid_status_400(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "bogus"},
        ])
        payload["driver_id"] = drv.id
        r = client.post(f"{BASE}/batch", json=payload)
        # 343baf02f Literal收紧后非法status由Pydantic前置422拦截
        assert r.status_code == 422

    def test_batch_negative_hours_422(self, client):
        """hours ge=0 → Pydantic 校验 422。"""
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": -1.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        r = client.post(f"{BASE}/batch", json=payload)
        assert r.status_code == 422

    def test_batch_driver_not_found_404(self, client):
        """司机不存在 → assert_driver_team_access 404。"""
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = 999999
        r = client.post(f"{BASE}/batch", json=payload)
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 2. 月度汇总 (出勤率 / rest 分离)
# ═══════════════════════════════════════════════════════════════

class TestSummary:
    def test_summary_rates_and_rest_split(self, client):
        """normal+late+absent 决定出勤率; rest 班次单列不计入 status。"""
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
            {"date": "2026-07-02", "shift_type": "day", "hours": 8.0, "status": "late"},
            {"date": "2026-07-03", "shift_type": "day", "hours": 0.0, "status": "absent"},
            {"date": "2026-07-04", "shift_type": "rest", "hours": 0.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        client.post(f"{BASE}/batch", json=payload)

        r = client.get(f"{BASE}/summary", params={"driver_id": drv.id, "month": "2026-07"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_days"] == 4
        assert d["total_hours"] == 16.0
        assert d["normal_days"] == 1
        assert d["late_days"] == 1
        assert d["absent_days"] == 1
        assert d["rest_days"] == 1
        # 出勤率 = (normal+late) / (normal+late+absent) = 2/3
        assert d["attendance_rate"] == round(2 / 3, 4)

    def test_summary_empty_month_zero_rate(self, client):
        """无应出勤记录 → attendance_rate=0.0。"""
        s = client._sesh
        drv = _seed_driver(s)
        r = client.get(f"{BASE}/summary", params={"driver_id": drv.id, "month": "2026-07"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_days"] == 0
        assert d["attendance_rate"] == 0.0

    def test_summary_invalid_month_400(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        r = client.get(f"{BASE}/summary", params={"driver_id": drv.id, "month": "202607"})
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# 3. 查询 (日期升序 + 分页 + 月份格式)
# ═══════════════════════════════════════════════════════════════

class TestList:
    def test_list_ordered_by_date_asc(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-03", "shift_type": "day", "hours": 8.0, "status": "normal"},
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
            {"date": "2026-07-02", "shift_type": "day", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        client.post(f"{BASE}/batch", json=payload)
        r = client.get(BASE, params={"driver_id": drv.id, "month": "2026-07"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total"] == 3
        dates = [it["date"] for it in d["items"]]
        assert dates == ["2026-07-01", "2026-07-02", "2026-07-03"]

    def test_list_pagination(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": f"2026-07-{i:02d}", "shift_type": "day", "hours": 8.0, "status": "normal"}
            for i in range(1, 4)
        ])
        payload["driver_id"] = drv.id
        client.post(f"{BASE}/batch", json=payload)
        r = client.get(BASE, params={"driver_id": drv.id, "month": "2026-07", "page": 1, "page_size": 2})
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2

    def test_list_invalid_month_400(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        r = client.get(BASE, params={"driver_id": drv.id, "month": "bad-month"})
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# 4. 修正 (字段覆盖 / 404 / 非法枚举)
# ═══════════════════════════════════════════════════════════════

class TestUpdate:
    def test_update_fields(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        client.post(f"{BASE}/batch", json=payload)
        rec = s.query(FleetDriverAttendance).filter_by(driver_id=drv.id, date="2026-07-01").first()

        r = client.put(f"{BASE}/{rec.id}", json={"hours": 6.5, "status": "late", "remark": "迟到"})
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["hours"] == 6.5
        assert d["status"] == "late"
        assert d["remark"] == "迟到"

    def test_update_not_found_404(self, client):
        r = client.put(f"{BASE}/999999", json={"hours": 1.0})
        assert r.status_code == 404

    def test_update_invalid_shift_type_400(self, client):
        s = client._sesh
        drv = _seed_driver(s)
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = drv.id
        client.post(f"{BASE}/batch", json=payload)
        rec = s.query(FleetDriverAttendance).filter_by(driver_id=drv.id, date="2026-07-01").first()
        r = client.put(f"{BASE}/{rec.id}", json={"shift_type": "bogus"})
        # 343baf02f Literal收紧后非法shift_type由Pydantic前置422拦截
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 5. 权限门 (router-level require_write_permission("fleet:manage"))
# ═══════════════════════════════════════════════════════════════

class TestPermissionGate:
    @pytest.fixture
    def viewer_token(self, client):
        """viewer 无 fleet:manage 权限。"""
        h = uuid.uuid4().hex[:6]
        _add_user(client._sesh, f"att_view_{h}", UserRole.VIEWER)
        return _login_token(client, f"att_view_{h}")

    def test_viewer_write_batch_403(self, client, viewer_token):
        payload = _batch([
            {"date": "2026-07-01", "shift_type": "day", "hours": 8.0, "status": "normal"},
        ])
        payload["driver_id"] = 1
        r = client.post(f"{BASE}/batch", json=payload, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_viewer_write_update_403(self, client, viewer_token):
        r = client.put(f"{BASE}/1", json={"hours": 1.0}, headers=_auth(viewer_token))
        assert r.status_code == 403

    def test_anonymous_401(self, anon_client):
        r = anon_client.get(f"{BASE}/summary", params={"driver_id": 1, "month": "2026-07"})
        assert r.status_code == 401
