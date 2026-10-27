"""
Celery 异步任务管理 API
Phase 4 - 任务提交、状态查询
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

from app.core.celery_app import celery_app, get_celery_status, CELERY_AVAILABLE
from app.middleware.permission import require_write_permission

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_write_permission("analytics:manage"))])


# ============ Schemas ============

class TaskSubmitRequest(BaseModel):
    """通用任务提交请求"""
    task_type: str  # health_score / efficiency_analysis / train_model / predict_faults
    params: Dict[str, Any] = {}

class TaskSubmitResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    message: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # PENDING / STARTED / SUCCESS / FAILURE / RETRY
    result: Optional[Any] = None
    error: Optional[str] = None
    runtime_seconds: Optional[float] = None


# ============ 任务类型映射 ============

TASK_MAP = {
    "health_score": "app.tasks.analytics_tasks.calculate_health_score_task",
    "efficiency_analysis": "app.tasks.analytics_tasks.analyze_efficiency_task",
    "batch_health_report": "app.tasks.analytics_tasks.batch_health_report_task",
    "train_model": "app.tasks.maintenance_tasks.train_model_task",
    "predict_faults": "app.tasks.maintenance_tasks.predict_faults_task",
}


# ============ API 路由 ============

@router.get("/status", summary="Celery Worker状态")
async def get_worker_status():
    """获取Celery worker运行状态"""
    status = get_celery_status()
    return {
        "code": 200,
        "message": "success",
        "data": status,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


@router.post("/submit", summary="提交异步任务")
async def submit_task(request: TaskSubmitRequest):
    """提交异步任务"""
    # 检查Celery是否可用
    if not CELERY_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Celery未安装，异步任务功能不可用。请安装: pip install celery"
        )
    
    task_name = TASK_MAP.get(request.task_type)
    if not task_name:
        raise HTTPException(status_code=400, detail=f"不支持的任务类型: {request.task_type}，可选: {list(TASK_MAP.keys())}")

    try:
        task_func = celery_app.tasks[task_name]
    except KeyError:
        raise HTTPException(status_code=503, detail=f"任务函数未注册: {task_name}，请确认Celery worker已启动")

    # 提交任务
    params = request.params
    result = task_func.delay(**params)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "task_id": result.id,
            "task_type": request.task_type,
            "status": "SUBMITTED",
            "message": f"任务已提交: {request.task_type}",
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


@router.get("/result/{task_id}", summary="查询任务结果")
async def get_task_result(task_id: str):
    """查询异步任务执行结果"""
    result = celery_app.AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "status": result.status,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    if hasattr(result, "date_done") and result.date_done:
        response["completed_at"] = result.date_done.isoformat()

    return {
        "code": 200,
        "message": "success",
        "data": response,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


@router.post("/cancel/{task_id}", summary="取消任务")
async def cancel_task(task_id: str):
    """撤销已提交的任务"""
    result = celery_app.AsyncResult(task_id)
    result.revoke(terminate=True)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "task_id": task_id,
            "status": "REVOKED",
            "message": "任务已取消",
        },
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }


@router.get("/types", summary="可用任务类型")
async def list_task_types():
    """列出所有可用的异步任务类型"""
    types = []
    for key, full_name in TASK_MAP.items():
        types.append({
            "type": key,
            "full_name": full_name,
            "description": {
                "health_score": "计算设备健康度评分",
                "efficiency_analysis": "能效分析",
                "batch_health_report": "批量生成设备健康报告",
                "train_model": "训练ML模型",
                "predict_faults": "故障预测",
            }.get(key, ""),
        })

    return {
        "code": 200,
        "message": "success",
        "data": types,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }
