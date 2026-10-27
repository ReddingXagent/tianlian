"""
权限管理 API — 数据库版 (使用 SQLAlchemy RoleTable/PermissionTable)
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.user import User, UserRole as UserRoleEnum
from app.models.rbac import (
    RoleTable, PermissionTable, Permission,
    user_role_table,
)
from app.api.v1.auth import get_current_user, require_role
from app.middleware.permission import get_user_permissions
from app.core.response import success_response, action_response
from app.services.audit_service import audit_service

router = APIRouter(dependencies=[Depends(require_role("admin"))])


class RoleCreateSchema(BaseModel):
    name: str
    display_name: str = Field(..., max_length=100)
    description: Optional[str] = ""
    permissions: list[str] = []

class RoleUpdateSchema(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[list[str]] = None

class UserRoleUpdateSchema(BaseModel):
    role: Literal["super_admin", "admin", "dispatcher", "station_master", "engineer", "operator", "viewer", "technician", "auditor"]
    extra_role_ids: Optional[list[int]] = None


def _check_admin_or_permission(current_user: User, perm: str):
    """简化权限检查（避免循环依赖）"""
    role_val = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role_val == "admin":
        return True
    perms = get_user_permissions(current_user)
    if perm not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"权限不足，需要: {perm}",
        )
    return True


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    """获取角色列表"""
    role_rows = db.query(RoleTable).order_by(RoleTable.id).all()
    user_count_map = _get_role_user_counts(db)

    items = []
    for r in role_rows:
        items.append({
            "id": r.id,
            "name": r.name,
            "display_name": r.display_name,
            "description": r.description,
            "is_system": bool(r.is_system),
            "permissions": sorted(set(p.name for p in r.permissions)),
            "user_count": user_count_map.get(r.name, 0),
        })
    return success_response({"items": items})


@router.get("/roles/{role_id}")
def get_role(role_id: int, db: Session = Depends(get_db)):
    """获取角色详情"""
    role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="角色不存在")
    return success_response({
        "id": role_row.id,
        "name": role_row.name,
        "display_name": role_row.display_name,
        "description": role_row.description,
        "is_system": bool(role_row.is_system),
        "permissions": sorted(set(p.name for p in role_row.permissions)),
    })


@router.post("/roles")
def create_role(
    data: RoleCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建自定义角色"""
    _check_admin_or_permission(current_user, "system:role")
    existing = db.query(RoleTable).filter(RoleTable.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="角色名已存在")

    role_row = RoleTable(
        name=data.name,
        display_name=data.display_name,
        description=data.description or "",
        is_system=0,
    )
    db.add(role_row)
    db.flush()

    if data.permissions:
        perms = db.query(PermissionTable).filter(
            PermissionTable.name.in_(data.permissions)
        ).all()
        role_row.permissions = perms

    db.commit()
    db.refresh(role_row)
    return success_response({
        "id": role_row.id,
        "name": role_row.name,
        "display_name": role_row.display_name,
        "permissions": sorted(set(p.name for p in role_row.permissions)),
    })


