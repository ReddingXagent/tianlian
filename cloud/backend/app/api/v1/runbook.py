"""
Runbook自动化执行 API

提供Runbook模板查询、手动触发执行、执行记录查询等功能
"""
import logging
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.models.runbook_execution import RunbookExecutionRecord
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.station import Station
from app.api.deps import is_platform_admin, assert_alarm_team_access, assert_station_team_access
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.core.response import success_response, paginated_response, error_response
from app.services.runbook_engine import RunbookTemplate, execute_runbook_for_alarm

logger = logging.getLogger(__name__)
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_write_permission("healing:manage"))])


def _team_station_ids(db: Session, user):
    """本 team 站点 id 列表；admin/super_admin 返回 None（不过滤，平台级全可见）。
    任务卡 1c19b59a team scoping。"""
    if is_platform_admin(user):
        return None
    rows = db.query(Station.id).filter(Station.team_id == user.team_id).all()
    return [r[0] for r in rows]


# USING get_db FROM app.core.database


# ========== Runbook模板查询 ==========

@router.get("/templates")
def list_runbook_templates(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    查询可用的Runbook模板列表
    
    Args:
        category: 按类别筛选 (inverter/charger/general)
    """
    templates = []
    for name, tmpl in RunbookTemplate.TEMPLATES.items():
        if category and tmpl.get("category") != category:
            continue
        templates.append({
            "name": name,
            "category": tmpl.get("category"),
            "description": tmpl.get("description"),
            "step_count": len(tmpl.get("steps", [])),
            "auto_steps": len([s for s in tmpl.get("steps", []) if s.auto_execute]),
            "manual_steps": len([s for s in tmpl.get("steps", []) if not s.auto_execute]),
        })
    
    return success_response(data=templates)


@router.get("/templates/{template_name}")
def get_runbook_template(template_name: str, db: Session = Depends(get_db)):
    """
    获取单个Runbook模板详情
    
    Args:
        template_name: 模板名称
    """
    tmpl = RunbookTemplate.TEMPLATES.get(template_name)
    if not tmpl:
        return error_response(code=404, message=f"模板 {template_name} 不存在")
    
    return success_response(data={
        "name": template_name,
        "category": tmpl.get("category"),
        "description": tmpl.get("description"),
        "steps": [
            {
                "step_id": s.step_id,
                "action_type": s.action_type,
                "description": s.description,
                "risk_level": s.risk_level,
                "auto_execute": s.auto_execute,
                "timeout_sec": s.timeout_sec,
            }
            for s in tmpl.get("steps", [])
        ],
    })


# ========== Runbook执行 ==========

@router.post("/execute/{alarm_id}")
def execute_runbook(
    alarm_id: int,
    dry_run: bool = Query(False, description="Dry run模式, 不实际执行"),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    为指定告警执行Runbook自动化修复
    
    流程:
    1. 查找告警关联的诊断记录
    2. 获取诊断结果和设备信息
    3. 匹配Runbook模板
    4. 执行自动步骤
    5. 创建人工工单
    
    Args:
        alarm_id: 告警ID
        dry_run: 预演模式
    """
    # team scoping（任务卡 1c19b59a）：告警归属校验前置，跨团队 → 404。
    assert_alarm_team_access(db, alarm_id, current_user)
    # 1. 获取告警
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        return error_response(code=404, message=f"告警#{alarm_id}不存在")
    
    # 2. 获取设备信息
    device = db.query(Device).filter(Device.id == alarm.device_id).first()
    if not device:
        return error_response(code=404, message=f"设备#{alarm.device_id}不存在")
    
    
    device_info = {
        "id": device.id,
        "name": device.name,
        "sn": device.sn,
        "ip": device.ip_address or "",
        "station_id": alarm.station_id or device.station_id or 0,
        "type": device.device_type.value if hasattr(device.device_type, 'value') else str(device.device_type),
    }
    
    # 3. 获取诊断结果
    diagnosis_result = {}
    if alarm.diagnosis_result:
        try:
            import json
            diagnosis_result = json.loads(alarm.diagnosis_result) if isinstance(alarm.diagnosis_result, str) else alarm.diagnosis_result
        except Exception:
            pass
    
    # 如果没有诊断结果, 使用告警信息构造
    if not diagnosis_result.get("fault_type"):
        diagnosis_result = {
            "fault_type": alarm.alarm_type or alarm.fault_code or "设备离线",
            "severity": alarm.level.value if hasattr(alarm.level, 'value') else "medium",
        }
    
    # 4. 执行Runbook
    try:
        result = execute_runbook_for_alarm(
            alarm_id=alarm_id,
            diagnosis_result=diagnosis_result,
            device_info=device_info,
            db=db,
            dry_run=dry_run,
        )
        
        return success_response(data=result, message="Runbook执行完成")
        
    except Exception as e:
        logger.exception("Runbook执行失败")
        return error_response(code=500, message="Runbook执行失败")


# ========== 执行记录查询 ==========

@router.get("/executions")
def list_runbook_executions(
    station_id: Optional[int] = None,
    device_id: Optional[int] = None,
    alarm_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询Runbook执行记录

    Args:
        station_id: 按站点筛选
        device_id: 按设备筛选
        alarm_id: 按告警筛选
        status: 按状态筛选
    """
    # team scoping（任务卡 1c19b59a）：station_id 入参校验归属；列表按本 team 站点过滤。
    if station_id:
        assert_station_team_access(db, station_id, current_user)
    query = db.query(RunbookExecutionRecord)
    sids = _team_station_ids(db, current_user)
    if sids is not None:
        query = query.filter(RunbookExecutionRecord.station_id.in_(sids))

    if station_id:
        query = query.filter(RunbookExecutionRecord.station_id == station_id)
    if device_id:
        query = query.filter(RunbookExecutionRecord.device_id == device_id)
    if alarm_id:
        query = query.filter(RunbookExecutionRecord.alarm_id == alarm_id)
    if status:
        query = query.filter(RunbookExecutionRecord.status == status)
    
    total = query.count()
    executions = query.order_by(desc(RunbookExecutionRecord.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    
    items = []
    for e in executions:
        items.append({
            "id": e.id,
            "runbook_id": e.runbook_id,
            "alarm_id": e.alarm_id,
            "device_id": e.device_id,
            "station_id": e.station_id,
            "fault_type": e.fault_type,
            "status": e.status,
            "total_duration_ms": e.total_duration_ms,
            "success_steps": e.success_steps,
            "failed_steps": e.failed_steps,
            "auto_executed": e.auto_executed,
            "manual_required": e.manual_required,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    
    return paginated_response(items=items, total=total, page=page, page_size=page_size)


@router.get("/executions/{execution_id}")
def get_runbook_execution(execution_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """
    获取Runbook执行详情(含步骤详情)

    Args:
        execution_id: 执行记录ID
    """
    record = db.query(RunbookExecutionRecord).filter(RunbookExecutionRecord.id == execution_id).first()
    if not record:
        return error_response(code=404, message=f"执行记录#{execution_id}不存在")
    # team scoping（任务卡 1c19b59a）：经 station_id 校验归属，跨团队 → 404。
    assert_station_team_access(db, record.station_id, current_user)
    
    return success_response(data={
        "id": record.id,
        "runbook_id": record.runbook_id,
        "alarm_id": record.alarm_id,
        "diagnosis_record_id": record.diagnosis_record_id,
        "device_id": record.device_id,
        "station_id": record.station_id,
        "fault_type": record.fault_type,
        "status": record.status,
        "steps": record.steps_json,
        "start_time": record.start_time.isoformat() if record.start_time else None,
        "end_time": record.end_time.isoformat() if record.end_time else None,
        "total_duration_ms": record.total_duration_ms,
        "success_steps": record.success_steps,
        "failed_steps": record.failed_steps,
        "skipped_steps": record.skipped_steps,
        "auto_executed": record.auto_executed,
        "manual_required": record.manual_required,
        "workorder_id": record.workorder_id,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    })


@router.get("/stats")
def get_runbook_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    获取Runbook执行统计
    """
    from sqlalchemy import func

    # team scoping（任务卡 1c19b59a）：非 admin 仅统计本 team 站点执行记录。
    sids = _team_station_ids(db, current_user)
    def _scoped(q):
        return q if sids is None else q.filter(RunbookExecutionRecord.station_id.in_(sids))

    # 总执行数
    total = _scoped(db.query(func.count(RunbookExecutionRecord.id))).scalar() or 0

    # 按状态统计
    status_stats = {}
    for row in _scoped(db.query(RunbookExecutionRecord.status, func.count(RunbookExecutionRecord.id))).group_by(RunbookExecutionRecord.status).all():
        status_stats[row[0]] = row[1]

    # 平均耗时
    avg_duration = _scoped(db.query(func.avg(RunbookExecutionRecord.total_duration_ms))).scalar() or 0

    # 成功率
    success_count = _scoped(db.query(func.count(RunbookExecutionRecord.id)).filter(
        RunbookExecutionRecord.failed_steps == 0
    )).scalar() or 0

    # 最近7天执行数
    from datetime import datetime, timedelta, timezone
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_count = _scoped(db.query(func.count(RunbookExecutionRecord.id)).filter(
        RunbookExecutionRecord.created_at >= week_ago
    )).scalar() or 0
    
    return success_response(data={
        "total_executions": total,
        "status_breakdown": status_stats,
        "average_duration_ms": round(avg_duration, 0),
        "success_rate": round(success_count / total * 100, 1) if total > 0 else 0,
        "last_7_days": recent_count,
    })
