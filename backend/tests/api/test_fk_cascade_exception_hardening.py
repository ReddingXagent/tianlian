"""fk_cascade 级联删除异常转译加固（卡 4e202c2b）

7 个删除端点（enterprises/stations/teams/tenant/users/work-orders/devices）
裸调 purge_*_children，DB 异常裸抛 500 泄漏内部细节（SQL/表名/驱动报文）。

本文件验证：
- IntegrityError → 409（含资源名，不含内部细节）
- OperationalError → 503（不含内部细节）
- 其余 Exception → 500（detail 不含 stmt/表名/驱动报文）
- 失败后调用 db.rollback()（不污染后续请求）

设计: monkeypatch sqlalchemy Query.delete/update 使 purge_* 内的处置语句抛
构造异常——走真实 _purge_guard 装饰器转译（直接替换 purge_* 属性会绕过装饰器）。
"""
import uuid as _uuid

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from tests.api.test_fk_delete_cascade import fk_env  # noqa: F401 复用 FK-ON 环境


def _u():
    return _uuid.uuid4().hex[:8]


def _integrity_err():
    return IntegrityError(
        "UPDATE device_configs SET ...", {"id": 1}, Exception("FOREIGN KEY constraint failed")
    )


def _operational_err():
    return OperationalError("DELETE FROM stations", {}, Exception("database is locked"))


def _generic_err():
    return RuntimeError("boom: relation stations does not exist")


# ─── patch 工具 ──────────────────────────────────────────────────

def _patch_purge(monkeypatch, name, exc):
    """在 DB 层注入异常: purge_* 的处置语句全是 Query.delete/update/execute。

    走真实 guard 装饰器（不能直接替换 purge_* 模块属性——那会绕过装饰器）。
    parent 行的 db.query(...).first() 查询不受影响。
    """
    from sqlalchemy.orm import Query

    def _boom(*a, **kw):
        raise exc

    monkeypatch.setattr(Query, "delete", _boom)
    monkeypatch.setattr(Query, "update", _boom)


def _assert_no_leak(detail: str):
    low = detail.lower()
    for token in ("update", "delete from", "insert", "select", "constraint",
                  "sqlite", "foreign key", "relation", "device_configs", "boom"):
        assert token not in low, f"detail 泄漏内部细节: {detail}"


# ─── 1. DELETE /api/v1/stations/{id} ────────────────────────────

