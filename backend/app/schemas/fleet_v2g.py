"""
V2G API请求/响应模型 - Phase44 V2G调度

包含:
- FleetV2GPlanRequest：创建计划的请求体
- FleetV2GPlanResponse：创建计划的响应体
- FleetV2GRevenueRequest: 记录收益的请求体
- FleetV2GRevenueResponse：收益统计的响应体
"""
from datetime import date, datetime
from pydantic import BaseModel, Field


class FleetV2GPlanRequest(BaseModel):
    """V2G计划创建请求"""
    enterprise_id: int = Field(..., gt=0, description="企业ID")
    vehicle_id: int = Field(..., gt=0, description="车辆ID")
    plan_date: date = Field(..., description="计划日期")
    planned_charge_start: datetime = Field(..., description="计划充电开始时间")
    planned_charge_end: datetime = Field(..., description="计划充电结束时间")
    planned_discharge_start: datetime = Field(..., description="计划放电开始时间")
    planned_discharge_end: datetime = Field(..., description="计划放电结束时间")
    target_soc_min: float = Field(..., gt=0, lt=100, description="目标最小SOC（%）")
    target_soc_max: float = Field(..., gt=0, lt=100, description="目标最大SOC（%）")


class FleetV2GPlanResponse(BaseModel):
    """V2G计划创建响应"""
    id: int
    enterprise_id: int
    vehicle_id: int
    plan_date: date
    planned_charge_start: datetime
    planned_charge_end: datetime
    planned_discharge_start: datetime
    planned_discharge_end: datetime
    target_soc_min: float
    target_soc_max: float
    status: str  # "scheduled" or "completed"


class FleetV2GRevenueRequest(BaseModel):
    """V2G收益记录请求"""
    enterprise_id: int = Field(..., gt=0, description="企业ID")
    vehicle_id: int = Field(..., gt=0, description="车辆ID")
    record_date: date = Field(..., description="记录日期")
    discharge_energy_kwh: float = Field(..., ge=0, description="放电电量(kWh)")
    discharge_revenue: float = Field(..., ge=0, description="放电收益(元)")
    grid_response_count: int = Field(default=0, ge=0, description="电网响应次数")
    peak_shaving_kwh: float = Field(default=0, ge=0, description="削峰电量(kWh)")
    valley_filling_kwh: float = Field(default=0, ge=0, description="填谷电量(kWh)")
    total_revenue: float = Field(..., ge=0, description="总收益(元)")


class FleetV2GRevenueResponse(BaseModel):
    """V2G收益记录响应"""
    id: int
    enterprise_id: int
    vehicle_id: int
    record_date: date
    discharge_energy_kwh: float
    discharge_revenue: float
    grid_response_count: int
    peak_shaving_kwh: float
    valley_filling_kwh: float
    total_revenue: float