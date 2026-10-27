"""工单共享 router 实例 — 从原 workorders.py 拆出 (卡 1ed83abf)。

所有路由子模块 (routes_lifecycle / routes_workflow / routes_extensions) 共用本 ``router``
对象注册端点, 包 ``__init__`` 重导出 ``router`` 供 ``include_router`` 挂载。
"""
from fastapi import APIRouter, Depends

from app.api.v1.auth import get_current_user
from app.middleware.permission import require_write_permission

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_write_permission("workorder:edit"))])
