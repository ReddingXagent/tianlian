"""
VPP 调度优化器缺陷修复 + 测试覆盖 — 任务卡 c7b966cd

被测模块 app/services/vpp/dispatch_optimizer/optimizer.py 是纯算法模块(仅依赖
标准库, 零 DB / 零外部 IO), 用纯单元测试直接构造 dataclass 输入, 无需 DB fixture。

本文件聚焦任务卡四处缺陷的回归 + 6 维度覆盖:
  BUG1 多站点互济 deficit 计算错误(L549) — 多余电站/余电不足场景下 deficit 被错误归零,
      后续余电站不再互济, 缺电站需求无法满足。
  BUG2 peak_threshold_kw ≤ 0 无校验 — 阈值 0/负导致全负荷判定过载, 触发大规模放电+削减。
  BUG3 _optimize_battery soc=None 默认 0.5 — 未知 SOC 下贸然放电有风险, 改为仅低谷充电。
  BUG4 _optimize_ev_charger current_power_kw 未 None 保护 — 直接比较抛 TypeError。

时间依赖隔离:
  - _optimize_battery / _optimize_ev_charger 形参收 current_price, 直接传入解耦 datetime。
  - optimize_economic_dispatch / optimize_multi_station_coordination 内部用 _pricing_hour()
    取电价, 通过 monkeypatch get_current_price 锁定固定值。
  - 电价时段直接用 get_current_price(hour=...) 注入显式小时, 天然稳定。

浮点断言: 电价经乘除后存 double 误差, 一律 pytest.approx; 计数/符号/类型直接断言。
"""
import logging
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

