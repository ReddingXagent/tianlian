"""异常检测端点（拆分自原 analytics.py）。"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, load_only

from app.api.deps import assert_device_team_access
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User

from ._shared import (
    _ROUTER_DEPENDENCIES,
    AnomalyDetectionRequest,
    AnomalyDetectionResponse,
    logger,
)


router = APIRouter(tags=["运维数据分析"], dependencies=_ROUTER_DEPENDENCIES)


@router.post("/anomaly-detection", summary="异常检测")
def detect_anomalies(request: AnomalyDetectionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    检测设备异常行为
    使用统计方法和机器学习算法识别异常模式
    """
    # team scoping（任务卡 b640bdd9）：非 admin 仅可检测本 team 设备，越权 → 404。
    assert_device_team_access(db, request.device_id, user)
    try:
        device = db.query(Device).filter(Device.id == request.device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail=f"设备 {request.device_id} 不存在")

        # 获取最近数据
        # 卡 7c1c396d: 逐点异常检测需保留序列物化（差分/最近5点等序列语义），
        # 但 load_only 列裁剪到五个 _detect_* 函数实读的 12 列，
        # 避免全列 ORM 实体物化（hours 上限已由 schema 夹紧到 168）。
        cutoff = datetime.now(timezone.utc) - timedelta(hours=request.hours)
        telemetry_data = db.query(Telemetry).options(
            load_only(
                Telemetry.id,
                Telemetry.timestamp,
                Telemetry.battery_temperature,
                Telemetry.battery_soc,
                Telemetry.battery_current,
                Telemetry.grid_voltage_a,
                Telemetry.grid_voltage_b,
                Telemetry.grid_voltage_c,
                Telemetry.grid_current_a,
                Telemetry.grid_current_b,
                Telemetry.grid_current_c,
                Telemetry.grid_power_total,
            )
        ).filter(
            Telemetry.device_id == request.device_id,
            Telemetry.timestamp >= cutoff
        ).order_by(Telemetry.timestamp.asc()).all()

        if not telemetry_data:
            raise HTTPException(status_code=404, detail="该设备没有遥测数据")

        # 检测异常
        anomalies = []
        anomaly_score = 0.0

        # 1. 检测温度异常
        temp_anomalies = _detect_temperature_anomalies(telemetry_data)
        anomalies.extend(temp_anomalies)

        # 2. 检测电压异常
        voltage_anomalies = _detect_voltage_anomalies(telemetry_data)
        anomalies.extend(voltage_anomalies)

        # 3. 检测电流异常
        current_anomalies = _detect_current_anomalies(telemetry_data)
        anomalies.extend(current_anomalies)

        # 4. 检测功率异常
        power_anomalies = _detect_power_anomalies(telemetry_data)
        anomalies.extend(power_anomalies)

        # 5. 检测SOC异常
        soc_anomalies = _detect_soc_anomalies(telemetry_data)
        anomalies.extend(soc_anomalies)

        # 计算总体异常分数
        if anomalies:
            severity_scores = {"low": 0.3, "medium": 0.6, "high": 0.9, "critical": 1.0}
            total_score = sum(severity_scores.get(a.get("severity", "low"), 0.3) for a in anomalies)
            anomaly_score = min(1.0, total_score / len(anomalies))

        # 确定总体严重程度
        if anomaly_score >= 0.8:
            severity = "critical"
        elif anomaly_score >= 0.6:
            severity = "high"
        elif anomaly_score >= 0.3:
            severity = "medium"
        else:
            severity = "low"

        # 分析根本原因
        root_causes = _analyze_root_causes(anomalies)

        # 生成建议措施
        suggested_actions = _generate_anomaly_actions(anomalies, severity)

        return AnomalyDetectionResponse(
            device_id=device.id,
            device_name=device.name,
            anomaly_score=round(anomaly_score, 3),
            detected_anomalies=anomalies,
            severity=severity,
            root_causes=root_causes,
            suggested_actions=suggested_actions
        )
    except HTTPException:
        # 业务异常(404 设备不存在/无遥测数据等)穿透，交全局 HTTPException handler 统一格式
        raise
    except Exception:
        # 兜底：numpy/统计等未预期异常 → 受控 500，不泄露详情；
        # 记 device_id/hours 业务上下文日志便于排查（app.main 全局 handler 不带此上下文）。
        logger.exception("异常检测失败 device_id=%s hours=%s", request.device_id, request.hours)
        raise HTTPException(status_code=500, detail="内部错误")


