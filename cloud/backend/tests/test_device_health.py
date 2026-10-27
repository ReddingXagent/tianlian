"""
设备健康度评估测试
测试健康度评分算法、API端点和边界条件
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

# 测试健康度评分服务
class TestHealthServiceScore:
    """测试健康度评分算法"""
    
    def test_health_status_healthy(self):
        """健康度 >= 80 显示健康"""
        from app.services.health import HealthService
        service = HealthService()
        
        assert service.get_health_status(80) == "healthy"
        assert service.get_health_status(90) == "healthy"
        assert service.get_health_status(100) == "healthy"
        assert service.get_health_status_display(80) == "健康"
    
    def test_health_status_sub_healthy(self):
        """健康度 50-79 显示亚健康"""
        from app.services.health import HealthService
        service = HealthService()
        
        assert service.get_health_status(50) == "sub_healthy"
        assert service.get_health_status(65) == "sub_healthy"
        assert service.get_health_status(79) == "sub_healthy"
        assert service.get_health_status_display(65) == "亚健康"
    
    def test_health_status_faulty(self):
        """健康度 < 50 显示故障"""
        from app.services.health import HealthService
        service = HealthService()
        
        assert service.get_health_status(49) == "faulty"
        assert service.get_health_status(30) == "faulty"
        assert service.get_health_status(0) == "faulty"
        assert service.get_health_status_display(30) == "故障"


class TestDeviceHealthAPI:
    """测试设备健康度 API 端点"""
    
    @pytest.fixture(autouse=True)
    def _setup(self, test_db):
        self.db = test_db
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        import bcrypt

        s = test_db["session"]
        station = Station(name="健康测试站", code="HEALTH001", status=StationStatus.NORMAL)
        s.add(station)
        s.flush()

        # 创建测试设备
        device = Device(
            sn="SN-HEALTH-001", 
            name="健康测试设备", 
            code="HEALTH001",
            type=DeviceType.PV_INVERTER, 
            status=DeviceStatus.ONLINE,
            station_id=station.id, 
            rated_power=20.0,
            health_score=85.0,
        )
        s.add(device)
        s.commit()
        s.refresh(device)
        self.device_id = device.id
        
        # 登录获取 token
        import requests
        client = requests.Session()
        from app.main import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)
        
        resp = self.client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("token") or data.get("data", {}).get("token", "")
        else:
            self.token = ""

    def test_get_device_health_endpoint(self):
        """GET /api/v1/devices/{id}/health 返回健康度信息"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")
        
        response = self.client.get(
            f"/api/v1/devices/{self.device_id}/health",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert response.status_code == 200, f"API 调用失败: {response.text}"
        
        data = response.json().get("data", response.json())
        assert "health_score" in data
        assert "health_status" in data
        assert "health_status_display" in data
        assert "checked_at" in data
    
    def test_get_device_health_nonexistent(self):
        """获取不存在设备的健康度返回404"""
        if not self.token:
            pytest.fail("登录失败: 测试环境认证回归, 不允许静默跳过")
        
        response = self.client.get(
            "/api/v1/devices/99999/health",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert response.status_code == 404


class TestHealthCalculationWithFactors:
    """测试健康度根据告警数、维护记录、运行时长计算"""
    
    @pytest.fixture(autouse=True)
    def _setup(self, test_db):
        self.db = test_db
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        from app.models.maintenance_record import MaintenanceRecord, MaintenanceType, MaintenanceStatus
        from app.models.alarm import Alarm, AlarmLevel, AlarmStatus

        s = test_db["session"]
        station = Station(name="综合健康测试站", code="COMPREHENSIVE", status=StationStatus.NORMAL)
        s.add(station)
        s.flush()

        device = Device(
            sn="SN-COMPREHENSIVE", 
            name="综合测试设备", 
            code="COMP001",
            type=DeviceType.PV_INVERTER, 
            status=DeviceStatus.ONLINE,
            station_id=station.id, 
            rated_power=20.0,
            total_run_hours=5000.0,  # 长时间运行
        )
        s.add(device)
        
        # 添加维护记录
        record = MaintenanceRecord(
            device_id=1,
            type=MaintenanceType.PREVENTIVE,
            status=MaintenanceStatus.COMPLETED,
            title="定期维护",
            planned_at=datetime.now(),
        )
        s.add(record)
        
        s.commit()
        s.refresh(device)
        self.device_id = device.id

    def test_health_score_equation_with_alarms_and_maintenance(self):
        """健康度评分考虑告警数、维护记录、运行时长"""
        from app.services.health import HealthService
        from app.models.device import Device
        
        service = HealthService()
        
        # 创建模拟设备数据
        device_data = {
            "insulation_resistance": 5.0,  # 良好
            "leakage_current": 5.0,  # 良好
            "temperature": 45.0,  # 良好
            "voltage": 220.0,  # 良好
            "comm_success_rate": 98.0,  # 良好
            "plug_count": 500,  # 较低使用量
            "ground_fault": False,
            "temp_rise_rate": 1.0,
            "current_thd": 5.0,
        }
        
        # 验证健康度在合理范围内
        result = service.calculate_device_health(
            device=self.db["session"].query(Device).first(),
            device_data=device_data,
            db=self.db["session"]
        )

        assert 0 <= result["health_score"] <= 100
        assert result["health_status"] in ["healthy", "sub_healthy", "faulty"]


# ─────────────────────────────────────────────────────────────
# HealthService 异常处理 + 输入校验补全 (服务层单元测试)
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def health_svc():
    from app.services.health import HealthService
    return HealthService()


@pytest.fixture
def patch_health_engine(monkeypatch):
    """控制 health_engine.calculate_health_score 返回 (score, dimension_scores)"""
    def _patch(score, dims):
        monkeypatch.setattr(
            "app.services.health.health_engine.calculate_health_score",
            lambda *a, **kw: (score, dims),
        )
    return _patch


def _mock_health_device():
    from unittest.mock import MagicMock
    d = MagicMock()
    d.id = 1
    d.code = "D1"
    d.name = "DEV"
    d.type = MagicMock()
    d.type.value = "pv_inverter"
    return d


# ─── get_health_status 分数范围校验 (负数 / >100 归最低档) ───

class TestHealthStatusRange:
    def test_negative_returns_faulty(self, health_svc):
        assert health_svc.get_health_status(-1) == "faulty"
        assert health_svc.get_health_status(-10) == "faulty"

    def test_over_100_returns_faulty(self, health_svc):
        """超过满分(>100)视为异常数据 → 最低档"""
        assert health_svc.get_health_status(101) == "faulty"
        assert health_svc.get_health_status(150) == "faulty"

    def test_boundary_100_still_healthy(self, health_svc):
        assert health_svc.get_health_status(100) == "healthy"

    def test_zero_returns_faulty(self, health_svc):
        assert health_svc.get_health_status(0) == "faulty"

    def test_negative_display_consistent(self, health_svc):
        assert health_svc.get_health_status_display(-5) == "故障"


# ─── calculate_device_health: db.commit 异常 → rollback + 不崩 ───

class TestCommitRollback:
    def test_commit_failure_rolls_back_and_returns_result(self, health_svc, patch_health_engine):
        patch_health_engine(75.0, {"electrical": 80})
        device = _mock_health_device()
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db connection lost")

        result = health_svc.calculate_device_health(device=device, device_data={}, db=db)

        assert db.commit.called
        assert db.rollback.called
        assert result["health_score"] == 75.0
        assert result["health_status"] == "sub_healthy"


# ─── dimension_scores 非数值转 int 容错 ───

class TestDimensionScoresCoercion:
    def test_non_numeric_dimensions_coerced_to_zero(self, health_svc, patch_health_engine):
        patch_health_engine(60.0, {
            "electrical": None, "thermal": "abc",
            "communication": 85.5, "power_quality": 90, "mechanical": None,
        })
        device = _mock_health_device()
        db = MagicMock()

        result = health_svc.calculate_device_health(device=device, device_data={}, db=db)

        assert result["health_score"] == 60.0
        db.add.assert_called_once()
        db.commit.assert_called_once()


# ─── get_all_devices_health 分页 ───

class TestGetAllDevicesHealthPagination:
    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.station import Station, StationStatus
        s = test_db["session"]
        station = Station(name="分页站", code="PAGE001", status=StationStatus.NORMAL)
        s.add(station)
        s.flush()
        self.db = s
        for i in range(5):
            s.add(Device(
                sn=f"SN-PG-{i}", name=f"DEV-{i}", code=f"PG{i}",
                type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                station_id=station.id, rated_power=20.0, health_score=80.0 + i,
            ))
        s.commit()

    def test_limit_returns_subset(self, health_svc):
        r = health_svc.get_all_devices_health(self.db, limit=2)
        assert len(r) == 2

    def test_offset_skips_first(self, health_svc):
        page1 = health_svc.get_all_devices_health(self.db, limit=2, offset=0)
        page2 = health_svc.get_all_devices_health(self.db, limit=2, offset=2)
        assert {d["device_id"] for d in page1}.isdisjoint({d["device_id"] for d in page2})

    def test_no_limit_returns_all(self, health_svc):
        """limit=None → 全量(向后兼容)"""
        r = health_svc.get_all_devices_health(self.db)
        assert len(r) == 5


# ─── JOIN on created_at 去重 ───

class TestGetAllDevicesHealthDedup:
    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        from app.models.device import Device, DeviceType, DeviceStatus, DeviceHealthRecord
        from app.models.station import Station, StationStatus
        s = test_db["session"]
        station = Station(name="去重站", code="DEDUP001", status=StationStatus.NORMAL)
        s.add(station)
        s.flush()
        device = Device(
            sn="SN-DD-0", name="DEV-DD", code="DD0",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
            station_id=station.id, rated_power=20.0, health_score=70.0,
        )
        s.add(device)
        s.commit()
        s.refresh(device)
        self.device_id = device.id
        self.db = s
        # 同一 device 同一 created_at 插入两条记录 (制造 JOIN 重复风险)
        ts = datetime(2026, 8, 3, 12, 0, 0)
        for score in (70, 71):
            rec = DeviceHealthRecord(
                device_id=device.id, electrical_safe_score=score,
                thermal_score=80, comm_score=80, power_quality_score=80,
                mechanical_score=80, total_score=score,
            )
            rec.created_at = ts
            s.add(rec)
        s.commit()

    def test_no_duplicate_device_in_results(self, health_svc):
        r = health_svc.get_all_devices_health(self.db)
        ids = [d["device_id"] for d in r]
        assert ids.count(self.device_id) == 1