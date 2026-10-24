"""汇总报表端点（拆分自原 reports.py）。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.alarm import Alarm, AlarmStatus
from app.models.device import Device, DeviceStatus
from app.models.station import Station
from app.models.user import User
from app.models.workorder import WorkOrder, WorkOrderStatus

from ._shared import _ROUTER_DEPENDENCIES, _own_station_ids, _get_team_performance
from .export import _render_export


router = APIRouter(tags=["数据分析报表"], dependencies=_ROUTER_DEPENDENCIES)


@router.get("/summary")
def report_summary(
    days: int = Query(30, ge=1, le=90, description="统计周期(天)"),
    format: Optional[str] = Query(None, alias="format", description="导出格式: csv/xlsx/pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据分析 - 汇总报表：全局指标 + 团队绩效 + 站点健康分布"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    own = _own_station_ids(db, user)

    # ── 全局计数（team scoping 任务卡 b640bdd9：非 admin 仅本 team 站点派生资源）──
    dev_q = db.query(Device)
    wo_q = db.query(WorkOrder).filter(WorkOrder.create_time >= cutoff)
    al_q = db.query(Alarm).filter(Alarm.created_at >= cutoff)
    if own is not None:
        dev_q = dev_q.filter(Device.station_id.in_(own))
        wo_q = wo_q.filter(WorkOrder.station_id.in_(own))
        al_q = al_q.filter(Alarm.station_id.in_(own))

    total_devices = dev_q.count()
    online_devices = dev_q.filter(Device.status == DeviceStatus.ONLINE).count()
    offline_devices = dev_q.filter(Device.status == DeviceStatus.OFFLINE).count()
    fault_devices = dev_q.filter(Device.status == DeviceStatus.FAULT).count()
    maintenance_devices = dev_q.filter(Device.status == DeviceStatus.MAINTENANCE).count()
    total_stations = len(own) if own is not None else db.query(Station).count()
    total_workorders = wo_q.count()
    completed_workorders = wo_q.filter(
        WorkOrder.status == WorkOrderStatus.COMPLETED
    ).count()
    total_alarms = al_q.count()
    active_alarms = al_q.filter(
        Alarm.status == AlarmStatus.ACTIVE
    ).count()

    wo_completion_rate = round(completed_workorders / total_workorders * 100, 1) if total_workorders > 0 else 0.0

    # ── 站点健康分布（仅本 team 站点）──
    station_health_dist = {"normal": 0, "warning": 0, "critical": 0, "offline": 0}
    stations_q = db.query(Station)
    if own is not None:
        stations_q = stations_q.filter(Station.id.in_(own))
    stations = stations_q.all()
    # 聚合查询消除 N+1（任务卡 56530ee3）：3 条 group_by 替代 3N 条逐站查询
    station_ids = [s.id for s in stations]
    active_alarm_by_station = dict(db.query(Alarm.station_id, func.count(Alarm.id)).filter(
        Alarm.status == AlarmStatus.ACTIVE,
        Alarm.station_id.in_(station_ids)
    ).group_by(Alarm.station_id).all())
    device_count_by_station = dict(db.query(Device.station_id, func.count(Device.id)).filter(
        Device.station_id.in_(station_ids)
    ).group_by(Device.station_id).all())
    offline_count_by_station = dict(db.query(Device.station_id, func.count(Device.id)).filter(
        Device.station_id.in_(station_ids),
        Device.status == DeviceStatus.OFFLINE
    ).group_by(Device.station_id).all())
    for s in stations:
        active_alarm_count = active_alarm_by_station.get(s.id, 0)
        device_count = device_count_by_station.get(s.id, 0)
        offline_count = offline_count_by_station.get(s.id, 0)
        if device_count == 0:
            station_health_dist["offline"] += 1
        elif offline_count > device_count * 0.5 or active_alarm_count > 5:
            station_health_dist["critical"] += 1
        elif offline_count > device_count * 0.2 or active_alarm_count > 2:
            station_health_dist["warning"] += 1
        else:
            station_health_dist["normal"] += 1

    # ── 团队绩效（非 admin 仅本 team 工程师）──
    team_performance = _get_team_performance(db, cutoff, user.team_id if own is not None else None)
    top_engineers = sorted(team_performance, key=lambda x: x["completion_rate"], reverse=True)[:5]

    if format:
        # 导出
        headers = ["指标", "数值"]
        data = [
            ["设备总数", str(total_devices)],
            ["在线设备", str(online_devices)],
            ["离线设备", str(offline_devices)],
            ["故障设备", str(fault_devices)],
            ["维护中设备", str(maintenance_devices)],
            ["站点总数", str(total_stations)],
            [f"近{days}天工单数", str(total_workorders)],
            [f"近{days}天完成工单", str(completed_workorders)],
            [f"工单完成率", f"{wo_completion_rate}%"],
            [f"近{days}天告警数", str(total_alarms)],
            [f"活跃告警", str(active_alarms)],
            ["站点健康-正常", str(station_health_dist["normal"])],
            ["站点健康-警告", str(station_health_dist["warning"])],
            ["站点健康-严重", str(station_health_dist["critical"])],
            ["站点健康-离线", str(station_health_dist["offline"])],
        ]
        return _render_export(format, data, headers, "业务汇总报表", "summary")

    return success_response({
        "period_days": days,
        "overview": {
            "total_devices": total_devices,
            "online_devices": online_devices,
            "offline_devices": offline_devices,
            "fault_devices": fault_devices,
            "maintenance_devices": maintenance_devices,
            "online_rate": round(online_devices / total_devices * 100, 1) if total_devices else 0,
            "total_stations": total_stations,
            "total_workorders": total_workorders,
            "completed_workorders": completed_workorders,
            "completion_rate": wo_completion_rate,
            "total_alarms": total_alarms,
            "active_alarms": active_alarms,
        },
        "station_health": {
            "distribution": station_health_dist,
            "healthy_rate": round(station_health_dist["normal"] / max(total_stations, 1) * 100, 1),
        },
        "team_performance": {
            "engineers": team_performance,
            "total_engineers": len(team_performance),
            "top_engineers": top_engineers,
        },
    })
