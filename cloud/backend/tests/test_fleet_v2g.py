"""
V2G 车队调度 API 测试 - Phase44
覆盖: 充放电计划CRUD、收益记录/查询、调度状态概览、调度执行记录
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """每个测试使用独立数据库"""
    pass


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _login():
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


def _create_enterprise(code="ENT_V2G_01"):
    from app.models.enterprise import Enterprise
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        ent = Enterprise(name=f"V2G测试企业_{code}", code=code, balance=10000.00)
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.id
    finally:
        db.close()


def _create_vehicle(enterprise_id, plate="豫A-V2G-001", vin="LSVAU2V2G00000001"):
    resp = client.post(
        f"/api/v1/enterprises/{enterprise_id}/vehicles",
        json={
            "plate_number": plate,
            "vin": vin,
            "driver_name": "测试司机",
            "driver_phone": "13800001234",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


def _create_device():
    """创建一个V2G充电桩设备用于测试调度记录"""
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.station import Station, StationStatus
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        station = Station(name="V2G测试站", code="STA_V2G_01", address="V2G测试地址", status=StationStatus.NORMAL)
        db.add(station)
        db.commit()
        db.refresh(station)
        device = Device(
            sn="SN-V2G-001",
            name="V2G桩#1",
            code="V2G001",
            type=DeviceType.V2G_CHARGER,
            status=DeviceStatus.ONLINE,
            station_id=station.id,
            rated_power=120.0,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return device.id
    finally:
        db.close()


def _create_dispatch_log(device_id, dispatch_type="discharge", status="completed"):
    from app.models.v2g_dispatch import V2GDispatchLog
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        log = V2GDispatchLog(
            device_id=device_id,
            dispatch_type=dispatch_type,
            target_power_kw=50.0,
            actual_power_kw=48.5,
            status=status,
            start_at=datetime.now(timezone.utc),
            end_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log.id
    finally:
        db.close()


def _plan_payload(enterprise_id, vehicle_id, plan_date=None):
    """构建计划创建请求体"""
    if plan_date is None:
        plan_date = date(2026, 7, 21)
    return {
        "enterprise_id": enterprise_id,
        "vehicle_id": vehicle_id,
        "plan_date": plan_date.isoformat(),
        "planned_charge_start": "2026-07-21T02:00:00",
        "planned_charge_end": "2026-07-21T06:00:00",
        "planned_discharge_start": "2026-07-21T10:00:00",
        "planned_discharge_end": "2026-07-21T14:00:00",
        "target_soc_min": 20.0,
        "target_soc_max": 80.0,
    }


def _revenue_payload(enterprise_id, vehicle_id, record_date=None):
    """构建收益记录请求体"""
    if record_date is None:
        record_date = date(2026, 7, 21)
    return {
        "enterprise_id": enterprise_id,
        "vehicle_id": vehicle_id,
        "record_date": record_date.isoformat(),
        "discharge_energy_kwh": 50.5,
        "discharge_revenue": 150.00,
        "grid_response_count": 3,
        "peak_shaving_kwh": 30.0,
        "valley_filling_kwh": 20.0,
        "total_revenue": 200.00,
    }


# ======================================================================
# 充放电计划 CRUD
# ======================================================================

class TestV2GPlanCRUD:
    """V2G充放电计划增删查改"""

    def test_create_plan(self):
        """创建V2G充放电计划"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        resp = client.post(
            "/api/v1/fleet/v2g/plans",
            json=_plan_payload(ent_id, veh_id),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enterprise_id"] == ent_id
        assert data["vehicle_id"] == veh_id
        assert data["plan_date"] == "2026-07-21"
        assert data["status"] == "scheduled"
        assert data["target_soc_min"] == 20.0
        assert data["target_soc_max"] == 80.0

    def test_create_plan_invalid_enterprise(self):
        """创建计划-企业不存在"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        payload = _plan_payload(ent_id, veh_id)
        payload["enterprise_id"] = 999999
        resp = client.post(
            "/api/v1/fleet/v2g/plans",
            json=payload,
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_create_plan_invalid_vehicle(self):
        """创建计划-车辆不存在"""
        ent_id = _create_enterprise()
        payload = _plan_payload(ent_id, 999999)
        resp = client.post(
            "/api/v1/fleet/v2g/plans",
            json=payload,
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_list_plans(self):
        """查询计划列表"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        # 创建2个计划
        for d in [date(2026, 7, 21), date(2026, 7, 22)]:
            client.post(
                "/api/v1/fleet/v2g/plans",
                json=_plan_payload(ent_id, veh_id, d),
                headers=_auth_headers(),
            )

        resp = client.get(
            f"/api/v1/fleet/v2g/plans?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_plans_filter_vehicle(self):
        """按车辆过滤计划"""
        ent_id = _create_enterprise()
        veh1 = _create_vehicle(ent_id, plate="豫A001", vin="LSVAU2V2GTEST0001")
        veh2 = _create_vehicle(ent_id, plate="豫A002", vin="LSVAU2V2GTEST0002")

        client.post("/api/v1/fleet/v2g/plans", json=_plan_payload(ent_id, veh1), headers=_auth_headers())
        client.post("/api/v1/fleet/v2g/plans", json=_plan_payload(ent_id, veh2), headers=_auth_headers())

        resp = client.get(
            f"/api/v1/fleet/v2g/plans?enterprise_id={ent_id}&vehicle_id={veh1}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["vehicle_id"] == veh1

    def test_list_plans_filter_date(self):
        """按日期过滤计划"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        client.post("/api/v1/fleet/v2g/plans", json=_plan_payload(ent_id, veh_id, date(2026, 7, 21)), headers=_auth_headers())
        client.post("/api/v1/fleet/v2g/plans", json=_plan_payload(ent_id, veh_id, date(2026, 7, 22)), headers=_auth_headers())

        resp = client.get(
            f"/api/v1/fleet/v2g/plans?enterprise_id={ent_id}&plan_date=2026-07-21",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["plan_date"] == "2026-07-21"

    def test_list_plans_empty(self):
        """空计划列表"""
        ent_id = _create_enterprise("ENT_EMPTY")
        resp = client.get(
            f"/api/v1/fleet/v2g/plans?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_get_plan_detail(self):
        """获取单个计划详情"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        create_resp = client.post(
            "/api/v1/fleet/v2g/plans",
            json=_plan_payload(ent_id, veh_id),
            headers=_auth_headers(),
        )
        plan_id = create_resp.json()["data"]["id"]

        resp = client.get(
            f"/api/v1/fleet/v2g/plans/{plan_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == plan_id
        assert data["enterprise_id"] == ent_id

    def test_get_plan_not_found(self):
        """获取不存在的计划"""
        resp = client.get(
            "/api/v1/fleet/v2g/plans/99999",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_update_plan_status(self):
        """更新计划状态"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        create_resp = client.post(
            "/api/v1/fleet/v2g/plans",
            json=_plan_payload(ent_id, veh_id),
            headers=_auth_headers(),
        )
        plan_id = create_resp.json()["data"]["id"]

        # 更新为充电中
        resp = client.put(
            f"/api/v1/fleet/v2g/plans/{plan_id}/status?new_status=charging",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "charging"

        # 更新为已完成
        resp2 = client.put(
            f"/api/v1/fleet/v2g/plans/{plan_id}/status?new_status=completed",
            headers=_auth_headers(),
        )
        assert resp2.status_code == 200
        assert resp2.json()["data"]["status"] == "completed"

    def test_update_plan_invalid_status(self):
        """更新计划状态-无效值"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        create_resp = client.post(
            "/api/v1/fleet/v2g/plans",
            json=_plan_payload(ent_id, veh_id),
            headers=_auth_headers(),
        )
        plan_id = create_resp.json()["data"]["id"]

        resp = client.put(
            f"/api/v1/fleet/v2g/plans/{plan_id}/status?new_status=invalid_state",
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_update_plan_status_not_found(self):
        """更新不存在计划的状态"""
        resp = client.put(
            "/api/v1/fleet/v2g/plans/99999/status?new_status=completed",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


# ======================================================================
# 收益管理
# ======================================================================

class TestV2GRevenue:
    """V2G放电收益记录与查询"""

    def test_record_revenue(self):
        """记录V2G放电收益"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        resp = client.post(
            "/api/v1/fleet/v2g/revenue",
            json=_revenue_payload(ent_id, veh_id),
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enterprise_id"] == ent_id
        assert data["vehicle_id"] == veh_id
        assert data["discharge_energy_kwh"] == 50.5
        assert data["discharge_revenue"] == 150.0
        assert data["grid_response_count"] == 3
        assert data["peak_shaving_kwh"] == 30.0
        assert data["valley_filling_kwh"] == 20.0
        assert data["total_revenue"] == 200.0

    def test_record_revenue_invalid_vehicle(self):
        """记录收益-车辆不存在"""
        ent_id = _create_enterprise()
        resp = client.post(
            "/api/v1/fleet/v2g/revenue",
            json=_revenue_payload(ent_id, 999999),
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_list_revenue(self):
        """查询收益列表"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        for d in [date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 21)]:
            client.post(
                "/api/v1/fleet/v2g/revenue",
                json=_revenue_payload(ent_id, veh_id, d),
                headers=_auth_headers(),
            )

        resp = client.get(
            f"/api/v1/fleet/v2g/revenue?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_list_revenue_filter_vehicle(self):
        """按车辆过滤收益"""
        ent_id = _create_enterprise()
        veh1 = _create_vehicle(ent_id, plate="豫R001", vin="LSVAU2V2GTEST0003")
        veh2 = _create_vehicle(ent_id, plate="豫R002", vin="LSVAU2V2GTEST0004")

        client.post("/api/v1/fleet/v2g/revenue", json=_revenue_payload(ent_id, veh1), headers=_auth_headers())
        client.post("/api/v1/fleet/v2g/revenue", json=_revenue_payload(ent_id, veh2), headers=_auth_headers())

        resp = client.get(
            f"/api/v1/fleet/v2g/revenue?enterprise_id={ent_id}&vehicle_id={veh1}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["vehicle_id"] == veh1

    def test_list_revenue_date_range(self):
        """按日期范围过滤收益"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        for d in [date(2026, 7, 15), date(2026, 7, 18), date(2026, 7, 21)]:
            client.post(
                "/api/v1/fleet/v2g/revenue",
                json=_revenue_payload(ent_id, veh_id, d),
                headers=_auth_headers(),
            )

        resp = client.get(
            f"/api/v1/fleet/v2g/revenue?enterprise_id={ent_id}&start_date=2026-07-17&end_date=2026-07-22",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2  # 7/18 and 7/21

    def test_list_revenue_empty(self):
        """空收益列表"""
        ent_id = _create_enterprise("ENT_REV_EMPTY")
        resp = client.get(
            f"/api/v1/fleet/v2g/revenue?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0


# ======================================================================
# 状态概览
# ======================================================================

class TestV2GStatus:
    """V2G调度状态概览"""

    def test_status_empty(self):
        """空状态概览"""
        ent_id = _create_enterprise()
        resp = client.get(
            f"/api/v1/fleet/v2g/status?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enterprise_id"] == ent_id
        assert data["plan_status_counts"] == {}
        assert data["recent_plans"] == []
        assert data["revenue_summary"]["total_revenue"] == 0
        assert data["revenue_summary"]["total_records"] == 0

    def test_status_with_plans(self):
        """有计划数据的状态概览"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        # 创建3个计划
        plan_ids = []
        for d in [date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 21)]:
            r = client.post(
                "/api/v1/fleet/v2g/plans",
                json=_plan_payload(ent_id, veh_id, d),
                headers=_auth_headers(),
            )
            plan_ids.append(r.json()["data"]["id"])

        # 更新一个为charging, 一个为completed
        client.put(f"/api/v1/fleet/v2g/plans/{plan_ids[0]}/status?new_status=completed", headers=_auth_headers())
        client.put(f"/api/v1/fleet/v2g/plans/{plan_ids[1]}/status?new_status=charging", headers=_auth_headers())

        resp = client.get(
            f"/api/v1/fleet/v2g/status?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["plan_status_counts"].get("scheduled", 0) == 1
        assert data["plan_status_counts"].get("charging", 0) == 1
        assert data["plan_status_counts"].get("completed", 0) == 1
        assert len(data["recent_plans"]) == 3

    def test_status_with_revenue(self):
        """有收益数据的状态概览"""
        ent_id = _create_enterprise()
        veh_id = _create_vehicle(ent_id)

        client.post("/api/v1/fleet/v2g/revenue", json=_revenue_payload(ent_id, veh_id, date(2026, 7, 20)), headers=_auth_headers())
        client.post("/api/v1/fleet/v2g/revenue", json=_revenue_payload(ent_id, veh_id, date(2026, 7, 21)), headers=_auth_headers())

        resp = client.get(
            f"/api/v1/fleet/v2g/status?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["revenue_summary"]["total_records"] == 2
        assert data["revenue_summary"]["total_revenue"] == 400.0  # 200 * 2


# ======================================================================
# 调度执行记录 (复用 v2g_dispatch_logs)
# ======================================================================

class TestV2GRecords:
    """V2G调度执行记录查询"""

    def test_list_records_empty(self):
        """空调度记录列表"""
        ent_id = _create_enterprise()
        resp = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_records_with_data(self):
        """有数据的调度记录列表"""
        ent_id = _create_enterprise()
        dev_id = _create_device()

        # 创建多条调度日志
        _create_dispatch_log(dev_id, "charge", "completed")
        _create_dispatch_log(dev_id, "discharge", "completed")
        _create_dispatch_log(dev_id, "standby", "pending")

        resp = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_list_records_filter_type(self):
        """按调度类型过滤记录"""
        ent_id = _create_enterprise()
        dev_id = _create_device()

        _create_dispatch_log(dev_id, "charge", "completed")
        _create_dispatch_log(dev_id, "discharge", "completed")
        _create_dispatch_log(dev_id, "discharge", "completed")

        resp = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}&dispatch_type=discharge",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        for item in data["items"]:
            assert item["dispatch_type"] == "discharge"

    def test_list_records_pagination(self):
        """调度记录分页"""
        ent_id = _create_enterprise()
        dev_id = _create_device()

        # 创建5条记录
        for i in range(5):
            _create_dispatch_log(dev_id, "discharge", "completed")

        # 第1页
        resp = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}&page=1&page_size=2",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2

        # 第3页
        resp2 = client.get(
            f"/api/v1/fleet/v2g/records?enterprise_id={ent_id}&page=3&page_size=2",
            headers=_auth_headers(),
        )
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert len(data2["items"]) == 1  # 5 = 2+2+1
