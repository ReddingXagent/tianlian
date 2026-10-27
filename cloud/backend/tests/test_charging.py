"""
充电策略引擎(P7)测试

覆盖:
- 数据模型与抽象基类(ChargingMode / ChargingContext / ChargingDecision / ChargingStrategy)
- 5 种充电策略: manual / timed / solar / price / balanced
- StrategyEngine: 模式切换 / 优先级排序 / 冲突解决(手动抢占)
- SolarForecaster: 24h 预测 / 天气系数 / 夜间归零
- StorageOptimizer: SOC 健康保护 / 温度保护 / 光伏余电充电 / 低价充电 / 高峰放电
- REST API: 5 个端点
"""
from __future__ import annotations

import math
from datetime import datetime
from unittest.mock import patch

import pytest

from app.services.charging.strategy_base import (
    ChargingContext,
    ChargingDecision,
    ChargingMode,
    ChargingStrategy,
)
from app.services.charging.mode_manual import ManualStrategy
from app.services.charging.mode_timed import TimedStrategy
from app.services.charging.mode_solar import SolarStrategy
from app.services.charging.mode_price import PriceStrategy
from app.services.charging.mode_balanced import BalancedStrategy
from app.services.charging.strategy_engine import (
    StrategyEngine,
    get_charging_engine,
)
from app.services.charging.solar_forecast import SolarForecaster, WeatherType
from app.services.charging.storage_optimizer import (
    StorageOptimizer,
    StorageAction,
)


# ─── Fixtures ───

def make_ctx(
    station_id="ST-001",
    charger_id="CHG-001",
    rated=120.0,
    demand=60.0,
    pv=0.0,
    battery_soc=None,
    battery_avail=0.0,
    price=None,
    in_valley=None,
    manual=None,
    grid_limit=None,
    target_soc=None,
    current_soc=None,
    temp=None,
) -> ChargingContext:
    return ChargingContext(
        station_id=station_id,
        charger_id=charger_id,
        rated_power_kw=rated,
        demand_power_kw=demand,
        pv_output_kw=pv,
        battery_soc=battery_soc,
        battery_available_kw=battery_avail,
        battery_capacity_kwh=200.0,
        battery_temp_c=temp,
        grid_price=price,
        grid_power_limit_kw=grid_limit,
        in_valley_period=in_valley,
        manual_power_kw=manual,
        target_soc=target_soc,
        current_soc=current_soc,
    )


# ─── 数据模型 & 基类 ───

class TestStrategyBase:
    def test_charging_mode_values(self):
        assert ChargingMode.MANUAL.value == "manual"
        assert ChargingMode.TIMED.value == "timed"
        assert ChargingMode.SOLAR.value == "solar"
        assert ChargingMode.PRICE.value == "price"
        assert ChargingMode.BALANCED.value == "balanced"

    def test_decision_reconcile_single_source(self):
        d = ChargingDecision(mode=ChargingMode.SOLAR, pv_power_kw=50)
        d.reconcile_source()
        assert d.source == "pv"
        assert d.target_power_kw == 50

    def test_decision_reconcile_mixed(self):
        d = ChargingDecision(
            mode=ChargingMode.BALANCED,
            pv_power_kw=30,
            battery_power_kw=10,
            grid_power_kw=20,
        )
        d.reconcile_source()
        assert d.source == "mixed"
        assert d.target_power_kw == 60

    def test_decision_reconcile_none(self):
        d = ChargingDecision(mode=ChargingMode.PRICE)
        d.reconcile_source()
        assert d.source == "none"
        assert d.target_power_kw == 0

    def test_clamp_power(self):
        assert ChargingStrategy.clamp_power(150, 120) == 120
        assert ChargingStrategy.clamp_power(-5, 120) == 0
        assert ChargingStrategy.clamp_power(50, 120) == 50

    def test_strategy_is_abstract(self):
        with pytest.raises(TypeError):
            ChargingStrategy()  # type: ignore[abstract]


# ─── 手动模式 ───

