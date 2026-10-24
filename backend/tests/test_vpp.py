"""
虚拟电厂(VPP)调度优化 测试
- VPPOptimizer 核心算法测试
- MultiStationCoordinator 站点管理测试
- API端点测试
"""
import pytest
from datetime import datetime
from unittest.mock import patch

from app.services.vpp.dispatch_optimizer import (
    VPPOptimizer,
    MultiStationCoordinator,
    ResourceType,
    DispatchMode,
    GridSignalType,
    GridSignal,
    StationStatus,
    ResourceCapability,
    DispatchCommand,
    DispatchPlan,
)


# ─── Fixtures ───

def make_station(sid="ST-001", name="测试站A", pv=200, battery=500, load=100, pv_out=120, soc=0.7, dispatch=200, online=True):
    return StationStatus(
        station_id=sid, station_name=name,
        total_pv_kw=pv, total_battery_kwh=battery, total_ev_chargers=10,
        current_load_kw=load, current_pv_output_kw=pv_out,
        current_battery_soc=soc, available_dispatch_kw=dispatch, online=online,
    )


def make_battery_resource(rid="ST-001-BAT", sid="ST-001", rated=250, available=200, soc=0.7, priority=2):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.BATTERY, station_id=sid,
        rated_power_kw=rated, current_power_kw=0, available_power_kw=available,
        soc=soc, efficiency=0.95, priority=priority,
    )


def make_ev_resource(rid="ST-001-EV", sid="ST-001", rated=140, current=80, available=40, priority=3):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.EV_CHARGER, station_id=sid,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def make_load_resource(rid="ST-001-LOAD", sid="ST-001", rated=50, current=30, available=15, priority=4):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.LOAD, station_id=sid,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


def make_pv_resource(rid="ST-001-PV", sid="ST-001", rated=200, current=120, available=120, priority=5):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.PV, station_id=sid,
        rated_power_kw=rated, current_power_kw=current, available_power_kw=available,
        priority=priority,
    )


# ─── VPPOptimizer 核心算法测试 ───

