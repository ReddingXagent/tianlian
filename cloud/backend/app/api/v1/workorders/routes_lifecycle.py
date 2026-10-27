"""工单生命周期端点 — CRUD / 统计 / 日志 (从原 workorders.py 拆出, 卡 1ed83abf)。

team scoping (任务卡 ed509541) 原样保留。路由注册顺序与原文件一致:
``""`` → ``/stats`` → ``/{workorder_id}`` (静态先于参数, 避免 /stats 被 {id} 抢先匹配)。
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import is_platform_admin, resolve_team_filter
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import action_response, paginated_response, success_response
from app.models.device import Device
from app.models.station import Station
from app.models.user import User
from app.models.workorder import (
    WorkOrder,
    WorkOrderLevel,
    WorkOrderLog,
    WorkOrderStatus,
    WorkOrderType,
)
from app.services.audit_service import audit_service

from .helpers import _broadcast_wo, _check_workorder_team
from .router import router
from .schemas import WorkOrderCreate, WorkOrderUpdate


@router.get("")
def list_workorders(
    status: Optional[str] = None,
    level: Optional[str] = None,
    type: Optional[str] = None,
    dispatch_type: Optional[str] = None,
    source: Optional[str] = None,
    team_id: Optional[int] = Query(None, description="按团队过滤（卡 2285f54a：admin 可指定任意团队；团队级用户仅限本团队，他团队 403）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取工单列表。

    team scoping（任务卡 ed509541）：非 admin 仅返回本 team 工单（经 station→team）。
    可选 ``team_id`` 查询参数（卡 2285f54a）：admin 可按任意团队过滤，团队级
    用户仅允许显式指定本团队——供 Tenants TeamDataView 工单 Tab 使用。
    移除原 ``@cached`` —— 其 key 不含 user.team_id，跨用户同 URL 会命中同一缓存串数据。
    """
    query = db.query(WorkOrder)
    scope_team = resolve_team_filter(db, user, team_id)
    if scope_team is not None:
        query = query.join(Station, WorkOrder.station_id == Station.id) \
                     .filter(Station.team_id == scope_team)
    elif not is_platform_admin(user):
        query = query.join(Station, WorkOrder.station_id == Station.id) \
                     .filter(Station.team_id == user.team_id)
    if status:
        query = query.filter(WorkOrder.status == status)
    if level:
        query = query.filter(WorkOrder.level == level)
    if type:
        query = query.filter(WorkOrder.type == type)
    if dispatch_type:
        query = query.filter(WorkOrder.dispatch_type == dispatch_type)
    if source:
        query = query.filter(WorkOrder.source == source)

    total = query.count()
    items = query.order_by(WorkOrder.create_time.desc()).offset((page-1)*page_size).limit(page_size).all()

    # 序列化为字典
    result_items = []
    for wo in items:
        wo_dict = {
            'id': wo.id,
            'fault_desc': wo.fault_desc,
            'type': wo.type.value if wo.type else 'repair',
            'level': wo.level.value if wo.level else 'warning',
            'status': wo.status.value if wo.status else 'pending',
            'station_id': wo.station_id,
            'device_id': wo.device_id,
            'assignee_id': wo.assignee_id,
            'creator_id': wo.creator_id,
            'dispatch_type': wo.dispatch_type,
            'source': wo.source,
            'create_time': wo.create_time.isoformat() if wo.create_time else None,
            'accept_time': wo.accept_time.isoformat() if wo.accept_time else None,
            'finish_time': wo.finish_time.isoformat() if wo.finish_time else None,
            'solution': wo.solution,
        }
        result_items.append(wo_dict)

    return paginated_response(result_items, total, page, page_size)


@router.get("/stats")
def workorder_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """工单统计：总数 + 状态/级别/类型分布，支持日期过滤与 group_by 分组。

    group_by: status(默认) / level / type / date(按天)
    team scoping（任务卡 ed509541）：非 admin 仅统计本 team 工单。
    """
    filters = []
    if start_date:
        filters.append(WorkOrder.create_time >= start_date)
    if end_date:
        filters.append(WorkOrder.create_time <= end_date)
    if not is_platform_admin(user):
        team_wo_ids = [
            wid for (wid,) in db.query(WorkOrder.id)
            .join(Station, WorkOrder.station_id == Station.id)
            .filter(Station.team_id == user.team_id).all()
        ]
        filters.append(WorkOrder.id.in_(team_wo_ids))

    total = db.query(WorkOrder).filter(*filters).count()

    def _dist(column):
        rows = db.query(column, func.count(WorkOrder.id)).filter(*filters).group_by(column).all()
        out = {}
        for value, cnt in rows:
            key = value.value if hasattr(value, "value") else (value if value is not None else "unknown")
            out[key] = cnt
        return out

    status_dist = _dist(WorkOrder.status)
    level_dist = _dist(WorkOrder.level)
    type_dist = _dist(WorkOrder.type)

    gb = (group_by or "status").lower()
    if gb == "level":
        groups = level_dist
    elif gb == "type":
        groups = type_dist
    elif gb in ("date", "day"):
        date_col = func.date(WorkOrder.create_time)
        rows = db.query(date_col, func.count(WorkOrder.id)).filter(*filters).group_by(date_col).order_by(date_col).all()
        groups = {str(d): c for d, c in rows if d is not None}
    else:
        groups = status_dist

    return success_response({
        "total": total,
        "status_distribution": status_dist,
        "level_distribution": level_dist,
        "type_distribution": type_dist,
        "groups": groups,
    })


