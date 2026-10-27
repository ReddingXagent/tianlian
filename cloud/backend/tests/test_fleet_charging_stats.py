"""
车队充电统计 API 测试

覆盖:
- 单车充电统计（有数据/空数据/日期筛选）
- 车队级充电汇总（有数据/空数据/排行+场站分布）
"""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _seed_enterprise(db, name="测试车队", code="FLEET001"):
    from app.models.enterprise import Enterprise, EnterpriseStatus
    ent = Enterprise(name=name, code=code, balance=10000, status=EnterpriseStatus.ACTIVE)
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


def _seed_vehicle(db, ent_id, plate="京A12345", vin="LSVAU2189N2000001"):
    from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus
    v = EnterpriseVehicle(
        enterprise_id=ent_id,
        plate_number=plate,
        vin=vin,
        status=EnterpriseVehicleStatus.ACTIVE,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _seed_station(db, name="测试充电站", code="ST001"):
    from app.models.station import Station, StationStatus
    s = Station(name=name, code=code, status=StationStatus.NORMAL)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_charging_order(db, vehicle_id=None, plate_number=None, station_id=1,
                         kwh=50.0, amount=80.0, days_ago=0, order_no=None):
    from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus
    start = datetime.now(timezone.utc) - timedelta(days=days_ago)
    o = ChargingOrder(
        order_no=order_no or f"CO{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        station_id=station_id,
        device_id=1,
        vehicle_id=vehicle_id,
        plate_number=plate_number,
        start_time=start,
        end_time=start + timedelta(hours=1),
        duration_minutes=60,
        charged_kwh=Decimal(str(kwh)),
        electricity_fee=Decimal(str(amount * 0.6)),
        service_fee=Decimal(str(amount * 0.3)),
        total_amount=Decimal(str(amount)),
        paid_amount=Decimal(str(amount)),
        order_status=OrderStatus.COMPLETED,
        payment_status=OrderPaymentStatus.PAID,
    )
    db.add(o)
    db.commit()
    return o


# ========== 单车充电统计 ==========

class TestVehicleChargingStats:

    def test_empty_data_returns_zero_structure(self):
        """无数据返回零值结构"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db)
            vehicle = _seed_vehicle(db, ent.id)
            ent_id = ent.id
            vehicle_id = vehicle.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/vehicles/{vehicle_id}/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_orders"] == 0
        assert data["summary"]["total_kwh"] == 0.0
        assert data["summary"]["total_amount"] == 0.0
        assert data["summary"]["avg_kwh_per_order"] == 0.0
        assert data["monthly_trend"] == []

    def test_with_data(self):
        """有数据返回正确统计"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db)
            vehicle = _seed_vehicle(db, ent.id)
            _seed_charging_order(db, vehicle_id=vehicle.id, plate_number=vehicle.plate_number,
                                 kwh=50, amount=80, days_ago=10)
            _seed_charging_order(db, vehicle_id=vehicle.id, plate_number=vehicle.plate_number,
                                 kwh=30, amount=48, days_ago=40)
            ent_id = ent.id
            vehicle_id = vehicle.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/vehicles/{vehicle_id}/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_orders"] == 2
        assert data["summary"]["total_kwh"] == 80.0
        assert data["summary"]["total_amount"] == 128.0
        assert data["summary"]["avg_kwh_per_order"] == 40.0
        assert data["summary"]["avg_amount_per_order"] == 64.0
        # 月度趋势应有数据
        assert len(data["monthly_trend"]) >= 1

    def test_date_filter(self):
        """日期筛选"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db)
            vehicle = _seed_vehicle(db, ent.id)
            # 近期订单
            _seed_charging_order(db, vehicle_id=vehicle.id, plate_number=vehicle.plate_number,
                                 kwh=50, amount=80, days_ago=5)
            # 较早订单（应被过滤）
            _seed_charging_order(db, vehicle_id=vehicle.id, plate_number=vehicle.plate_number,
                                 kwh=100, amount=160, days_ago=200)
            ent_id = ent.id
            vehicle_id = vehicle.id
        finally:
            db.close()

        # 只查近30天
        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/vehicles/{vehicle_id}/charging-stats",
            headers=_auth_headers(),
            params={"start_date": start},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_orders"] == 1
        assert data["summary"]["total_kwh"] == 50.0

    def test_vehicle_not_found(self):
        """车辆不存在返回404"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db)
            ent_id = ent.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/vehicles/99999/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_enterprise_not_found(self):
        """企业不存在返回404"""
        resp = client.get(
            "/api/v1/enterprises/99999/vehicles/1/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


# ========== 车队级充电汇总 ==========

class TestEnterpriseChargingStats:

    def test_empty_data_returns_zero_structure(self):
        """无数据返回零值结构"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db)
            ent_id = ent.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_orders"] == 0
        assert data["summary"]["total_kwh"] == 0.0
        assert data["active_vehicles"] == 0
        assert data["top_vehicles"] == []
        assert data["station_distribution"] == []

    def test_no_vehicles(self):
        """企业无车辆返回零值结构"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db, name="空车队", code="EMPTY001")
            ent_id = ent.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_orders"] == 0
        assert data["active_vehicles"] == 0
        assert data["top_vehicles"] == []

    def test_with_data(self):
        """有数据返回汇总+排行+场站分布"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db)
            v1 = _seed_vehicle(db, ent.id, plate="京A11111", vin="LSVAU2189N2000011")
            v2 = _seed_vehicle(db, ent.id, plate="京A22222", vin="LSVAU2189N2000022")
            station = _seed_station(db)

            # v1 充两次
            _seed_charging_order(db, vehicle_id=v1.id, plate_number=v1.plate_number,
                                 station_id=station.id, kwh=100, amount=150, days_ago=5)
            _seed_charging_order(db, vehicle_id=v1.id, plate_number=v1.plate_number,
                                 station_id=station.id, kwh=50, amount=75, days_ago=15)
            # v2 充一次
            _seed_charging_order(db, vehicle_id=v2.id, plate_number=v2.plate_number,
                                 station_id=station.id, kwh=80, amount=120, days_ago=10)
            ent_id = ent.id
            v1_id = v1.id
            v2_id = v2.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        # 汇总
        assert data["summary"]["total_orders"] == 3
        assert data["summary"]["total_kwh"] == 230.0
        assert data["summary"]["total_amount"] == 345.0
        assert data["active_vehicles"] == 2

        # 排行: v1(150kWh) > v2(80kWh)
        assert len(data["top_vehicles"]) == 2
        assert data["top_vehicles"][0]["vehicle_id"] == v1_id
        assert data["top_vehicles"][0]["charged_kwh"] == 150.0
        assert data["top_vehicles"][1]["vehicle_id"] == v2_id

        # 场站分布
        assert len(data["station_distribution"]) == 1
        assert data["station_distribution"][0]["charged_kwh"] == 230.0

    def test_date_filter(self):
        """日期筛选排除旧数据"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db, name="日期筛选车队", code="DATE001")
            v1 = _seed_vehicle(db, ent.id, plate="京B11111", vin="LSVAU2189N2000031")
            _seed_charging_order(db, vehicle_id=v1.id, plate_number=v1.plate_number,
                                 kwh=100, amount=150, days_ago=5)
            _seed_charging_order(db, vehicle_id=v1.id, plate_number=v1.plate_number,
                                 kwh=200, amount=300, days_ago=300)
            ent_id = ent.id
        finally:
            db.close()

        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/charging-stats",
            headers=_auth_headers(),
            params={"start_date": start},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["total_orders"] == 1
        assert data["summary"]["total_kwh"] == 100.0

    def test_enterprise_not_found(self):
        """企业不存在返回404"""
        resp = client.get(
            "/api/v1/enterprises/99999/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_no_500_on_empty(self):
        """确保无数据时不返回500"""
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            ent = _seed_enterprise(db, name="零值测试", code="ZERO001")
            _seed_vehicle(db, ent.id, plate="京C00001", vin="LSVAU2189N2000041")
            ent_id = ent.id
        finally:
            db.close()

        resp = client.get(
            f"/api/v1/enterprises/{ent_id}/charging-stats",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