class TestVPPOptimizer:
    """VPPOptimizer 核心算法测试"""

    def setup_method(self):
        self.optimizer = VPPOptimizer()

    # 电价测试
    def test_get_price_valley_night(self):
        """低谷电价(23:00-6:00)"""
        assert self.optimizer.get_current_price(0.5) == 0.3
        assert self.optimizer.get_current_price(3.0) == 0.3
        assert self.optimizer.get_current_price(23.5) == 0.3

    def test_get_price_peak(self):
        """尖峰电价(10:00-12:00)"""
        assert self.optimizer.get_current_price(10.5) == 1.2
        assert self.optimizer.get_current_price(11.5) == 1.2

    def test_get_price_high(self):
        """高峰电价(8:00-10:00, 18:00-21:00)"""
        assert self.optimizer.get_current_price(9.0) == 0.9
        assert self.optimizer.get_current_price(19.0) == 0.9

    def test_get_price_flat(self):
        """平段电价"""
        assert self.optimizer.get_current_price(7.0) == 0.6
        assert self.optimizer.get_current_price(14.0) == 0.6
        assert self.optimizer.get_current_price(22.0) == 0.6

    # 经济调度测试
    @patch.object(VPPOptimizer, 'get_current_price', return_value=0.9)
    def test_economic_dispatch_high_price_discharge(self, mock_price):
        """高电价时储能应放电"""
        stations = [make_station()]
        resources = [make_battery_resource(soc=0.8, available=200)]
        plan = self.optimizer.optimize_economic_dispatch(stations, resources)

        assert plan.mode == DispatchMode.ECONOMIC
        assert len(plan.commands) > 0
        # 储能放电: target_power_kw > 0
        bat_cmd = [c for c in plan.commands if c.resource_type == ResourceType.BATTERY]
        assert len(bat_cmd) > 0
        assert bat_cmd[0].target_power_kw > 0

    @patch.object(VPPOptimizer, 'get_current_price', return_value=0.3)
    def test_economic_dispatch_valley_charge(self, mock_price):
        """低谷电价时储能应充电"""
        stations = [make_station()]
        resources = [make_battery_resource(soc=0.3, available=200)]
        plan = self.optimizer.optimize_economic_dispatch(stations, resources)

        bat_cmd = [c for c in plan.commands if c.resource_type == ResourceType.BATTERY]
        assert len(bat_cmd) > 0
        # 充电: target_power_kw < 0
        assert bat_cmd[0].target_power_kw < 0

    def test_economic_dispatch_pv_no_command(self):
        """光伏不调度，不产生指令"""
        stations = [make_station()]
        resources = [make_pv_resource()]
        plan = self.optimizer.optimize_economic_dispatch(stations, resources)

        pv_cmd = [c for c in plan.commands if c.resource_type == ResourceType.PV]
        assert len(pv_cmd) == 0

    # 削峰填谷测试
    def test_peak_shaving_below_threshold(self):
        """负荷低于阈值时无需调度"""
        stations = [make_station(load=100)]
        resources = [make_battery_resource()]
        plan = self.optimizer.optimize_peak_shaving(stations, resources, peak_threshold_kw=500)

        assert plan.total_dispatch_kw == 0
        assert len(plan.commands) == 0

    def test_peak_shaving_above_threshold(self):
        """负荷超阈值时储能放电"""
        stations = [make_station(load=600), make_station(sid="ST-002", name="站B", load=400)]
        resources = [make_battery_resource(available=300, soc=0.8)]
        plan = self.optimizer.optimize_peak_shaving(stations, resources, peak_threshold_kw=500)

        total_load = 600 + 400  # 1000 > 500
        assert total_load > 500
        assert plan.mode == DispatchMode.PEAK_SHAVING
        # 应该有放电指令
        discharge_cmds = [c for c in plan.commands if c.target_power_kw > 0]
        assert len(discharge_cmds) > 0

    def test_peak_shaving_low_soc_skip(self):
        """SOC过低时储能不放电"""
        stations = [make_station(load=600)]
        resources = [make_battery_resource(soc=0.05, available=200)]  # SOC < 0.10 + 0.1
        plan = self.optimizer.optimize_peak_shaving(stations, resources, peak_threshold_kw=300)

        bat_cmds = [c for c in plan.commands if c.resource_type == ResourceType.BATTERY]
        assert len(bat_cmds) == 0

    # 需求响应测试
    def test_demand_response_basic(self):
        """基本需求响应"""
        stations = [make_station()]
        resources = [make_battery_resource(soc=0.8, available=200)]
        signal = GridSignal(
            signal_type=GridSignalType.DEMAND_RESPONSE,
            timestamp=datetime.now(),
            target_power_kw=100,
            duration_min=30,
            reward_per_kwh=0.5,
        )
        plan = self.optimizer.handle_demand_response(stations, resources, signal)

        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        assert len(plan.commands) > 0
        assert plan.total_dispatch_kw > 0

    def test_demand_response_with_ev_and_load(self):
        """需求响应-储能不足时利用充电桩和负荷"""
        stations = [make_station()]
        resources = [
            make_battery_resource(soc=0.05, available=10),  # SOC太低
            make_ev_resource(current=80),
            make_load_resource(available=30),
        ]
        signal = GridSignal(
            signal_type=GridSignalType.DEMAND_RESPONSE,
            timestamp=datetime.now(),
            target_power_kw=100,
            duration_min=30,
            reward_per_kwh=0.8,
        )
        plan = self.optimizer.handle_demand_response(stations, resources, signal)

        # 应该利用EV和LOAD来响应
        ev_cmds = [c for c in plan.commands if c.resource_type == ResourceType.EV_CHARGER]
        load_cmds = [c for c in plan.commands if c.resource_type == ResourceType.LOAD]
        assert len(ev_cmds) > 0 or len(load_cmds) > 0

    # 多站点协同测试
    def test_multi_station_coordination(self):
        """多站点协同调度"""
        stations = [
            make_station(sid="ST-001", load=200, pv_out=50, dispatch=100),  # 缺电
            make_station(sid="ST-002", load=50, pv_out=200, dispatch=150),  # 余电
        ]
        resources = [
            make_battery_resource(rid="ST-001-BAT", sid="ST-001", soc=0.3, available=50),
            make_battery_resource(rid="ST-002-BAT", sid="ST-002", soc=0.8, available=150),
        ]
        plan = self.optimizer.optimize_multi_station_coordination(stations, resources)

        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert len(plan.stations_involved) > 0


# ─── MultiStationCoordinator 测试 ───

