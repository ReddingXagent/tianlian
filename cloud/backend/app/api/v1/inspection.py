"""
巡检运维管理 API
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Literal, Optional, List
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from app.core.database import get_db
from app.core.iso_utils import parse_iso8601_or_400
from app.models.inspection import (
    InspectionTask, InspectionPlan, TaskStatus, PlanStatus, PlanCycle, PlanTarget,
    InspectionTemplate, InspectionResult,
    TEMPLATE_STATUS_VALUES, RESULT_STATUS_VALUES,
)
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import (
    is_platform_admin, team_scope, assert_team_access, assert_station_team_access,
)
from app.models.station import Station
from app.models.user import User
from app.core.response import success_response, paginated_response, action_response
from pydantic import BaseModel, Field

router = APIRouter(dependencies=[Depends(require_write_permission("workorder:edit"))])


# ─── Pydantic Schemas ───

class PlanCreate(BaseModel):
    name: str = Field(..., max_length=200)
    cycle: str = "weekly"
    target: str = "all"
    assignee: Optional[str] = None
    assignee_id: Optional[int] = None
    team_id: Optional[int] = None
    description: Optional[str] = None
    config: Optional[dict] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    cycle: Optional[str] = None
    target: Optional[str] = None
    assignee: Optional[str] = None
    assignee_id: Optional[int] = None
    team_id: Optional[int] = None
    description: Optional[str] = None
    config: Optional[dict] = None


class TaskCreate(BaseModel):
    name: str = Field(..., max_length=200)
    plan_id: Optional[int] = None
    station_id: Optional[int] = None
    station_name: Optional[str] = Field(None, max_length=200)
    assignee: Optional[str] = None
    assignee_id: Optional[int] = None
    total_items: int = 0
    scheduled_date: Optional[str] = None
    description: Optional[str] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    status: Optional[Literal["scheduled", "in_progress", "completed", "cancelled"]] = None
    assignee: Optional[str] = None
    assignee_id: Optional[int] = None
    total_items: Optional[int] = None
    completed_items: Optional[int] = None
    actual_date: Optional[str] = None
    description: Optional[str] = None
    result: Optional[dict] = None
    remark: Optional[str] = Field(None, max_length=500)


# ─── 巡检模板 / 结果 Schemas ───

class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    items: Optional[List[dict]] = None           # 透传 [{name, type, standard_value, unit}]
    device_types: Optional[List[str]] = None      # spec 字段（数组）
    target: Optional[str] = None                  # 前端单选 → 桥接 device_types
    status: Optional[Literal["active", "inactive"]] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    items: Optional[List[dict]] = None
    device_types: Optional[List[str]] = None
    target: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


class ResultItemIn(BaseModel):
    item_name: str
    item_value: Optional[str] = None
    value: Optional[str] = None                   # 前端字段 → 桥接 item_value
    result: Optional[str] = "normal"
    abnormal_desc: Optional[str] = None
    photo_url: Optional[str] = None
    recorded_at: Optional[str] = None


class ResultCreate(BaseModel):
    results: List[ResultItemIn]


# ─── 辅助函数 ───

def plan_to_dict(plan: InspectionPlan) -> dict:
    """Plan ORM → dict"""
    task_count = len(plan.tasks) if plan.tasks else 0
    return {
        "id": plan.id,
        "name": plan.name,
        "cycle": plan.cycle.value if isinstance(plan.cycle, PlanCycle) else plan.cycle,
        "target": plan.target.value if isinstance(plan.target, PlanTarget) else plan.target,
        "assignee": plan.assignee,
        "assignee_id": plan.assignee_id,
        "team_id": plan.team_id,
        "status": plan.status.value if isinstance(plan.status, PlanStatus) else plan.status,
        "next_execute": plan.next_execute.isoformat() if plan.next_execute else None,
        "last_execute": plan.last_execute.isoformat() if plan.last_execute else None,
        "description": plan.description,
        "config": plan.config,
        "task_count": task_count,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def task_to_dict(task: InspectionTask) -> dict:
    """Task ORM → dict"""
    progress_pct = round((task.completed_items / task.total_items) * 100, 1) if task.total_items > 0 else 0
    return {
        "id": task.id,
        "name": task.name,
        "plan_id": task.plan_id,
        "plan_name": task.plan.name if task.plan else None,
        "station_id": task.station_id,
        "station_name": task.station_name,
        "assignee": task.assignee,
        "assignee_id": task.assignee_id,
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
        "total_items": task.total_items,
        "completed_items": task.completed_items,
        "progress": progress_pct,
        "scheduled_date": task.scheduled_date.isoformat() if task.scheduled_date else None,
        "actual_date": task.actual_date.isoformat() if task.actual_date else None,
        "description": task.description,
        "result": task.result,
        "remark": task.remark,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _task_team_id(db: Session, task: InspectionTask) -> Optional[int]:
    """任务归属 team 解析（卡 0ff95dca — IDOR 补防）：优先 task.station_id→
    Station.team_id；无 station 回退 task.plan→team。均无 → None（配合
    assert_team_access 的「无归属即拒」语义，团队级用户不可访问无主任务）。
    """
    if task.station_id:
        team_id = db.query(Station.team_id).filter(Station.id == task.station_id).scalar()
        if team_id is not None:
            return team_id
    if task.plan_id:
        team_id = db.query(InspectionPlan.team_id).filter(InspectionPlan.id == task.plan_id).scalar()
        return team_id
    return None


def _assert_task_team_access(db: Session, task: InspectionTask, user: User) -> None:
    """任务归属校验（卡 0ff95dca）：admin 豁免；团队级跨团队 → 404（不泄露存在）。"""
    assert_team_access(user, _task_team_id(db, task))


def template_to_dict(t: InspectionTemplate) -> dict:
    """Template ORM → dict。target 取 device_types 首元素（前端单选桥接）。"""
    device_types = t.device_types or []
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "items": t.items or [],
        "item_count": len(t.items or []),
        "device_types": device_types,
        "target": device_types[0] if device_types else None,
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def result_to_dict(r: InspectionResult) -> dict:
    """Result ORM → dict。回传 item_value + value 别名（兼容前端字段名）。"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "item_name": r.item_name,
        "item_value": r.item_value,
        "value": r.item_value,
        "result": r.result,
        "abnormal_desc": r.abnormal_desc,
        "photo_url": r.photo_url,
        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
    }