class TestManualStrategy:
    def setup_method(self):
        self.s = ManualStrategy()

    def test_mode_and_priority(self):
        assert self.s.mode == ChargingMode.MANUAL
        assert self.s.priority == 1

    def test_manual_power_respected(self):
        ctx = make_ctx(demand=60, manual=30)
        d = self.s.evaluate(ctx)
        assert d.mode == ChargingMode.MANUAL
        assert d.target_power_kw == 30
        assert d.curtailed is False  # 用户主动设定,不算降功率

    def test_manual_clamped_to_rated(self):
        ctx = make_ctx(rated=120, manual=200)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 120

    def test_manual_falls_back_to_demand(self):
        """未设定手动功率时,回落到充电需求"""
        ctx = make_ctx(demand=80, manual=None)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 80


# ─── 定时模式 ───

class TestTimedStrategy:
    def setup_method(self):
        self.s = TimedStrategy()

    def test_mode_and_priority(self):
        assert self.s.mode == ChargingMode.TIMED
        assert self.s.priority == 2

    def test_valley_full_power(self):
        """低谷时段满功率充电"""
        ctx = make_ctx(demand=60, rated=120, in_valley=True)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 60
        assert d.curtailed is False

    def test_peak_stop(self):
        """高峰(非低谷)时段停充"""
        ctx = make_ctx(demand=60, in_valley=False)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 0
        assert d.curtailed is True

    def test_valley_clamped_to_rated(self):
        ctx = make_ctx(demand=200, rated=120, in_valley=True)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 120

    def test_no_period_info_defaults_conservative(self):
        """无时段信息时保守停充"""
        ctx = make_ctx(demand=60, in_valley=None)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 0


# ─── 光伏优先 ───

class TestSolarStrategy:
    def setup_method(self):
        self.s = SolarStrategy()

    def test_mode_and_priority(self):
        assert self.s.mode == ChargingMode.SOLAR
        assert self.s.priority == 3

    def test_pv_exceeds_demand(self):
        """光伏 > 需求 → 按需求充,全部来自光伏"""
        ctx = make_ctx(demand=40, pv=80)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 40
        assert d.pv_power_kw == 40
        assert d.source == "pv"
        assert d.grid_power_kw == 0
        assert d.curtailed is False

    def test_pv_below_demand_curtails(self):
        """光伏 < 需求 → 降功率到光伏水平"""
        ctx = make_ctx(demand=80, pv=30)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 30
        assert d.pv_power_kw == 30
        assert d.grid_power_kw == 0
        assert d.curtailed is True

    def test_zero_pv_zero_charge(self):
        ctx = make_ctx(demand=80, pv=0)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 0
        assert d.curtailed is True

    def test_pv_clamped_to_rated(self):
        ctx = make_ctx(demand=200, rated=120, pv=150)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 120


# ─── 电价优先 ───

class TestPriceStrategy:
    def setup_method(self):
        self.s = PriceStrategy()

    def test_mode_and_priority(self):
        assert self.s.mode == ChargingMode.PRICE
        assert self.s.priority == 4

    def test_low_price_charges(self):
        """低价时段集中充电"""
        ctx = make_ctx(demand=60, price=0.3)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 60
        assert d.source == "grid"
        assert d.curtailed is False

    def test_high_price_stops(self):
        """高电价时段暂停充电"""
        ctx = make_ctx(demand=60, price=1.2)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 0
        assert d.curtailed is True

    def test_clamped_to_rated(self):
        ctx = make_ctx(demand=200, rated=120, price=0.3)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 120

    def test_no_price_defaults_charge(self):
        """无电价信息时默认允许充电(不阻塞)"""
        ctx = make_ctx(demand=60, price=None)
        d = self.s.evaluate(ctx)
        assert d.target_power_kw == 60


# ─── 均衡模式 ───

