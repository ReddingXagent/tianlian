"""
天链光储充运维系统 V3 - 后端 API
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.database import DB_TYPE, init_db, engine
from app.core.response import error_response
from app.utils.sanitize import sanitize_for_log
from app.core.sentry_config import init_sentry
from app.core.rate_limit import limiter
from app.core.log_config import setup_logging, get_request_id
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.middleware.logging_middleware import RequestIDMiddleware, RequestBodySizeMiddleware
from app.middleware.audit import AuditMiddleware
from app.middleware.deprecation import DeprecationHeaderMiddleware  # 卡 b1faf814: deprecated 路由响应头
from app.api.v1 import api_router
# WebSocket路由已迁移到统一模块
from app.ws.routes import router as ws_router
from app.ws import ws_manager
from app.core.station_router import init_station_router  # Phase2: 矩阵路由层

# ─── Prometheus 指标 ───
from app.metrics import setup_metrics

# ─── 结构化日志 ───
logger = setup_logging(
    app_name="tianlian-v3",
)

# ─── Sentry 错误监控 ───
init_sentry()


# OpenAPI 标签元数据（Swagger UI 分组展示）
openapi_tags_metadata = [
    {"name": "认证", "description": "用户注册、登录、Token 管理、验证码登录、密码重置"},
    {"name": "用户", "description": "用户 CRUD 管理"},
    {"name": "站点", "description": "光储充站点管理 — 创建、查询、更新、删除"},
    {"name": "设备", "description": "设备注册、管理、状态监控、健康度、控制、维护计划"},
    {"name": "遥测数据", "description": "设备遥测数据上报与查询"},
    {"name": "故障码诊断", "description": "基于协议分析的故障码知识库与诊断"},
    {"name": "智能诊断", "description": "AI 驱动设备诊断 — 单个诊断、批量诊断、健康趋势"},
    {"name": "智能故障诊断", "description": "故障关键词匹配与自动诊断"},
    {"name": "报表导出", "description": "设备/工单/站点/汇总报表导出"},
    {"name": "报表管理", "description": "报表模板管理与生成"},
    {"name": "告警", "description": "告警查询、确认、关闭与管理"},
    {"name": "告警规则", "description": "告警规则配置与阈值管理"},
    {"name": "工单", "description": "运维工单管理 — 创建、派单、接单、处理、完成"},
    {"name": "设备维护记录", "description": "设备维护记录 CRUD 与维护计划"},
    {"name": "健康检查", "description": "系统存活探针、就绪探针、设备健康度"},
    {"name": "健康度监控", "description": "设备健康度实时监控与刷新"},
    {"name": "RBAC", "description": "角色与权限管理"},
    {"name": "知识库", "description": "运维知识库管理 — 文章 CRUD、搜索"},
    {"name": "统计", "description": "系统统计数据与面板"},
    {"name": "团队管理", "description": "运维团队管理"},
    {"name": "工程师管理", "description": "工程师独立管理"},
    {"name": "网关管理", "description": "IoT 网关注册与管理"},
    {"name": "扫码报修", "description": "扫码识别设备、快速报修、二维码管理"},
    {"name": "实时监控", "description": "设备实时数据监控"},
    {"name": "AI日志分析", "description": "AI 驱动的日志分析"},
    {"name": "多租户管理", "description": "多租户隔离与管理"},
    {"name": "API密钥管理", "description": "API 密钥的创建、撤销与管理"},
    {"name": "安全管理", "description": "安全策略与配置"},
    {"name": "操作日志", "description": "用户操作审计日志"},
    {"name": "告警通知", "description": "告警通知渠道与记录"},
    {"name": "通知配置", "description": "通知渠道配置 (SMS/邮件/APP)"},
    {"name": "通知规则", "description": "通知发送规则"},
    {"name": "通知发送", "description": "通知消息发送"},
    {"name": "SSL证书管理", "description": "SSL 证书生命周期管理"},
    {"name": "值班排班管理", "description": "值班人员排班调度"},
    {"name": "Runbook自动化", "description": "运维 Runbook 自动执行"},
    {"name": "Runbook审批流", "description": "Runbook 执行审批流程"},
    {"name": "能耗分析报表", "description": "光储充能耗数据分析"},
    {"name": "数字孪生可视化", "description": "站点与设备 3D 数字孪生"},
    {"name": "预测性维护", "description": "AI 预测性维护模型"},
    {"name": "虚拟电厂VPP", "description": "虚拟电厂调度优化、多站点协同"},
    {"name": "告警自愈引擎", "description": "告警自动修复与自愈"},
    {"name": "运维大屏可视化", "description": "运维大屏数据展示"},
    {"name": "运维数据分析与预测", "description": "数据趋势分析与预测"},
    {"name": "巡检运维管理", "description": "设备巡检计划与执行"},
    {"name": "设备库管理", "description": "设备模板库管理"},
    {"name": "异步任务管理", "description": "Celery 异步任务调度"},
    {"name": "监控告警闭环", "description": "监控 → 告警 → 自愈闭环流程"},
    {"name": "告警Webhook", "description": "Alertmanager Webhook 接收"},
    {"name": "Pod管理", "description": "分布式 Pod 健康注册"},
    {"name": "跨Pod查询", "description": "矩阵路由层跨 Pod 数据查询"},
    {"name": "充电策略引擎", "description": "智能充电策略 — 5种模式 + 光伏预测 + 储能调度"},
    {"name": "系统配置", "description": "系统全局配置管理"},
    {"name": "企业账户管理", "description": "企业账户 CRUD — 名称、编码、余额、信用额度"},
    {"name": "定价管理", "description": "峰谷电价规则 CRUD"},
    {"name": "充电订单管理", "description": "充电订单查询、交易记录"},
    {"name": "车队车辆管理", "description": "企业车队车辆 CRUD"},
    {"name": "车队资金池交易", "description": "企业资金池充值/扣费/交易记录"},
    {"name": "车队概览", "description": "车队整体运营概览数据"},
    {"name": "协议实例管理", "description": "设备协议实例管理"},
    {"name": "权限管理", "description": "权限列表与树形图"},
    {"name": "角色管理", "description": "团队级角色管理"},
    {"name": "WebSocket", "description": "实时数据推送 — 设备遥测、数字孪生"},
]

# 创建 FastAPI 应用 - OpenAPI / Swagger 文档
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 天链光储充运维系统 V3 后端 API

光储充一体化智能运维平台，覆盖光伏发电、储能管理、充电桩运维全链路。

### 核心能力

- **设备管理** — 逆变器/充电桩/PCS/电表 注册、监控、控制
- **遥测采集** — Modbus/MQTT/DLT645/IEC104 多协议数据上报
- **告警诊断** — 告警规则、故障码知识库、AI 智能诊断
- **工单管理** — 创建、派单、接单、处理、完成全流程
- **运维自动化** — Runbook 执行、自愈引擎、预测性维护
- **运营管理** — 企业账户、峰谷定价、充电订单、车队管理
- **虚拟电厂** — VPP 调度优化、多站点协同、电网互动

### 安全

- **认证方式**: Bearer Token (JWT)
- **获取 Token**: `POST /api/v1/auth/login` (用户名密码) 或 `POST /api/v1/auth/sms/login` (验证码)
- **请求头**: `Authorization: Bearer {token}`

### 响应格式

所有 API 响应采用统一格式:
```json
{
  "code": 200,
  "message": "success",
  "data": { ... },
  "ts": "2024-01-01T00:00:00"
}
```

分页响应:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  },
  "ts": "2024-01-01T00:00:00"
}
```
""",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    openapi_tags=openapi_tags_metadata,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 1,
        "docExpansion": "list",
        "filter": True,
        "tagsSorter": "alpha",
        "tryItOutEnabled": True,
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
    contact={
        "name": "天链科技",
        "url": "https://tianlian.cloud",
    },
    license_info={
        "name": "Proprietary",
    },
)

