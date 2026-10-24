"""
天链 V3 后端测试 Fixtures

每个测试函数使用独立临时 SQLite 文件副本。
"""
import os, tempfile, shutil
import logging
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# 强制测试环境使用 SQLite，必须在导入任何 app 模块之前设置
os.environ["DB_TYPE"] = "sqlite"
# 卡af65de3b: 默认库指向 UUID 临时文件而非 cwd 相对 ./tianlian_v3.db 陈旧开发库。
# 该陈旧库 stations 表 25 列、无 contact_person, 与模型/alembic baseline 漂移;
# 模块级 `from app.core.database import SessionLocal` 的 15 个生产文件 (tasks/services 等)
# 不经 fixture override, 会直连这个漂移库。UUID 临时库为空文件, 连上即显式失败而非静默读脏数据。
from uuid import uuid4
_TMP_DB_URL = f"sqlite:////tmp/tianlian_env_{uuid4().hex}.db"
os.environ["DATABASE_URL"] = _TMP_DB_URL
# app/core/database.py SQLite 分支读取 DATABASE_URL (仅 sqlite scheme 时生效, 卡1e6cb038)
# 与 DATABASE_URL_DEV (.env 定义后者指向 ./tianlian_v3.db), 必须一并覆盖;
# load_dotenv() 默认不覆盖已存在的 env 变量。
os.environ["DATABASE_URL_DEV"] = _TMP_DB_URL
# 测试 SECRET_KEY 必须 ≥32 字节 (RFC 7518 §3.2), 否则 PyJWT 抛 InsecureKeyLengthWarning
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-32bytes-plus")
os.environ["SKIP_CSRF"] = "true"  # 测试环境跳过 CSRF 校验
# 测试默认关闭限流 (TestClient 同 IP 会撞 5/min 登录上限, 致 test_auth*.py 误红);
# 需测限流本身时在测试内 monkeypatch limiter.enabled=True (见 test_auth_rate_limit.py)
os.environ["RATE_LIMIT_ENABLED"] = "false"

# 卡17354607: _fast_hash / _PRECOMPUTED_HASHES 抽到 tests/_test_helpers.py,
# conftest 与各测试文件统一用 `from tests._test_helpers import` 引用
# (tests/ 是含 __init__.py 的 package, 须走包式导入),
# 避免 `from conftest import` 在收集期 ModuleNotFoundError。
# 卡43bb99d7: 原缓存语义保持不变 (进程级 bcrypt hash 复用)。
from tests._test_helpers import _fast_hash, _PRECOMPUTED_HASHES  # noqa: F401


