"""
dispatch_optimizer VPP 核心调度引擎测试 — 任务卡 92ac062f

被测模块 app/services/vpp/dispatch_optimizer.py 是纯算法模块(仅依赖标准库,
零 DB / 零外部 IO), 故本文件用纯单元测试直接构造 dataclass 输入, 无需 DB fixture。

时间依赖隔离(核心难点):
- 底层 _optimize_battery / _optimize_ev_charger 形参接收 current_price, 直接传入即可,
  天然与 datetime.now() 解耦, 是最干净的测点。
- 公开方法 optimize_economic_dispatch / optimize_multi_station_coordination 内部用
  datetime.now() 取电价, 结果随运行时刻漂移。通过 monkeypatch 锁定 get_current_price
  返回固定值, 消除时间不确定性。
- 异常降级路径(每个公开方法 try/except 包裹 _impl): monkeypatch 对应 _impl 抛异常,
  稳定复现降级分支, 不依赖脆弱的脏输入构造。

浮点断言: 电价(0.6/0.3/0.9)在 double 不精确, 经乘除后 revenue/cost 形如
14.999999999999998, 故一律用 pytest.approx; 计数 / 符号 / 类型用直接断言。

覆盖 6 个方法(每方法 ≥1 正常 + ≥1 边界):
  optimize_economic_dispatch / optimize_peak_shaving / handle_demand_response /
  optimize_multi_station_coordination / _optimize_battery / _optimize_ev_charger
"""
from datetime import datetime

import pytest

from app.services.vpp.dispatch_optimizer import (
    VPPOptimizer,
    ResourceType,
    DispatchMode,
    GridSignalType,
    GridSignal,
    StationStatus,
    ResourceCapability,
)


# ═══════════════════════════════════════════════════════════════
# 工厂函数 — 构造 dataclass 输入, 隔离 DB
# ═══════════════════════════════════════════════════════════════

def _station(sid="ST-1", name="测试站A", load=200.0, pv=100.0,
             available=100.0, online=True):
    return StationStatus(
        station_id=sid, station_name=name,
        total_pv_kw=pv, total_battery_kwh=500.0, total_ev_chargers=10,
        current_load_kw=load, current_pv_output_kw=pv,
        current_battery_soc=0.5, available_dispatch_kw=available, online=online,
    )


def _battery(rid="BAT-1", sid="ST-1", rated=100.0, available=100.0,
             soc=0.8, current=0.0, priority=2):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.BATTERY, station_id=sid,
        rated_power_kw=rated, current_power_kw=current,
        available_power_kw=available, soc=soc, priority=priority,
    )


def _ev(rid="EV-1", sid="ST-1", power=100.0, available=50.0, priority=3):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.EV_CHARGER, station_id=sid,
        rated_power_kw=200.0, current_power_kw=power,
        available_power_kw=available, priority=priority,
    )


def _load(rid="LOAD-1", sid="ST-1", available=50.0, priority=4):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.LOAD, station_id=sid,
        rated_power_kw=50.0, current_power_kw=30.0,
        available_power_kw=available, priority=priority,
    )


def _pv(rid="PV-1", sid="ST-1", power=100.0, priority=5):
    return ResourceCapability(
        resource_id=rid, resource_type=ResourceType.PV, station_id=sid,
        rated_power_kw=100.0, current_power_kw=power,
        available_power_kw=power, priority=priority,
    )


def _signal(stype=GridSignalType.DEMAND_RESPONSE, target=None,
            duration=None, reward=None):
    return GridSignal(
        signal_type=stype, timestamp=datetime.now(),
        target_power_kw=target, duration_min=duration, reward_per_kwh=reward,
    )


def _boom(*_a, **_k):
    """统一异常桩: 让被测 _impl 抛异常, 触发公开方法的异常降级分支。"""
    raise RuntimeError("forced failure for degrade test")


@pytest.fixture
def opt():
    """每个测试 fresh VPPOptimizer, 避免跨用例 config 残留。"""
    return VPPOptimizer()


def _fix_price(optimizer, price, monkeypatch):
    """锁定电价, 消除 datetime.now() 导致的测试漂移。"""
    monkeypatch.setattr(optimizer, "get_current_price", lambda *_a, **_k: price)


# ═══════════════════════════════════════════════════════════════
# 1. _optimize_battery (L676) — 储能调度策略, 直接测
# ═══════════════════════════════════════════════════════════════

