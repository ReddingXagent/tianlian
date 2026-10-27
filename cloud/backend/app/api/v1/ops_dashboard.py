"""
运维大屏可视化 API - 实时拓扑 + 事件流 + 健康度评分
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.database import get_db
from app.models.device import Device
from app.models.station import Station
from app.models.alarm import Alarm
from app.models.workorder import WorkOrder
from app.models.gateway import Gateway
from app.models.healing_execution import HealingExecution
from app.models.user import User

from app.api.deps import is_platform_admin, assert_station_team_access
from app.api.v1.auth import get_current_user
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ops-dashboard", tags=["运维大屏"], dependencies=[Depends(get_current_user)])


def _team_station_ids(db: Session, user) -> Optional[list]:
    """本 team 站点 id 列表；admin/super_admin 返回 None（不过滤，平台级全可见）。
    任务卡 1c19b59a team scoping。"""
    if is_platform_admin(user):
        return None
    rows = db.query(Station.id).filter(Station.team_id == user.team_id).all()
    return [r[0] for r in rows]


# ─── 实时拓扑 ───────────────────────────────────────

@router.get("/topology")
def get_topology(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """获取全量拓扑数据：站点→网关→设备层级关系

    注：移除原 @cached(ttl=30) —— cache key 不含 user.team_id，跨用户同 URL 会串数据
    （任务卡 1c19b59a team scoping，同 stations/predictive_maintenance 治理）。
    """
    try:
        sids = _team_station_ids(db, current_user)
        sta_q = db.query(Station)
        gw_q = db.query(Gateway)
        dev_q = db.query(Device)
        if sids is not None:
            sta_q = sta_q.filter(Station.id.in_(sids))
            gw_q = gw_q.filter(Gateway.station_id.in_(sids))
            dev_q = dev_q.filter(Device.station_id.in_(sids))
        stations = sta_q.all()
        gateways = gw_q.all()
        devices = dev_q.all()

        # 构建站点节点
        station_nodes = []
        for s in stations:
            s_devices = [d for d in devices if d.station_id == s.id]
            s_gateways = [g for g in gateways if g.station_id == s.id]
            online_count = sum(1 for d in s_devices if getattr(d, 'status', 'offline') == 'online')
            fault_count = sum(1 for d in s_devices if getattr(d, 'status', 'offline') == 'fault')
            total_count = len(s_devices)

            station_nodes.append({
                "id": f"station-{s.id}",
                "type": "station",
                "name": s.name,
                "status": "normal" if fault_count == 0 else ("warning" if fault_count <= 2 else "fault"),
                "device_count": total_count,
                "online_count": online_count,
                "fault_count": fault_count,
                "gateway_count": len(s_gateways),
                "health_score": getattr(s, 'health_score', None) or 85,
                "position": {"lat": getattr(s, 'lat', 31.23), "lng": getattr(s, 'lng', 121.50)},
            })

        # 构建网关节点
        gateway_nodes = []
        for g in gateways:
            g_devices = [d for d in devices if getattr(d, 'gateway_id', None) == g.id]
            online = sum(1 for d in g_devices if getattr(d, 'status', 'offline') == 'online')
            gateway_nodes.append({
                "id": f"gateway-{g.id}",
                "type": "gateway",
                "name": getattr(g, 'name', f'网关-{g.id}'),
                "station_id": g.station_id,
                "status": getattr(g, 'status', 'online'),
                "device_count": len(g_devices),
                "online_count": online,
                "sn": getattr(g, 'sn', ''),
            })

        # 构建设备节点
        device_nodes = []
        for d in devices:
            device_nodes.append({
                "id": f"device-{d.id}",
                "type": "device",
                "name": getattr(d, 'name', f'设备-{d.id}'),
                "station_id": d.station_id,
                "gateway_id": getattr(d, 'gateway_id', None),
                "device_type": getattr(d, 'device_type', 'unknown'),
                "status": getattr(d, 'status', 'offline'),
                "health_score": getattr(d, 'health_score', None) or 80,
            })

        # 构建连接线（edges）
        edges = []
        # 站点→网关
        for g in gateway_nodes:
            edges.append({
                "source": f"station-{g['station_id']}",
                "target": g["id"],
                "type": "station-gateway",
            })
        # 网关→设备
        for d in device_nodes:
            if d["gateway_id"]:
                edges.append({
                    "source": f"gateway-{d['gateway_id']}",
                    "target": d["id"],
                    "type": "gateway-device",
                })
            else:
                edges.append({
                    "source": f"station-{d['station_id']}",
                    "target": d["id"],
                    "type": "station-device",
                })

        return {
            "nodes": {
                "stations": station_nodes,
                "gateways": gateway_nodes,
                "devices": device_nodes,
            },
            "edges": edges,
            "summary": {
                "total_stations": len(station_nodes),
                "total_gateways": len(gateway_nodes),
                "total_devices": len(device_nodes),
                "online_devices": sum(1 for d in device_nodes if d["status"] == "online"),
                "fault_devices": sum(1 for d in device_nodes if d["status"] == "fault"),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_topology 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 事件流 ──────────────────────────────────────────

@router.get("/event-stream")
def get_event_stream(
    limit: int = Query(50, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取最新事件流：告警+工单+自愈，按时间倒序混合排列"""
    # team scoping（任务卡 1c19b59a）：station 存在才校验归属（跨团队→404）；
    # 不存在的 station 走既有契约（返回空事件，不泄露存在性）。
    try:
        if station_id:
            if db.query(Station.id).filter(Station.id == station_id).first():
                assert_station_team_access(db, station_id, current_user)
            sids = [station_id]
        else:
            sids = _team_station_ids(db, current_user)
        events = []

        # 告警事件
        alarm_query = db.query(Alarm).order_by(desc(Alarm.created_at))
        if sids is not None:
            alarm_query = alarm_query.filter(Alarm.station_id.in_(sids))
        alarms = alarm_query.limit(limit).all()
        # alarms表只有station_id/device_id数字列 → 批量查名称(2026-10-10 丁哥: 事件流必须显示站点/设备名/告警类型)
        _dids = {a.device_id for a in alarms if a.device_id}
        _sids = {a.station_id for a in alarms if a.station_id}
        _dmap = {d.id: d.name for d in db.query(Device).filter(Device.id.in_(_dids)).all()} if _dids else {}
        _smap = {s.id: s.name for s in db.query(Station).filter(Station.id.in_(_sids)).all()} if _sids else {}
        for a in alarms:
            events.append({
                "id": f"alarm-{a.id}",
                "type": "alarm",
                "title": (getattr(a, 'content', '') or f'告警#{a.id}')[:60],
                "level": getattr(a, 'level', 'warning') or 'warning',
                "status": getattr(a, 'status', 'active'),
                "station_name": _smap.get(a.station_id, ''),
                "device_name": _dmap.get(a.device_id, ''),
                "alarm_type": getattr(a, 'alarm_type', '') or '',
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "timestamp": a.created_at.isoformat() if a.created_at else datetime.min.isoformat(),
            })

        # 工单事件
        wo_query = db.query(WorkOrder).order_by(desc(WorkOrder.create_time))
        if sids is not None:
            wo_query = wo_query.filter(WorkOrder.station_id.in_(sids))
        workorders = wo_query.limit(limit).all()
        for w in workorders:
            events.append({
                "id": f"workorder-{w.id}",
                "type": "workorder",
                "title": getattr(w, 'title', '') or getattr(w, 'description', f'工单#{w.id}'),
                "level": "critical" if getattr(w, 'priority', '') == 'critical' else "info",
                "status": getattr(w, 'status', 'pending'),
                "station_name": getattr(w, 'station_name', ''),
                "device_name": getattr(w, 'device_name', ''),
                "created_at": w.create_time.isoformat() if w.create_time else None,
                "timestamp": w.create_time.isoformat() if w.create_time else datetime.min.isoformat(),
            })

        # 自愈事件
        healing_query = db.query(HealingExecution).order_by(desc(HealingExecution.created_at))
        if sids is not None:
            healing_query = healing_query.filter(HealingExecution.station_id.in_(sids))
        healings = healing_query.limit(limit).all()
        for h in healings:
            events.append({
                "id": f"healing-{h.id}",
                "type": "healing",
                "title": getattr(h, 'rule_name', '') or f'自愈#{h.id}',
                "level": "success",
                "status": getattr(h, 'status', 'pending'),
                "station_name": getattr(h, 'station_name', ''),
                "device_name": getattr(h, 'device_name', ''),
                "result": getattr(h, 'result', ''),
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "timestamp": h.created_at.isoformat() if h.created_at else datetime.min.isoformat(),
            })

        # 按时间倒序排列，取前N条
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"events": events[:limit], "total": len(events)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_event_stream 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 健康度评分 ──────────────────────────────────────