def _detect_temperature_anomalies(telemetry_data: List[Telemetry]) -> List[Dict]:
    """检测温度异常"""
    anomalies = []
    temp_values = [t.battery_temperature for t in telemetry_data if t.battery_temperature is not None]

    if len(temp_values) < 5:
        return anomalies

    temps = np.array(temp_values)

    # 统计异常检测
    mean_temp = np.mean(temps)
    std_temp = np.std(temps)

    # 温度过高检测
    high_threshold = mean_temp + 3 * std_temp
    high_temps = temps[temps > high_threshold]

    if len(high_temps) > 0:
        anomalies.append({
            "type": "temperature_high",
            "severity": "high" if max(high_temps) > 50 else "medium",
            "description": f"检测到{len(high_temps)}次温度过高事件，最高温度{max(high_temps):.1f}°C",
            "metric": "battery_temperature",
            "value": float(max(high_temps)),
            "threshold": float(high_threshold)
        })

    # 温度过低检测
    low_threshold = mean_temp - 3 * std_temp
    low_temps = temps[temps < low_threshold]

    if len(low_temps) > 0:
        anomalies.append({
            "type": "temperature_low",
            "severity": "medium" if min(low_temps) < 0 else "low",
            "description": f"检测到{len(low_temps)}次温度过低事件，最低温度{min(low_temps):.1f}°C",
            "metric": "battery_temperature",
            "value": float(min(low_temps)),
            "threshold": float(low_threshold)
        })

    # 温度快速变化检测
    if len(temps) >= 10:
        temp_changes = np.abs(np.diff(temps))
        rapid_change_idx = np.where(temp_changes > 5)[0]  # 5°C/采样间隔
        if len(rapid_change_idx) > 0:
            anomalies.append({
                "type": "temperature_rapid_change",
                "severity": "medium",
                "description": f"检测到{len(rapid_change_idx)}次温度快速变化事件",
                "metric": "battery_temperature_change",
                "value": float(np.max(temp_changes)),
                "threshold": 5.0
            })

    return anomalies


def _detect_voltage_anomalies(telemetry_data: List[Telemetry]) -> List[Dict]:
    """检测电压异常"""
    anomalies = []

    # 检查三相电压平衡
    voltages = []
    voltage_labels = []

    for t in telemetry_data:
        if t.grid_voltage_a is not None:
            voltages.append(t.grid_voltage_a)
            voltage_labels.append("A相")
        if t.grid_voltage_b is not None:
            voltages.append(t.grid_voltage_b)
            voltage_labels.append("B相")
        if t.grid_voltage_c is not None:
            voltages.append(t.grid_voltage_c)
            voltage_labels.append("C相")

    if len(voltages) < 3:
        return anomalies

    volt_array = np.array(voltages)

    # 电压过高/过低检测
    mean_volt = np.mean(volt_array)

    # 标准电压范围：210V-250V
    if mean_volt > 250:
        anomalies.append({
            "type": "voltage_high",
            "severity": "high",
            "description": f"平均电压过高：{mean_volt:.1f}V",
            "metric": "grid_voltage",
            "value": float(mean_volt),
            "threshold": 250.0
        })
    elif mean_volt < 210:
        anomalies.append({
            "type": "voltage_low",
            "severity": "high",
            "description": f"平均电压过低：{mean_volt:.1f}V",
            "metric": "grid_voltage",
            "value": float(mean_volt),
            "threshold": 210.0
        })

    # 三相不平衡检测
    if len([t for t in telemetry_data if t.grid_voltage_a is not None and t.grid_voltage_b is not None and t.grid_voltage_c is not None]) >= 5:
        imbalance_scores = []
        for t in telemetry_data[-5:]:  # 最近5个点
            if t.grid_voltage_a and t.grid_voltage_b and t.grid_voltage_c:
                max_v = max(t.grid_voltage_a, t.grid_voltage_b, t.grid_voltage_c)
                min_v = min(t.grid_voltage_a, t.grid_voltage_b, t.grid_voltage_c)
                imbalance = (max_v - min_v) / max_v * 100
                imbalance_scores.append(imbalance)

        if imbalance_scores and max(imbalance_scores) > 5:  # 5%不平衡度阈值
            anomalies.append({
                "type": "voltage_imbalance",
                "severity": "medium",
                "description": f"三相电压不平衡，最大不平衡度{max(imbalance_scores):.1f}%",
                "metric": "voltage_imbalance",
                "value": float(max(imbalance_scores)),
                "threshold": 5.0
            })

    return anomalies


def _detect_current_anomalies(telemetry_data: List[Telemetry]) -> List[Dict]:
    """检测电流异常"""
    anomalies = []

    currents = []
    for t in telemetry_data:
        if t.grid_current_a is not None:
            currents.append(t.grid_current_a)
        if t.grid_current_b is not None:
            currents.append(t.grid_current_b)
        if t.grid_current_c is not None:
            currents.append(t.grid_current_c)
        if t.battery_current is not None:
            currents.append(t.battery_current)

    if len(currents) < 3:
        return anomalies

    curr_array = np.array(currents)

    # 电流过高检测
    high_currents = curr_array[curr_array > 100]  # 100A阈值
    if len(high_currents) > 0:
        anomalies.append({
            "type": "current_high",
            "severity": "critical" if max(high_currents) > 150 else "high",
            "description": f"检测到{len(high_currents)}次电流过高事件，最高电流{max(high_currents):.1f}A",
            "metric": "current",
            "value": float(max(high_currents)),
            "threshold": 100.0
        })

    # 电流突增检测
    if len(curr_array) >= 10:
        current_changes = np.abs(np.diff(curr_array))
        surge_idx = np.where(current_changes > 30)[0]  # 30A突增
        if len(surge_idx) > 0:
            anomalies.append({
                "type": "current_surge",
                "severity": "high",
                "description": f"检测到{len(surge_idx)}次电流突增事件",
                "metric": "current_change",
                "value": float(np.max(current_changes)),
                "threshold": 30.0
            })

    return anomalies