class TestOptimizeBattery:
    def test_charge_in_valley(self, opt):
        """低谷电价 + SOC 未满 → 充电(负功率), 产生成本无收益。"""
        bat = _battery(soc=0.3, available=100.0, rated=100.0)
        cmd = opt._optimize_battery(bat, current_price=0.3, hour=0.5)

        assert cmd is not None
        assert cmd.resource_type == ResourceType.BATTERY
        assert cmd.target_power_kw < 0              # 负 = 充电/吸收
        assert cmd.target_power_kw == pytest.approx(-100.0)
        assert cmd.estimated_revenue == 0           # 充电无收益
        assert cmd.estimated_cost == pytest.approx(0.3 * 100 / 60 * 15)  # ≈7.5
        assert cmd.dispatch_mode == DispatchMode.ECONOMIC

    def test_discharge_in_high_price(self, opt):
        """高电价 + SOC 高于放电下限 → 放电(正功率), 产生峰谷价差收益。"""
        bat = _battery(soc=0.8, available=100.0, rated=100.0)
        cmd = opt._optimize_battery(bat, current_price=0.9, hour=19.0)

        assert cmd is not None
        assert cmd.target_power_kw > 0              # 正 = 放电/出力
        assert cmd.target_power_kw == pytest.approx(100.0)
        assert cmd.estimated_revenue == pytest.approx(100 * (0.9 - 0.3) / 60 * 15)  # ≈15
        assert cmd.estimated_cost == 0

    def test_idle_in_flat_price(self, opt):
        """平段电价(0.6) 既不满足低谷充电(<=0.33) 也不满足高价放电(>=0.9) → 不调度。"""
        bat = _battery(soc=0.5)
        assert opt._optimize_battery(bat, current_price=0.6, hour=13.0) is None

    def test_soc_below_discharge_floor_no_discharge(self, opt):
        """高电价但 SOC 低于放电下限(默认0.20) → 不放电, 返回 None。"""
        bat = _battery(soc=0.15)  # 0.15 < 0.20
        assert opt._optimize_battery(bat, current_price=0.9, hour=19.0) is None

    def test_soc_none_no_discharge_only_valley_charge(self, opt):
        """SOC=None(卡c7b966cd修复): 未知SOC不再默认0.5放电(过放风险), 高电价返回None;
        仅允许低谷充电(充电不会过放)。"""
        bat = _battery(soc=None)

        # 高电价: SOC未知, 跳过放电决策
        cmd_discharge = opt._optimize_battery(bat, current_price=0.9, hour=19.0)
        assert cmd_discharge is None

        # 低谷: 充电安全, 仍允许
        cmd_charge = opt._optimize_battery(bat, current_price=0.3, hour=0.5)
        assert cmd_charge is not None and cmd_charge.target_power_kw < 0

    def test_config_overrides_discharge_floor(self, opt, monkeypatch):
        """config 抬高放电下限至 0.5, SOC=0.4 高电价也不再放电。"""
        from app.services.vpp.dispatch_optimizer import VPPOptimizer as _V
        configured = _V(config={"battery_discharge_soc_floor": 0.5})
        assert configured._battery_discharge_soc_floor == pytest.approx(0.5)

        bat = _battery(soc=0.4)  # 0.4 < 0.5(覆盖后下限)
        assert configured._optimize_battery(bat, current_price=0.9, hour=19.0) is None

    def test_floor_floor_at_battery_soc_min(self, opt):
        """config 设极小放电下限, 兜底不低于 BATTERY_SOC_MIN(0.10)。"""
        from app.services.vpp.dispatch_optimizer import VPPOptimizer as _V
        configured = _V(config={"battery_discharge_soc_floor": 0.01})
        assert configured._battery_discharge_soc_floor == pytest.approx(0.10)


# ═══════════════════════════════════════════════════════════════
# 2. _optimize_ev_charger (L719) — 充电桩策略, 直接测
# ═══════════════════════════════════════════════════════════════

class TestOptimizeEvCharger:
    def test_curtail_in_high_price(self, opt):
        """高电价 + 正在充电 → 削减 50% 充电功率(默认比例), 节省收益。"""
        ev = _ev(power=100.0)
        cmd = opt._optimize_ev_charger(ev, current_price=0.9, hour=19.0)

        assert cmd is not None
        assert cmd.resource_type == ResourceType.EV_CHARGER
        assert cmd.target_power_kw == pytest.approx(-50.0)   # 100 * 0.5
        assert cmd.estimated_revenue == pytest.approx(50 * 0.9 / 60 * 15)  # ≈11.25
        assert cmd.estimated_cost == 0

    def test_idle_in_low_price(self, opt):
        """低谷电价(0.3 < 0.9) → 不削减, 返回 None。"""
        ev = _ev(power=100.0)
        assert opt._optimize_ev_charger(ev, current_price=0.3, hour=0.5) is None

    def test_zero_power_no_curtail(self, opt):
        """高电价但充电桩未在充电(current_power_kw=0) → 无可削减, None。"""
        ev = _ev(power=0.0)
        assert opt._optimize_ev_charger(ev, current_price=0.9, hour=19.0) is None

    def test_config_overrides_curtail_ratio(self, opt):
        """config 削减比例 0.3, 100kW 充电只削减 30kW。"""
        from app.services.vpp.dispatch_optimizer import VPPOptimizer as _V
        configured = _V(config={"ev_curtailment_ratio": 0.3})
        assert configured._ev_curtail_ratio == pytest.approx(0.3)

        ev = _ev(power=100.0)
        cmd = configured._optimize_ev_charger(ev, current_price=0.9, hour=19.0)
        assert cmd is not None
        assert cmd.target_power_kw == pytest.approx(-30.0)   # 100 * 0.3


# ═══════════════════════════════════════════════════════════════
# 3. optimize_economic_dispatch (L212) — 经济调度(峰谷套利)
# ═══════════════════════════════════════════════════════════════

class TestOptimizeEconomicDispatch:
    def test_high_price_discharge(self, opt, monkeypatch):
        """高电价时段, 高 SOC 储能放电 → 生成 ECONOMIC 调度计划含放电指令。"""
        _fix_price(opt, 0.9, monkeypatch)
        stations = [_station(sid="ST-1")]
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0)]

        plan = opt.optimize_economic_dispatch(stations, resources)

        assert plan.mode == DispatchMode.ECONOMIC
        assert plan.plan_id.startswith("eco_")
        assert plan.stations_involved == ["ST-1"]
        assert len(plan.commands) == 1
        cmd = plan.commands[0]
        assert cmd.resource_type == ResourceType.BATTERY
        assert cmd.target_power_kw == pytest.approx(100.0)
        assert cmd.estimated_revenue == pytest.approx(100 * (0.9 - 0.3) / 60 * 15)
        assert plan.total_dispatch_kw == pytest.approx(100.0)
        assert plan.net_profit == pytest.approx(plan.estimated_revenue - plan.estimated_cost)

    def test_empty_inputs(self, opt, monkeypatch):
        """空 stations + 空 resources → 空计划(无指令, 0 功率), 不崩。"""
        _fix_price(opt, 0.9, monkeypatch)
        plan = opt.optimize_economic_dispatch([], [])
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert plan.net_profit == 0

    def test_pv_not_dispatched(self, opt, monkeypatch):
        """仅光伏资源 → 光伏不参与调度, 计划无指令。"""
        _fix_price(opt, 0.9, monkeypatch)
        stations = [_station(sid="ST-1")]
        resources = [_pv(rid="PV-1", sid="ST-1")]
        plan = opt.optimize_economic_dispatch(stations, resources)
        assert plan.commands == []

    def test_commands_sorted_by_priority(self, opt, monkeypatch):
        """多资源调度指令按 priority 升序排列。"""
        _fix_price(opt, 0.9, monkeypatch)
        resources = [
            _battery(rid="BAT-A", sid="ST-1", soc=0.8, priority=5),
            _battery(rid="BAT-B", sid="ST-1", soc=0.8, priority=1),
        ]
        plan = opt.optimize_economic_dispatch([_station()], resources)
        priorities = [c.priority for c in plan.commands]
        assert priorities == sorted(priorities)
        assert plan.commands[0].resource_id == "BAT-B"   # priority=1 排前

    def test_exception_degrades_to_safe_plan(self, opt, monkeypatch):
        """_impl 抛异常 → 异常降级返回安全空计划, 调用方不崩溃。"""
        monkeypatch.setattr(opt, "_optimize_economic_dispatch_impl", _boom)
        stations = [_station(sid="ST-1", online=True)]

        plan = opt.optimize_economic_dispatch(stations, [_battery()])

        assert plan.mode == DispatchMode.ECONOMIC
        assert plan.plan_id.startswith("safe_")
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert plan.net_profit == 0
        assert "异常降级" in plan.trigger
        # 降级仍提取 online 站点(保证可观测)
        assert plan.stations_involved == ["ST-1"]


# ═══════════════════════════════════════════════════════════════
# 4. optimize_peak_shaving (L273) — 削峰填谷
# ═══════════════════════════════════════════════════════════════

