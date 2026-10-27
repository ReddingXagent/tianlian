import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入所有模型以便 autogenerate 检测
from app.core.database import Base
from app.models import *  # noqa: F401,F403
from alembic_url_resolver import resolve_alembic_database_url  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# [卡b60a1d0d] 解析真实数据库 URL, 优先级: ALEMBIC_DATABASE_URL / DATABASE_URL 环境
# 变量 → backend/.env 的 DATABASE_URL → alembic.ini 原值。修复 bacc9ed17 占位化
# sqlalchemy.url 后, 生产 `alembic upgrade head` 报 'could not translate host name
# "ALEMBIC_HOST"' 的问题 (原 env.py 只读环境变量、不读 .env)。占位符交由解析器
# fail-fast 抛明确错误。逻辑抽到 alembic_url_resolver.py 以便单元测试。
config.set_main_option(
    "sqlalchemy.url",
    resolve_alembic_database_url(config.get_main_option("sqlalchemy.url") or ""),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# [卡057c8a9e] disable_existing_loggers=False: fileConfig 默认 True 会把进程内
# 已创建的 app.* logger 全部设 disabled=True (alembic.ini 只声明
# root/sqlalchemy/alembic 三个 logger, 本文件 import app.models 后业务 logger
# 均已存在)。生产 alembic 进程里这会误杀迁移期间的应用侧日志; 测试进程
# (tests/test_migration_chain_fresh_db.py 跑 command.upgrade) 里该状态跨测试
# 残留 → 后续所有 caplog 断言族消息缺失 (set_level/at_level 无法穿透
# logger.disabled), 全量串行 34 红的根因。
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 使用项目的 Base.metadata
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
