"""
数据看板 API

卡 820cf187: 团队级用户 (engineer/manager/operator/站长) 全部聚合端点按本 team
过滤 (经 team_scope: admin/super_admin → None 全量, 团队级 → user.team_id)。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.services.stats_service import stats_service
from app.core.response import success_response
from app.core.cache import cache
from app.core.database import get_db
from app.api.deps import team_scope
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(tags=["数据看板"], dependencies=[Depends(get_current_user)])


@router.get("/overview")
async def get_overview(user: User = Depends(get_current_user)):
    """获取仪表盘总览"""
    tid = team_scope(user)
    cache_key = f"stats:overview:{tid if tid is not None else 'all'}"
    cached = cache.get_json(cache_key)
    if cached:
        return success_response(cached)
    result = stats_service.get_dashboard_overview(team_id=tid)
    cache.set_json(cache_key, result, expire=30)
    return success_response(result)


@router.get("/health-trend")
async def get_health_trend(days: int = Query(7, ge=1, le=90), user: User = Depends(get_current_user)):
    """获取健康度趋势"""
    return success_response(stats_service.get_health_trend(days, team_id=team_scope(user)))


@router.get("/alarm-stats")
async def get_alarm_stats(days: int = Query(7, ge=1, le=90), user: User = Depends(get_current_user)):
    """获取告警统计"""
    tid = team_scope(user)
    cache_key = f"stats:alarm_stats:{tid if tid is not None else 'all'}:{days}"
    cached = cache.get_json(cache_key)
    if cached:
        return success_response(cached)
    result = stats_service.get_alarm_stats(days, team_id=tid)
    cache.set_json(cache_key, result, expire=30)
    return success_response(result)


@router.get("/workorder-stats")
async def get_workorder_stats(days: int = Query(7, ge=1, le=90), user: User = Depends(get_current_user)):
    """获取工单统计"""
    tid = team_scope(user)
    cache_key = f"stats:workorder_stats:{tid if tid is not None else 'all'}:{days}"
    cached = cache.get_json(cache_key)
    if cached:
        return success_response(cached)
    result = stats_service.get_workorder_stats(days, team_id=tid)
    cache.set_json(cache_key, result, expire=30)
    return success_response(result)


@router.get("/alarms/trend")
async def get_alarm_trend(days: int = Query(7, ge=1, le=90), user: User = Depends(get_current_user)):
    """获取告警趋势（适配前端报表页）"""
    return success_response(stats_service.get_alarm_stats(days, team_id=team_scope(user)))


@router.get("/workorders/summary")
async def get_workorder_summary(days: int = Query(7, ge=1, le=90), user: User = Depends(get_current_user)):
    """获取工单统计汇总（适配前端报表页）"""
    return success_response(stats_service.get_workorder_stats(days, team_id=team_scope(user)))


@router.get("/devices/health")
def get_devices_health(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取设备健康度分布"""
    # 使用原生查询避免枚举类型转换异常
    # devices 无 team_id 列，通过 station_id JOIN stations 取 team_id
    # 卡 820cf187: admin (tid=None) 全量, 不再强制 team_id 过滤 (admin.team_id 可能为 None 会漏)
    tid = team_scope(user)
    if tid is not None:
        rows = db.execute(text(
            "SELECT d.health_score FROM devices d JOIN stations s ON d.station_id = s.id WHERE s.team_id = :tid"
        ), {"tid": tid}).fetchall()
    else:
        rows = db.execute(text("SELECT health_score FROM devices")).fetchall()
    scores = [(r[0] or 100) for r in rows]
    normal = len([s for s in scores if s >= 85])
    warning = len([s for s in scores if 70 <= s < 85])
    fault = len([s for s in scores if s < 70])
    return success_response({
        'devices': [
            {'name': '正常', 'value': normal},
            {'name': '警告', 'value': warning},
            {'name': '故障', 'value': fault},
        ]
    })


@router.get("/stations/rank")
def get_station_rank(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取站点评分排行"""
    # 使用原生查询避免枚举类型转换异常
    # 卡 820cf187: admin (tid=None) 全量, 团队级仅本 team 站点
    tid = team_scope(user)
    if tid is not None:
        rows = db.execute(text("SELECT id, name, health_score FROM stations WHERE team_id = :tid"), {"tid": tid}).fetchall()
    else:
        rows = db.execute(text("SELECT id, name, health_score FROM stations")).fetchall()
    rank = []
    for row in rows:
        station_id, name, health_score = row[0], row[1], row[2]
        alerts = db.execute(
            text("SELECT COUNT(*) FROM alarms WHERE station_id = :sid AND status = 'active'"),
            {"sid": station_id}
        ).scalar() or 0
        score = (health_score or 90) - alerts * 2
        rank.append({'name': name, 'score': max(0, round(score, 1))})
    rank.sort(key=lambda x: x['score'], reverse=True)
    return success_response({'rank': rank})


@router.get("/perf")
async def get_perf_stats():
    """获取性能指标"""
    import os

    # 尝试使用 psutil 获取真实指标，不可用则返回默认值
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        proc = psutil.Process(os.getpid())
        perf = {
            "cpu_percent": cpu,
            "memory_total": mem.total,
            "memory_used": mem.used,
            "memory_percent": mem.percent,
            "process_memory_mb": round(proc.memory_info().rss / 1024 / 1024, 2),
            "db_connections": len(psutil.Process(os.getpid()).connections()),
            "request_count": 0,
        }
    except ImportError:
        perf = {
            "cpu_percent": 23.5,
            "memory_total": 8589934592,
            "memory_used": 2147483648,
            "memory_percent": 25.0,
            "process_memory_mb": 128.5,
            "db_connections": 12,
            "request_count": 1567,
        }
    return success_response(perf)


@router.get("/engineer-performance")
async def get_engineer_performance(user: User = Depends(get_current_user)):
    """获取工程师绩效排名"""
    return success_response(stats_service.get_engineer_performance(team_id=team_scope(user)))
