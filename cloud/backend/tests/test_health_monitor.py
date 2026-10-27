"""健康度监控 API 测试
覆盖: devices, trend, calculate, boundary cases
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """种子 station + device（任务卡 ab5c5f17：治理后 trend/calculate 校验 device 存在；
    admin 豁免 team，device 需存在。trend/calculate 返回固定/随机数据，不依赖 device 业务字段）。"""
    from app.models.station import Station, StationStatus
    from app.models.device import Device, DeviceType, DeviceStatus
    s = test_db["session"]
    s.add(Station(id=1, name="种子站", code="SEEDST01", status=StationStatus.NORMAL))
    s.commit()
    for did in (1, 2, 3, 9999):
        s.add(Device(id=did, sn=f"SN-SEED-{did}", name=f"种子设备{did}",
                     code=f"SEED{did}", type=DeviceType.PV_INVERTER,
                     status=DeviceStatus.ONLINE, station_id=1, health_score=85.0))
    s.commit()


@pytest.fixture
def auth_token():
    """获取认证 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


class TestHealthMonitorAPI:

    # ========== 设备健康度列表 ==========

    # ========== 设备健康聚合概览 ==========

    def test_health_devices_empty_structure(self, client):
        """空库时返回完整聚合结构(各计数为0)。
        用 conftest client（独立空 DB，无 module-level 种子 device）。"""
        resp = client.get("/api/v1/health/devices")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data.keys()) >= {"overall", "rankings", "evaluations", "abnormal"}
        overall = data["overall"]
        for key in ("totalDevices", "healthyCount", "warningCount",
                    "criticalCount", "pendingEval", "overallScore"):
            assert key in overall
        assert overall["totalDevices"] == 0
        assert overall["overallScore"] == 0.0
        assert data["rankings"] == {"best": [], "worst": []}
        assert data["evaluations"] == []
        assert data["abnormal"] == []

    def test_health_devices_response_format(self):
        """响应格式验证(统一响应包装 code=200)"""
        resp = client.get("/api/v1/health/devices")
        assert resp.json().get("code") == 200

    def test_health_devices_aggregation(self, client, seed_users, seed_devices):
        """聚合概览: 计数/平均分与种子数据一致"""
        resp = client.get("/api/v1/health/devices")
        assert resp.status_code == 200
        overall = resp.json()["data"]["overall"]
        # seed_devices 提供了 4 个设备(默认 health_score=100.0)
        assert overall["totalDevices"] == 4
        assert overall["healthyCount"] + overall["warningCount"] + overall["criticalCount"] == 4
        assert 0.0 <= overall["overallScore"] <= 100.0

    def test_health_devices_rankings(self, client, seed_users, seed_devices):
        """rankings 含 best/worst, 每项结构完整, 分数单调"""
        resp = client.get("/api/v1/health/devices")
        rankings = resp.json()["data"]["rankings"]
        assert isinstance(rankings["best"], list)
        assert isinstance(rankings["worst"], list)
        for item in rankings["best"]:
            assert {"id", "deviceName", "stationName", "score", "status"} <= set(item.keys())
            assert item["status"] in {"normal", "warning", "critical"}
        # best 降序, worst 升序
        best_scores = [i["score"] for i in rankings["best"]]
        worst_scores = [i["score"] for i in rankings["worst"]]
        assert best_scores == sorted(best_scores, reverse=True)
        assert worst_scores == sorted(worst_scores)

    def test_health_devices_abnormal_low_score(self, client, seed_users, seed_stations):
        """health_score < 60 的设备进入 abnormal 列表"""
        from app.models.device import Device, DeviceType, DeviceStatus
        s = client._sesh
        s.add(Device(
            sn="SN-BAD-001", name="坏设备", code="BAD001",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.FAULT,
            station_id=seed_stations["station_a"].id, health_score=35.0,
        ))
        s.commit()

        resp = client.get("/api/v1/health/devices")
        data = resp.json()["data"]
        abnormal = data["abnormal"]
        names = [d["deviceName"] for d in abnormal]
        assert "坏设备" in names
        bad = next(d for d in abnormal if d["deviceName"] == "坏设备")
        assert bad["score"] < 60.0
        assert isinstance(bad["abnormalIndicators"], list) and bad["abnormalIndicators"]
        assert bad["suggestion"]

    def test_health_devices_evaluations_from_records(self, client, seed_users, seed_devices):
        """DeviceHealthRecord 记录出现在 evaluations 列表"""
        from app.models.device import DeviceHealthRecord
        s = client._sesh
        dev = seed_devices["inv001"]
        s.add(DeviceHealthRecord(
            device_id=dev.id, total_score=88.0,
            electrical_safe_score=28, thermal_score=22,
            comm_score=20, power_quality_score=15, mechanical_score=10,
        ))
        s.commit()

        resp = client.get("/api/v1/health/devices")
        evaluations = resp.json()["data"]["evaluations"]
        names = [e["deviceName"] for e in evaluations]
        assert dev.name in names
        rec = next(e for e in evaluations if e["deviceName"] == dev.name)
        assert rec["score"] == 88.0
        assert "dimensions" in rec
        assert rec["status"] in {"normal", "warning", "critical"}

    def test_health_devices_evaluations_latest_first(self, client, seed_users, seed_devices):
        """evaluations 按创建时间倒序(最新在前)"""
        from app.models.device import DeviceHealthRecord
        from datetime import datetime, timedelta
        s = client._sesh
        dev = seed_devices["chg001"]
        base = datetime(2026, 1, 1, 0, 0, 0)
        for i in range(3):
            s.add(DeviceHealthRecord(
                device_id=dev.id, total_score=70.0 + i,
                electrical_safe_score=28, thermal_score=22,
                comm_score=20, power_quality_score=15, mechanical_score=10,
                created_at=base + timedelta(days=i),
            ))
        s.commit()

        resp = client.get("/api/v1/health/devices")
        evals = [e for e in resp.json()["data"]["evaluations"]
                 if e["deviceId"] == dev.id]
        # 最新(score=72)在前
        assert evals[0]["score"] == 72.0

    # ========== 设备健康度趋势 ==========

    def test_get_health_trend(self):
        """获取设备健康度趋势 (卡6bc6f3f1: 无记录返回空列表)"""
        resp = client.get("/api/v1/health/trend/1")
        assert resp.status_code == 200
        data = resp.json()
        trend = data["data"]["trend"]
        assert trend == []  # 种子无 DeviceHealthRecord, 不再硬编码3天假趋势

    def test_get_health_trend_high_id(self):
        """获取大ID设备趋势"""
        resp = client.get("/api/v1/health/trend/9999")
        assert resp.status_code == 200

    def test_get_health_trend_dimensions(self):
        """趋势维度完整"""
        resp = client.get("/api/v1/health/trend/1")
        data = resp.json()
        dims = data["data"]["dimensions"]
        expected_keys = {
            "electrical_safety", "thermal_stability",
            "communication", "power_quality", "mechanical_life"
        }
        assert expected_keys.issubset(set(dims.keys()))

    def test_get_health_trend_dimension_sum(self):
        """维度总和接近100"""
        resp = client.get("/api/v1/health/trend/1")
        data = resp.json()
        dims = data["data"]["dimensions"]
        assert all(v is None for v in dims.values())  # 卡6bc6f3f1: 无记录不硬编码

    # ========== 健康度计算 ==========

    def test_calculate_health(self, auth_token):
        """计算设备健康度"""
        resp = client.post("/api/v1/health/calculate/1", headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "health" in data["data"]
        assert "dimensions" in data["data"]
        assert "calculated_at" in data["data"]

    def test_calculate_health_range(self, auth_token):
        """无遥测设备: 通信缺失低位分, 不返回 75-95 随机值 (卡6bc6f3f1)"""
        resp = client.post("/api/v1/health/calculate/1", headers={"Authorization": f"Bearer {auth_token}"})
        health = resp.json()["data"]["health"]
        assert 0 <= health < 60

    def test_calculate_health_different_ids(self, auth_token):
        """不同设备ID计算"""
        for did in [1, 2, 3]:
            resp = client.post(f"/api/v1/health/calculate/{did}", headers={"Authorization": f"Bearer {auth_token}"})
            assert resp.status_code == 200
            assert resp.json()["data"]["device_id"] == did

    def test_calculate_health_contains_timestamp(self, auth_token):
        """计算结果包含时间戳"""
        resp = client.post("/api/v1/health/calculate/1", headers={"Authorization": f"Bearer {auth_token}"})
        data = resp.json()["data"]
        assert "calculated_at" in data
        assert len(data["calculated_at"]) > 0

    def test_calculate_health_dimension_keys(self, auth_token):
        """维度键名完整"""
        resp = client.post("/api/v1/health/calculate/1", headers={"Authorization": f"Bearer {auth_token}"})
        dims = resp.json()["data"]["dimensions"]
        expected_keys = {
            "electrical_safety", "thermal_stability",
            "communication", "power_quality", "mechanical_life"
        }
        assert expected_keys.issubset(set(dims.keys()))

    def test_calculate_health_dimension_values(self, auth_token):
        """维度值为 0-100 或 null (卡6bc6f3f1: 维度不再按 30 分制随机)"""
        resp = client.post("/api/v1/health/calculate/1", headers={"Authorization": f"Bearer {auth_token}"})
        dims = resp.json()["data"]["dimensions"]
        for key, value in dims.items():
            assert value is None or 0 <= value <= 100, f"{key}={value} out of range"

# ========== [d3cc573c] 后台自动建单 creator_id 回归 ==========

def test_check_and_create_alarms_workorder_creator_is_none(test_db):
    """[d3cc573c] 健康巡检后台自动建单 creator_id 为 None，不为硬编码 999。

    未修前 creator_id=999（fresh DB 无 id=999 用户），断言失败。
    """
    from app.services.health_monitor import health_monitor
    from app.models.workorder import WorkOrder

    s = test_db["session"]
    s.query(WorkOrder).delete()  # 清既有 PENDING 干扰
    s.commit()

    # 种子设备 health_score=85（健康）不建单；置低后触发
    from app.models.device import Device
    s.query(Device).update({"health_score": 50.0})
    s.commit()
    result = health_monitor.check_and_create_alarms(s)
    assert result, "置低健康度后应建单"

    orders = s.query(WorkOrder).all()
    assert orders, "应存在自动创建的工单"
    for wo in orders:
        assert wo.creator_id is None


# ========== 卡6bc6f3f1: trend/calculate 接真实数据 ==========

class TestHealthTrendReal:
    """trend 接 DeviceHealthRecord 真实序列 (卡6bc6f3f1)"""

    def test_trend_empty_returns_empty_list(self, client, seed_users, seed_devices):
        """无记录返回空列表，禁止硬编码假趋势"""
        resp = client.get(f"/api/v1/health/trend/{seed_devices['inv001'].id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["trend"] == []

    def test_trend_from_records(self, client, seed_users, seed_devices):
        """趋势来自 DeviceHealthRecord.created_at 序列"""
        from app.models.device import DeviceHealthRecord
        from datetime import datetime, timedelta
        s = client._sesh
        dev = seed_devices["inv001"]
        base = datetime(2026, 1, 1)
        for i in range(3):
            s.add(DeviceHealthRecord(device_id=dev.id, total_score=80.0 + i,
                                     created_at=base + timedelta(days=i)))
        s.commit()
        resp = client.get(f"/api/v1/health/trend/{dev.id}")
        data = resp.json()["data"]
        assert len(data["trend"]) == 3
        assert data["trend"][0]["date"] == "2026-01-01"
        assert data["trend"][0]["health"] == 80.0
        assert data["trend"][2]["health"] == 82.0

    def test_trend_dimensions_latest_record(self, client, seed_users, seed_devices):
        """dimensions 取最新一条记录"""
        from app.models.device import DeviceHealthRecord
        from datetime import datetime, timedelta
        s = client._sesh
        dev = seed_devices["chg001"]
        base = datetime(2026, 1, 1)
        for i in range(2):
            s.add(DeviceHealthRecord(
                device_id=dev.id, total_score=70.0 + i,
                electrical_safe_score=26 + i, thermal_score=20,
                comm_score=18, power_quality_score=14, mechanical_score=9,
                created_at=base + timedelta(days=i)))
        s.commit()
        resp = client.get(f"/api/v1/health/trend/{dev.id}")
        dims = resp.json()["data"]["dimensions"]
        assert dims["electrical_safety"] == 27  # 最新 (i=1)
        assert dims["communication"] == 18

    def test_trend_dimensions_empty_when_no_record(self, client, seed_users, seed_devices):
        """无记录时 dimensions 各维度为 null（不再硬编码）"""
        resp = client.get(f"/api/v1/health/trend/{seed_devices['inv001'].id}")
        dims = resp.json()["data"]["dimensions"]
        assert all(v is None for v in dims.values())


class TestCalculateHealthReal:
    """calculate 基于真实 Telemetry 计算并落库 (卡6bc6f3f1)"""

    def _post(self, client, device_id):
        return client.post(f"/api/v1/health/calculate/{device_id}")

    def test_no_tlemetry_comm_low_record(self, client, seed_users, seed_stations):
        """无任何 telemetry 的设备: 落 comm_score 低位记录，不返回随机值"""
        from app.models.device import Device, DeviceType, DeviceStatus, DeviceHealthRecord
        s = client._sesh
        dev = Device(sn="SN-NOTEL", name="无遥测设备", code="NOTEL",
                     type=DeviceType.PV_INVERTER, status=DeviceStatus.OFFLINE,
                     station_id=seed_stations["station_a"].id)
        s.add(dev)
        s.commit()
        resp = self._post(client, dev.id)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["health"] < 60  # 通信缺失 → 低分
        dims = data["dimensions"]
        assert dims["communication"] is not None and dims["communication"] < 50
        # 不可得维度为 null
        assert dims["electrical_safety"] is None
        assert data["data_source"]["electrical_safety"] == "no_telemetry"
        # 落库
        rec = s.query(DeviceHealthRecord).filter(
            DeviceHealthRecord.device_id == dev.id).order_by(
            DeviceHealthRecord.id.desc()).first()
        assert rec is not None
        assert rec.total_score == data["health"]

    def test_calculate_with_telemetry_persists(self, client, seed_users, seed_stations):
        """有 telemetry: 各维度基于真实数据计算并写 DeviceHealthRecord"""
        from app.models.device import Device, DeviceType, DeviceStatus, DeviceHealthRecord
        from app.models.telemetry import Telemetry
        from datetime import datetime, timedelta, timezone
        s = client._sesh
        dev = Device(sn="SN-CALC", name="计算设备", code="CALC",
                     type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
                     station_id=seed_stations["station_a"].id, rated_power=60.0)
        s.add(dev)
        s.commit()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(12):  # 近 1h 每 5min 一条
            s.add(Telemetry(
                device_id=dev.id, timestamp=now - timedelta(minutes=5 * i),
                grid_power_total=30.0, grid_voltage_a=230.0, grid_voltage_b=230.0,
                grid_voltage_c=230.0, grid_power_factor=0.98, charger_power=30.0,
                gun_temperature=35.0))
        s.commit()
        resp = self._post(client, dev.id)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert 0 <= data["health"] <= 100
        dims = data["dimensions"]
        assert dims["electrical_safety"] is not None
        assert dims["thermal_stability"] is not None
        assert dims["communication"] is not None
        rec = s.query(DeviceHealthRecord).filter(
            DeviceHealthRecord.device_id == dev.id).order_by(
            DeviceHealthRecord.id.desc()).first()
        assert rec is not None
        assert rec.comm_score is not None and rec.comm_score > 0

    def test_calculate_deterministic(self, client, seed_users, seed_stations):
        """同样数据两次计算结果一致（非随机）"""
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.telemetry import Telemetry
        from datetime import datetime, timedelta, timezone
        s = client._sesh
        dev = Device(sn="SN-DET", name="确定性设备", code="DET",
                     type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                     station_id=seed_stations["station_a"].id, rated_power=50.0)
        s.add(dev)
        s.commit()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(10):
            s.add(Telemetry(device_id=dev.id, timestamp=now - timedelta(minutes=i * 6),
                            grid_power_total=20.0, grid_voltage_a=228.0,
                            grid_power_factor=0.95, pv1_power=15.0,
                            inv_temperature=45.0))
        s.commit()
        r1 = self._post(client, dev.id).json()["data"]
        r2 = self._post(client, dev.id).json()["data"]
        assert r1["health"] == r2["health"]
        assert r1["dimensions"] == r2["dimensions"]

    def test_calculate_sporadic_telemetry_low_comm(self, client, seed_users, seed_stations):
        """遥测断档(仅1条老数据): comm_score 降低"""
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.telemetry import Telemetry
        from datetime import datetime, timedelta, timezone
        s = client._sesh
        dev = Device(sn="SN-SPARSE", name="断档设备", code="SPARSE",
                     type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                     station_id=seed_stations["station_a"].id)
        s.add(dev)
        s.commit()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        s.add(Telemetry(device_id=dev.id, timestamp=now - timedelta(hours=6),
                        grid_power_total=10.0))
        s.commit()
        data = self._post(client, dev.id).json()["data"]
        assert data["dimensions"]["communication"] < 60


# ========== 卡07cdb6af: 健康度数据来源标记 (mock/telemetry) ==========

class TestHealthDataSource:
    """health_monitor 数据来源透出: 遥测表最新记录可查 → 接真实遥测, 否则 mock"""

    def _seed_telemetry(self, s, model_cls, device_id, **fields):
        from datetime import datetime, timezone
        row = model_cls(device_id=device_id, station_id=1,
                        timestamp=datetime.now(timezone.utc), **fields)
        s.add(row)
        s.commit()

    def test_mock_data_has_source_marker(self):
        """无遥测记录时 _generate_mock_data 返回 dict 带 source=mock"""
        from app.services.health_monitor import HealthMonitor
        data = HealthMonitor()._generate_mock_data("pv_inverter")
        assert data.get("source") == "mock"

    def test_mock_warning_logged_once(self, caplog):
        """mock 数据 warning 进程级只警告一次, 不刷屏"""
        import logging as _logging
        import app.services.health_monitor as hm_module
        from app.services.health_monitor import HealthMonitor
        hm_module._mock_warned = False  # 复位进程级 flag, 消除用例顺序依赖
        hm = HealthMonitor()
        with caplog.at_level(_logging.WARNING, logger="app.services.health_monitor"):
            hm._generate_mock_data("pv_inverter")
            hm._generate_mock_data("charger_dc")
        mock_warnings = [r for r in caplog.records
                         if "模拟数据" in r.getMessage()]
        assert len(mock_warnings) == 1, f"应只警告一次, 实际 {len(mock_warnings)}"

    def test_real_telemetry_pv_fields(self, test_db):
        """pv 设备: telemetry_pv 有最新记录 → 真实字段(internal_temperature/grid_voltage) + source=telemetry"""
        from app.services.health_monitor import HealthMonitor
        from app.models.telemetry_v2 import TelemetryPV
        s = test_db["session"]
        self._seed_telemetry(s, TelemetryPV, 1,
                             internal_temperature=42.0, grid_voltage_a=400.0,
                             grid_power_factor=0.95)
        hm = HealthMonitor()
        data = hm._collect_device_data(s, 1, "pv_inverter")
        assert data["source"] == "telemetry"
        assert data["temperature"] == 42.0
        assert data["voltage"] == 400.0
        assert data["power_factor"] == 0.95

    def test_real_telemetry_battery_soh(self, test_db):
        """battery 设备: battery_soh 透传"""
        from app.services.health_monitor import HealthMonitor
        from app.models.telemetry_v2 import TelemetryBattery
        s = test_db["session"]
        self._seed_telemetry(s, TelemetryBattery, 2, battery_soh=88.0,
                             internal_temperature=35.0)
        data = HealthMonitor()._collect_device_data(s, 2, "battery")
        assert data["source"] == "telemetry"
        assert data["battery_soh"] == 88.0

    def test_real_telemetry_charger_gun_temp(self, test_db):
        """charger 设备: gun_temperature 透传"""
        from app.services.health_monitor import HealthMonitor
        from app.models.telemetry_v2 import TelemetryCharger
        s = test_db["session"]
        self._seed_telemetry(s, TelemetryCharger, 3, gun_temperature=45.0,
                             charger_voltage=380.0)
        data = HealthMonitor()._collect_device_data(s, 3, "charger_dc")
        assert data["source"] == "telemetry"
        assert data["gun_temperature"] == 45.0
        assert data["voltage"] == 380.0

    def test_no_telemetry_falls_back_mock(self, test_db):
        """设备无遥测记录 → 回退 mock + source=mock (种子 device 4 无遥测)"""
        from app.services.health_monitor import HealthMonitor
        s = test_db["session"]
        data = HealthMonitor()._collect_device_data(s, 4, "pv_inverter")
        assert data["source"] == "mock"

    def test_unmapped_type_uses_legacy_then_mock(self, test_db):
        """无专表类型(meter/gateway/v2g_charger): 查 legacy telemetry, 无记录回退 mock"""
        from app.services.health_monitor import HealthMonitor
        s = test_db["session"]
        data = HealthMonitor()._collect_device_data(s, 1, "meter")
        assert data["source"] == "mock"

    def test_get_device_health_carries_source(self, test_db):
        """get_device_health 响应透出 source 字段"""
        from app.services.health_monitor import health_monitor
        s = test_db["session"]
        result = health_monitor.get_device_health(1, s)
        assert result.get("source") in ("mock", "telemetry")

    def test_calculate_all_health_items_carry_source(self, test_db):
        """calculate_all_health 每项带 source"""
        from app.services.health_monitor import health_monitor
        s = test_db["session"]
        results = health_monitor.calculate_all_health(s)
        assert results
        for item in results:
            assert item.get("source") in ("mock", "telemetry")
