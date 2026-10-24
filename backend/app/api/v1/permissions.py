"""
天链 V3 — 权限列表/树形图 API
GET /api/v1/permissions — 返回权限列表和树形结构
"""
import logging
from fastapi import APIRouter, Depends, HTTPException

from app.models.rbac import Permission
from app.core.response import success_response
from app.api.v1.auth import get_current_user
from app.api.v1.system_config.common import _check_admin_or_permission

router = APIRouter(dependencies=[Depends(get_current_user)])

logger = logging.getLogger(__name__)


RESOURCE_LABELS = {
    "device": "设备管理",
    "workorder": "工单管理",
    "alarm": "告警管理",
    "station": "站点管理",
    "user": "用户管理",
    "report": "报表管理",
    "audit": "审计管理",
    "system": "系统管理",
}

ACTION_LABELS = {
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


def _build_items() -> list[dict]:
    """构建权限平铺列表"""
    resource_order = list(RESOURCE_LABELS.keys())
    items = []
    for p in Permission:
        resource, action = p.value.split(":", 1) if ":" in p.value else ("other", p.value)
        items.append({
            "name": p.value,
            "resource": resource,
            "action": action,
            "label": f"{RESOURCE_LABELS.get(resource, resource)} - {ACTION_LABELS.get(action, action)}",
            "label_short": ACTION_LABELS.get(action, action),
        })
    items.sort(key=lambda x: (resource_order.index(x["resource"]) if x["resource"] in resource_order else 99, x["action"]))
    return items


def _build_tree() -> list[dict]:
    """构建权限树形图"""
    resource_order = list(RESOURCE_LABELS.keys())
    tree: dict[str, dict] = {}
    for p in Permission:
        resource, action = p.value.split(":", 1) if ":" in p.value else ("other", p.value)
        if resource not in tree:
            tree[resource] = {
                "key": resource,
                "title": RESOURCE_LABELS.get(resource, resource),
                "resource": resource,
                "children": [],
            }
        tree[resource]["children"].append({
            "key": p.value,
            "title": f"{ACTION_LABELS.get(action, action)} ({p.value})",
            "name": p.value,
            "resource": resource,
            "action": action,
            "label": ACTION_LABELS.get(action, action),
            "is_leaf": True,
        })
    return sorted(tree.values(), key=lambda x: resource_order.index(x["resource"]) if x["resource"] in resource_order else 99)


@router.get("")
async def list_permissions(user=Depends(get_current_user)):
    """获取权限列表 + 树形图"""
    _check_admin_or_permission(user, "system:role")
    try:
        return success_response({
            "items": _build_items(),
            "tree": _build_tree(),
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_permissions 异常")
        raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
