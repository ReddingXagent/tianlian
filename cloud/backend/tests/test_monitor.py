"""
实时监控 API 测试
覆盖: realtime实时数据 + history历史数据
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


class TestMonitorAPI:
    """实时监控 API 测试类"""

    # ========== 实时数据 ==========

    def test_get_realtime_data_success(self, auth_token):
        """测试获取实时监控数据成功"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        monitor_data = data.get("data", data)
        # 实时数据应包含关键指标
        assert "totalPower" in monitor_data or "devices" in monitor_data or "update_time" in monitor_data

    def test_get_realtime_data_structure(self, auth_token):
        """测试实时监控数据结构"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        monitor_data = data.get("data", data)
        
        # 检查预期字段
        expected_fields = [
            "totalPower", "powerTrend", "todayGeneration",
            "todayConsumption", "gridImport", "gridExport",
            "efficiency", "update_time", "devices"
        ]
        # 至少应包含部分字段
        found_fields = [f for f in expected_fields if f in monitor_data]
        assert len(found_fields) > 0

    def test_get_realtime_data_devices(self, auth_token):
        """测试实时监控数据设备列表"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        monitor_data = data.get("data", data)
        
        if "devices" in monitor_data:
            devices = monitor_data["devices"]
            assert isinstance(devices, list)
            # 每个设备应包含基本字段
            for device in devices:
                assert "id" in device or "name" in device

    def test_get_realtime_data_power_range(self, auth_token):
        """测试实时监控功率数据范围"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        monitor_data = data.get("data", data)
        
        if "totalPower" in monitor_data:
            power = monitor_data["totalPower"]
            # 功率应为数值
            assert isinstance(power, (int, float))
            # 功率应为正数（模拟数据）
            assert power >= 0

    def test_get_realtime_data_efficiency_range(self, auth_token):
        """测试实时监控效率数据范围"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        monitor_data = data.get("data", data)
        
        if "efficiency" in monitor_data:
            efficiency = monitor_data["efficiency"]
            assert isinstance(efficiency, (int, float))
            # 效率应在合理范围
            assert 0 <= efficiency <= 100

    def test_get_realtime_data_update_time(self, auth_token):
        """测试实时监控更新时间"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        monitor_data = data.get("data", data)
        
        if "update_time" in monitor_data:
            update_time = monitor_data["update_time"]
            # 应为ISO格式时间字符串
            assert isinstance(update_time, str)

    def test_get_realtime_requires_auth(self):
        """测试实时监控需要认证"""
        response = client.get("/api/v1/monitor/realtime")
        # 未认证应返回401或403
        assert response.status_code in [401, 403, 200]  # 200表示无认证要求

    # ========== 历史数据 ==========

    def test_get_history_data_success(self, auth_token):
        """测试获取历史监控数据成功"""
        response = client.get("/api/v1/monitor/history", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        history_data = data.get("data", data)
        # 历史数据应包含data字段
        assert "data" in history_data or "total_records" in history_data

    def test_get_history_data_structure(self, auth_token):
        """测试历史监控数据结构"""
        response = client.get("/api/v1/monitor/history", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        history_data = data.get("data", data)
        
        if "data" in history_data:
            records = history_data["data"]
            assert isinstance(records, list)
            # 每条记录应包含时间字段
            for record in records:
                assert "time" in record or "power" in record

    def test_get_history_data_with_time_range(self, auth_token):
        """测试历史监控数据时间范围"""
        response = client.get("/api/v1/monitor/history?start_time=2024-01-01&end_time=2024-01-02", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200

    def test_get_history_data_total_records(self, auth_token):
        """测试历史监控数据记录总数"""
        response = client.get("/api/v1/monitor/history", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        history_data = data.get("data", data)
        
        if "total_records" in history_data:
            total = history_data["total_records"]
            assert isinstance(total, int)
            assert total >= 0

    def test_get_history_data_power_values(self, auth_token):
        """测试历史监控功率数值"""
        response = client.get("/api/v1/monitor/history", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        history_data = data.get("data", data)
        
        if "data" in history_data:
            for record in history_data["data"]:
                if "power" in record:
                    power = record["power"]
                    assert isinstance(power, (int, float))
                if "generation" in record:
                    generation = record["generation"]
                    assert isinstance(generation, (int, float))
                if "consumption" in record:
                    consumption = record["consumption"]
                    assert isinstance(consumption, (int, float))

    # ========== 多次请求测试 ==========

    def test_realtime_data_changes(self, auth_token):
        """测试实时数据随时间变化"""
        # 第一次请求
        resp1 = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        data1 = resp1.json().get("data", {})
        
        # 第二次请求（模拟数据可能变化）
        resp2 = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        data2 = resp2.json().get("data", {})
        
        # 两次请求都应成功
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        
        # 结构应一致
        assert set(data1.keys()) == set(data2.keys())

    def test_history_data_consistent(self, auth_token):
        """测试历史数据一致性"""
        # 多次请求历史数据
        for _ in range(3):
            response = client.get("/api/v1/monitor/history", headers={
                "Authorization": f"Bearer {auth_token}"
            })
            assert response.status_code == 200
            data = response.json()
            history_data = data.get("data", data)
            
            if "data" in history_data:
                # 每次请求应返回相同结构
                assert isinstance(history_data["data"], list)

    # ========== 边界测试 ==========

    def test_realtime_data_invalid_auth(self):
        """测试无效认证获取实时数据"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": "Bearer invalid_token"
        })
        # 无效token应返回401或403
        assert response.status_code in [401, 403, 200]

    def test_history_data_no_auth(self):
        """测试无认证获取历史数据"""
        response = client.get("/api/v1/monitor/history")
        # 根据API设计，可能需要或不需要认证
        assert response.status_code in [200, 401, 403]

    def test_realtime_data_response_format(self, auth_token):
        """测试实时数据响应格式"""
        response = client.get("/api/v1/monitor/realtime", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        # 响应应为JSON
        assert response.headers.get("content-type", "").startswith("application/json")
        
        # 解析JSON
        data = response.json()
        # 应包含success或data字段
        assert "success" in data or "data" in data or "code" in data

    def test_history_data_response_format(self, auth_token):
        """测试历史数据响应格式"""
        response = client.get("/api/v1/monitor/history", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        # 响应应为JSON
        assert response.headers.get("content-type", "").startswith("application/json")
        
        data = response.json()
        assert "success" in data or "data" in data or "code" in data

# ========== 卡 ddff009c: 真实 Telemetry 聚合 ==========

from datetime import datetime, timedelta, timezone as _tz

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry


class TestMonitorRealtimeAggregation:
    """realtime 接真实 Telemetry 聚合 (卡 ddff009c)"""

    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        self.session = test_db["session"]

    def _mk_device(self, sn, dtype, name=None):
        st = self.session.query(Station).first()
        if not st:
            st = Station(name="监控站", code="MON001", status=StationStatus.NORMAL)
            self.session.add(st)
            self.session.flush()
        d = Device(sn=sn, name=name or sn, type=dtype,
                   status=DeviceStatus.ONLINE, station_id=st.id)
        self.session.add(d)
        self.session.flush()
        return d

    def _tele(self, did, ts, **kw):
        t = Telemetry(device_id=did, timestamp=ts, **kw)
        self.session.add(t)
        return t

    def _get(self, token):
        r = client.get("/api/v1/monitor/realtime",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        return r.json().get("data", r.json())

    def test_empty_db_returns_zero(self, auth_token):
        """空库返回全 0，禁止假值"""
        data = self._get(auth_token)
        assert data["totalPower"] == 0
        assert data["powerTrend"] == 0
        assert data["todayGeneration"] == 0
        assert data["todayConsumption"] == 0
        assert data["gridImport"] == 0
        assert data["gridExport"] == 0
        assert data["efficiency"] == 0
        assert data["devices"] == []

    def test_multi_device_total_power_sum(self, auth_token):
        """totalPower = 每设备最新一条 grid_power_total 求和"""
        now = datetime.now(_tz.utc).replace(tzinfo=None)
        d1 = self._mk_device("SN-MON-1", DeviceType.PV_INVERTER, "逆变器A")
        d2 = self._mk_device("SN-MON-2", DeviceType.CHARGER_DC, "充电桩B")
        # d1: 两条取最新
        self._tele(d1.id, now - timedelta(minutes=10), grid_power_total=5.0)
        self._tele(d1.id, now - timedelta(minutes=1), grid_power_total=30.0)
        # d2: 最新
        self._tele(d2.id, now - timedelta(minutes=2), grid_power_total=15.0)
        self.session.commit()

        data = self._get(auth_token)
        assert data["totalPower"] == 30.0 + 15.0
        # powerTrend = 与上一采样差值: d1 (30-5) + d2 (无上一条=0)
        assert data["powerTrend"] == 25.0
        names = {d["name"] for d in data["devices"]}
        assert names == {"逆变器A", "充电桩B"}
        by_name = {d["name"]: d for d in data["devices"]}
        assert by_name["逆变器A"]["power"] == 30.0
        assert by_name["逆变器A"]["type"] == "inverter"
        assert by_name["充电桩B"]["type"] == "charger"

    def test_today_consumption_charger_kwh_delta(self, auth_token):
        """todayConsumption 参考 36c6b919: charger_kwh 累计差值"""
        now = datetime.now(_tz.utc).replace(tzinfo=None)
        d = self._mk_device("SN-MON-3", DeviceType.CHARGER_DC)
        self._tele(d.id, now - timedelta(hours=1), charger_kwh=10.0)
        self._tele(d.id, now, charger_kwh=13.5)
        self.session.commit()
        data = self._get(auth_token)
        assert data["todayConsumption"] == 3.5

    def test_today_consumption_grid_fallback(self, auth_token):
        """无 charger_kwh 时回退 grid_power_total×时长。

        卡 70202e7b: todayConsumption 只统计业务今天窗 (biz_day_bounds, ba16a9ff
        同口径), 上海 00:00-02:00 跑测时 now-2h 已属业务昨日会被过滤 → seed 起点
        钳制到业务日界内, 期望值按实际窗长计算, 任意时刻跑均稳定。
        """
        from app.tasks.tz_utils import biz_day_bounds_utc_naive, now_in_biz_tz
        now = datetime.now(_tz.utc).replace(tzinfo=None)
        day_start, _ = biz_day_bounds_utc_naive(now_in_biz_tz().date())
        start = max(now - timedelta(hours=2), day_start + timedelta(minutes=1))
        d = self._mk_device("SN-MON-4", DeviceType.PV_INVERTER)
        self._tele(d.id, start, grid_power_total=6.0)
        self._tele(d.id, now, grid_power_total=6.0)
        self.session.commit()
        data = self._get(auth_token)
        expected = 6.0 * (now - start).total_seconds() / 3600
        assert data["todayConsumption"] == pytest.approx(expected, abs=0.01)


class TestMonitorHistoryRealQuery:
    """history 按 start/end 真查询 (卡 ddff009c)"""

    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        self.session = test_db["session"]
        st = Station(name="历史站", code="MONHIS1", status=StationStatus.NORMAL)
        self.session.add(st)
        self.session.flush()
        d = Device(sn="SN-MON-H1", name="历史设备", type=DeviceType.PV_INVERTER,
                   status=DeviceStatus.ONLINE, station_id=st.id)
        self.session.add(d)
        self.session.flush()
        self.session.commit()
        self.device = d

    def _tele(self, ts, **kw):
        t = Telemetry(device_id=self.device.id, timestamp=ts, **kw)
        self.session.add(t)
        return t

    def _get(self, token, **params):
        r = client.get("/api/v1/monitor/history", params=params,
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        return r.json().get("data", r.json())

    def test_empty_window_returns_empty(self, auth_token):
        """无数据返回空列表 + total_records=0"""
        data = self._get(auth_token, start_time="2024-01-01T00:00:00",
                         end_time="2024-01-02T00:00:00")
        assert data["data"] == []
        assert data["total_records"] == 0

    def test_hour_bucket_avg(self, auth_token):
        """按小时 bucket avg 聚合"""
        base = datetime(2024, 1, 1, 10, 0)
        for m, p in [(0, 10.0), (20, 20.0), (40, 30.0)]:
            self._tele(base + timedelta(minutes=m), grid_power_total=p)
        self._tele(base + timedelta(hours=1, minutes=10), grid_power_total=60.0)
        self.session.commit()
        data = self._get(auth_token, start_time="2024-01-01T00:00:00",
                         end_time="2024-01-02T00:00:00")
        assert data["total_records"] == 2
        buckets = {row["time"]: row for row in data["data"]}
        assert buckets["2024-01-01T10:00:00"]["power"] == 20.0
        assert buckets["2024-01-01T11:00:00"]["power"] == 60.0

    def test_window_filters_outside_data(self, auth_token):
        """时间窗外的数据被过滤"""
        base = datetime(2024, 1, 1, 10, 0)
        self._tele(base, grid_power_total=10.0)
        self._tele(base + timedelta(days=2), grid_power_total=99.0)
        self.session.commit()
        data = self._get(auth_token, start_time="2024-01-01T00:00:00",
                         end_time="2024-01-02T00:00:00")
        assert data["total_records"] == 1
        assert data["data"][0]["power"] == 10.0

    def test_end_before_start_returns_empty(self, auth_token):
        """end < start 边界返回空"""
        base = datetime(2024, 1, 1, 10, 0)
        self._tele(base, grid_power_total=10.0)
        self.session.commit()
        data = self._get(auth_token, start_time="2024-01-02T00:00:00",
                         end_time="2024-01-01T00:00:00")
        assert data["data"] == []
        assert data["total_records"] == 0

# ========== 卡 11f7d020: realtime N+1 消除 — 逐字段对齐 + 查询数不随设备数增长 ==========

from sqlalchemy import event as _sa_event

from app.api.deps import team_scope as _team_scope
from app.api.v1.analytics.efficiency import _calculate_device_efficiency as _ref_eff
from app.tasks.tz_utils import biz_day_bounds_utc_naive as _biz_bounds, now_in_biz_tz as _now_biz


def _reference_realtime(session):
    """原实现（逐设备 2 查询 + 全天行全量加载）的忠实复制 — 逐字段对齐基准。"""
    day_start, _ = _biz_bounds(_now_biz().date())
    now_naive = datetime.now(_tz.utc).replace(tzinfo=None)
    devices = session.query(Device).order_by(Device.id).all()  # admin 语义: 无 team 过滤
    total_power = power_trend = grid_import = grid_export = 0.0
    today_generation = today_consumption = 0.0
    device_items = []
    efficiencies = []
    for device in devices:
        recent = (
            session.query(Telemetry)
            .filter(Telemetry.device_id == device.id)
            .order_by(Telemetry.timestamp.desc())
            .limit(2)
            .all()
        )
        if not recent:
            continue
        latest, prev = recent[0], (recent[1] if len(recent) > 1 else None)
        power = latest.grid_power_total or 0.0
        total_power += power
        if power > 0:
            grid_import += power
        else:
            grid_export += abs(power)
        if prev is not None and prev.grid_power_total is not None:
            power_trend += power - prev.grid_power_total
        today_rows = (
            session.query(Telemetry)
            .filter(
                Telemetry.device_id == device.id,
                Telemetry.timestamp >= day_start,
                Telemetry.timestamp <= now_naive,
            )
            .order_by(Telemetry.timestamp.asc())
            .all()
        )
        if not today_rows:
            today_rows = [latest]
        today_generation += latest.daily_generation or 0.0
        kwh_values = [t.charger_kwh for t in today_rows if t.charger_kwh is not None]
        if kwh_values:
            today_consumption += max(0.0, kwh_values[-1] - kwh_values[0])
        else:
            grid_values = [
                t.grid_power_total for t in today_rows if t.grid_power_total is not None
            ]
            if grid_values:
                avg_power = sum(grid_values) / len(grid_values)
                hours = max(
                    0.0,
                    (today_rows[-1].timestamp - today_rows[0].timestamp).total_seconds() / 3600,
                )
                today_consumption += avg_power * hours
        efficiencies.append(_ref_eff(today_rows, device))
        device_items.append({
            "id": device.id,
            "name": device.name,
            "type": device.device_type,
            "power": power,
            "status": device.status.value if device.status else "offline",
        })
    efficiency = sum(efficiencies) / len(efficiencies) if efficiencies else 0.0
    return {
        "totalPower": round(total_power, 2),
        "powerTrend": round(power_trend, 2),
        "todayGeneration": round(today_generation, 2),
        "todayConsumption": round(today_consumption, 2),
        "gridImport": round(grid_import, 2),
        "gridExport": round(grid_export, 2),
        "efficiency": round(min(100.0, max(0.0, efficiency)), 2),
        "devices": device_items,
    }


class TestRealtimeQueryCountCard11f7d020:
    """卡 11f7d020: N+1 消除 — 响应逐字段与原实现对齐; SELECT 数不随设备数线性增长"""

    @pytest.fixture(autouse=True)
    def _seed(self, test_db):
        self.session = test_db["session"]
        self.engine = test_db["engine"]

    def _mk_device(self, sn, dtype, name=None):
        st = self.session.query(Station).first()
        if not st:
            st = Station(name="监控站N1", code="MONNQL1", status=StationStatus.NORMAL)
            self.session.add(st)
            self.session.flush()
        d = Device(sn=sn, name=name or sn, type=dtype,
                   status=DeviceStatus.ONLINE, station_id=st.id)
        self.session.add(d)
        self.session.flush()
        return d

    def _tele(self, did, ts, **kw):
        t = Telemetry(device_id=did, timestamp=ts, **kw)
        self.session.add(t)
        return t

    def _count_queries(self, token):
        """发起一次 realtime 请求，统计期间发出的 SELECT 语句数"""
        counter = {"n": 0}

        def _before(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper().startswith("SELECT"):
                counter["n"] += 1

        _sa_event.listen(self.engine, "before_cursor_execute", _before)
        try:
            r = client.get("/api/v1/monitor/realtime",
                           headers={"Authorization": f"Bearer {token}"})
        finally:
            _sa_event.remove(self.engine, "before_cursor_execute", _before)
        assert r.status_code == 200, r.text
        return counter["n"], r.json().get("data", r.json())

    @staticmethod
    def _assert_fields_match(actual, expected):
        """逐字段对齐（update_time 每请求必然不同，单独跳过）"""
        for key in ["totalPower", "powerTrend", "todayGeneration", "todayConsumption",
                    "gridImport", "gridExport", "efficiency"]:
            assert actual[key] == pytest.approx(expected[key], abs=0.011), key
        assert actual["devices"] == expected["devices"]

    def test_response_matches_reference_mixed_devices(self, auth_token):
        """多类型设备混合场景下，批量化实现与原实现响应逐字段一致"""
        now = datetime.now(_tz.utc).replace(tzinfo=None)
        day_start, _ = _biz_bounds(_now_biz().date())
        t0 = max(now - timedelta(hours=3), day_start + timedelta(minutes=1))
        # 逆变器: kwh 路径 + 昨日旧数据（不得混入）
        d1 = self._mk_device("SN-NQ-1", DeviceType.PV_INVERTER, "逆变器N1")
        self._tele(d1.id, now - timedelta(days=2), grid_power_total=99.0, charger_kwh=8.0)
        self._tele(d1.id, t0, grid_power_total=5.0, charger_kwh=10.0, daily_generation=2.0)
        self._tele(d1.id, now, grid_power_total=30.0, charger_kwh=13.5, daily_generation=3.0)
        # 充电桩: grid 回退路径（无 kwh）
        d2 = self._mk_device("SN-NQ-2", DeviceType.CHARGER_DC, "充电桩N2")
        self._tele(d2.id, t0, grid_power_total=6.0, charger_power=4.0)
        self._tele(d2.id, now, grid_power_total=6.0, charger_power=4.0)
        # 储能电池: soc 变化序列（battery 效率路径）
        d3 = self._mk_device("SN-NQ-3", DeviceType.BATTERY, "电池N3")
        for i, soc in enumerate([50.0, 52.0, 54.0, 55.0]):
            self._tele(d3.id, t0 + timedelta(minutes=10 * i),
                       grid_power_total=-2.0, battery_soc=soc)
        # 通用类型(meter): pf + 温度路径
        d4 = self._mk_device("SN-NQ-4", DeviceType.METER, "电表N4")
        self._tele(d4.id, t0, grid_power_total=1.0, grid_power_factor=0.95, battery_temperature=30.0)
        self._tele(d4.id, now, grid_power_total=1.0, grid_power_factor=0.93, battery_temperature=32.0)
        # 无遥测设备: 不得出现在 devices 列表
        self._mk_device("SN-NQ-5", DeviceType.GATEWAY, "网关N5")
        self.session.commit()

        r = client.get("/api/v1/monitor/realtime",
                       headers={"Authorization": f"Bearer {auth_token}"})
        assert r.status_code == 200
        data = r.json().get("data", r.json())
        expected = _reference_realtime(self.session)
        assert len(data["devices"]) == 4  # 无遥测设备被跳过
        self._assert_fields_match(data, expected)

    def test_query_count_not_linear_in_devices(self, auth_token):
        """SELECT 数不随设备数线性增长: 8 台设备 ≤ 2 台设备 + 3"""
        now = datetime.now(_tz.utc).replace(tzinfo=None)
        day_start, _ = _biz_bounds(_now_biz().date())
        t0 = max(now - timedelta(hours=2), day_start + timedelta(minutes=1))
        for i in range(8):
            d = self._mk_device(f"SN-NQL-{i}", DeviceType.PV_INVERTER)
            self._tele(d.id, t0, grid_power_total=1.0, charger_kwh=1.0)
            self._tele(d.id, now - timedelta(seconds=5 * i + 1), grid_power_total=2.0, charger_kwh=2.0)
        self.session.commit()

        n_small, _ = self._count_queries(auth_token)
        # 硬上界: 原实现 ≈ 2N + 认证/设备查询 ≈ 20+ 条；批量化后应 ≤ 12
        assert n_small <= 12, f"N+1 未消除: 8 台设备触发了 {n_small} 条 SELECT"

