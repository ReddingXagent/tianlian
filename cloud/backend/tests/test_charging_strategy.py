"""
充电策略服务层 + API 测试

覆盖:
- ChargingMode 枚举
- 5 种充电模式策略 (manual/timed/solar/price/balanced)
- StrategyEngine 模式管理/切换/评估/冲突解决
- SolarForecaster 光伏预测
- StorageOptimizer 储能优化
- API 端点
"""
import pytest
from datetime import datetime
from app.services.charging import (
    ChargingMode,
    ChargingContext,
    ChargingDecision,
    ChargingStrategy,
    ManualStrategy,
    TimedStrategy,
    SolarStrategy,
    PriceStrategy,
    BalancedStrategy,
    StrategyEngine,
    get_charging_engine,
    SolarForecaster,
    ForecastPoint,
    SolarForecast,
    WeatherType,
    StorageOptimizer,
    StorageAction,
)

# ═══════════════════════════════════════════════════════════════
# ChargingMode 枚举测试
# ═══════════════════════════════════════════════════════════════

class TestChargingMode:
    """充电模式枚举测试"""

    def test_has_five_modes(self):
        assert len(ChargingMode) == 5

    def test_mode_values(self):
        assert ChargingMode.MANUAL.value == "manual"
        assert ChargingMode.TIMED.value == "timed"
        assert ChargingMode.SOLAR.value == "solar"
        assert ChargingMode.PRICE.value == "price"
        assert ChargingMode.BALANCED.value == "balanced"


# ═══════════════════════════════════════════════════════════════
# 各模式策略测试
# ═══════════════════════════════════════════════════════════════

def _make_ctx(**kwargs) -> ChargingContext:
    """快捷创建 ChargingContext"""
    defaults = dict(
        station_id="station-1",
        charger_id="charger-1",
        rated_power_kw=120,
        demand_power_kw=60,
    )
    defaults.update(kwargs)
    return ChargingContext(**defaults)


class TestManualStrategy:
    """手动模式策略测试"""

    def test_mode_and_priority(self):
        s = ManualStrategy()
        assert s.mode == ChargingMode.MANUAL
        assert s.priority == 1

    def test_uses_manual_power(self):
        s = ManualStrategy()
        ctx = _make_ctx(manual_power_kw=40)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 40
        assert d.source == "grid"

    def test_clamps_to_rated(self):
        s = ManualStrategy()
        ctx = _make_ctx(manual_power_kw=200, rated_power_kw=120)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 120

    def test_falls_back_to_demand(self):
        s = ManualStrategy()
        ctx = _make_ctx(demand_power_kw=50, manual_power_kw=None)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 50

    def test_priority_is_highest(self):
        s = ManualStrategy()
        assert s.priority == 1


class TestTimedStrategy:
    """定时模式策略测试"""

    def test_mode_and_priority(self):
        s = TimedStrategy()
        assert s.mode == ChargingMode.TIMED
        assert s.priority == 2

    def test_charge_in_valley(self):
        s = TimedStrategy()
        ctx = _make_ctx(demand_power_kw=60, in_valley_period=True)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 60
        assert not d.curtailed

    def test_stop_in_peak(self):
        s = TimedStrategy()
        ctx = _make_ctx(demand_power_kw=60, in_valley_period=False)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 0
        assert d.curtailed

    def test_stop_when_no_period_info(self):
        s = TimedStrategy()
        ctx = _make_ctx(demand_power_kw=60, in_valley_period=None)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 0

    def test_clamps_to_rated(self):
        s = TimedStrategy()
        ctx = _make_ctx(demand_power_kw=200, rated_power_kw=120, in_valley_period=True)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 120


class TestSolarStrategy:
    """光伏优先模式策略测试"""

    def test_mode_and_priority(self):
        s = SolarStrategy()
        assert s.mode == ChargingMode.SOLAR
        assert s.priority == 3

    def test_charge_when_sunny(self):
        s = SolarStrategy()
        ctx = _make_ctx(demand_power_kw=60, pv_output_kw=80)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 60  # 光伏充足按需求
        assert not d.curtailed

    def test_curtail_when_pv_insufficient(self):
        s = SolarStrategy()
        ctx = _make_ctx(demand_power_kw=60, pv_output_kw=20)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 20  # 降功率至光伏水平
        assert d.curtailed
        assert d.source == "pv"

    def test_idle_when_dark(self):
        s = SolarStrategy()
        ctx = _make_ctx(demand_power_kw=60, pv_output_kw=0)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 0
        assert d.curtailed


