"""故障分析报表端点（拆分自原 reports.py）。"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.alarm import Alarm, AlarmLevel
from app.models.device import Device
from app.models.station import Station
from app.models.user import User
from app.models.workorder import WorkOrder, WorkOrderStatus

from ._shared import _ROUTER_DEPENDENCIES, _own_station_ids, _check_station_in_scope, _biz_day_key
from .export import _render_export


router = APIRouter(tags=["数据分析报表"], dependencies=_ROUTER_DEPENDENCIES)


@router.get("/faults")
def report_faults(
    days: int = Query(30, ge=1, le=90, description="统计周期(天)"),
    station_id: Optional[int] = Query(None, alias="station_id"),
    format: Optional[str] = Query(None, alias="format", description="导出格式: csv/xlsx/pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据分析 - 故障分析报表：故障类型分布、频次分析、趋势、MTBF/MTTR"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    own = _own_station_ids(db, user)
    _check_station_in_scope(station_id, own, user)

    query = db.query(Alarm).filter(Alarm.created_at >= cutoff)
    if own is not None:
        query = query.filter(Alarm.station_id.in_(own))
    if station_id:
        query = query.filter(Alarm.station_id == station_id)
    # 故障类告警 (排除info级别)
    alarms = query.filter(Alarm.level != AlarmLevel.INFO).all()

    # ── 故障类型分布 ──
    fault_type_dist = {}
    for a in alarms:
        at = a.alarm_type or "unknown"
        fault_type_dist[at] = fault_type_dist.get(at, 0) + 1

    # ── 故障级别分布 ──
    fault_level_dist = {"warning": 0, "critical": 0, "fatal": 0}
    for a in alarms:
        lv = a.level.value if hasattr(a.level, 'value') else str(a.level) if a.level else "warning"
        if lv in fault_level_dist:
            fault_level_dist[lv] += 1
        elif lv == "info":
            pass
        else:
            fault_level_dist[lv] = 1

    # ── 故障设备排行 (TOP 10) ──
    device_faults = {}
    device_names = {}
    device_stations = {}
    for a in alarms:
        did = a.device_id
        device_faults[did] = device_faults.get(did, 0) + 1
        if did not in device_names:
            dev = db.query(Device).filter(Device.id == did).first()
            device_names[did] = dev.name if dev else f"设备#{did}"
            device_stations[did] = dev.station_id if dev else None
    station_names_q = db.query(Station)
    if own is not None:
        station_names_q = station_names_q.filter(Station.id.in_(own))
    station_names = {s.id: s.name for s in station_names_q.all()}
    top_fault_devices = sorted(
        [{
            "device_id": did,
            "device_name": device_names[did],
            "station_name": station_names.get(device_stations[did], ""),
            "fault_count": cnt
        }
         for did, cnt in device_faults.items()],
        key=lambda x: x["fault_count"], reverse=True
    )[:10]

    # ── MTBF/MTTR 计算 (基于已完成工单；限本 team 站点 — 任务卡 b640bdd9) ──
    wo_mtbf_q = db.query(WorkOrder).filter(
        WorkOrder.create_time >= cutoff,
        WorkOrder.status == WorkOrderStatus.COMPLETED,
        WorkOrder.accept_time.isnot(None),
        WorkOrder.finish_time.isnot(None)
    )
    if own is not None:
        wo_mtbf_q = wo_mtbf_q.filter(WorkOrder.station_id.in_(own))
    workorders = wo_mtbf_q.all()

    mtbf_hours = 0.0
    mttr_hours = 0.0
    if workorders:
        # MTTR: 平均修复时间 (从接单到完成)
        repair_times = [(wo.finish_time - wo.accept_time).total_seconds() / 3600 for wo in workorders]
        mttr_hours = round(sum(repair_times) / len(repair_times), 1)
        # MTBF: 平均故障间隔 (简化计算: 统计周期总小时数 / 故障次数)
        total_hours = days * 24
        total_faults = len(alarms)
        mtbf_hours = round(total_hours / max(total_faults, 1), 1) if total_faults > 0 else total_hours

    # ── 趋势：按天统计故障数 ──
    daily = defaultdict(int)
    daily_by_type = defaultdict(lambda: defaultdict(int))
    for a in alarms:
        day_key = _biz_day_key(a.created_at)
        daily[day_key] += 1
        at = a.alarm_type or "unknown"
        daily_by_type[day_key][at] += 1

    fault_trend = [{"date": d, "count": c} for d, c in sorted(daily.items())]

    # 按类型的趋势数据
    all_types = list(set(at for a in alarms for at in [a.alarm_type or "unknown"]))
    fault_trend_by_type = []
    for ftype in all_types:
        series = []
        for d in sorted(daily.keys()):
            series.append({"date": d, "count": daily_by_type[d].get(ftype, 0)})
        if any(s["count"] > 0 for s in series):
            fault_trend_by_type.append({"type": ftype, "data": series})

    if format:
        headers = ["故障ID", "设备", "站点", "故障类型", "级别", "状态", "创建时间", "解决时间"]
        data = []
        for a in alarms:
            dev_name = device_names.get(a.device_id, f"#{a.device_id}")
            st_name = station_names.get(device_stations.get(a.device_id), "")
            data.append([
                str(a.id), dev_name, st_name, a.alarm_type or "",
                a.level.value if a.level else "", a.status.value if a.status else "",
                a.created_at.strftime('%Y-%m-%d %H:%M') if a.created_at else "",
                a.resolved_at.strftime('%Y-%m-%d %H:%M') if a.resolved_at else "",
            ])
        return _render_export(format, data, headers, "故障分析报表", "faults")

    return success_response({
        "period_days": days,
        "total_faults": len(alarms),
        "fault_type_distribution": fault_type_dist,
        "fault_level_distribution": fault_level_dist,
        "top_fault_devices": top_fault_devices,
        "mtbf_hours": mtbf_hours,
        "mttr_hours": mttr_hours,
        "fault_trend": fault_trend,
        "fault_trend_by_type": fault_trend_by_type,
    })
