"""
安全模块 - 通用认证依赖
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User


def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """验证当前用户是否为管理员"""
    user_role = current_user.role if isinstance(current_user.role, str) else current_user.role.value
    if user_role.upper() not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员角色",
        )
    return current_user