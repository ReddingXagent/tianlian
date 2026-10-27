"""工单状态机 + 派单端点 — accept/start/complete/verify/reject/dispatch/transfer/urge
(从原 workorders.py 拆出, 卡 1ed83abf)。team scoping (任务卡 ed509541) 原样保留。

================================================================================
状态机全图与收口决策 (夜班: 状态机收口 + 行锁防双接单 + 自验收拦截)
================================================================================

WorkOrderStatus 同时定义了两套生命周期 (app/models/workorder.py L28-37):

  A套 (活跃工作流, 唯一有写入路径):
      pending → accepted → processing → pending_verify → completed
                  ↑__________驳回(reject)__________|
      转单(transfer) 把任意活跃态重置回 pending; 派单(dispatch) pending→processing。

  B套 (遗留/外部同步状态, 全库 grep 零写入路径 — 见本卡决策):
      assigned / in_progress / resolved / closed
      仅在 schemas._DONE_STATUSES(评价完成态)、dashboard/ops_dashboard(统计查询)
      被读取, 无任何 `order.status = B套` 的写入点。属早期未实现的生命周期残留,
      或预留给外部系统同步。当前代码全走 A套。

决策1 [死单收口·缺陷1]: B套状态不参与工作流流转。处于 B套 的工单对任何 workflow
  端点都是"死单" —— 过去虽因不满足 A套 前置状态而返回 400, 但消息泛("当前状态不
  允许X"), 等同静默卡住。现统一经 ``_reject_legacy_status`` 显式 400, 消息点名
  "遗留/外部同步状态(X) 不参与工作流, 请联系管理员迁移状态", 便于排查与人工干预。
  不删除 B套 枚举/dashboard 读取 (数据库可能已有这些状态的存量记录)。

决策2 [并发·双接单·缺陷2]: accept/verify/reject/dispatch/start/complete/transfer
  关键查询一律 ``.with_for_update()`` (生产 PostgreSQL/MySQL 真行锁, 串行化同一工单
  的并发流转; SQLite 下为 no-op, 与 enterprise_balance_service 先例一致)。其中
  accept(接单) 的双接单危害最大 (两工程师都以为自己持有工单), 故在 with_for_update
  之外, 另以**原子条件 UPDATE** (WHERE status=pending) 兜底: 仅当工单仍为 pending
  才落 accepted, 败者 rowcount=0 → 409。SQLite 写锁串行化 UPDATE 语句、WHERE 在获锁
  后对已提交数据重估, 使双接单在 SQLite 测试库上亦可诚实复现 (见
  tests/api/test_workorders_workflow.py 双接单并发用例)。verify/reject 并发为幂等
  (重复置 completed/processing), dispatch 并发末次 assignee 生效, with_for_update 已
  足够, 不再叠加条件 UPDATE。

决策3 [越权·自验收·缺陷3]: team scoping 之外补 actor 级校验。
  - accept: 已指派给特定工程师的工单 (转单后 pending+assignee_id) 仅该 assignee 可
    接; 未指派 (assignee_id 为空, 抢单池) 任何同团队工程师可接; 平台管理员豁免。
  - complete: 已指派工单仅 assignee 可完成 (管理员豁免, 支持代完成)。
  - verify: 完成人(assignee) 不得验收自己的工单 → 400 自验收拦截。未指派工单
    (assignee_id 为空, 如纯管理员流程) 不拦截; 平台管理员天然不与工程师 assignee
    同 id, 故无需额外豁免 (现有 admin 驱动的流转测试 assignee_id 恒为空, 不回归)。
================================================================================
"""
import json
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import is_platform_admin
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.response import success_response
from app.models.device import Device
from app.models.station import Station
from app.models.user import User, UserRole
from app.models.workorder import WorkOrder, WorkOrderLog, WorkOrderStatus
from app.services.audit_service import audit_service
from app.services.dispatch_engine import dispatch_engine

from .helpers import _broadcast_wo, _check_workorder_team
from .router import router
from .schemas import WorkOrderDispatch, WorkOrderTransfer, WorkOrderUrge


# B套遗留/外部同步状态: 全库 grep 确认零写入路径 (决策1)。处于这些状态的工单对工作流
# 是"死单", 各端点经 _reject_legacy_status 显式 400 (点名遗留状态, 不静默卡住)。
_LEGACY_STATUSES = frozenset({
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.RESOLVED,
    WorkOrderStatus.CLOSED,
})


def _reject_legacy_status(order: WorkOrder, action: str) -> None:
    """B套遗留状态显式拒绝 (缺陷1/决策1)。A套活跃状态放行, 交各端点原有状态校验。

    置于 team scoping (404 不泄露存在) 之后、A套状态校验之前: 跨团队先 404, 同团队
    命中遗留态再 400 点名。
    """
    if order.status in _LEGACY_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"工单处于遗留/外部同步状态({order.status.value}), 不参与工作流流转, "
                f"无法{action}; 请联系管理员迁移状态"
            ),
        )


