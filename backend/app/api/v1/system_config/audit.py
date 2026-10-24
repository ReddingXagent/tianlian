"""
系统配置 - 日志审计域
/audit/logs, /audit/logs/stats, /audit/logs/export,
/audit/actions, /audit/modules
"""
from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.v1.reports.export import _sanitize_cell
from app.models.user import User
from app.models.audit_log import AuditLog, AuditAction, AuditModule
from app.core.response import success_response, paginated_response
from app.services.audit_service import audit_service
from app.tasks.tz_utils import biz_day_bounds_utc_naive, today_in_biz_tz

from .common import _check_admin_or_permission

router = APIRouter(tags=["系统配置"], dependencies=[Depends(get_current_user)])

logger = logging.getLogger(__name__)


class AuditLogQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    action: Optional[str] = None
    module: Optional[str] = None
    username: Optional[str] = None
    result: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@router.get("/audit/logs")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    module: Optional[str] = None,
    username: Optional[str] = None,
    result: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取审计日志列表"""
    try:
        _check_admin_or_permission(current_user, "audit:view")

        query = db.query(AuditLog)

        if action:
            query = query.filter(AuditLog.action == action)
        if module:
            query = query.filter(AuditLog.module == module)
        if username:
            query = query.filter(AuditLog.username.ilike(f"%{username}%"))
        if result:
            query = query.filter(AuditLog.result == result)
        if start_time:
            query = query.filter(AuditLog.timestamp >= start_time)
        if end_time:
            query = query.filter(AuditLog.timestamp <= end_time)

        total = query.count()
        items = query.order_by(desc(AuditLog.timestamp)).offset((page - 1) * page_size).limit(page_size).all()

        return paginated_response(
            items=[item.to_dict() for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_audit_logs 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/audit/logs/stats")
def get_audit_log_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取审计日志统计"""
    try:
        _check_admin_or_permission(current_user, "audit:view")

        # 卡 77b1ed08: 今日统计按业务时区(上海)墙钟日界 (参照 dashboard.py:47),
        # 旧 func.date(UTC时间戳)==UTC今天 在上海 00:00-08:00 窗口错位 8h;
        # 改业务日换算的 naive-UTC 闭开时间窗直接比较 timestamp。
        day_start, day_end = biz_day_bounds_utc_naive(today_in_biz_tz())
        total = db.query(AuditLog).count()
        today_count = db.query(AuditLog).filter(
            AuditLog.timestamp >= day_start, AuditLog.timestamp < day_end
        ).count()

        by_action = dict(db.query(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action).all())
        by_module = dict(db.query(AuditLog.module, func.count(AuditLog.id)).group_by(AuditLog.module).all())
        failed = db.query(AuditLog).filter(AuditLog.result == "failure").count()

        return success_response({
            "total_logs": total,
            "today_logs": today_count,
            "failed_logs": failed,
            "by_action": by_action,
            "by_module": by_module,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_audit_log_stats 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/audit/logs/export")
def export_audit_logs(
    action: Optional[str] = None,
    module: Optional[str] = None,
    username: Optional[str] = None,
    result: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出审计日志"""
    try:
        _check_admin_or_permission(current_user, "audit:export")

        query = db.query(AuditLog)
        if action:
            query = query.filter(AuditLog.action == action)
        if module:
            query = query.filter(AuditLog.module == module)
        if username:
            query = query.filter(AuditLog.username.ilike(f"%{username}%"))
        if result:
            query = query.filter(AuditLog.result == result)
        if start_time:
            query = query.filter(AuditLog.timestamp >= start_time)
        if end_time:
            query = query.filter(AuditLog.timestamp <= end_time)

        # 限制导出最大行数
        items = query.order_by(desc(AuditLog.timestamp)).limit(10000).all()

        audit_service.log_crud(
            user_id=current_user.id,
            username=current_user.username,
            action="export",
            module="system_config",
            target_desc=f"导出审计日志 {len(items)} 条",
        )

        data = [item.to_dict() for item in items]

        if format == "csv":
            import csv
            import io
            output = io.StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(
                    {k: _sanitize_cell(v) for k, v in row.items()} for row in data
                )
            return success_response({
                "content": output.getvalue(),
                "filename": f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                "content_type": "text/csv",
            })

        return success_response({
            "content": data,
            "filename": f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json",
            "content_type": "application/json",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_audit_logs 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/audit/actions")
async def get_audit_actions():
    """获取可用的审计动作列表"""
    try:
        return success_response({
            "actions": [a.value for a in AuditAction],
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_audit_actions 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")


@router.get("/audit/modules")
async def get_audit_modules():
    """获取可用的审计模块列表"""
    try:
        return success_response({
            "modules": [m.value for m in AuditModule],
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_audit_modules 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
