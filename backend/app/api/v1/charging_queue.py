"""
充电排序队列 API

功能:
- GET    /api/v1/fleet/charging/queue                —— 实时队列
- POST   /api/v1/fleet/charging/queue/enqueue         —— 入队
- DELETE /api/v1/fleet/charging/queue/{queue_id}/dequeue —— 离队
- PATCH  /api/v1/fleet/charging/queue/{queue_id}/priority —— 优先级调整
- GET    /api/v1/fleet/charging/rules                  —— 规则列表
- POST   /api/v1/fleet/charging/rules                  —— 创建规则
- PUT    /api/v1/fleet/charging/rules/{rule_id}        —— 更新规则
- DELETE /api/v1/fleet/charging/rules/{rule_id}        —— 删除规则
"""
from datetime import datetime, timezone
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.response import success_response, paginated_response, action_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import (
    is_platform_admin,
    assert_station_team_access,
    assert_enterprise_team_access,
)
from app.models.charging_queue import ChargingQueue, ChargingQueueRule, ChargingQueueStatus
from app.models.station import Station
from app.models.enterprise import Enterprise
from app.models.user import User
from app.services.charging_queue_service import (
    sort_queue,
    get_active_rule,
    recalculate_priorities,
    DEFAULT_PRIORITY_CRITERIA,
)

router = APIRouter(dependencies=[Depends(require_write_permission("charging:manage"))])


# ========== Schemas ==========

class EnqueueRequest(BaseModel):
    station_id: int
    vehicle_id: int
    enterprise_id: Optional[int] = 0
    required_energy_kwh: float = 0.0
    target_soc: float = 0.8
    current_soc: Optional[float] = 0.0
    priority: int = 100


class PriorityUpdateRequest(BaseModel):
    priority: int


class RuleCreateRequest(BaseModel):
    enterprise_id: int = 0
    station_id: Optional[int] = None
    rule_name: str = Field(..., max_length=100)
    priority_criteria: Optional[List[Any]] = None
    max_queue_length: int = 100
    enable: bool = True


class RuleUpdateRequest(BaseModel):
    rule_name: Optional[str] = None
    priority_criteria: Optional[List[Any]] = None
    max_queue_length: Optional[int] = None
    enable: Optional[bool] = None


# ========== Helpers ==========

