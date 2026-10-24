"""
设备 API 测试
"""
import pytest
from fastapi.testclient import TestClient


def _get_token(client, username="admin", password="admin123"):
    """获取认证 token；测试环境 login 应稳定可用，失败直接 fail 以暴露真实问题。"""
    resp = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"login 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    token = (data.get("data", {}).get("token") or data.get("token")
             or data.get("data", {}).get("access_token") or data.get("access_token"))
    assert token, f"login 响应未含 token: {data}"
    return token


class TestDeviceList:
    """设备列表查询测试"""

    def test_list_devices_success(self, client: TestClient, seed_users, seed_devices):
        """列出所有设备"""
        token = _get_token(client)

        response = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"

    def test_list_devices_unauthenticated(self, anon_client: TestClient):
        """未认证用户无法获取设备列表"""
        response = anon_client.get("/api/v1/devices")
        assert response.status_code in (401, 403)

    def test_list_devices_filter_by_status(self, client: TestClient, seed_users, seed_devices):
        """按状态过滤设备"""
        token = _get_token(client)

        response = client.get(
            "/api/v1/devices?status=online",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_list_devices_filter_by_type(self, client: TestClient, seed_users, seed_devices):
        """按类型过滤设备"""
        token = _get_token(client)

        response = client.get(
            "/api/v1/devices?type=pv_inverter",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200


class TestDeviceDetail:
    """设备详情测试"""

    def test_get_device_by_id(self, client: TestClient, seed_users, seed_devices):
        """获取单个设备详情"""
        token = _get_token(client)

        device_id = seed_devices["inv001"].id
        response = client.get(
            f"/api/v1/devices/{device_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_get_device_by_sn(self, client: TestClient, seed_users, seed_devices):
        """通过序列号查询设备"""
        pytest.skip(reason="端点 /api/v1/devices/sn/{sn} 未实现（设备按 id 查询，无 by-sn 端点）")
        token = _get_token(client)

        response = client.get(
            "/api/v1/devices/sn/SN-TEST-001",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_get_nonexistent_device(self, client: TestClient, seed_users, seed_devices):
        """查询不存在的设备"""
        token = _get_token(client)

        response = client.get(
            "/api/v1/devices/99999",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code in (200, 404)


class TestDeviceHealth:
    """设备健康度测试"""

    def test_device_health_endpoint(self, client: TestClient, seed_users, seed_devices):
        """获取所有设备健康度"""
        pytest.skip(reason="端点 /api/v1/health/devices/health 批量健康未实现（实际仅有 /devices/{device_id}/health 单设备）")
        token = _get_token(client)

        response = client.get(
            "/api/v1/health/devices/health",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200


class TestDeviceRBAC:
    """设备权限测试"""

    def test_viewer_can_list_devices(self, client: TestClient, seed_users, seed_devices):
        """只读用户可以查看设备列表"""
        token = _get_token(client, "viewer1", "view123")

        response = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200


class TestDeviceMaintenancePlan:
    """设备维护计划设置测试"""

    @pytest.fixture(autouse=True)
    def _setup(self, client, seed_users):
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        import bcrypt

        s = client._sesh
        station = Station(name="维护测试站", code="MT001", status=StationStatus.NORMAL)
        s.add(station)
        s.flush()

        device = Device(
            sn="SN-MT-001", name="维护测试设备", code="MT001",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
            station_id=station.id, rated_power=20.0,
        )
        s.add(device)
        s.commit()
        s.refresh(device)
        self.device_id = device.id

        # 登录获取 token
        resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("token") or data.get("data", {}).get("token", "")
        else:
            self.token = ""

    def test_set_maintenance_plan(self, client):
        """设置设备维护计划"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        resp = client.put(
            f"/api/v1/devices/{self.device_id}/maintenance-plan",
            json={
                "maintenance_interval_days": 60,
                "next_maintenance": "2026-08-01",
                "last_maintenance": "2026-06-01",
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()["data"]
        assert data["maintenance_interval_days"] == 60
        assert data["next_maintenance"] == "2026-08-01"
        assert data["last_maintenance"] == "2026-06-01"

    def test_set_maintenance_plan_partial(self, client):
        """部分更新维护计划"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        resp = client.put(
            f"/api/v1/devices/{self.device_id}/maintenance-plan",
            json={"maintenance_interval_days": 30},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["maintenance_interval_days"] == 30

    def test_set_maintenance_plan_invalid_interval(self, client):
        """维护周期必须大于0"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        resp = client.put(
            f"/api/v1/devices/{self.device_id}/maintenance-plan",
            json={"maintenance_interval_days": 0},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 400

    def test_set_maintenance_plan_nonexistent(self, client):
        """设置不存在设备的维护计划"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        resp = client.put(
            "/api/v1/devices/99999/maintenance-plan",
            json={"maintenance_interval_days": 30},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 404


class TestDeviceMaintenanceRecords:
    """设备维护记录集成测试"""

    @pytest.fixture(autouse=True)
    def _setup(self, client, seed_users):
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus

        s = client._sesh
        station = Station(name="集成测试站", code="IT001", status=StationStatus.NORMAL)
        s.add(station)
        s.flush()

        device = Device(
            sn="SN-IT-001", name="集成测试设备", code="IT001",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
            station_id=station.id, rated_power=20.0,
            maintenance_interval_days=90,
        )
        s.add(device)
        s.commit()
        s.refresh(device)
        self.device_id = device.id

        resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("token") or data.get("data", {}).get("token", "")
        else:
            self.token = ""

    def test_device_detail_includes_maintenance_info(self, client):
        """设备详情包含维护计划信息"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        resp = client.get(
            f"/api/v1/devices/{self.device_id}",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "maintenance_interval_days" in data
        assert "last_maintenance" in data
        assert "next_maintenance" in data
        assert "maintenance_records" in data
        assert "maintenance_record_count" in data
        assert isinstance(data["maintenance_records"], list)
        assert data["maintenance_interval_days"] == 90

    def test_device_maintenance_records_list(self, client):
        """获取设备维护记录列表"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        # 先创建一条维护记录
        client.post(
            "/api/v1/maintenance-records",
            json={"device_id": self.device_id, "title": "集成测试维护", "type": "preventive"},
            headers={"Authorization": f"Bearer {self.token}"}
        )

        resp = client.get(
            f"/api/v1/devices/{self.device_id}/maintenance-records",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_device_maintenance_records_nonexistent(self, client):
        """获取不存在设备的维护记录"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")

        resp = client.get(
            "/api/v1/devices/99999/maintenance-records",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert resp.status_code == 404


class TestDeviceListTelemetry:
    """设备列表 power/total_energy 最新遥测摘要测试"""

    def test_devices_with_telemetry_return_power_and_energy(self, client, seed_users, seed_devices):
        """有遥测数据的设备返回最新一条的 power/total_energy（按类型分表，取最新一条）"""
        from datetime import datetime, timezone, timedelta
        from app.core.cache import clear_memory_cache
        from app.models.telemetry_v2 import TelemetryPV, TelemetryBattery, TelemetryCharger

        s = client._sesh
        now = datetime.now(timezone.utc)
        pv_dev = seed_devices["inv001"]    # PV_INVERTER -> telemetry_pv
        chg_dev = seed_devices["chg001"]  # CHARGER_DC  -> telemetry_charger
        pcs_dev = seed_devices["pcs001"]  # PCS         -> telemetry_battery

        # PV: 两条记录，验证取最新一条 (12.5 / 1000.0)，旧记录 (11.0 / 900.0) 应被忽略
        s.add(TelemetryPV(device_id=pv_dev.id, station_id=pv_dev.station_id,
                          timestamp=now - timedelta(minutes=5),
                          grid_power_total=11.0, total_generation=900.0))
        s.add(TelemetryPV(device_id=pv_dev.id, station_id=pv_dev.station_id,
                          timestamp=now,
                          grid_power_total=12.5, total_generation=1000.0))
        # Charger: charger_power / charger_kwh
        s.add(TelemetryCharger(device_id=chg_dev.id, station_id=chg_dev.station_id,
                               timestamp=now, charger_power=60.0, charger_kwh=250.0))
        # Battery(PCS): grid_power_total / total_discharge
        s.add(TelemetryBattery(device_id=pcs_dev.id, station_id=pcs_dev.station_id,
                               timestamp=now, grid_power_total=30.0, total_discharge=500.0))
        s.commit()

        clear_memory_cache()
        token = _get_token(client)
        resp = client.get("/api/v1/devices?page_size=100",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        by_id = {it["id"]: it for it in resp.json()["data"]["items"]}

        # PV 取最新一条
        assert by_id[pv_dev.id]["power"] == 12.5
        assert by_id[pv_dev.id]["total_energy"] == 1000.0
        # Charger
        assert by_id[chg_dev.id]["power"] == 60.0
        assert by_id[chg_dev.id]["total_energy"] == 250.0
        # Battery(PCS)
        assert by_id[pcs_dev.id]["power"] == 30.0
        assert by_id[pcs_dev.id]["total_energy"] == 500.0

    def test_devices_without_telemetry_return_none(self, client, seed_users, seed_devices):
        """无遥测数据的设备 power/total_energy 为 None，不报错"""
        from app.core.cache import clear_memory_cache

        clear_memory_cache()
        token = _get_token(client)
        resp = client.get("/api/v1/devices?page_size=100",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        assert items, "seed_devices 应至少返回一个设备"
        for it in items:
            assert it["power"] is None
            assert it["total_energy"] is None

class TestDeviceListPageGuard:
    """分页 page 参数 ge=1 守卫回归测试（卡0db1465a）"""

    def test_page_zero_returns_422(self, client: TestClient, seed_users):
        """page=0 → 422，而非负 offset 导致 500"""
        token = _get_token(client)
        resp = client.get("/api/v1/devices?page=0",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422

    def test_page_negative_returns_422(self, client: TestClient, seed_users):
        """page=-1 → 422"""
        token = _get_token(client)
        resp = client.get("/api/v1/devices?page=-1",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422
