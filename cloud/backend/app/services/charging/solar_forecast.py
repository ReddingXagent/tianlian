"""光伏发电预测 — 基于历史曲线 + 天气的简单预测模型

模型:
- 白天(6:00-18:00)出力按正弦曲线, 峰值在正午 12:00
- 天气系数: 晴 1.0 / 阴 0.5 / 雨 0.2
- 夜间出力为 0
- 支持两种入口: 装机容量预测(forecast_24h) / 历史曲线预测(forecast_with_history)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class WeatherType(str, Enum):
    SUNNY = "sunny"    # 晴
    CLOUDY = "cloudy"  # 阴
    RAINY = "rainy"    # 雨


@dataclass
class ForecastPoint:
    """逐小时预测点"""
    hour: int          # 0-23
    power_kw: float    # 预测功率


@dataclass
class SolarForecast:
    """24h 光伏预测结果"""
    weather: str
    installed_kw: float
    points: List[ForecastPoint] = field(default_factory=list)
    total_kwh: float = 0.0     # 未来24h总发电量(数值上 = ∑每小时功率)
    peak_power_kw: float = 0.0  # 预测峰值功率


class SolarForecaster:
    """光伏预测器"""

    DAY_START = 6   # 白天起始小时
    DAY_END = 18    # 白天结束小时(不含)

    WEATHER_FACTORS = {
        WeatherType.SUNNY: 1.0,
        WeatherType.CLOUDY: 0.5,
        WeatherType.RAINY: 0.2,
    }

    def weather_factor(self, weather) -> float:
        """获取天气折算系数(0-1)"""
        if isinstance(weather, WeatherType):
            wt = weather
        else:
            try:
                wt = WeatherType(weather)
            except ValueError:
                raise ValueError(
                    f"未知天气类型: {weather} (支持: sunny/cloudy/rainy)"
                )
        return self.WEATHER_FACTORS[wt]

    def _day_shape(self, hour: int, installed_kw: float) -> float:
        """白天正弦形状: 6点0 → 12点峰值 → 18点0, 夜间0"""
        if not (self.DAY_START <= hour < self.DAY_END):
            return 0.0
        span = self.DAY_END - self.DAY_START
        return installed_kw * math.sin(math.pi * (hour - self.DAY_START) / span)

    def forecast_24h(
        self,
        installed_kw: float,
        weather: str,
        start_hour: int = 0,
    ) -> SolarForecast:
        """基于装机容量 + 天气预测未来 24h 逐小时发电"""
        factor = self.weather_factor(weather)
        weather_label = weather if isinstance(weather, str) else weather.value

        points: List[ForecastPoint] = []
        for i in range(24):
            hour = (start_hour + i) % 24
            power = self._day_shape(hour, installed_kw) * factor
            points.append(ForecastPoint(hour=hour, power_kw=round(power, 3)))

        total = round(sum(p.power_kw for p in points), 3)
        peak = round(max((p.power_kw for p in points), default=0.0), 3)

        return SolarForecast(
            weather=weather_label,
            installed_kw=installed_kw,
            points=points,
            total_kwh=total,
            peak_power_kw=peak,
        )

    def forecast_with_history(
        self,
        history: List[float],
        weather: str,
    ) -> SolarForecast:
        """基于历史发电曲线(24点每小时kW)预测: 历史值 × 天气系数"""
        factor = self.weather_factor(weather)
        weather_label = weather if isinstance(weather, str) else weather.value
        installed_kw = max(history) if history else 0.0

        points: List[ForecastPoint] = []
        for h in range(24):
            base = history[h] if h < len(history) else 0.0
            points.append(ForecastPoint(hour=h, power_kw=round(base * factor, 3)))

        total = round(sum(p.power_kw for p in points), 3)
        peak = round(max((p.power_kw for p in points), default=0.0), 3)

        return SolarForecast(
            weather=weather_label,
            installed_kw=round(installed_kw, 3),
            points=points,
            total_kwh=total,
            peak_power_kw=peak,
        )