def _load_workorder_for_update(db: Session, workorder_id: str) -> WorkOrder:
    """加载工单并取行锁 (缺陷2/决策2)。with_for_update 在 PG/MySQL 真锁行, SQLite no-op。"""
    return (
        db.query(WorkOrder)
        .filter(WorkOrder.id == workorder_id)
        .with_for_update()
        .first()
    )


@router.post("/{workorder_id}/dispatch")
def dispatch_workorder(workorder_id: str, data: WorkOrderDispatch = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """智能派单（team scoping：跨团队 → 404）"""
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "派单")

    if order.status != 'pending':
        raise HTTPException(status_code=400, detail="工单状态不允许派单")

    # 获取站点位置
    station = None
    if order.station_id:
        station = db.query(Station).filter(Station.id == order.station_id).first()

    # 获取所有可用工程师 (卡 3ad52033: 团队级用户仅本团队工程师池, admin 保持全量)
    engineer_q = db.query(User).filter(User.role == UserRole.ENGINEER)
    if not is_platform_admin(user):
        engineer_q = engineer_q.filter(User.team_id == user.team_id)
    engineers = engineer_q.all()

    if not engineers:
        raise HTTPException(status_code=404, detail="没有可用工程师")

    # 使用派单引擎计算最佳工程师
    device = None
    if order.device_id:
        from app.models.device import Device
        device = db.query(Device).filter(Device.id == order.device_id).first()

    workorder_data = {
        'device_type': device.type.value if device else 'unknown',
        'level': order.level.value,
        'required_parts': [],
    }

    station_loc = {'lat': station.lat, 'lon': station.lon} if station and station.lat else {'lat': 31.23, 'lon': 121.47}

    engineer_list = []
    for eng in engineers:
        # 解析工程师技能
        try:
            eng_skills = json.loads(eng.skills) if eng.skills else []
        except (json.JSONDecodeError, TypeError):
            eng_skills = []
        if not eng_skills:
            eng_skills = ['通用维修']  # 默认技能

        # 计算工程师绩效（卡 d9076d31：count 下推 SQL；avg_hours 分母只计双时间戳齐全样本）
        eng_total = db.query(func.count(WorkOrder.id)).filter(WorkOrder.assignee_id == eng.id).scalar() or 0
        eng_completed_n = db.query(func.count(WorkOrder.id)).filter(
            WorkOrder.assignee_id == eng.id, WorkOrder.status == 'completed'
        ).scalar() or 0
        completion_rate = eng_completed_n / eng_total * 100 if eng_total else 85
        # 仅拉 completed 的轻量时间戳元组，avg 分母=有效样本数
        avg_hours = 3.5
        if eng_completed_n:
            timestamps = db.query(WorkOrder.accept_time, WorkOrder.finish_time).filter(
                WorkOrder.assignee_id == eng.id, WorkOrder.status == 'completed'
            ).all()
            durations = [
                (ft - at).total_seconds() / 3600
                for at, ft in timestamps if at and ft
            ]
            avg_hours = round(sum(durations) / len(durations), 1) if durations else 3.5

        engineer_list.append({
            'id': eng.id,
            'name': eng.real_name or eng.username,
            'status': 'active',
            'location': {
                'lat': eng.latitude or (31.23 + eng.id * 0.01),
                'lon': eng.longitude or (121.47 + eng.id * 0.01),
            },
            'skills': eng_skills,
            'current_load': db.query(WorkOrder).filter(
                WorkOrder.assignee_id == eng.id,
                WorkOrder.status.in_(['pending', 'processing'])
            ).count(),
            'performance': {
                'completion_rate': round(completion_rate, 1),
                'satisfaction': 4.5,
                'avg_hours': avg_hours,
            },
            'parts': [],  # 备件从仓库系统获取
        })

    result = dispatch_engine.calculate_best_engineer(workorder_data, engineer_list, station_loc)

    if not result:
        raise HTTPException(status_code=404, detail="未找到合适工程师")

    # 自动派单
    order.assignee_id = result['engineer']['id']
    order.status = WorkOrderStatus.PROCESSING
    order.update_time = datetime.now(timezone.utc)
    db.commit()

    # 添加派单日志
    log = WorkOrderLog(
        order_id=order.id,
        action='dispatch',
        description=f"系统自动派单给工程师 {result['engineer']['name']} (评分：{result['total_score']:.1f})",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="dispatch", module="workorders",
            target_id=workorder_id,
            target_desc=f"派单给{result['engineer']['name']}",
        )
    except Exception:
        pass

    _broadcast_wo(db, 'dispatched', {'id': order.id, 'status': 'processing', 'engineer': result['engineer']['name']})
    return success_response({
        'engineer': result['engineer'],
        'score': result['total_score'],
        'details': result['score_details'],
    }, message='派单成功')