class TestBalancedStrategy:
    def setup_method(self):
        self.s = BalancedStrategy()

    def test_mode_and_priority(self):
        assert self.s.mode == ChargingMode.BALANCED
        assert self.s.priority == 5

    def test_pv_covers_all(self):
        """光伏满足全部需求"""
        ctx = make_ctx(demand=50, pv=80, battery_soc=0.5, battery_avail=50, price=0.6)
        d = self.s.evaluate(ctx)
        assert d.pv_power_kw == 50
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 0
        assert d.source == "pv"
        assert d.target_power_kw == 50

    def test_pv_plus_battery(self):
        """光伏不足,储能补足"""
        ctx = make_ctx(demand=60, pv=30, battery_soc=0.7, battery_avail=50, price=0.6)
        d = self.s.evaluate(ctx)
        assert d.pv_power_kw == 30
        assert d.battery_power_kw == 30
        assert d.target_power_kw == 60
        assert d.source == "mixed"

    def test_pv_battery_grid_all_sources(self):
        """光伏+储能仍不足,电网兜底"""
        ctx = make_ctx(demand=120, pv=30, battery_soc=0.7, battery_avail=40, price=0.6)
        d = self.s.evaluate(ctx)
        assert d.pv_power_kw == 30
        assert d.battery_power_kw == 40
        assert d.grid_power_kw == 50
        assert d.target_power_kw == 120
        assert d.source == "mixed"

    def test_low_soc_battery_not_discharged(self):
        """储能 SOC 过低时不放电"""
        ctx = make_ctx(demand=120, pv=30, battery_soc=0.05, battery_avail=40, price=0.6)
        d = self.s.evaluate(ctx)
        assert d.pv_power_kw == 30
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 90

    def test_grid_limit_respected(self):
        """电网取电上限生效"""
        ctx = make_ctx(
            demand=120, pv=30, battery_soc=0.7, battery_avail=40,
            price=0.6, grid_limit=50,
        )
        d = self.s.evaluate(ctx)
        assert d.grid_power_kw == 50
        # 30(pv) + 40(battery) + 50(grid) = 120, 刚好
        assert d.target_power_kw == 120

    def test_grid_limit_curtails(self):
        """电网上限使总功率低于需求 → 降功率"""
        ctx = make_ctx(
            demand=120, pv=30, battery_soc=0.7, battery_avail=40,
            price=0.6, grid_limit=20,
        )
        d = self.s.evaluate(ctx)
        assert d.grid_power_kw == 20
        assert d.target_power_kw == 90  # 30+40+20
        assert d.curtailed is True


# ─── StrategyEngine ───

class TestStrategyEngine:
    def setup_method(self):
        self.engine = StrategyEngine()

    def test_default_mode(self):
        assert self.engine.current_mode == ChargingMode.BALANCED

    def test_registers_all_strategies(self):
        modes = set(self.engine.strategies.keys())
        assert modes == {
            ChargingMode.MANUAL, ChargingMode.TIMED, ChargingMode.SOLAR,
            ChargingMode.PRICE, ChargingMode.BALANCED,
        }

    def test_list_strategies_sorted_by_priority(self):
        infos = self.engine.list_strategies()
        priorities = [i["priority"] for i in infos]
        assert priorities == sorted(priorities)
        assert priorities[0] == 1  # manual 最高

    def test_switch_mode(self):
        self.engine.switch_mode(ChargingMode.SOLAR)
        assert self.engine.current_mode == ChargingMode.SOLAR

    def test_switch_mode_by_string(self):
        self.engine.switch_mode("price")
        assert self.engine.current_mode == ChargingMode.PRICE

    def test_switch_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            self.engine.switch_mode("nonexistent")

    def test_evaluate_uses_current_mode(self):
        self.engine.switch_mode(ChargingMode.SOLAR)
        ctx = make_ctx(demand=40, pv=80)
        d = self.engine.evaluate(ctx)
        assert d.mode == ChargingMode.SOLAR
        assert d.target_power_kw == 40

    def test_evaluate_explicit_mode_override(self):
        ctx = make_ctx(demand=60, price=1.2)
        d = self.engine.evaluate(ctx, mode=ChargingMode.MANUAL)
        assert d.mode == ChargingMode.MANUAL

    def test_resolve_conflict_manual_preempts(self):
        """冲突解决: 手动指令抢占当前模式"""
        self.engine.switch_mode(ChargingMode.PRICE)
        ctx = make_ctx(demand=60, price=1.2, manual=30)  # 高价本应停充
        d = self.engine.resolve(ctx)
        assert d.mode == ChargingMode.MANUAL
        assert d.target_power_kw == 30

    def test_resolve_no_manual_uses_current(self):
        self.engine.switch_mode(ChargingMode.PRICE)
        ctx = make_ctx(demand=60, price=1.2, manual=None)
        d = self.engine.resolve(ctx)
        assert d.mode == ChargingMode.PRICE
        assert d.target_power_kw == 0

    def test_get_strategy_by_mode(self):
        s = self.engine.get_strategy(ChargingMode.SOLAR)
        assert isinstance(s, SolarStrategy)

    def test_per_station_mode(self):
        """按站点独立切换模式"""
        self.engine.switch_mode(ChargingMode.SOLAR, station_id="ST-A")
        self.engine.switch_mode(ChargingMode.PRICE, station_id="ST-B")
        assert self.engine.get_current_mode("ST-A") == ChargingMode.SOLAR
        assert self.engine.get_current_mode("ST-B") == ChargingMode.PRICE

    def test_get_current_mode_falls_back_to_global(self):
        """无站点级模式时回落到全局"""
        self.engine.switch_mode(ChargingMode.TIMED)
        assert self.engine.get_current_mode("ST-NEW") == ChargingMode.TIMED


