"""test_solar_forecast.py — SolarForecaster 光伏预测单元测试

被测对象: app/services/charging/solar_forecast.py。

纯逻辑/数值测试, 无外部依赖。模型契约:
- 白天 6:00-18:00(左闭右开)出力按正弦曲线, 峰值在 12:00(= 装机容量)。
- 天气系数: sunny 1.0 / cloudy 0.5 / rainy 0.2。
- 夜间(< 6 或 >= 18)出力为 0。

覆盖维度:
- weather_factor: 三种天气(字符串/枚举)、非法值抛 ValueError、WeatherType 取值。
- _day_shape: 夜间 0、正午峰值=装机、9/15 对称、6 点起 0 / 18 点止 0。
- forecast_24h: 24 点、metadata、total=∑points、夜间点为 0、天气缩放(大小+峰值精确倍数)、
  装机 0 全零、start_hour 偏移(总量守恒)、枚举天气 label、峰值上界。
- forecast_with_history: 基础乘系数、天气折算、空历史、不足 24 点补 0、installed_kw=max(history)。
"""
import math

import pytest

from app.services.charging.solar_forecast import (
    SolarForecaster,
    WeatherType,
    ForecastPoint,
    SolarForecast,
)


@pytest.fixture
def f():
    return SolarForecaster()


# ─── WeatherType / weather_factor ───

class TestWeatherType:
    def test_values(self):
        assert WeatherType.SUNNY.value == "sunny"
        assert WeatherType.CLOUDY.value == "cloudy"
        assert WeatherType.RAINY.value == "rainy"


class TestWeatherFactor:
    def test_string_inputs(self, f):
        assert f.weather_factor("sunny") == 1.0
        assert f.weather_factor("cloudy") == 0.5
        assert f.weather_factor("rainy") == 0.2

    def test_enum_inputs(self, f):
        assert f.weather_factor(WeatherType.SUNNY) == 1.0
        assert f.weather_factor(WeatherType.CLOUDY) == 0.5
        assert f.weather_factor(WeatherType.RAINY) == 0.2

    def test_invalid_string_raises(self, f):
        with pytest.raises(ValueError, match="未知天气类型"):
            f.weather_factor("storm")

    def test_invalid_type_raises(self, f):
        with pytest.raises(ValueError):
            f.weather_factor(123)


# ─── _day_shape ───

class TestDayShape:
    def test_night_hours_zero(self, f):
        for h in [0, 3, 5, 18, 22]:
            assert f._day_shape(h, 100) == 0.0

    def test_noon_is_peak_equal_installed(self, f):
        # sin(pi * (12-6) / 12) = sin(pi/2) = 1.0
        assert abs(f._day_shape(12, 100) - 100.0) < 1e-9

    def test_symmetry_around_noon(self, f):
        assert abs(f._day_shape(9, 100) - f._day_shape(15, 100)) < 1e-9
        assert abs(f._day_shape(7, 100) - f._day_shape(17, 100)) < 1e-9

    def test_boundaries(self, f):
        # 6 点含(DAY_START), sin(0)=0; 18 点不含, 直接 0
        assert f._day_shape(6, 100) == 0.0
        assert f._day_shape(18, 100) == 0.0

    def test_daytime_positive_between_boundaries(self, f):
        for h in [7, 9, 11, 13, 15, 17]:
            assert f._day_shape(h, 100) > 0.0


# ─── forecast_24h ───