# ─── Prometheus 指标注册 ───
setup_metrics(app)
logger.info("Prometheus 指标已注册，/metrics 端点已就绪")

# ─── 数据库初始化 ───
@app.on_event("startup")
async def startup_db():
    """启动时初始化数据库表 + 启动WS心跳 + 初始化路由"""
    logger.info("正在初始化数据库 (DB_TYPE=%s)...", DB_TYPE)
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error("数据库初始化失败: %s", str(e))
        if DB_TYPE == "postgres":
            logger.error("请确认 PostgreSQL 已启动且 DATABASE_URL 正确")
        raise

    # Schema 同步保障：对比 metadata 与 DB，缺表自动建、缺列(dev 自动补 / prod 仅告警)
    try:
        from app.utils.schema_validator import validate_schema
        validate_schema(engine)
    except Exception as e:
        logger.warning("Schema 校验跳过（不影响启动）: %s", e)

    # 启动 WebSocket 心跳保活
    await ws_manager.start_heartbeat()

    # Phase2: 初始化 StationRouter（矩阵路由层）
    from app.core.cache import cache
    init_station_router(
        local_only=settings.POD_LOCAL_ONLY,
        redis_client=cache.client if cache.enabled else None,
        pod_id=settings.POD_ID,
        region_id=settings.REGION_ID,
        endpoint=settings.POD_ENDPOINT
    )
    logger.info(
        "StationRouter 初始化完成 (pod_id=%s, region_id=%s, local_only=%s)",
        settings.POD_ID, settings.REGION_ID, settings.POD_LOCAL_ONLY
    )

    # YKC 云快充网关 (任务卡 9a5d070e): 默认关, 云端环境变量 YKC_GATEWAY_ENABLED=true 开
    try:
        from app.gateway.ykc import start_ykc_gateway
        await start_ykc_gateway()
    except Exception as e:
        logger.warning("YKC 网关启动跳过（不影响应用）: %s", e)

    # SZBus 深圳巴士协议网关 (2026-10-09): 默认关, SZBUS_GATEWAY_ENABLED=true 开
    try:
        from app.gateway.szbus import start_szbus_gateway
        await start_szbus_gateway()
    except Exception as e:
        logger.warning("SZBus 网关启动跳过（不影响应用）: %s", e)

    # 记录初始数据库连接池指标
    try:
        from app.metrics import update_db_metrics
        pool = engine.pool
        pool_size = getattr(pool, 'size', lambda: 0)()
        active = getattr(pool, 'checkedout', lambda: 0)()
        idle = getattr(pool, 'checkedin', lambda: 0)()
        overflow = max(0, getattr(pool, 'overflow', lambda: 0)())
        update_db_metrics(pool_size, active, idle, overflow)
        logger.info("数据库连接池初始指标已记录")
    except Exception as e:
        logger.debug("记录数据库连接池指标时出错 (不影响启动): %s", e)