@router.get("/health-scores")
def get_health_scores(
    station_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取健康度评分概览：整体+各站点+趋势

    注：移除原 @cached(ttl=30) —— cache key 不含 user.team_id，跨用户同 URL 会串数据
    （任务卡 1c19b59a team scoping）。
    """
    # team scoping（任务卡 1c19b59a）：station 存在才校验归属（跨团队→404）；
    # 不存在的 station 走既有契约（返回空事件，不泄露存在性）。
    try:
        if station_id:
            if db.query(Station.id).filter(Station.id == station_id).first():
                assert_station_team_access(db, station_id, current_user)
            sids = [station_id]
        else:
            sids = _team_station_ids(db, current_user)
        sta_q = db.query(Station)
        dev_q = db.query(Device)
        if sids is not None:
            sta_q = sta_q.filter(Station.id.in_(sids))
            dev_q = dev_q.filter(Device.station_id.in_(sids))
        stations = sta_q.all()
        devices = dev_q.all()

        station_scores = []
        total_health = 0
        total_online = 0
        total_fault = 0
        total_devices_count = 0

        for s in stations:
            s_devices = [d for d in devices if d.station_id == s.id]
            online = sum(1 for d in s_devices if getattr(d, 'status', 'offline') == 'online')
            fault = sum(1 for d in s_devices if getattr(d, 'status', 'offline') == 'fault')
            # health_score 列 nullable，None 按默认 80 参与均值（卡 fcfd13fd 防 500）
            device_health_scores = [
                (hs if hs is not None else 80)
                for hs in (getattr(d, 'health_score', None) for d in s_devices)
            ]
            avg_health = sum(device_health_scores) / len(device_health_scores) if device_health_scores else 0

            # 计算综合健康度：设备健康度*0.6 + 在线率*0.3 - 故障惩罚*0.1
            online_rate = (online / len(s_devices) * 100) if s_devices else 0
            fault_penalty = min(fault * 5, 30)
            composite_score = max(0, min(100, avg_health * 0.6 + online_rate * 0.3 - fault_penalty * 0.1 + 10))

            station_scores.append({
                "station_id": s.id,
                "station_name": s.name,
                "health_score": round(composite_score, 1),
                "device_health_avg": round(avg_health, 1),
                "online_rate": round(online_rate, 1),
                "device_count": len(s_devices),
                "online_count": online,
                "fault_count": fault,
                "status": "normal" if composite_score >= 80 else ("warning" if composite_score >= 60 else "fault"),
            })

            total_health += composite_score
            total_online += online
            total_fault += fault
            total_devices_count += len(s_devices)

        overall_score = total_health / len(station_scores) if station_scores else 0
        overall_online_rate = (total_online / total_devices_count * 100) if total_devices_count else 0

        # 健康度分布
        distribution = {
            "excellent": sum(1 for s in station_scores if s["health_score"] >= 90),
            "good": sum(1 for s in station_scores if 80 <= s["health_score"] < 90),
            "warning": sum(1 for s in station_scores if 60 <= s["health_score"] < 80),
            "fault": sum(1 for s in station_scores if s["health_score"] < 60),
        }

        return {
            "overall_score": round(overall_score, 1),
            "overall_online_rate": round(overall_online_rate, 1),
            "total_stations": len(station_scores),
            "total_devices": total_devices_count,
            "total_online": total_online,
            "total_fault": total_fault,
            "distribution": distribution,
            "stations": station_scores,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_health_scores 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


# ─── 大屏综合数据 ─────────────────────────────────────

@router.get("/overview")
def get_dashboard_overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """大屏综合概览：一次性返回所有大屏需要的数据

    注：移除原 @cached(ttl=30) —— cache key 不含 user.team_id，跨用户同 URL 会串数据
    （任务卡 1c19b59a team scoping）。
    """
    try:
        sids = _team_station_ids(db, current_user)

        # 站点统计
        station_q = db.query(func.count(Station.id))
        device_q = db.query(func.count(Device.id))
        online_q = db.query(func.count(Device.id)).filter(Device.status == 'online')
        fault_q = db.query(func.count(Device.id)).filter(Device.status == 'fault')
        if sids is not None:
            station_q = station_q.filter(Station.id.in_(sids))
            device_q = device_q.filter(Device.station_id.in_(sids))
            online_q = online_q.filter(Device.station_id.in_(sids))
            fault_q = fault_q.filter(Device.station_id.in_(sids))
        station_count = station_q.scalar() or 0
        device_count = device_q.scalar() or 0
        online_count = online_q.scalar() or 0
        fault_count = fault_q.scalar() or 0

        # 告警统计
        active_q = db.query(func.count(Alarm.id)).filter(Alarm.status == 'active')
        crit_q = db.query(func.count(Alarm.id)).filter(
            Alarm.status == 'active', Alarm.level == 'critical'
        )
        if sids is not None:
            active_q = active_q.filter(Alarm.station_id.in_(sids))
            crit_q = crit_q.filter(Alarm.station_id.in_(sids))
        active_alarms = active_q.scalar() or 0
        critical_alarms = crit_q.scalar() or 0

        # 工单统计
        pend_q = db.query(func.count(WorkOrder.id)).filter(WorkOrder.status == 'pending')
        prog_q = db.query(func.count(WorkOrder.id)).filter(WorkOrder.status == 'in_progress')
        if sids is not None:
            pend_q = pend_q.filter(WorkOrder.station_id.in_(sids))
            prog_q = prog_q.filter(WorkOrder.station_id.in_(sids))
        pending_wo = pend_q.scalar() or 0
        in_progress_wo = prog_q.scalar() or 0

        # 自愈统计(近24h)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        h24_q = db.query(func.count(HealingExecution.id)).filter(
            HealingExecution.created_at >= yesterday
        )
        hs24_q = db.query(func.count(HealingExecution.id)).filter(
            HealingExecution.created_at >= yesterday,
            HealingExecution.status == 'success',
        )
        if sids is not None:
            h24_q = h24_q.filter(HealingExecution.station_id.in_(sids))
            hs24_q = hs24_q.filter(HealingExecution.station_id.in_(sids))
        healing_24h = h24_q.scalar() or 0
        healing_success_24h = hs24_q.scalar() or 0

        # 在线率
        online_rate = (online_count / device_count * 100) if device_count > 0 else 0

        return {
            "stats": {
                "stations": station_count,
                "devices": device_count,
                "online": online_count,
                "fault": fault_count,
                "online_rate": round(online_rate, 1),
            },
            "alarms": {
                "active": active_alarms,
                "critical": critical_alarms,
            },
            "workorders": {
                "pending": pending_wo,
                "in_progress": in_progress_wo,
            },
            "healing": {
                "total_24h": healing_24h,
                "success_24h": healing_success_24h,
                "success_rate": round(healing_success_24h / healing_24h * 100, 1) if healing_24h > 0 else 0,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_dashboard_overview 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