class TestDeleteStationException:
    @pytest.mark.parametrize("mk_exc,code,msg", [
        (_integrity_err, 409, "站点"),
        (_operational_err, 503, None),
        (_generic_err, 500, "站点"),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code, msg):
        from app.models.station import Station, StationStatus
        s = client._sesh
        st = Station(name=f"站{_u()}", code=f"ST{_u().upper()}",
                     status=StationStatus.NORMAL)
        s.add(st); s.commit(); s.refresh(st)

        _patch_purge(monkeypatch, "purge_station_children", mk_exc())
        resp = client.delete(f"/api/v1/stations/{st.id}")
        assert resp.status_code == code, resp.text
        detail = str(resp.json().get("detail", ""))
        if msg:
            assert msg in detail
        _assert_no_leak(detail)

    def test_rollback_called(self, client, monkeypatch):
        from unittest.mock import patch
        from sqlalchemy.orm import Query
        from app.models.station import Station, StationStatus
        s = client._sesh
        st = Station(name=f"站{_u()}", code=f"SB{_u().upper()}",
                     status=StationStatus.NORMAL)
        s.add(st); s.commit(); s.refresh(st)

        def _boom(*a, **kw):
            raise _integrity_err()

        monkeypatch.setattr(Query, "delete", _boom)
        with patch.object(type(s), "rollback") as rb:
            resp = client.delete(f"/api/v1/stations/{st.id}")
        assert resp.status_code == 409
        rb.assert_called()


# ─── 2. DELETE /api/v1/teams/{id} ────────────────────────────────

class TestDeleteTeamException:
    @pytest.mark.parametrize("mk_exc,code", [
        (_integrity_err, 409), (_operational_err, 503), (_generic_err, 500),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code):
        from app.models.user import Team
        s = client._sesh
        team = Team(name=f"团{_u()}", code=f"TM{_u().upper()}")
        s.add(team); s.commit(); s.refresh(team)

        _patch_purge(monkeypatch, "purge_team_children", mk_exc())
        resp = client.delete(f"/api/v1/teams/{team.id}")
        assert resp.status_code == code, resp.text
        if code != 503:
            assert "团队" in str(resp.json().get("detail", ""))
        _assert_no_leak(str(resp.json().get("detail", "")))


# ─── 3. DELETE /api/v1/tenants/{id} ─────────────────────────────

class TestDeleteTenantException:
    @pytest.mark.parametrize("mk_exc,code", [
        (_integrity_err, 409), (_operational_err, 503), (_generic_err, 500),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code):
        from app.models.tenant import Tenant
        s = client._sesh
        t = Tenant(name=f"租{_u()}", code=f"TE{_u().upper()}")
        s.add(t); s.commit(); s.refresh(t)

        _patch_purge(monkeypatch, "purge_tenant_children", mk_exc())
        resp = client.delete(f"/api/v1/tenants/{t.id}")
        assert resp.status_code == code, resp.text
        if code != 503:
            assert "租户" in str(resp.json().get("detail", ""))
        _assert_no_leak(str(resp.json().get("detail", "")))


# ─── 4. DELETE /api/v1/users/{id} ───────────────────────────────

class TestDeleteUserException:
    @pytest.mark.parametrize("mk_exc,code", [
        (_integrity_err, 409), (_operational_err, 503), (_generic_err, 500),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code):
        from app.models.user import User, UserRole
        s = client._sesh
        u = User(username=f"u{_u()}", password_hash="x",
                 role=UserRole.VIEWER, status="active")
        s.add(u); s.commit(); s.refresh(u)

        _patch_purge(monkeypatch, "purge_user_children", mk_exc())
        resp = client.delete(f"/api/v1/users/{u.id}")
        assert resp.status_code == code, resp.text
        if code != 503:
            assert "用户" in str(resp.json().get("detail", ""))
        _assert_no_leak(str(resp.json().get("detail", "")))


# ─── 5. DELETE /api/v1/enterprises/{id} ─────────────────────────

class TestDeleteEnterpriseException:
    @pytest.mark.parametrize("mk_exc,code", [
        (_integrity_err, 409), (_operational_err, 503), (_generic_err, 500),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code):
        from app.models.enterprise import Enterprise, EnterpriseStatus
        s = client._sesh
        ent = Enterprise(name=f"企{_u()}", code=f"EE{_u().upper()}",
                         status=EnterpriseStatus.ACTIVE)
        s.add(ent); s.commit(); s.refresh(ent)

        _patch_purge(monkeypatch, "purge_enterprise_children", mk_exc())
        resp = client.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == code, resp.text
        if code != 503:
            assert "企业" in str(resp.json().get("detail", ""))
        _assert_no_leak(str(resp.json().get("detail", "")))

    def test_ledger_guard_still_409_before_purge(self, client, monkeypatch):
        """账本守卫在前：有账本数据仍 409 且不触发 purge。"""
        from decimal import Decimal
        from app.models.enterprise import Enterprise, EnterpriseStatus
        s = client._sesh
        ent = Enterprise(name=f"企L{_u()}", code=f"EL{_u().upper()}",
                         status=EnterpriseStatus.ACTIVE, balance=Decimal("1.00"))
        s.add(ent); s.commit(); s.refresh(ent)

        import app.services.fk_cascade as fkc
        called = []
        monkeypatch.setattr(
            fkc, "purge_enterprise_children",
            lambda *a, **kw: called.append(1))
        resp = client.delete(f"/api/v1/enterprises/{ent.id}")
        assert resp.status_code == 409
        assert not called


# ─── 6/7. work-orders / devices 同模式端点 ──────────────────────

class TestDeleteWorkorderException:
    @pytest.mark.parametrize("mk_exc,code", [
        (_integrity_err, 409), (_operational_err, 503), (_generic_err, 500),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code):
        from app.models.station import Station, StationStatus
        from app.models.workorder import WorkOrder
        s = client._sesh
        st = Station(name=f"站W{_u()}", code=f"SW{_u().upper()}",
                     status=StationStatus.NORMAL)
        s.add(st); s.commit(); s.refresh(st)
        wo = WorkOrder(id=f"WO-XH-{_u()}", station_id=st.id)
        s.add(wo); s.commit()

        _patch_purge(monkeypatch, "purge_workorder_children", mk_exc())
        resp = client.delete(f"/api/v1/work-orders/{wo.id}")
        assert resp.status_code == code, resp.text
        _assert_no_leak(str(resp.json().get("detail", "")))


class TestDeleteDeviceException:
    @pytest.mark.parametrize("mk_exc,code", [
        (_integrity_err, 409), (_operational_err, 503), (_generic_err, 500),
    ])
    def test_translated(self, client, monkeypatch, mk_exc, code):
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        st = Station(name=f"站D{_u()}", code=f"SD{_u().upper()}",
                     status=StationStatus.NORMAL)
        s.add(st); s.commit(); s.refresh(st)
        dev = Device(sn=f"SN-XH-{_u()}", name="桩", code=f"XD{_u().upper()}",
                     type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                     station_id=st.id)
        s.add(dev); s.commit(); s.refresh(dev)

        _patch_purge(monkeypatch, "purge_device_children", mk_exc())
        resp = client.delete(f"/api/v1/devices/{dev.id}")
        assert resp.status_code == code, resp.text
        _assert_no_leak(str(resp.json().get("detail", "")))
