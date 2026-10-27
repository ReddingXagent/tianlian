"""
监控告警闭环 API
Phase 5 - 预测性维护告警 → 工单 → 诊断 → 修复 → 验证闭环
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Literal, List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
import logging

from app.core.database import get_db
from app.api.v1.auth import require_role
from app.api.deps import get_current_user, is_platform_admin
from app.core.cache import cache
from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
from app.models.workorder import WorkOrder, WorkOrderStatus, WorkOrderType, WorkOrderLevel
from app.models.device import Device
from app.models.station import Station
from app.models.user import User
from app.models.analytics import PredictionAlert
from app.services.im_notify import im_notify_service

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_role("admin", "operator"))])


# ============ 团队归属校验（卡 7fd8f66 / 审计 #5）===========

def _check_station_ownership(db: Session, station_id: Optional[int], user: User, msg: str) -> None:
    """校验资源经 station 归属本 team；platform admin 豁免；不匹配/无归属 → 404（不泄露存在）。

    与 digital_twin._check_device_team / deps.assert_team_access 同构：
    双方必须有明确 team_id 且相等才放行。
    """
    if is_platform_admin(user):
        return
    team_id = None
    if station_id is not None:
        row = db.query(Station.team_id).filter(Station.id == station_id).first()
        team_id = row[0] if row else None
    if team_id is None or user.team_id is None or team_id != user.team_id:
        raise HTTPException(status_code=404, detail=msg)


def _team_scoped(db: Session, model, user: User):
    """stats 类聚合查询的 team 过滤：admin 全平台；团队级仅本 team 站点数据。

    复用 model.station_id → Station.team_id 的归属链（与 _check_station_ownership 同源）。
    """
    query = db.query(model)
    if is_platform_admin(user):
        return query
    return query.join(Station, model.station_id == Station.id).filter(Station.team_id == user.team_id)


# ============ Schemas ============

class AlertTriggerRequest(BaseModel):
    """告警触发请求"""
    device_id: int
    alert_type: Literal["predictive", "anomaly", "threshold"]
    severity: str  # low / medium / high / critical
    message: str
    prediction_data: Optional[Dict[str, Any]] = None  # 预测数据

class WorkflowStatusResponse(BaseModel):
    """闭环状态响应"""
    alert_id: int
    workorder_id: Optional[str]
    current_stage: str  # alert / workorder / diagnosis / repair / verification / closed
    stages: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

class DiagnosisRequest(BaseModel):
    """诊断请求"""
    workorder_id: str = Field(..., max_length=50)
    diagnosis_type: str  # ai / manual / automated
    findings: List[str]
    root_cause: str
    suggested_actions: List[str]

class RepairRequest(BaseModel):
    """修复请求"""
    workorder_id: str
    repair_type: str  # manual / automated / remote
    actions_taken: List[str]
    parts_replaced: Optional[List[str]] = None
    duration_minutes: int

class VerificationRequest(BaseModel):
    """验证请求"""
    workorder_id: str
    verification_type: str  # auto / manual
    checks_passed: List[str]
    health_score_after: float
    notes: Optional[str] = None


# ============ 告警触发 → 工单创建 ============

@router.post("/trigger", summary="触发告警闭环")
def trigger_alert_workflow(
    request: AlertTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    触发告警并启动闭环流程
    1. 创建告警记录
    2. 自动创建工单（严重告警）
    3. 关联预测数据
    """
    device = db.query(Device).filter(Device.id == request.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"设备 {request.device_id} 不存在")
    _check_station_ownership(db, device.station_id, user, f"设备 {request.device_id} 不存在")
    
    # 1. 创建告警
    alarm = Alarm(
        device_id=request.device_id,
        station_id=device.station_id,
        content=request.message,  # 使用 content 字段（模型定义）
        level=AlarmLevel(request.severity),
        status=AlarmStatus.ACTIVE,
        alarm_type=request.alert_type,  # 使用 alarm_type 字段（模型定义）
        created_at=datetime.now(timezone.utc),
    )
    db.add(alarm)
    db.flush()  # 获取alarm.id
    
    # 2. 根据严重程度决定是否自动创建工单
    workorder = None
    if request.severity in ["high", "critical"]:
        # 确定工单严重级别
        level_map = {
            "critical": WorkOrderLevel.CRITICAL,
            "high": WorkOrderLevel.WARNING,
            "medium": WorkOrderLevel.INFO,
            "low": WorkOrderLevel.INFO,
        }
        
        workorder = WorkOrder(
            id=f"WO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{alarm.id:04d}",  # 生成工单号
            device_id=request.device_id,
            station_id=device.station_id,
            type=WorkOrderType.REPAIR,
            level=level_map.get(request.severity, WorkOrderLevel.INFO),
            status=WorkOrderStatus.PENDING,
            fault_desc=f"[{request.alert_type}] {request.message}\n设备 {device.name} 触发{request.severity}级别告警，需要立即处理。",
            create_time=datetime.now(timezone.utc),
        )
        db.add(workorder)
        db.flush()
        
        # 关联告警和工单
        alarm.workorder_id = workorder.id
    
    # 3. 如果有预测数据，保存到PredictionAlert
    if request.prediction_data and hasattr(PredictionAlert, '__table__'):
        try:
            prediction = PredictionAlert(
                alarm_id=alarm.id,
                device_id=request.device_id,
                prediction_type=request.prediction_data.get("type", "lstm"),
                prediction_score=request.prediction_data.get("score", 0.0),
                prediction_details=request.prediction_data,
                created_at=datetime.now(timezone.utc),
            )
            db.add(prediction)
        except Exception as e:
            logger.warning("保存预测数据失败: %s", e)
    
    db.commit()
    cache.delete_pattern("alert_workflow:stats")
    
    # 4. 后台任务：发送通知
    if request.severity in ["high", "critical"]:
        background_tasks.add_task(
            notify_urgent_alert,
            alarm.id,
            device.name,
            request.message,
            request.severity
        )
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "alert_id": alarm.id,
            "workorder_id": workorder.id if workorder else None,
            "device_name": device.name,
            "severity": request.severity,
            "workflow_stage": "alert_created",
            "auto_workorder": workorder is not None,
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


