"""设备健康度评分端点（拆分自原 analytics.py）。"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, load_only

from app.api.deps import assert_device_team_access
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User

from ._shared import (
    _ROUTER_DEPENDENCIES,
    HealthScoreRequest,
    HealthScoreResponse,
)


router = APIRouter(tags=["运维数据分析"], dependencies=_ROUTER_DEPENDENCIES)

logger = logging.getLogger(__name__)


@router.post("/health-score", summary="设备健康度评分")
def calculate_health_score(request: HealthScoreRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    计算设备综合健康度评分
    基于多个维度：电池健康、温度稳定性、功率效率、告警频率等
    """
    # team scoping（任务卡 b640bdd9）：非 admin 仅可评分本 team 设备，越权 → 404。
    assert_device_team_access(db, request.device_id, user)
    device = db.query(Device).filter(Device.id == request.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"设备 {request.device_id} 不存在")

    # 获取历史数据
    # 卡 7c1c396d: 读放大降载 —— 90 天窗口分钟级遥测可达数万行:
    # 1) 空集判定下推 SQL (count), 无遥测时不再物化任何行;
    # 2) 有数据时物化改为 load_only 列裁剪, 仅加载各评分函数实读的 6 列
    #    (battery_soc/battery_soh/battery_temperature/grid_power_factor/timestamp/id),
    #    避免全列 ORM 实体物化。
    cutoff = datetime.now(timezone.utc) - timedelta(days=request.days)
    telemetry_exists = db.query(func.count(Telemetry.id)).filter(
        Telemetry.device_id == request.device_id,
        Telemetry.timestamp >= cutoff
    ).scalar()
    if not telemetry_exists:
        raise HTTPException(status_code=404, detail="该设备没有遥测数据")

    telemetry_data = db.query(Telemetry).options(
        load_only(
            Telemetry.id,
            Telemetry.timestamp,
            Telemetry.battery_soc,
            Telemetry.battery_soh,
            Telemetry.battery_temperature,
            Telemetry.grid_power_factor,
        )
    ).filter(
        Telemetry.device_id == request.device_id,
        Telemetry.timestamp >= cutoff
    ).order_by(Telemetry.timestamp.desc()).all()

    alarm_data = db.query(Alarm).filter(
        Alarm.device_id == request.device_id,
        Alarm.created_at >= cutoff,
        Alarm.status != 'resolved'
    ).all()

    # 计算各项评分 → 加权汇总 → 风险分级: 含 numpy 统计与算术, 数据异常(NaN/inf/空)
    # 会抛 ValueError/ArithmeticError, 兜底为 500 而非裸异常泄露 (卡 f3e5633d)
    try:
        # 计算各项评分
        scores = {
            "battery_health": _calculate_battery_health_score(telemetry_data),
            "temperature_stability": _calculate_temperature_score(telemetry_data),
            "power_efficiency": _calculate_power_efficiency_score(telemetry_data),
            "alarm_frequency": _calculate_alarm_score(alarm_data, request.days),
            "operational_consistency": _calculate_consistency_score(telemetry_data)
        }

        # 加权计算总分
        weights = {
            "battery_health": 0.35,
            "temperature_stability": 0.20,
            "power_efficiency": 0.20,
            "alarm_frequency": 0.15,
            "operational_consistency": 0.10
        }

        overall_score = sum(scores[key] * weights[key] for key in scores.keys())
    except (ValueError, ArithmeticError, TypeError) as e:
        logger.exception("健康度评分计算失败 device_id=%s", request.device_id)
        raise HTTPException(status_code=500, detail="健康度评分计算失败")

    # 确定风险等级
    if overall_score >= 80:
        risk_level = "low"
        trend = "stable"
    elif overall_score >= 60:
        risk_level = "medium"
        trend = "stable"
    elif overall_score >= 40:
        risk_level = "high"
        trend = "degrading"
    else:
        risk_level = "critical"
        trend = "degrading"

    # 识别关键问题
    key_issues = []
    if scores["battery_health"] < 60:
        key_issues.append("电池健康度偏低")
    if scores["temperature_stability"] < 70:
        key_issues.append("温度波动较大")
    if scores["alarm_frequency"] < 50:
        key_issues.append("告警频率较高")

    # 生成建议
    recommendations = []
    if overall_score < 70:
        recommendations.append("建议进行预防性维护检查")
    if scores["battery_health"] < 70:
        recommendations.append("建议检查电池状态和充电策略")
    if len(alarm_data) > 5:
        recommendations.append("建议分析高频告警原因")

    return HealthScoreResponse(
        device_id=device.id,
        device_name=device.name,
        overall_score=round(overall_score, 2),
        score_breakdown={k: round(v, 2) for k, v in scores.items()},
        risk_level=risk_level,
        trend=trend,
        key_issues=key_issues,
        recommendations=recommendations
    )