class TestPriceStrategy:
    """电价优先模式策略测试"""

    def test_mode_and_priority(self):
        s = PriceStrategy()
        assert s.mode == ChargingMode.PRICE
        assert s.priority == 4

    def test_charge_when_low_price(self):
        s = PriceStrategy()
        ctx = _make_ctx(demand_power_kw=60, grid_price=0.3)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 60  # 低谷电价,集中充电
        assert not d.curtailed

    def test_stop_when_high_price(self):
        s = PriceStrategy()
        ctx = _make_ctx(demand_power_kw=60, grid_price=0.8)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 0
        assert d.curtailed

    def test_allow_when_no_price(self):
        s = PriceStrategy()
        ctx = _make_ctx(demand_power_kw=60, grid_price=None)
        d = s.evaluate(ctx)
        assert d.target_power_kw == 60  # 无电价信息,不阻塞
        assert not d.curtailed

    def test_valley_threshold(self):
        s = PriceStrategy()
        assert s.VALLEY_THRESHOLD == 0.50


class TestBalancedStrategy:
    """均衡模式策略测试"""

    def test_mode_and_priority(self):
        s = BalancedStrategy()
        assert s.mode == ChargingMode.BALANCED
        assert s.priority == 5

    def test_pv_first_then_battery_then_grid(self):
        s = BalancedStrategy()
        ctx = _make_ctx(
            demand_power_kw=100,
            pv_output_kw=40,
            battery_soc=0.8,
            battery_available_kw=30,
            grid_power_limit_kw=100,
        )
        d = s.evaluate(ctx)
        assert d.pv_power_kw == 40
        assert d.battery_power_kw == 30
        assert d.grid_power_kw == 30
        assert d.target_power_kw == 100
        assert d.source == "mixed"

    def test_totally_from_pv(self):
        s = BalancedStrategy()
        ctx = _make_ctx(demand_power_kw=40, pv_output_kw=50)
        d = s.evaluate(ctx)
        assert d.pv_power_kw == 40
        assert d.source == "pv"

    def test_from_grid_when_no_pv_no_battery(self):
        s = BalancedStrategy()
        ctx = _make_ctx(demand_power_kw=50, pv_output_kw=0, battery_soc=0.1)
        d = s.evaluate(ctx)
        assert d.grid_power_kw == 50
        assert d.source == "grid"

    def test_pv_surplus_goes_to_pv_first(self):
        s = BalancedStrategy()
        ctx = _make_ctx(
            demand_power_kw=30,
            pv_output_kw=30,
            battery_soc=0.8,
        )
        d = s.evaluate(ctx)
        assert d.pv_power_kw == 30
        assert d.battery_power_kw == 0
        assert d.grid_power_kw == 0

    def test_clamps_total_to_rated(self):
        s = BalancedStrategy()
        ctx = _make_ctx(
            demand_power_kw=200,
            pv_output_kw=100,
            battery_soc=0.8,
            battery_available_kw=100,
            rated_power_kw=120,
        )
        d = s.evaluate(ctx)
        assert abs(d.target_power_kw - 120) < 0.1

    def test_reason_contains_information(self):
        s = BalancedStrategy()
        ctx = _make_ctx(demand_power_kw=60, pv_output_kw=20, battery_soc=0.5, battery_available_kw=10)
        d = s.evaluate(ctx)
        assert "均衡调度" in d.reason
        assert "太阳能" not in d.reason


# ═══════════════════════════════════════════════════════════════
# StrategyEngine 测试
# ═══════════════════════════════════════════════════════════════