class TestForecast24h:
    def test_returns_24_points_with_sequential_hours(self, f):
        r = f.forecast_24h(50, "sunny")
        assert len(r.points) == 24
        assert [p.hour for p in r.points] == list(range(24))
        assert all(isinstance(p, ForecastPoint) for p in r.points)

    def test_metadata(self, f):
        r = f.forecast_24h(50, "sunny")
        assert isinstance(r, SolarForecast)
        assert r.weather == "sunny"
        assert r.installed_kw == 50

    def test_total_equals_sum_of_points(self, f):
        r = f.forecast_24h(50, "sunny")
        expected = round(sum(p.power_kw for p in r.points), 3)
        assert r.total_kwh == expected

    def test_peak_equals_installed_sunny(self, f):
        r = f.forecast_24h(100, "sunny")
        assert abs(r.peak_power_kw - 100.0) < 1e-9

    def test_night_points_zero(self, f):
        r = f.forecast_24h(50, "sunny")
        for p in r.points:
            if p.hour < 6 or p.hour >= 18:
                assert p.power_kw == 0.0

    def test_weather_scales_total_monotonically(self, f):
        sunny = f.forecast_24h(100, "sunny")
        cloudy = f.forecast_24h(100, "cloudy")
        rainy = f.forecast_24h(100, "rainy")
        assert sunny.total_kwh > cloudy.total_kwh > rainy.total_kwh

    def test_cloudy_peak_is_half_sunny(self, f):
        # 单点 peak 不受累加 round 误差影响, 倍数精确
        sunny = f.forecast_24h(100, "sunny")
        cloudy = f.forecast_24h(100, "cloudy")
        assert abs(cloudy.peak_power_kw - sunny.peak_power_kw * 0.5) < 1e-9
        assert abs(cloudy.peak_power_kw - 50.0) < 1e-9

    def test_installed_zero_all_zero(self, f):
        r = f.forecast_24h(0, "sunny")
        assert r.total_kwh == 0.0
        assert r.peak_power_kw == 0.0
        assert all(p.power_kw == 0.0 for p in r.points)

    def test_start_hour_offset_keeps_total(self, f):
        """start_hour 只改变小时排列顺序, 24h 总量应守恒。"""
        base = f.forecast_24h(50, "sunny", start_hour=0)
        shifted = f.forecast_24h(50, "sunny", start_hour=12)
        assert shifted.points[0].hour == 12
        assert abs(shifted.total_kwh - base.total_kwh) < 1e-3

    def test_enum_weather_label_converted_to_value(self, f):
        r = f.forecast_24h(50, WeatherType.CLOUDY)
        assert r.weather == "cloudy"  # 枚举转 value 字符串

    def test_peak_le_installed(self, f):
        r = f.forecast_24h(77, "sunny")
        assert 0 < r.peak_power_kw <= 77

    def test_rainy_peak_is_twenty_percent(self, f):
        r = f.forecast_24h(100, "rainy")
        assert abs(r.peak_power_kw - 20.0) < 1e-9  # 100 * 0.2


# ─── forecast_with_history ───

class TestForecastWithHistory:
    def test_basic_multiplies_by_factor(self, f):
        history = [0.0] * 24
        history[12] = 100.0
        r = f.forecast_with_history(history, "sunny")

        noon = [p for p in r.points if p.hour == 12][0]
        assert noon.power_kw == 100.0
        assert r.peak_power_kw == 100.0
        assert r.installed_kw == 100.0  # max(history)

    def test_weather_factor_applied(self, f):
        history = [0.0] * 24
        history[12] = 100.0
        r = f.forecast_with_history(history, "rainy")

        noon = [p for p in r.points if p.hour == 12][0]
        assert abs(noon.power_kw - 20.0) < 1e-3  # 100 * 0.2

    def test_empty_history(self, f):
        r = f.forecast_with_history([], "sunny")
        assert r.total_kwh == 0.0
        assert r.installed_kw == 0.0
        assert r.peak_power_kw == 0.0
        assert len(r.points) == 24

    def test_short_history_pads_with_zero(self, f):
        """history 不足 24 点时, 缺失位置补 0。"""
        r = f.forecast_with_history([10.0, 20.0], "sunny")
        assert r.points[0].power_kw == 10.0
        assert r.points[1].power_kw == 20.0
        assert r.points[2].power_kw == 0.0
        assert r.points[23].power_kw == 0.0
        assert len(r.points) == 24

    def test_installed_kw_is_max_of_history(self, f):
        history = [5.0, 80.0, 30.0] + [0.0] * 21
        r = f.forecast_with_history(history, "sunny")
        assert r.installed_kw == 80.0

    def test_history_all_zero(self, f):
        r = f.forecast_with_history([0.0] * 24, "sunny")
        assert r.total_kwh == 0.0
        assert r.installed_kw == 0.0