# ─── 光伏预测 ───

class TestSolarForecaster:
    def setup_method(self):
        self.f = SolarForecaster()

    def test_weather_factors(self):
        assert self.f.weather_factor(WeatherType.SUNNY) == 1.0
        assert self.f.weather_factor(WeatherType.CLOUDY) == 0.5
        assert self.f.weather_factor(WeatherType.RAINY) == 0.2

    def test_weather_factor_invalid_raises(self):
        with pytest.raises(ValueError):
            self.f.weather_factor("snowy")  # type: ignore[arg-type]

    def test_forecast_24_points(self):
        result = self.f.forecast_24h(installed_kw=100, weather="sunny")
        assert len(result.points) == 24
        assert result.weather == "sunny"
        assert result.installed_kw == 100

    def test_night_hours_zero(self):
        """夜间(0-5点, 18-23点)功率为0"""
        result = self.f.forecast_24h(installed_kw=100, weather="sunny")
        night = [p.power_kw for p in result.points if p.hour < 6 or p.hour >= 18]
        assert all(v == 0 for v in night)

    def test_peak_at_midday(self):
        """峰值出现在正午附近"""
        result = self.f.forecast_24h(installed_kw=100, weather="sunny")
        assert result.peak_power_kw == pytest.approx(100, abs=1)
        peak_hour = max(result.points, key=lambda p: p.power_kw).hour
        assert peak_hour == 12

    def test_cloudy_reduces_output(self):
        sunny = self.f.forecast_24h(100, "sunny")
        cloudy = self.f.forecast_24h(100, "cloudy")
        assert cloudy.total_kwh < sunny.total_kwh
        assert cloudy.peak_power_kw == pytest.approx(50, abs=1)

    def test_rainy_lowest(self):
        rainy = self.f.forecast_24h(100, "rainy")
        cloudy = self.f.forecast_24h(100, "cloudy")
        assert rainy.total_kwh < cloudy.total_kwh

    def test_total_kwh_positive(self):
        result = self.f.forecast_24h(100, "sunny")
        assert result.total_kwh > 0
        # 100kW 晴天 12h 正弦积分 ≈ 100*12*2/π ≈ 764 kWh
        assert 600 < result.total_kwh < 900

    def test_forecast_with_history(self):
        """基于历史曲线预测: 输出形状应与历史相似(正弦曲线峰值在正午)"""
        # 6:00-17:00 白天发电, 峰值在 12:00
        day_curve = [0, 26, 50, 71, 87, 97, 100, 97, 87, 71, 50, 26]
        history = [0.0] * 6 + [float(v) for v in day_curve] + [0.0] * 6
        result = self.f.forecast_with_history(history, weather="sunny")
        assert len(result.points) == 24
        # 正午附近应保持高功率
        noon = next(p for p in result.points if p.hour == 12)
        assert noon.power_kw == 100
        # 阴天系数 0.5
        cloudy = self.f.forecast_with_history(history, weather="cloudy")
        noon_c = next(p for p in cloudy.points if p.hour == 12)
        assert noon_c.power_kw == 50


# ─── 储能调度 ───