class TestStrategyEngine:
    """策略引擎调度器测试"""

    def test_default_mode(self):
        engine = StrategyEngine()
        assert engine.current_mode == ChargingMode.BALANCED

    def test_switch_mode_global(self):
        engine = StrategyEngine()
        engine.switch_mode("solar")
        assert engine.current_mode == ChargingMode.SOLAR

    def test_switch_mode_by_station(self):
        engine = StrategyEngine()
        engine.switch_mode("price", station_id="station-a")
        assert engine.get_current_mode("station-a") == ChargingMode.PRICE
        # 全局不受影响
        assert engine.current_mode == ChargingMode.BALANCED

    def test_station_mode_overrides_global(self):
        engine = StrategyEngine()
        engine.switch_mode("manual")
        engine.switch_mode("timed", station_id="station-a")
        assert engine.get_current_mode("station-a") == ChargingMode.TIMED
        assert engine.get_current_mode("station-b") == ChargingMode.MANUAL

    def test_switch_with_enum(self):
        engine = StrategyEngine()
        engine.switch_mode(ChargingMode.MANUAL)
        assert engine.current_mode == ChargingMode.MANUAL

    def test_switch_invalid_mode(self):
        engine = StrategyEngine()
        with pytest.raises(ValueError):
            engine.switch_mode("invalid_mode")

    def test_switch_updates_timestamp(self):
        engine = StrategyEngine()
        engine.switch_mode("solar")
        assert engine.last_switched_at is not None

    def test_list_strategies_returns_5(self):
        engine = StrategyEngine()
        items = engine.list_strategies()
        assert len(items) == 5

    def test_list_strategies_sorted_by_priority(self):
        engine = StrategyEngine()
        items = engine.list_strategies()
        priorities = [i["priority"] for i in items]
        assert priorities == sorted(priorities)

    def test_list_strategies_contains_mode_names(self):
        engine = StrategyEngine()
        items = engine.list_strategies()
        modes = {i["mode"] for i in items}
        assert modes == {"manual", "timed", "solar", "price", "balanced"}

    def test_evaluate_with_current_mode(self):
        engine = StrategyEngine()
        ctx = _make_ctx()
        d = engine.evaluate(ctx)
        assert isinstance(d, ChargingDecision)
        assert d.mode == ChargingMode.BALANCED

    def test_evaluate_with_specified_mode(self):
        engine = StrategyEngine()
        ctx = _make_ctx()
        d = engine.evaluate(ctx, mode="manual")
        assert d.mode == ChargingMode.MANUAL

    def test_evaluate_with_enum_mode(self):
        engine = StrategyEngine()
        ctx = _make_ctx()
        d = engine.evaluate(ctx, mode=ChargingMode.PRICE)
        assert d.mode == ChargingMode.PRICE

    def test_resolve_manual_overrides(self):
        engine = StrategyEngine()
        # 设为 solar, 但提供 manual_power_kw → resolve 应走 manual
        engine.switch_mode("solar")
        ctx = _make_ctx(manual_power_kw=80)
        d = engine.resolve(ctx)
        assert d.mode == ChargingMode.MANUAL
        assert d.target_power_kw == 80

    def test_resolve_no_manual_uses_current(self):
        engine = StrategyEngine()
        engine.switch_mode("timed")
        ctx = _make_ctx(in_valley_period=True)
        d = engine.resolve(ctx)
        assert d.mode == ChargingMode.TIMED

    def test_get_strategy(self):
        engine = StrategyEngine()
        s = engine.get_strategy("manual")
        assert isinstance(s, ManualStrategy)

    def test_get_charging_engine_returns_singleton(self):
        e1 = get_charging_engine()
        e2 = get_charging_engine()
        assert e1 is e2


# ═══════════════════════════════════════════════════════════════
# SolarForecaster 光伏预测测试
# ═══════════════════════════════════════════════════════════════

