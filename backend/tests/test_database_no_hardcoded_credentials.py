"""
[卡439a1fcd] 移除硬编码DB凭证 — 安全回归测试

守护两条安全契约:
1. fail-fast: DB_TYPE=postgres 且未配置 DATABASE_URL 时, app.core.database 必须
   抛 RuntimeError 拒绝启动, 绝不回退到任何硬编码凭证串。
   必须用子进程隔离执行: 主测试进程在 conftest 阶段早已 import database
   (sqlite engine 已建), 无法重放模块级 fail-fast; 子进程从受控环境 import
   才能真实触发 database.py 顶部那段模块级代码。
2. 无硬编码: app/ 下任何 .py 不得再含已知泄露凭证 'tianlian123'。
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
LEAKED_SECRET = "tianlian123"


def _run_postgres_import(database_url: str) -> subprocess.CompletedProcess:
    """隔离子进程: 以 DB_TYPE=postgres import app.core.database。

    子进程继承父环境但钉死关键变量。database.py 顶部 load_dotenv() 默认
    override=False, 不会用 backend/.env 覆盖此处已设的环境变量, 因此能精确
    模拟"未配置 DATABASE_URL"(传空串)与"已配置"(传真实 DSN)两种场景。
    """
    env = os.environ.copy()
    env["DB_TYPE"] = "postgres"
    env["DATABASE_URL"] = database_url          # "" = 未配置; 非空 = 已配置
    env["DATABASE_URL_DEV"] = ""
    # 故意不把 engine 真正连上库; 只验证 import 期模块级行为。
    # 成功路径: print 到 stdout 后 sys.exit(0); 失败路径: import 期即抛错,
    # returncode=1 且 traceback 落 stderr (SystemExit('str') 会误返回 1, 故不用)。
    code = (
        "import sys; "
        "import app.core.database as d; "
        "print('IMPORT_OK:' + str(d.engine.url)); "
        "sys.exit(0)"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_postgres_missing_database_url_raises_runtime_error():
    """DB_TYPE=postgres 且 DATABASE_URL 为空 → 必须 RuntimeError, 不回退硬编码。"""
    result = _run_postgres_import("")
    # 修复前: import 成功(回退硬编码 localhost DSN) exit 0 → 此断言失败(RED)
    # 修复后: raise RuntimeError exit 1 → 通过(GREEN)
    assert result.returncode != 0, (
        "期望 fail-fast RuntimeError, 实际 import 成功并使用了回退凭证(安全漏洞):\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    combined = result.stderr + result.stdout
    assert "RuntimeError" in combined or "DATABASE_URL" in combined, (
        "子进程异常退出但消息未提及凭证缺失, 可能是无关错误掩盖了 fail-fast:\n"
        f"{combined}"
    )
    # fail-fast 路径绝不能在输出里泄露真实回退凭证
    assert LEAKED_SECRET not in combined, (
        f"检测到硬编码凭证回退泄露 '{LEAKED_SECRET}':\n{combined}"
    )


def test_postgres_with_database_url_imports_cleanly():
    """对照组: 配了 DATABASE_URL 时正常 import (排除环境/依赖损坏导致的误报)。"""
    result = _run_postgres_import("postgresql://u:p@127.0.0.1:5432/dummy")
    assert result.returncode == 0, (
        "配置了 DATABASE_URL 却 import 失败, 可能是无关错误而非 fail-fast:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "IMPORT_OK" in result.stdout


def test_no_hardcoded_secret_in_app_source():
    """app/ 下所有 .py 不得含泄露凭证 'tianlian123'。"""
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if LEAKED_SECRET in line:
                offenders.append(f"{path.relative_to(BACKEND_DIR)}:{i}: {line.strip()}")
    assert not offenders, (
        "app/ 源码仍含硬编码凭证 'tianlian123':\n" + "\n".join(offenders)
    )


def test_no_hardcoded_secret_in_alembic_ini():
    """[卡1ea0675a] alembic.ini 不得含泄露凭证 'tianlian123'。

    alembic.ini 的 sqlalchemy.url 仅作占位, 真实连接串由 ALEMBIC_DATABASE_URL
    环境变量覆盖 (见 alembic/env.py); 占位符不得内嵌已知泄露凭证。
    """
    alembic_ini = BACKEND_DIR / "alembic.ini"
    text = alembic_ini.read_text(encoding="utf-8")
    assert LEAKED_SECRET not in text, (
        f"alembic.ini 仍含硬编码凭证 '{LEAKED_SECRET}', "
        "应改为占位符并由 ALEMBIC_DATABASE_URL 覆盖"
    )