class TestMultiStationCoordinator:
    """多站点协同调度器测试"""

    def setup_method(self):
        self.coordinator = MultiStationCoordinator()

    def test_register_station(self):
        """站点注册"""
        station = make_station()
        self.coordinator.register_station(station)
        assert "ST-001" in self.coordinator.stations
        assert self.coordinator.stations["ST-001"].station_name == "测试站A"

    def test_unregister_station(self):
        """站点注销"""
        station = make_station()
        self.coordinator.register_station(station)
        self.coordinator.unregister_station("ST-001")
        assert "ST-001" not in self.coordinator.stations

    def test_register_resource(self):
        """资源注册"""
        resource = make_battery_resource()
        self.coordinator.register_resource(resource)
        assert "ST-001-BAT" in self.coordinator.resources

    def test_update_station_status(self):
        """更新站点状态"""
        station = make_station(load=100)
        self.coordinator.register_station(station)
        self.coordinator.update_station_status("ST-001", current_load_kw=200, online=False)
        assert self.coordinator.stations["ST-001"].current_load_kw == 200
        assert self.coordinator.stations["ST-001"].online is False

    def test_aggregate_capacity(self):
        """聚合容量计算"""
        self.coordinator.register_station(make_station(sid="ST-001", pv=200, battery=500, load=100, pv_out=120, soc=0.7, dispatch=200))
        self.coordinator.register_station(make_station(sid="ST-002", name="站B", pv=150, battery=400, load=80, pv_out=100, soc=0.6, dispatch=150))
        self.coordinator.register_resource(make_battery_resource(rid="ST-001-BAT", soc=0.7))
        self.coordinator.register_resource(make_battery_resource(rid="ST-002-BAT", sid="ST-002", soc=0.6))

        cap = self.coordinator.get_aggregate_capacity()
        assert cap['online_stations'] == 2
        assert cap['total_pv_kw'] == 350
        assert cap['total_battery_kwh'] == 900
        assert cap['current_load_kw'] == 180
        assert cap['current_pv_output_kw'] == 220
        assert 0 < cap['avg_battery_soc'] < 1

    def test_aggregate_capacity_offline(self):
        """离线站点不计入在线统计"""
        self.coordinator.register_station(make_station(sid="ST-001", online=True))
        self.coordinator.register_station(make_station(sid="ST-002", name="站B", online=False))
        cap = self.coordinator.get_aggregate_capacity()
        assert cap['online_stations'] == 1
        assert cap['total_stations'] == 2

    def test_dispatch_economic(self):
        """经济调度"""
        self.coordinator.register_station(make_station())
        self.coordinator.register_resource(make_battery_resource(soc=0.7, available=200))
        plan = self.coordinator.dispatch_economic()

        assert plan is not None
        assert plan.mode == DispatchMode.ECONOMIC
        assert len(self.coordinator.dispatch_history) == 1

    def test_dispatch_peak_shaving(self):
        """削峰填谷"""
        self.coordinator.register_station(make_station(load=600))
        self.coordinator.register_resource(make_battery_resource(soc=0.7, available=300))
        plan = self.coordinator.dispatch_peak_shaving(threshold_kw=300)

        assert plan.mode == DispatchMode.PEAK_SHAVING

    def test_dispatch_demand_response(self):
        """需求响应"""
        self.coordinator.register_station(make_station())
        self.coordinator.register_resource(make_battery_resource(soc=0.8, available=200))
        signal = GridSignal(
            signal_type=GridSignalType.DEMAND_RESPONSE,
            timestamp=datetime.now(),
            target_power_kw=100,
            duration_min=30,
            reward_per_kwh=0.5,
        )
        plan = self.coordinator.dispatch_demand_response(signal)
        assert plan.mode == DispatchMode.DEMAND_RESPONSE

    def test_dispatch_multi_station(self):
        """多站点协同"""
        self.coordinator.register_station(make_station(sid="ST-001", load=200, pv_out=50))
        self.coordinator.register_station(make_station(sid="ST-002", name="站B", load=50, pv_out=200))
        self.coordinator.register_resource(make_battery_resource(soc=0.7, available=100))
        self.coordinator.register_resource(make_battery_resource(rid="ST-002-BAT", sid="ST-002", soc=0.8, available=150))
        plan = self.coordinator.dispatch_multi_station()
        assert plan is not None

    def test_dispatch_history_limit(self):
        """调度历史最多保留100条"""
        self.coordinator.register_station(make_station())
        self.coordinator.register_resource(make_battery_resource(soc=0.7, available=200))
        for _ in range(105):
            self.coordinator.dispatch_economic()
        assert len(self.coordinator.dispatch_history) == 100

    def test_get_dispatch_history(self):
        """获取调度历史"""
        self.coordinator.register_station(make_station())
        self.coordinator.register_resource(make_battery_resource(soc=0.7, available=200))
        self.coordinator.dispatch_economic()
        self.coordinator.dispatch_economic()
        history = self.coordinator.get_dispatch_history(limit=10)
        assert len(history) == 2
        assert 'plan_id' in history[0]
        assert 'mode' in history[0]

    def test_simulate_station_data(self):
        """模拟站点数据加载"""
        self.coordinator.simulate_station_data(count=3)
        assert len(self.coordinator.stations) == 3
        assert len(self.coordinator.resources) == 12  # 3 stations * 4 resources

    def test_clear_all(self):
        """clear_all 原子清空 stations/resources 且可再注册"""
        self.coordinator.register_station(make_station())
        self.coordinator.register_resource(make_battery_resource())
        assert len(self.coordinator.stations) == 1
        assert len(self.coordinator.resources) == 1

        self.coordinator.clear_all()
        assert self.coordinator.stations == {}
        assert self.coordinator.resources == {}

        # 清空后再 register 正常
        self.coordinator.register_station(make_station(sid="ST-002"))
        self.coordinator.register_resource(make_battery_resource(rid="ST-002-BAT", sid="ST-002"))
        assert len(self.coordinator.stations) == 1
        assert len(self.coordinator.resources) == 1
        assert "ST-002" in self.coordinator.stations

    def test_auto_dispatch_with_emergency_signal(self):
        """自动调度-紧急信号→需求响应"""
        self.coordinator.register_station(make_station())
        self.coordinator.register_resource(make_battery_resource(soc=0.8, available=200))
        signal = GridSignal(
            signal_type=GridSignalType.EMERGENCY,
            timestamp=datetime.now(),
            target_power_kw=100,
            duration_min=30,
        )
        plan = self.coordinator.auto_dispatch(signal)
        assert plan.mode == DispatchMode.DEMAND_RESPONSE

    def test_auto_dispatch_overload_peak_shaving(self):
        """自动调度-负荷超阈值→削峰"""
        self.coordinator.register_station(make_station(load=600))
        self.coordinator.register_resource(make_battery_resource(soc=0.7, available=300))
        self.coordinator.peak_threshold_kw = 300
        plan = self.coordinator.auto_dispatch()
        assert plan.mode == DispatchMode.PEAK_SHAVING