def _station(sid="ST-1", name="测试站", load=200.0, pv=100.0,
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


def _signal(stype=GridSignalType.DEMAND_RESPONSE, target=None,
            duration=None, reward=None):
    return GridSignal(
        signal_type=stype, timestamp=datetime.now(),
        target_power_kw=target, duration_min=duration, reward_per_kwh=reward,
    )


@pytest.fixture
def opt():
    """每个测试 fresh VPPOptimizer, 避免跨用例 config 残留。"""
    return VPPOptimizer()


def _fix_price(optimizer, price, monkeypatch):
    """锁定电价, 消除 datetime.now() 导致的测试漂移。"""
    monkeypatch.setattr(optimizer, "get_current_price", lambda *_a, **_k: price)


# ═══════════════════════════════════════════════════════════════
# 1. 电价时段 get_current_price
# ═══════════════════════════════════════════════════════════════

class TestPriceSchedule:
    def test_peak_price(self, opt):
        """尖峰 10:00-12:00 → 1.2 元/kWh。"""
        assert opt.get_current_price(hour=11.0) == pytest.approx(1.2)

    def test_high_price_morning(self, opt):
        """早高峰 8:00-10:00 → 0.9 元/kWh。"""
        assert opt.get_current_price(hour=9.0) == pytest.approx(0.9)

    def test_high_price_evening(self, opt):
        """晚高峰 18:00-21:00 → 0.9 元/kWh。"""
        assert opt.get_current_price(hour=19.0) == pytest.approx(0.9)

    def test_flat_price(self, opt):
        """平段 12:00-18:00 → 0.6 元/kWh。"""
        assert opt.get_current_price(hour=13.0) == pytest.approx(0.6)

    def test_valley_price_late_night(self, opt):
        """低谷 23:00-6:00 → 0.3 元/kWh。"""
        assert opt.get_current_price(hour=2.0) == pytest.approx(0.3)

    def test_valley_price_boundary(self, opt):
        """低谷边界 23:30 → 0.3 元/kWh(23:00 含)。"""
        assert opt.get_current_price(hour=23.5) == pytest.approx(0.3)

    def test_price_with_multiplier(self):
        """price_multiplier=2 → 尖峰电价翻倍至 2.4。"""
        configured = VPPOptimizer(config={"price_multiplier": 2.0})
        assert configured.get_current_price(hour=11.0) == pytest.approx(2.4)

    def test_price_timezone_aware(self, opt):
        """aware 时刻注入: 北京正午 12:30 (平段) → 0.6, 验证时区解析路径。"""
        from zoneinfo import ZoneInfo
        noon = datetime(2026, 8, 7, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert opt.get_current_price(now=noon) == pytest.approx(0.6)


# ═══════════════════════════════════════════════════════════════
# 2. 经济调度 optimize_economic_dispatch — 峰谷套利
# ═══════════════════════════════════════════════════════════════

class TestEconomicDispatch:
    def test_valley_charge(self, opt, monkeypatch):
        """低谷电价 + SOC 未满 → 储能充电(负功率), 产生成本无收益。"""
        _fix_price(opt, 0.3, monkeypatch)
        stations = [_station(sid="ST-1")]
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.3, available=100.0)]

        plan = opt.optimize_economic_dispatch(stations, resources)

        assert plan.mode == DispatchMode.ECONOMIC
        assert len(plan.commands) == 1
        cmd = plan.commands[0]
        assert cmd.target_power_kw == pytest.approx(-100.0)   # 充电
        assert cmd.estimated_cost == pytest.approx(0.3 * 100 / 60 * 15)
        assert plan.total_dispatch_kw == pytest.approx(-100.0)

    def test_high_price_discharge(self, opt, monkeypatch):
        """高电价 + SOC 高于放电下限 → 储能放电(正功率), 产生峰谷价差收益。"""
        _fix_price(opt, 0.9, monkeypatch)
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0)]

        plan = opt.optimize_economic_dispatch([_station(sid="ST-1")], resources)

        cmd = plan.commands[0]
        assert cmd.target_power_kw == pytest.approx(100.0)    # 放电
        assert cmd.estimated_revenue == pytest.approx(100 * (0.9 - 0.3) / 60 * 15)

    def test_flat_price_no_action(self, opt, monkeypatch):
        """平段电价(0.6) 既不满足低谷充电(<=0.33) 也不满足高价放电(>=0.9) → 不调度。"""
        _fix_price(opt, 0.6, monkeypatch)
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.5)]
        plan = opt.optimize_economic_dispatch([_station(sid="ST-1")], resources)
        assert plan.commands == []

    def test_empty_inputs(self, opt, monkeypatch):
        """空 stations + 空 resources → 空计划, 不崩。"""
        _fix_price(opt, 0.9, monkeypatch)
        plan = opt.optimize_economic_dispatch([], [])
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert plan.net_profit == 0


# ═══════════════════════════════════════════════════════════════
# 3. 削峰填谷 optimize_peak_shaving
# ═══════════════════════════════════════════════════════════════

class TestPeakShaving:
    def test_normal_load_empty_plan(self, opt):
        """负荷 300 低于阈值 500 → 无过载, 空指令计划。"""
        stations = [_station(sid="ST-1", load=300.0)]
        plan = opt.optimize_peak_shaving(stations, [], peak_threshold_kw=500.0)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "负荷正常" in plan.trigger

    def test_overload_battery_then_load(self, opt):
        """负荷 600 超阈值 500 → 储能优先放电(80kW), 不足转负荷削减(20kW)。"""
        stations = [_station(sid="ST-1", load=600.0)]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.8, available=80.0),
            _load(rid="LOAD-1", sid="ST-1", available=50.0),
        ]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)

        assert len(plan.commands) == 2
        assert plan.commands[0].resource_type == ResourceType.BATTERY
        assert plan.commands[0].target_power_kw == pytest.approx(80.0)
        assert plan.commands[1].resource_type == ResourceType.LOAD
        assert plan.commands[1].target_power_kw == pytest.approx(-20.0)

    def test_threshold_zero_returns_safe_plan(self, opt):
        """BUG2: 阈值=0 → 不应把全负荷判为过载, 返回安全空计划。"""
        stations = [_station(sid="ST-1", load=200.0)]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0),
            _load(rid="LOAD-1", sid="ST-1", available=100.0),
        ]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=0.0)

        assert plan.mode == DispatchMode.PEAK_SHAVING
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "无效" in plan.trigger or "无效" in plan.plan_id or plan.plan_id.startswith("ps_")

    def test_threshold_negative_returns_safe_plan(self, opt):
        """BUG2: 负阈值同样返回安全空计划, 不触发大规模削减。"""
        stations = [_station(sid="ST-1", load=200.0)]
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0)]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=-50.0)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0

    def test_low_soc_skips_battery(self, opt):
        """储能 SOC 过低(<0.20)被跳过 → 全部过载转负荷削减。"""
        stations = [_station(sid="ST-1", load=600.0)]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.15, available=80.0),
            _load(rid="LOAD-1", sid="ST-1", available=50.0),
        ]
        plan = opt.optimize_peak_shaving(stations, resources, peak_threshold_kw=500.0)
        types = [c.resource_type for c in plan.commands]
        assert ResourceType.BATTERY not in types
        assert ResourceType.LOAD in types


