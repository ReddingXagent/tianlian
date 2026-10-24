"""
车队概览 API 测试 - Phase43 车队管理

覆盖:
- GET /api/v1/fleet/overview?enterprise_id=X —— 概览聚合
- 企业不存在(404) / 缺参(422) / 空数据 / 车辆数 / 累计消费聚合 / 最近交易截断 / 企业隔离
- 扩展指标: 信用额度 / 车辆状态分布 / V2G总收益 / 碳减排总量
"""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


# ========== Fixtures ==========

_counter = [0]


def _unique_code(prefix: str = "ENT_O") -> str:
    _counter[0] += 1
    return f"{prefix}{_counter[0]}"


def _create_enterprise(test_db, name="测试车队企业", balance=10000.00, credit_limit=5000.00):
    """创建测试企业，返回 Enterprise 对象"""
    from app.models.enterprise import Enterprise, EnterpriseStatus
    db = test_db["session"]
    ent = Enterprise(
        name=name,
        code=_unique_code(),
        balance=Decimal(str(balance)),
        credit_limit=Decimal(str(credit_limit)),
        status=EnterpriseStatus.ACTIVE,
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


def _add_vehicle(test_db, enterprise_id, vin, plate_number="豫A12345", status=None):
    from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus
    db = test_db["session"]
    v = EnterpriseVehicle(
        enterprise_id=enterprise_id,
        plate_number=plate_number,
        vin=vin,
        status=status or EnterpriseVehicleStatus.ACTIVE,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _add_transaction(test_db, enterprise_id, type_, amount, balance_after=0):
    from app.models.enterprise_transaction import EnterpriseTransaction, TransactionType
    db = test_db["session"]
    tx = EnterpriseTransaction(
        enterprise_id=enterprise_id,
        type=TransactionType(type_),
        amount=Decimal(str(amount)),
        balance_after=Decimal(str(balance_after)),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _add_v2g_revenue(test_db, enterprise_id, vehicle_id, revenue=100.0, discharge_kwh=50.0):
    from app.models.fleet_v2g import FleetV2GRevenue
    import datetime
    db = test_db["session"]
    rec = FleetV2GRevenue(
        enterprise_id=enterprise_id,
        vehicle_id=vehicle_id,
        record_date=datetime.date.today(),
        discharge_energy_kwh=Decimal(str(discharge_kwh)),
        discharge_revenue=Decimal(str(revenue)),
        total_revenue=Decimal(str(revenue)),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _add_carbon_reduction(test_db, enterprise_id, vehicle_id, reduction_kg=200.0):
    from app.models.carbon_emission import CarbonReductionRecord
    import datetime
    db = test_db["session"]
    rec = CarbonReductionRecord(
        vehicle_id=vehicle_id,
        enterprise_id=enterprise_id,
        record_date=datetime.date.today(),
        charge_energy_kwh=Decimal("100.00"),
        carbon_reduction_kg=Decimal(str(reduction_kg)),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@pytest.fixture
def enterprise_id(test_db):
    """每个测试自动创建一个企业，返回 id"""
    return _create_enterprise(test_db).id


@pytest.fixture
def client(test_db):
    """构造绑定到 test_db 的 TestClient"""
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


def _overview(client, enterprise_id):
    return client.get(
        f"/api/v1/fleet/overview?enterprise_id={enterprise_id}",
        headers=_auth_headers(client),
    )


# ========== 概览基础测试 ==========

class TestFleetOverview:
    """车队概览聚合测试"""

    def test_overview_basic(self, client, enterprise_id):
        """基础字段：企业信息 + 空数据默认值"""
        resp = _overview(client, enterprise_id)
        assert resp.status_code == 200
        data = resp.json()["data"]
        ent = data["enterprise"]
        assert ent["id"] == enterprise_id
        assert ent["name"] == "测试车队企业"
        assert ent["balance"] == 10000.0
        assert ent["status"] == "active"
        assert "code" in ent and ent["code"]
        assert data["total_vehicles"] == 0
        assert data["total_charged_kwh"] == 0.0
        assert data["total_spent"] == 0.0
        assert data["recent_transactions"] == []

    def test_overview_enterprise_not_found(self, client):
        """企业不存在 -> 404"""
        resp = _overview(client, 99999)
        assert resp.status_code == 404

    def test_overview_missing_enterprise_id(self, client):
        """缺少必填参数 enterprise_id -> 422"""
        resp = client.get("/api/v1/fleet/overview", headers=_auth_headers(client))
        assert resp.status_code == 422

    def test_overview_total_vehicles(self, client, test_db, enterprise_id):
        """车辆数统计正确"""
        _add_vehicle(test_db, enterprise_id, vin="VIN_OV_001")
        _add_vehicle(test_db, enterprise_id, vin="VIN_OV_002", plate_number="豫B22222")
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert data["total_vehicles"] == 2

    def test_overview_charged_and_spent_aggregation(self, client, test_db, enterprise_id):
        """累计消费聚合：仅 consume 计入，recharge/refund 不计入"""
        _add_transaction(test_db, enterprise_id, "recharge", 1000)
        _add_transaction(test_db, enterprise_id, "consume", 200)
        _add_transaction(test_db, enterprise_id, "consume", 350)
        _add_transaction(test_db, enterprise_id, "refund", 50)
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        # total_charged_kwh = sum(consume.amount) = 200 + 350
        assert data["total_charged_kwh"] == 550.0
        # total_spent == total_charged_kwh
        assert data["total_spent"] == 550.0

    def test_overview_recent_transactions_limit(self, client, test_db, enterprise_id):
        """最近交易最多返回5条，且按 id 降序"""
        ids = []
        for i in range(7):
            tx = _add_transaction(test_db, enterprise_id, "consume", 10)
            ids.append(tx.id)
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert len(data["recent_transactions"]) == 5
        returned_ids = [t["id"] for t in data["recent_transactions"]]
        # 仅最近5条
        assert returned_ids == sorted(ids, reverse=True)[:5]
        # 降序排列
        assert returned_ids == sorted(returned_ids, reverse=True)
        # 字段完整
        first = data["recent_transactions"][0]
        for key in ("id", "type", "amount", "balance_after", "remark", "created_at"):
            assert key in first

    def test_overview_isolated_by_enterprise(self, client, test_db):
        """不同企业的数据互不影响"""
        ent1 = _create_enterprise(test_db, name="企业甲", balance=5000)
        ent2 = _create_enterprise(test_db, name="企业乙", balance=8000)
        _add_vehicle(test_db, ent1.id, vin="VIN_ISO_1")
        _add_transaction(test_db, ent1.id, "consume", 100)
        # ent2 无任何数据
        resp = _overview(client, ent2.id)
        data = resp.json()["data"]
        assert data["total_vehicles"] == 0
        assert data["total_charged_kwh"] == 0.0
        assert data["recent_transactions"] == []
        # ent1 的概览正常
        resp1 = _overview(client, ent1.id)
        data1 = resp1.json()["data"]
        assert data1["total_vehicles"] == 1
        assert data1["total_charged_kwh"] == 100.0


# ========== 扩展指标测试 ==========

class TestFleetOverviewExtendedMetrics:
    """车队概览扩展指标测试"""

    def test_overview_credit_limit(self, client, enterprise_id):
        """信用额度返回正确"""
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        ent = data["enterprise"]
        assert ent["credit_limit"] == 5000.0
        # credit_balance = balance + credit_limit = 10000 + 5000
        assert ent["credit_balance"] == 15000.0

    def test_overview_credit_limit_zero(self, client, test_db):
        """信用额度为 0 时正常返回"""
        ent = _create_enterprise(test_db, name="零信用企业", balance=1000, credit_limit=0)
        resp = _overview(client, ent.id)
        data = resp.json()["data"]
        assert data["enterprise"]["credit_limit"] == 0.0
        assert data["enterprise"]["credit_balance"] == 1000.0

    def test_overview_vehicle_status_distribution(self, client, test_db, enterprise_id):
        """车辆状态分布统计正确"""
        from app.models.enterprise_vehicle import EnterpriseVehicleStatus as VS
        _add_vehicle(test_db, enterprise_id, vin="VS001", status=VS.ACTIVE)
        _add_vehicle(test_db, enterprise_id, vin="VS002", status=VS.ACTIVE)
        _add_vehicle(test_db, enterprise_id, vin="VS003", status=VS.MAINTENANCE)
        _add_vehicle(test_db, enterprise_id, vin="VS004", status=VS.RETIRED)

        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        dist = data["vehicle_status_distribution"]
        assert dist.get("active") == 2
        assert dist.get("maintenance") == 1
        assert dist.get("retired") == 1

    def test_overview_vehicle_status_distribution_empty(self, client, enterprise_id):
        """无车辆时状态分布为空字典"""
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert data["vehicle_status_distribution"] == {}

    def test_overview_v2g_revenue(self, client, test_db, enterprise_id):
        """V2G 总收益汇总"""
        v1 = _add_vehicle(test_db, enterprise_id, vin="V2G001")
        v2 = _add_vehicle(test_db, enterprise_id, vin="V2G002")
        _add_v2g_revenue(test_db, enterprise_id, v1.id, revenue=150.50)
        _add_v2g_revenue(test_db, enterprise_id, v2.id, revenue=300.00)

        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert data["total_v2g_revenue"] == 450.50

    def test_overview_v2g_revenue_empty(self, client, enterprise_id):
        """无 V2G 数据时收益为 0"""
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert data["total_v2g_revenue"] == 0.0

    def test_overview_carbon_reduction(self, client, test_db, enterprise_id):
        """碳减排总量汇总"""
        v1 = _add_vehicle(test_db, enterprise_id, vin="CR001")
        v2 = _add_vehicle(test_db, enterprise_id, vin="CR002")
        _add_carbon_reduction(test_db, enterprise_id, v1.id, reduction_kg=500.0)
        _add_carbon_reduction(test_db, enterprise_id, v2.id, reduction_kg=300.5)

        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert data["total_carbon_reduction_kg"] == 800.5

    def test_overview_carbon_reduction_empty(self, client, enterprise_id):
        """无碳减排数据时为 0"""
        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        assert data["total_carbon_reduction_kg"] == 0.0

    def test_overview_all_metrics_together(self, client, test_db, enterprise_id):
        """综合场景: 车辆 + 交易 + V2G + 碳减排 同时存在"""
        from app.models.enterprise_vehicle import EnterpriseVehicleStatus as VS
        v1 = _add_vehicle(test_db, enterprise_id, vin="ALL001", status=VS.ACTIVE)
        v2 = _add_vehicle(test_db, enterprise_id, vin="ALL002", status=VS.MAINTENANCE)
        _add_transaction(test_db, enterprise_id, "consume", 500)
        _add_v2g_revenue(test_db, enterprise_id, v1.id, revenue=200.0)
        _add_carbon_reduction(test_db, enterprise_id, v1.id, reduction_kg=100.0)
        _add_carbon_reduction(test_db, enterprise_id, v2.id, reduction_kg=50.0)

        resp = _overview(client, enterprise_id)
        data = resp.json()["data"]
        # 车辆
        assert data["total_vehicles"] == 2
        assert data["vehicle_status_distribution"]["active"] == 1
        assert data["vehicle_status_distribution"]["maintenance"] == 1
        # 交易
        assert data["total_charged_kwh"] == 500.0
        # V2G
        assert data["total_v2g_revenue"] == 200.0
        # 碳减排
        assert data["total_carbon_reduction_kg"] == 150.0
        # 信用额度
        assert data["enterprise"]["credit_limit"] == 5000.0
