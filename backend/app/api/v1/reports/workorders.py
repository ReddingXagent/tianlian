"""工单报表端点（拆分自原 reports.py）。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.user import User
from app.models.workorder import WorkOrder, WorkOrderStatus

from ._shared import _ROUTER_DEPENDENCIES, _own_station_ids, _check_station_in_scope
from .export import _render_export


router = APIRouter(tags=["数据分析报表"], dependencies=_ROUTER_DEPENDENCIES)


@router.get("/workorders")
def report_workorders(
    days: int = Query(30, ge=1, le=90, description="统计周期(天)"),
    station_id: Optional[int] = Query(None, alias="station_id"),
    format: Optional[str] = Query(None, alias="format", description="导出格式: csv/xlsx/pdf"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据分析 - 工单报表：类型分布、状态分析、工程师绩效、响应/完成时效"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    own = _own_station_ids(db, user)
    _check_station_in_scope(station_id, own, user)

    query = db.query(WorkOrder).filter(WorkOrder.create_time >= cutoff)
    if own is not None:
        query = query.filter(WorkOrder.station_id.in_(own))
    if station_id:
        query = query.filter(WorkOrder.station_id == station_id)
    workorders = query.all()

    # ── 类型分布 ──
    type_dist = {}
    for wo in workorders:
        t = wo.type.value if hasattr(wo.type, 'value') else str(wo.type) if wo.type else "unknown"
        type_dist[t] = type_dist.get(t, 0) + 1

    # ── 优先级分布 ──
    level_dist = {}
    for wo in workorders:
        lv = wo.level.value if hasattr(wo.level, 'value') else str(wo.level) if wo.level else "unknown"
        level_dist[lv] = level_dist.get(lv, 0) + 1

    # ── 状态分布 ──
    status_dist = {}
    for wo in workorders:
        st = wo.status.value if hasattr(wo.status, 'value') else str(wo.status) if wo.status else "unknown"
        status_dist[st] = status_dist.get(st, 0) + 1

    # ── 工程师工单统计（非 admin 仅本 team 工程师 — 任务卡 b640bdd9）──
    engineer_stats = []
    eng_q = db.query(User).filter(User.role.in_(["engineer", "dispatcher", "station_master"]))
    if own is not None:
        eng_q = eng_q.filter(User.team_id == user.team_id)
    engineers = eng_q.all()
    for eng in engineers:
        assigned = [wo for wo in workorders if wo.assignee_id == eng.id]
        completed = [wo for wo in assigned if wo.status == WorkOrderStatus.COMPLETED]
        if assigned:
            ct = len(completed)
            cr = round(ct / len(assigned) * 100, 1)
            # 平均响应时间
            responded = [wo for wo in assigned if wo.accept_time]
            avg_resp = 0.0
            if responded:
                total_sec = sum((wo.accept_time - wo.create_time).total_seconds() for wo in responded)
                avg_resp = round(total_sec / len(responded) / 3600, 1)
            # 平均完成时间
            done = [wo for wo in completed if wo.accept_time and wo.finish_time]
            avg_dur = 0.0
            if done:
                total_sec = sum((wo.finish_time - wo.accept_time).total_seconds() for wo in done)
                avg_dur = round(total_sec / len(done) / 3600, 1)
            engineer_stats.append({
                "engineer_id": eng.id,
                "name": eng.real_name or eng.username,
                "level": eng.level.value if eng.level else "junior",
                "assigned": len(assigned),
                "completed": ct,
                "completion_rate": cr,
                "avg_response_hours": avg_resp,
                "avg_completion_hours": avg_dur,
            })

    # ── 整体时效统计 ──
    responded_all = [wo for wo in workorders if wo.accept_time]
    completed_all = [wo for wo in workorders if wo.status == WorkOrderStatus.COMPLETED and wo.accept_time and wo.finish_time]
    avg_response = round(
        sum((wo.accept_time - wo.create_time).total_seconds() for wo in responded_all) / max(len(responded_all), 1) / 3600, 1
    ) if responded_all else 0.0
    avg_completion = round(
        sum((wo.finish_time - wo.accept_time).total_seconds() for wo in completed_all) / max(len(completed_all), 1) / 3600, 1
    ) if completed_all else 0.0

    if format:
        headers = ["工单ID", "标题", "类型", "优先级", "状态", "创建时间", "完成时间", "处理人"]
        # 批量加载所有处理人，避免逐工单 N+1 查 User
        assignee_ids = {wo.assignee_id for wo in workorders if wo.assignee_id}
        assignee_map = {}
        if assignee_ids:
            for _u in db.query(User).filter(User.id.in_(assignee_ids)).all():
                assignee_map[_u.id] = _u.real_name or _u.username
        data = []
        for wo in workorders:
            assignee_name = assignee_map.get(wo.assignee_id, "") if wo.assignee_id else ""
            data.append([
                wo.id, wo.fault_desc or "", wo.type.value if wo.type else "",
                wo.level.value if wo.level else "", wo.status.value if wo.status else "",
                wo.create_time.strftime('%Y-%m-%d %H:%M') if wo.create_time else "",
                wo.finish_time.strftime('%Y-%m-%d %H:%M') if wo.finish_time else "",
                assignee_name,
            ])
        return _render_export(format, data, headers, "工单报表", "workorders")

    return success_response({
        "period_days": days,
        "total_workorders": len(workorders),
        "type_distribution": type_dist,
        "level_distribution": level_dist,
        "status_distribution": status_dist,
        "completion_rate": round(
            status_dist.get("completed", 0) / max(len(workorders), 1) * 100, 1
        ),
        "efficiency": {
            "avg_response_hours": avg_response,
            "avg_completion_hours": avg_completion,
        },
        "engineer_performance": engineer_stats,
    })
