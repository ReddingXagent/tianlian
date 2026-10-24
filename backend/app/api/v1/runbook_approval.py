"""
Runbook审批流 API

功能:
1. 查询待审批列表
2. 审批/拒绝操作
3. 审批超时自动处理
4. 审批升级(低级审批人→高级审批人)
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.models.runbook_approval import RunbookApproval, RunbookApprovalLog
from app.models.runbook_execution import RunbookExecutionRecord
from app.models.alarm import Alarm
from app.models.station import Station
from app.api.deps import is_platform_admin, assert_alarm_team_access
from app.api.v1.auth import get_current_user
from app.core.response import success_response, paginated_response, error_response
from app.models.user import User, UserRole
from app.services.runbook_engine import safe_command_list

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


def _team_station_ids(db: Session, user):
    """本 team 站点 id 列表；admin/super_admin 返回 None（不过滤，平台级全可见）。
    任务卡 1c19b59a team scoping。"""
    if is_platform_admin(user):
        return None
    rows = db.query(Station.id).filter(Station.team_id == user.team_id).all()
    return [r[0] for r in rows]


def _assert_approval_alarm_team_access(db: Session, alarm_id, user):
    """审批关联告警的 team 软校验（任务卡 1c19b59a）。

    alarm 真实存在则按 assert_alarm_team_access 校验归属（跨团队→404）；
    孤儿/占位 alarm_id 放行——审批可达性已由 list/history/stats 的
    inner-join(Alarm) 过滤保障（孤儿审批不在任何列表），单条 approve/reject 的
    越权防护由 RBAC required_level(can_approve_at_level) 兜底。真实业务流
    approval.alarm_id 必指向现存 alarm，故 team 隔离对真实数据有效。
    """
    if is_platform_admin(user):
        return
    if not alarm_id:
        return
    if not db.query(Alarm.id).filter(Alarm.id == alarm_id).first():
        return
    assert_alarm_team_access(db, alarm_id, user)


# USING get_db FROM app.core.database


# ========== 审批风险等级到所需审批级别的映射 ==========

RISK_TO_APPROVAL_LEVEL = {
    "low": None,           # 无需审批
    "medium": "operator",  # 运维人员审批
    "high": "manager",     # 管理层审批
    "critical": "admin",   # 系统管理员审批
}

APPROVAL_TIMEOUT_MINUTES = {
    "medium": 30,
    "high": 60,
    "critical": 120,
}


# ========== 用户角色 → 审批层级映射（任务卡 b198e42c）==========
# required_level 体系(operator/manager/admin)与 UserRole 枚举体系不同源，
# 此处显式映射为可比的层级数值：数字越大审批权限越高。
# is_platform_admin(admin/super_admin)显式豁免，无视 required_level 放行，
# 与 auth.require_role / deps.is_platform_admin 同源。
APPROVAL_LEVEL_RANK = {
    "operator": 1,
    "manager": 2,
    "admin": 3,
}

ROLE_APPROVAL_LEVEL = {
    UserRole.VIEWER: 0,           # 只读，无审批权
    UserRole.TECHNICIAN: 0,       # 现场技术员，无审批权
    UserRole.AUDITOR: 0,          # 审计员，只读
    UserRole.OPERATOR: 1,         # = operator 级
    UserRole.ENGINEER: 1,         # 工程师 ≥ operator
    UserRole.STATION_MASTER: 2,   # 站长 = manager 级
    UserRole.DISPATCHER: 2,       # 调度员 = manager 级
    UserRole.ADMIN: 3,            # = admin 级
    UserRole.SUPER_ADMIN: 3,      # 顶格（实际经 is_platform_admin 豁免）
}


def _user_role_value(user) -> str:
    """取 user.role 的字符串值(小写)，兼容 enum 与裸字符串。"""
    role = getattr(user, "role", None)
    if hasattr(role, "value"):
        return str(role.value).lower()
    return str(role).lower() if role else ""


def _required_level_rank(level) -> int:
    """required_level → 层级数值；None(无需审批)视为 0，未知值保守取 0。"""
    if not level:
        return 0
    return APPROVAL_LEVEL_RANK.get(str(level).lower(), 0)


def can_approve_at_level(user, required_level) -> bool:
    """审批权限校验：admin/super_admin 豁免；其余按角色层级 ≥ required_level 判定。

    防授权绕过→RCE：低级别用户不得 approve/reject 高级别审批(含 critical)，
    否则经 auto_execute_after_approval 触发 _execute_approved_step → subprocess
    主机执行命令。与 deps.is_platform_admin 平台级判定保持同源。
    """
    if is_platform_admin(user):
        return True
    user_rank = ROLE_APPROVAL_LEVEL.get(_user_role_value(user), 0)
    return user_rank >= _required_level_rank(required_level)


def create_approval_request(
    db: Session,
    runbook_id: str,
    alarm_id: int,
    step_index: int,
    step_description: str,
    action_type: str,
    command_preview: str,
    risk_level: str,
    rollback_preview: str = None,
) -> RunbookApproval:
    """
    创建审批请求

    当Runbook步骤的风险等级需要审批时调用。
    同 (runbook_id, step_index) 已存在 pending 审批时不重复创建, 返回已有记录
    (卡 5421defc 第二层防御: 防重复执行堆积审批)。
    """
    existing = db.query(RunbookApproval).filter(
        RunbookApproval.runbook_id == runbook_id,
        RunbookApproval.step_index == step_index,
        RunbookApproval.status == "pending",
    ).first()
    if existing is not None:
        logger.info(
            "审批请求已存在(runbook=%s, step=%s), 不重复创建", runbook_id, step_index
        )
        return existing

    required_level = RISK_TO_APPROVAL_LEVEL.get(risk_level, "manager")
    timeout_min = APPROVAL_TIMEOUT_MINUTES.get(risk_level, 30)
    
    approval = RunbookApproval(
        runbook_id=runbook_id,
        alarm_id=alarm_id,
        step_index=step_index,
        step_description=step_description,
        action_type=action_type,
        command_preview=command_preview,
        risk_level=risk_level,
        rollback_preview=rollback_preview,
        status="pending",
        required_level=required_level,
        auto_execute_after_approval=True,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=timeout_min),
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


# ========== API端点 ==========

@router.get("/pending")
def list_pending_approvals(
    risk_level: Optional[str] = None,
    station_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查询待审批列表
    
    返回所有pending状态的审批请求
    """
    query = db.query(RunbookApproval).filter(RunbookApproval.status == "pending")
    # team scoping（任务卡 1c19b59a）：非 admin 仅本 team 告警的审批（经 alarm_id→station→team）。
    sids = _team_station_ids(db, current_user)
    if sids is not None:
        query = query.join(Alarm, Alarm.id == RunbookApproval.alarm_id).filter(Alarm.station_id.in_(sids))

    if risk_level:
        query = query.filter(RunbookApproval.risk_level == risk_level)
    
    # 检查是否已超时
    now = datetime.now(timezone.utc)
    query = query.filter(RunbookApproval.expires_at > now)  # 排除已过期的
    
    total = query.count()
    approvals = query.order_by(
        # critical优先, 然后按创建时间
        RunbookApproval.risk_level.desc(),
        RunbookApproval.created_at.asc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    items = []
    for a in approvals:
        items.append({
            "id": a.id,
            "runbook_id": a.runbook_id,
            "alarm_id": a.alarm_id,
            "step_index": a.step_index,
            "step_description": a.step_description,
            "action_type": a.action_type,
            "command_preview": a.command_preview,
            "risk_level": a.risk_level,
            "rollback_preview": a.rollback_preview,
            "required_level": a.required_level,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    
    return paginated_response(items=items, total=total, page=page, page_size=page_size)


@router.get("/history")
def list_approval_history(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询审批历史"""
    query = db.query(RunbookApproval)
    # team scoping（任务卡 1c19b59a）：非 admin 仅本 team 告警的审批。
    sids = _team_station_ids(db, current_user)
    if sids is not None:
        query = query.join(Alarm, Alarm.id == RunbookApproval.alarm_id).filter(Alarm.station_id.in_(sids))

    if status:
        query = query.filter(RunbookApproval.status == status)
    
    total = query.count()
    approvals = query.order_by(desc(RunbookApproval.updated_at)).offset((page - 1) * page_size).limit(page_size).all()
    
    items = []
    for a in approvals:
        items.append({
            "id": a.id,
            "runbook_id": a.runbook_id,
            "alarm_id": a.alarm_id,
            "step_description": a.step_description,
            "risk_level": a.risk_level,
            "status": a.status,
            "approver_name": a.approver_name,
            "reject_reason": a.reject_reason,
            "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    
    return paginated_response(items=items, total=total, page=page, page_size=page_size)


@router.post("/{approval_id}/approve")
def approve_runbook_step(
    approval_id: int,
    comment: str = Body("", embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    审批通过Runbook步骤
    
    审批通过后，如果设置了auto_execute_after_approval，
    将自动执行该步骤
    """
    approval = db.query(RunbookApproval).filter(RunbookApproval.id == approval_id).first()
    if not approval:
        return error_response(code=404, message="审批记录不存在")

    # 角色层级校验(任务卡 b198e42c)：低级别用户不得越权 approve 高级别审批，
    # 否则经 auto_execute_after_approval 触发 subprocess → 授权绕过 RCE。
    # 校验置于状态更新之前，确保越权请求不篡改审批状态。
    if not can_approve_at_level(current_user, approval.required_level):
        raise HTTPException(
            status_code=403,
            detail=f"审批权限不足，需要 {approval.required_level or 'operator'} 级及以上审批人",
        )

    # team scoping（任务卡 1c19b59a）：审批归属软校验（经 alarm_id→station→team），
    # alarm 真实存在才校验，跨团队 → 404；孤儿/占位 alarm 由 RBAC 兜底（见 helper 注释）。
    _assert_approval_alarm_team_access(db, approval.alarm_id, current_user)

    if approval.status != "pending":
        return error_response(code=400, message=f"审批状态为{approval.status}，无法审批")
    
    # 检查是否超时
    # DB(DateTime 无 tz) 读出的 expires_at 为 naive datetime，按系统约定(UTC)补 tz 后再与 aware now 比较，
    # 否则 offset-naive vs offset-aware 比较 → TypeError → 500（utcnow→now(timezone.utc) 重构残留）。
    if approval.expires_at:
        expires_at = approval.expires_at if approval.expires_at.tzinfo else approval.expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            approval.status = "expired"
            db.commit()
            return error_response(code=400, message="审批已超时")
    
    # 更新审批状态
    approval.status = "approved"
    approval.approver_id = current_user.id if hasattr(current_user, 'id') else 0
    approval.approver_name = current_user.username if hasattr(current_user, 'username') else str(current_user)
    approval.approved_at = datetime.now(timezone.utc)
    db.commit()
    
    # 记录日志
    log = RunbookApprovalLog(
        approval_id=approval.id,
        action="approve",
        operator_id=approval.approver_id,
        operator_name=approval.approver_name,
        comment=comment,
    )
    db.add(log)
    
    # 如果设置了审批后自动执行，执行该步骤
    execution_result = None
    if approval.auto_execute_after_approval:
        try:
            execution_result = _execute_approved_step(approval, db)
            approval.executed_after_approval = True
        except Exception as e:
            logger.exception("审批后自动执行步骤失败")
            execution_result = {"error": "步骤自动执行失败"}
    
    db.commit()
    
    return success_response(
        data={
            "approval_id": approval.id,
            "status": "approved",
            "executed": approval.executed_after_approval,
            "execution_result": execution_result,
        },
        message="审批通过" + ("，步骤已自动执行" if approval.executed_after_approval else "")
    )


@router.post("/{approval_id}/reject")
def reject_runbook_step(
    approval_id: int,
    reason: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    拒绝Runbook步骤审批
    
    拒绝后该步骤将被跳过，Runbook继续执行下一步
    """
    approval = db.query(RunbookApproval).filter(RunbookApproval.id == approval_id).first()
    if not approval:
        return error_response(code=404, message="审批记录不存在")

    # 角色层级校验(任务卡 b198e42c)：低级别用户同样不得拒绝高级别审批。
    if not can_approve_at_level(current_user, approval.required_level):
        raise HTTPException(
            status_code=403,
            detail=f"审批权限不足，需要 {approval.required_level or 'operator'} 级及以上审批人",
        )

    # team scoping（任务卡 1c19b59a）：审批归属软校验（经 alarm_id→station→team），
    # alarm 真实存在才校验，跨团队 → 404；孤儿/占位 alarm 由 RBAC 兜底（见 helper 注释）。
    _assert_approval_alarm_team_access(db, approval.alarm_id, current_user)

    if approval.status != "pending":
        return error_response(code=400, message=f"审批状态为{approval.status}，无法操作")
    
    approval.status = "rejected"
    approval.approver_id = current_user.id if hasattr(current_user, 'id') else 0
    approval.approver_name = current_user.username if hasattr(current_user, 'username') else str(current_user)
    approval.approved_at = datetime.now(timezone.utc)
    approval.reject_reason = reason
    
    # 记录日志
    log = RunbookApprovalLog(
        approval_id=approval.id,
        action="reject",
        operator_id=approval.approver_id,
        operator_name=approval.approver_name,
        comment=reason,
    )
    db.add(log)
    db.commit()
    
    return success_response(data={
        "approval_id": approval.id,
        "status": "rejected",
    }, message="已拒绝执行")


@router.post("/expire-check")
def check_expired_approvals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    批量检查并处理超时审批
    
    超时的审批自动标记为expired
    可由定时任务调用
    """
    now = datetime.now(timezone.utc)
    exp_q = db.query(RunbookApproval).filter(
        and_(
            RunbookApproval.status == "pending",
            RunbookApproval.expires_at < now,
        )
    )
    # team scoping（任务卡 1c19b59a）：非 admin 仅处理本 team 告警的超时审批。
    sids = _team_station_ids(db, current_user)
    if sids is not None:
        exp_q = exp_q.join(Alarm, Alarm.id == RunbookApproval.alarm_id).filter(Alarm.station_id.in_(sids))
    expired = exp_q.all()
    
    count = 0
    for a in expired:
        a.status = "expired"
        log = RunbookApprovalLog(
            approval_id=a.id,
            action="expire",
            operator_id=0,
            operator_name="system",
            comment="审批超时自动过期",
        )
        db.add(log)
        count += 1
    
    db.commit()
    
    return success_response(data={
        "expired_count": count,
    }, message=f"已处理{count}条超时审批")


@router.get("/stats")
def get_approval_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """审批统计"""
    from sqlalchemy import func

    # team scoping（任务卡 1c19b59a）：非 admin 仅统计本 team 告警的审批。
    sids = _team_station_ids(db, current_user)
    def _scoped(q):
        return q if sids is None else q.join(Alarm, Alarm.id == RunbookApproval.alarm_id).filter(Alarm.station_id.in_(sids))

    total = _scoped(db.query(func.count(RunbookApproval.id))).scalar() or 0
    pending = _scoped(db.query(func.count(RunbookApproval.id)).filter(RunbookApproval.status == "pending")).scalar() or 0
    approved = _scoped(db.query(func.count(RunbookApproval.id)).filter(RunbookApproval.status == "approved")).scalar() or 0
    rejected = _scoped(db.query(func.count(RunbookApproval.id)).filter(RunbookApproval.status == "rejected")).scalar() or 0
    expired = _scoped(db.query(func.count(RunbookApproval.id)).filter(RunbookApproval.status == "expired")).scalar() or 0

    # 按风险等级统计待审批
    pending_by_risk = {}
    for row in _scoped(db.query(
        RunbookApproval.risk_level,
        func.count(RunbookApproval.id)
    ).filter(RunbookApproval.status == "pending").group_by(RunbookApproval.risk_level)).all():
        pending_by_risk[row[0]] = row[1]
    
    return success_response(data={
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "expired": expired,
        "pending_by_risk": pending_by_risk,
    })


# ========== 内部函数 ==========

def _execute_approved_step(approval: RunbookApproval, db: Session) -> dict:
    """
    执行已审批通过的步骤
    
    从Runbook执行记录中找到对应步骤并执行
    """
    import json
    import time
    import subprocess
    from app.services.runbook_engine import RunbookStatus

    # 执行前二次复核 status==approved(任务卡 b198e42c)：防 approve commit 后、
    # execute 前被并发 reject/expire 改写状态，仍继续执行命令(重放/竞态)。
    # 重新从库读取最新状态，内存中的 approval 对象可能已过期。
    fresh = db.query(RunbookApproval).filter(RunbookApproval.id == approval.id).first()
    if not fresh or fresh.status != "approved":
        return {
            "status": "skipped",
            "reason": "approval not in approved state (concurrent modification)",
        }

    # 找到关联的Runbook执行记录
    record = db.query(RunbookExecutionRecord).filter(
        RunbookExecutionRecord.runbook_id == approval.runbook_id
    ).first()
    
    if not record:
        raise Exception(f"Runbook执行记录 {approval.runbook_id} 不存在")
    
    steps = json.loads(record.steps_json) if isinstance(record.steps_json, str) else record.steps_json
    
    # 找到对应步骤
    step = None
    for s in steps:
        if s.get("step_id") == approval.step_index or s.get("step_id", 0) == approval.step_index:
            step = s
            break
    
    if not step:
        # 索引方式查找
        if 0 <= approval.step_index < len(steps):
            step = steps[approval.step_index]
    
    if not step:
        raise Exception(f"步骤 #{approval.step_index} 不存在")
    
    command = step.get("command", "")
    if not command:
        return {"status": "skipped", "reason": "no command"}
    
    # 执行命令
    start = time.time()
    try:
        result = subprocess.run(
            safe_command_list(command), shell=False, capture_output=True,
            text=True, timeout=step.get("timeout_sec", 60)
        )
        duration_ms = int((time.time() - start) * 1000)
        
        if result.returncode == 0:
            step["status"] = RunbookStatus.COMPLETED
            step["result"] = result.stdout.strip()
            step["duration_ms"] = duration_ms
            record.success_steps += 1
        else:
            step["status"] = RunbookStatus.FAILED
            step["error_message"] = result.stderr.strip()[:500]
            step["duration_ms"] = duration_ms
            record.failed_steps += 1
            
            # 尝试回滚
            rollback = step.get("rollback_command", "")
            if rollback:
                try:
                    subprocess.run(safe_command_list(rollback), shell=False, capture_output=True, text=True, timeout=30)
                    step["status"] = RunbookStatus.ROLLED_BACK
                except Exception:
                    pass
        
        record.steps_json = json.dumps(steps, ensure_ascii=False)
        db.commit()
        
        return {
            "status": step["status"],
            "result": step.get("result", ""),
            "duration_ms": duration_ms,
        }
        
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "timeout"}
    except ValueError as e:
        # 命令安全校验拒绝 (validate_shell_command) —— 受控业务反馈, 非内部异常:
        # 用固定文案回执, 既保留"注入被拒"语义、又不回显攻击者输入; 实际异常已记录日志。
        logger.warning("步骤执行被拒绝: %s", e)
        return {"status": "failed", "error": "命令被安全校验拒绝，疑似注入"}
    except Exception as e:
        logger.exception("执行步骤失败")
        return {"status": "failed", "error": "步骤执行失败"}
