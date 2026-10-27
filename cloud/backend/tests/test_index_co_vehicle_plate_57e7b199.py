"""卡 57e7b199: charging_orders 补 vehicle_id/plate_number 索引.

模型 __table_args__ 原先对 vehicle_id/plate_number 零索引, 多个热点查询全表扫:
fleet 充电统计 (vehicle_id 聚合)、车辆详情订单历史 (vehicle_id)、
占位费重叠单匹配 (_match_charging_order 按 plate_number)、
车牌维度订单查询/报表 (plate_number)。

覆盖:
1. 结构: Base.metadata.create_all (SQLite) 后 inspect 验证两索引存在且列正确。
2. 功能回归: 单车充电统计端点带 plate 订单正常聚合 (fleet 查询面)。
3. 功能回归: _match_charging_order 能按 plate 命中带时间窗的订单 (占位费查询面)。
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.models.charging_order import ChargingOrder, OrderStatus, OrderPaymentStatus

client = TestClient(app)


# ═══════════════════════════════════════════════════════════
# 1. 结构: create_all 后两索引存在
# ═══════════════════════════════════════════════════════════

def test_indexes_exist_on_metadata_create_all():
    engine = create_engine("sqlite://")
    ChargingOrder.__table__.create(engine)
    try:
        idx = {i["name"]: i["column_names"] for i in inspect(engine).get_indexes("charging_orders")}
        assert idx.get("idx_co_vehicle") == ["vehicle_id"]
        assert idx.get("idx_co_plate") == ["plate_number"]
    finally:
        engine.dispose()


def test_indexes_declared_not_unique():
    """普通二级索引, 非唯一 (两列均可空且无唯一语义)。"""
    engine = create_engine("sqlite://")
    ChargingOrder.__table__.create(engine)
    try:
        idx = {i["name"]: i for i in inspect(engine).get_indexes("charging_orders")}
        assert not idx["idx_co_vehicle"]["unique"]
        assert not idx["idx_co_plate"]["unique"]
    finally:
        engine.dispose()


# ═══════════════════════════════════════════════════════════
# 2/3. 功能回归 (走全局 test_db fixture 的应用库)
# ═══════════════════════════════════════════════════════════

def _login():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def test_vehicle_charging_stats_with_plate_order(test_db):
    """单车充电统计: vehicle_id 关联的带 plate 订单正常聚合 (fleet 查询面)。"""
    from app.core.database import SessionLocal
    from app.models.enterprise import Enterprise, EnterpriseStatus
    from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus

    db = SessionLocal()
    try:
        ent = Enterprise(name="索引车队", code="IDX57001",
                         balance=10000, status=EnterpriseStatus.ACTIVE)
        db.add(ent); db.commit(); db.refresh(ent)
        v = EnterpriseVehicle(enterprise_id=ent.id, plate_number="京B57001",
                              vin="LSVIDX57001", status=EnterpriseVehicleStatus.ACTIVE)
        db.add(v); db.commit(); db.refresh(v)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        db.add(ChargingOrder(
            order_no=f"IDX57{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            station_id=1, device_id=1, vehicle_id=v.id, plate_number=v.plate_number,
            start_time=start, end_time=start + timedelta(hours=1), duration_minutes=60,
            charged_kwh=Decimal("50"), electricity_fee=Decimal("48"),
            service_fee=Decimal("24"), total_amount=Decimal("80"),
            paid_amount=Decimal("80"),
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
        ))
        db.commit()
        ent_id, vid = ent.id, v.id
    finally:
        db.close()

    resp = client.get(
        f"/api/v1/enterprises/{ent_id}/vehicles/{vid}/charging-stats",
        headers={"Authorization": f"Bearer {_login()}"},
    )
    assert resp.status_code == 200
    summary = resp.json()["data"]["summary"]
    assert summary["total_orders"] == 1
    assert summary["total_kwh"] == 50.0


def test_match_charging_order_hits_plate_indexed_query(test_db):
    """占位费匹配: plate_number + station + 时间窗相交命中订单 (占位费查询面)。"""
    from app.core.database import SessionLocal
    from app.models.parking_event import OccupancyEvent
    from app.services import occupancy_fee_service as svc

    db = SessionLocal()
    try:
        enter = datetime(2026, 8, 26, 2, 0)  # naive-UTC
        o = ChargingOrder(
            order_no=f"IDX57P{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            station_id=57, device_id=1, vehicle_id=None, plate_number="京C57002",
            start_time=enter + timedelta(minutes=10),
            end_time=enter + timedelta(minutes=70),
            duration_minutes=60,
            charged_kwh=Decimal("10"), electricity_fee=Decimal("6"),
            service_fee=Decimal("4"), total_amount=Decimal("10"),
            paid_amount=Decimal("10"),
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
        )
        db.add(o); db.commit()
        e = OccupancyEvent(
            plate_number="京C57002", station_id=57,
            enter_at=enter, exit_at=enter + timedelta(hours=2),
        )
        db.add(e); db.commit()
        got = svc._match_charging_order(db, e)
        assert got is not None and got.id == o.id
    finally:
        db.close()
