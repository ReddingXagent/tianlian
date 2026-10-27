"""alembic 数据库 URL 解析 (卡 b60a1d0d)。

抽取自 alembic/env.py 以便单元测试 —— env.py 顶部 import 了 alembic.context 与
app 模型 (直接 import 会触发副作用), 且 alembic/ 目录与已安装的 alembic 库命名冲突、
无法作为包导入。本模块零 app 依赖, 仅用 os + dotenv, 可被 env.py 与 tests 直接导入。

解决的问题
----------
commit bacc9ed17 把 alembic.ini 的 sqlalchemy.url 占位化 (移除明文凭证) 后, 生产
`alembic upgrade head` 报 'could not translate host name "ALEMBIC_HOST"'。根因:
原 env.py 只读 ALEMBIC_DATABASE_URL 环境变量, 不读 backend/.env 的 DATABASE_URL,
而生产 DATABASE_URL 恰好只配在 .env 里。本模块按优先级解析真实 URL 并对占位符
fail-fast, 给运维明确指引而非 psycopg2 的底层天书。

优先级 (高 → 低)
----------------
1. ALEMBIC_DATABASE_URL 环境变量 —— 显式 override, 向后兼容本地 SQLite 验证
   (见记忆 alembic-upgrade-head-sqlite-baseline-conflict)。
2. DATABASE_URL 环境变量。
3. backend/.env 文件里的 DATABASE_URL (生产主路径)。
4. alembic.ini sqlalchemy.url 原值 (通常为占位符 → 触发 _guard_placeholder)。
"""
import os
from pathlib import Path
from typing import Mapping, Optional

from dotenv import dotenv_values

# alembic.ini 占位串里出现的 token; 最终 URL 含任一即判定为未配置真实凭证。
# 用具体 token 而非裸 "ALEMBIC" 前缀, 避免误伤含该词的真实主机名/口令。
_PLACEHOLDER_TOKENS = ("ALEMBIC_HOST", "ALEMBIC_USER", "ALEMBIC_PASSWORD", "ALEMBIC_DB")


def _read_dotenv_value(key: str, dotenv_path: Path) -> Optional[str]:
    """从 .env 文件读取某个 key 的值, 不污染 os.environ; 文件缺失或无该键返回 None。

    dotenv_values 会自动剥掉值两侧的引号, 与 shell / app 的 load_dotenv 语义一致。
    """
    if not dotenv_path.is_file():
        return None
    val = dotenv_values(str(dotenv_path)).get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _guard_placeholder(url: str, source: str) -> str:
    """URL 含 alembic.ini 占位符 token 时抛 RuntimeError, 给出明确修复指引。"""
    for token in _PLACEHOLDER_TOKENS:
        if token in url:
            raise RuntimeError(
                f"alembic 数据库 URL 未配置真实凭证 (来源: {source}): URL 含占位符 "
                f"{token!r}。请设置环境变量 DATABASE_URL (或 ALEMBIC_DATABASE_URL), "
                f"或在 backend/.env 中配置 DATABASE_URL=<真实连接串>; 原占位 URL: {url}"
            )
    return url


def resolve_alembic_database_url(
    ini_url: str,
    env: Optional[Mapping[str, str]] = None,
    dotenv_path: Optional[Path] = None,
) -> str:
    """按优先级解析 alembic 使用的数据库 URL, 并对占位符 fail-fast。

    任一级取到的值都过占位符校验: 含 ALEMBIC_HOST 等 token 即抛 RuntimeError,
    避免把占位串交给 psycopg2 报 'could not translate host name "ALEMBIC_HOST"'。

    参数:
      ini_url:      alembic.ini 的 sqlalchemy.url 原值 (最低优先级兜底)。
      env:          环境变量映射; 缺省读 os.environ。仅用于注入测试。
      dotenv_path:  .env 文件路径; 缺省指向与本文件同目录的 backend/.env。仅用于注入测试。

    返回:
      可直接交给 SQLAlchemy 的真实数据库 URL。
    """
    if env is None:
        env = os.environ
    if dotenv_path is None:
        # 本模块位于 backend/alembic_url_resolver.py → backend/.env 与本文件同目录
        dotenv_path = Path(__file__).resolve().parent / ".env"

    # 1) + 2) 环境变量 (ALEMBIC_DATABASE_URL 优先, 再 DATABASE_URL)
    for key in ("ALEMBIC_DATABASE_URL", "DATABASE_URL"):
        val = env.get(key)
        if isinstance(val, str) and val.strip():
            return _guard_placeholder(val.strip(), f"环境变量 {key}")

    # 3) backend/.env 的 DATABASE_URL
    dotenv_val = _read_dotenv_value("DATABASE_URL", dotenv_path)
    if dotenv_val:
        return _guard_placeholder(dotenv_val, f".env ({dotenv_path})")

    # 4) alembic.ini 原值 (大概率仍是占位符 → _guard_placeholder 抛明确错误)
    return _guard_placeholder(ini_url, "alembic.ini sqlalchemy.url")
