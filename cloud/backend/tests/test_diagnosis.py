"""
智能诊断 API 测试
覆盖: device diagnosis + batch diagnosis + history
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    pass


@pytest.fixture
def auth_token(test_db):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


@pytest.fixture
def test_station(test_db):
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(name="诊断测试站点", code="DIAG-STATION-001", status=StationStatus.NORMAL)
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="DIAG-DEV-001", name="诊断测试设备",
        type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
        station_id=test_station.id, protocol_type=ProtocolType.MODBUS_RTU
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestDiagnosisAPI:

    def test_diagnosis_requires_auth(self):
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        assert client.post("/api/v1/diagnosis/device", json={"device_id": 1}).status_code in (401, 403)

    def test_device_diagnosis(self, auth_token, test_device):
        resp = client.post("/api/v1/diagnosis/device", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "include_history": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_batch_diagnosis(self, auth_token, test_station):
        resp = client.post("/api/v1/diagnosis/batch", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "station_id": test_station.id,
        })
        assert resp.status_code == 200

    def test_diagnosis_history(self, auth_token, test_device):
        resp = client.get(f"/api/v1/diagnosis/history/{test_device.id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code in (200, 404)

    def test_device_diagnosis_stats_count_equivalence(self, test_db, auth_token, test_device):
        """卡 d9076d31: count 下推后统计口径与旧全量口径逐项等价。

        构造混合 status/level 告警 + 混合 status 工单, 断言响应数字与手工计算一致:
        - 告警: total=4, active=2, critical=1 (RESOLVED+CRITICAL 不计入 critical)
        - 工单: total=4, pending=2 (PENDING+PROCESSING), completed=1
        """
        db = test_db["session"]
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
        from app.models.workorder import WorkOrder, WorkOrderStatus

        alarms = [
            Alarm(device_id=test_device.id, alarm_type="t1",
                  status=AlarmStatus.ACTIVE, level=AlarmLevel.CRITICAL),
            Alarm(device_id=test_device.id, alarm_type="t2",
                  status=AlarmStatus.ACTIVE, level=AlarmLevel.WARNING),
            Alarm(device_id=test_device.id, alarm_type="t3",
                  status=AlarmStatus.RESOLVED, level=AlarmLevel.CRITICAL),
            Alarm(device_id=test_device.id, alarm_type="t4",
                  status=AlarmStatus.RESOLVED, level=AlarmLevel.INFO),
        ]
        db.add_all(alarms)
        db.commit()

        workorders = [
            WorkOrder(id=f"WO-DIAG-{test_device.id}-1", fault_desc="d", type="repair",
                      level="warning", status=WorkOrderStatus.PENDING,
                      device_id=test_device.id),
            WorkOrder(id=f"WO-DIAG-{test_device.id}-2", fault_desc="d", type="repair",
                      level="warning", status=WorkOrderStatus.PROCESSING,
                      device_id=test_device.id),
            WorkOrder(id=f"WO-DIAG-{test_device.id}-3", fault_desc="d", type="repair",
                      level="warning", status=WorkOrderStatus.COMPLETED,
                      device_id=test_device.id),
            WorkOrder(id=f"WO-DIAG-{test_device.id}-4", fault_desc="d", type="repair",
                      level="warning", status=WorkOrderStatus.CLOSED,
                      device_id=test_device.id),
        ]
        db.add_all(workorders)
        db.commit()

        resp = client.post("/api/v1/diagnosis/device", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"device_id": test_device.id, "include_history": True})
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()["data"]

        assert data["alarm_stats"] == {"total": 4, "active": 2, "critical": 1}
        assert data["workorder_stats"] == {"total": 4, "pending": 2, "completed": 1}
        # 活跃告警分析项同步等价 (count/critical_count)
        alarm_items = [a for a in data["analysis"] if a.get("category") == "告警"]
        assert len(alarm_items) == 1
        assert alarm_items[0]["count"] == 2
        assert alarm_items[0]["critical_count"] == 1

    def test_device_diagnosis_stats_empty(self, auth_token, test_device):
        """零告警零工单: 全 0 计数, 无告警分析项。"""
        resp = client.post("/api/v1/diagnosis/device", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={"device_id": test_device.id})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["alarm_stats"] == {"total": 0, "active": 0, "critical": 0}
        assert data["workorder_stats"] == {"total": 0, "pending": 0, "completed": 0}
        assert not [a for a in data["analysis"] if a.get("category") == "告警"]
