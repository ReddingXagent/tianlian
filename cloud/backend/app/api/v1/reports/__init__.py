"""数据分析报表 API 包（拆分自原 reports.py / 991 行）。

原 ``app/api/v1/reports.py`` 按报表类型拆分为同包子模块；本包 ``__init__``
按原文件端点声明顺序聚合各子模块 router，重建与原文件一致的 ``router``：
- 端点集合与注册顺序不变（summary → devices → workorders → alarms → faults → v2g）；
  各端点均为具体 path（/summary 等），无集合根空 path，故 ``include_router`` 无空 path 限制。
- router 级鉴权依赖 ``Depends(get_current_user)`` 由各子模块 router 各自携带
  （FastAPI 不会把父 router 的 dependencies 传递给 include 进来的子路由），
  故 ``app.api.v1.reports.router`` 导入路径与行为保持向后兼容。

子模块：summary / devices / workorders / alarms / faults / v2g；
共享定义见 ``_shared``（team scoping + 团队绩效），导出渲染见 ``export``。
"""
from fastapi import APIRouter

from . import summary, devices, workorders, alarms, faults, v2g

# 按 reports.py 原端点声明顺序聚合
router = APIRouter()
router.include_router(summary.router)
router.include_router(devices.router)
router.include_router(workorders.router)
router.include_router(alarms.router)
router.include_router(faults.router)
router.include_router(v2g.router)