# ─── API 端点测试 ───

class TestVPPAPI:
    """VPP REST API 测试"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        from app.services.vpp import dispatch_optimizer

        # 卡34c4a347: 自建 TestClient(app) 不经 conftest.client fixture，指向空 UUID 库
        # (卡af65de3b 后默认库无 users 表)，login 500 → 无 token → 全 401。
        # 改用 conftest client（自带 seeded 测试库 + admin token 注入）。
        self.client = client
        # 重置VPP coordinator
        dispatch_optimizer._coordinator = None

    def test_get_capacity(self):
        """GET /vpp/capacity"""
        resp = self.client.get("/api/v1/vpp/capacity")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert 'online_stations' in data['data']
        assert 'total_pv_kw' in data['data']

    def test_list_stations(self):
        """GET /vpp/stations"""
        resp = self.client.get("/api/v1/vpp/stations")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert isinstance(data['data'], list)

    def test_register_station(self):
        """POST /vpp/stations"""
        resp = self.client.post("/api/v1/vpp/stations", json={
            "station_id": "TEST-001",
            "station_name": "测试站",
            "total_pv_kw": 100,
            "total_battery_kwh": 200,
            "total_ev_chargers": 5,
            "current_load_kw": 50,
            "current_pv_output_kw": 60,
            "current_battery_soc": 0.5,
            "available_dispatch_kw": 80,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['station_id'] == 'TEST-001'

    def test_update_station(self):
        """PUT /vpp/stations/{id}"""
        # 先注册
        self.client.post("/api/v1/vpp/stations", json={
            "station_id": "TEST-002",
            "station_name": "更新测试站",
            "total_pv_kw": 100,
        })
        resp = self.client.put("/api/v1/vpp/stations/TEST-002", json={
            "current_load_kw": 200,
            "online": False,
        })
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_update_station_not_found(self):
        """PUT /vpp/stations/{id} - 404"""
        resp = self.client.put("/api/v1/vpp/stations/NONEXIST", json={
            "current_load_kw": 200,
        })
        assert resp.status_code == 404

    def test_delete_station(self):
        """DELETE /vpp/stations/{id}"""
        self.client.post("/api/v1/vpp/stations", json={
            "station_id": "TEST-DEL",
            "station_name": "待删除站",
        })
        resp = self.client.delete("/api/v1/vpp/stations/TEST-DEL")
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_delete_station_not_found(self):
        """DELETE /vpp/stations/{id} - 404"""
        resp = self.client.delete("/api/v1/vpp/stations/NONEXIST")
        assert resp.status_code == 404

    def test_register_resource(self):
        """POST /vpp/resources"""
        resp = self.client.post("/api/v1/vpp/resources", json={
            "resource_id": "RES-001",
            "resource_type": "battery",
            "station_id": "ST-001",
            "rated_power_kw": 250,
            "current_power_kw": 0,
            "available_power_kw": 200,
            "soc": 0.7,
        })
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_register_resource_invalid_type(self):
        """POST /vpp/resources - 无效类型"""
        resp = self.client.post("/api/v1/vpp/resources", json={
            "resource_id": "RES-BAD",
            "resource_type": "invalid",
            "station_id": "ST-001",
        })
        assert resp.status_code == 400

    def test_dispatch_auto(self):
        """POST /vpp/dispatch - auto"""
        resp = self.client.post("/api/v1/vpp/dispatch", json={
            "mode": "auto",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert 'plan_id' in data['data']

    def test_dispatch_economic(self):
        """POST /vpp/dispatch - economic"""
        resp = self.client.post("/api/v1/vpp/dispatch", json={
            "mode": "economic",
        })
        assert resp.status_code == 200

    def test_dispatch_peak_shaving(self):
        """POST /vpp/dispatch - peak_shaving"""
        resp = self.client.post("/api/v1/vpp/dispatch", json={
            "mode": "peak_shaving",
            "peak_threshold_kw": 500,
        })
        assert resp.status_code == 200

    def test_dispatch_demand_response(self):
        """POST /vpp/dispatch - demand_response"""
        resp = self.client.post("/api/v1/vpp/dispatch", json={
            "mode": "demand_response",
            "grid_signal": {
                "signal_type": "demand_response",
                "target_power_kw": 100,
                "duration_min": 30,
                "reward_per_kwh": 0.5,
            },
        })
        assert resp.status_code == 200

    def test_dispatch_demand_response_no_signal(self):
        """POST /vpp/dispatch - demand_response without signal → 400"""
        resp = self.client.post("/api/v1/vpp/dispatch", json={
            "mode": "demand_response",
        })
        assert resp.status_code == 400

    def test_dispatch_invalid_mode(self):
        """POST /vpp/dispatch - 无效模式"""
        resp = self.client.post("/api/v1/vpp/dispatch", json={
            "mode": "invalid_mode",
        })
        assert resp.status_code == 400

    def test_dispatch_history(self):
        """GET /vpp/dispatch/history"""
        # 先执行一次调度
        self.client.post("/api/v1/vpp/dispatch", json={"mode": "economic"})
        resp = self.client.get("/api/v1/vpp/dispatch/history?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert isinstance(data['data'], list)
        assert len(data['data']) > 0

    def test_get_price(self):
        """GET /vpp/price"""
        resp = self.client.get("/api/v1/vpp/price")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert 'current_price' in data['data']
        assert 'period' in data['data']
        assert 'price_schedule' in data['data']

    def test_list_resources(self):
        """GET /vpp/resources"""
        resp = self.client.get("/api/v1/vpp/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert isinstance(data['data'], list)

    def test_simulate(self):
        """POST /vpp/simulate"""
        resp = self.client.post("/api/v1/vpp/simulate?count=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True

    def test_simulate_reloads_via_clear_all(self):
        """POST /vpp/simulate 应走持锁 clear_all 而非裸 clear"""
        from app.services.vpp import dispatch_optimizer
        coordinator = dispatch_optimizer.get_vpp_coordinator()
        coordinator.register_station(make_station(sid="ST-OLD"))

        orig = coordinator.clear_all
        with patch.object(coordinator, 'clear_all',
                          side_effect=orig) as m:
            resp = self.client.post("/api/v1/vpp/simulate?count=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        m.assert_called_once()
        # 旧站点被清除, 重新模拟出2个新站点
        assert "ST-OLD" not in coordinator.stations
        assert len(coordinator.stations) == 2