# ─── 计划 API ───

@router.get("/plans", tags=["巡检运维"])
def list_plans(
    status: Optional[str] = None,
    team_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取巡检计划列表

    任务卡 708350b3: team_id 服务端强制——团队级用户仅见本 team 计划
    （query team_id 被忽略）；admin/平台级可按 team_id 筛选或看全部。
    """
    query = db.query(InspectionPlan)

    scope = team_scope(current_user)
    if scope is not None:
        query = query.filter(InspectionPlan.team_id == scope)
    elif team_id is not None:
        query = query.filter(InspectionPlan.team_id == team_id)
    if status:
        query = query.filter(InspectionPlan.status == status)

    total = query.count()
    items = query.order_by(InspectionPlan.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response([plan_to_dict(p) for p in items], total, page, page_size)


@router.get("/plans/{plan_id}", tags=["巡检运维"])
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取巡检计划详情"""
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    assert_team_access(current_user, plan.team_id)

    result = plan_to_dict(plan)
    result["tasks"] = [task_to_dict(t) for t in (plan.tasks or [])]
    return success_response(result)


@router.post("/plans", tags=["巡检运维"])
def create_plan(
    data: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建巡检计划

    任务卡 708350b3: team_id 服务端强制——admin 可指定任意团队；
    团队级用户创建的计划归属其本人 team（body team_id 被忽略）。
    """
    # 校验 cycle
    try:
        cycle_enum = PlanCycle(data.cycle)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的周期: {data.cycle}")

    # 校验 target
    try:
        target_enum = PlanTarget(data.target)
    except ValueError:
        target_enum = PlanTarget.ALL

    # team_id 服务端强制：admin 用 body 指定，团队级用户锁本人 team
    team_id = data.team_id if is_platform_admin(current_user) else current_user.team_id

    new_plan = InspectionPlan(
        name=data.name,
        cycle=cycle_enum,
        target=target_enum,
        assignee=data.assignee,
        assignee_id=data.assignee_id,
        team_id=team_id,
        description=data.description,
        config=data.config,
        status=PlanStatus.ACTIVE,
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return success_response(plan_to_dict(new_plan), message="计划创建成功")


@router.put("/plans/{plan_id}", tags=["巡检运维"])
def update_plan(
    plan_id: int,
    data: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新巡检计划"""
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    assert_team_access(current_user, plan.team_id)

    update_data = data.model_dump(exclude_unset=True)
    # 任务卡 708350b3: team_id 改归属仅 admin 可为
    if "team_id" in update_data and not is_platform_admin(current_user):
        update_data.pop("team_id")

    # 处理枚举字段
    if "cycle" in update_data:
        try:
            update_data["cycle"] = PlanCycle(update_data["cycle"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的周期: {update_data['cycle']}")
    if "target" in update_data:
        try:
            update_data["target"] = PlanTarget(update_data["target"])
        except ValueError:
            pass

    for key, value in update_data.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return success_response(plan_to_dict(plan), message="计划已更新")


@router.delete("/plans/{plan_id}", tags=["巡检运维"])
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除巡检计划"""
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    assert_team_access(current_user, plan.team_id)

    db.delete(plan)
    db.commit()
    return action_response(success=True, message=f"计划 {plan_id} 已删除")


@router.put("/plans/{plan_id}/status", tags=["巡检运维"])
def toggle_plan_status(
    plan_id: int,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换计划状态（激活/暂停）"""
    plan = db.query(InspectionPlan).filter(InspectionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    assert_team_access(current_user, plan.team_id)

    try:
        new_status = PlanStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态: {status}")

    plan.status = new_status
    db.commit()
    db.refresh(plan)
    return success_response(plan_to_dict(plan), message=f"计划已{'激活' if status == 'active' else '暂停'}")


# ─── 任务 API ───

@router.get("/tasks", tags=["巡检运维"])
def list_tasks(
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
    station_id: Optional[int] = None,
    assignee: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取巡检任务列表

    卡 0ff95dca: team 服务端强制——团队级用户仅见本 team 任务（task→station
    或 plan 推导归属）；admin/平台级可看全部。无归属任务（无 station 且无
    plan）平台级可见，团队级不可见。
    """
    query = db.query(InspectionTask)

    scope = team_scope(current_user)
    if scope is not None:
        query = query.join(Station, Station.id == InspectionTask.station_id, isouter=True).join(
            InspectionPlan, InspectionPlan.id == InspectionTask.plan_id, isouter=True
        ).filter(
            (Station.team_id == scope) | (InspectionPlan.team_id == scope)
        )

    if status:
        query = query.filter(InspectionTask.status == status)
    if plan_id:
        query = query.filter(InspectionTask.plan_id == plan_id)
    if station_id:
        query = query.filter(InspectionTask.station_id == station_id)
    if assignee:
        query = query.filter(InspectionTask.assignee.ilike(f"%{assignee}%"))
    if keyword:
        query = query.filter(
            InspectionTask.name.ilike(f"%{keyword}%") |
            InspectionTask.station_name.ilike(f"%{keyword}%")
        )

    total = query.count()
    items = query.order_by(InspectionTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response([task_to_dict(t) for t in items], total, page, page_size)


@router.get("/tasks/{task_id}", tags=["巡检运维"])
def get_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """获取巡检任务详情（卡 0ff95dca: 跨团队 → 404）"""
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_task_team_access(db, task, current_user)
    return success_response(task_to_dict(task))


@router.post("/tasks", tags=["巡检运维"])
def create_task(data: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """创建巡检任务（卡 0ff95dca: station_id 须归属本人 team，admin 豁免）"""
    # station 归属校验：团队级用户引用他 team 站点建任务 → 404（不泄露存在）
    if data.station_id is not None:
        assert_station_team_access(db, data.station_id, current_user)
    # plan 归属校验：引用他 team 计划建任务同样 404
    if data.plan_id is not None:
        plan = db.query(InspectionPlan).filter(InspectionPlan.id == data.plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail="计划不存在")
        assert_team_access(current_user, plan.team_id)

    scheduled = None
    if data.scheduled_date:
        try:
            scheduled = date.fromisoformat(data.scheduled_date)
        except ValueError:
            pass

    new_task = InspectionTask(
        name=data.name,
        plan_id=data.plan_id,
        station_id=data.station_id,
        station_name=data.station_name,
        assignee=data.assignee,
        assignee_id=data.assignee_id,
        total_items=data.total_items,
        scheduled_date=scheduled,
        description=data.description,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return success_response(task_to_dict(new_task), message="任务创建成功")


@router.put("/tasks/{task_id}", tags=["巡检运维"])
def update_task(task_id: int, data: TaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """更新巡检任务（卡 0ff95dca: 跨团队 → 404）"""
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_task_team_access(db, task, current_user)

    update_data = data.model_dump(exclude_unset=True)

    # 处理状态枚举
    if "status" in update_data:
        try:
            update_data["status"] = TaskStatus(update_data["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的任务状态: {update_data['status']}")

    # 处理日期
    if "scheduled_date" in update_data and update_data["scheduled_date"]:
        try:
            update_data["scheduled_date"] = date.fromisoformat(update_data["scheduled_date"])
        except ValueError:
            update_data.pop("scheduled_date", None)

    if "actual_date" in update_data and update_data["actual_date"]:
        try:
            update_data["actual_date"] = date.fromisoformat(update_data["actual_date"])
        except ValueError:
            update_data.pop("actual_date", None)

    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return success_response(task_to_dict(task), message="任务已更新")


@router.delete("/tasks/{task_id}", tags=["巡检运维"])
def delete_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """删除巡检任务（卡 0ff95dca: 跨团队 → 404）"""
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_task_team_access(db, task, current_user)

    db.delete(task)
    db.commit()
    return action_response(success=True, message=f"任务 {task_id} 已删除")


# ─── 统计 API ───

@router.get("/stats", tags=["巡检运维"])
def get_inspection_stats(db: Session = Depends(get_db)):
    """巡检统计概览"""
    # 任务统计
    total_tasks = db.query(sqlfunc.count(InspectionTask.id)).scalar() or 0
    active_tasks = db.query(sqlfunc.count(InspectionTask.id)).filter(
        InspectionTask.status.in_([TaskStatus.SCHEDULED, TaskStatus.IN_PROGRESS])
    ).scalar() or 0
    completed_tasks = db.query(sqlfunc.count(InspectionTask.id)).filter(
        InspectionTask.status == TaskStatus.COMPLETED
    ).scalar() or 0

    # 按状态分布（一次 GROUP BY 取代逐状态 COUNT）
    status_rows = db.query(
        InspectionTask.status, sqlfunc.count(InspectionTask.id)
    ).group_by(InspectionTask.status).all()
    status_counts: dict[str, int] = {}
    for s, c in status_rows:
        key = s.value if hasattr(s, "value") else str(s)
        status_counts[key] = c
    status_distribution = {}
    for s in TaskStatus:
        status_distribution[s.value] = status_counts.get(s.value, 0)

    # 计划统计
    total_plans = db.query(sqlfunc.count(InspectionPlan.id)).scalar() or 0
    active_plans = db.query(sqlfunc.count(InspectionPlan.id)).filter(
        InspectionPlan.status == PlanStatus.ACTIVE
    ).scalar() or 0

    # 完成率
    completion_rate = round((completed_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0

    return success_response({
        "tasks": {
            "total": total_tasks,
            "active": active_tasks,
            "completed": completed_tasks,
            "completion_rate": completion_rate,
            "by_status": status_distribution,
        },
        "plans": {
            "total": total_plans,
            "active": active_plans,
        },
    })


# ─── 巡检模板 API（spec 2.5）───

@router.get("/templates", tags=["巡检运维"])
def list_templates(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取巡检模板列表（分页 + status 筛选）"""
    query = db.query(InspectionTemplate)

    if status:
        query = query.filter(InspectionTemplate.status == status)

    total = query.count()
    items = query.order_by(InspectionTemplate.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response([template_to_dict(t) for t in items], total, page, page_size)


@router.get("/templates/{template_id}", tags=["巡检运维"])
def get_template(template_id: int, db: Session = Depends(get_db)):
    """获取巡检模板详情"""
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")
    return success_response(template_to_dict(t))


@router.post("/templates", tags=["巡检运维"])
def create_template(data: TemplateCreate, db: Session = Depends(get_db)):
    """创建巡检模板"""
    status = data.status or "active"
    if status not in TEMPLATE_STATUS_VALUES:
        raise HTTPException(status_code=400, detail=f"无效的状态: {status}")

    # 前端单选 target 桥接为 device_types 数组；显式 device_types 优先
    if data.device_types is not None:
        device_types = data.device_types
    elif data.target:
        device_types = [data.target]
    else:
        device_types = []

    new_template = InspectionTemplate(
        name=data.name,
        description=data.description,
        items=data.items,
        device_types=device_types,
        status=status,
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return success_response(template_to_dict(new_template), message="模板创建成功")


@router.put("/templates/{template_id}", tags=["巡检运维"])
def update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db)):
    """更新巡检模板"""
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")

    update_data = data.model_dump(exclude_unset=True)

    if "status" in update_data and update_data["status"] is not None:
        if update_data["status"] not in TEMPLATE_STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"无效的状态: {update_data['status']}")

    # target 桥接：device_types 未提供且 target 提供时，用 target 重置 device_types
    if "device_types" not in update_data:
        if "target" in update_data:
            tgt = update_data.pop("target")
            if tgt:
                update_data["device_types"] = [tgt]
    else:
        update_data.pop("target", None)  # device_types 优先，丢弃 target

    for key, value in update_data.items():
        setattr(t, key, value)

    db.commit()
    db.refresh(t)
    return success_response(template_to_dict(t), message="模板已更新")


@router.delete("/templates/{template_id}", tags=["巡检运维"])
def delete_template(template_id: int, db: Session = Depends(get_db)):
    """删除巡检模板"""
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")

    db.delete(t)
    db.commit()
    return action_response(success=True, message=f"模板 {template_id} 已删除")


# ─── 巡检结果 API（spec 2.5，按任务录入）───

@router.get("/tasks/{task_id}/results", tags=["巡检运维"])
def list_results(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """查询任务的巡检结果（卡 0ff95dca: 跨团队 → 404）"""
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_task_team_access(db, task, current_user)

    results = (
        db.query(InspectionResult)
        .filter(InspectionResult.task_id == task_id)
        .order_by(InspectionResult.id.asc())
        .all()
    )
    return success_response([result_to_dict(r) for r in results])


@router.post("/tasks/{task_id}/results", tags=["巡检运维"])
def create_results(task_id: int, data: ResultCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """批量录入巡检结果（卡 0ff95dca: 跨团队 → 404）"""
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_task_team_access(db, task, current_user)

    if not data.results:
        raise HTTPException(status_code=400, detail="巡检结果不能为空")

    now = datetime.now(timezone.utc)
    created = []
    for item in data.results:
        res_value = item.result or "normal"
        if res_value not in RESULT_STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"无效的结果状态: {res_value}")

        # 前端 value 桥接 item_value
        value = item.item_value if item.item_value is not None else item.value

        recorded_at = now
        if item.recorded_at:
            # py3.9 兼容 'Z' + 坏值显式 400 (卡 c4cbcbf1): 旧实现 except:pass 静默
            # 改用 server now → 客户端 Z/坏值输入时间丢失。
            recorded_at = parse_iso8601_or_400(item.recorded_at, "recorded_at 格式无效，需 ISO 8601")

        r = InspectionResult(
            task_id=task_id,
            item_name=item.item_name,
            item_value=value,
            result=res_value,
            abnormal_desc=item.abnormal_desc,
            photo_url=item.photo_url,
            recorded_at=recorded_at,
        )
        db.add(r)
        created.append(r)

    db.commit()
    for r in created:
        db.refresh(r)
    return success_response([result_to_dict(r) for r in created], message=f"已录入 {len(created)} 条巡检结果")