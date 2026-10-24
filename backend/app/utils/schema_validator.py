"""
Schema 同步保障工具

启动时对比 SQLAlchemy Base.metadata 与实际 DB schema，自动补齐偏差:
  - 缺表  → 自动 CREATE TABLE（所有环境，幂等安全）
  - 缺列  → 开发环境(sqlite) 自动 ALTER TABLE ADD COLUMN
            生产环境(postgres) 仅 WARNING（提示走 alembic 迁移，避免误改生产 schema）

设计原则:
  1. 永不阻断启动 — 任何异常都 catch 并降级为日志，返回 warnings
  2. 生产只读告警 — postgres 下绝不自动 DDL，schema 变更必须经 alembic 受控迁移
  3. 幂等         — 多次执行无副作用，已存在的表/列跳过
  4. idempotent DDL — CREATE TABLE 用 checkfirst，ADD COLUMN 先查 inspector
"""
import logging
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import MetaData

from app.core.database import Base, engine, DB_TYPE

logger = logging.getLogger(__name__)


def _is_dev_db(db_type: Optional[str] = None) -> bool:
    """开发环境判定：sqlite 视为开发，postgres 视为生产。

    与 database.py 的约定一致：SQLite=开发，PostgreSQL=生产。
    """
    return (db_type or DB_TYPE) != "postgres"


def validate_schema(
    eng: Optional[Engine] = None,
    metadata: Optional[MetaData] = None,
) -> dict:
    """对比 metadata 与 DB，缺表建表，缺列开发自动补 / 生产告警。

    Args:
        eng: 目标 engine，默认 app.core.database.engine
        metadata: 模型 metadata，默认 Base.metadata

    Returns:
        {
          "created_tables": [...],   # 已自动创建的表
          "added_columns":  [...],   # 已自动补齐的列 (table.col)
          "warnings":       [...],   # 警告/失败信息
        }

    永不抛异常 — 失败一律降级为 warnings，避免阻断应用启动。
    """
    eng = eng if eng is not None else engine
    metadata = metadata if metadata is not None else Base.metadata
    result: dict = {"created_tables": [], "added_columns": [], "warnings": []}

    try:
        insp = inspect(eng)
        existing_tables = set(insp.get_table_names())
    except SQLAlchemyError as e:
        msg = f"无法读取 DB inspector（跳过 schema 校验）: {e}"
        logger.warning("[schema-validator] %s", msg)
        result["warnings"].append(msg)
        return result

    dev_mode = _is_dev_db()

    for table_name, table_obj in metadata.tables.items():
        # ─── 缺表 → CREATE TABLE ───
        if table_name not in existing_tables:
            try:
                table_obj.create(eng, checkfirst=True)
                result["created_tables"].append(table_name)
                logger.info("[schema-validator] 缺表已创建: %s", table_name)
            except SQLAlchemyError as e:
                msg = f"创建表 {table_name} 失败: {e}"
                logger.warning("[schema-validator] %s", msg)
                result["warnings"].append(msg)
            continue

        # ─── 表已存在 → 检查列差异 ───
        try:
            db_cols = {c["name"] for c in insp.get_columns(table_name)}
        except SQLAlchemyError:
            continue

        missing_cols = [c for c in table_obj.columns if c.name not in db_cols]
        if not missing_cols:
            continue

        if dev_mode:
            # 开发环境：自动 ALTER ADD COLUMN（不带约束，最兼容）
            for col in missing_cols:
                try:
                    col_type = col.type.compile(dialect=eng.dialect)
                    ddl = (
                        f'ALTER TABLE "{table_name}" '
                        f'ADD COLUMN "{col.name}" {col_type}'
                    )
                    with eng.begin() as conn:
                        conn.execute(text(ddl))
                    result["added_columns"].append(f"{table_name}.{col.name}")
                    logger.info(
                        "[schema-validator] 缺列已补: %s.%s (%s)",
                        table_name, col.name, col_type,
                    )
                except SQLAlchemyError as e:
                    msg = f"补列 {table_name}.{col.name} 失败: {e}"
                    logger.warning("[schema-validator] %s", msg)
                    result["warnings"].append(msg)
        else:
            # 生产环境：仅 WARNING，不改 schema
            for col in missing_cols:
                w = (
                    f"生产环境缺列 {table_name}.{col.name} "
                    f"— 请用 alembic 迁移补齐，已跳过自动修复"
                )
                result["warnings"].append(w)
                logger.warning("[schema-validator] %s", w)

    created = len(result["created_tables"])
    added = len(result["added_columns"])
    warns = len(result["warnings"])
    if created or added or warns:
        logger.info(
            "[schema-validator] 完成 (mode=%s): 建表 %d, 补列 %d, 警告 %d",
            "dev" if dev_mode else "prod", created, added, warns,
        )
    return result
