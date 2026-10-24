"""
遥测数据采集 API 包 — 天链V2 Phase1 改造 / Phase3 TDengine 双模式查询

原 app/api/v1/telemetry.py(1105行) 按职责拆分为子模块(卡 61109a8a):
- models.py   : 上报 Pydantic 模型(光伏/储能/充电桩/旧版/批量)
- helpers.py  : 配置常量 + TDengine 查询路由 + 请求头解析 + 表路由/记录构建
- queries.py  : 批量 latest 取数(消除 N+1)
- routes.py   : router + 全部 HTTP 端点

本 __init__ 重导出 router 与对外契约符号, 保持两类引用路径不变:
- `telemetry.router` → app/api/v1/__init__.py 的 include_router
- `from app.api.v1.telemetry import get_current_gateway_or_user` → charging_sessions 等
网关鉴权(节流 + TTL 缓存 + dep) 实现在 app.core.auth_throttle(卡 4c8120a6 抽离),
此处 re-export 保持调用方导入契约不变。
"""
from app.core.auth_throttle import get_current_gateway_or_user
from .routes import router
from .models import (
    TelemetryReportBase,
    TelemetryPVReport,
    TelemetryBatteryReport,
    TelemetryChargerReport,
    TelemetryReportLegacy,
    TelemetryBatchReport,
)

__all__ = [
    'router',
    'get_current_gateway_or_user',
    'TelemetryReportBase',
    'TelemetryPVReport',
    'TelemetryBatteryReport',
    'TelemetryChargerReport',
    'TelemetryReportLegacy',
    'TelemetryBatchReport',
]
