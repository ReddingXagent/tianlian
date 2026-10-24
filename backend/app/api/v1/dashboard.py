"""
天链V3 — 数据大屏独立展示模式
面向监控大屏/电视墙的聚合数据端点
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timezone
from typing import Optional

from app.core.database import get_db
from app.models.device import Device
from app.models.station import Station
from app.models.alarm import Alarm
from app.models.workorder import WorkOrder
from app.models.user import User
from app.api.deps import team_scope
from app.api.v1.auth import get_current_user
from app.tasks.tz_utils import biz_day_bounds_utc_naive, today_in_biz_tz

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["数据大屏"], dependencies=[Depends(get_current_user)])


@router.get("/large-screen")
def get_large_screen_data(
    tz_offset: Optional[int] = Query(8, description="时区偏移（默认东八区）"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    大屏独立展示模式聚合数据端点。

    返回监控大屏/电视墙展示所需要的全部聚合数据，包括：
    - 核心指标（设备总量、在线数、告警数、工单数）
    - 站点健康分布
    - 告警实时列表
    - 工单/设备在线统计
    """
    try:
        now = datetime.now(timezone.utc)
        # today_new_alarms 窗口: 业务日(上海)[00:00,24:00) 换算为 naive-UTC 起点
        # (卡 ba16a9ff); Alarm.created_at 为 server_default func.now() (UTC)。
        today_start, _ = biz_day_bounds_utc_naive(today_in_biz_tz())

        # ── 团队范围 (卡 e61ac986): 团队级用户全部聚合按本 team 站点过滤; admin 全量 ──
        tid = team_scope(user)
        station_ids = None
        if tid is not None:
            station_ids = [
                row[0] for row in
                db.query(Station.id).filter(Station.team_id == tid).all()
            ]

        def _device_q():
            q = db.query(Device)
            if station_ids is not None:
                q = q.filter(Device.station_id.in_(station_ids))
            return q

        def _alarm_q():
            q = db.query(Alarm)
            if station_ids is not None:
                q = q.filter(Alarm.station_id.in_(station_ids))
            return q

        def _wo_q():
            q = db.query(WorkOrder)
            if station_ids is not None:
                q = q.filter(WorkOrder.station_id.in_(station_ids))
            return q

        # ── 设备统计 ──
        device_count = _device_q().count() or 0
        online_count = _device_q().filter(
            Device.status == 'online'
        ).count() or 0
        fault_count = _device_q().filter(
            Device.status == 'fault'
        ).count() or 0
        offline_count = _device_q().filter(
            Device.status == 'offline'
        ).count() or 0
        online_rate = round(
            (online_count / device_count * 100) if device_count > 0 else 0, 1
        )

        # ── 站点统计 ──
        station_count = (
            db.query(func.count(Station.id)).filter(Station.team_id == tid)
            .scalar() or 0 if tid is not None
            else db.query(func.count(Station.id)).scalar() or 0
        )

        # ── 告警统计 ──
        active_alarms = _alarm_q().filter(
            Alarm.status == 'active'
        ).count() or 0
        critical_alarms = _alarm_q().filter(
            Alarm.status == 'active',
            Alarm.level == 'critical',
        ).count() or 0
        warning_alarms = _alarm_q().filter(
            Alarm.status == 'active',
            Alarm.level.in_(['warning', 'major']),
        ).count() or 0
        today_new_alarms = _alarm_q().filter(
            Alarm.created_at >= today_start
        ).count() or 0

        # ── 工单统计 ──
        pending_wos = _wo_q().filter(
            WorkOrder.status == 'pending'
        ).count() or 0
        in_progress_wos = _wo_q().filter(
            WorkOrder.status == 'in_progress'
        ).count() or 0
        completed_wos = _wo_q().filter(
            WorkOrder.status.in_(['completed', 'closed'])
        ).count() or 0

        # ── 站点健康分布 ──
        stations_q = db.query(Station)
        if tid is not None:
            stations_q = stations_q.filter(Station.team_id == tid)
        stations = stations_q.all()
        devices = _device_q().all()

        health_distribution = {
            "excellent": 0,
            "good": 0,
            "warning": 0,
            "critical": 0,
        }

        station_health_list = []
        for s in stations:
            s_devices = [d for d in devices if d.station_id == s.id]
            if not s_devices:
                continue
            online = sum(
                1 for d in s_devices if getattr(d, 'status', 'offline') == 'online'
            )
            fault = sum(
                1 for d in s_devices if getattr(d, 'status', 'offline') == 'fault'
            )
            # health_score 列 nullable（生产存量/迁移数据可为 NULL），None 按默认 80 参与均值
            scores = [
                (hs if hs is not None else 80)
                for hs in (getattr(d, 'health_score', None) for d in s_devices)
            ]
            avg_health = sum(scores) / len(scores) if scores else 80
            online_rate_st = (
                online / len(s_devices) * 100
            ) if s_devices else 0
            fault_penalty = min(fault * 5, 30)
            composite = max(
                0,
                min(
                    100,
                    avg_health * 0.6 + online_rate_st * 0.3 - fault_penalty * 0.1 + 10,
                ),
            )

            if composite >= 90:
                health_distribution["excellent"] += 1
            elif composite >= 70:
                health_distribution["good"] += 1
            elif composite >= 50:
                health_distribution["warning"] += 1
            else:
                health_distribution["critical"] += 1

            station_health_list.append({
                "station_id": s.id,
                "station_name": s.name,
                "health_score": round(composite, 1),
                "device_count": len(s_devices),
                "online_count": online,
                "fault_count": fault,
            })

        # ── 告警实时列表（最近20条活跃告警） ──
        recent_alarms_raw = (
            _alarm_q()
            .filter(Alarm.status == 'active')
            .order_by(desc(Alarm.created_at))
            .limit(20)
            .all()
        )
        recent_alarms = []
        for a in recent_alarms_raw:
            recent_alarms.append({
                "id": a.id,
                "title": getattr(a, 'title', '') or getattr(a, 'description', '') or f'告警#{a.id}',
                "level": getattr(a, 'level', 'warning'),
                "device_name": getattr(a, 'device_name', ''),
                "station_name": getattr(a, 'station_name', ''),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })

        # ── 设备在线率统计（按设备类型） ──
        all_device_types = _device_q().with_entities(
            Device.type,
            func.count(Device.id).label('total'),
        ).group_by(Device.type).all()

        online_device_types = _device_q().with_entities(
            Device.type,
            func.count(Device.id).label('online'),
        ).filter(Device.status == 'online').group_by(Device.type).all()

        online_map = {d.type: d.online for d in online_device_types}
        device_type_stats = []
        for dt in all_device_types:
            t = dt.type.value if hasattr(dt.type, 'value') else str(dt.type)
            total = dt.total
            type_online = online_map.get(dt.type, 0)
            device_type_stats.append({
                "type": t,
                "total": total,
                "online": type_online,
                "rate": round((type_online / total * 100) if total > 0 else 0, 1),
            })

        return {
            "core_metrics": {
                "total_devices": device_count,
                "online_devices": online_count,
                "fault_devices": fault_count,
                "offline_devices": offline_count,
                "online_rate": online_rate,
                "total_stations": station_count,
                "active_alarms": active_alarms,
                "critical_alarms": critical_alarms,
                "pending_workorders": pending_wos,
                "in_progress_workorders": in_progress_wos,
            },
            "health_distribution": health_distribution,
            "station_health": station_health_list,
            "recent_alarms": recent_alarms,
            "workorder_stats": {
                "pending": pending_wos,
                "in_progress": in_progress_wos,
                "completed": completed_wos,
                "today_new_alarms": today_new_alarms,
            },
            "alarm_stats": {
                "active": active_alarms,
                "critical": critical_alarms,
                "warning": warning_alarms,
                "today_new": today_new_alarms,
            },
            "device_type_stats": device_type_stats,
            "timestamp": now.isoformat(),
        }
    except Exception:
        logger.exception("大屏数据聚合失败")
        raise HTTPException(status_code=500, detail="大屏数据暂时不可用")
