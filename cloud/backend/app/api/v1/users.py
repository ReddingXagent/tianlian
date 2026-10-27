"""
用户模块 - 数据库版
"""
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.core.database import get_db
from app.models.user import User
from app.api.v1.auth import get_current_user, check_password_byte_length
from app.api.deps import team_scope, assert_team_access, is_platform_admin
from app.middleware.permission import require_permission, get_user_permissions

from app.services.audit_service import audit_service
from app.core.response import success_response, paginated_response, action_response

router = APIRouter()


# USING get_db FROM app.core.database


class UserCreate(BaseModel):
    username: str = Field(..., max_length=50)
    password: str
    real_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[Literal["super_admin", "admin", "dispatcher", "station_master", "engineer", "operator", "viewer", "technician", "auditor"]] = "engineer"
    level: Optional[Literal["junior", "middle", "senior"]] = "junior"
    team_id: Optional[int] = None
    status: Optional[Literal["active", "inactive", "suspended"]] = "active"

    @field_validator("password")
    @classmethod
    def _check_password_bytes(cls, v: str) -> str:
        # bcrypt 5.0 >72 字节抛 ValueError → 500, 入口统一 400 (卡 d827fd9a)
        return check_password_byte_length(v)


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[Literal["super_admin", "admin", "dispatcher", "station_master", "engineer", "operator", "viewer", "technician", "auditor"]] = None
    level: Optional[Literal["junior", "middle", "senior"]] = None
    team_id: Optional[int] = None
    status: Optional[Literal["active", "inactive", "suspended"]] = None


class ResetPasswordBody(BaseModel):
    """管理员重置密码请求体 (卡 922b2fba): new_password 可空 → 生成12位随机强密码。"""
    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def _check_password_bytes(cls, v):
        if v is None:
            return v
        return check_password_byte_length(v)


# 临时密码字符集: 大小写字母 + 数字 (12位, secrets CSPRNG)
_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def generate_temporary_password(length: int = 12) -> str:
    """生成一次性强随机临时密码 (卡 922b2fba)。"""
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


# 公开演示账号保护: demo 账户为只读体验账户, 禁止修改参数/删除 (开源演示环境用)
DEMO_LOCKED_USERNAME = "demo"


def ensure_not_demo(user: Optional[User]) -> None:
    """对 demo 演示账户的任何参数变更/删除一律 403 (开源公开演示环境专用)."""
    if user is not None and user.username == DEMO_LOCKED_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="演示账户为只读体验账户，不允许修改或删除",
        )


def reset_user_password(db: Session, user: User, new_password: Optional[str]) -> dict:
    """重置用户密码共享逻辑 (users/tenants 两路由复用, 卡 922b2fba)。

    - new_password 空 → 生成 12 位随机密码, 明文一次性返回 {temporary_password}
    - 递增 token_version 驱逐全部已签发 token/刷新会话 (与 auth.password_reset 同口径)
    - 写审计日志
    """
    from app.api.v1.auth import get_password_hash

    temporary = None
    if new_password:
        get_password_hash(new_password)  # 校验+hash (内部含 72 字节守卫)
        user.password_hash = get_password_hash(new_password)
    else:
        temporary = generate_temporary_password()
        user.password_hash = get_password_hash(temporary)
    # 改密驱逐: 旧 access token 立即失效, refresh 无法续期 (卡 5d6a978b 同口径)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    db.refresh(user)

    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="update", module="users",
            target_id=str(user.id),
            target_desc=f"管理员重置密码:{user.username}",
        )
    except Exception:
        pass

    if temporary is not None:
        return {"temporary_password": temporary, "message": "已生成临时密码, 请立即转交用户并提醒登录后修改"}
    return {"message": "密码已重置"}


def _user_to_dict(user: User) -> dict:
    """User ORM → dict"""
    team_name = None
    if user.team_id:
        team = user.team
        if team:
            team_name = team.name

    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "phone": user.phone,
        "role": user.role.value if user.role else "engineer",
        "level": user.level.value if user.level else "junior",
        "team_id": user.team_id,
        "team_name": team_name,
        "status": user.status,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get("")