@app.on_event("shutdown")
async def shutdown_events():
    """应用关闭时的清理工作"""
    logger.info("天链V3 应用正在关闭...")
    try:
        await ws_manager.stop_heartbeat()
        logger.info("WebSocket 心跳已停止")
    except Exception as e:
        logger.warning("关闭 WebSocket 心跳时出错: %s", e)

    # YKC 云快充网关 (任务卡 9a5d070e)
    try:
        from app.gateway.ykc import stop_ykc_gateway
        await stop_ykc_gateway()
    except Exception as e:
        logger.warning("关闭 YKC 网关时出错: %s", e)

    # SZBus 深圳巴士协议网关
    try:
        from app.gateway.szbus import stop_szbus_gateway
        await stop_szbus_gateway()
    except Exception as e:
        logger.warning("关闭 SZBus 网关时出错: %s", e)

    logger.info("天链V3 应用已关闭")


# 中间件注册顺序（后添加的先执行）
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestBodySizeMiddleware)

# Phase5-16: GZip 压缩中间件 (API响应压缩, 减少传输体积 60-80%)
app.add_middleware(GZipMiddleware, minimum_size=500)

# ─── SlowAPI 限流 ───
app.state.limiter = limiter
# RateLimitExceeded → 429 (装饰器/中间件超限时抛出, 需 handler 转换为 429 响应)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# SlowAPIMiddleware: 使 default_limits (1000 req/min) 对全部端点全局生效
app.add_middleware(SlowAPIMiddleware)

# 配置 CORS - 白名单模式（不允许通配符 + credentials 同时使用）
ALLOWED_ORIGINS = [
    "http://localhost:3004",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://demo.example.com",
    "http://127.0.0.1:3004",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept"],
)

# 安全响应头中间件
app.add_middleware(SecurityHeadersMiddleware)

# 废弃端点响应头 (卡 b1faf814): deprecated 路由注入 Deprecation/Sunset 头
app.add_middleware(DeprecationHeaderMiddleware)

# CSRF 防护中间件 (Double Submit Cookie)
app.add_middleware(CSRFMiddleware)

# 审计日志中间件 (自动拦截 POST/PUT/PATCH/DELETE)
app.add_middleware(AuditMiddleware)

# 注册路由
app.include_router(api_router, prefix="/api/v1")
# WebSocket统一路由 (标准化前缀: /ws/v1/)
app.include_router(ws_router, tags=["WebSocket"])

# 上传目录 (车队充值凭证/发票) 不做静态直挂 (卡 554bb70b):
# uploads/ 含发票 PII 与付款凭证, 裸挂 /uploads 会绕过签名令牌与鉴权。
# 文件一律经作用域端点下发: /api/v1/business/invoice-file (签名令牌),
# /api/v1/fleet/recharge/{id}/voucher (登录 + 团队作用域)。

# 根路径
@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }

# 全局异常处理 - 统一响应格式
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTPException处理器 - 统一格式"""
    request_id = get_request_id()
    logger.warning(
        "HTTPException %d: %s",
        exc.status_code, exc.detail,
        extra={"request_id": request_id, "status_code": exc.status_code},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            code=exc.status_code,
            message=str(exc.detail),
            data=None if not settings.DEBUG else {"detail": str(exc.detail)}
        )
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器 - 不泄露内部错误详情"""
    request_id = get_request_id()
    logger.exception(
        "未处理异常: %s",
        sanitize_for_log(str(exc)),
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content=error_response(
            code=500,
            message="服务器内部错误",
            data=None  # 生产环境永不泄露堆栈/内部路径
        )
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=int(settings.PORT),
        reload=settings.DEBUG
    )