class TestOptimizePeakShaving:
    def test_overload_discharge_then_curtail(self, opt):
        """负荷 600 超阈值 500 → 储能优先放电(80kW), 不足部分削减负荷(20kW)。"""
        stations = [_station(sid="ST-1", load=600.0)]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.8, available=80.0),
            _load(rid="LOAD-1", sid="ST-1", available=50.0),
        ]

        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)

        assert plan.mode == DispatchMode.PEAK_SHAVING
        assert plan.plan_id.startswith("ps_")
        assert len(plan.commands) == 2
        # 储能放电指令(先加)
        assert plan.commands[0].resource_type == ResourceType.BATTERY
        assert plan.commands[0].target_power_kw == pytest.approx(80.0)
        # 负荷削减指令(后加, 负功率)
        assert plan.commands[1].resource_type == ResourceType.LOAD
        assert plan.commands[1].target_power_kw == pytest.approx(-20.0)
        # total = sum(target) = 80 + (-20)
        assert plan.total_dispatch_kw == pytest.approx(60.0)

    def test_no_overload_empty_plan(self, opt):
        """负荷 300 低于阈值 500 → 无过载, 返回空指令计划。"""
        stations = [_station(sid="ST-1", load=300.0)]
        plan = opt.optimize_peak_shaving(stations, [], peak_threshold_kw=500.0)

        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "负荷正常" in plan.trigger
        assert plan.stations_involved == ["ST-1"]

    def test_low_soc_skips_battery_falls_to_load(self, opt):
        """储能 SOC 过低(<0.20)被跳过 → 全部过载转由负荷削减承担。"""
        stations = [_station(sid="ST-1", load=600.0)]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.15, available=80.0),  # 被跳过
            _load(rid="LOAD-1", sid="ST-1", available=50.0),
        ]

        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)

        types = [c.resource_type for c in plan.commands]
        assert ResourceType.BATTERY not in types          # 储能被跳过
        assert ResourceType.LOAD in types                 # 转由负荷承担
        assert plan.commands[0].target_power_kw == pytest.approx(-50.0)  # min(50, 100)

    def test_exception_degrades_to_safe_plan(self, opt, monkeypatch):
        """_impl 抛异常 → 降级安全空计划。"""
        monkeypatch.setattr(opt, "_optimize_peak_shaving_impl", _boom)
        plan = opt.optimize_peak_shaving([_station()], [_battery()], peak_threshold_kw=500.0)

        assert plan.mode == DispatchMode.PEAK_SHAVING
        assert plan.plan_id.startswith("safe_")
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0


# ═══════════════════════════════════════════════════════════════
# 5. handle_demand_response (L388) — 需求响应
# ═══════════════════════════════════════════════════════════════

class TestHandleDemandResponse:
    def test_battery_then_ev_curtail(self, opt):
        """目标 200kW: 储能放电 150 + EV 削减 50, 响应率 100%。"""
        stations = [_station(sid="ST-1")]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.8, available=150.0, rated=200.0),
            _ev(rid="EV-1", sid="ST-1", power=100.0),
        ]
        signal = _signal(target=200, duration=60, reward=0.5)

        plan = opt.handle_demand_response(stations, resources, signal)

        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        assert plan.plan_id.startswith("dr_")
        assert len(plan.commands) == 2
        assert plan.commands[0].resource_type == ResourceType.BATTERY
        assert plan.commands[0].target_power_kw == pytest.approx(150.0)
        assert plan.commands[0].priority == 1
        assert plan.commands[1].resource_type == ResourceType.EV_CHARGER
        assert plan.commands[1].target_power_kw == pytest.approx(-50.0)
        # total_dispatch 用 abs 求和 = 150 + 50
        assert plan.total_dispatch_kw == pytest.approx(200.0)
        assert "响应率100.0%" in plan.trigger

    def test_zero_target_zero_response(self, opt):
        """目标 0kW → 无指令, 响应率 0%。"""
        stations = [_station(sid="ST-1")]
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8)]
        signal = _signal(target=0)

        plan = opt.handle_demand_response(stations, resources, signal)

        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "响应率0.0%" in plan.trigger

    def test_default_reward_when_signal_none(self, opt):
        """signal.reward_per_kwh=None → 用 dr_reward_rate(默认0.5) 计算收益。"""
        stations = [_station(sid="ST-1")]
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0)]
        signal = _signal(target=200, duration=60, reward=None)  # None

        plan = opt.handle_demand_response(stations, resources, signal)

        assert len(plan.commands) == 1
        # reward=0.5: revenue = 100 * 0.5 * 60 / 60 = 50
        assert plan.commands[0].estimated_revenue == pytest.approx(50.0)

    def test_low_soc_battery_skipped(self, opt):
        """储能 SOC 低于 DR 阈值(BATTERY_SOC_MIN+0.15=0.25) → 跳过, 转由 EV 削减。"""
        stations = [_station(sid="ST-1")]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.20, available=150.0),  # 0.20<0.25 跳过
            _ev(rid="EV-1", sid="ST-1", power=100.0),
        ]
        signal = _signal(target=200, duration=60, reward=0.5)

        plan = opt.handle_demand_response(stations, resources, signal)

        types = [c.resource_type for c in plan.commands]
        assert ResourceType.BATTERY not in types
        assert ResourceType.EV_CHARGER in types

    def test_exception_degrades_to_safe_plan(self, opt, monkeypatch):
        """_impl 抛异常 → 降级安全空计划。"""
        monkeypatch.setattr(opt, "_handle_demand_response_impl", _boom)
        plan = opt.handle_demand_response([_station()], [_battery()], _signal(target=100))

        assert plan.mode == DispatchMode.DEMAND_RESPONSE
        assert plan.plan_id.startswith("safe_")
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0