# ============ 闭环状态查询 ============

@router.get("/status/{alert_id}", summary="查询闭环状态")
def get_workflow_status(alert_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """查询告警闭环的完整状态"""
    alarm = db.query(Alarm).filter(Alarm.id == alert_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail=f"告警 {alert_id} 不存在")
    _check_station_ownership(db, alarm.station_id, user, f"告警 {alert_id} 不存在")
    
    stages = []
    current_stage = "alert"
    
    # 告警阶段
    stages.append({
        "stage": "alert",
        "status": alarm.status.value,
        "timestamp": alarm.created_at.isoformat() if alarm.created_at else None,
    })
    
    # 工单阶段
    if alarm.workorder_id:
        workorder = db.query(WorkOrder).filter(WorkOrder.id == alarm.workorder_id).first()
        if workorder:
            current_stage = "workorder"
            stages.append({
                "stage": "workorder",
                "status": workorder.status.value,
                "timestamp": workorder.create_time.isoformat() if workorder.create_time else None,
                "assigned_to": workorder.assignee_id,
            })
            
            # 诊断阶段（如果工单有诊断结果）
            if hasattr(workorder, 'diagnosis_result') and workorder.diagnosis_result:
                current_stage = "diagnosis"
                stages.append({
                    "stage": "diagnosis",
                    "status": "completed",
                    "timestamp": workorder.updated_at.isoformat() if workorder.updated_at else None,
                    "findings": workorder.diagnosis_result,
                })
            
            # 修复阶段
            if workorder.status in [WorkOrderStatus.PROCESSING, WorkOrderStatus.COMPLETED]:
                current_stage = "repair"
                stages.append({
                    "stage": "repair",
                    "status": "in_progress" if workorder.status == WorkOrderStatus.PROCESSING else "completed",
                    "timestamp": workorder.updated_at.isoformat() if workorder.updated_at else None,
                })
            
            # 验证阶段（工单完成后）
            if workorder.status == WorkOrderStatus.COMPLETED and alarm.status == AlarmStatus.RESOLVED:
                current_stage = "verification"
                stages.append({
                    "stage": "verification",
                    "status": "passed",
                    "timestamp": alarm.resolved_at.isoformat() if alarm.resolved_at else None,
                })
            
            # 闭环完成
            if alarm.status == AlarmStatus.RESOLVED and workorder.status == WorkOrderStatus.COMPLETED:
                current_stage = "closed"
    
    return WorkflowStatusResponse(
        alert_id=alarm.id,
        workorder_id=alarm.workorder_id,
        current_stage=current_stage,
        stages=stages,
        created_at=alarm.created_at or datetime.now(timezone.utc),
        updated_at=alarm.updated_at or alarm.created_at or datetime.now(timezone.utc),
    )


# ============ 诊断流程 ============

@router.post("/diagnosis", summary="添加诊断结果")
def add_diagnosis(request: DiagnosisRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """添加诊断结果到工单"""
    workorder = db.query(WorkOrder).filter(WorkOrder.id == request.workorder_id).first()
    if not workorder:
        raise HTTPException(status_code=404, detail=f"工单 {request.workorder_id} 不存在")
    _check_station_ownership(db, workorder.station_id, user, f"工单 {request.workorder_id} 不存在")
    
    # 更新工单诊断信息
    workorder.diagnosis_result = {
        "type": request.diagnosis_type,
        "findings": request.findings,
        "root_cause": request.root_cause,
        "suggested_actions": request.suggested_actions,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    workorder.status = WorkOrderStatus.PROCESSING  # 进入处理状态
    workorder.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    cache.delete_pattern("alert_workflow:stats")
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "workorder_id": workorder.id,
            "diagnosis_added": True,
            "status": workorder.status.value,
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


# ============ 修复流程 ============

@router.post("/repair", summary="记录修复操作")
def record_repair(request: RepairRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """记录修复操作"""
    workorder = db.query(WorkOrder).filter(WorkOrder.id == request.workorder_id).first()
    if not workorder:
        raise HTTPException(status_code=404, detail=f"工单 {request.workorder_id} 不存在")
    _check_station_ownership(db, workorder.station_id, user, f"工单 {request.workorder_id} 不存在")
    
    # 记录修复信息
    if not hasattr(workorder, 'repair_log'):
        workorder.repair_log = []
    
    repair_entry = {
        "type": request.repair_type,
        "actions": request.actions_taken,
        "parts_replaced": request.parts_replaced or [],
        "duration_minutes": request.duration_minutes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    workorder.repair_log.append(repair_entry)
    workorder.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    cache.delete_pattern("alert_workflow:stats")
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "workorder_id": workorder.id,
            "repair_recorded": True,
            "total_repairs": len(workorder.repair_log),
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


# ============ 验证与闭环 ============

@router.post("/verify", summary="验证并完成闭环")
def verify_and_close(request: VerificationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """验证修复效果并完成闭环"""
    workorder = db.query(WorkOrder).filter(WorkOrder.id == request.workorder_id).first()
    if not workorder:
        raise HTTPException(status_code=404, detail=f"工单 {request.workorder_id} 不存在")
    _check_station_ownership(db, workorder.station_id, user, f"工单 {request.workorder_id} 不存在")
    
    # 1. 更新工单状态为完成
    workorder.status = WorkOrderStatus.COMPLETED
    workorder.completed_at = datetime.now(timezone.utc)
    workorder.updated_at = datetime.now(timezone.utc)
    
    # 2. 记录验证信息
    workorder.verification_result = {
        "type": request.verification_type,
        "checks_passed": request.checks_passed,
        "health_score_after": request.health_score_after,
        "notes": request.notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # 3. 如果关联了告警，更新告警状态
    alarm = db.query(Alarm).filter(Alarm.workorder_id == workorder.id).first()
    if alarm:
            alarm.status = AlarmStatus.RESOLVED
            alarm.resolved_at = datetime.now(timezone.utc)
            alarm.updated_at = datetime.now(timezone.utc)
            
            # 更新设备健康度
            if request.health_score_after > 0:
                device = db.query(Device).filter(Device.id == alarm.device_id).first()
                if device:
                    device.health_score = request.health_score_after
    
    db.commit()
    cache.delete_pattern("alert_workflow:stats")
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "workorder_id": workorder.id,
            "alert_id": alarm.id if alarm else None,
            "workflow_completed": True,
            "final_health_score": request.health_score_after,
            "checks_passed": request.checks_passed,
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


# ============ 闭环统计 ============

@router.get("/stats", summary="闭环统计")
def get_workflow_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取告警闭环统计数据（团队级仅本队口径，platform admin 全平台口径）"""
    # 卡 占位: 手写显式 cache key 替代 @cached (db 依赖对象致 key 漂移, 缓存永不命中)。
    # 卡 7fd8f66: 统计收敛 team scope, cache key 须含 team 维度段, 防跨队口径串缓存。
    scope = "all" if is_platform_admin(user) else f"team:{user.team_id}"
    cache_key = f"alert_workflow:stats:{scope}"
    if (cached_result := cache.get_json(cache_key)) is not None:
        cached_result["timestamp"] = int(datetime.now(timezone.utc).timestamp())
        return cached_result
    # 统计各类告警数量（team scoped）
    total_alerts = _team_scoped(db, Alarm, user).count()
    active_alerts = _team_scoped(db, Alarm, user).filter(Alarm.status == AlarmStatus.ACTIVE).count()
    resolved_alerts = _team_scoped(db, Alarm, user).filter(Alarm.status == AlarmStatus.RESOLVED).count()

    # 统计有工单的告警
    alerts_with_workorder = _team_scoped(db, Alarm, user).filter(Alarm.workorder_id.isnot(None)).count()

    # 统计工单状态
    total_workorders = _team_scoped(db, WorkOrder, user).count()
    pending_workorders = _team_scoped(db, WorkOrder, user).filter(WorkOrder.status == WorkOrderStatus.PENDING).count()
    completed_workorders = _team_scoped(db, WorkOrder, user).filter(WorkOrder.status == WorkOrderStatus.COMPLETED).count()

    # 计算闭环率
    closed_loop_rate = (resolved_alerts / total_alerts * 100) if total_alerts > 0 else 0

    # 计算平均闭环时间（最近7天）
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_resolved = _team_scoped(db, Alarm, user).filter(
        Alarm.status == AlarmStatus.RESOLVED,
        Alarm.resolved_at >= seven_days_ago
    ).all()
    
    avg_closure_time_hours = 0
    if recent_resolved:
        closure_times = []
        for alarm in recent_resolved:
            if alarm.created_at and alarm.resolved_at:
                hours = (alarm.resolved_at - alarm.created_at).total_seconds() / 3600
                closure_times.append(hours)
        avg_closure_time_hours = sum(closure_times) / len(closure_times) if closure_times else 0

    # 卡 eb0e1afd: 原 return{...} 内联直返, 其后 cacheable/set_json/return 三句死代码
    # (result 未定义) → 缓存写侧瘫痪; 改赋值 result 使缓存写入复活, 对外契约不变。
    result = {
        "code": 200,
        "message": "success",
        "data": {
            "alerts": {
                "total": total_alerts,
                "active": active_alerts,
                "resolved": resolved_alerts,
                "with_workorder": alerts_with_workorder,
            },
            "workorders": {
                "total": total_workorders,
                "pending": pending_workorders,
                "completed": completed_workorders,
            },
            "metrics": {
                "closed_loop_rate": round(closed_loop_rate, 1),
                "avg_closure_time_hours": round(avg_closure_time_hours, 1),
            },
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }
    # timestamp 逐秒变化, 剔除后再入缓存; 命中时回填当下时间戳保持契约不变
    cacheable = {k: v for k, v in result.items() if k != "timestamp"}
    cache.set_json(cache_key, cacheable, expire=30)
    return result


# ============ 后台任务 ============

def notify_urgent_alert(alert_id: int, device_name: str, message: str, severity: str):
    """发送紧急告警通知（后台任务）"""
    logger.info("[通知] 告警 #%s: %s - %s (%s)", alert_id, device_name, message, severity)

    # 构造告警对象用于IM通知
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        alarm = db.query(Alarm).filter(Alarm.id == alert_id).first()
        if alarm and im_notify_service.webhook_url:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(im_notify_service.notify_system_alarm(alarm))
                logger.info("[IM通知] 告警 #%s 通知发送成功", alert_id)
            except Exception as e:
                logger.error("[IM通知] 告警 #%s 发送失败: %s", alert_id, e)
            finally:
                loop.close()
        elif not im_notify_service.webhook_url:
            logger.warning("[IM通知] IM_WEBHOOK_URL 未配置，跳过告警 #%s", alert_id)
    except Exception as e:
        logger.error("[通知] 告警 #%s 处理异常: %s", alert_id, e)
    finally:
        db.close()