"""
用户类型管理 API - P0 运营核心补齐
GET /api/v1/operate/users                    — 用户类型列表（5种类型统一）
GET /api/v1/operate/users/stats              — 用户统计（按类型分组计数）
GET /api/v1/operate/users/by-type/{type}     — 按用户类型筛选
PUT /api/v1/operate/users/{id}               — 编辑运营用户信息
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Literal

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.models.end_user import EndUser
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.api.deps import is_platform_admin, assert_team_access
from app.middleware.permission import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

VALID_USER_TYPES = ["app", "card", "vin", "interconnect", "enterprise"]
VALID_STATUSES = ["active", "inactive", "suspended"]


class UserUpdate(BaseModel):
    """运营用户编辑表单（对齐前端）"""
    username: Optional[str] = None
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[Literal["active", "inactive", "suspended"]] = None


@router.get("/users", summary="用户列表（统一管理）")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_type: Optional[str] = Query(None, description="用户类型筛选: app/card/vin/interconnect/enterprise"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="搜索用户名/手机号"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        q = db.query(User)
        # team scoping（任务卡 ab5c5f17）：非 admin 仅返回本 team 用户。
        if not is_platform_admin(user):
            q = q.filter(User.team_id == user.team_id)
        if user_type:
            q = q.filter(User.role == user_type)
        if status:
            q = q.filter(User.status == status)
        if search:
            q = q.filter(
                (User.username.ilike(f"%{search}%")) |
                (User.phone.ilike(f"%{search}%")) |
                (User.real_name.ilike(f"%{search}%"))
            )
        total = q.count()
        items = q.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = [{
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "phone": u.phone,
            "email": u.email,
            "role": u.role.value if hasattr(u.role, 'value') else str(u.role),
            "status": u.status,
            "last_login": str(u.last_login) if u.last_login else None,
            "created_at": str(u.created_at) if u.created_at else None,
        } for u in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_users 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/users/stats", summary="用户统计（按类型）")
def users_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        stats = {}
        # team scoping（任务卡 ab5c5f17）：非 admin 仅统计本 team 用户。
        scoped = not is_platform_admin(user)

        def _f(q):
            return q.filter(User.team_id == user.team_id) if scoped else q

        # 按角色统计
        all_roles = _f(db.query(User.role, func.count(User.id))).group_by(User.role).all()
        stats["by_role"] = {str(r): c for r, c in all_roles}

        # 按状态统计
        all_statuses = _f(db.query(User.status, func.count(User.id))).group_by(User.status).all()
        stats["by_status"] = {s: c for s, c in all_statuses}

        # 总数
        stats["total"] = _f(db.query(func.count(User.id))).scalar() or 0
        stats["active_count"] = _f(db.query(func.count(User.id)).filter(User.status == "active")).scalar() or 0

        # C端用户类型是契约§8.0载体口径, 与运营 User.role/RBAC 完全隔离
        type_counts = {
            value.value if hasattr(value, "value") else str(value): count
            for value, count in db.query(
                EndUser.user_type, func.count(EndUser.id)
            ).group_by(EndUser.user_type).all()
        }
        type_stats = {t: type_counts.get(t, 0) for t in VALID_USER_TYPES}
        stats["by_user_type"] = type_stats

        return success_response(stats)
    except HTTPException:
        raise
    except Exception:
        logger.exception("users_stats 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.get("/users/by-type/{user_type}", summary="按用户类型筛选")
def users_by_type(
    user_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        if user_type not in VALID_USER_TYPES:
            raise HTTPException(400, f"无效的用户类型: {user_type}，支持: {', '.join(VALID_USER_TYPES)}")

        q = db.query(EndUser).filter(EndUser.user_type == user_type)
        total = q.count()
        items = q.order_by(EndUser.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        data = [{
            "end_user_id": item.id,
            "nickname": item.nickname,
            "avatar_url": item.avatar_url,
            "phone": item.phone,
            "user_type": item.user_type.value if hasattr(item.user_type, 'value') else str(item.user_type),
            "status": item.status.value if hasattr(item.status, 'value') else str(item.status),
            "created_at": str(item.created_at) if item.created_at else None,
        } for item in items]
        return paginated_response(data, total, page, page_size)
    except HTTPException:
        raise
    except Exception:
        logger.exception("users_by_type 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


@router.put("/users/{user_id}", summary="编辑运营用户信息")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("operate:manage")),
):
    try:
        # 1. 查找用户
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, f"用户不存在: id={user_id}")
        # team scoping（任务卡 ab5c5f17）：非 admin 仅可编辑本 team 用户；越权 → 404（不泄露存在）。
        assert_team_access(current_user, user.team_id)

        # 2. 校验 status
        if payload.status is not None and payload.status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"无效的状态值: {payload.status}，支持: {', '.join(VALID_STATUSES)}",
            )

        # 3. 校验 email 格式（空串保护）
        if payload.email is not None and payload.email.strip() == "":
            payload.email = None

        # 4. 更新字段（仅更新提交且非 None 的字段）
        update_data = payload.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        db.commit()
        db.refresh(user)

        return success_response({
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "phone": user.phone,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
            "status": user.status,
            "last_login": str(user.last_login) if user.last_login else None,
            "created_at": str(user.created_at) if user.created_at else None,
        }, message="更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("update_user 异常")
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})