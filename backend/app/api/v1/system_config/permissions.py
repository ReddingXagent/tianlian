"""
系统配置 - 权限配置域
/permissions/tree, /permissions/list,
/roles (CRUD), /users, /check/{permission_name}
"""
from typing import Literal, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User, UserRole as UserRoleEnum
from app.models.rbac import (
    RoleTable, PermissionTable, Permission,
    user_role_table,
)
from app.middleware.permission import get_user_permissions, require_permission
from app.core.response import success_response, action_response
from app.services.audit_service import audit_service

from .common import _check_admin_or_permission

router = APIRouter(tags=["系统配置"])


# ── 权限配置 Schemas ──

class RoleCreateSchema(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    display_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = ""
    permissions: List[str] = []


class RoleUpdateSchema(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class UserRoleUpdateSchema(BaseModel):
    role: Literal["super_admin", "admin", "dispatcher", "station_master", "engineer", "operator", "viewer", "technician", "auditor"]
    extra_role_ids: Optional[List[int]] = None


# ── Helper Functions ──

def _get_role_label(role: str) -> str:
    return {
        "super_admin": "超级管理员",
        "admin": "管理员",
        "operator": "运维操作员",
        "viewer": "只读用户",
        "auditor": "审计员",
    }.get(role, role)


def _get_permission_label(name: str) -> str:
    labels = {
        "device:view": "查看设备", "device:create": "创建设备", "device:edit": "编辑设备",
        "device:delete": "删除设备", "device:control": "控制设备",
        "workorder:view": "查看工单", "workorder:create": "创建工单", "workorder:edit": "编辑工单",
        "workorder:delete": "删除工单", "workorder:assign": "分配工单",
        "alarm:view": "查看告警", "alarm:process": "处理告警", "alarm:delete": "删除告警",
        "station:view": "查看站点", "station:create": "创建站点", "station:edit": "编辑站点",
        "station:delete": "删除站点",
        "user:view": "查看用户", "user:create": "创建用户", "user:edit": "编辑用户",
        "user:delete": "删除用户", "user:role": "用户角色管理",
        "report:view": "查看报表", "report:export": "导出报表",
        "audit:view": "查看审计日志", "audit:export": "导出审计日志",
        "system:config": "系统配置", "system:role": "角色管理",
    }
    return labels.get(name, name)


def _role_to_dict(r: RoleTable) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "display_name": r.display_name,
        "description": r.description or "",
        "is_system": bool(r.is_system),
        "permissions": sorted(set(p.name for p in r.permissions)),
        "permission_labels": {p.name: _get_permission_label(p.name) for p in r.permissions},
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ── 权限配置 API ──

@router.get("/permissions/tree")
async def get_permission_tree(_: object = Depends(require_permission("rbac:read"))):
    """获取权限树形结构（用于权限配置页面）"""
    resource_labels = {
        "device": "设备管理", "workorder": "工单管理", "alarm": "告警管理",
        "station": "站点管理", "user": "用户管理", "report": "报表管理",
        "audit": "审计管理", "system": "系统管理",
    }
    action_labels = {
        "view": "查看", "create": "创建", "edit": "编辑", "delete": "删除",
        "control": "控制", "assign": "分配", "process": "处理", "export": "导出",
        "role": "角色管理", "config": "系统配置",
    }
    resource_order = list(resource_labels.keys())

    tree: dict = {}
    for p in Permission:
        resource, action = p.value.split(":", 1) if ":" in p.value else ("other", p.value)
        if resource not in tree:
            tree[resource] = {
                "key": resource,
                "title": resource_labels.get(resource, resource),
                "resource": resource,
                "children": [],
            }
        tree[resource]["children"].append({
            "key": p.value,
            "title": f"{action_labels.get(action, action)} ({p.value})",
            "name": p.value,
            "resource": resource,
            "action": action,
            "label": action_labels.get(action, action),
            "is_leaf": True,
        })

    sorted_tree = sorted(
        tree.values(),
        key=lambda x: resource_order.index(x["resource"]) if x["resource"] in resource_order else 99
    )
    return success_response({"tree": sorted_tree})


@router.get("/permissions/list")
async def list_permissions(_: object = Depends(require_permission("rbac:read"))):
    """获取权限平铺列表"""
    resource_labels = {
        "device": "设备管理", "workorder": "工单管理", "alarm": "告警管理",
        "station": "站点管理", "user": "用户管理", "report": "报表管理",
        "audit": "审计管理", "system": "系统管理",
    }
    action_labels = {
        "view": "查看", "create": "创建", "edit": "编辑", "delete": "删除",
        "control": "控制", "assign": "分配", "process": "处理", "export": "导出",
        "role": "角色管理", "config": "系统配置",
    }
    resource_order = list(resource_labels.keys())

    items = []
    for p in Permission:
        resource, action = p.value.split(":", 1) if ":" in p.value else ("other", p.value)
        items.append({
            "name": p.value,
            "resource": resource,
            "action": action,
            "label": f"{resource_labels.get(resource, resource)} - {action_labels.get(action, action)}",
            "label_short": action_labels.get(action, action),
        })
    items.sort(key=lambda x: (resource_order.index(x["resource"]) if x["resource"] in resource_order else 99, x["action"]))
    return success_response({"items": items})


@router.get("/roles")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取角色列表（含用户数统计）"""
    _check_admin_or_permission(current_user, "system:role")
    role_rows = db.query(RoleTable).order_by(RoleTable.id).all()

    # 统计各角色用户数
    user_counts: dict[int, int] = {}
    rows = db.query(
        user_role_table.c.role_id,
        func.count(user_role_table.c.user_id),
    ).group_by(user_role_table.c.role_id).all()
    for role_id, count in rows:
        user_counts[role_id] = count

    items = []
    for r in role_rows:
        d = _role_to_dict(r)
        d["user_count"] = user_counts.get(r.id, 0)
        items.append(d)

    return success_response({"items": items, "total": len(items)})


@router.get("/roles/{role_id}")
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取角色详情"""
    _check_admin_or_permission(current_user, "system:role")
    role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="角色不存在")
    return success_response(_role_to_dict(role_row))


@router.post("/roles", status_code=201)
def create_role(
    data: RoleCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("rbac:manage")),
):
    """创建自定义角色"""
    _check_admin_or_permission(current_user, "system:role")
    existing = db.query(RoleTable).filter(RoleTable.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"角色名 {data.name} 已存在")

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

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        module="system_config",
        target_id=str(role_row.id),
        target_desc=f"创建角色 {role_row.display_name}",
    )

    return success_response(_role_to_dict(role_row), message=f"角色 {data.display_name} 创建成功")


@router.put("/roles/{role_id}")
def update_role(
    role_id: int,
    data: RoleUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_permission("rbac:manage")),
):
    """更新角色"""
    _check_admin_or_permission(current_user, "system:role")
    role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
    if not role_row:
        raise HTTPException(status_code=404, detail="角色不存在")

    old_perms = {p.name for p in role_row.permissions}

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

    new_perms = {p.name for p in role_row.permissions}
    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        module="system_config",
        target_id=str(role_id),
        target_desc=f"更新角色 {role_row.display_name}",
        old_value=str(old_perms),
        new_value=str(new_perms),
    )

    return success_response(_role_to_dict(role_row), message=f"角色 {role_row.display_name} 更新成功")


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

    display_name = role_row.display_name
    db.delete(role_row)
    db.commit()

    audit_service.log_crud(
        user_id=current_user.id,
        username=current_user.username,
        action="delete",
        module="system_config",
        target_id=str(role_id),
        target_desc=f"删除角色 {display_name}",
    )

    return action_response(success=True, message=f"角色 {display_name} 已删除")


@router.get("/users")
def list_users_with_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户列表（含角色和权限信息，分页返回）"""
    _check_admin_or_permission(current_user, "user:view")
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
        module="system_config",
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
