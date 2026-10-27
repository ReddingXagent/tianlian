"""
操作日志/审计日志 API - 数据库版
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.api.v1.auth import get_current_user
from app.api.v1.system_config.common import _check_admin_or_permission
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.database import get_db
from app.core.response import success_response, paginated_response

router = APIRouter()


@router.get("")
async def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    module: Optional[str] = None,
    username: Optional[str] = None,
    result: Optional[str] = None,
    hours: Optional[int] = Query(None, ge=1, le=720, description="最近N小时(边界1~720)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取操作/审计日志"""
    _check_admin_or_permission(current_user, "audit:view")
    result = audit_service.get_logs(
        page=page, page_size=page_size,
        action=action, module=module,
        username=username, result=result,
        hours=hours,
        db=db,
    )
    return paginated_response(
        items=result.get('items', []),
        total=result.get('total', 0),
        page=result.get('page', page),
        page_size=result.get('page_size', page_size)
    )


@router.get("/stats")
async def get_log_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取日志统计"""
    _check_admin_or_permission(current_user, "audit:view")
    return success_response(audit_service.get_stats(db=db))
