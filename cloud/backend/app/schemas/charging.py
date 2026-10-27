"""
充电策略引擎 — Pydantic API 模型

用于 app/api/v1/charging_strategy.py 的请求/响应序列化。
服务层(app/services/charging)使用 dataclass;本文件负责 API 边界的序列化。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── 策略元信息 ───

class StrategyInfo(BaseModel):
    """单个充电模式描述"""
    mode: str = Field(..., description="模式标识: manual/timed/solar/price/balanced")
    name: str = Field(..., description="中文名称")
    description: str = Field("", description="模式说明")
    priority: int = Field(..., description="调度优先级(1最高)")


# ─── 策略评估请求/响应 ───

class ChargingContextIn(BaseModel):
    """充电决策输入(POST body)"""
    station_id: str = Field(..., description="站点ID")
    charger_id: str = Field(..., description="充电桩ID")
    rated_power_kw: float = Field(..., gt=0, description="充电桩额定功率(kW)")
    demand_power_kw: float = Field(0, ge=0, description="车辆充电需求功率(kW)")
    current_soc: Optional[float] = Field(None, ge=0, le=1, description="车辆电池SOC")
    target_soc: Optional[float] = Field(None, ge=0, le=1, description="目标SOC")
    pv_output_kw: float = Field(0, ge=0, description="当前光伏出力(kW)")
    battery_soc: Optional[float] = Field(None, ge=0, le=1, description="储能SOC")
    battery_capacity_kwh: float = Field(0, ge=0, description="储能容量(kWh)")
    battery_available_kw: float = Field(0, ge=0, description="储能可放电功率(kW)")
    battery_temp_c: Optional[float] = Field(None, description="储能温度(℃)")
    grid_price: Optional[float] = Field(None, ge=0, description="实时电价(元/kWh)")
    grid_power_limit_kw: Optional[float] = Field(None, ge=0, description="电网取电上限(kW)")
    in_valley_period: Optional[bool] = Field(None, description="当前是否低谷时段")
    manual_power_kw: Optional[float] = Field(None, ge=0, description="手动指定功率(kW)")


class ChargingDecisionOut(BaseModel):
    """充电决策输出"""
    mode: str
    target_power_kw: float = Field(0, description="目标充电总功率(kW)")
    pv_power_kw: float = Field(0, description="来自光伏(kW)")
    battery_power_kw: float = Field(0, description="来自储能放电(kW)")
    grid_power_kw: float = Field(0, description="来自电网(kW)")
    source: str = Field("grid", description="主能量来源: pv/battery/grid/mixed/none")
    curtailed: bool = Field(False, description="是否相对需求降了功率")
    reason: str = Field("", description="决策原因")


# ─── 模式切换 ───

class StrategySwitchRequest(BaseModel):
    """切换当前充电模式"""
    mode: str = Field(..., description="目标模式: manual/timed/solar/price/balanced")
    station_id: Optional[str] = Field(None, description="站点ID(可选,按站切换)")


class StrategySwitchResponse(BaseModel):
    """切换结果"""
    mode: str
    station_id: Optional[str] = None
    switched_at: str
    previous_mode: Optional[str] = None


class CurrentStrategyOut(BaseModel):
    """当前激活模式"""
    mode: str
    station_id: Optional[str] = None
    switched_at: Optional[str] = None


# ─── 光伏预测 ───

class SolarForecastPoint(BaseModel):
    """逐小时光伏预测点"""
    hour: int = Field(..., ge=0, le=23, description="小时(0-23)")
    power_kw: float = Field(0, ge=0, description="预测功率(kW)")


class SolarForecastOut(BaseModel):
    """未来24h光伏预测"""
    weather: str = Field(..., description="天气: sunny/cloudy/rainy")
    installed_kw: float = Field(..., description="光伏装机容量(kW)")
    points: List[SolarForecastPoint] = Field(default_factory=list)
    total_kwh: float = Field(0, ge=0, description="未来24h总发电量(kWh)")
    peak_power_kw: float = Field(0, ge=0, description="预测峰值功率(kW)")


# ─── 储能状态 ───

class StorageStatusOut(BaseModel):
    """储能调度状态"""
    soc: float = Field(..., ge=0, le=1, description="当前SOC")
    target_soc: float = Field(..., ge=0, le=1, description="目标SOC")
    action: str = Field(..., description="动作: charge/discharge/idle")
    power_kw: float = Field(0, description="功率(kW, 正=充电, 负=放电)")
    reason: str = Field("", description="决策原因")
    health_ok: bool = Field(True, description="电池健康状态是否允许调度")
    within_safe_range: bool = Field(True, description="SOC是否在安全区间(10%-90%)")
