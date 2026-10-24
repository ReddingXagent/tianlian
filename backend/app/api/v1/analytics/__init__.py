"""运维数据分析与AI预测 API 包（拆分自原 analytics.py / 946 行）。

原 ``app/api/v1/analytics.py`` 按分析类型拆分为同包子模块；本包 ``__init__``
按原文件端点声明顺序聚合各子模块 router，重建与原文件一致的 ``router``：
- 端点集合与注册顺序不变（health-score → efficiency-analysis → anomaly-detection）；
  各端点均为具体 path，无集合根空 path，故 ``include_router`` 无空 path 限制。
- router 级鉴权依赖 ``[Depends(get_current_user), Depends(require_write_permission("analytics:manage"))]``
  由各子模块 router 各自携带（FastAPI 不会把父 router 的 dependencies 传递给 include
  进来的子路由），故 ``app.api.v1.analytics.router`` 导入路径与行为保持向后兼容。

子模块：health / efficiency / anomaly；共享 schema 与依赖见 ``_shared``。
"""
from fastapi import APIRouter

from . import health, efficiency, anomaly

# 按 analytics.py 原端点声明顺序聚合
router = APIRouter()
router.include_router(health.router)
router.include_router(efficiency.router)
router.include_router(anomaly.router)