# ═══════════════════════════════════════════════════════════════
# 6. optimize_multi_station_coordination (L508) — 多站点协同
# ═══════════════════════════════════════════════════════════════

class TestOptimizeMultiStationCoordination:
    def test_inter_station_power_sharing(self, opt, monkeypatch):
        """缺电站点从余电站点的储能互济放电, 生成 GRID_SUPPORT 调度指令。"""
        _fix_price(opt, 0.6, monkeypatch)   # 平段, 走放电分支但剩余储能已被互济占用
        # ST-A 缺电: surplus = 50 - 200 + 50 = -100
        st_a = _station(sid="ST-A", load=200.0, pv=50.0, available=50.0)
        # ST-B 余电: surplus = 300 - 100 + 200 = 400
        st_b = _station(sid="ST-B", load=100.0, pv=300.0, available=200.0)
        resources = [_battery(rid="BAT-B", sid="ST-B", soc=0.8, available=100.0)]

        plan = opt.optimize_multi_station_coordination([st_a, st_b], resources)

        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert plan.plan_id.startswith("coord_")
        assert set(plan.stations_involved) == {"ST-A", "ST-B"}
        # 互济指令来自 ST-B 储能放电
        assert len(plan.commands) >= 1
        share_cmd = plan.commands[0]
        assert share_cmd.station_id == "ST-B"
        assert share_cmd.resource_type == ResourceType.BATTERY
        assert share_cmd.target_power_kw > 0
        assert share_cmd.dispatch_mode == DispatchMode.GRID_SUPPORT
        assert share_cmd.priority == 1

    def test_no_signal_no_dr_commands(self, opt, monkeypatch):
        """无 grid_signal → 不触发需求响应, 计划仅含互济/经济调度指令。"""
        _fix_price(opt, 0.3, monkeypatch)   # 低谷, 走充电分支
        st = _station(sid="ST-1", load=100.0, pv=100.0, available=100.0)
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.3, available=100.0)]

        plan = opt.optimize_multi_station_coordination([st], resources, grid_signal=None)

        assert plan.mode == DispatchMode.GRID_SUPPORT
        modes = {c.dispatch_mode for c in plan.commands}
        assert DispatchMode.DEMAND_RESPONSE not in modes   # 无 signal 不走 DR

    def test_grid_signal_triggers_demand_response(self, opt, monkeypatch):
        """传入 DEMAND_RESPONSE 信号 → 协同计划内包含需求响应指令。"""
        _fix_price(opt, 0.6, monkeypatch)
        # 单站, surplus=0 避免互济干扰(无缺电站, 互济不执行)
        st = _station(sid="ST-1", load=100.0, pv=100.0, available=100.0)
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0)]
        signal = _signal(stype=GridSignalType.DEMAND_RESPONSE, target=100, duration=60, reward=0.5)

        plan = opt.optimize_multi_station_coordination([st], resources, grid_signal=signal)

        modes = {c.dispatch_mode for c in plan.commands}
        assert DispatchMode.DEMAND_RESPONSE in modes

    def test_exception_degrades_to_safe_plan(self, opt, monkeypatch):
        """_impl 抛异常 → 降级安全空计划。"""
        monkeypatch.setattr(opt, "_optimize_multi_station_coordination_impl", _boom)
        plan = opt.optimize_multi_station_coordination([_station()], [_battery()])

        assert plan.mode == DispatchMode.GRID_SUPPORT
        assert plan.plan_id.startswith("safe_")
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "异常降级" in plan.trigger