@router.put("/roles/{role_id}")
def update_role(
    role_id: int,
    data: RoleUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新角色"""
    _check_admin_or_permission(current_user, "system:role")
    role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="角色不存在")

    if data.display_name is not None:
        role_row.display_name = data.display_name
    if data.description is not None:
        role_row.description = data.description
    if data.permissions is not None:
        perms = db.query(PermissionTable).filter(
            PermissionTable.name.in_(data.permissions)
        ).all()
        role_row.permissions = perms

    db.commit()
    db.refresh(role_row)
    return success_response({
        "id": role_row.id,
        "name": role_row.name,
        "display_name": role_row.display_name,
        "permissions": sorted(set(p.name for p in role_row.permissions)),
    })


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除角色（系统内置角色不可删除）"""
    _check_admin_or_permission(current_user, "system:role")
    role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role_row.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不可删除")

    db.delete(role_row)
    db.commit()
    return action_response(success=True, message=f"角色 {role_row.display_name} 已删除")


@router.get("/permissions")
async def list_permissions():
    """获取所有权限列表"""
    items = [
        {
            "name": p.value,
            "resource": p.value.split(":")[0] if ":" in p.value else "",
            "action": p.value.split(":")[1] if ":" in p.value else "",
            "label": _get_permission_label(p),
        }
        for p in Permission
    ]
    return success_response({"items": items})


@router.get("/users")
def list_rbac_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取用户列表 (含角色和权限信息，分页返回)"""
    query = db.query(User).options(
        selectinload(User.assigned_roles).selectinload(RoleTable.permissions)
    )
    total = query.count()
    users = query.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for u in users:
        role_val = u.role.value if hasattr(u.role, 'value') else u.role
        extra_roles = []
        if hasattr(u, 'assigned_roles') and u.assigned_roles:
            extra_roles = [
                {"id": r.id, "name": r.name, "display_name": r.display_name}
                for r in u.assigned_roles if r.name != role_val
            ]
        items.append({
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "role": role_val,
            "role_label": _get_role_label(role_val),
            "extra_roles": extra_roles,
            "status": u.status,
            "permissions": get_user_permissions(u),
        })
    return success_response({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/users/{user_id}")
def get_rbac_user(user_id: int, db: Session = Depends(get_db)):
    """获取用户详细权限信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    role_val = user.role.value if hasattr(user.role, 'value') else user.role
    extra_roles = []
    if hasattr(user, 'assigned_roles') and user.assigned_roles:
        extra_roles = [
            {"id": r.id, "name": r.name, "display_name": r.display_name}
            for r in user.assigned_roles if r.name != role_val
        ]
    return success_response({
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": role_val,
        "role_label": _get_role_label(role_val),
        "extra_roles": extra_roles,
        "permissions": get_user_permissions(user),
        "status": user.status,
    })


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    data: UserRoleUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新用户角色"""
    _check_admin_or_permission(current_user, "user:role")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    try:
        user.role = UserRoleEnum(data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的角色: {data.role}")

    if data.extra_role_ids is not None:
        extra_roles = db.query(RoleTable).filter(
            RoleTable.id.in_(data.extra_role_ids)
        ).all()
        user.assigned_roles = extra_roles

    db.commit()
    db.refresh(user)

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        module="rbac",
        target_id=str(user_id),
        target_desc=f"更新用户 {user.username} 角色为 {data.role}",
    )

    return success_response({
        "id": user.id,
        "username": user.username,
        "role": data.role,
    }, message=f"用户 {user.username} 的角色已更新为 {data.role}")


@router.get("/check/{permission_name}")
async def check_permission(
    permission_name: str,
    current_user: User = Depends(get_current_user),
):
    """检查当前用户是否有指定权限"""
    user_perms = get_user_permissions(current_user)
    allowed = permission_name in user_perms
    return success_response({
        "permission": permission_name,
        "allowed": allowed,
        "user_permissions": user_perms,
    })


# ─── 辅助函数 ───

def _get_role_label(role: str) -> str:
    return {
        "admin": "管理员",
        "operator": "运维操作员",
        "viewer": "只读用户",
        "auditor": "审计员",
    }.get(role, role)


def _get_permission_label(permission: Permission) -> str:
    return {
        "device:view": "查看设备",
        "device:create": "创建设备",
        "device:edit": "编辑设备",
        "device:delete": "删除设备",
        "device:control": "控制设备",
        "workorder:view": "查看工单",
        "workorder:create": "创建工单",
        "workorder:edit": "编辑工单",
        "workorder:delete": "删除工单",
        "workorder:assign": "分配工单",
        "alarm:view": "查看告警",
        "alarm:process": "处理告警",
        "alarm:delete": "删除告警",
        "station:view": "查看站点",
        "station:create": "创建站点",
        "station:edit": "编辑站点",
        "station:delete": "删除站点",
        "user:view": "查看用户",
        "user:create": "创建用户",
        "user:edit": "编辑用户",
        "user:delete": "删除用户",
        "user:role": "用户角色管理",
        "report:view": "查看报表",
        "report:export": "导出报表",
        "audit:view": "查看审计日志",
        "audit:export": "导出审计日志",
        "system:config": "系统配置",
        "system:role": "角色管理",
    }.get(permission.value, permission.value)


def _get_role_user_counts(db: Session) -> dict[str, int]:
    """统计每个角色的用户数"""
    from sqlalchemy import func
    result: dict[str, int] = {}
    # User.role 固定角色：一次 GROUP BY 取代逐个 COUNT
    fixed_roles = ("admin", "operator", "viewer", "auditor")
    role_counts: dict[str, int] = {}
    for r, c in db.query(User.role, func.count(User.id)).filter(
        User.role.in_(fixed_roles)
    ).group_by(User.role).all():
        key = r.value if hasattr(r, "value") else str(r)
        role_counts[key] = c
    for role_name in fixed_roles:
        result[role_name] = role_counts.get(role_name, 0)
    # 多对多关联表：一次 GROUP BY + 一次批量取角色名，避免逐角色 N+1
    rows = db.query(
        user_role_table.c.role_id,
        func.count(user_role_table.c.user_id)
    ).group_by(user_role_table.c.role_id).all()
    if rows:
        role_name_map = {
            r.id: r.name
            for r in db.query(RoleTable).filter(
                RoleTable.id.in_([rid for rid, _ in rows])
            ).all()
        }
        for role_id, count in rows:
            name = role_name_map.get(role_id)
            if name:
                result[name] = result.get(name, 0) + count
    return result