class TestStorageOptimizer:
    def setup_method(self):
        self.o = StorageOptimizer()

    def test_soc_safe_range_constants(self):
        assert self.o.SOC_MIN == 0.10
        assert self.o.SOC_MAX == 0.90

    def test_low_soc_must_charge(self):
        """SOC 低于下限 → 强制充电,健康状态告警"""
        action = self.o.optimize(soc=0.05, pv_surplus_kw=20)
        assert action.action == "charge"
        assert action.power_kw > 0
        assert action.health_ok is False

    def test_high_soc_no_charge(self):
        """SOC 高于上限 → 禁止充电"""
        action = self.o.optimize(soc=0.95, pv_surplus_kw=20)
        assert action.action != "charge"
        assert action.health_ok is False

    def test_pv_surplus_charges(self):
        """光伏余电优先充入储能"""
        action = self.o.optimize(soc=0.5, pv_surplus_kw=30)
        assert action.action == "charge"
        assert action.power_kw > 0
        assert "光伏" in action.reason or "pv" in action.reason.lower()

    def test_low_price_charges_from_grid(self):
        """电网低价时段充电"""
        action = self.o.optimize(soc=0.5, pv_surplus_kw=0, grid_price=0.3)
        assert action.action == "charge"
        assert action.power_kw > 0

    def test_peak_price_discharges(self):
        """高峰电价时段放电供给负荷"""
        action = self.o.optimize(soc=0.7, grid_price=1.2, load_kw=50)
        assert action.action == "discharge"
        assert action.power_kw < 0

    def test_flat_price_idle(self):
        """平段无余电 → 待机"""
        action = self.o.optimize(soc=0.5, pv_surplus_kw=0, grid_price=0.6, load_kw=0)
        assert action.action == "idle"
        assert action.power_kw == 0

    def test_temp_protection_blocks_charge(self):
        """温度过高禁止充电"""
        action = self.o.optimize(soc=0.5, pv_surplus_kw=30, temp_c=60)
        assert action.action != "charge"

    def test_low_soc_blocks_discharge(self):
        """SOC 过低即使高价也不放电"""
        action = self.o.optimize(soc=0.05, grid_price=1.2, load_kw=50)
        # SOC<MIN 应优先充电恢复,而非放电
        assert action.action != "discharge"

    def test_within_safe_range(self):
        action = self.o.optimize(soc=0.5)
        assert action.within_safe_range is True
        action_low = self.o.optimize(soc=0.05)
        assert action_low.within_safe_range is False

    def test_target_soc_management(self):
        """SOC 目标管理: 当前低于目标时倾向充电"""
        action = self.o.optimize(soc=0.3, pv_surplus_kw=30, target_soc=0.7)
        assert action.action == "charge"


# ─── API 端点 ───

class TestChargingAPI:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        from app.services.charging import strategy_engine as engine_mod
        engine_mod._engine = None  # 重置单例,保证测试隔离
        self.client = client

    def test_list_strategies(self):
        resp = self.client.get("/api/v1/charging/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        modes = [s["mode"] for s in data["data"]]
        assert set(modes) == {"manual", "timed", "solar", "price", "balanced"}

    def test_get_current_strategy(self):
        resp = self.client.get("/api/v1/charging/strategy/current")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["mode"] == "balanced"

    def test_switch_strategy(self):
        resp = self.client.post("/api/v1/charging/strategy/switch", json={
            "mode": "solar",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["mode"] == "solar"
        # 再次查询确认生效
        cur = self.client.get("/api/v1/charging/strategy/current").json()["data"]
        assert cur["mode"] == "solar"

    def test_switch_invalid_strategy(self):
        resp = self.client.post("/api/v1/charging/strategy/switch", json={
            "mode": "nonexistent",
        })
        assert resp.status_code == 400

    def test_get_solar_forecast_default(self):
        resp = self.client.get("/api/v1/charging/forecast/solar?installed_kw=100&weather=sunny")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["weather"] == "sunny"
        assert len(data["points"]) == 24
        assert data["total_kwh"] > 0

    def test_get_solar_forecast_invalid_weather(self):
        resp = self.client.get("/api/v1/charging/forecast/solar?installed_kw=100&weather=snowy")
        assert resp.status_code == 400

    def test_get_storage_status(self):
        resp = self.client.get("/api/v1/charging/storage/status?soc=0.5&pv_surplus_kw=30")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "charge"
        assert data["power_kw"] > 0
