"""
数据库配置
支持 SQLite (默认) 和 PostgreSQL 切换
通过环境变量 DB_TYPE 控制: sqlite (默认) | postgres

连接池优化 (Phase34):
- pool_pre_ping: 连接前检测, 防止复用已断开的连接
- pool_recycle: 连接回收周期 (默认 3600s)
- 慢查询日志: SQLALCHEMY_WARN_20 告警 + echo="once" 模式
"""
import os
import time
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)

# 数据库类型: sqlite (默认) 或 postgres
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

# 默认连接池配置 (对 SQLite 也施加 pool_pre_ping / pool_recycle 以保持统一)
POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))
ECHO_ENABLED = os.getenv("DEBUG", "false").lower() == "true"

# ─── 慢查询日志配置 ───
# 当 SQLALCHEMY_WARN_20 启用时, SQLAlchemy 2.0 会发出 DeprecationWarning
# 我们借此记录慢查询, 同时在 logger 层面记录所有实际 SQL
SLOW_QUERY_MS = int(os.getenv("DB_SLOW_QUERY_MS", "200"))  # 超过 200ms 视为慢查询
_slow_query_logger = logging.getLogger("app.db.slow_query")

if DB_TYPE == "postgres":
    # ─── PostgreSQL 模式 ───
    # [卡439a1fcd] 移除硬编码凭证回退 (fail-fast): 缺 DATABASE_URL 必须显式失败,
    # 绝不静默落到默认 DSN 把明文凭证带进生产。运维须在 .env/环境变量显式配置。
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError(
            "DB_TYPE=postgres 但未配置 DATABASE_URL。请在环境变量/.env 中显式设置 "
            "PostgreSQL 连接串 (如 postgresql://user:password@host:5432/dbname); "
            "原硬编码凭证回退已移除。"
        )
    pool_size = int(os.getenv("DB_POOL_SIZE", "50"))  # Phase1: 默认50（原20）
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    engine = create_engine(
        DATABASE_URL,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=POOL_PRE_PING,
        echo=ECHO_ENABLED,
    )
    logger.info(
        "[DB] PostgreSQL模式已激活 pool_size=%s max_overflow=%s recycle=%s pre_ping=%s",
        pool_size, max_overflow, POOL_RECYCLE, POOL_PRE_PING,
    )
else:
    # ─── SQLite 模式 (默认) ───
    # [卡1e6cb038] URL 优先级: DATABASE_URL 若已设置且为 sqlite scheme (sqlite:///...)
    # 则优先生效; 否则回退 DATABASE_URL_DEV (默认 sqlite:///./tianlian_v3.db)。
    # 修复: 用户按标准习惯设 DATABASE_URL=sqlite:///xxx.db 不再被静默吞掉落到
    # cwd 相对默认库; postgres 等非 sqlite scheme 的 DATABASE_URL 在本分支忽略
    # (现网 .env 双定义 DATABASE_URL=postgresql://... + DATABASE_URL_DEV=sqlite://...
    # 的兼容路径行为不变)。
    _env_url = os.getenv("DATABASE_URL")
    DATABASE_URL = (
        _env_url
        if _env_url and _env_url.startswith("sqlite")
        else os.getenv("DATABASE_URL_DEV", "sqlite:///./tianlian_v3.db")
    )

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
        pool_pre_ping=POOL_PRE_PING,
        pool_recycle=POOL_RECYCLE,
        echo=ECHO_ENABLED,
    )

    # SQLite WAL 模式 + 性能 PRAGMA (Phase5-16 性能优化)
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA cache_size=-8000")  # 8MB cache
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        cursor.close()

    logger.info(
        "[DB] SQLite模式已激活 (WAL) recycle=%s pre_ping=%s pool_size=%s",
        POOL_RECYCLE, POOL_PRE_PING,
        int(os.getenv("DB_POOL_SIZE", "10")),
    )


# ─── 慢查询监听 ───
@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """在执行 SQL 前记录时间戳"""
    conn.info.setdefault("query_start_time", {})
    conn.info["query_start_time"] = time.time()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """执行后检测是否慢查询"""
    start = conn.info.pop("query_start_time", None)
    if start is None:
        return
    duration_ms = round((time.time() - start) * 1000, 2)
    if duration_ms >= SLOW_QUERY_MS:
        # 截断过长的 SQL
        stmt_short = statement[:200] if len(statement) > 200 else statement
        _slow_query_logger.warning(
            "慢查询 %sms [%s..] params=%s",
            duration_ms, stmt_short,
            str(parameters)[:100] if parameters else "",
        )


# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── 异步引擎 + 异步会话 (卡52f731ac) ───
# 上一轮把 154 个无 await 的 async 端点转为同步 def (commit 885878ca1), 由 FastAPI
# 自动丢进线程池, 不再阻塞事件循环。剩余含真实 await (httpx/asyncio) 的端点无法转 def,
# 但其函数体内仍有同步 db.query/commit 直接跑在事件循环上 → 阻塞所有协程。
# 引入 sqlalchemy.ext.asyncio 异步会话供这些端点使用, 把 DB IO 移出事件循环。
#
# 同步 engine/session 完全保留: 其余端点 (def + 部分 async) 仍在用, 不受影响。
#
# 驱动: SQLite → aiosqlite (线程化包装, dev 默认); PostgreSQL → asyncpg (生产)。
#
# fail-fast 策略: asyncpg/aiosqlite 非同步 engine 的必需依赖, 故驱动缺失时 **不在
# 模块 import 时 raise** (否则连 /health 都启动失败, 拖垮整个应用)。改为仅在异步会话
# 被实际使用 (get_async_db / AsyncSessionLocal) 时抛清晰错误 —— 同步端点照常运行。
def _sync_to_async_url(sync_url: str) -> str:
    """把同步 DATABASE_URL 翻译成 create_async_engine 可用的 URL。

    - sqlite://...        → sqlite+aiosqlite://...
    - postgresql://...    → postgresql+asyncpg://...
    - 已带异步 driver 前缀的原样返回
    """
    if sync_url.startswith("sqlite+aiosqlite://"):
        return sync_url
    if sync_url.startswith("postgresql+asyncpg://"):
        return sync_url
    if sync_url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + sync_url[len("sqlite://"):]
    # psycopg2 同步串 (postgresql:// / postgres://) → asyncpg
    if sync_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + sync_url[len("postgresql://"):]
    if sync_url.startswith("postgres://"):
        return "postgresql+asyncpg://" + sync_url[len("postgres://"):]
    return sync_url


ASYNC_DATABASE_URL = _sync_to_async_url(DATABASE_URL)

# 异步驱动可用性探测: 仅记录状态, 不 raise (见上方 fail-fast 策略说明)。
_ASYNC_DRIVER_OK = True
_ASYNC_DRIVER_ERR = ""
if DB_TYPE == "postgres":
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        _ASYNC_DRIVER_OK = False
        _ASYNC_DRIVER_ERR = (
            "DB_TYPE=postgres 启用了异步会话, 但未安装 asyncpg。"
            "请在 requirements.txt 增补 asyncpg 并 pip install; "
            "同步 engine 不受影响, 仅含 await 的异步端点依赖异步会话。"
        )
else:
    try:
        import aiosqlite  # noqa: F401
    except ImportError:
        _ASYNC_DRIVER_OK = False
        _ASYNC_DRIVER_ERR = (
            "SQLite 异步会话需要 aiosqlite, 但未安装。"
            "请 pip install aiosqlite (已固定 0.22.1)。"
        )

# 驱动可用时才建 engine; 缺失时为 None, get_async_db 会 fail-fast 报清晰错误。
if _ASYNC_DRIVER_OK:
    if DB_TYPE == "postgres":
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=int(os.getenv("DB_POOL_SIZE", "50")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=POOL_PRE_PING,
            echo=ECHO_ENABLED,
        )
    else:
        async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            connect_args={"check_same_thread": False},
            pool_pre_ping=POOL_PRE_PING,
            echo=ECHO_ENABLED,
        )

    # expire_on_commit=False: 异步会话 commit 后访问 ORM 属性不再触发隐式刷新
    # (异步隐式 IO 在事件循环外抛 MissingGreenlet/IO during async), 与异步读写约定一致。
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
else:
    logger.warning("异步数据库驱动缺失, 异步会话已禁用: %s", _ASYNC_DRIVER_ERR)
    async_engine = None
    AsyncSessionLocal = None


def _ensure_async_driver():
    """异步会话访问前置校验: 驱动缺失 → 立即抛清晰错误 (fail-fast, 而非运行时 500)。"""
    if not _ASYNC_DRIVER_OK:
        raise RuntimeError(_ASYNC_DRIVER_ERR)


async def get_async_db():
    """获取异步数据库会话 (供含真实 await 的端点使用)。

    每请求独立 AsyncSession, 退出时自动关闭。配合 tests/conftest.py 的
    dependency_overrides 指向同一测试库, 保证测试可见性。
    """
    _ensure_async_driver()
    async with AsyncSessionLocal() as session:
        yield session


def init_db():
    """初始化数据库表"""
    from app.models import rbac as rbac_module
    from app.models import runbook as _runbook_model
    # Phase1: 新增遥测专表和预聚合模型
    Base.metadata.create_all(bind=engine)

    # 种子数据: 角色和权限
    try:
        session = SessionLocal()
        rbac_module.seed_roles_and_permissions(session)
        session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("RBAC种子数据初始化跳过: %s", e)

    # 种子数据: Runbook 内置模板 (硬编码→DB 持久化, spec maint-platform §2.6)
    try:
        session = SessionLocal()
        _runbook_model.seed_builtin_runbook_templates(session)
        session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Runbook种子数据初始化跳过: %s", e)