class TestSolarForecaster:
    """光伏预测器测试"""

    def test_forecast_24h_returns_24_points(self):
        f = SolarForecaster()
        result = f.forecast_24h(installed_kw=50, weather="sunny")
        assert len(result.points) == 24

    def test_forecast_daytime_positive(self):
        f = SolarForecaster()
        result = f.forecast_24h(installed_kw=50, weather="sunny")
        noon = [p for p in result.points if p.hour == 12][0]
        assert noon.power_kw > 0

    def test_forecast_night_zero(self):
        f = SolarForecaster()
        result = f.forecast_24h(installed_kw=50, weather="sunny")
        for p in result.points:
            if p.hour < 6 or p.hour >= 18:
                assert p.power_kw == 0, f"Hour {p.hour} should be 0"

    def test_forecast_weather_factor_reduces(self):
        f = SolarForecaster()
        sunny = f.forecast_24h(installed_kw=50, weather="sunny")
        cloudy = f.forecast_24h(installed_kw=50, weather="cloudy")
        rainy = f.forecast_24h(installed_kw=50, weather="rainy")
        assert sunny.total_kwh > cloudy.total_kwh
        assert cloudy.total_kwh > rainy.total_kwh

    def test_forecast_total_kwh_reasonable(self):
        f = SolarForecaster()
        result = f.forecast_24h(installed_kw=50, weather="sunny")
        assert result.total_kwh > 0
        # 白天 12h × 正弦峰值 ≤ 装机×0.5 × 12
        max_possible = 50 * 12
        assert result.total_kwh < max_possible

    def test_forecast_peak_power(self):
        f = SolarForecaster()
        result = f.forecast_24h(installed_kw=100, weather="sunny")
        assert result.peak_power_kw > 0
        assert result.peak_power_kw <= 100

    def test_weather_factor_sunny(self):
        f = SolarForecaster()
        assert f.weather_factor("sunny") == 1.0

    def test_weather_factor_cloudy(self):
        f = SolarForecaster()
        assert f.weather_factor("cloudy") == 0.5

    def test_weather_factor_rainy(self):
        f = SolarForecaster()
        assert f.weather_factor("rainy") == 0.2

    def test_invalid_weather_raises(self):
        f = SolarForecaster()
        with pytest.raises(ValueError):
            f.weather_factor("unknown")

    def test_forecast_with_history(self):
        f = SolarForecaster()
        history = [0]*24
        history[12] = 100  # 中午峰值100kW
        result = f.forecast_with_history(history, weather="cloudy")
        assert result.total_kwh > 0
        noon = [p for p in result.points if p.hour == 12][0]
        assert noon.power_kw == 50.0  # 100 * 0.5 (cloudy)

    def test_forecast_symmetry(self):
        f = SolarForecaster()
        # 9:00 和 15:00 在正弦曲线上应相等(对称于12:00)
        result = f.forecast_24h(installed_kw=100, weather="sunny")
        h9 = [p for p in result.points if p.hour == 9][0]
        h15 = [p for p in result.points if p.hour == 15][0]
        assert abs(h9.power_kw - h15.power_kw) < 1.0

    def test_forecast_with_custom_start(self):
        f = SolarForecaster()
        result = f.forecast_24h(installed_kw=50, weather="sunny", start_hour=6)
        # start_hour=6 means hour indices shift: first point is hour 6
        assert result.points[0].hour == 6
        assert len(result.points) == 24


# ═══════════════════════════════════════════════════════════════
# StorageOptimizer 储能调度测试
# ═══════════════════════════════════════════════════════════════

class TestStorageOptimizer:
    """储能调度优化器测试"""

    def test_force_charge_when_soc_too_low(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.05)
        assert action.action == "charge"
        assert not action.health_ok
        assert not action.within_safe_range

    def test_idle_when_soc_high_and_no_trigger(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.95)
        assert action.action == "idle"
        assert not action.within_safe_range

    def test_discharge_when_soc_high_and_peak_price(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.95, grid_price=1.0)
        assert action.action == "discharge"
        assert action.power_kw < 0

    def test_discharge_when_soc_high_and_load(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.95, load_kw=30)
        assert action.action == "discharge"

    def test_charge_from_pv_surplus(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5, pv_surplus_kw=30)
        assert action.action == "charge"
        assert action.power_kw > 0
        assert action.health_ok

    def test_charge_from_valley_price(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5, grid_price=0.3)
        assert action.action == "charge"
        assert "低谷电价" in action.reason

    def test_discharge_peak_price(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5, grid_price=1.0, load_kw=20)
        assert action.action == "discharge"
        assert action.power_kw < 0

    def test_idle_flat_price_no_surplus(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5, grid_price=0.6)
        assert action.action == "idle"

    def test_idle_mid_soc_no_pv_no_load_mid_price(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5)
        assert action.action == "idle"

    def test_temp_over_limit_blocks_charge(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5, temp_c=50)
        assert not action.health_ok
        assert action.action == "idle"

    def test_temp_over_limit_allows_discharge(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.5, temp_c=50, grid_price=1.0, load_kw=10)
        assert action.action == "discharge"

    def test_respects_target_soc(self):
        opt = StorageOptimizer()
        action = opt.optimize(soc=0.05, target_soc=0.7)
        assert action.target_soc == 0.7


# ═══════════════════════════════════════════════════════════════
# API 端点测试
# ═══════════════════════════════════════════════════════════════

