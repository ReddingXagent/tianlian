"""
遥测数据 API 测试
覆盖: latest/history/stats/report/simulate
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture"""
    pass


@pytest.fixture
def auth_token(test_db):
    """获取认证token"""
    response = client.post("/api/v1/auth/login", data={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return token


@pytest.fixture
def test_station(test_db):
    """创建测试站点"""
    db = test_db["session"]
    from app.models.station import Station, StationStatus
    station = Station(
        name="遥测测试站点",
        code="TELEMETRY-STATION-001",
        status=StationStatus.NORMAL
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


@pytest.fixture
def test_device(test_db, test_station):
    """创建测试设备"""
    db = test_db["session"]
    from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
    device = Device(
        sn="TELEMETRY-DEV-001",
        name="遥测测试设备",
        type=DeviceType.PV_INVERTER,
        status=DeviceStatus.ONLINE,
        station_id=test_station.id,
        protocol_type=ProtocolType.MODBUS_RTU
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestTelemetryAPI:
    """遥测数据 API 测试类"""

    # ========== 数据上报 ==========

    def test_report_telemetry_success(self, auth_token, test_device):
        """测试遥测数据上报成功"""
        response = client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "grid_voltage_a": 220.5,
            "grid_current_a": 10.2,
            "grid_power_total": 15.5,
            "battery_soc": 85.0,
            "battery_temperature": 32.5,
            "internal_temperature": 40.0
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True or data.get("data") is not None

    def test_report_telemetry_device_not_found(self, auth_token):
        """测试遥测数据上报设备不存在"""
        response = client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": 99999,
            "grid_voltage_a": 220.0
        })
        assert response.status_code == 404

    def test_report_telemetry_charger_data(self, auth_token, test_station, test_db):
        """测试充电桩遥测数据上报"""
        db = test_db["session"]
        from app.models.device import Device, DeviceType, DeviceStatus
        charger = Device(
            sn="CHARGER-001",
            name="测试充电桩",
            type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE,
            station_id=test_station.id
        )
        db.add(charger)
        db.commit()
        db.refresh(charger)

        response = client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": charger.id,
            "charger_voltage": 400.0,
            "charger_current": 50.0,
            "charger_power": 20.0,
            "charger_soc": 60.0,
            "gun_status": 1
        })
        assert response.status_code == 200

    # ========== 最新数据 ==========

    def test_get_latest_telemetry_success(self, auth_token, test_device):
        """测试获取最新遥测数据成功"""
        # 先上报一条数据
        client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "grid_voltage_a": 221.0,
            "battery_soc": 90.0
        })

        # 获取最新
        response = client.get(f"/api/v1/telemetry/device/{test_device.id}/latest", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        telemetry = data.get("data", data)
        assert telemetry.get("device_id") == test_device.id

    def test_get_latest_telemetry_not_found(self, auth_token, test_station, test_db):
        """测试获取最新遥测数据不存在"""
        db = test_db["session"]
        from app.models.device import Device, DeviceType, DeviceStatus
        new_device = Device(
            sn="NEW-DEV-NO-TELEMETRY",
            name="无遥测设备",
            type=DeviceType.PV_INVERTER,
            status=DeviceStatus.ONLINE,
            station_id=test_station.id
        )
        db.add(new_device)
        db.commit()
        db.refresh(new_device)

        response = client.get(f"/api/v1/telemetry/device/{new_device.id}/latest", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    # ========== 历史数据 ==========

    def test_get_telemetry_history_success(self, auth_token, test_device):
        """测试获取遥测历史数据成功"""
        # 先上报多条数据
        for i in range(3):
            client.post("/api/v1/telemetry/report", headers={
                "Authorization": f"Bearer {auth_token}"
            }, json={
                "device_id": test_device.id,
                "grid_voltage_a": 220.0 + i,
                "battery_soc": 80.0 + i
            })

        # 获取历史
        response = client.get(f"/api/v1/telemetry/device/{test_device.id}/history?hours=24", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        history = data.get("data", data)
        assert history.get("device_id") == test_device.id
        assert history.get("count") >= 3

    def test_get_telemetry_history_custom_hours(self, auth_token, test_device):
        """测试获取遥测历史数据自定义时间范围"""
        response = client.get(f"/api/v1/telemetry/device/{test_device.id}/history?hours=1", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    # ========== 统计数据 ==========

    def test_get_telemetry_stats_success(self, auth_token, test_device):
        """测试获取遥测统计数据成功"""
        # 先上报数据
        client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "grid_voltage_a": 220.0,
            "grid_power_total": 15.0,
            "battery_soc": 85.0,
            "battery_temperature": 30.0
        })

        # 获取统计
        response = client.get(f"/api/v1/telemetry/device/{test_device.id}/stats?hours=24", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        stats = data.get("data", data)
        assert stats.get("device_id") == test_device.id
        assert "stats" in stats

    def test_get_telemetry_stats_structure(self, auth_token, test_device):
        """测试遥测统计数据结构"""
        client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "grid_voltage_a": 220.5,
            "internal_temperature": 45.0
        })

        response = client.get(f"/api/v1/telemetry/device/{test_device.id}/stats", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        stats = data.get("data", {}).get("stats", {})
        assert "grid" in stats or "thermal" in stats

    def test_get_telemetry_stats_charger_kwh_net_increment(self, auth_token, test_station, test_db):
        """回归(卡 6e80d5d6): 充电桩 charger_kwh 是累计电能表快照(单调递增),
        total_kwh 必须取 MAX-MIN 窗口净增量, 而非 SUM(N 行快照求和会把计数器翻 N 倍)。
        窗口 1.0 → 2.5 → 4.0 → 5.0 → 净增量 4.0(SUM 旧口径=12.5)。
        """
        from datetime import datetime, timedelta, timezone
        from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
        from app.models.telemetry_v2 import TelemetryCharger

        db = test_db["session"]
        charger = Device(
            sn="ST-CHG-KWH-001", name="充电桩累计计数器", type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE, station_id=test_station.id,
            protocol_type=ProtocolType.MODBUS_RTU,
        )
        db.add(charger); db.commit(); db.refresh(charger)

        base = datetime.now(timezone.utc) - timedelta(minutes=10)
        for i, kwh in enumerate([1.0, 2.5, 4.0, 5.0]):
            db.add(TelemetryCharger(
                device_id=charger.id, station_id=test_station.id,
                timestamp=base + timedelta(minutes=i),
                region_id="default", pod_id="pod-01",
                charger_power=11.0, charger_soc=50.0,
                charger_kwh=kwh,
            ))
        db.commit()

        response = client.get(f"/api/v1/telemetry/device/{charger.id}/stats?hours=24", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["data"]["table_type"] == "charger"
        total_kwh = data["data"]["stats"]["charger"]["total_kwh"]
        # 净增量 = 5.0 - 1.0 = 4.0, 不是 SUM=12.5
        assert total_kwh == pytest.approx(4.0)

    # ========== 场站概览 ==========

    def test_get_station_telemetry_overview_success(self, auth_token, test_station, test_device):
        """测试获取场站遥测概览成功"""
        # 上报数据
        client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": test_device.id,
            "grid_power_total": 10.0
        })

        response = client.get(f"/api/v1/telemetry/station/{test_station.id}/overview", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        overview = data.get("data", data)
        assert overview.get("station_id") == test_station.id

    def test_station_overview_legacy_telemetry(self, auth_token, test_station, test_db):
        """回归: 场站概览对 legacy Telemetry 模型(无 station_id)不应500

        meter/v2g_charger/gateway 等类型不在 DEVICE_TYPE_TABLE_MAP,
        route_to_telemetry_table 返回旧 Telemetry 表(仅 device_id, 无 station_id),
        此前端点无条件 filter(model_class.station_id) 触发 AttributeError -> 500。
        """
        db = test_db["session"]
        from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
        legacy_device = Device(
            sn="TELEMETRY-LEGACY-001",
            name="电表(legacy表)",
            type=DeviceType.METER,
            status=DeviceStatus.ONLINE,
            station_id=test_station.id,
            protocol_type=ProtocolType.MODBUS_RTU,
        )
        db.add(legacy_device)
        db.commit()
        db.refresh(legacy_device)

        response = client.get(f"/api/v1/telemetry/station/{test_station.id}/overview", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200, f"legacy Telemetry 路径不应500: {response.text}"
        data = response.json()
        overview = data.get("data", data)
        assert overview.get("station_id") == test_station.id
        # legacy 设备应出现在概览中
        device_ids = [item["device_id"] for item in overview.get("overview", [])]
        assert legacy_device.id in device_ids

    def test_station_overview_batch_latest_and_fallback(self, auth_token, test_station, test_db):
        """回归(卡 0e7deb3d 批量化取 latest): 行为与逐设备实现等价 ——
        1) 同设备多条遥测, 取 timestamp 最新一条的值(非最早/非任意);
        2) v2 设备在专表无数据时, fallback 到 legacy Telemetry 表取值。
        覆盖窗口函数 row_number 分组取最新 + 批量 legacy fallback 路径。
        """
        from datetime import datetime, timedelta
        from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
        from app.models.telemetry import Telemetry
        from app.models.telemetry_v2 import TelemetryCharger

        db = test_db["session"]
        # 充电桩: 专表多条, 仅最新一条应被选中
        charger = Device(
            sn="OV-CHG-001", name="充电桩A", type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE, station_id=test_station.id,
            protocol_type=ProtocolType.MODBUS_RTU,
        )
        db.add(charger); db.commit(); db.refresh(charger)
        base = datetime(2026, 7, 1, 0, 0, 0)
        db.add(TelemetryCharger(
            device_id=charger.id, station_id=test_station.id, timestamp=base,
            region_id="default", pod_id="pod-01",
            charger_power=1.1, charger_soc=10.0,
        ))
        db.add(TelemetryCharger(
            device_id=charger.id, station_id=test_station.id, timestamp=base + timedelta(hours=1),
            region_id="default", pod_id="pod-01",
            charger_power=22.5, charger_soc=80.0,
        ))
        # 光伏: 类型映射 TelemetryPV, 但专表无数据 → 走 legacy Telemetry fallback
        pv_fb = Device(
            sn="OV-PV-FB-001", name="光伏(走fallback)", type=DeviceType.PV_INVERTER,
            status=DeviceStatus.ONLINE, station_id=test_station.id,
            protocol_type=ProtocolType.MODBUS_RTU,
        )
        db.add(pv_fb); db.commit(); db.refresh(pv_fb)
        db.add(Telemetry(
            device_id=pv_fb.id, timestamp=base + timedelta(hours=2),
            grid_power_total=7.7, battery_soc=55.0,
        ))
        db.commit()

        resp = client.get(f"/api/v1/telemetry/station/{test_station.id}/overview", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert resp.status_code == 200, resp.text
        items = {it["device_id"]: it for it in resp.json()["data"]["overview"]}

        # 充电桩取专表最新(22.5/80.0), 不是旧值
        ch = items[charger.id]["latest_telemetry"]
        assert ch["power"] == 22.5
        assert ch["soc"] == 80.0

        # PV fallback: 专表无数据 → legacy Telemetry 的 grid_power_total/battery_soc
        fb = items[pv_fb.id]["latest_telemetry"]
        assert fb["power"] == 7.7
        assert fb["soc"] == 55.0

    # ========== 模拟数据生成 ==========

    def test_simulate_telemetry_success(self, auth_token, test_device):
        """测试生成模拟遥测数据成功"""
        response = client.post(f"/api/v1/telemetry/device/{test_device.id}/simulate?hours=1&interval_seconds=60", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        # 支持两种响应格式: {success: True, data: {...}} 或 {code: 200, data: {...}}
        result = data.get("data", data)
        assert result.get("records_created") > 0

    def test_simulate_telemetry_custom_params(self, auth_token, test_device):
        """测试生成模拟遥测数据自定义参数"""
        response = client.post(f"/api/v1/telemetry/device/{test_device.id}/simulate?hours=2&interval_seconds=120", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_simulate_telemetry_device_not_found(self, auth_token):
        """测试生成模拟遥测数据设备不存在"""
        response = client.post(f"/api/v1/telemetry/device/99999/simulate?hours=1", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    # ========== 边界测试 ==========

    def test_get_latest_telemetry_invalid_device_id(self, auth_token):
        """测试获取最新遥测数据无效设备ID"""
        response = client.get("/api/v1/telemetry/device/99999/latest", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 404

    def test_get_telemetry_history_invalid_device_id(self, auth_token):
        """测试获取遥测历史数据无效设备ID"""
        response = client.get("/api/v1/telemetry/device/99999/history", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        # 设备不存在但可能有空数据返回
        assert response.status_code in [200, 404]

    def test_report_telemetry_battery_data(self, auth_token, test_station, test_db):
        """测试电池遥测数据上报"""
        db = test_db["session"]
        from app.models.device import Device, DeviceType, DeviceStatus
        battery = Device(
            sn="BATTERY-001",
            name="测试电池柜",
            type=DeviceType.BATTERY,
            status=DeviceStatus.ONLINE,
            station_id=test_station.id
        )
        db.add(battery)
        db.commit()
        db.refresh(battery)

        response = client.post("/api/v1/telemetry/report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "device_id": battery.id,
            "battery_voltage": 400.0,
            "battery_current": 25.0,
            "battery_soc": 75.0,
            "battery_soh": 95.0,
            "battery_temperature": 28.0
        })
        assert response.status_code == 200

    # ========== 批量上报跨表字段回归 ==========

    def test_batch_report_pv_ignores_cross_table_fields(self, auth_token, test_device, test_db):
        """回归: PV设备批量上报含充电桩/电池等跨表字段,应静默忽略并成功落库

        重现生产 bug: TelemetryReportLegacy 携带 charger_voltage 等字段,
        当 PV 设备路由到 TelemetryPV 时未过滤直接构造触发 TypeError,整批失败。
        """
        response = client.post("/api/v1/telemetry/batch-report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "records": [{
                "device_id": test_device.id,
                "grid_voltage_a": 220.5,
                "pv1_voltage": 400.0,
                "pv1_power": 5.0,
                # 跨表无关字段(属于 charger/battery schema)
                "charger_voltage": 400.0,
                "charger_current": 50.0,
                "battery_soc": 80.0,
                "gun_status": 1,
            }]
        })
        assert response.status_code == 200
        data = response.json()
        result = data.get("data", data)
        assert result.get("total_success") == 1

        # 验证落库 TelemetryPV 且有效字段写入
        db = test_db["session"]
        from app.models.telemetry_v2 import TelemetryPV
        records = db.query(TelemetryPV).filter(
            TelemetryPV.device_id == test_device.id
        ).all()
        assert len(records) == 1
        assert records[0].grid_voltage_a == 220.5
        assert records[0].pv1_voltage == 400.0
        assert records[0].pv1_power == 5.0
        # 无关字段被静默忽略(TelemetryPV 无这些列)
        assert not hasattr(records[0], "charger_voltage")

    def test_batch_report_mixed_pv_and_charger(self, auth_token, test_station, test_device, test_db):
        """回归: 混合批次(PV+charger)双向跨表字段,全部成功落库到各自专表"""
        db = test_db["session"]
        from app.models.device import Device, DeviceType, DeviceStatus
        charger = Device(
            sn="BATCH-CHG-001",
            name="批量测试充电桩",
            type=DeviceType.CHARGER_DC,
            status=DeviceStatus.ONLINE,
            station_id=test_station.id,
        )
        db.add(charger)
        db.commit()
        db.refresh(charger)

        response = client.post("/api/v1/telemetry/batch-report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "records": [
                {
                    "device_id": test_device.id,  # PV 设备
                    "grid_voltage_a": 220.0,
                    "pv1_power": 5.0,
                    "charger_voltage": 400.0,  # 跨表字段,应忽略
                },
                {
                    "device_id": charger.id,  # charger 设备
                    "charger_voltage": 400.0,
                    "charger_current": 50.0,
                    "pv1_voltage": 999.0,  # 跨表字段,应忽略
                },
            ]
        })
        assert response.status_code == 200
        data = response.json()
        result = data.get("data", data)
        assert result.get("total_success") == 2

        from app.models.telemetry_v2 import TelemetryPV, TelemetryCharger
        pv = db.query(TelemetryPV).filter(
            TelemetryPV.device_id == test_device.id
        ).all()
        chg = db.query(TelemetryCharger).filter(
            TelemetryCharger.device_id == charger.id
        ).all()
        assert len(pv) == 1
        assert pv[0].pv1_power == 5.0
        assert len(chg) == 1
        assert chg[0].charger_voltage == 400.0

    def test_batch_report_emits_timing_log(self, auth_token, test_device, test_db, caplog):
        """卡 f78a8e44: batch-report 请求结束输出含固定键的 timing 分段日志"""
        import logging
        caplog.set_level(logging.INFO, logger="app.core.timing_log")
        response = client.post("/api/v1/telemetry/batch-report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "records": [{
                "device_id": test_device.id,
                "grid_voltage_a": 220.0,
            }]
        })
        assert response.status_code == 200
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "endpoint=telemetry/batch-report" in msgs
        assert "batch_size=1" in msgs
        for key in ("total_ms", "auth_ms", "parse_ms", "insert_ms", "commit_ms"):
            assert f"{key}=" in msgs, f"timing 日志缺固定键: {key}"

    # ========== 毒记录隔离 / commit 失败降级（P1 data-safety）==========

    def test_batch_report_orphan_device_does_not_poison_batch(
        self, auth_token, test_station, test_db
    ):
        """孤儿设备(场站被裸 SQL 硬删,设备未清理)的遥测记录不得连坐同批健康记录。

        重现生产 P1: bulk_insert_mappings + 单次 commit 整批单事务, 任一记录 FK 违约
        (TelemetryPV.station_id nullable=False + FK→stations.id) → 整批回滚 500,
        健康设备遥测被同批毒记录连坐丢失。修复后预校验隔离孤儿, 健康记录正常落库。
        """
        from sqlalchemy import text
        from app.models.device import Device, DeviceType, DeviceStatus, ProtocolType
        from app.models.station import Station, StationStatus
        from app.models.telemetry_v2 import TelemetryPV

        db = test_db["session"]

        # 健康设备: 挂合法 station
        healthy = Device(
            sn="ORPHAN-HEALTHY", name="健康设备", type=DeviceType.PV_INVERTER,
            status=DeviceStatus.ONLINE, station_id=test_station.id,
            protocol_type=ProtocolType.MODBUS_RTU,
        )
        db.add(healthy)
        db.commit()
        db.refresh(healthy)

        # 孤儿设备: 先挂独立 station, commit 后裸 SQL 硬删 station
        # (绕过 ORM cascade="all, delete-orphan", device 行保留, station_id 变悬空)
        ghost_station = Station(
            name="将被硬删的站", code="GHOST-ST-ORPHAN", status=StationStatus.NORMAL,
        )
        db.add(ghost_station)
        db.commit()
        db.refresh(ghost_station)
        orphan = Device(
            sn="ORPHAN-DEV", name="孤儿设备", type=DeviceType.PV_INVERTER,
            status=DeviceStatus.ONLINE, station_id=ghost_station.id,
            protocol_type=ProtocolType.MODBUS_RTU,
        )
        db.add(orphan)
        db.commit()
        db.refresh(orphan)
        db.execute(text("DELETE FROM stations WHERE id = :sid"), {"sid": ghost_station.id})
        db.commit()
        db.expire_all()

        resp = client.post("/api/v1/telemetry/batch-report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "records": [
                {"device_id": healthy.id, "grid_voltage_a": 220.0, "pv1_power": 5.0},
                {"device_id": orphan.id, "grid_voltage_a": 221.0, "pv1_power": 6.0},
            ]
        })
        # 修复前: 整批 FK 违约 → 500; 修复后: 孤儿跳过, 健康落库 → 200
        assert resp.status_code == 200, f"孤儿记录不应连坐整批: {resp.text}"
        data = resp.json()["data"]
        assert data["total_success"] == 1, data
        # errors 明细含孤儿 device_id, 便于定位
        errs = " ".join(data["stats"]["errors"])
        assert str(orphan.id) in errs, errs

        # 健康记录确实落库
        healthy_rows = db.query(TelemetryPV).filter(
            TelemetryPV.device_id == healthy.id
        ).all()
        assert len(healthy_rows) == 1
        # 孤儿记录未落库
        orphan_rows = db.query(TelemetryPV).filter(
            TelemetryPV.device_id == orphan.id
        ).all()
        assert len(orphan_rows) == 0

    def test_batch_report_bulk_failure_falls_back_per_row(
        self, auth_token, test_device, test_db, monkeypatch
    ):
        """整批 commit 失败 → 降级逐条写入, 健康记录落库, 毒记录隔离记 errors。

        预校验之外的未知毒源(其他约束/类型违反)仍可能让整批 commit 抛错;
        except 后逐条 fallback 隔离毒记录, 最大化健康记录落库率, 不再整批回滚丢失。
        """
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session
        from app.models.device import Device, DeviceType, DeviceStatus
        from app.models.telemetry_v2 import TelemetryPV

        db = test_db["session"]
        # 第二个 PV 设备, 同 test_device 合法 station; 用作"毒源"
        poison = Device(
            sn="FALLBACK-POISON", name="毒源设备", type=DeviceType.PV_INVERTER,
            status=DeviceStatus.ONLINE, station_id=test_device.station_id,
        )
        db.add(poison)
        db.commit()
        db.refresh(poison)

        original_bulk = Session.bulk_insert_mappings

        def fake_bulk(self, mapper, mappings, **kw):
            # 整批(len>1)模拟约束违反触发降级; 逐条时仅毒源那条抛错, 其余真实写
            if len(mappings) > 1:
                raise IntegrityError(
                    "simulated batch insert", {}, Exception("batch constraint violation"),
                )
            if mappings and mappings[0].get("device_id") == poison.id:
                raise IntegrityError(
                    "simulated poison row", {}, Exception("poison row constraint"),
                )
            return original_bulk(self, mapper, mappings, **kw)

        monkeypatch.setattr(Session, "bulk_insert_mappings", fake_bulk)

        resp = client.post("/api/v1/telemetry/batch-report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "records": [
                {"device_id": test_device.id, "grid_voltage_a": 220.0, "pv1_power": 5.0},
                {"device_id": poison.id, "grid_voltage_a": 221.0, "pv1_power": 6.0},
            ]
        })
        # 修复前: 整批失败冒泡 500; 修复后: 降级逐条, 健康落库, 毒源隔离 → 200
        assert resp.status_code == 200, f"降级路径应返回200: {resp.text}"
        data = resp.json()["data"]
        assert data["total_success"] == 1, data
        errs = " ".join(data["stats"]["errors"])
        assert str(poison.id) in errs, errs

        # 健康记录落库, 毒源未落库
        healthy_rows = db.query(TelemetryPV).filter(
            TelemetryPV.device_id == test_device.id
        ).all()
        poison_rows = db.query(TelemetryPV).filter(
            TelemetryPV.device_id == poison.id
        ).all()
        assert len(healthy_rows) == 1
        assert len(poison_rows) == 0

    def test_batch_report_failure_log_includes_device_id(
        self, auth_token, test_device, test_db, monkeypatch, caplog
    ):
        """失败路径 logger.error 必须携带 device_id 列表, 便于运维定位毒源。

        整批失败时记录该表全部 device_ids; 逐条失败时记录单条 device_id。
        """
        import logging
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session
        from app.models.device import Device, DeviceType, DeviceStatus

        db = test_db["session"]
        dev2 = Device(
            sn="LOG-DEV", name="日志定位设备", type=DeviceType.PV_INVERTER,
            status=DeviceStatus.ONLINE, station_id=test_device.station_id,
        )
        db.add(dev2)
        db.commit()
        db.refresh(dev2)

        original_bulk = Session.bulk_insert_mappings

        def fake_bulk(self, mapper, mappings, **kw):
            # 整批抛错触发降级日志(记录全部 device_ids); 逐条全部成功
            if len(mappings) > 1:
                raise IntegrityError("simulated batch", {}, Exception("batch fail"))
            return original_bulk(self, mapper, mappings, **kw)

        monkeypatch.setattr(Session, "bulk_insert_mappings", fake_bulk)

        caplog.set_level(logging.ERROR)
        resp = client.post("/api/v1/telemetry/batch-report", headers={
            "Authorization": f"Bearer {auth_token}"
        }, json={
            "records": [
                {"device_id": test_device.id, "grid_voltage_a": 220.0},
                {"device_id": dev2.id, "grid_voltage_a": 221.0},
            ]
        })
        assert resp.status_code == 200, resp.text
        msgs = " ".join(r.getMessage() for r in caplog.records)
        # 整批失败日志须含两条记录的 device_id, 便于定位
        assert str(test_device.id) in msgs, f"日志缺 device_id {test_device.id}: {msgs}"
        assert str(dev2.id) in msgs, f"日志缺 device_id {dev2.id}: {msgs}"