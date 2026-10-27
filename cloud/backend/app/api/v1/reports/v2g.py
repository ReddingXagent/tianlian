"""V2G 运营分析报表端点（拆分自原 reports.py）。"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.device import Device, DeviceType
from app.models.device_efficiency_log import DeviceEfficiencyLog
from app.models.user import User
from app.models.v2g_dispatch import V2GDispatchLog

from ._shared import _ROUTER_DEPENDENCIES, _own_station_ids, _check_station_in_scope, _biz_day_key
from .export import _render_export


router = APIRouter(tags=["数据分析报表"], dependencies=_ROUTER_DEPENDENCIES)


@router.get("/v2g")
def report_v2g(
    days: int = Query(30, ge=1, le=90, description="统计周期(天)"),
    station_id: Optional[int] = Query(None, alias="station_id"),
    format: Optional[str] = Query(None, alias="format", description="导出格式: csv/xlsx/pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据分析 - V2G运营报表：充放电量趋势、效率分析、收益统计、调度响应"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    own = _own_station_ids(db, user)
    _check_station_in_scope(station_id, own, user)

    # 查询所有V2G设备（限本 team 站点 — 任务卡 b640bdd9）
    v2g_devices_query = db.query(Device).filter(Device.type == DeviceType.V2G_CHARGER)
    if own is not None:
        v2g_devices_query = v2g_devices_query.filter(Device.station_id.in_(own))
    if station_id:
        v2g_devices_query = v2g_devices_query.filter(Device.station_id == station_id)
    v2g_devices = v2g_devices_query.all()
    device_ids = [d.id for d in v2g_devices]

    # ── 充放电量统计 ──
    dispatch_logs = db.query(V2GDispatchLog).filter(
        V2GDispatchLog.device_id.in_(device_ids),
        V2GDispatchLog.start_at >= cutoff
    ).all()

    total_charge_kwh = sum(getattr(log, 'actual_energy_kwh', None) or 0 for log in dispatch_logs if log.dispatch_type == "charge")
    total_discharge_kwh = sum(getattr(log, 'actual_energy_kwh', None) or 0 for log in dispatch_logs if log.dispatch_type == "discharge")

    # ── 调度统计 ──
    total_dispatches = len(dispatch_logs)
    completed_dispatches = len([log for log in dispatch_logs if log.status == "completed"])
    failed_dispatches = len([log for log in dispatch_logs if log.status == "failed"])
    dispatch_success_rate = round(completed_dispatches / max(total_dispatches, 1) * 100, 1)

    # ── 充放电效率 (从效率日志获取) ──
    efficiency_logs = db.query(DeviceEfficiencyLog).filter(
        DeviceEfficiencyLog.device_id.in_(device_ids),
        DeviceEfficiencyLog.recorded_at >= cutoff,
        DeviceEfficiencyLog.metric_type.in_(["charge", "generation"])
    ).all()

    charge_efficiencies = [log.metric_value for log in efficiency_logs if log.metric_type == "charge"]
    discharge_efficiencies = [log.metric_value for log in efficiency_logs if log.metric_type == "generation"]

    avg_charge_efficiency = round(sum(charge_efficiencies) / len(charge_efficiencies), 1) if charge_efficiencies else 0.0
    avg_discharge_efficiency = round(sum(discharge_efficiencies) / len(discharge_efficiencies), 1) if discharge_efficiencies else 0.0

    # ── V2G设备详情 ──
    device_details = []
    for dev in v2g_devices:
        dev_logs = [log for log in dispatch_logs if log.device_id == dev.id]
        dev_charge = sum(getattr(log, 'actual_energy_kwh', None) or 0 for log in dev_logs if log.dispatch_type == "charge")
        dev_discharge = sum(getattr(log, 'actual_energy_kwh', None) or 0 for log in dev_logs if log.dispatch_type == "discharge")

        dev_charge_eff = [log.metric_value for log in efficiency_logs if log.device_id == dev.id and log.metric_type == "charge"]
        dev_discharge_eff = [log.metric_value for log in efficiency_logs if log.device_id == dev.id and log.metric_type == "generation"]

        device_details.append({
            "device_id": dev.id,
            "device_name": dev.name,
            "device_code": dev.code,
            "station_name": dev.station.name if dev.station else "",
            "total_charge_kwh": round(dev_charge, 2),
            "total_discharge_kwh": round(dev_discharge, 2),
            "charge_efficiency": round(sum(dev_charge_eff) / len(dev_charge_eff), 1) if dev_charge_eff else 0.0,
            "discharge_efficiency": round(sum(dev_discharge_eff) / len(dev_discharge_eff), 1) if dev_discharge_eff else 0.0,
            "dispatch_count": len(dev_logs),
            "dispatch_success_rate": round(len([l for l in dev_logs if l.status == "completed"]) / max(len(dev_logs), 1) * 100, 1),
        })

    # ── 收益估算 (假设放电电价 0.5元/kWh, 充电电价 0.3元/kWh) ──
    discharge_price = 0.5  # 元/kWh
    charge_price = 0.3     # 元/kWh
    estimated_revenue = round(total_discharge_kwh * discharge_price - total_charge_kwh * charge_price, 2)

    # ── 趋势：按天统计充放电量 ──
    daily_charge = defaultdict(float)
    daily_discharge = defaultdict(float)
    daily_dispatches = defaultdict(int)

    for log in dispatch_logs:
        day_key = _biz_day_key(log.start_at)
        if log.dispatch_type == "charge":
            daily_charge[day_key] += getattr(log, 'actual_energy_kwh', None) or 0
        elif log.dispatch_type == "discharge":
            daily_discharge[day_key] += getattr(log, 'actual_energy_kwh', None) or 0
        daily_dispatches[day_key] += 1

    v2g_trend = []
    for day in sorted(set(list(daily_charge.keys()) + list(daily_discharge.keys()))):
        v2g_trend.append({
            "date": day,
            "charge_kwh": round(daily_charge.get(day, 0), 2),
            "discharge_kwh": round(daily_discharge.get(day, 0), 2),
            "dispatch_count": daily_dispatches.get(day, 0),
        })

    # ── 电网调度响应统计 ──
    grid_dispatch_logs = [log for log in dispatch_logs if log.dispatch_type in ["charge", "discharge"]]
    grid_response_count = len(grid_dispatch_logs)

    if format:
        headers = ["设备名称", "站点", "充电量(kWh)", "放电量(kWh)", "充电效率(%)", "放电效率(%)", "调度次数", "调度成功率(%)"]
        data = []
        for d in device_details:
            data.append([
                d["device_name"], d["station_name"],
                str(d["total_charge_kwh"]), str(d["total_discharge_kwh"]),
                str(d["charge_efficiency"]), str(d["discharge_efficiency"]),
                str(d["dispatch_count"]), str(d["dispatch_success_rate"]),
            ])
        return _render_export(format, data, headers, "V2G运营报表", "v2g")

    return success_response({
        "period_days": days,
        "device_count": len(v2g_devices),
        "energy": {
            "total_charge_kwh": round(total_charge_kwh, 2),
            "total_discharge_kwh": round(total_discharge_kwh, 2),
            "net_energy_kwh": round(total_discharge_kwh - total_charge_kwh, 2),
        },
        "efficiency": {
            "avg_charge_efficiency": avg_charge_efficiency,
            "avg_discharge_efficiency": avg_discharge_efficiency,
            "avg_conversion_efficiency": round((avg_charge_efficiency * avg_discharge_efficiency) / 100, 1) if avg_charge_efficiency and avg_discharge_efficiency else 0.0,
        },
        "dispatch": {
            "total_dispatches": total_dispatches,
            "completed_dispatches": completed_dispatches,
            "failed_dispatches": failed_dispatches,
            "success_rate": dispatch_success_rate,
            "grid_response_count": grid_response_count,
        },
        "revenue": {
            "estimated_revenue": estimated_revenue,
            "discharge_revenue": round(total_discharge_kwh * discharge_price, 2),
            "charge_cost": round(total_charge_kwh * charge_price, 2),
        },
        "device_details": device_details,
        "daily_trend": v2g_trend,
    })