def _calculate_battery_health_score(telemetry_data: List[Telemetry]) -> float:
    """计算电池健康度评分"""
    soc_values = [t.battery_soc for t in telemetry_data if t.battery_soc is not None]
    soh_values = [t.battery_soh for t in telemetry_data if t.battery_soh is not None]

    if not soc_values or not soh_values:
        return 50.0  # 默认中等分数

    avg_soc = np.mean(soc_values)
    avg_soh = np.mean(soh_values)

    # SOC评分 (0-100)
    soc_score = min(100, max(0, avg_soc * 0.8))  # SOC在20-100%为佳

    # SOH评分 (0-100)
    soh_score = min(100, max(0, avg_soh))

    # 综合评分
    return (soc_score * 0.4 + soh_score * 0.6)


def _calculate_temperature_score(telemetry_data: List[Telemetry]) -> float:
    """计算温度稳定性评分"""
    temp_values = [t.battery_temperature for t in telemetry_data if t.battery_temperature is not None]

    if not temp_values or len(temp_values) < 2:
        return 70.0  # 默认分数

    temps = np.array(temp_values)

    # 理想温度范围 15-35°C
    ideal_min, ideal_max = 15, 35

    # 温度稳定性 (方差越小越好)
    temp_std = np.std(temps)
    stability_score = max(0, 100 - temp_std * 10)  # 每1°C标准差扣10分

    # 温度范围评分
    in_range = np.sum((temps >= ideal_min) & (temps <= ideal_max))
    range_score = (in_range / len(temps)) * 100

    return (stability_score * 0.6 + range_score * 0.4)


def _calculate_power_efficiency_score(telemetry_data: List[Telemetry]) -> float:
    """计算功率效率评分"""
    # 计算功率因数稳定性
    pf_values = [t.grid_power_factor for t in telemetry_data if t.grid_power_factor is not None]

    if not pf_values:
        return 75.0  # 默认分数

    pf_array = np.array(pf_values)

    # 功率因数接近1为佳
    pf_avg = np.mean(pf_array)
    pf_score = min(100, max(0, abs(pf_avg) * 100))  # 绝对值接近1得分高

    # 功率因数稳定性
    pf_std = np.std(pf_array)
    stability_score = max(0, 100 - pf_std * 50)  # 稳定性越高得分越高

    return (pf_score * 0.7 + stability_score * 0.3)


def _calculate_alarm_score(alarm_data: List[Alarm], days: int) -> float:
    """计算告警频率评分"""
    if not alarm_data:
        return 100.0  # 无告警得满分

    # 按告警等级(level)加权 —— key 与 AlarmLevel 枚举 value 对齐
    # (AlarmLevel: info/warning/critical/fatal)，保证每个等级命中正确权重；
    # 未命中(如未来新增等级)兜底权重 1。AlarmLevel 为 str enum，
    # 枚举实例作 dict key 查询时按其字符串 value 命中。
    severity_weights = {
        "fatal": 6,       # 致命 - 最严重
        "critical": 5,    # 严重
        "warning": 3,     # 警告
        "info": 1,        # 提示 - 最轻
    }

    weighted_alarms = sum(severity_weights.get(alarm.level, 1) for alarm in alarm_data)

    # 每天平均告警权重
    daily_weight = weighted_alarms / days

    # 评分：每天权重小于1得100分，大于5得0分，线性插值
    if daily_weight <= 1:
        return 100
    elif daily_weight >= 5:
        return 0
    else:
        return 100 - (daily_weight - 1) * 25  # 线性递减


def _calculate_consistency_score(telemetry_data: List[Telemetry]) -> float:
    """计算运行一致性评分"""
    if len(telemetry_data) < 2:
        return 70.0

    # 检查数据连续性
    timestamps = [t.timestamp for t in telemetry_data]
    timestamps.sort()

    # 计算时间间隔
    intervals = []
    for i in range(1, len(timestamps)):
        interval = (timestamps[i] - timestamps[i-1]).total_seconds()
        intervals.append(interval)

    if not intervals:
        return 70.0

    # 理想间隔：1小时 (3600秒)
    ideal_interval = 3600
    interval_scores = []

    for interval in intervals:
        # 间隔在0.5-2小时之间为佳
        if interval >= 1800 and interval <= 7200:  # 0.5-2小时
            score = 100
        else:
            # 偏离越大得分越低
            deviation = abs(interval - ideal_interval) / ideal_interval
            score = max(0, 100 - deviation * 100)
        interval_scores.append(score)

    return np.mean(interval_scores) if interval_scores else 70.0
