"""
系统配置 - 共享依赖层
权限校验 / JSON 配置存取（system_configs 表）
被各业务域子模块复用，避免重复实现。
"""
import json
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.api.deps import is_platform_admin
from app.models.system_config import SystemConfig
from app.models.user import User
from app.middleware.permission import get_user_permissions


def _check_admin_or_permission(current_user: User, perm: str):
    role_val = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role_val in ("admin", "super_admin"):
        return True
    perms = get_user_permissions(current_user)
    if perm not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"权限不足，需要: {perm}",
        )
    return True


def _load_json_config(db: Session, config_key: str, default: dict) -> dict:
    """从 system_configs 表读取 JSON 配置"""
    row = db.execute(
        text("SELECT config_value FROM system_configs WHERE config_key = :k"),
        {"k": config_key},
    ).first()
    if row and row[0]:
        try:
            val = row[0] if isinstance(row[0], str) else str(row[0])
            data = json.loads(val)
            if isinstance(data, dict):
                merged = {**default, **data}
                return merged
        except Exception:
            pass
    return dict(default)


def _save_json_config(db: Session, config_key: str, config_value: dict, config_type: str = "global"):
    """保存 JSON 配置到 system_configs 表 (upsert)"""
    val_json = json.dumps(config_value, ensure_ascii=False)
    existing = db.execute(
        text("SELECT id FROM system_configs WHERE config_key = :k"),
        {"k": config_key},
    ).first()
    if existing:
        db.execute(
            text("UPDATE system_configs SET config_value = :v, updated_at = CURRENT_TIMESTAMP WHERE config_key = :k"),
            {"v": val_json, "k": config_key},
        )
    else:
        db.execute(
            text("INSERT INTO system_configs (config_key, config_value, type, created_at, updated_at) VALUES (:k, :v, :t, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
            {"k": config_key, "v": val_json, "t": config_type},
        )


def list_system_configs_for_team(db: Session, user: User) -> List[SystemConfig]:
    """按 team 维度列出 system_configs (卡 cf614348 team_id 隔离)。

    - 平台管理员 → 全部配置;
    - 团队级用户 → 仅本 team (team_id == user.team_id) + 平台共享 (team_id IS NULL),
      乙公司配置不可见。

    走 ORM (SystemConfig), 与 raw SQL 的 _load/_save 互不影响。
    """
    query = db.query(SystemConfig)
    if not is_platform_admin(user):
        if user.team_id is None:
            # 无团队用户: 仅平台共享
            query = query.filter(SystemConfig.team_id.is_(None))
        else:
            query = query.filter(
                or_(
                    SystemConfig.team_id.is_(None),
                    SystemConfig.team_id == user.team_id,
                )
            )
    return query.all()
