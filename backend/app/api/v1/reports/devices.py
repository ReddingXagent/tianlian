"""设备报表端点（拆分自原 reports.py）。"""
from typing import Optional

import numpy as np
from fastapi import APIRouter, Query, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.device import Device, DeviceStatus
from app.models.station import Station
from app.models.user import User

from ._shared import _ROUTER_DEPENDENCIES, _own_station_ids, _check_station_in_scope
from .export import _render_export


router = APIRouter(tags=["数据分析报表"], dependencies=_ROUTER_DEPENDENCIES)


@router.get("/devices")
def report_devices(
    days: int = Query(30, ge=1, le=90, description="统计周期(天)"),
    station_id: Optional[int] = Query(None, alias="station_id"),
    format: Optional[str] = Query(None, alias="format", description="导出格式: csv/xlsx/pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据分析 - 设备报表：类型分布、状态分布、站点健康、运行统计"""
    own = _own_station_ids(db, user)
    _check_station_in_scope(station_id, own, user)
    query = db.query(Device)
    if own is not None:
        query = query.filter(Device.station_id.in_(own))
    if station_id:
        query = query.filter(Device.station_id == station_id)
    devices = query.all()

    # ── 类型分布 ──
    type_dist = {}
    for d in devices:
        t = d.type.value if hasattr(d.type, 'value') else str(d.type) if d.type else "unknown"
        type_dist[t] = type_dist.get(t, 0) + 1

    # ── 状态分布 ──
    status_dist = {"online": 0, "offline": 0, "fault": 0, "charging": 0, "maintenance": 0}
    for d in devices:
        st = d.status.value if hasattr(d.status, 'value') else str(d.status) if d.status else "offline"
        if st in status_dist:
            status_dist[st] += 1
        else:
            status_dist[st] = 1

    # ── 站点分布（限本 team 站点 — 任务卡 b640bdd9）──
    station_dist = []
    stations_q = db.query(Station)
    device_counts_q = db.query(Device.station_id, func.count(Device.id))
    if own is not None:
        stations_q = stations_q.filter(Station.id.in_(own))
        device_counts_q = device_counts_q.filter(Device.station_id.in_(own))
    stations_map = {s.id: s.name for s in stations_q.all()}
    # 一次 GROUP BY 取代逐站 COUNT，避免站点数 N+1
    device_counts_by_station = dict(device_counts_q.group_by(Device.station_id).all())
    for sid, name in stations_map.items():
        count = device_counts_by_station.get(sid, 0)
        if count:
            station_dist.append({"station_id": sid, "station_name": name, "device_count": count})

    # ── 健康度分布 ──
    health_buckets = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "unknown": 0}
    for d in devices:
        hs = d.health_score
        if hs is None or d.status == DeviceStatus.OFFLINE:
            health_buckets["unknown"] += 1
        elif hs >= 85:
            health_buckets["excellent"] += 1
        elif hs >= 70:
            health_buckets["good"] += 1
        elif hs >= 50:
            health_buckets["fair"] += 1
        else:
            health_buckets["poor"] += 1

    avg_health = np.mean([d.health_score for d in devices if d.health_score is not None]) if any(d.health_score for d in devices) else 0.0

    if format:
        headers = ["设备ID", "设备名称", "设备类型", "序列号", "所属站点", "状态", "健康分", "额定功率(kW)"]
        data = []
        for d in devices:
            st_name = stations_map.get(d.station_id, "")
            data.append([
                str(d.id), d.name, d.type.value if d.type else "", d.sn,
                st_name, d.status.value if d.status else "",
                str(d.health_score) if d.health_score else "", str(d.rated_power or 0)
            ])
        return _render_export(format, data, headers, "设备报表", "devices")

    return success_response({
        "period_days": days,
        "total_devices": len(devices),
        "type_distribution": type_dist,
        "status_distribution": status_dist,
        "station_distribution": station_dist,
        "health_score": {
            "average": round(float(avg_health), 1),
            "distribution": health_buckets,
        },
        "online_rate": round(status_dist.get("online", 0) / max(len(devices), 1) * 100, 1),
        "fault_rate": round(status_dist.get("fault", 0) / max(len(devices), 1) * 100, 1),
    })
