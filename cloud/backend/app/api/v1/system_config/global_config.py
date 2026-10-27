"""
系统配置 - 全局配置域 (admin spec §2.3)
/global (GET/PUT)
JSON 配置存取复用 common._load_json_config / _save_json_config
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.api.deps import assert_config_domain_access
from app.models.user import User
from app.core.response import success_response
from app.services.audit_service import audit_service

from .common import _check_admin_or_permission, _load_json_config, _save_json_config

router = APIRouter(tags=["系统配置"])


DEFAULT_GLOBAL_CONFIG = {
    "system_name": "天链云平台",
    "logo_url": "",
    "copyright": "© 2024 天链科技. All rights reserved.",
    "login_bg_url": "",
    "language": "zh-CN",
}


class GlobalConfigUpdate(BaseModel):
    system_name: Optional[str] = Field(None, max_length=100)
    logo_url: Optional[str] = Field(None, max_length=500)
    copyright: Optional[str] = Field(None, max_length=300)
    login_bg_url: Optional[str] = Field(None, max_length=500)
    language: Optional[str] = Field(None, max_length=20)


@router.get("/global")
async def get_global_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取全局配置 (system 域: 平台管理员 + ops_company 可读)"""
    assert_config_domain_access(db, current_user, "system")
    config = _load_json_config(db, "global_config", DEFAULT_GLOBAL_CONFIG)
    return success_response(config)


@router.put("/global")
def update_global_config(
    data: GlobalConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新全局配置 (system 域: 平台管理员 + ops_company 可写)"""
    assert_config_domain_access(db, current_user, "system")
    _check_admin_or_permission(current_user, "system:config")

    config = _load_json_config(db, "global_config", DEFAULT_GLOBAL_CONFIG)
    updates = data.dict(exclude_none=True)
    old_value = dict(config)
    config.update(updates)
    _save_json_config(db, "global_config", config, "global")
    db.commit()

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        module="system_config",
        target_desc="更新全局配置",
        old_value=str(old_value),
        new_value=str(config),
    )

    return success_response(config, message="全局配置已更新")
