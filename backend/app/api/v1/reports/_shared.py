"""数据分析报表 API 共享定义（拆分自原 reports.py）。

仅存放跨子模块复用的模块级对象：logger、router 级鉴权依赖、team scoping helper、
团队工程师绩效聚合 helper。各报表端点按类型拆分到同包各子模块。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin
from app.tasks.tz_utils import get_biz_tz
from app.models.station import Station
from app.models.user import User
from app.models.workorder import WorkOrder, WorkOrderStatus


logger = logging.getLogger("app.api.v1.reports")


# 报表 router 级鉴权依赖（原 reports.py 顶层 router 的 dependencies）
_ROUTER_DEPENDENCIES = [Depends(get_current_user)]


def _own_station_ids(db: Session, user: User):
    """报表 team scoping（任务卡 b640bdd9）：非 admin 返回本 team 站点 id 列表，
    admin 返回 None（全量，不过滤）。报表各端点按此集合过滤 station 派生资源，
    杜绝团队级用户读到跨团队聚合数据。"""
    if is_platform_admin(user):
        return None
    return [sid for (sid,) in db.query(Station.id).filter(Station.team_id == user.team_id).all()]


def _biz_day_key(ts) -> str:
    """UTC-naive 落库时间 → 业务时区墙钟日键 '%Y-%m-%d'（卡 e86c6209，对齐 energy_report 20cb47ed 契约）。
    None/异常回退 'unknown'（与原 strftime fallback 语义一致）。"""
    if ts is None:
        return "unknown"
    try:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(get_biz_tz()).strftime('%Y-%m-%d')
    except Exception:
        return "unknown"


def _check_station_in_scope(station_id: Optional[int], own, user: User):
    """报表 station_id 查询参数归属校验：非 admin 传入他队站点 → 404（不泄露存在）。
    own 为 None（admin）时直接放行，保持 admin 传不存在的 station_id 返回空的原语义。"""
    if station_id and own is not None and station_id not in own:
        raise HTTPException(status_code=404, detail="站点不存在")


def _get_team_performance(db: Session, cutoff: datetime, team_id: Optional[int] = None) -> list:
    """获取团队工程师绩效数据（team_id 非空时仅统计该 team 工程师 — 任务卡 b640bdd9）。"""
    eng_q = db.query(User).filter(
        User.role.in_(["engineer", "dispatcher", "station_master"])
    )
    if team_id is not None:
        eng_q = eng_q.filter(User.team_id == team_id)
    engineers = eng_q.all()
    result = []
    for eng in engineers:
        assigned = db.query(WorkOrder).filter(
            WorkOrder.assignee_id == eng.id,
            WorkOrder.create_time >= cutoff
        ).all()
        completed = [wo for wo in assigned if wo.status == WorkOrderStatus.COMPLETED]
        total = len(assigned)
        done = len(completed)
        rate = round(done / total * 100, 1) if total > 0 else 0.0
        # 响应时间
        responded = [wo for wo in assigned if wo.accept_time]
        avg_resp = round(
            sum((wo.accept_time - wo.create_time).total_seconds() for wo in responded) / max(len(responded), 1) / 3600, 1
        ) if responded else 0.0
        # 完成时间
        finished = [wo for wo in completed if wo.accept_time and wo.finish_time]
        avg_dur = round(
            sum((wo.finish_time - wo.accept_time).total_seconds() for wo in finished) / max(len(finished), 1) / 3600, 1
        ) if finished else 0.0
        # 绩效评分 (综合完成率+响应速度)
        score = round(rate * 0.6 + max(0, 100 - avg_resp * 5) * 0.4, 1) if total > 0 else 0.0
        result.append({
            "engineer_id": eng.id,
            "name": eng.real_name or eng.username,
            "level": eng.level.value if eng.level else "junior",
            "assigned": total,
            "completed": done,
            "completion_rate": rate,
            "avg_response_hours": avg_resp,
            "avg_completion_hours": avg_dur,
            "performance_score": score,
        })
    result.sort(key=lambda x: x["performance_score"], reverse=True)
    return result
