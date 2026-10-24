"""定价管理 V2 API 包（拆分自原 pricing_management.py / 936 行）。

6 类定价 CRUD（时段定义 / 充电费 / 服务费 / 停车费 / 占桩费 / 预约费）+ 订单费用估算联动。
原 ``app/api/v1/pricing_management.py`` 按定价资源拆分为同包子模块；本包 ``__init__``
按原文件端点声明顺序聚合各子模块 router，重建与原文件一致的 ``router``：
- 端点集合与注册顺序不变（time-slots → energy → service-fee → parking → occupancy →
  reservation → order-estimate）；各端点路径均以 ``/pricing/mgmt/...`` 开头（具体 path），
  无集合根空 path，故 ``include_router`` 无空 path 限制（即便本 router 在 v1 聚合处无 prefix）。
- router 级鉴权依赖 ``Depends(require_role("admin"))`` 由各子模块 router 各自携带
  （FastAPI 不会把父 router 的 dependencies 传递给 include 进来的子路由），故
  ``app.api.v1.pricing_management.router`` 导入路径与行为保持向后兼容（测试直接 import router）。

子模块：time_slots / energy / service_fee / parking / occupancy / reservation / order_estimate；
共享 schema、解析 helper 与依赖见 ``_shared``。
"""
from fastapi import APIRouter

from . import (
    time_slots,
    energy,
    service_fee,
    parking,
    occupancy,
    reservation,
    order_estimate,
)

# 按 pricing_management.py 原端点声明顺序聚合
router = APIRouter()
router.include_router(time_slots.router)
router.include_router(energy.router)
router.include_router(service_fee.router)
router.include_router(parking.router)
router.include_router(occupancy.router)
router.include_router(reservation.router)
router.include_router(order_estimate.router)