def _entry_to_dict(e: ChargingQueue) -> dict:
    return {
        "id": e.id,
        "station_id": e.station_id,
        "vehicle_id": e.vehicle_id,
        "enterprise_id": e.enterprise_id,
        "rule_id": e.rule_id,
        "priority": e.priority,
        "arrival_time": e.arrival_time.isoformat() if e.arrival_time else None,
        "estimated_wait_minutes": e.estimated_wait_minutes,
        "required_energy_kwh": e.required_energy_kwh,
        "target_soc": e.target_soc,
        "current_soc": e.current_soc,
        "status": e.status,
        "assigned_device_id": e.assigned_device_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _rule_to_dict(r: ChargingQueueRule) -> dict:
    return {
        "id": r.id,
        "enterprise_id": r.enterprise_id,
        "station_id": r.station_id,
        "rule_name": r.rule_name,
        "priority_criteria": r.priority_criteria,
        "max_queue_length": r.max_queue_length,
        "enable": r.enable,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _assert_rule_team_access(db: Session, rule: ChargingQueueRule, user: User) -> None:
    """规则归属校验（任务卡 e1f0e6d5）：优先 station→team，station 缺失时按 enterprise→team；
    admin 豁免；越权 → 404（不泄露存在）。

    ChargingQueueRule 无 team_id 列：station_id 非空时归属站点，否则归属 enterprise。
    供 update/delete 复用，避免两处重复实现。
    """
    if is_platform_admin(user):
        return
    if rule.station_id is not None:
        assert_station_team_access(db, rule.station_id, user)
    else:
        assert_enterprise_team_access(db, rule.enterprise_id, user)


# ========== Queue Endpoints ==========

@router.get("/charging/queue", summary="实时充电队列")
def get_charging_queue(
    station_id: int = Query(..., description="电站ID"),
    status: Optional[str] = Query(None, description="状态过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取实时充电队列 (按优先级排序)"""
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可查本 team 站点队列；越权 → 404。
    assert_station_team_access(db, station_id, user)
    query = db.query(ChargingQueue).filter(ChargingQueue.station_id == station_id)
    if status:
        query = query.filter(ChargingQueue.status == status)
    else:
        query = query.filter(ChargingQueue.status == ChargingQueueStatus.WAITING.value)

    entries = query.all()

    # 获取排序规则
    first_entry = entries[0] if entries else None
    enterprise_id = first_entry.enterprise_id if first_entry else 0
    rule = get_active_rule(db, enterprise_id=enterprise_id, station_id=station_id)
    criteria = rule.priority_criteria if rule else DEFAULT_PRIORITY_CRITERIA

    sorted_entries = sort_queue(entries, criteria)
    total = len(sorted_entries)
    start = (page - 1) * page_size
    paged_entries = sorted_entries[start:start + page_size]
    return paginated_response([_entry_to_dict(e) for e in paged_entries], total, page, page_size)


@router.post("/charging/queue/enqueue", summary="车辆入队")
def enqueue_vehicle(
    data: EnqueueRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """车辆加入充电队列"""
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可入队本 team 站点；越权 → 404。
    assert_station_team_access(db, data.station_id, user)
    # 检查是否已在队列中
    existing = db.query(ChargingQueue).filter(
        ChargingQueue.station_id == data.station_id,
        ChargingQueue.vehicle_id == data.vehicle_id,
        ChargingQueue.status.in_([ChargingQueueStatus.WAITING.value, ChargingQueueStatus.CHARGING.value]),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该车辆已在队列中")

    # 检查队列长度限制
    rule = get_active_rule(db, enterprise_id=data.enterprise_id or 0, station_id=data.station_id)
    if rule:
        current_count = db.query(ChargingQueue).filter(
            ChargingQueue.station_id == data.station_id,
            ChargingQueue.status == ChargingQueueStatus.WAITING.value,
        ).count()
        if current_count >= rule.max_queue_length:
            raise HTTPException(status_code=429, detail=f"队列已满 (最大 {rule.max_queue_length})")

    entry = ChargingQueue(
        station_id=data.station_id,
        vehicle_id=data.vehicle_id,
        enterprise_id=data.enterprise_id or 0,
        rule_id=rule.id if rule else None,
        priority=data.priority,
        arrival_time=datetime.now(timezone.utc),
        estimated_wait_minutes=0,
        required_energy_kwh=data.required_energy_kwh,
        target_soc=data.target_soc,
        current_soc=data.current_soc,
        status=ChargingQueueStatus.WAITING.value,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # 重算等待时间
    criteria = rule.priority_criteria if rule else DEFAULT_PRIORITY_CRITERIA
    recalculate_priorities(db, data.station_id, criteria)
    db.commit()
    db.refresh(entry)

    return success_response(_entry_to_dict(entry), message="入队成功")


@router.delete("/charging/queue/{queue_id}/dequeue", summary="车辆离队")
def dequeue_vehicle(
    queue_id: int,
    reason: str = Query("manual", description="离队原因"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """车辆离开充电队列"""
    entry = db.query(ChargingQueue).filter(ChargingQueue.id == queue_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="队列条目不存在")
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可操作本 team 站点的队列条目；越权 → 404。
    assert_station_team_access(db, entry.station_id, user)

    if entry.status in (ChargingQueueStatus.CANCELLED.value, ChargingQueueStatus.COMPLETED.value):
        raise HTTPException(status_code=400, detail="该条目已结束")

    if reason == "completed":
        entry.status = ChargingQueueStatus.COMPLETED.value
    else:
        entry.status = ChargingQueueStatus.CANCELLED.value
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()

    # 重算剩余队列
    rule = get_active_rule(db, enterprise_id=entry.enterprise_id or 0, station_id=entry.station_id)
    criteria = rule.priority_criteria if rule else DEFAULT_PRIORITY_CRITERIA
    recalculate_priorities(db, entry.station_id, criteria)
    db.commit()

    return action_response(True, message=f"离队成功 (原因: {reason})")


@router.patch("/charging/queue/{queue_id}/priority", summary="优先级调整")
def update_priority(
    queue_id: int,
    data: PriorityUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """调整队列条目的优先级"""
    entry = db.query(ChargingQueue).filter(ChargingQueue.id == queue_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="队列条目不存在")
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可操作本 team 站点的队列条目；越权 → 404。
    assert_station_team_access(db, entry.station_id, user)

    if entry.status != ChargingQueueStatus.WAITING.value:
        raise HTTPException(status_code=400, detail="仅等待中的条目可调整优先级")

    entry.priority = data.priority
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()

    # 重算排序
    rule = get_active_rule(db, enterprise_id=entry.enterprise_id or 0, station_id=entry.station_id)
    criteria = rule.priority_criteria if rule else DEFAULT_PRIORITY_CRITERIA
    recalculate_priorities(db, entry.station_id, criteria)
    db.commit()
    db.refresh(entry)

    return success_response(_entry_to_dict(entry), message="优先级调整成功")


# ========== Rule CRUD Endpoints ==========

@router.get("/charging/rules", summary="充电排序规则列表")
def list_rules(
    enterprise_id: Optional[int] = Query(None, description="企业ID过滤"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取充电排序规则列表"""
    query = db.query(ChargingQueueRule)
    if enterprise_id is not None:
        query = query.filter(ChargingQueueRule.enterprise_id == enterprise_id)
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅本 team 站点/企业派生的规则。
    if not is_platform_admin(user):
        own_stations = db.query(Station.id).filter(Station.team_id == user.team_id)
        own_enterprises = db.query(Enterprise.id).filter(Enterprise.owner_team_id == user.team_id)
        query = query.filter(or_(
            ChargingQueueRule.station_id.in_(own_stations),
            ChargingQueueRule.enterprise_id.in_(own_enterprises),
        ))

    rules = query.order_by(ChargingQueueRule.id.desc()).all()
    return success_response([_rule_to_dict(r) for r in rules])


@router.post("/charging/rules", summary="创建充电排序规则")
def create_rule(
    data: RuleCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建充电排序规则"""
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可为本 team 创建规则；
    # 指定站点按 station→team 校验，全局规则按 enterprise→team 校验；越权 → 404。
    if not is_platform_admin(user):
        if data.station_id is not None:
            assert_station_team_access(db, data.station_id, user)
        else:
            assert_enterprise_team_access(db, data.enterprise_id, user)
    criteria = data.priority_criteria if data.priority_criteria else list(DEFAULT_PRIORITY_CRITERIA)

    rule = ChargingQueueRule(
        enterprise_id=data.enterprise_id,
        station_id=data.station_id,
        rule_name=data.rule_name,
        priority_criteria=criteria,
        max_queue_length=data.max_queue_length,
        enable=data.enable,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    return success_response(_rule_to_dict(rule), message="规则创建成功")


@router.put("/charging/rules/{rule_id}", summary="更新充电排序规则")
def update_rule(
    rule_id: int,
    data: RuleUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新充电排序规则"""
    rule = db.query(ChargingQueueRule).filter(ChargingQueueRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可改本 team 规则；越权 → 404。
    _assert_rule_team_access(db, rule, user)

    if data.rule_name is not None:
        rule.rule_name = data.rule_name
    if data.priority_criteria is not None:
        rule.priority_criteria = data.priority_criteria
    if data.max_queue_length is not None:
        rule.max_queue_length = data.max_queue_length
    if data.enable is not None:
        rule.enable = data.enable
    rule.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(rule)

    return success_response(_rule_to_dict(rule), message="规则更新成功")


@router.delete("/charging/rules/{rule_id}", summary="删除充电排序规则")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除充电排序规则"""
    rule = db.query(ChargingQueueRule).filter(ChargingQueueRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    # team scoping（任务卡 e1f0e6d5）：非 admin 仅可删本 team 规则；越权 → 404。
    _assert_rule_team_access(db, rule, user)

    db.delete(rule)
    db.commit()

    return action_response(True, message="规则删除成功")
