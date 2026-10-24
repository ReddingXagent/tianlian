"""
定价管理 V2 测试

覆盖:
- TimeSlotDefinition CRUD (尖/峰/平/谷时段)
- EnergyPrice CRUD (充电费)
- ServiceFeePrice CRUD (服务费)
- ParkingPrice CRUD (停车费)
- OccupancyFeePrice CRUD (占桩费)
- ReservationFeePrice CRUD (预约费)
- 订单费用估算联动
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.api.v1.pricing_management import router
from app.models.pricing_v2 import (
    TimeSlotDefinition, PeriodType,
    EnergyPrice, ServiceFeePrice, ParkingPrice,
    OccupancyFeePrice, ReservationFeePrice,
)
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole
import bcrypt


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def pricing_client():
    """独立测试环境: 全新 SQLite + 全模型建表 + pricing_management 路由"""
    import os, uuid
    db_path = f"/tmp/tianlian_pricing_test_{uuid.uuid4().hex}.db"

    from sqlalchemy import create_engine, BigInteger as SA_BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(SA_BigInteger, "sqlite")
    def _compile_bigint_sqlite(element, compiler, **kw):
        return "INTEGER"

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables from models
    import app.models  # register all models
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()

    # Seed: admin user
    session.add(User(
        username="admin",
        password_hash=bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode(),
        role=UserRole.ADMIN,
        status="active",
    ))
    # Seed: station
    station = Station(name="测试电站", code="STA001", address="北京市", status=StationStatus.NORMAL)
    session.add(station)
    session.commit()
    session.refresh(station)

    # Build FastAPI app
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: session

    # Override auth dependency
    from app.api.v1.auth import get_current_user
    admin_user = session.query(User).filter(User.username == "admin").first()
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with TestClient(app) as c:
        c._sesh = session
        c._station_id = station.id
        yield c

    session.close()
    engine.dispose()
    os.unlink(db_path)


# ═══════════════════════════════════════════════════════════════
# 1. TimeSlotDefinition CRUD
# ═══════════════════════════════════════════════════════════════

class TestTimeSlotCRUD:

    def test_create(self, pricing_client):
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "尖时段",
            "period_type": "peak",
            "start_time": "10:00",
            "end_time": "12:00",
            "description": "上午尖峰",
            "is_active": True,
            "sort_order": 1,
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "尖时段"
        assert data["period_type"] == "peak"
        assert data["start_time"] == "10:00"
        assert data["end_time"] == "12:00"
        assert data["is_active"] is True
        assert "id" in data

    def test_list(self, pricing_client):
        # Create 3 slots
        for i, (pt, name) in enumerate([("peak", "尖"), ("flat", "平"), ("valley", "谷")]):
            pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
                "name": name, "period_type": pt,
                "start_time": f"{10+i*2}:00", "end_time": f"{12+i*2}:00",
                "sort_order": i,
            })
        r = pricing_client.get("/api/v1/pricing/mgmt/time-slots")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 3
        assert len(data["items"]) >= 3

    def test_get_by_id(self, pricing_client):
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "峰时段", "period_type": "shoulder",
            "start_time": "08:00", "end_time": "10:00",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.get(f"/api/v1/pricing/mgmt/time-slots/{item_id}")
        assert r2.status_code == 200
        assert r2.json()["data"]["name"] == "峰时段"

    def test_get_404(self, pricing_client):
        r = pricing_client.get("/api/v1/pricing/mgmt/time-slots/9999")
        assert r.status_code == 404

    def test_update(self, pricing_client):
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "平时段", "period_type": "flat",
            "start_time": "06:00", "end_time": "08:00",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/time-slots/{item_id}", json={
            "name": "平段更新",
            "is_active": False,
        })
        assert r2.status_code == 200
        d = r2.json()["data"]
        assert d["name"] == "平段更新"
        assert d["is_active"] is False

    def test_delete(self, pricing_client):
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "谷时段", "period_type": "valley",
            "start_time": "00:00", "end_time": "06:00",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.delete(f"/api/v1/pricing/mgmt/time-slots/{item_id}")
        assert r2.status_code == 200
        r3 = pricing_client.get(f"/api/v1/pricing/mgmt/time-slots/{item_id}")
        assert r3.status_code == 404

    def test_invalid_period_type(self, pricing_client):
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "test", "period_type": "invalid",
            "start_time": "00:00", "end_time": "06:00",
        })
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# 2. EnergyPrice CRUD
# ═══════════════════════════════════════════════════════════════

class TestEnergyPriceCRUD:

    def _create_slot(self, client):
        r = client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "尖", "period_type": "peak",
            "start_time": "10:00", "end_time": "12:00",
        })
        return r.json()["data"]["id"]

    def test_create(self, pricing_client):
        sid = pricing_client._station_id
        slot_id = self._create_slot(pricing_client)
        r = pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id,
            "price_per_kwh": 1.2345,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["price_per_kwh"] == 1.2345
        assert d["station_id"] == sid

    def test_list_and_filter(self, pricing_client):
        sid = pricing_client._station_id
        slot_id = self._create_slot(pricing_client)
        pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id,
            "price_per_kwh": 0.8, "effective_date": "2026-01-01",
        })
        r = pricing_client.get(f"/api/v1/pricing/mgmt/energy?station_id={sid}")
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1

    def test_update_and_delete(self, pricing_client):
        sid = pricing_client._station_id
        slot_id = self._create_slot(pricing_client)
        r = pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id,
            "price_per_kwh": 0.5, "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/energy/{item_id}", json={
            "price_per_kwh": 0.99,
        })
        assert r2.json()["data"]["price_per_kwh"] == 0.99
        r3 = pricing_client.delete(f"/api/v1/pricing/mgmt/energy/{item_id}")
        assert r3.status_code == 200
        assert pricing_client.get(f"/api/v1/pricing/mgmt/energy/{item_id}").status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. ServiceFeePrice CRUD
# ═══════════════════════════════════════════════════════════════

class TestServiceFeeCRUD:

    def test_create(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "app",
            "fee_type": "fixed", "fee_value": 2.50,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["fee_value"] == 2.50
        assert d["user_type"] == "app"
        assert d["fee_type"] == "fixed"

    def test_invalid_user_type(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "invalid_type",
            "fee_type": "fixed", "fee_value": 1.0,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 400

    def test_invalid_fee_type(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "app",
            "fee_type": "invalid", "fee_value": 1.0,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 400

    def test_update_and_delete(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "card",
            "fee_type": "percent", "fee_value": 0.12,
            "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/service-fee/{item_id}", json={
            "fee_value": 0.15,
        })
        assert r2.json()["data"]["fee_value"] == 0.15
        pricing_client.delete(f"/api/v1/pricing/mgmt/service-fee/{item_id}")
        assert pricing_client.get(f"/api/v1/pricing/mgmt/service-fee/{item_id}").status_code == 404


# ═══════════════════════════════════════════════════════════════
# 4. ParkingPrice CRUD
# ═══════════════════════════════════════════════════════════════

class TestParkingPriceCRUD:

    def test_create(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/parking", json={
            "station_id": sid,
            "free_minutes": 30,
            "hourly_rate": 5.00,
            "daily_cap": 50.00,
            "enable_night_rate": True,
            "night_rate": 2.00,
            "night_start": "22:00",
            "night_end": "06:00",
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["free_minutes"] == 30
        assert d["hourly_rate"] == 5.00
        assert d["daily_cap"] == 50.00
        assert d["enable_night_rate"] is True
        assert d["night_start"] == "22:00"

    def test_list_filter(self, pricing_client):
        sid = pricing_client._station_id
        pricing_client.post("/api/v1/pricing/mgmt/parking", json={
            "station_id": sid,
            "hourly_rate": 3.00,
            "effective_date": "2026-01-01",
        })
        r = pricing_client.get(f"/api/v1/pricing/mgmt/parking?station_id={sid}")
        assert r.json()["data"]["total"] >= 1

    def test_update_and_delete(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/parking", json={
            "station_id": sid,
            "hourly_rate": 4.00,
            "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/parking/{item_id}", json={
            "hourly_rate": 6.00,
            "free_minutes": 60,
        })
        d = r2.json()["data"]
        assert d["hourly_rate"] == 6.00
        assert d["free_minutes"] == 60
        pricing_client.delete(f"/api/v1/pricing/mgmt/parking/{item_id}")
        assert pricing_client.get(f"/api/v1/pricing/mgmt/parking/{item_id}").status_code == 404


# ═══════════════════════════════════════════════════════════════
# 5. OccupancyFeePrice CRUD
# ═══════════════════════════════════════════════════════════════

class TestOccupancyFeeCRUD:

    def test_create(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/occupancy", json={
            "station_id": sid,
            "grace_minutes": 15,
            "rate_per_minute": 0.50,
            "max_fee": 100.00,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["grace_minutes"] == 15
        assert d["rate_per_minute"] == 0.50
        assert d["max_fee"] == 100.00

    def test_update(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/occupancy", json={
            "station_id": sid,
            "rate_per_minute": 0.30,
            "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/occupancy/{item_id}", json={
            "grace_minutes": 30,
            "max_fee": 200.00,
        })
        d = r2.json()["data"]
        assert d["grace_minutes"] == 30
        assert d["max_fee"] == 200.00

    def test_delete(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/occupancy", json={
            "station_id": sid,
            "rate_per_minute": 0.20,
            "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        pricing_client.delete(f"/api/v1/pricing/mgmt/occupancy/{item_id}")
        assert pricing_client.get(f"/api/v1/pricing/mgmt/occupancy/{item_id}").status_code == 404


# ═══════════════════════════════════════════════════════════════
# 5.5 生效期重叠校验 (卡 a311a5b0, 缺陷1 上游预防)
#     同维度生效期重叠 → 409; 不相交/不同维度/更新自身/失效行 → 放行
# ═══════════════════════════════════════════════════════════════

class TestEffectiveOverlapValidation:

    def _slot(self, pricing_client):
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "峰", "period_type": "peak",
            "start_time": "10:00", "end_time": "12:00",
        })
        return r.json()["data"]["id"]

    def test_energy_overlap_create_returns_409(self, pricing_client):
        """同 (station, slot) 重叠生效期(均 open-ended)→ 409, 明确 message。"""
        sid = pricing_client._station_id
        slot_id = self._slot(pricing_client)
        base = {"station_id": sid, "slot_id": slot_id,
                "price_per_kwh": 0.8, "effective_date": "2026-01-01"}
        assert pricing_client.post("/api/v1/pricing/mgmt/energy", json=base).status_code == 200
        r = pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            **base, "price_per_kwh": 1.0, "effective_date": "2026-02-01",
        })
        assert r.status_code == 409
        assert "重叠" in r.text  # 我们的 409 明确 message

    def test_energy_adjacent_non_overlap_allowed(self, pricing_client):
        """旧定价 expire(01-31) < 新 effective(02-01) → 区间不相交 → 允许(200)。"""
        sid = pricing_client._station_id
        slot_id = self._slot(pricing_client)
        pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id, "price_per_kwh": 0.8,
            "effective_date": "2026-01-01", "expire_date": "2026-01-31",
        })
        r = pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id, "price_per_kwh": 1.0,
            "effective_date": "2026-02-01",
        })
        assert r.status_code == 200

    def test_service_fee_dimension_is_station_plus_user_type(self, pricing_client):
        """维度 = (station, user_type): 同维度重叠 → 409; 不同 user_type → 200。"""
        sid = pricing_client._station_id
        pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "app", "fee_type": "percent",
            "fee_value": 0.3, "effective_date": "2026-01-01",
        })
        r_same = pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "app", "fee_type": "percent",
            "fee_value": 0.5, "effective_date": "2026-02-01",
        })
        assert r_same.status_code == 409
        r_diff = pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "card", "fee_type": "percent",
            "fee_value": 0.4, "effective_date": "2026-02-01",
        })
        assert r_diff.status_code == 200

    def test_update_self_not_flagged_as_overlap(self, pricing_client):
        """更新自身(同 id 排除)即使生效期未变也不误判重叠 → 200。"""
        sid = pricing_client._station_id
        slot_id = self._slot(pricing_client)
        r = pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id, "price_per_kwh": 0.8,
            "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/energy/{item_id}", json={
            "price_per_kwh": 0.9,
        })
        assert r2.status_code == 200
        assert r2.json()["data"]["price_per_kwh"] == 0.9

    def test_inactive_existing_row_does_not_conflict(self, pricing_client):
        """既有 is_active=False 行不参与 .first() 选取, 新 active 行与之"重叠"也放行(200)。"""
        sid = pricing_client._station_id
        slot_id = self._slot(pricing_client)
        pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id, "price_per_kwh": 0.8,
            "effective_date": "2026-01-01", "is_active": False,
        })
        r = pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id, "price_per_kwh": 1.0,
            "effective_date": "2026-02-01",
        })
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# 6. ReservationFeePrice CRUD
# ═══════════════════════════════════════════════════════════════

class TestReservationFeeCRUD:

    def test_create(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/reservation", json={
            "station_id": sid,
            "deposit_amount": 50.00,
            "reservation_policy": "slot_based",
            "fee_amount": 5.00,
            "no_show_penalty": 20.00,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["deposit_amount"] == 50.00
        assert d["reservation_policy"] == "slot_based"
        assert d["no_show_penalty"] == 20.00

    def test_invalid_policy(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/reservation", json={
            "station_id": sid,
            "reservation_policy": "invalid",
            "fee_amount": 5.0,
            "deposit_amount": 10.0,
            "no_show_penalty": 0,
            "effective_date": "2026-01-01",
        })
        assert r.status_code == 400

    def test_update_and_delete(self, pricing_client):
        sid = pricing_client._station_id
        r = pricing_client.post("/api/v1/pricing/mgmt/reservation", json={
            "station_id": sid,
            "reservation_policy": "flat",
            "deposit_amount": 30.0,
            "fee_amount": 3.0,
            "no_show_penalty": 10.0,
            "effective_date": "2026-01-01",
        })
        item_id = r.json()["data"]["id"]
        r2 = pricing_client.put(f"/api/v1/pricing/mgmt/reservation/{item_id}", json={
            "no_show_penalty": 50.00,
        })
        assert r2.json()["data"]["no_show_penalty"] == 50.00
        pricing_client.delete(f"/api/v1/pricing/mgmt/reservation/{item_id}")
        assert pricing_client.get(f"/api/v1/pricing/mgmt/reservation/{item_id}").status_code == 404


# ═══════════════════════════════════════════════════════════════
# 7. 订单费用估算联动
# ═══════════════════════════════════════════════════════════════

class TestOrderEstimate:

    def test_estimate_with_data(self, pricing_client):
        """设置各类定价数据后估算费用"""
        sid = pricing_client._station_id

        # 时段
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "尖", "period_type": "peak",
            "start_time": "10:00", "end_time": "12:00",
        })
        slot_id = r.json()["data"]["id"]

        # 充电费
        pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id,
            "price_per_kwh": 0.80,
            "effective_date": "2020-01-01",
        })

        # 服务费
        pricing_client.post("/api/v1/pricing/mgmt/service-fee", json={
            "station_id": sid, "user_type": "app",
            "fee_type": "percent", "fee_value": 0.50,
            "effective_date": "2020-01-01",
        })

        # 停车费
        pricing_client.post("/api/v1/pricing/mgmt/parking", json={
            "station_id": sid,
            "free_minutes": 30,
            "hourly_rate": 5.00,
            "daily_cap": 50.00,
            "effective_date": "2020-01-01",
        })

        # 占桩费
        pricing_client.post("/api/v1/pricing/mgmt/occupancy", json={
            "station_id": sid,
            "grace_minutes": 15,
            "rate_per_minute": 0.50,
            "max_fee": 100.00,
            "effective_date": "2020-01-01",
        })

        # 估算
        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": sid,
            "user_type": "app",
            "energy_kwh": 30.0,
            "charging_minutes": 60,
            "parking_minutes": 90,
            "occupancy_minutes": 30,
        })
        assert r.status_code == 200
        d = r.json()["data"]
        # energy: avg_price=0.80 * 30 = 24.0
        assert d["energy_cost"] == pytest.approx(24.0, abs=0.01)
        # service: percent 0.50 * 30 = 15.0
        assert d["service_fee"] == pytest.approx(15.0, abs=0.01)
        # parking: (90-30)=60min=1h * 5.0 = 5.0
        assert d["parking_fee"] == pytest.approx(5.0, abs=0.01)
        # occupancy: (30-15)=15min * 0.50 = 7.50
        assert d["occupancy_fee"] == pytest.approx(7.50, abs=0.01)
        # total
        assert d["total"] == pytest.approx(51.50, abs=0.01)

    def test_estimate_empty(self, pricing_client):
        """无定价数据时估算费用应为0"""
        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": pricing_client._station_id,
            "user_type": "app",
            "energy_kwh": 50.0,
            "charging_minutes": 120,
            "parking_minutes": 120,
            "occupancy_minutes": 60,
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["energy_cost"] == 0.0
        assert d["service_fee"] == 0.0
        assert d["parking_fee"] == 0.0
        assert d["occupancy_fee"] == 0.0
        assert d["total"] == 0.0

    def test_estimate_daily_cap(self, pricing_client):
        """停车费日封顶测试"""
        sid = pricing_client._station_id
        pricing_client.post("/api/v1/pricing/mgmt/parking", json={
            "station_id": sid,
            "free_minutes": 0,
            "hourly_rate": 10.00,
            "daily_cap": 30.00,
            "effective_date": "2020-01-01",
        })
        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": sid,
            "energy_kwh": 0,
            "parking_minutes": 600,  # 10h * 10 = 100 > 30 cap
        })
        d = r.json()["data"]
        assert d["parking_fee"] == pytest.approx(30.0, abs=0.01)

    def test_estimate_occupancy_cap(self, pricing_client):
        """占桩费封顶测试"""
        sid = pricing_client._station_id
        pricing_client.post("/api/v1/pricing/mgmt/occupancy", json={
            "station_id": sid,
            "grace_minutes": 0,
            "rate_per_minute": 1.00,
            "max_fee": 50.00,
            "effective_date": "2020-01-01",
        })
        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": sid,
            "energy_kwh": 0,
            "occupancy_minutes": 200,  # 200 * 1 = 200 > 50 cap
        })
        d = r.json()["data"]
        assert d["occupancy_fee"] == pytest.approx(50.0, abs=0.01)

    def test_estimate_free_minutes(self, pricing_client):
        """停车免费时长测试"""
        sid = pricing_client._station_id
        pricing_client.post("/api/v1/pricing/mgmt/parking", json={
            "station_id": sid,
            "free_minutes": 60,
            "hourly_rate": 5.00,
            "effective_date": "2020-01-01",
        })
        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": sid,
            "energy_kwh": 0,
            "parking_minutes": 30,  # < 60 free → 0
        })
        d = r.json()["data"]
        assert d["parking_fee"] == 0.0

    def test_estimate_grace_period(self, pricing_client):
        """占桩宽限时间测试"""
        sid = pricing_client._station_id
        pricing_client.post("/api/v1/pricing/mgmt/occupancy", json={
            "station_id": sid,
            "grace_minutes": 30,
            "rate_per_minute": 0.50,
            "effective_date": "2020-01-01",
        })
        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": sid,
            "energy_kwh": 0,
            "occupancy_minutes": 20,  # < 30 grace → 0
        })
        d = r.json()["data"]
        assert d["occupancy_fee"] == 0.0

    def test_estimate_uses_biz_today_for_effective_price(self, pricing_client, monkeypatch):
        """凌晨窗口: effective_date=业务今天的电价应计入估算 (卡 48bc65fe)。

        云端 UTC 容器 date.today()=UTC 昨天 < effective_date(业务今天) →
        旧实现漏掉该电价 (energy_cost=0); today_in_biz_tz() 取业务今天 → 计入。
        """
        from datetime import date as _date
        from app.api.v1.pricing_management import order_estimate as oe_mod

        biz_today = _date(2026, 8, 7)
        utc_today = _date(2026, 8, 6)
        sid = pricing_client._station_id

        # 时段 (EnergyPrice.slot_id 必填)
        r = pricing_client.post("/api/v1/pricing/mgmt/time-slots", json={
            "name": "峰", "period_type": "peak",
            "start_time": "10:00", "end_time": "12:00",
        })
        slot_id = r.json()["data"]["id"]
        # 电价: 业务今天才生效 (effective_date = biz_today)
        pricing_client.post("/api/v1/pricing/mgmt/energy", json={
            "station_id": sid, "slot_id": slot_id,
            "price_per_kwh": 0.80,
            "effective_date": str(biz_today),
        })

        monkeypatch.setattr(oe_mod, "today_in_biz_tz", lambda: biz_today, raising=False)

        class _FrozenDate(_date):
            @classmethod
            def today(cls):
                return utc_today
        monkeypatch.setattr(oe_mod, "date", _FrozenDate, raising=False)

        r = pricing_client.post("/api/v1/pricing/mgmt/order-estimate", json={
            "station_id": sid, "user_type": "app",
            "energy_kwh": 30.0, "charging_minutes": 60,
            "parking_minutes": 0, "occupancy_minutes": 0,
        })
        assert r.status_code == 200
        d = r.json()["data"]
        # avg_price=0.80 * 30 = 24.0 (旧实现 date.today()<effective_date → 0)
        assert d["energy_cost"] == pytest.approx(24.0, abs=0.01), d


# ═══════════════════════════════════════════════════════════════
# 异常路径加固 (卡 f3e5633d): _parse_date / _parse_time 非法输入 → 400
# ═══════════════════════════════════════════════════════════════

def test_parking_create_invalid_effective_date_400(pricing_client):
    """非法 effective_date → _parse_date 抛 HTTPException 400, 不裸奔 500。"""
    sid = pricing_client._station_id
    r = pricing_client.post("/api/v1/pricing/mgmt/parking", json={
        "station_id": sid,
        "hourly_rate": 5.00,
        "effective_date": "not-a-date",
    })
    assert r.status_code == 400


def test_parking_create_invalid_night_start_400(pricing_client):
    """非法 night_start → _parse_time 抛 HTTPException 400。"""
    sid = pricing_client._station_id
    r = pricing_client.post("/api/v1/pricing/mgmt/parking", json={
        "station_id": sid,
        "hourly_rate": 5.00,
        "enable_night_rate": True,
        "night_start": "25时",  # 非 HH:MM
        "night_end": "06:00",
        "effective_date": "2026-01-01",
    })
    assert r.status_code == 400