# ═══════════════════════════════════════════════════════════════
# 4. 需求响应 handle_demand_response
# ═══════════════════════════════════════════════════════════════

class TestDemandResponse:
    def test_battery_priority(self, opt):
        """目标 150kW: 仅储能即可满足 → 储能放电 150, 响应率 100%。"""
        stations = [_station(sid="ST-1")]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.8, available=150.0, rated=200.0),
            _ev(rid="EV-1", sid="ST-1", power=100.0),
        ]
        signal = _signal(target=150, duration=60, reward=0.5)
        plan = opt.handle_demand_response(stations, resources, signal)

        assert len(plan.commands) == 1
        assert plan.commands[0].resource_type == ResourceType.BATTERY
        assert plan.commands[0].target_power_kw == pytest.approx(150.0)
        assert plan.commands[0].priority == 1
        assert "响应率100.0%" in plan.trigger

    def test_ev_curtail_after_battery(self, opt):
        """储能不足时转充电桩削减: 储能放电150 + EV削减50 = 200kW。"""
        stations = [_station(sid="ST-1")]
        resources = [
            _battery(rid="BAT-1", sid="ST-1", soc=0.8, available=150.0, rated=200.0),
            _ev(rid="EV-1", sid="ST-1", power=100.0),
        ]
        signal = _signal(target=200, duration=60, reward=0.5)
        plan = opt.handle_demand_response(stations, resources, signal)

        types = [c.resource_type for c in plan.commands]
        assert types == [ResourceType.BATTERY, ResourceType.EV_CHARGER]
        assert plan.commands[1].target_power_kw == pytest.approx(-50.0)

    def test_load_adjust(self, opt):
        """无储能无充电桩, 仅可调负荷承担响应。"""
        stations = [_station(sid="ST-1")]
        resources = [_load(rid="LOAD-1", sid="ST-1", available=80.0)]
        signal = _signal(target=60, duration=60, reward=0.5)
        plan = opt.handle_demand_response(stations, resources, signal)

        assert len(plan.commands) == 1
        assert plan.commands[0].resource_type == ResourceType.LOAD
        assert plan.commands[0].target_power_kw == pytest.approx(-60.0)
        assert plan.commands[0].priority == 3

    def test_zero_target_zero_response(self, opt):
        """目标 0kW → 无指令, 响应率 0%。"""
        stations = [_station(sid="ST-1")]
        signal = _signal(target=0)
        plan = opt.handle_demand_response(stations, [_battery(soc=0.8)], signal)
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0
        assert "响应率0.0%" in plan.trigger


# ═══════════════════════════════════════════════════════════════
# 5. 多站点协同 optimize_multi_station_coordination — BUG1 重点
# ═══════════════════════════════════════════════════════════════