def _detect_power_anomalies(telemetry_data: List[Telemetry]) -> List[Dict]:
    """检测功率异常"""
    anomalies = []

    powers = [t.grid_power_total for t in telemetry_data if t.grid_power_total is not None]
    if len(powers) < 5:
        return anomalies

    power_array = np.array(powers)

    # 功率过高检测
    high_powers = power_array[power_array > 100]  # 100kW阈值
    if len(high_powers) > 0:
        anomalies.append({
            "type": "power_high",
            "severity": "high",
            "description": f"检测到{len(high_powers)}次功率过高事件，最高功率{max(high_powers):.1f}kW",
            "metric": "grid_power_total",
            "value": float(max(high_powers)),
            "threshold": 100.0
        })

    # 功率波动检测
    if len(power_array) >= 10:
        power_std = np.std(power_array)
        if power_std > 20:  # 20kW标准差阈值
            anomalies.append({
                "type": "power_fluctuation",
                "severity": "medium",
                "description": f"功率波动较大，标准差{power_std:.1f}kW",
                "metric": "power_std",
                "value": float(power_std),
                "threshold": 20.0
            })

    return anomalies


def _detect_soc_anomalies(telemetry_data: List[Telemetry]) -> List[Dict]:
    """检测SOC异常"""
    anomalies = []

    soc_values = [t.battery_soc for t in telemetry_data if t.battery_soc is not None]
    if len(soc_values) < 5:
        return anomalies

    soc_array = np.array(soc_values)

    # SOC过低检测
    low_soc = soc_array[soc_array < 20]  # 20%阈值
    if len(low_soc) > 0:
        anomalies.append({
            "type": "soc_low",
            "severity": "critical" if min(low_soc) < 10 else "high",
            "description": f"检测到{len(low_soc)}次SOC过低事件，最低SOC{min(low_soc):.1f}%",
            "metric": "battery_soc",
            "value": float(min(low_soc)),
            "threshold": 20.0
        })

    # SOC快速下降检测
    if len(soc_array) >= 10:
        soc_changes = np.diff(soc_array)
        rapid_drop_idx = np.where(soc_changes < -5)[0]  # 5%/采样间隔下降
        if len(rapid_drop_idx) > 0:
            anomalies.append({
                "type": "soc_rapid_drop",
                "severity": "high",
                "description": f"检测到{len(rapid_drop_idx)}次SOC快速下降事件",
                "metric": "soc_change",
                "value": float(np.min(soc_changes)),
                "threshold": -5.0
            })

    return anomalies


def _generate_anomaly_actions(anomalies: List[Dict], severity: str) -> List[str]:
    """根据异常类型和严重程度生成建议措施"""
    actions = []
    anomaly_types = {a["type"] for a in anomalies}

    if severity in ("critical", "high"):
        actions.append("立即安排技术人员现场排查")
    elif severity in ("medium",):
        actions.append("在24小时内安排技术人员检查")
    else:
        actions.append("安排常规巡检检查")

    if "temperature_high" in anomaly_types or "temperature_rising" in anomaly_types:
        actions.append("检查设备散热风扇和通风环境")
    if "current_overload" in anomaly_types:
        actions.append("检查负载分配，必要时进行减载操作")
    if "voltage_drop" in anomaly_types or "voltage_over" in anomaly_types:
        actions.append("检查电源线路接触和变压器工作状态")
    if "insulation_degradation" in anomaly_types:
        actions.append("进行绝缘测试，必要时更换绝缘部件")

    return actions if actions else ["安排技术人员进行全面检查"]


def _analyze_root_causes(anomalies: List[Dict]) -> List[str]:
    """分析异常的根本原因"""
    root_causes = []

    anomaly_types = [a["type"] for a in anomalies]

    # 温度相关异常
    temp_types = ["temperature_high", "temperature_rising", "temperature_deviation"]
    if any(t in anomaly_types for t in temp_types):
        root_causes.append("温度异常，可能存在散热不良或负载过高问题")

    # 电流/电压异常
    current_types = ["current_overload", "current_unbalance", "voltage_drop", "voltage_over"]
    if any(t in anomaly_types for t in current_types):
        root_causes.append("电气参数异常，检查线路连接与负载分配")

    # 绝缘相关
    if "insulation_degradation" in anomaly_types:
        root_causes.append("绝缘性能下降，建议安排检修")

    return root_causes
