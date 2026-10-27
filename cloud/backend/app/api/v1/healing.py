"""
告警自愈引擎 API

提供自愈规则管理、执行记录查询、审批操作等功能
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import success_response, paginated_response, error_response
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.api.deps import is_platform_admin
from app.models.user import User
from app.models.station import Station
from app.models.healing_execution import HealingExecution
from app.schemas.healing import (
    HealingRuleCreateRequest,
    HealingRuleUpdateRequest,
    HealingExecutionRejectRequest,
)
from app.services.healing_engine import healing_engine

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_write_permission("healing:manage"))])


# USING get_db FROM app.core.database


def _execution_team_id(db: Session, execution_id: int):
    """自愈执行经 station_id→team 归属（任务卡 ed509541）。"""
    row = (
        db.query(Station.team_id)
        .join(HealingExecution, HealingExecution.station_id == Station.id)
        .filter(HealingExecution.id == execution_id)
        .first()
    )
    return row[0] if row else None


def _check_execution_team(db: Session, execution_id: int, user: User, msg: str = "执行记录不存在"):
    """详情/写端点归属校验：admin 豁免；非 admin 仅本 team 执行，否则 404。"""
    if is_platform_admin(user):
        return
    tid = _execution_team_id(db, execution_id)
    if tid is None or user.team_id is None or tid != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _own_station_ids(db: Session, user: User):
    """本 team 站点 id 列表；admin 返回 None（不过滤，平台级可见）。"""
    if is_platform_admin(user):
        return None
    return [sid for (sid,) in db.query(Station.id).filter(Station.team_id == user.team_id).all()]


# ========== 自愈规则管理 ==========

@router.get("/rules")
def list_healing_rules(
    enabled_only: bool = Query(False, description="仅显示启用的规则"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取自愈规则列表"""
    try:
        rules = healing_engine.list_rules(db, enabled_only=enabled_only)
        return success_response(data=rules)
    except HTTPException:
        raise
    except Exception:
        logger.exception("获取自愈规则列表失败")
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.post("/rules")
def create_healing_rule(
    data: HealingRuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    创建自愈规则

    请求体示例:
    {
        "name": "逆变器通讯中断自愈",
        "description": "当逆变器通讯中断时自动执行修复",
        "alarm_pattern": {
            "alarm_levels": ["critical", "warning"],
            "alarm_types": ["逆变器通讯中断"],
            "device_types": ["inverter"]
        },
        "runbook_template": "逆变器通讯中断",
        "auto_approve": false,
        "max_retries": 2,
        "cooldown_minutes": 30,
        "priority": 10,
        "enabled": true
    }
    """
    try:
        # 参数校验：name / alarm_pattern 业务必填，缺失返回业务级 400（非 Pydantic 422）。
        if not data.name:
            return error_response(code=400, message="规则名称不能为空")
        if not data.alarm_pattern:
            return error_response(code=400, message="告警匹配条件不能为空")

        # exclude_unset=True：仅取客户端实际传入字段，复刻原 dict 语义，
        # 由 healing_engine 内部 .get(key, default) 回填未传字段的默认值。
        result = healing_engine.create_rule(data.model_dump(exclude_unset=True), db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(data=result, message="创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建自愈规则失败 name=%s", data.name)
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.get("/rules/{rule_id}")
def get_healing_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取自愈规则详情"""
    try:
        from app.models.healing_rule import HealingRule
        rule = db.query(HealingRule).filter(HealingRule.id == rule_id).first()
        if not rule:
            return error_response(code=404, message=f"规则#{rule_id}不存在")

        return success_response(data={
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "alarm_pattern": rule.alarm_pattern,
            "runbook_template": rule.runbook_template,
            "auto_approve": rule.auto_approve,
            "max_retries": rule.max_retries,
            "cooldown_minutes": rule.cooldown_minutes,
            "priority": rule.priority,
            "enabled": rule.enabled,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("获取自愈规则详情失败 rule_id=%s", rule_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.put("/rules/{rule_id}")
def update_healing_rule(
    rule_id: int,
    data: HealingRuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新自愈规则"""
    try:
        # exclude_unset=True：仅更新客户端实际传入字段，未传字段保持原值。
        result = healing_engine.update_rule(rule_id, data.model_dump(exclude_unset=True), db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(data=result, message="更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新自愈规则失败 rule_id=%s", rule_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.delete("/rules/{rule_id}")
def delete_healing_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除自愈规则"""
    try:
        result = healing_engine.delete_rule(rule_id, db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(message=result["message"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("删除自愈规则失败 rule_id=%s", rule_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


# ========== 执行记录 ==========

@router.get("/executions")
def list_healing_executions(
    status: Optional[str] = None,
    rule_id: Optional[int] = None,
    device_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询自愈执行记录"""
    try:
        result = healing_engine.list_executions(
            db, status=status, rule_id=rule_id, device_id=device_id,
            page=page, page_size=page_size,
            station_ids=_own_station_ids(db, user),
        )
        return paginated_response(
            items=result["items"],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"]
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询自愈执行记录失败")
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.get("/executions/{execution_id}")
def get_healing_execution(
    execution_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取自愈执行详情"""
    try:
        _check_execution_team(db, execution_id, user)
        result = healing_engine.get_execution(execution_id, db)
        if not result:
            return error_response(code=404, message=f"执行记录#{execution_id}不存在")

        return success_response(data=result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("获取自愈执行详情失败 execution_id=%s", execution_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


# ========== 审批操作 ==========

@router.post("/executions/{execution_id}/approve")
def approve_healing_execution(
    execution_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """审批通过自愈执行"""
    try:
        _check_execution_team(db, execution_id, user)
        approver = user.username if hasattr(user, 'username') else f"user_{user.id}"
        result = healing_engine.approve_execution(execution_id, approver, db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(data=result, message="审批通过，已开始执行")
    except HTTPException:
        raise
    except Exception:
        logger.exception("审批自愈执行失败 execution_id=%s", execution_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.post("/executions/{execution_id}/reject")
def reject_healing_execution(
    execution_id: int,
    data: Optional[HealingExecutionRejectRequest] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    拒绝自愈执行

    请求体（可选）: {"reason": "拒绝原因"}
    """
    try:
        _check_execution_team(db, execution_id, user)
        reason = data.reason if data else ""
        rejector = user.username if hasattr(user, 'username') else f"user_{user.id}"
        result = healing_engine.reject_execution(execution_id, rejector, reason, db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(data=result, message="已拒绝执行")
    except HTTPException:
        raise
    except Exception:
        logger.exception("拒绝自愈执行失败 execution_id=%s", execution_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.post("/executions/{execution_id}/retry")
def retry_healing_execution(
    execution_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重试失败的自愈执行"""
    try:
        _check_execution_team(db, execution_id, user)
        result = healing_engine.retry_execution(execution_id, db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(data=result, message="重试执行完成")
    except HTTPException:
        raise
    except Exception:
        logger.exception("重试自愈执行失败 execution_id=%s", execution_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


# ========== 手动触发 ==========

@router.post("/trigger/{alarm_id}")
def trigger_healing_for_alarm(
    alarm_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动为指定告警触发自愈评估"""
    try:
        from app.models.alarm import Alarm
        from app.models.device import Device

        alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
        if not alarm:
            return error_response(code=404, message=f"告警#{alarm_id}不存在")
        # team 校验（任务卡 ed509541）：trigger 保持 error_response 契约，
        # 跨团队返回 404 body（与 healing 端点 error_response 风格一致，不泄露存在）。
        if not is_platform_admin(user):
            tid = None
            if alarm.station_id:
                tid = db.query(Station.team_id).filter(Station.id == alarm.station_id).scalar()
            elif alarm.device_id:
                tid = (
                    db.query(Station.team_id)
                    .join(Device, Device.station_id == Station.id)
                    .filter(Device.id == alarm.device_id)
                    .scalar()
                )
            if tid is None or user.team_id is None or tid != user.team_id:
                return error_response(code=404, message="告警不存在")

        result = healing_engine.evaluate_alarm(alarm, db)
        if not result:
            return success_response(data=None, message="未匹配到自愈规则")

        return success_response(data=result, message="自愈评估完成")
    except HTTPException:
        raise
    except Exception:
        logger.exception("触发告警自愈失败 alarm_id=%s", alarm_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


# ========== 效果验证 ==========

@router.post("/executions/{execution_id}/verify")
def verify_healing_result(
    execution_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """验证自愈执行后的效果（告警是否清除、设备是否恢复）"""
    try:
        _check_execution_team(db, execution_id, user)
        result = healing_engine.verify_healing_result(execution_id, db)
        if "error" in result:
            return error_response(code=400, message=result["error"])

        return success_response(data=result, message="验证完成")
    except HTTPException:
        raise
    except Exception:
        logger.exception("验证自愈结果失败 execution_id=%s", execution_id)
        db.rollback()
        return error_response(code=500, message="内部错误")


@router.post("/batch-verify")
def batch_verify_healing(
    hours: int = Query(24, ge=1, le=720, description="检查最近N小时内的记录(边界1~720)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量验证已成功执行但未验证的自愈记录"""
    try:
        result = healing_engine.batch_verify_completed(db, hours=hours)
        return success_response(data=result, message="批量验证完成")
    except HTTPException:
        raise
    except Exception:
        logger.exception("批量验证自愈记录失败 hours=%s", hours)
        db.rollback()
        return error_response(code=500, message="内部错误")


# ========== 统计 ==========

@router.get("/stats")
def get_healing_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取自愈统计"""
    try:
        stats = healing_engine.get_stats(db)
        return success_response(data=stats)
    except HTTPException:
        raise
    except Exception:
        logger.exception("获取自愈统计失败")
        db.rollback()
        return error_response(code=500, message="内部错误")
