"""能效分析端点（拆分自原 analytics.py）。"""
from typing import Any, Dict, List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, load_only

from app.api.deps import assert_device_team_access, assert_station_team_access, is_platform_admin
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User

from ._shared import (
    _ROUTER_DEPENDENCIES,
    EfficiencyAnalysisRequest,
    EfficiencyAnalysisResponse,
)


router = APIRouter(tags=["运维数据分析"], dependencies=_ROUTER_DEPENDENCIES)


@router.post("/efficiency-analysis", summary="能效分析")
def analyze_efficiency(request: EfficiencyAnalysisRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    分析设备或场站的能源使用效率
    提供优化建议和预计节省
    """
    # team scoping（任务卡 b640bdd9）：非 admin 仅可分析本 team 站点/设备，任一越权 → 404；
    # admin 显式豁免（保留原可跨站/设备分析语义）。
    if not is_platform_admin(user):
        if request.station_id:
            assert_station_team_access(db, request.station_id, user)
        if request.device_ids:
            for did in request.device_ids:
                assert_device_team_access(db, did, user)
    # 获取设备列表
    if request.device_ids:
        devices = db.query(Device).filter(Device.id.in_(request.device_ids)).all()
    elif request.station_id:
        devices = db.query(Device).filter(Device.station_id == request.station_id).all()
    else:
        raise HTTPException(status_code=400, detail="必须提供device_ids或station_id")

    if not devices:
        raise HTTPException(status_code=404, detail="未找到设备")

    results = []
    total_energy = 0.0

    # 批量加载所有设备的遥测数据，避免逐设备 N+1 查询 Telemetry 大表
    # 卡 7c1c396d 同族对齐（卡 27eb37e6 补漏）：load_only 列裁剪，仅加载能耗计算与
    # 各 _calculate_*_efficiency 实读的列，避免全列 ORM 实体物化
    device_ids = [d.id for d in devices]
    all_telemetry = (
        db.query(Telemetry)
        .options(
            load_only(
                Telemetry.id,
                Telemetry.device_id,
                Telemetry.timestamp,
                Telemetry.grid_power_total,
                Telemetry.inv_power_a,
                Telemetry.charger_power,
                Telemetry.battery_soc,
                Telemetry.grid_power_factor,
                Telemetry.battery_temperature,
            )
        )
        .filter(
            Telemetry.device_id.in_(device_ids),
            Telemetry.timestamp >= request.start_date,
            Telemetry.timestamp <= request.end_date,
            Telemetry.grid_power_total.isnot(None),
        )
        .order_by(Telemetry.device_id, Telemetry.timestamp.asc())
        .all()
    )
    telemetry_by_device: Dict[int, List[Telemetry]] = {}
    for _t in all_telemetry:
        telemetry_by_device.setdefault(_t.device_id, []).append(_t)

    for device in devices:
        # 从批量加载的结果中按设备取遥测数据（组内已按 timestamp 升序）
        telemetry_data = telemetry_by_device.get(device.id, [])

        if not telemetry_data:
            continue

        # 计算总能耗 (kWh)
        # 假设功率数据为kW，时间间隔为1小时
        power_values = [t.grid_power_total for t in telemetry_data if t.grid_power_total is not None]
        avg_power = np.mean(power_values) if power_values else 0

        # 时间段长度（小时）
        hours = (request.end_date - request.start_date).total_seconds() / 3600
        energy_kwh = avg_power * hours

        # 计算效率评分
        efficiency_score = _calculate_device_efficiency(telemetry_data, device)

        total_energy += energy_kwh

        results.append({
            "device_id": device.id,
            "device_name": device.name,
            "device_type": device.device_type,
            "avg_power_kw": round(avg_power, 2),
            "energy_kwh": round(energy_kwh, 2),
            "efficiency_score": round(efficiency_score, 2),
            "efficiency_level": "high" if efficiency_score >= 80 else "medium" if efficiency_score >= 60 else "low"
        })

    # 总体效率评分
    avg_efficiency = np.mean([r["efficiency_score"] for r in results]) if results else 70.0

    # 生成优化建议
    suggestions = _generate_efficiency_suggestions(results, avg_efficiency)

    # 计算预计节省
    estimated_savings = _calculate_potential_savings(results, total_energy, avg_efficiency)

    return EfficiencyAnalysisResponse(
        period=f"{request.start_date.date()} 至 {request.end_date.date()}",
        total_devices=len(results),
        total_energy_kwh=round(total_energy, 2),
        efficiency_score=round(avg_efficiency, 2),
        breakdown_by_device=results,
        optimization_suggestions=suggestions,
        estimated_savings=estimated_savings
    )


def _calculate_device_efficiency(telemetry_data: List[Telemetry], device: Device) -> float:
    """计算单个设备效率评分"""
    # 根据设备类型使用不同的效率计算方法
    if device.device_type == "inverter":
        return _calculate_inverter_efficiency(telemetry_data)
    elif device.device_type == "charger":
        return _calculate_charger_efficiency(telemetry_data)
    elif device.device_type == "battery":
        return _calculate_battery_efficiency(telemetry_data)
    else:
        return _calculate_general_efficiency(telemetry_data)


def _calculate_inverter_efficiency(telemetry_data: List[Telemetry]) -> float:
    """计算逆变器效率"""
    # 逆变器效率 = 输出功率 / 输入功率
    input_power = []
    output_power = []

    for t in telemetry_data:
        if t.grid_power_total is not None and t.inv_power_a is not None:
            input_power.append(t.grid_power_total)
            output_power.append(t.inv_power_a)

    if not input_power or not output_power:
        return 85.0  # 默认效率

    avg_input = np.mean(input_power)
    avg_output = np.mean(output_power)

    if avg_input == 0:
        return 0.0

    efficiency = (avg_output / avg_input) * 100
    return min(100, max(0, efficiency))


def _calculate_charger_efficiency(telemetry_data: List[Telemetry]) -> float:
    """计算充电桩效率"""
    # 充电桩效率 = 充电功率 / 输入功率
    input_power = []
    charge_power = []

    for t in telemetry_data:
        if t.grid_power_total is not None and t.charger_power is not None:
            input_power.append(t.grid_power_total)
            charge_power.append(t.charger_power)

    if not input_power or not charge_power:
        return 88.0  # 默认效率

    avg_input = np.mean(input_power)
    avg_charge = np.mean(charge_power)

    if avg_input == 0:
        return 0.0

    efficiency = (avg_charge / avg_input) * 100
    return min(100, max(0, efficiency))


def _calculate_battery_efficiency(telemetry_data: List[Telemetry]) -> float:
    """计算电池效率"""
    # 电池效率基于SOC变化和充放电效率
    soc_values = [t.battery_soc for t in telemetry_data if t.battery_soc is not None]

    if len(soc_values) < 2:
        return 90.0  # 默认效率

    soc_changes = []
    for i in range(1, len(soc_values)):
        change = soc_values[i] - soc_values[i-1]
        if abs(change) > 0.1:  # 忽略微小变化
            soc_changes.append(change)

    if not soc_changes:
        return 90.0

    # 效率评分：SOC变化稳定为高效
    change_std = np.std(soc_changes)
    efficiency = max(0, 100 - change_std * 100)
    return efficiency


def _calculate_general_efficiency(telemetry_data: List[Telemetry]) -> float:
    """计算通用设备效率"""
    # 基于功率因数评分
    pf_values = [t.grid_power_factor for t in telemetry_data if t.grid_power_factor is not None]

    if not pf_values:
        return 80.0

    avg_pf = np.mean(pf_values)
    pf_score = min(100, max(0, abs(avg_pf) * 100))

    # 基于温度稳定性
    temp_values = [t.battery_temperature for t in telemetry_data if t.battery_temperature is not None]
    if temp_values:
        temp_std = np.std(temp_values)
        temp_score = max(0, 100 - temp_std * 5)
    else:
        temp_score = 80.0

    return (pf_score * 0.6 + temp_score * 0.4)


def _generate_efficiency_suggestions(device_results: List[Dict], avg_efficiency: float) -> List[str]:
    """生成能效优化建议"""
    suggestions = []

    if avg_efficiency < 70:
        suggestions.append("整体能效偏低，建议进行系统级优化")

    low_efficiency_devices = [d for d in device_results if d["efficiency_score"] < 60]
    if low_efficiency_devices:
        device_names = ", ".join([d["device_name"] for d in low_efficiency_devices[:3]])
        suggestions.append(f"设备 {device_names} 能效较低，建议重点检查")

    # 检查是否有充电桩效率问题
    chargers = [d for d in device_results if d.get("device_type") == "charger" and d["efficiency_score"] < 85]
    if chargers:
        suggestions.append("部分充电桩效率低于85%，建议检查充电模块和散热系统")

    # 检查逆变器效率
    inverters = [d for d in device_results if d.get("device_type") == "inverter" and d["efficiency_score"] < 90]
    if inverters:
        suggestions.append("部分逆变器效率低于90%，建议检查MPPT和滤波电路")

    if not suggestions:
        suggestions.append("当前能效良好，建议继续保持并定期监测")

    return suggestions


def _calculate_potential_savings(device_results: List[Dict], total_energy: float, avg_efficiency: float) -> Dict[str, float]:
    """计算潜在节能效益"""
    if avg_efficiency >= 85:
        # 高效系统，提升空间有限
        potential_improvement = 0.05  # 5%
    elif avg_efficiency >= 70:
        potential_improvement = 0.10  # 10%
    elif avg_efficiency >= 50:
        potential_improvement = 0.15  # 15%
    else:
        potential_improvement = 0.20  # 20%

    # 假设电费0.8元/kWh
    electricity_price = 0.8  # 元/kWh

    current_cost = total_energy * electricity_price
    potential_savings_kwh = total_energy * potential_improvement
    potential_cost_savings = potential_savings_kwh * electricity_price

    return {
        "current_cost_yuan": round(current_cost, 2),
        "potential_savings_kwh": round(potential_savings_kwh, 2),
        "potential_cost_savings_yuan": round(potential_cost_savings, 2),
        "efficiency_improvement_percent": round(potential_improvement * 100, 1)
    }
