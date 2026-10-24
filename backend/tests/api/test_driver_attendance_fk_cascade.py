"""司机考勤 FK 级联清理（卡 97a891bc 同族）

FleetDriverAttendance.driver_id NOT NULL 且无 ondelete、FleetDriver 模型亦无
指向考勤的 relationship，两处删司机路径（delete_driver 单删 / 企业整删 bulk
delete）均不清理考勤 → SQLite 留孤儿行、生产 PG IntegrityError 裸 500。

服务层显式清理（fk_cascade 范式，不动模型/迁移）：
- purge_driver_children 在 db.delete(driver) 前清考勤；
- purge_enterprise_children 在 fleet_drivers bulk delete 前批量清考勤。
"""
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient


def _u():
    return _uuid.uuid4().hex[:8]


def _create_enterprise(db):
    from app.models.enterprise import Enterprise
    ent = Enterprise(name=f"考勤FK企业{_u()}", code=f"ATT{_u().upper()}")
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


def _seed_driver_with_attendance(db, ent):
    """构造 带考勤记录的司机（零余额零流水），返回 (driver, attendance)。"""
    from app.models.fleet_driver import DriverStatus, FleetDriver, LicenseType
    from app.models.fleet_driver_attendance import FleetDriverAttendance

    driver = FleetDriver(
        enterprise_id=ent.id, name=f"考勤司机{_u()}",
        phone=f"139{_u()[:8]}", license_no=f"LIC{_u()}",
        license_type=LicenseType.C1, status=DriverStatus.ACTIVE,
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)
    att = FleetDriverAttendance(
        driver_id=driver.id, date="2026-09-05",
        shift_type="day", hours=8.0, status="normal",
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return driver, att


@pytest.fixture
def client(test_db):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: test_db["session"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth_headers(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


class TestDeleteDriverAttendanceCascade:
    def test_delete_driver_clears_attendance(self, client, test_db):
        """删除带考勤的司机（零余额零流水）→ 考勤孤儿被清理。"""
        from app.models.fleet_driver import FleetDriver
        from app.models.fleet_driver_attendance import FleetDriverAttendance

        s = test_db["session"]
        ent = _create_enterprise(s)
        driver, att = _seed_driver_with_attendance(s, ent)
        driver_id, att_id = driver.id, att.id

        resp = client.delete(
            f"/api/v1/fleet/drivers/{driver_id}", headers=_auth_headers(client)
        )
        assert resp.status_code == 200, resp.text
        s.expire_all()

        assert s.query(FleetDriverAttendance).filter(
            FleetDriverAttendance.driver_id == driver_id).count() == 0
        assert s.query(FleetDriverAttendance).filter(
            FleetDriverAttendance.id == att_id).count() == 0
        assert s.query(FleetDriver).filter(
            FleetDriver.id == driver.id).count() == 0

    def test_delete_driver_without_attendance_still_ok(self, client, test_db):
        """无考勤司机删除路径不受 purge 影响。"""
        from app.models.fleet_driver import FleetDriver

        s = test_db["session"]
        ent = _create_enterprise(s)
        driver, _ = _seed_driver_with_attendance(s, ent)
        driver_id = driver.id
        from app.models.fleet_driver_attendance import FleetDriverAttendance
        s.query(FleetDriverAttendance).filter(
            FleetDriverAttendance.driver_id == driver_id).delete()
        s.commit()

        resp = client.delete(
            f"/api/v1/fleet/drivers/{driver_id}", headers=_auth_headers(client)
        )
        assert resp.status_code == 200, resp.text
        s.expire_all()
        assert s.query(FleetDriver).filter(
            FleetDriver.id == driver.id).count() == 0

    def test_enterprise_purge_clears_attendance(self, client, test_db):
        """企业整删：带考勤的司机随企业删除 → 考勤行与司机行都被清理。"""
        from app.models.fleet_driver import FleetDriver
        from app.models.fleet_driver_attendance import FleetDriverAttendance

        s = test_db["session"]
        ent = _create_enterprise(s)
        driver, att = _seed_driver_with_attendance(s, ent)
        driver_id, att_id = driver.id, att.id

        resp = client.delete(
            f"/api/v1/enterprises/{ent.id}", headers=_auth_headers(client)
        )
        assert resp.status_code == 200, resp.text
        s.expire_all()

        assert s.query(FleetDriverAttendance).filter(
            FleetDriverAttendance.driver_id == driver_id).count() == 0
        assert s.query(FleetDriver).filter(
            FleetDriver.id == driver_id).count() == 0