@router.get("/{workorder_id}")
def get_workorder(workorder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取工单详情（team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    return success_response(order)


@router.post("")
def create_workorder(data: WorkOrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """创建工单。

    team scoping（任务卡 ed509541）：非 admin 必须指定本 team 站点（station_id），
    工单归属经 station 间接判定；指定他团站点/设备 → 404（不泄露存在）。
    admin 保留原逻辑（可不指定站点）。
    """
    # 生成工单号
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    wo_id = f"WO-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"

    if not is_platform_admin(user):
        if data.station_id is None:
            raise HTTPException(status_code=400, detail="需指定本团队站点 station_id")
        st = db.query(Station).filter(Station.id == data.station_id).first()
        if st is None or st.team_id is None or st.team_id != user.team_id:
            raise HTTPException(status_code=404, detail="站点不存在")
        if data.device_id is not None:
            dev_team = (
                db.query(Station.team_id)
                .join(Device, Device.station_id == Station.id)
                .filter(Device.id == data.device_id).first()
            )
            if dev_team is None or dev_team[0] is None or dev_team[0] != user.team_id:
                raise HTTPException(status_code=404, detail="设备不存在")

    order = WorkOrder(
        id=wo_id,
        fault_desc=data.fault_desc,
        type=WorkOrderType(data.type),
        level=WorkOrderLevel(data.level),
        station_id=data.station_id,
        device_id=data.device_id,
        status=WorkOrderStatus.PENDING,
        creator_id=user.id,
        source=data.source,
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        # FK违约(站点/设备/创建人不存在)兜底: 返4xx非500 (卡片 1236b769)
        db.rollback()
        raise HTTPException(status_code=400, detail="工单关联数据校验失败: 站点/设备不存在")
    db.refresh(order)

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="create", module="workorders",
            target_id=wo_id, target_desc=f"创建工单:{data.fault_desc[:50]}",
        )
    except Exception:
        pass

    _broadcast_wo(db, 'created', {'id': wo_id, 'fault_desc': data.fault_desc, 'status': 'pending'})
    return success_response(order)


@router.put("/{workorder_id}")
def update_workorder(workorder_id: str, data: WorkOrderUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新工单（team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)

    if data.fault_desc:
        order.fault_desc = data.fault_desc
    if data.level:
        order.level = WorkOrderLevel(data.level)
    if data.status:
        order.status = WorkOrderStatus(data.status)
        if data.status == 'accepted':
            order.accept_time = datetime.now(timezone.utc)
        elif data.status == 'completed':
            order.finish_time = datetime.now(timezone.utc)
    if data.assignee_id is not None:
        order.assignee_id = data.assignee_id
    if data.solution:
        order.solution = data.solution

    order.update_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"更新工单:{order.fault_desc[:30] if order.fault_desc else ''}",
        )
    except Exception:
        pass
    return success_response(order)


@router.delete("/{workorder_id}")
def delete_workorder(workorder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除工单（team scoping：跨团队 → 404）"""
    order = db.query(WorkOrder).filter(WorkOrder.id == workorder_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)

    # 卡 21205721: 服务层显式级联（checkin/support/spare_part/rating 子表
    # order_id NOT NULL, 裸 delete 在 PG 下 IntegrityError 500 / SQLite 下留孤儿）
    from app.services.fk_cascade import purge_workorder_children
    purge_workorder_children(db, workorder_id)

    db.delete(order)
    db.commit()
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="delete", module="workorders",
            target_id=workorder_id, target_desc=f"删除工单:{workorder_id}",
        )
    except Exception:
        pass
    return action_response(message='工单已删除')


@router.get("/{workorder_id}/logs")
def get_workorder_logs(workorder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取工单处理日志（team scoping：跨团队 → 404）"""
    _check_workorder_team(db, workorder_id, user)
    logs = db.query(WorkOrderLog).filter(WorkOrderLog.order_id == workorder_id).order_by(WorkOrderLog.created_at.desc()).all()
    return success_response({
        'items': [{
            'id': log.id,
            'action': log.action,
            'description': log.description or log.content,
            'created_at': log.created_at.isoformat() if log.created_at else None,
        } for log in logs],
        'total': len(logs),
    })
