"""
碳排放管理 API 单元测试

覆盖:
- 排放因子 CRUD
- 减排计算 (充电量×电网因子 vs 燃油基准)
- 碳减排明细查询
- 月度汇总报告
- 概览统计
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.carbon_emission import (
    CarbonEmissionFactor,
    CarbonReductionRecord,
    CarbonReductionSummary,
)
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_vehicle import EnterpriseVehicle, EnterpriseVehicleStatus


# ─── Fixtures ───

@pytest.fixture(scope="function")
def seed_enterprise_and_vehicle(client):
    """创建测试企业和车辆"""
    s: Session = client._sesh
    ent = Enterprise(
        name="测试物流公司",
        code="ENT-CARBON-001",
        status=EnterpriseStatus.ACTIVE,
    )
    s.add(ent)
    s.commit()
    s.refresh(ent)

    veh = EnterpriseVehicle(
        enterprise_id=ent.id,
        plate_number="京A12345",
        vin="LSJA1234567890123",
        status=EnterpriseVehicleStatus.ACTIVE,
    )
    s.add(veh)
    s.commit()
    s.refresh(veh)

    return {"enterprise": ent, "vehicle": veh}


@pytest.fixture(scope="function")
def seed_factors(client):
    """创建测试排放因子"""
    s: Session = client._sesh
    grid_factor = CarbonEmissionFactor(
        year=2026,
        region="全国",
        factor_type="grid",
        emission_factor=0.5703,
        source="生态环境部2022",
    )
    fuel_factor = CarbonEmissionFactor(
        year=2026,
        region="全国",
        factor_type="fuel",
        emission_factor=1.2110,
        source="GB/T 32150",
    )
    s.add_all([grid_factor, fuel_factor])
    s.commit()
    s.refresh(grid_factor)
    s.refresh(fuel_factor)
    return {"grid": grid_factor, "fuel": fuel_factor}


# ─── 排放因子 CRUD ───

class TestCarbonEmissionFactors:
    """碳排放因子 CRUD 测试"""

    def test_create_factor(self, client, seed_enterprise_and_vehicle):
        """测试创建排放因子"""
        resp = client.post("/api/v1/fleet/carbon/factors", json={
            "year": 2026,
            "region": "全国",
            "factor_type": "grid",
            "emission_factor": 0.5703,
            "source": "生态环境部",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["year"] == 2026
        assert data["region"] == "全国"
        assert data["factor_type"] == "grid"
        assert abs(data["emission_factor"] - 0.5703) < 0.0001

    def test_create_duplicate_factor_fails(self, client, seed_enterprise_and_vehicle):
        """测试重复创建因子应失败"""
        payload = {
            "year": 2026,
            "region": "华北",
            "factor_type": "grid",
            "emission_factor": 0.65,
        }
        client.post("/api/v1/fleet/carbon/factors", json=payload)
        resp = client.post("/api/v1/fleet/carbon/factors", json=payload)
        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    def test_list_factors(self, client, seed_enterprise_and_vehicle, seed_factors):
        """测试查询因子列表"""
        resp = client.get("/api/v1/fleet/carbon/factors", params={"year": 2026})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2
        types = [item["factor_type"] for item in data["items"]]
        assert "grid" in types
        assert "fuel" in types

    def test_list_factors_filter_type(self, client, seed_enterprise_and_vehicle, seed_factors):
        """测试按类型筛选因子"""
        resp = client.get("/api/v1/fleet/carbon/factors", params={"factor_type": "grid"})
        assert resp.status_code == 200
        for item in resp.json()["data"]["items"]:
            assert item["factor_type"] == "grid"

    def test_update_factor(self, client, seed_enterprise_and_vehicle, seed_factors):
        """测试更新因子"""
        fid = seed_factors["grid"].id
        resp = client.put(f"/api/v1/fleet/carbon/factors/{fid}", json={
            "emission_factor": 0.5800,
            "source": "更新后的来源",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert abs(data["emission_factor"] - 0.58) < 0.0001
        assert data["source"] == "更新后的来源"

    def test_delete_factor(self, client, seed_enterprise_and_vehicle, seed_factors):
        """测试删除因子"""
        fid = seed_factors["fuel"].id
        resp = client.delete(f"/api/v1/fleet/carbon/factors/{fid}")
        assert resp.status_code == 200
        # 再查应不存在
        resp2 = client.get(f"/api/v1/fleet/carbon/factors/{fid}")
        # GET by id not implemented as single endpoint, check list
        resp_list = client.get("/api/v1/fleet/carbon/factors", params={"factor_type": "fuel"})
        items = resp_list.json()["data"]["items"]
        assert all(item["id"] != fid for item in items)

    def test_update_nonexistent_factor(self, client):
        """测试更新不存在的因子"""
        resp = client.put("/api/v1/fleet/carbon/factors/99999", json={"emission_factor": 1.0})
        assert resp.status_code == 404

    def test_delete_nonexistent_factor(self, client):
        """测试删除不存在的因子"""
        resp = client.delete("/api/v1/fleet/carbon/factors/99999")
        assert resp.status_code == 404


# ─── 减排计算 ───

class TestCarbonReductionCalc:
    """减排计算测试"""

    def test_calculate_reduction(self, client, seed_enterprise_and_vehicle, seed_factors):
        """测试手动计算减排量"""
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        resp = client.post("/api/v1/fleet/carbon/calculate", json={
            "vehicle_id": veh_id,
            "record_date": "2026-07-15",
            "charge_energy_kwh": 100.0,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["vehicle_id"] == veh_id
        assert abs(data["charge_energy_kwh"] - 100.0) < 0.01
        assert data["carbon_reduction_kg"] > 0
        assert data["equivalent_fuel_saved_liters"] > 0

        # 验证计算逻辑: (1.2110 - 0.5703) * 100 = 64.07 kg
        expected_reduction = (1.2110 - 0.5703) * 100
        assert abs(data["carbon_reduction_kg"] - expected_reduction) < 0.5

        # 节油量: 100 * 0.56 = 56 L
        expected_fuel = 100 * 0.56
        assert abs(data["equivalent_fuel_saved_liters"] - expected_fuel) < 0.5

    def test_calculate_nonexistent_vehicle(self, client):
        """测试对不存在车辆计算减排量"""
        resp = client.post("/api/v1/fleet/carbon/calculate", json={
            "vehicle_id": 99999,
            "record_date": "2026-07-15",
            "charge_energy_kwh": 50.0,
        })
        assert resp.status_code == 404

    def test_calculate_invalid_date(self, client, seed_enterprise_and_vehicle):
        """测试日期格式错误"""
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        resp = client.post("/api/v1/fleet/carbon/calculate", json={
            "vehicle_id": veh_id,
            "record_date": "2026/07/15",
            "charge_energy_kwh": 50.0,
        })
        assert resp.status_code == 400

    def test_calculate_uses_default_factors(self, client, seed_enterprise_and_vehicle):
        """测试无因子时使用默认值"""
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        resp = client.post("/api/v1/fleet/carbon/calculate", json={
            "vehicle_id": veh_id,
            "record_date": "2026-03-01",
            "charge_energy_kwh": 200.0,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 应该有正的减排量 (默认因子下)
        assert data["carbon_reduction_kg"] > 0

    def test_reduction_calculation_formula(self):
        """测试减排计算公式 (单元测试)"""
        from app.api.v1.carbon_emission import calculate_reduction, DEFAULT_GRID_FACTOR, DEFAULT_FUEL_LITERS_PER_KWH, GASOLINE_CO2_PER_LITER
        from decimal import Decimal

        charge = Decimal("100")
        grid_f = Decimal("0.5703")
        fuel_f = Decimal("1.2110")  # 0.56 * 2.1625

        reduction, fuel_saved = calculate_reduction(charge, grid_f, fuel_f)
        # (1.2110 - 0.5703) * 100 = 64.07
        assert abs(float(reduction) - 64.07) < 0.01
        # 100 * 0.56 = 56
        assert abs(float(fuel_saved) - 56.0) < 0.01

    def test_reduction_zero_when_grid_higher(self):
        """测试当电网因子高于燃油基准时减排量为0"""
        from app.api.v1.carbon_emission import calculate_reduction
        from decimal import Decimal

        charge = Decimal("100")
        grid_f = Decimal("2.0")     # 高电网排放
        fuel_f = Decimal("1.0")     # 低燃油基准

        reduction, fuel_saved = calculate_reduction(charge, grid_f, fuel_f)
        assert reduction == Decimal("0")  # 减排量不应为负


# ─── 明细与概览 ───

class TestCarbonDetailsAndOverview:
    """碳减排明细和概览测试"""

    def _seed_records(self, client, enterprise_id, vehicle_id):
        """批量创建减排记录"""
        s: Session = client._sesh
        from datetime import date
        records = []
        for i, (d, kwh) in enumerate([
            ("2026-07-01", 50), ("2026-07-05", 80), ("2026-07-10", 120),
            ("2026-06-15", 60),
        ]):
            r = CarbonReductionRecord(
                vehicle_id=vehicle_id,
                enterprise_id=enterprise_id,
                record_date=date.fromisoformat(d),
                charge_energy_kwh=kwh,
                grid_factor=0.5703,
                fuel_factor=1.2110,
                carbon_reduction_kg=round((1.2110 - 0.5703) * kwh, 2),
                equivalent_fuel_saved_liters=round(0.56 * kwh, 2),
            )
            s.add(r)
            records.append(r)
        s.commit()
        for r in records:
            s.refresh(r)
        return records

    def test_carbon_details(self, client, seed_enterprise_and_vehicle):
        """测试查询减排明细"""
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        self._seed_records(client, ent_id, veh_id)

        resp = client.get("/api/v1/fleet/carbon/details", params={"enterprise_id": ent_id})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 4
        for item in data["items"]:
            assert item["enterprise_id"] == ent_id

    def test_carbon_details_date_filter(self, client, seed_enterprise_and_vehicle):
        """测试按日期筛选明细"""
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        self._seed_records(client, ent_id, veh_id)

        resp = client.get("/api/v1/fleet/carbon/details", params={
            "enterprise_id": ent_id,
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3  # 7月的3条

    def test_carbon_details_vehicle_filter(self, client, seed_enterprise_and_vehicle):
        """测试按车辆筛选明细"""
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        self._seed_records(client, ent_id, veh_id)

        resp = client.get("/api/v1/fleet/carbon/details", params={
            "enterprise_id": ent_id,
            "vehicle_id": veh_id,
        })
        assert resp.status_code == 200
        for item in resp.json()["data"]["items"]:
            assert item["vehicle_id"] == veh_id

    def test_carbon_overview(self, client, seed_enterprise_and_vehicle):
        """测试碳减排概览"""
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        self._seed_records(client, ent_id, veh_id)

        resp = client.get("/api/v1/fleet/carbon/overview", params={
            "enterprise_id": ent_id,
            "year": 2026,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_charge_kwh"] > 0
        assert data["total_reduction_kg"] > 0
        assert data["vehicle_count"] >= 1
        assert len(data["monthly_trend"]) == 12

    def test_carbon_overview_nonexistent_enterprise(self, client):
        """测试不存在企业的概览"""
        resp = client.get("/api/v1/fleet/carbon/overview", params={"enterprise_id": 99999})
        assert resp.status_code == 404


# ─── 月度汇总报告 ───

class TestCarbonReports:
    """月度报告测试"""

    def _seed_records_and_summary(self, client, enterprise_id, vehicle_id):
        """创建记录和汇总"""
        s: Session = client._sesh
        from datetime import date

        # 明细记录
        for d, kwh in [("2026-07-01", 100), ("2026-07-15", 200)]:
            s.add(CarbonReductionRecord(
                vehicle_id=vehicle_id,
                enterprise_id=enterprise_id,
                record_date=date.fromisoformat(d),
                charge_energy_kwh=kwh,
                grid_factor=0.5703,
                fuel_factor=1.2110,
                carbon_reduction_kg=round((1.2110 - 0.5703) * kwh, 2),
                equivalent_fuel_saved_liters=round(0.56 * kwh, 2),
            ))

        # 已有汇总
        s.add(CarbonReductionSummary(
            enterprise_id=enterprise_id,
            report_year=2026,
            report_month=7,
            total_charge_kwh=300,
            total_reduction_kg=round((1.2110 - 0.5703) * 300, 2),
            total_fuel_saved_liters=round(0.56 * 300, 2),
            vehicle_count=1,
            verified=False,
        ))
        s.commit()

    def test_get_reports(self, client, seed_enterprise_and_vehicle):
        """测试获取月度报告"""
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        self._seed_records_and_summary(client, ent_id, veh_id)

        resp = client.get("/api/v1/fleet/carbon/reports", params={
            "enterprise_id": ent_id,
            "year": 2026,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        jul = [d for d in data if d["report_month"] == 7]
        assert len(jul) == 1
        assert jul[0]["total_charge_kwh"] >= 300
        assert jul[0]["verified"] is False

    def test_get_reports_auto_aggregate(self, client, seed_enterprise_and_vehicle):
        """测试无汇总时自动从明细聚合"""
        s: Session = client._sesh
        from datetime import date
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id

        for d, kwh in [("2026-08-01", 50), ("2026-08-10", 70)]:
            s.add(CarbonReductionRecord(
                vehicle_id=veh_id,
                enterprise_id=ent_id,
                record_date=date.fromisoformat(d),
                charge_energy_kwh=kwh,
                grid_factor=0.5703,
                fuel_factor=1.2110,
                carbon_reduction_kg=round((1.2110 - 0.5703) * kwh, 2),
                equivalent_fuel_saved_liters=round(0.56 * kwh, 2),
            ))
        s.commit()

        resp = client.get("/api/v1/fleet/carbon/reports", params={
            "enterprise_id": ent_id,
            "year": 2026,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        aug = [d for d in data if d["report_month"] == 8]
        assert len(aug) == 1
        assert aug[0]["total_charge_kwh"] == 120  # 50+70

    def test_verify_report(self, client, seed_enterprise_and_vehicle):
        """测试审核月度报告"""
        ent_id = seed_enterprise_and_vehicle["enterprise"].id
        veh_id = seed_enterprise_and_vehicle["vehicle"].id
        self._seed_records_and_summary(client, ent_id, veh_id)

        s: Session = client._sesh
        summary = s.query(CarbonReductionSummary).filter(
            CarbonReductionSummary.enterprise_id == ent_id,
        ).first()

        resp = client.post(f"/api/v1/fleet/carbon/reports/{summary.id}/verify")
        assert resp.status_code == 200
        assert resp.json()["data"]["verified"] is True

    def test_verify_nonexistent_report(self, client):
        """测试审核不存在的报告"""
        resp = client.post("/api/v1/fleet/carbon/reports/99999/verify")
        assert resp.status_code == 404
