"""
[卡1e6cb038] SQLite 分支 DATABASE_URL / DATABASE_URL_DEV 优先级回归测试

守护契约 (DB_TYPE=sqlite 默认分支):
1. DATABASE_URL 显式指向 sqlite (sqlite:///...) → 优先于 DATABASE_URL_DEV 生效
   (修复: 用户按标准习惯设 DATABASE_URL=sqlite:///xxx.db 不再被静默吞掉)。
2. DATABASE_URL 是 postgres 等非 sqlite scheme → 忽略, 回退 DATABASE_URL_DEV
   (现网兼容路径: .env 同时定义 postgresql 的 DATABASE_URL 与 sqlite 的 _DEV)。
3. 两者都未设 → 默认 sqlite:///./tianlian_v3.db (原默认行为不变)。

必须用子进程隔离: 主测试进程 conftest 阶段早已 import database (engine 已建),
无法重放模块级 URL 解析; 子进程从受控环境 import 才真实触发模块级代码。
参考 test_database_no_hardcoded_credentials.py 的范式。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_sqlite_import(database_url: str | None, database_url_dev: str | None) -> str:
    """隔离子进程: 以 DB_TYPE=sqlite import app.core.database, 返回引擎 URL 字符串。

    子进程继承父环境但钉死关键变量。database.py 顶部 load_dotenv() 默认
    override=False, 不会用 backend/.env 覆盖此处已设的环境变量。
    传 None 表示从子进程环境删除该键 (真正模拟"未设置", load_dotenv 亦无法注入,
    因 backend/.env 未定义 DATABASE_URL 之外的覆盖来源; 空串会被 os.getenv 视为
    已设置从而绕过默认值, 故未设置必须用删除键模拟)。
    """
    env = os.environ.copy()
    env["DB_TYPE"] = "sqlite"
    for key, value in (("DATABASE_URL", database_url), ("DATABASE_URL_DEV", database_url_dev)):
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    code = (
        "import sys; "
        "import app.core.database as d; "
        "print('IMPORT_OK:' + str(d.engine.url)); "
        "sys.exit(0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"DB_TYPE=sqlite import 意外失败:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "IMPORT_OK:" in result.stdout, f"未捕获引擎 URL:\n{result.stdout}"
    return result.stdout.strip().split("IMPORT_OK:", 1)[1]


def test_sqlite_scheme_database_url_takes_precedence():
    """a) DATABASE_URL=sqlite://… 显式 sqlite → 优先于 DATABASE_URL_DEV。"""
    url = _run_sqlite_import(
        "sqlite:////tmp/tianlian_card_1e6cb038_a.db",
        "sqlite:////tmp/tianlian_card_1e6cb038_b.db",
    )
    assert url.startswith("sqlite:////tmp/tianlian_card_1e6cb038_a.db"), (
        f"显式 sqlite DATABASE_URL 被忽略, 实际引擎 URL: {url}"
    )


def test_postgres_scheme_database_url_ignored_in_sqlite_mode():
    """b) DATABASE_URL=postgresql://… → 忽略, 回退 DATABASE_URL_DEV (现网路径不变)。"""
    url = _run_sqlite_import(
        "postgresql://user:pass@127.0.0.1:5432/dummy",
        "sqlite:////tmp/tianlian_card_1e6cb038_b.db",
    )
    assert url.startswith("sqlite:////tmp/tianlian_card_1e6cb038_b.db"), (
        f"非 sqlite scheme 的 DATABASE_URL 应被忽略回退 _DEV, 实际引擎 URL: {url}"
    )


def test_both_unset_falls_back_to_default_dev_url():
    """c) 两者都未设 → 默认 sqlite:///./tianlian_v3.db。"""
    url = _run_sqlite_import(None, None)
    assert "tianlian_v3.db" in url, (
        f"未设任何变量时未落默认 ./tianlian_v3.db, 实际引擎 URL: {url}"
    )