@router.post("/{workorder_id}/accept")
def accept_workorder(workorder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """接单 - 工程师接单（team scoping：跨团队 → 404）。

    并发安全(缺陷2/决策2): with_for_update 提供 PG/MySQL 行锁; 另以原子条件 UPDATE
    (WHERE status=pending) 兜底 SQLite(FOR UPDATE no-op), 败者 rowcount=0 → 409,
    跨后端保证"恰一个工程师接单成功"。
    """
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "接单")

    # 缺陷3/决策3: 已指派给特定工程师(如转单后 pending+assignee_id)仅该 assignee 可接;
    # 未指派(assignee_id 为空, 抢单池)任何同团队工程师可接; 平台管理员豁免。
    if (
        order.assignee_id is not None
        and not is_platform_admin(user)
        and user.id != order.assignee_id
    ):
        raise HTTPException(status_code=403, detail="该工单已指派给其他工程师, 您无权接单")

    if order.status != WorkOrderStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"工单当前状态不允许接单: {order.status.value}")

    # 原子条件 UPDATE: 跨后端(含 SQLite, FOR UPDATE no-op)防双接单 check-then-set 撕裂。
    # 仅当工单仍为 pending 才落 accepted; 并发败者匹配 0 行 → 409。
    # (WorkOrder 无 update_time 列, accept_time 为真实列; 故仅写 status+accept_time。)
    now = datetime.now(timezone.utc)
    updated = (
        db.query(WorkOrder)
        .filter(WorkOrder.id == workorder_id, WorkOrder.status == WorkOrderStatus.PENDING)
        .update(
            {
                WorkOrder.status: WorkOrderStatus.ACCEPTED,
                WorkOrder.accept_time: now,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        # 并发败者: 本事务读检查(pending)与 UPDATE 之间, 另一事务已把 pending → accepted。
        db.rollback()
        raise HTTPException(status_code=409, detail="工单刚被其他工程师接单, 请刷新后重试")
    db.commit()
    db.refresh(order)

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='accepted',
        description="工程师已接单",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"接单:工单{workorder_id}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'accepted', {'id': order.id, 'status': 'accepted'})
    return success_response({'status': order.status.value, 'accept_time': str(order.accept_time) if order.accept_time else None}, message='接单成功')


@router.post("/{workorder_id}/start")
def start_workorder(workorder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """开始处理 - 工程师开始处理工单（team scoping：跨团队 → 404）"""
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "开始处理")

    if order.status not in [WorkOrderStatus.ACCEPTED, WorkOrderStatus.PENDING]:
        raise HTTPException(status_code=400, detail=f"工单当前状态不允许开始: {order.status.value}")

    order.status = WorkOrderStatus.PROCESSING
    order.update_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='started',
        description="开始处理工单",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"开始处理:工单{workorder_id}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'started', {'id': order.id, 'status': 'processing'})
    return success_response({'status': order.status.value}, message='开始处理')


@router.post("/{workorder_id}/complete")
def complete_workorder(workorder_id: str, solution: str = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """完成工单 - 工程师提交完成申请（team scoping：跨团队 → 404）"""
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "完成")

    # 缺陷3/决策3: 已指派工单仅指派工程师可完成; 平台管理员豁免(支持代完成)。
    if (
        order.assignee_id is not None
        and not is_platform_admin(user)
        and user.id != order.assignee_id
    ):
        raise HTTPException(status_code=403, detail="仅指派工程师可完成该工单")

    if order.status != WorkOrderStatus.PROCESSING:
        raise HTTPException(status_code=400, detail=f"工单当前状态不允许完成: {order.status.value}")

    order.status = WorkOrderStatus.PENDING_VERIFY
    order.finish_time = datetime.now(timezone.utc)
    if solution:
        order.solution = solution
    order.update_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='completed',
        description="工程师提交完成，等待验收",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"提交完成:工单{workorder_id}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'completed', {'id': order.id, 'status': 'pending_verify', 'solution': solution})
    return success_response({'status': order.status.value, 'finish_time': str(order.finish_time) if order.finish_time else None}, message='完成申请已提交')


@router.post("/{workorder_id}/verify")
def verify_workorder(workorder_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """验收工单 - 管理员/客户验收通过（team scoping：跨团队 → 404）"""
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, current_user)
    _reject_legacy_status(order, "验收")

    if order.status != WorkOrderStatus.PENDING_VERIFY:
        raise HTTPException(status_code=400, detail=f"工单当前不允许验收: {order.status.value}")

    # 缺陷3/决策3: 自验收拦截 — 完成人(assignee)不得验收自己工单。
    # 未指派(assignee_id 为空, 如纯管理员流程)不拦截; 平台管理员天然不与工程师 assignee 同 id。
    if order.assignee_id is not None and current_user.id == order.assignee_id:
        raise HTTPException(status_code=400, detail="不允许验收自己处理的工单(禁止自验收)")

    order.status = WorkOrderStatus.COMPLETED
    order.verify_time = datetime.now(timezone.utc)
    order.verifier_id = current_user.id  # 记录验收人(maint-spec §2.2)
    order.update_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='verified',
        user_id=current_user.id,
        description="工单验收完成",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=current_user.id, username=current_user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"验收完成:工单{workorder_id}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'verified', {'id': order.id, 'status': 'completed'})
    return success_response({'status': order.status.value, 'verify_time': str(order.verify_time) if order.verify_time else None}, message='验收完成')


@router.post("/{workorder_id}/reject")
def reject_workorder(workorder_id: str, reason: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """驳回工单 - 验收不通过（team scoping：跨团队 → 404）"""
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "驳回")

    if order.status != WorkOrderStatus.PENDING_VERIFY:
        raise HTTPException(status_code=400, detail=f"工单当前不允许驳回: {order.status.value}")

    # 驳回后重新变为处理中
    order.status = WorkOrderStatus.PROCESSING
    order.update_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='rejected',
        description=f"验收驳回: {reason}",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"验收驳回:工单{workorder_id}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'rejected', {'id': order.id, 'status': 'processing', 'reason': reason})
    return success_response({'status': order.status.value, 'reason': reason}, message='验收驳回')


@router.post("/{workorder_id}/transfer")
def transfer_workorder(workorder_id: str, data: WorkOrderTransfer, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """转单 - 转给其他工程师（team scoping：跨团队 → 404）"""
    order = _load_workorder_for_update(db, workorder_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "转单")

    if order.status not in [WorkOrderStatus.PENDING, WorkOrderStatus.ACCEPTED, WorkOrderStatus.PROCESSING]:
        raise HTTPException(status_code=400, detail=f"工单当前状态不允许转单: {order.status.value}")

    if data.target_engineer_id == order.assignee_id:
        raise HTTPException(status_code=400, detail="不能转给自己")

    # 验证目标工程师存在 (卡 3ad52033: 团队级用户仅可转本团队工程师, 跨团队 → 404 不泄露存在)
    target_q = db.query(User).filter(User.id == data.target_engineer_id, User.role == UserRole.ENGINEER)
    if not is_platform_admin(user):
        target_q = target_q.filter(User.team_id == user.team_id)
    target = target_q.first()
    if not target:
        raise HTTPException(status_code=404, detail="目标工程师不存在")

    old_engineer = order.assignee_id
    order.assignee_id = data.target_engineer_id
    order.status = WorkOrderStatus.PENDING  # 转单后重置为待接单
    order.accept_time = None
    order.update_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='transferred',
        description=f"工单从工程师 {old_engineer} 转给 {target.real_name or target.username}: {data.reason}",
    )
    db.add(log)
    db.commit()

    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="workorders",
            target_id=workorder_id, target_desc=f"转单:{data.reason[:30]}",
        )
    except Exception:
        pass
    _broadcast_wo(db, 'transferred', {'id': order.id, 'status': 'pending', 'new_engineer': target.real_name or target.username})
    return success_response({
        'status': order.status.value,
        'new_engineer': target.real_name or target.username,
        'reason': data.reason,
    }, message='转单成功')


@router.post("/{workorder_id}/urge")
def urge_workorder(workorder_id: str, data: WorkOrderUrge = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """催单 - 催促工程师处理（team scoping：跨团队 → 404）"""
    order = (
        db.query(WorkOrder)
        .filter(WorkOrder.id == workorder_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    _check_workorder_team(db, workorder_id, user)
    _reject_legacy_status(order, "催单")

    if order.status not in [WorkOrderStatus.PENDING, WorkOrderStatus.ACCEPTED, WorkOrderStatus.PROCESSING]:
        raise HTTPException(status_code=400, detail=f"工单当前状态不允许催单: {order.status.value}")

    msg = data.message if data else "请尽快处理"

    # 添加日志
    log = WorkOrderLog(
        order_id=str(order.id),
        action='urged',
        description=f"催单: {msg}",
    )
    db.add(log)
    db.commit()

    return success_response({'message': f'已催单给工程师 {order.assignee_id}', 'note': msg}, message='催单成功')
