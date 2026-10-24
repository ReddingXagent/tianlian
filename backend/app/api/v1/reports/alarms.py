"""告警报表端点（拆分自原 reports.py）。"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.alarm import Alarm, AlarmStatus
from app.models.device import Device
from app.models.user import User

from ._shared import _ROUTER_DEPENDENCIES, _own_station_ids, _check_station_in_scope, _biz_day_key
from .export import _render_export


router = APIRouter(tags=["数据分析报表"], dependencies=_ROUTER_DEPENDENCIES)


@router.get("/alarms")
def report_alarms(
    days: int = Query(30, ge=1, le=90, description="统计周期(天)"),
    station_id: Optional[int] = Query(None, alias="station_id"),
    format: Optional[str] = Query(None, alias="format", description="导出格式: csv/xlsx/pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据分析 - 告警报表：级别分布、类型统计、处理效率、故障设备排行"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    own = _own_station_ids(db, user)
    _check_station_in_scope(station_id, own, user)

    query = db.query(Alarm).filter(Alarm.created_at >= cutoff)
    if own is not None:
        query = query.filter(Alarm.station_id.in_(own))
    if station_id:
        query = query.filter(Alarm.station_id == station_id)
    alarms = query.all()

    # ── 级别分布 ──
    level_dist = {"info": 0, "warning": 0, "critical": 0, "fatal": 0}
    for a in alarms:
        lv = a.level.value if hasattr(a.level, 'value') else str(a.level) if a.level else "info"
        if lv in level_dist:
            level_dist[lv] += 1
        else:
            level_dist[lv] = 1

    # ── 类型分布 ──
    type_dist = {}
    for a in alarms:
        at = a.alarm_type or "unknown"
        type_dist[at] = type_dist.get(at, 0) + 1

    # ── 状态分布 ──
    status_dist = {}
    for a in alarms:
        st = a.status.value if hasattr(a.status, 'value') else str(a.status) if a.status else "unknown"
        status_dist[st] = status_dist.get(st, 0) + 1

    # ── 处理率 ──
    resolved = sum(1 for a in alarms if a.status in (AlarmStatus.RESOLVED, AlarmStatus.PROCESSED, AlarmStatus.IGNORED))
    resolved_rate = round(resolved / max(len(alarms), 1) * 100, 1)

    # ── 故障设备排行 ──
    device_faults = {}
    device_names = {}
    for a in alarms:
        did = a.device_id
        device_faults[did] = device_faults.get(did, 0) + 1
        if did not in device_names:
            dev = db.query(Device).filter(Device.id == did).first()
            device_names[did] = dev.name if dev else f"设备#{did}"
    top_fault_devices = sorted(
        [{"device_id": did, "device_name": device_names[did], "alarm_count": cnt}
         for did, cnt in device_faults.items()],
        key=lambda x: x["alarm_count"], reverse=True
    )[:10]

    # ── 趋势：按天统计 ──
    daily = defaultdict(int)
    for a in alarms:
        day_key = _biz_day_key(a.created_at)
        daily[day_key] += 1
    alarm_trend = [{"date": d, "count": c} for d, c in sorted(daily.items())]

    if format:
        headers = ["告警ID", "设备", "告警类型", "级别", "状态", "创建时间", "解决时间"]
        data = []
        for a in alarms:
            dev_name = device_names.get(a.device_id, f"#{a.device_id}")
            data.append([
                str(a.id), dev_name, a.alarm_type or "",
                a.level.value if a.level else "", a.status.value if a.status else "",
                a.created_at.strftime('%Y-%m-%d %H:%M') if a.created_at else "",
                a.resolved_at.strftime('%Y-%m-%d %H:%M') if a.resolved_at else "",
            ])
        return _render_export(format, data, headers, "告警报表", "alarms")

    return success_response({
        "period_days": days,
        "total_alarms": len(alarms),
        "level_distribution": level_dist,
        "type_distribution": type_dist,
        "status_distribution": status_dist,
        "resolved_rate": resolved_rate,
        "active_alarms": status_dist.get("active", 0),
        "top_fault_devices": top_fault_devices,
        "daily_trend": alarm_trend,
    })
