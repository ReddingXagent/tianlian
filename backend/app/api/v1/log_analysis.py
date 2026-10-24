"""
AI 智能日志分析 API - 故障自动诊断

功能：
- POST /analyze - 手动输入日志分析
- GET /model_config - 获取当前AI模型配置
- POST /model_config - 更新AI模型配置
- GET /model_config/task-mappings - 获取任务映射
- PUT /model_config/task-mapping - 更新任务映射
- GET /alarm/{alarm_id} - 获取告警的诊断结果
- POST /trigger/{alarm_id} - 触发告警自动诊断
- GET /{analysis_id} - 获取诊断结果
- GET / - 列出诊断历史
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.models.ai_diagnosis import AIDiagnosisRecord, DiagnosisStatus
from app.models.alarm import Alarm
from app.models.device import Device
from app.models.station import Station
from app.services.ai_diagnosis import analyze_device_logs
from app.services.diagnostic_pipeline import trigger_diagnosis
from app.services.ai_model_config import model_manager
from app.core.response import success_response, paginated_response
from app.api.deps import (
    is_platform_admin, assert_device_team_access, assert_alarm_team_access, assert_station_team_access,
)
from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("healing:manage"))])


def _team_station_ids(db: Session, user):
    """本 team 站点 id 列表；admin/super_admin 返回 None（不过滤，平台级全可见）。
    任务卡 1c19b59a team scoping。"""
    if is_platform_admin(user):
        return None
    rows = db.query(Station.id).filter(Station.team_id == user.team_id).all()
    return [r[0] for r in rows]


# USING get_db FROM app.core.database


# ========== Schema ==========

class AnalyzeManualRequest(BaseModel):
    """手动分析请求"""
    device_id: int
    logs: List[str]
    fault_code: Optional[str] = None
    fault_description: Optional[str] = None


class BatchAnalysisRequest(BaseModel):
    """批量分析请求"""
    device_ids: List[int]
    task_type: str = "log_analysis"


class ProviderConfig(BaseModel):
    """Provider配置"""
    provider: str
    model_id: str
    name: str
    base_url: str
    api_key: str = ""
    enabled: bool = True


class TaskMappingConfig(BaseModel):
    """任务映射"""
    task_type: str
    model_name: str


# ========== API ==========

# --- 注意: 具体路径路由必须在参数化路由之前注册 ---
# 例如 GET /model_config 必须在 GET /{analysis_id} 之前

@router.post("/analyze", summary="手动分析日志")
def manual_analyze(data: AnalyzeManualRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """手动输入日志进行分析"""
    # team scoping（任务卡 1c19b59a）：设备归属校验前置，跨团队 → 404。
    assert_device_team_access(db, data.device_id, current_user)
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    station = db.query(Station).filter(Station.id == device.station_id).first()
    device_info = {c.name: getattr(device, c.name) for c in device.__table__.columns}
    if station:
        device_info["station_name"] = station.name
    else:
        device_info["station_name"] = "未知站点"
    
    fault_ctx = None
    if data.fault_code or data.fault_description:
        fault_ctx = {
            "fault_code": data.fault_code or "",
            "content": data.fault_description or "",
            "level": "manual",
        }

    # 外部 AI 调用: 网络故障/超时/上游异常统一兜底, 不冒泡裸堆栈。
    try:
        result = analyze_device_logs(device_info, data.logs, fault_ctx)
    except Exception:
        logger.exception("AI 日志分析调用失败 device_id=%s", data.device_id)
        raise HTTPException(status_code=500, detail="AI 分析服务暂时不可用")

    # 保存到数据库
    record = AIDiagnosisRecord(
        device_id=data.device_id,
        station_id=device.station_id,
        status=DiagnosisStatus.COMPLETED if result["success"] else DiagnosisStatus.FAILED,
        trigger_type="manual",
        log_source="manual_paste",
        raw_log="\n".join(data.logs),
        raw_ai_response=result.get("raw_response"),
        duration_ms=result.get("duration_ms"),
        error_message=result.get("error"),
        completed_at=datetime.now(timezone.utc),
    )

    if result["success"] and result["result"]:
        r = result["result"]
        record.fault_type = r.get("fault_type")
        record.fault_location = r.get("fault_location")
        record.root_cause = r.get("root_cause")
        record.severity = r.get("severity")
        record.confidence = r.get("confidence")
        record.immediate_actions = r.get("immediate_actions")
        record.repair_suggestions = r.get("repair_suggestions")
        record.preventive_measures = r.get("preventive_measures")
        record.remote_fixable = r.get("remote_fixable", False)

    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.exception("AI 诊断记录写入冲突 device_id=%s", data.device_id)
        raise HTTPException(status_code=409, detail="诊断记录写入冲突")
    except Exception:
        db.rollback()
        logger.exception("AI 诊断记录写入失败 device_id=%s", data.device_id)
        raise HTTPException(status_code=500, detail="内部错误")
    db.refresh(record)

    return success_response({
        "record_id": record.id,
        "analysis": result.get("result") if result["success"] else None,
        "error": result.get("error"),
        "model_used": result.get("model_used"),
        "duration_ms": result.get("duration_ms"),
    }, message="分析完成" if result["success"] else "分析失败")


# --- 模型配置路由（具体路径，必须放在参数化路径之前）---

@router.get("/model_config", summary="获取AI模型配置")
def get_model_config():
    """获取当前AI模型配置"""
    return model_manager.to_config_dict()


@router.post("/model_config", summary="更新AI模型配置")
def update_model_config(providers: List[ProviderConfig]):
    """更新AI模型provider列表"""
    providers_list = [p.model_dump() for p in providers]
    model_manager.update_providers(providers_list)
    return success_response(message="模型配置已更新")


@router.get("/model_config/task-mappings", summary="获取任务映射")
def get_task_mappings():
    """获取所有任务映射"""
    return model_manager.get_all_mappings()


@router.put("/model_config/task-mapping", summary="更新任务映射")
def update_task_mapping(mapping: TaskMappingConfig):
    """更新任务-模型映射"""
    model_manager.update_task_mapping(mapping.task_type, mapping.model_name)
    return success_response(message=f"任务 {mapping.task_type} → {mapping.model_name}")


# --- 告警诊断路由 ---

@router.get("/alarm/{alarm_id}", summary="获取告警的诊断")
def get_alarm_analysis(alarm_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """获取指定告警关联的诊断结果"""
    # team scoping（任务卡 1c19b59a）：告警存在则校验归属（跨团队→404）；不存在的告警
    # 走既有契约（has_diagnosis=False，不泄露存在性）。
    if db.query(Alarm.id).filter(Alarm.id == alarm_id).first():
        assert_alarm_team_access(db, alarm_id, current_user)
    record = db.query(AIDiagnosisRecord).filter(
        AIDiagnosisRecord.alarm_id == alarm_id
    ).order_by(desc(AIDiagnosisRecord.created_at)).first()
    if not record:
        return success_response({"has_diagnosis": False})
    result = record.to_dict()
    result["has_diagnosis"] = True
    return success_response(result)


@router.post("/trigger/{alarm_id}", summary="触发告警诊断")
def trigger_alarm_diagnosis(alarm_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """为指定告警触发AI诊断"""
    # team scoping（任务卡 1c19b59a）：告警存在则校验归属（跨团队→404）；不存在的告警
    # 走既有契约（trigger 失败→500，不泄露存在性）。
    if db.query(Alarm.id).filter(Alarm.id == alarm_id).first():
        assert_alarm_team_access(db, alarm_id, current_user)
    # 外部诊断管道调用: 异常统一兜底, 不冒泡裸堆栈。
    try:
        result = trigger_diagnosis(alarm_id, trigger_type="manual", db=db)
    except Exception:
        logger.exception("触发告警诊断失败 alarm_id=%s", alarm_id)
        raise HTTPException(status_code=500, detail="诊断服务暂时不可用")
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "诊断失败"))
    return result


# --- 参数化路由 ---

@router.get("/{analysis_id}", summary="获取诊断结果")
def get_analysis(analysis_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """获取诊断结果详情"""
    record = db.query(AIDiagnosisRecord).filter(AIDiagnosisRecord.id == analysis_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="诊断记录不存在")
    # team scoping（任务卡 1c19b59a）：经 station_id 校验归属，跨团队 → 404。
    assert_station_team_access(db, record.station_id, current_user)
    return record.to_dict()


@router.get("", summary="诊断历史列表")
def list_analysis(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取诊断历史列表"""
    query = db.query(AIDiagnosisRecord)
    # team scoping（任务卡 1c19b59a）：非 admin 仅本 team 站点诊断记录。
    sids = _team_station_ids(db, current_user)
    if sids is not None:
        query = query.filter(AIDiagnosisRecord.station_id.in_(sids))
    if status:
        query = query.filter(AIDiagnosisRecord.status == status)
    if device_id:
        query = query.filter(AIDiagnosisRecord.device_id == device_id)
    
    total = query.count()
    items = query.order_by(desc(AIDiagnosisRecord.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return paginated_response([item.to_dict() for item in items], total, page, page_size)