"""
企业车辆详情聚合 API 测试 - 车队管理

覆盖:
- GET /api/v1/enterprises/{enterprise_id}/vehicles/{vehicle_id}/profile —— 单车详情聚合

聚合字段:
- vehicle: 车辆基本信息
- charging_history: 充电订单列表(最近50条)
- v2g: {records, total_revenue} V2G收益记录与总收益
- carbon: 碳减排记录列表
- transactions: 企业账户流水列表
"""
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


# ========== Fixtures (与 test_enterprise_vehicles_patch.py 保持一致，保证可独立运行) ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_VPR") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, name="测试车队企业"):
    from app.models.enterprise import Enterprise
    db = test_db["session"]
    ent = Enterprise(name=name, code=_unique_code(), balance=10000.00)
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


@pytest.fixture
def test_db_local(test_db):
    """conftest 的 test_db 直通，便于在测试中拿到 session。"""
    return test_db


@pytest.fixture
def client(test_db):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: test_db["session"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers(client):
    return {"Authorization": f"Bearer {_login(client)}"}


def _bind_vehicle(client, enterprise_id, **overrides):
    """绑定车辆辅助函数，默认成功"""
    payload = {
        "plate_number": "豫A99999",
        "vin": "LSJU26938VF000001",
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json=payload,
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, f"绑定车辆失败: {resp.text}"
    return resp.json()["data"]


# ========== 聚合接口 ==========

class TestVehicleProfile:
    """车辆详情聚合接口测试"""

    def test_profile_with_data(self, client, test_db):
        """有数据时结构完整：vehicle + 各聚合段齐全"""
        ent = _create_enterprise(test_db)
        created = _bind_vehicle(
            client, ent.id, plate_number="豫P20001", vin="LSJU26938VF000011",
        )
        vid = created["id"]
        s = test_db["session"]

        # 充电订单（通过 plate_number 关联）
        from app.models.charging_order import (
            ChargingOrder, OrderStatus, OrderPaymentStatus,
        )
        s.add(ChargingOrder(
            order_no="CO_PROF_001", station_id=1, device_id=1,
            plate_number="豫P20001", vehicle_id=vid,
            charged_kwh=Decimal("50.00"),
            total_amount=Decimal("80.00"),
            paid_amount=Decimal("80.00"),
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
        ))

        # V2G 收益（通过 enterprise_id + vehicle_id 关联）
        from app.models.fleet_v2g import FleetV2GRevenue
        s.add(FleetV2GRevenue(
            enterprise_id=ent.id, vehicle_id=vid,
            record_date=date(2026, 7, 1),
            discharge_energy_kwh=Decimal("30.00"),
            total_revenue=Decimal("45.00"),
        ))
        s.add(FleetV2GRevenue(
            enterprise_id=ent.id, vehicle_id=vid,
            record_date=date(2026, 7, 2),
            discharge_energy_kwh=Decimal("20.00"),
            total_revenue=Decimal("25.00"),
        ))

        # 碳减排记录
        from app.models.carbon_emission import CarbonReductionRecord
        s.add(CarbonReductionRecord(
            enterprise_id=ent.id, vehicle_id=vid,
            record_date=date(2026, 7, 1),
            charge_energy_kwh=Decimal("50.00"),
            carbon_reduction_kg=Decimal("12.50"),
        ))

        # 账户流水
        from app.models.enterprise_transaction import (
            EnterpriseTransaction, TransactionType,
        )
        s.add(EnterpriseTransaction(
            enterprise_id=ent.id, vehicle_id=vid,
            type=TransactionType.CONSUME,
            amount=Decimal("80.00"), balance_after=Decimal("9920.00"),
        ))
        s.commit()

        resp = client.get(
            f"/api/v1/enterprises/{ent.id}/vehicles/{vid}/profile",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        # vehicle 基本信息
        assert data["vehicle"]["id"] == vid
        assert data["vehicle"]["vin"] == "LSJU26938VF000011"

        # 充电历史（list）
        assert isinstance(data["charging_history"], list)
        assert len(data["charging_history"]) == 1
        assert data["charging_history"][0]["order_no"] == "CO_PROF_001"

        # V2G（dict：记录 + 总收益）
        assert isinstance(data["v2g"], dict)
        assert isinstance(data["v2g"]["records"], list)
        assert len(data["v2g"]["records"]) == 2
        assert data["v2g"]["total_revenue"] == pytest.approx(70.0)

        # 碳排放（list）
        assert isinstance(data["carbon"], list)
        assert len(data["carbon"]) == 1
        assert data["carbon"][0]["carbon_reduction_kg"] == pytest.approx(12.5)

        # 流水（list）
        assert isinstance(data["transactions"], list)
        assert len(data["transactions"]) == 1
        assert data["transactions"][0]["amount"] == pytest.approx(80.0)

    def test_profile_empty_data(self, client, test_db):
        """无关联数据时各聚合段为空数组/v2g 空结构，且 200"""
        ent = _create_enterprise(test_db)
        created = _bind_vehicle(
            client, ent.id, plate_number="豫P20002", vin="LSJU26938VF000021",
        )
        vid = created["id"]

        resp = client.get(
            f"/api/v1/enterprises/{ent.id}/vehicles/{vid}/profile",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert data["vehicle"]["id"] == vid
        assert data["charging_history"] == []
        assert data["v2g"]["records"] == []
        assert data["v2g"]["total_revenue"] == 0
        assert data["carbon"] == []
        assert data["transactions"] == []

    def test_profile_vehicle_not_found(self, client, test_db):
        """车辆不存在 -> 404"""
        ent = _create_enterprise(test_db)
        resp = client.get(
            f"/api/v1/enterprises/{ent.id}/vehicles/99999/profile",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_profile_wrong_enterprise(self, client, test_db):
        """跨企业越权查询 -> 404（查询带 enterprise_id 约束）"""
        ent1 = _create_enterprise(test_db, name="企业甲")
        ent2 = _create_enterprise(test_db, name="企业乙")
        # 车辆挂在 ent1
        created = _bind_vehicle(
            client, ent1.id, plate_number="豫P20003", vin="LSJU26938VF000031",
        )
        # 用 ent2 的 URL 查询
        resp = client.get(
            f"/api/v1/enterprises/{ent2.id}/vehicles/{created['id']}/profile",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404

    def test_profile_enterprise_not_found(self, client, test_db):
        """企业不存在 -> 404"""
        resp = client.get(
            "/api/v1/enterprises/99999/vehicles/1/profile",
            headers=_auth_headers(client),
        )
        assert resp.status_code == 404