def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    team_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用户列表

    卡 2d34e5c1: team_id 服务端强制——团队级用户仅可见本 team 用户
    （query team_id 被忽略）；admin/平台级可按 team_id 筛选或看全部。
    """
    query = db.query(User)

    scope = team_scope(current_user)
    if scope is not None:
        query = query.filter(User.team_id == scope)
    elif team_id is not None:
        query = query.filter(User.team_id == team_id)

    if keyword:
        query = query.filter(
            User.username.contains(keyword) | User.real_name.contains(keyword)
        )

    if role:
        from app.models.user import UserRole
        try:
            query = query.filter(User.role == UserRole(role))
        except ValueError:
            pass

    if status:
        query = query.filter(User.status == status)

    total = query.count()
    items = query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return paginated_response(
        [_user_to_dict(u) for u in items],
        total, page, page_size
    )


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用户详情"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 卡 2d34e5c1: 团队级用户跨团队 → 404 不泄露存在
    assert_team_access(current_user, user.team_id)

    result = _user_to_dict(user)
    # 添加权限信息（基于角色）
    result["permissions"] = _get_permissions_by_role(user.role.value if user.role else "engineer")
    return success_response(result)


@router.post("")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("user:create")),
):
    """创建用户"""
    from app.models.user import UserRole, EngineerLevel
    from app.api.v1.auth import get_password_hash

    # 卡 a3750a42: 非平台管理员禁止铸造 admin/super_admin 账号
    if user.role in ("admin", "super_admin") and not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="仅平台管理员可创建管理员账号")

    # 检查username唯一性
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"用户名 {user.username} 已存在")

    # 密码加密 (bcrypt, 与 auth.py/engineers.py 一致)
    password_hash = get_password_hash(user.password)

    new_user = User(
        username=user.username,
        password_hash=password_hash,
        real_name=user.real_name,
        phone=user.phone,
        role=UserRole(user.role) if user.role else UserRole.ENGINEER,
        level=EngineerLevel(user.level) if user.level else EngineerLevel.JUNIOR,
        team_id=user.team_id,
        status=user.status or "active",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=new_user.id, username=new_user.username,
            action="create", module="users",
            target_id=str(new_user.id), target_desc=f"创建用户:{new_user.username}",
        )
    except Exception:
        pass
    return success_response(_user_to_dict(new_user))


@router.put("/{user_id}")
def update_user(
    user_id: int,
    user: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("user:edit")),
):
    """更新用户"""
    existing = db.query(User).filter(User.id == user_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")
    ensure_not_demo(existing)

    # 卡 4b499911: team scoping——团队级用户跨团队编辑 → 404 不泄露存在
    if not is_platform_admin(current_user):
        assert_team_access(current_user, existing.team_id)

    update_data = user.model_dump(exclude_unset=True)

    # 卡 4b499911: 批量赋值维度——非平台管理员禁止改归属 (team_id 静默弹出)
    if not is_platform_admin(current_user):
        update_data.pop("team_id", None)

    # 卡 a3750a42: 改 role 是高危操作 — 需持 user:role 权限或为平台管理员;
    # 且禁止自我提权 (目标角色高于当前角色 → 403)
    if "role" in update_data and update_data["role"]:
        from app.models.user import UserRole
        if not (
            is_platform_admin(current_user)
            or "user:role" in get_user_permissions(current_user)
        ):
            raise HTTPException(status_code=403, detail="仅平台管理员或持有用户角色管理权限可修改用户角色")
        if existing.id == current_user.id:
            new_role = UserRole(update_data["role"])
            current_role = current_user.role if isinstance(current_user.role, UserRole) else UserRole(str(current_user.role.value))
            if list(UserRole).index(new_role) < list(UserRole).index(current_role):
                raise HTTPException(status_code=403, detail="不能将自身的角色提升为更高权限角色")

    for key, value in update_data.items():
        if key in ("role", "level") and value:
            from app.models.user import UserRole, EngineerLevel
            if key == "role":
                value = UserRole(value)
            else:
                value = EngineerLevel(value)
        setattr(existing, key, value)

    db.commit()
    db.refresh(existing)
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=existing.id, username=existing.username,
            action="update", module="users",
            target_id=str(existing.id), target_desc=f"更新用户:{existing.username}",
            detail=str(update_data)[:500],
        )
    except Exception:
        pass
    return success_response(_user_to_dict(existing))


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("user:delete")),
):
    """删除用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    ensure_not_demo(user)

    # 卡 21205721: 服务层显式级联（api_key/on_call_shift/on_call_log 级联删,
    # 工单/告警/维保/站点/知识库等历史引用置空保留）
    from app.services.fk_cascade import purge_user_children
    purge_user_children(db, user_id)

    db.delete(user)
    db.commit()
    # 审计日志
    try:
        audit_service.log_crud(
            user_id=user.id, username=user.username,
            action="delete", module="users",
            target_id=str(user.id), target_desc=f"删除用户:{user.username}",
        )
    except Exception:
        pass
    return action_response(success=True, message=f"用户 {user_id} 已删除")


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    body: ResetPasswordBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员重置用户密码 (卡 922b2fba)。

    - 仅平台管理员 (admin/super_admin), 其余 403
    - new_password 空 → 12 位随机强密码, 明文一次性返回 temporary_password
    - 递增 token_version 驱逐该用户全部已签发 token / 刷新会话
    """
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=403, detail="仅平台管理员可重置用户密码")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    ensure_not_demo(user)
    result = reset_user_password(db, user, body.new_password)
    return success_response(result)


def _get_permissions_by_role(role: str) -> list:
    """根据角色获取权限"""
    permissions_map = {
        "admin": [
            "device:view", "device:create", "device:edit", "device:delete", "device:control",
            "workorder:view", "workorder:create", "workorder:edit", "workorder:delete", "workorder:assign",
            "alarm:view", "alarm:process", "alarm:delete",
            "station:view", "station:create", "station:edit", "station:delete",
            "user:view", "user:create", "user:edit", "user:delete", "user:role",
        ],
        "manager": [
            "device:view", "device:control",
            "workorder:view", "workorder:create", "workorder:assign",
            "alarm:view", "alarm:process",
            "station:view", "station:create", "station:edit",
        ],
        "engineer": [
            "device:view", "device:control",
            "workorder:view", "workorder:create",
            "alarm:view", "alarm:process",
        ],
        "viewer": [
            "device:view",
            "workorder:view",
            "alarm:view",
            "station:view",
        ],
    }
    return permissions_map.get(role, [])
