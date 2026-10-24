"""
天链 V3 — 角色管理 API (团队级)
提供角色 CRUD + 权限树形图数据，供 /teams/roles 页面使用
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.user import User
from app.models.rbac import (
    RoleTable, PermissionTable, Permission,
    user_role_table,
)
from app.api.v1.auth import get_current_user
from app.middleware.permission import get_user_permissions
from app.core.response import success_response, action_response

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ─── 请求/响应模型 ───

class RoleCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="角色名称(英文标识)")
    display_name: str = Field(..., min_length=2, max_length=100, description="显示名称")
    description: Optional[str] = Field("", description="角色说明")
    permissions: list[str] = Field(default_factory=list, description="权限列表")


class RoleUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    permissions: Optional[list[str]] = None


# ─── 辅助函数 ───

def _check_admin_or_permission(current_user: User, perm: str):
    """检查管理员或指定权限"""
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


def _build_permission_tree() -> list[dict]:
    """构建权限树形图数据，按 resource 分组"""
    resource_labels = {
        "device": "设备管理",
        "workorder": "工单管理",
        "alarm": "告警管理",
        "station": "站点管理",
        "user": "用户管理",
        "report": "报表管理",
        "audit": "审计管理",
        "system": "系统管理",
    }
    action_labels = {
        "view": "查看",
        "create": "创建",
        "edit": "编辑",
        "delete": "删除",
        "control": "控制",
        "assign": "分配",
        "process": "处理",
        "export": "导出",
        "role": "角色管理",
        "config": "系统配置",
    }

    tree: dict[str, dict] = {}
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

    return sorted(tree.values(), key=lambda x: list(resource_labels.keys()).index(x["resource"]) if x["resource"] in resource_labels else 99)


def _get_permission_label(name: str) -> str:
    """获取权限中文标签"""
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


# ─── API 端点 ───

@router.get("")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取角色列表（含用户数统计）"""
    _check_admin_or_permission(current_user, "system:role")
    try:
        role_rows = db.query(RoleTable).order_by(RoleTable.id).all()

        # 统计各角色用户数
        from sqlalchemy import func
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询角色列表失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.get("/tree")
async def get_permission_tree(
    current_user: User = Depends(get_current_user),
):
    """获取权限树形图数据"""
    _check_admin_or_permission(current_user, "system:role")
    tree = _build_permission_tree()
    return success_response({"tree": tree})


@router.get("/{role_id}")
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取角色详情"""
    _check_admin_or_permission(current_user, "system:role")
    try:
        role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
        if not role_row:
            raise HTTPException(status_code=404, detail="角色不存在")
        return success_response(_role_to_dict(role_row))
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询角色详情失败 role_id=%s", role_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.post("", status_code=201)
def create_role(
    data: RoleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建自定义角色"""
    try:
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
        return success_response(_role_to_dict(role_row), message=f"角色 {data.display_name} 创建成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("创建角色失败 name=%s", data.name)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.put("/{role_id}")
def update_role(
    role_id: int,
    data: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新角色"""
    try:
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
        return success_response(_role_to_dict(role_row), message=f"角色 {role_row.display_name} 更新成功")
    except HTTPException:
        raise
    except Exception:
        logger.exception("更新角色失败 role_id=%s", role_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除角色（系统内置角色不可删除）"""
    try:
        _check_admin_or_permission(current_user, "system:role")

        role_row = db.query(RoleTable).filter(RoleTable.id == role_id).first()
        if not role_row:
            raise HTTPException(status_code=404, detail="角色不存在")
        if role_row.is_system:
            raise HTTPException(status_code=400, detail="系统内置角色不可删除")

        display_name = role_row.display_name
        db.delete(role_row)
        db.commit()
        return action_response(success=True, message=f"角色 {display_name} 已删除")
    except HTTPException:
        raise
    except Exception:
        logger.exception("删除角色失败 role_id=%s", role_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="内部错误")
