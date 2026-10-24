"""运维数据分析与AI预测 API 共享定义（拆分自原 analytics.py）。

存放跨子模块复用的模块级对象：logger、router 级鉴权依赖、各端点的 Pydantic
请求/响应 schema。三类分析端点（健康度评分 / 能效分析 / 异常检测）拆分到同包
各子模块，均从本模块导入所需 schema。
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Depends
from pydantic import BaseModel, Field, model_validator

from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission


logger = logging.getLogger("app.api.v1.analytics")


# 运维数据分析 router 级鉴权依赖（原 analytics.py 顶层 router 的 dependencies）
_ROUTER_DEPENDENCIES = [
    Depends(get_current_user),
    Depends(require_write_permission("analytics:manage")),
]


# ============ Pydantic Schemas ============

class HealthScoreRequest(BaseModel):
    device_id: int
    days: int = Field(7, ge=1, le=90, description="分析多少天的数据")

class HealthScoreResponse(BaseModel):
    device_id: int
    device_name: str
    overall_score: float  # 0-100分
    score_breakdown: Dict[str, float]  # 各项评分
    risk_level: str  # low/medium/high/critical
    trend: str  # improving/stable/degrading
    key_issues: List[str]
    recommendations: List[str]

class EfficiencyAnalysisRequest(BaseModel):
    device_ids: Optional[List[int]] = None
    station_id: Optional[int] = None
    start_date: datetime
    end_date: datetime

    # 卡 27eb37e6: 日期无界读放大加固 —— 该端点批量一次性物化整批设备的遥测大表，
    # 无跨度上限时认证用户传 2000-2099 可全量拉取 99 年遥测进内存。
    # 跨度上限取 366 天，与 get_energy_trend（卡 05ccb577）对齐。
    @model_validator(mode="after")
    def _validate_date_span(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date 必须晚于或等于 start_date")
        if self.end_date - self.start_date > timedelta(days=366):
            raise ValueError("分析时间跨度不能超过366天")
        return self

class EfficiencyAnalysisResponse(BaseModel):
    period: str
    total_devices: int
    total_energy_kwh: float
    efficiency_score: float  # 0-100
    breakdown_by_device: List[Dict[str, Any]]
    optimization_suggestions: List[str]
    estimated_savings: Dict[str, float]  # 预计节省

class AnomalyDetectionRequest(BaseModel):
    device_id: int
    # 卡 7c1c396d: 无界 hours(如 10^9)会让检测端点全量拉取设备历史遥测，夹紧到 7 天
    hours: int = Field(24, ge=1, le=168)  # 检测最近多少小时的数据

class AnomalyDetectionResponse(BaseModel):
    device_id: int
    device_name: str
    anomaly_score: float  # 0-1
    detected_anomalies: List[Dict[str, Any]]
    severity: str  # low/medium/high/critical
    root_causes: List[str]
    suggested_actions: List[str]

class MaintenanceOptimizationRequest(BaseModel):
    station_id: int
    budget_constraint: Optional[float] = None  # 预算限制
    priority_devices: Optional[List[int]] = None  # 优先设备

class MaintenanceOptimizationResponse(BaseModel):
    station_id: int
    station_name: str
    optimal_schedule: List[Dict[str, Any]]
    total_cost: float
    estimated_uptime_improvement: float  # 预计可用率提升百分比
    risk_reduction: float  # 风险降低百分比
    spare_parts_needed: List[Dict[str, Any]]
