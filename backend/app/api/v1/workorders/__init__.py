"""
工单管理 API — 包入口

原 app/api/v1/workorders.py(1071行) 按职责拆为子模块 (卡 1ed83abf):
- schemas.py            : Pydantic Schema + 活跃/完成态常量
- helpers.py            : WS 广播 / 团队归属校验 / 评价序列化
- router.py             : 共享 router 实例 (含鉴权 dependencies)
- routes_lifecycle.py   : CRUD / 统计 / 日志
- routes_workflow.py    : 状态机 (accept/start/complete/verify/reject) + 派单/转单/催单
- routes_extensions.py  : 签到 / 支援 / 备件 / 评价 / 一站式验收

本 __init__ 重导出 ``router`` 及全部 Schema/helper, 保持
``from app.api.v1.workorders import router`` 与
``include_router(workorders.router, ...)`` 路径完全不变。

⚠️ 路由注册顺序: 导入 routes_lifecycle 先于 workflow/extensions, 与原文件一致 ——
GET ``/stats`` (静态) 必须先于 ``/{workorder_id}`` (参数) 注册, 否则 /stats 会被
参数路由抢先匹配。三个 routes 子模块共用 router.py 的同一 ``router`` 对象,
import 即触发 ``@router`` 装饰器注册。
"""
from .router import router
from .schemas import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderDispatch,
    WorkOrderCheckinSchema,
    WorkOrderSupportSchema,
    WorkOrderSparePartSchema,
    WorkOrderRateSchema,
    WorkOrderAcceptanceSchema,
    WorkOrderTransfer,
    WorkOrderUrge,
)
from .helpers import (
    _broadcast_wo,
    _workorder_team_id,
    _check_workorder_team,
    _serialize_rating,
)

# 导入路由子模块以触发 @router 装饰器注册端点 (顺序: lifecycle → workflow → extensions)。
from . import routes_lifecycle  # noqa: F401,E402
from . import routes_workflow  # noqa: F401,E402
from . import routes_extensions  # noqa: F401,E402

__all__ = ["router"]
