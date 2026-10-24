"""
系统配置 API 包 - 按业务域拆分
原 system_config.py (1562 行) → 7 个业务域子模块

保持导入面兼容：``from app.api.v1.system_config import router``
所有 API 路径 / 响应格式 / operation 不变；前缀 /system-config 由上层
api_router.include_router 施加，本包总 router 不自带前缀。

业务域分组：
- permissions  权限配置（roles/users/permissions tree+list/check）
- notification 通知配置（switches/templates/rules）+ 兼容旧接口
- audit        日志审计
- global_config 全局配置
- payment      支付通道
- invoice      发票配置
"""
from fastapi import APIRouter

from . import (
    permissions,
    notification,
    audit,
    global_config,
    payment,
    invoice,
)

router = APIRouter(tags=["系统配置"])
router.include_router(permissions.router)
router.include_router(notification.router)
router.include_router(audit.router)
router.include_router(global_config.router)
router.include_router(payment.router)
router.include_router(invoice.router)

__all__ = ["router"]