class TestMultiStationCoordination:
    def test_bug1_deficit_three_exporters_all_used(self, opt, monkeypatch):
        """BUG1 核心: 缺电站缺口 100kW, 3 个余电站各可互济 30kW(电池上限)。

        修复前 deficit = abs(imp_surplus) - transfer_kw 公式在首轮(余电不足 30<100)
        将 deficit 错误归零, 仅产生 1 条互济指令; 修复后 deficit 按实际互济量逐轮
        扣减, 3 个余电站全部参与, 共互济 90kW。
        """
        _fix_price(opt, 0.6, monkeypatch)   # 平段, 避免经济调度放电混入
        # 缺电站: surplus = 0 - 100 + 0 = -100
        st_def = _station(sid="ST-DEF", load=100.0, pv=0.0, available=0.0)
        # 3 个余电站各 surplus = 130 - 100 + 0 = 30, 电池可放 30
        exporters = [
            (_station(sid=f"ST-E{i}", load=100.0, pv=130.0, available=0.0),
             _battery(rid=f"BAT-E{i}", sid=f"ST-E{i}", soc=0.8, available=30.0))
            for i in range(1, 4)
        ]
        stations = [st_def] + [s for s, _ in exporters]
        resources = [b for _, b in exporters]

        plan = opt.optimize_multi_station_coordination(stations, resources)

        share_cmds = [c for c in plan.commands
                      if c.dispatch_mode == DispatchMode.GRID_SUPPORT]
        # 修复前此处 == 1(deficit 错误归零跳过后续余电站), 修复后 == 3
        assert len(share_cmds) == 3
        # 累计互济量 = 30 * 3 = 90(缺口 100, 余电站总可放 90, 全部用尽)
        total_shared = sum(c.target_power_kw for c in share_cmds)
        assert total_shared == pytest.approx(90.0)
        # 三个余电站均参与
        assert {c.station_id for c in share_cmds} == {"ST-E1", "ST-E2", "ST-E3"}

    def test_bug1_deficit_partial_then_remaining(self, opt, monkeypatch):
        """BUG1: 缺口 100, 余电站A电池只能放 40 → 转余电站B补足剩余 60。

        修复前 deficit 在 A 轮被错误归零, B 轮 deficit<=0 被跳过; 修复后 B 继续补 60。
        """
        _fix_price(opt, 0.6, monkeypatch)
        st_def = _station(sid="ST-DEF", load=100.0, pv=0.0, available=0.0)
        st_a = _station(sid="ST-A", load=0.0, pv=200.0, available=0.0)   # surplus=200
        st_b = _station(sid="ST-B", load=0.0, pv=200.0, available=0.0)   # surplus=200
        resources = [
            _battery(rid="BAT-A", sid="ST-A", soc=0.8, available=40.0),
            _battery(rid="BAT-B", sid="ST-B", soc=0.8, available=100.0),
        ]
        plan = opt.optimize_multi_station_coordination(
            [st_def, st_a, st_b], resources)

        share_cmds = [c for c in plan.commands
                      if c.dispatch_mode == DispatchMode.GRID_SUPPORT]
        # A 放 40 + B 放 60 = 100, 满足缺口
        assert len(share_cmds) == 2
        total = sum(c.target_power_kw for c in share_cmds)
        assert total == pytest.approx(100.0)
        per_station = {c.station_id: c.target_power_kw for c in share_cmds}
        assert per_station["ST-A"] == pytest.approx(40.0)
        assert per_station["ST-B"] == pytest.approx(60.0)

    def test_basic_inter_station_sharing(self, opt, monkeypatch):
        """基础互济: 单缺电 + 单余电, 余电充足 → 互济指令来自余电站储能。"""
        _fix_price(opt, 0.6, monkeypatch)
        st_def = _station(sid="ST-DEF", load=200.0, pv=0.0, available=0.0)
        st_sur = _station(sid="ST-SUR", load=100.0, pv=400.0, available=0.0)
        resources = [_battery(rid="BAT-S", sid="ST-SUR", soc=0.8, available=100.0)]

        plan = opt.optimize_multi_station_coordination([st_def, st_sur], resources)

        assert plan.mode == DispatchMode.GRID_SUPPORT
        share_cmds = [c for c in plan.commands
                      if c.dispatch_mode == DispatchMode.GRID_SUPPORT]
        assert len(share_cmds) >= 1
        cmd = share_cmds[0]
        assert cmd.station_id == "ST-SUR"
        assert cmd.resource_type == ResourceType.BATTERY
        assert cmd.priority == 1

    def test_no_grid_signal(self, opt, monkeypatch):
        """无 grid_signal → 不触发需求响应指令。"""
        _fix_price(opt, 0.6, monkeypatch)
        st = _station(sid="ST-1", load=100.0, pv=100.0, available=100.0)
        resources = [_battery(rid="BAT-1", sid="ST-1", soc=0.8, available=100.0)]
        plan = opt.optimize_multi_station_coordination([st], resources, grid_signal=None)
        modes = {c.dispatch_mode for c in plan.commands}
        assert DispatchMode.DEMAND_RESPONSE not in modes

    def test_empty_stations(self, opt, monkeypatch):
        """空站点 + 空资源 → 空计划, 不崩。"""
        _fix_price(opt, 0.6, monkeypatch)
        plan = opt.optimize_multi_station_coordination([], [])
        assert plan.commands == []
        assert plan.total_dispatch_kw == 0