def pytest_configure(config):
    """卡f88180ac: 启动时检测残留 pytest 进程并警告。

    根因: 全量 pytest「>N 分钟无输出疑似卡死」反复出现, 真因不是测试本身死锁,
    而是上一轮(或别的 assistant_model 实例用 .venv2/python3)跑 pytest 后未清理, 进程被
    launchd 收养(PPID=1)成孤儿, 长期占满 CPU 拖死新进程。pytest.ini 的 --timeout
    只防「自己这个进程内的测试 hang」, 防不住「被别人的僵尸进程拖死」。

    本钩子只在 controller 主进程跑一次(xdist worker 跳过, 避免误判), 检测到本项目
    残留 pytest 进程时打印醒目警告 + 清理命令, 不自动 pkill(避免误杀用户在另一个
    终端正在调试的并行测试)。检测轻量: 仅 ps + awk, 不拖慢启动。
    """
    # xdist worker 进程有 workerinput, controller 没有; 只在 controller 检测一次
    if hasattr(config, "workerinput"):
        return
    try:
        import subprocess
        out = subprocess.run(
            ["ps", "-eo", "pid,ppid,etime,command"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        own_pid = str(os.getpid())
        # 命中条件: command 第一段是 Python 解释器 + 带 -m pytest/bin/pytest + 本项目 tests/
        # 必须看「command 第一段」(实际可执行路径), 不能整行 grep —— assistant_model 工具调用的
        # zsh wrapper 命令行里会嵌入完整任务文本(含 'pytest tests' 字样), 整行匹配会误中。
        stale = []
        for line in out.splitlines()[1:]:  # 跳过表头
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            pid, ppid, elapsed, command = parts[0], parts[1], parts[2], parts[3]
            if pid == own_pid:
                continue
            # command 第一段 = 解释器绝对路径, 必须 python(排除 /bin/zsh /bin/bash 等)
            exe = command.split()[0] if command.split() else ""
            if "/python" not in exe.lower() and not exe.lower().endswith("python"):
                continue
            if ("-m pytest" not in command and "bin/pytest" not in command):
                continue
            if "tests/" not in command:
                continue
            # 不强制 command 含项目绝对路径: 后台 nohup 起的 pytest command 通常是
            # 'python -m pytest tests/'(相对路径), cwd 决定项目但 ps 不显示 cwd。
            # 本钩子只警告不自动杀, 误报代价低; 真隔离靠人工核对 ELAPSED/PID。
            stale.append(f"  PID={pid} PPID={ppid} ELAPSED={elapsed}  {command[:80]}")
        if stale:
            config.stash.setdefault("_stale_pytest_warning", True)
            print(
                "\n" + "=" * 78 +
                "\n⚠ 卡f88180ac: 检测到 {} 个残留 pytest 进程在跑, 会占 CPU 拖慢/拖死本次运行:".format(len(stale))
                + "\n" + "\n".join(stale)
                + "\n建议清理后重试:"
                + "\n  pkill -9 -f 'pytest tests' ; pkill -9 -f 'for f in tests'"
                + "\n(确认无误后再杀; 仅杀 tianlian-cloud 相关, 不影响其它项目)"
                + "\n" + "=" * 78 + "\n",
                flush=True,
            )
    except Exception:
        # 检测本身绝不能阻塞测试启动, 任何异常都静默吞掉
        pass


@pytest.fixture(scope="session")
def _session_app():
    """session 级 FastAPI app (872 路由 + health 端点), 全测试复用。

    根因: client fixture 每 test 重建 app + include_router(872 路由) 固有耗时 ~0.67s,
    是 client fixture setup 慢(~2.3s/test) 的主因 —— 单文件数十测试累计超 60s, 表现为"挂起"。
    session 级建一次, 每 test 仅切 dependency_overrides。
    """
    from app.api.v1 import api_router
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    for _path, _handler in [
        ("/", lambda: {"name": "app", "version": "3.0.0", "status": "running"}),
        ("/api/v1/health", lambda: {"status": "healthy", "version": "3.0.0"}),
        ("/api/v1/live", lambda: {"status": "alive", "uptime_seconds": 0}),
        ("/api/v1/livez", lambda: {"status": "alive", "uptime_seconds": 0}),
        ("/api/v1/ready", lambda: {"status": "ready", "checks": {"database": {"status": "ok"}}, "uptime_seconds": 0}),
        ("/api/v1/readyz", lambda: {"status": "ready", "checks": {"database": {"status": "ok"}}, "uptime_seconds": 0}),
        ("/api/v1/ping", lambda: {"message": "pong"}),
    ]:
        app.get(_path)(_handler)
    yield app


@pytest.fixture(scope="session")
def _client_template_db(_schema_template_db):
    """session 级 seeded 模板 DB: schema + RBAC + admin, 供 client fixture 每 test 复制。

    根因: client fixture 每 test create_all(0.4s) + seed RBAC/admin(0.4s) 是 setup 慢的次因。
    session 级预 seed 一次, 每 test 仅 shutil.copy2(~0.01s)。
    独立于 _schema_template_db (后者只建 schema, test_db 依赖其纯净语义, 不可预 seed)。
    """
    import uuid
    db_path = f"/tmp/tianlian_client_tpl_{uuid.uuid4().hex}.db"
    shutil.copy2(_schema_template_db, db_path)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session = sessionmaker(bind=engine)()
    from app.models.rbac import seed_roles_and_permissions
    try:
        seed_roles_and_permissions(session)
    except Exception:
        session.rollback()
    session.commit()
    from app.models.user import User, UserRole
    if not session.query(User).filter(User.username == "admin").first():
        session.add(User(
            username="admin",
            password_hash=_fast_hash("admin123"),
            role=UserRole.ADMIN,
            status="active",
        ))
    session.commit()
    session.close()
    engine.dispose()
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def db_session(client):
    """SQLAlchemy session (same DB as client fixture)"""
    return client._sesh


def _login_admin_token(c):
    """登录 admin 拿 token，供 client fixture 默认注入认证头。"""
    r = c.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    if r.status_code != 200:
        return None
    return r.json().get("data", {}).get("token")


@pytest.fixture(autouse=True)
def _isolate_memory_cache():
    """卡2f8e2e32: 全局兜底 —— 每测试 setup 前清空 app.core.cache 模块级内存缓存。

    根因: client fixture 切库时清缓存, 但 test_db fixture 只隔离 DB (独立 sqlite
    副本 + override SessionLocal) 不清内存缓存 → 经 test_db 的用例 (模块级
    TestClient(app.main.app) + 服务层直调) 跨用例共享 _MEMORY_CACHE。eb0e1afd
    (b97e22006) 复活 stats 缓存写侧后, cache key (如 alert_workflow:stats:all)
    不含库维度而测试库 id 序列相同 (admin 恒 "all"), 换库后同 key 命中上一用例
    旧值 → 串扰假绿/假红 (复现: tests/test_cache_isolation.py)。全仓 9+ 测试文件
    的用例内手工 clear_memory_cache 自救 (test_alert_workflow/test_stats_service
    等) 即本缺口症状, 本 fixture 之后那些手工调用均为幂等冗余。

    与 client fixture 内的切库清理保守共存 (不收敛为一处): 该处语义是「换库瞬间
    清」与 DB 生命周期强绑定, 本处语义是「每测试边界清」的隔离基建; clear 幂等
    双调零成本, 而改 client fixture 既有行为有破坏面, 保守优先不动。
    """
    from app.core.cache import clear_memory_cache
    clear_memory_cache()
    yield


@pytest.fixture(autouse=True)
def _silence_env_slow_request_log():
    """卡057c8a9e: 环境性慢请求 WARNING 噪声隔离 (可恢复)。

    根因: RequestIDMiddleware 对 duration>100ms 的请求发 WARNING (logger
    "app.middleware.request", app/middleware/logging_middleware.py:129)。串行
    全量长跑机器负载高时, client fixture 的 login 及测试内请求随机超 100ms →
    该 WARNING 实时混入当前测试 caplog.records → caplog/timing_log 严格断言族
    (all(levelno < WARNING)/条数/records[0]) 随机红; 轻载重放即绿 (卡 145af9a1
    不可复现之谜同根因)。压到 ERROR 仅滤掉时敏的慢请求 WARNING; 500 异常路径的
    ERROR 级仍放行 (error.log 监控不缺)。

    兼容: 显式测试中间件日志的用例 (tests/core/test_logging_middleware.py,
    tests/test_caplog_noise_guard_card057c8a9e.py) 自带
    caplog.set_level(DEBUG, logger="app.middleware.request") 前置覆盖, 不受
    本压制影响 (caplog teardown 先恢复到压制值, 本 fixture teardown 再恢复
    原值, 时序无冲突)。
    """
    target = logging.getLogger("app.middleware.request")
    saved_level = target.level
    target.setLevel(logging.ERROR)
    try:
        yield
    finally:
        target.setLevel(saved_level)


@pytest.fixture(scope="function")
def client(_session_app, _client_template_db):
    """默认带 admin 认证头的 client。

    全局 enforce_auth 要求所有非白名单端点认证，故 API 测试默认登录为 admin，
    免去逐个注入 token。需要测「匿名拒绝(401)/白名单端点」时改用 anon_client。
    认证漏洞由 tests/test_auth_enforcement.py 兜底扫描所有非白名单端点。

    优化(卡 c7e9): 复用 session 级 app(_session_app, 免每 test include 872 路由 0.67s) +
    复制 session 级 seeded 模板(_client_template_db, 免每 test create_all+seed 0.8s)。
    每 test 仅切 DB + login, setup 从 ~2.3s 降到 ~0.5s。
    行为等价: 每 test 独立 DB 文件(隔离) + admin token 注入, 与原实现一致。
    require_permission (app/middleware/permission.py) 用 SessionLocal 查 user, 需与
    get_db 一致指向本测试库 (卡 b9d16fae)。
    """
    import uuid
    from app.core.database import get_db
    import app.core.database as db_module
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

    app = _session_app
    db_path = f"/tmp/tianlian_test_{uuid.uuid4().hex}.db"
    shutil.copy2(_client_template_db, db_path)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session = sessionmaker(bind=engine)()

    # 卡52f731ac: 异步会话指向同一测试库 (sqlite+aiosqlite)。用 NullPool —— 连接用后即关
    # (在 TestClient 事件循环存活期内), 不跨请求/跨 test 残留 → 无需 dispose、不污染主线程
    # 事件循环 policy (避免 asyncio.run 破坏后续 asyncio.get_event_loop() 用例)。
    # override 模块级全局 AsyncSessionLocal (与 SessionLocal 同模式), 覆盖所有 app 实例
    # (含 app.main.app 的模块级 client), 保证 async 端点读到测试库而非生产库。
    _async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    _test_async_sessionmaker = async_sessionmaker(
        bind=_async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False,
    )

    _orig_session_local = db_module.SessionLocal
    # 每 client 切库时同步清空内存缓存 (app.core.cache 模块级缓存跨 test 存活,
    # 读端点手写稳定 cache key 后真正会命中, 会把上一 test 的数据串进本 test)。
    # 卡2f8e2e32: 全量用例的兜底清空已上移为 autouse fixture _isolate_memory_cache
    # (覆盖不经 client 的 test_db 路径), 此处保留换库瞬间的清理作双保险, 幂等零成本。
    from app.core.cache import clear_memory_cache
    clear_memory_cache()
    db_module.SessionLocal = sessionmaker(bind=engine)
    _orig_async_session_local = db_module.AsyncSessionLocal
    db_module.AsyncSessionLocal = _test_async_sessionmaker
    # session 级 app 跨 test 复用, 必须 finally 还原 override, 否则泄漏到后续 test
    _orig_get_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session

    try:
        with TestClient(app) as c:
            c._sesh = session
            token = _login_admin_token(c)
            if token:
                c.headers["Authorization"] = f"Bearer {token}"
            yield c
    finally:
        if _orig_get_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = _orig_get_db_override
        db_module.SessionLocal = _orig_session_local
        db_module.AsyncSessionLocal = _orig_async_session_local
        session.close()
        engine.dispose()
        os.unlink(db_path)


@pytest.fixture(scope="function")
def anon_client(client):
    """共享 client 的 DB/app，但清除认证头 —— 用于测匿名拒绝(401)与白名单端点。"""
    client.headers.pop("Authorization", None)
    yield client


@pytest.fixture(autouse=True)
def _auth_module_level_client(request):
    """对 module-level `client = TestClient(app.main.app)` 注入 admin token。

    这类测试文件（如 test_tasks/test_stats）不经过 conftest client fixture，
    故 client 默认 token 无效。本 fixture 在每个测试前，对测试模块顶层的
    TestClient 实例登录并注入 Authorization 头，适配全局 enforce_auth。
    仅作用于顶层定义了 `client = TestClient(...)` 的模块，其余测试零开销。
    """
    mod_client = getattr(request.module, "client", None)
    if not isinstance(mod_client, TestClient):
        yield
        return
    # 确保 test_db 已运行（SessionLocal override + admin seed）
    try:
        request.getfixturevalue("test_db")
    except Exception:
        pass
    try:
        r = mod_client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        if r.status_code == 200:
            token = r.json().get("data", {}).get("token")
            if token:
                mod_client.headers["Authorization"] = f"Bearer {token}"
    except Exception:
        pass
    yield


@pytest.fixture
async def async_client():
    """异步 HTTP client（绑定全局 app，供 async 测试如 alert-webhook 使用）。"""
    import httpx
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(scope="function")
def seed_users(client):
    """Seed essential users, ensuring no duplicate unique constraints."""
    from app.models.user import User, UserRole
    s = client._sesh
    # Helper to add if missing
    def add_user(username, password, real_name, role, status):
        if not s.query(User).filter(User.username == username).first():
            s.add(User(
                username=username,
                password_hash=_fast_hash(password),
                real_name=real_name,
                role=role,
                status=status,
            ))
    add_user("admin", "admin123", "管理员", UserRole.ADMIN, "active")
    add_user("engineer1", "eng123", "工程师张三", UserRole.ENGINEER, "active")
    add_user("viewer1", "view123", "观察员李四", UserRole.VIEWER, "active")
    add_user("inactive_user", "inactive123", "停用用户", UserRole.ENGINEER, "inactive")
    s.commit()
    return {u: s.query(User).filter(User.username == u).first() for u in ["admin", "engineer1", "viewer1", "inactive_user"]}

@pytest.fixture(scope="function")
def seed_stations(client, seed_users):
    from app.models.station import Station, StationStatus
    s = client._sesh
    s1 = Station(name="测试电站A", code="STA001", address="北京市朝阳区", status=StationStatus.NORMAL)
    s2 = Station(name="测试电站B", code="STA002", address="上海市浦东新区", status=StationStatus.NORMAL)
    s.add_all([s1, s2])
    s.commit()
    s.refresh(s1)
    s.refresh(s2)
    return {"station_a": s1, "station_b": s2}


@pytest.fixture(scope="function")
def seed_devices(client, seed_stations):
    from app.models.device import Device, DeviceType, DeviceStatus
    s = client._sesh
    dt = [("SN-TEST-001","逆变器#1","INV001",DeviceType.PV_INVERTER,DeviceStatus.ONLINE,"station_a",20.0),
          ("SN-TEST-002","充电桩#1","CHG001",DeviceType.CHARGER_DC,DeviceStatus.ONLINE,"station_a",120.0),
          ("SN-TEST-003","储能PCS#1","PCS001",DeviceType.PCS,DeviceStatus.FAULT,"station_b",50.0),
          ("SN-TEST-004","离线设备#1","OFF001",DeviceType.BATTERY_INVERTER,DeviceStatus.OFFLINE,"station_b",None)]
    for sn,name,code,dtype,status,sk,rp in dt:
        s.add(Device(sn=sn,name=name,code=code,type=dtype,status=status,station_id=seed_stations[sk].id,rated_power=rp))
    s.commit()
    return {code.lower(): s.query(Device).filter(Device.sn == sn).first() for sn,_,code,_,_,_,_ in dt}


@pytest.fixture(scope="function")
def seed_alarms(client, seed_devices):
    from app.models.alarm import Alarm, AlarmLevel, AlarmStatus
    s = client._sesh
    objs = [
        Alarm(device_id=seed_devices["inv001"].id, alarm_type="over_temp", level=AlarmLevel.WARNING, content="温度过高", status=AlarmStatus.ACTIVE),
        Alarm(device_id=seed_devices["pcs001"].id, alarm_type="comm_fault", level=AlarmLevel.CRITICAL, content="通讯中断", status=AlarmStatus.ACTIVE),
        Alarm(device_id=seed_devices["chg001"].id, alarm_type="emergency_stop", level=AlarmLevel.CRITICAL, content="急停触发", status=AlarmStatus.RESOLVED),
    ]
    s.add_all(objs)
    s.commit()
    for o in objs:
        s.refresh(o)
    return {"over_temp": objs[0], "comm_fault": objs[1], "emergency": objs[2]}


def _get_token(client, username="admin", password="admin123"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    if r.status_code != 200: return ""
    inner = r.json().get("data", {})
    return inner.get("token", "")


@pytest.fixture(scope="session")
def _schema_template_db():
    """session 级：从模型建一次完整 schema 的 DB，供 test_db 复制（避免每个测试 create_all 全表，大幅加速）。"""
    import uuid
    from sqlalchemy import BigInteger as SA_BigInteger
    from sqlalchemy.ext.compiler import compiles
    from app.core.database import Base
    import app.models  # 导入所有模型，确保 Base.metadata 包含所有表

    @compiles(SA_BigInteger, "sqlite")
    def _compile_bigint_sqlite(element, compiler, **kw):
        return "INTEGER"

    db_path = f"/tmp/tianlian_schema_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    # Create report_mgmt table (raw SQL, no ORM model yet)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS report_mgmt (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                station_id INTEGER,
                author TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                content TEXT NOT NULL DEFAULT '{}',
                summary TEXT,
                period_start TEXT,
                period_end TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Create system_configs table for key-value JSON config storage
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS system_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_value TEXT NOT NULL DEFAULT '{}',
                type TEXT NOT NULL DEFAULT 'global',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
    
    engine.dispose()
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def test_db(_schema_template_db):
    """独立测试 DB 环境（兼容旧测试签名），返回 dict {engine, session, SessionLocal, get_db}。

    复制 session 级 schema 模板（保证 schema 与代码同步，如 users.email）-> seed RBAC + admin -> override 模块级 SessionLocal。
    服务层测试通过 `from app.core.database import SessionLocal` 拿到的即此测试库，实现完全隔离。
    """
    import uuid
    from app.core.database import Base
    import app.core.database as db_module
    from sqlalchemy.pool import NullPool
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

    db_path = f"/tmp/tianlian_test_{uuid.uuid4().hex}.db"
    shutil.copy2(_schema_template_db, db_path)

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    from app.models.rbac import seed_roles_and_permissions
    try:
        seed_roles_and_permissions(session)
    except Exception:
        session.rollback()
    session.commit()

    from app.models.user import User, UserRole
    session.add(User(
        username="admin",
        password_hash=_fast_hash("admin123"),
        role=UserRole.ADMIN,
        status="active",
    ))
    session.commit()
    session.close()

    # 关键：覆盖模块级 SessionLocal，服务层 `from app.core.database import SessionLocal` 即此库
    _orig_session_local = db_module.SessionLocal
    db_module.SessionLocal = TestingSessionLocal

    # 卡52f731ac: 同步 override 之外, 额外覆盖模块级 AsyncSessionLocal 指向本测试库。
    # 模块级 TestClient(app.main.app) 的测试 (如 test_predictive_maintenance) 经 get_async_db
    # 读全局 AsyncSessionLocal —— 不覆盖则落到生产库 tianlian_v3.db (查到 device 1 → 400, 非 404)。
    # NullPool: 连接用后即关, 无跨事件循环残留 → 不 dispose、不污染主线程 loop policy。
    _async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    _test_async_sessionmaker = async_sessionmaker(
        bind=_async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False,
    )
    _orig_async_session_local = db_module.AsyncSessionLocal
    db_module.AsyncSessionLocal = _test_async_sessionmaker

    def get_test_db():
        return TestingSessionLocal()

    yield {
        "engine": engine,
        "session": TestingSessionLocal(),
        "SessionLocal": TestingSessionLocal,
        "get_db": get_test_db,
    }

    db_module.SessionLocal = _orig_session_local
    db_module.AsyncSessionLocal = _orig_async_session_local
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)