class TestChargingAPI:
    """充电策略 API 测试"""

    BASE = "/api/v1/charging"

    def test_list_strategies(self, client):
        """列举全部充电模式"""
        response = client.get(f"{self.BASE}/strategies")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        items = data["data"]
        assert len(items) == 5
        modes = {i["mode"] for i in items}
        assert modes == {"manual", "timed", "solar", "price", "balanced"}

    def test_get_current_strategy_default(self, client):
        """默认模式为 balanced"""
        response = client.get(f"{self.BASE}/strategy/current")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["mode"] == "balanced"

    def test_get_current_strategy_with_station(self, client):
        """查询指定站点当前模式"""
        response = client.get(f"{self.BASE}/strategy/current?station_id=station-a")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["station_id"] == "station-a"

    def test_switch_strategy(self, client):
        """切换充电模式"""
        response = client.post(
            f"{self.BASE}/strategy/switch",
            json={"mode": "solar"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["mode"] == "solar"
        assert data["data"]["previous_mode"] == "balanced"

    def test_switch_strategy_by_station(self, client):
        """按站点切换模式"""
        response = client.post(
            f"{self.BASE}/strategy/switch",
            json={"mode": "price", "station_id": "station-a"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["mode"] == "price"
        assert data["data"]["station_id"] == "station-a"

    def test_switch_invalid_mode(self, client):
        """切换非法模式应返回 400"""
        response = client.post(
            f"{self.BASE}/strategy/switch",
            json={"mode": "invalid_mode"},
        )
        assert response.status_code == 400

    def test_switch_returns_previous_mode(self, client):
        """切换后返回前一模式"""
        # 先切换到 solar
        client.post(f"{self.BASE}/strategy/switch", json={"mode": "solar"})
        # 再切回 manual
        response = client.post(
            f"{self.BASE}/strategy/switch",
            json={"mode": "manual"},
        )
        data = response.json()
        assert data["data"]["previous_mode"] == "solar"

    def test_solar_forecast_basic(self, client):
        """光伏预测 API"""
        response = client.get(
            f"{self.BASE}/forecast/solar",
            params={"installed_kw": 50, "weather": "sunny"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        result = data["data"]
        assert result["installed_kw"] == 50
        assert result["weather"] == "sunny"
        assert len(result["points"]) == 24
        assert result["total_kwh"] > 0

    def test_solar_forecast_custom_weather(self, client):
        """光伏预测指定天气"""
        response = client.get(
            f"{self.BASE}/forecast/solar",
            params={"installed_kw": 100, "weather": "cloudy"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["weather"] == "cloudy"
        # 阴天应小于晴天
        assert data["data"]["total_kwh"] > 0

    def test_solar_forecast_invalid_weather(self, client):
        """非法天气应返回 400"""
        response = client.get(
            f"{self.BASE}/forecast/solar",
            params={"installed_kw": 50, "weather": "invalid"},
        )
        assert response.status_code == 400

    def test_storage_status_basic(self, client):
        """储能调度状态 API"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        result = data["data"]
        assert result["soc"] == 0.5
        assert "action" in result
        assert "reason" in result
        assert "health_ok" in result

    def test_storage_status_force_charge(self, client):
        """SOC 过低的储能调度"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.05},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["action"] == "charge"
        assert not data["data"]["health_ok"]

    def test_storage_status_with_price(self, client):
        """带光伏余电和电价的储能调度"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.5, "pv_surplus_kw": 30, "grid_price": 0.3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["action"] == "charge"

    def test_storage_status_discharge_peak(self, client):
        """高电价放电"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.5, "grid_price": 0.95, "load_kw": 20},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["action"] == "discharge"
        assert data["data"]["power_kw"] < 0

    def test_storage_status_with_target_soc(self, client):
        """带目标 SOC 的储能调度"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.05, "target_soc": 0.7},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["target_soc"] == 0.7

    def test_storage_status_with_temp(self, client):
        """温度异常应返回健康警告"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.5, "temp_c": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert not data["data"]["health_ok"]

    def test_storage_status_temp_over_upper_bound(self, client):
        """储能温度超过 100℃ 应被 FastAPI 422 拦截，不落到 service 层"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.5, "temp_c": 9999},
        )
        assert response.status_code == 422

    def test_storage_status_temp_below_lower_bound(self, client):
        """储能温度低于 -50℃ 应被 FastAPI 422 拦截"""
        response = client.get(
            f"{self.BASE}/storage/status",
            params={"soc": 0.5, "temp_c": -999},
        )
        assert response.status_code == 422

    def test_health_endpoint(self, client):
        """健康检查端点在 api/v1 下"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200