# ═══════════════════════════════════════════════════════════════
# 6. 边界 — BUG3 / BUG4 / None 防护
# ═══════════════════════════════════════════════════════════════

class TestBoundaryGuards:
    def test_bug3_soc_none_high_price_no_discharge(self, opt, caplog):
        """BUG3: soc=None + 高电价 → 不做放电决策, 返回 None, 并打 warning。"""
        bat = _battery(soc=None)
        with caplog.at_level(logging.WARNING, logger="vpp"):
            cmd = opt._optimize_battery(bat, current_price=0.9, hour=19.0)
        assert cmd is None
        assert any("SOC" in rec.message or "soc" in rec.message for rec in caplog.records)

    def test_bug3_soc_none_valley_charge(self, opt):
        """BUG3: soc=None + 低谷电价 → 仍允许低谷充电(负功率), SOC 未知不影响充电安全。"""
        bat = _battery(soc=None)
        cmd = opt._optimize_battery(bat, current_price=0.3, hour=2.0)
        assert cmd is not None
        assert cmd.target_power_kw < 0
        assert cmd.estimated_cost == pytest.approx(0.3 * 100 / 60 * 15)

    def test_bug3_soc_none_flat_no_action(self, opt):
        """BUG3: soc=None + 平段 → 既非低谷充电也禁止放电, 返回 None。"""
        bat = _battery(soc=None)
        assert opt._optimize_battery(bat, current_price=0.6, hour=13.0) is None

    def test_bug4_ev_current_power_none(self, opt):
        """BUG4: ev.current_power_kw=None + 高电价 → 不崩, 返回 None(无可削减功率)。"""
        ev = _ev(power=100.0)
        ev.current_power_kw = None
        # 修复前: None > 0 抛 TypeError; 修复后: 守卫返回 None
        cmd = opt._optimize_ev_charger(ev, current_price=0.9, hour=19.0)
        assert cmd is None

    def test_battery_low_soc_no_discharge(self, opt):
        """SOC 低于放电下限(默认 0.20) + 高电价 → 不放电。"""
        bat = _battery(soc=0.15)
        assert opt._optimize_battery(bat, current_price=0.9, hour=19.0) is None

    def test_battery_charge_near_full(self, opt):
        """低谷电价但 SOC 已达上限(0.95) → 不再充电。"""
        bat = _battery(soc=0.96)
        assert opt._optimize_battery(bat, current_price=0.3, hour=2.0) is None

    def test_ev_zero_power_no_curtail(self, opt):
        """高电价但充电桩未在充电(current_power_kw=0) → 无可削减, None。"""
        ev = _ev(power=0.0)
        assert opt._optimize_ev_charger(ev, current_price=0.9, hour=19.0) is None
