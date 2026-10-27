#!/usr/bin/env python3
"""
生产 schema 漂移检测守卫 (只读)。

背景
----
生产用 PostgreSQL, 测试用 SQLite (conftest 用 fresh DB + Base.metadata.create_all
从模型建表)。当模型加了列却漏写 alembic 迁移时, 测试全绿但生产缺列 —— 已发生两次
(v2g actual_energy_kwh / 14 缺列 + 5 缺索引)。本脚本只读对比 SQLAlchemy 模型
metadata 与目标库实际结构, 提前暴露漂移。

用法
----
本地 / 生产 (生产建议经跳板机执行, 不落凭据到磁盘):

    ssh prod 'cd /opt/tianlian-cloud/backend && .venv/bin/python scripts/check_schema_drift.py'

显式指定库 (优先级高于环境变量):

    .venv/bin/python scripts/check_schema_drift.py --url postgresql://user:pwd@host:5432/db
    DATABASE_URL=postgresql://... .venv/bin/python scripts/check_schema_drift.py

退出码
------
    0 = 无漂移 (孤儿列不算错, 仍返回 0)
    1 = 有漂移 (缺表 / 缺列 / 缺索引)
    2 = 连接失败

安全
----
绝对只读: 仅使用 SQLAlchemy inspector 查询 information_schema / PRAGMA, 不执行任何
DDL / 迁移 / 写操作。URL 通过 --url 或 DATABASE_URL 传入, 禁止在代码中硬编码凭据。
"""
import argparse
import os
import sys

# 自举: 让 `python scripts/check_schema_drift.py` 能 import backend 包
# (生产用法: cd /opt/tianlian-cloud/backend && .venv/bin/python scripts/check_schema_drift.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import MetaData, create_engine, inspect


@dataclass
class DriftReport:
    """模型 metadata 与目标库的结构差异。"""

    missing_tables: list = field(default_factory=list)        # 模型有 / 库无 (整表)
    missing_columns: dict = field(default_factory=dict)       # table -> [col, ...]
    missing_indexes: dict = field(default_factory=dict)       # table -> [idx_name, ...]
    orphan_columns: dict = field(default_factory=dict)        # 库有 / 模型无 (仅报告)

    def has_blocking_drift(self) -> bool:
        """是否存在必须修复的漂移 (孤儿列不算)。"""
        return bool(self.missing_tables or self.missing_columns or self.missing_indexes)


def detect_drift(inspector, metadata: MetaData) -> DriftReport:
    """对比 inspector 反映的库结构与模型 metadata, 返回漂移报告。

    - 缺列: 模型声明 / 库无
    - 孤儿列: 库有 / 模型无 (仅报告)
    - 缺索引: 只比对模型显式声明的 Index 与 column.index=True; 主键约束、唯一约束
      自动生成的索引跳过 (不计为模型声明索引, 也不算库缺失)。
    """
    report = DriftReport()
    db_tables = set(inspector.get_table_names())

    for table_name, table in metadata.tables.items():
        if table_name not in db_tables:
            report.missing_tables.append(table_name)
            continue

        # ── 列对比 ──
        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}
        missing = sorted(model_cols - db_cols)
        if missing:
            report.missing_columns[table_name] = missing
        orphan = sorted(db_cols - model_cols)
        if orphan:
            report.orphan_columns[table_name] = orphan

        # ── 索引对比 (只比模型显式声明的) ──
        declared_idx = {idx.name for idx in table.indexes if idx.name}
        db_idx = {i["name"] for i in inspector.get_indexes(table_name) if i.get("name")}
        # 主键 / 唯一约束自动生成的索引名算“库里有”, 避免误报。
        pk = inspector.get_pk_constraint(table_name) or {}
        if pk.get("name"):
            db_idx.add(pk["name"])
        for uc in inspector.get_unique_constraints(table_name) or []:
            if uc.get("name"):
                db_idx.add(uc["name"])
        miss_idx = sorted(declared_idx - db_idx)
        if miss_idx:
            report.missing_indexes[table_name] = miss_idx

    report.missing_tables.sort()
    return report


def render_report(report: DriftReport, url: str) -> str:
    """人类可读报告, 按 表名.列名 分组。"""
    lines = [
        "=== Schema Drift Report ===",
        f"目标库: {url}",
    ]
    if report.has_blocking_drift():
        lines.append("结论: ⚠ 检测到漂移 (模型与库不一致)")
    else:
        lines.append("结论: ✓ 无漂移 (模型与库一致)")

    if report.missing_tables:
        lines.append("")
        lines.append(f"[缺表] 模型有 / 库无 ({len(report.missing_tables)}):")
        lines += [f"  - {t}" for t in report.missing_tables]

    if report.missing_columns:
        lines.append("")
        lines.append("[缺列] 模型有 / 库无:")
        for t, cols in report.missing_columns.items():
            lines += [f"  - {t}.{c}" for c in cols]

    if report.missing_indexes:
        lines.append("")
        lines.append("[缺索引] 模型显式声明 / 库无:")
        for t, idxs in report.missing_indexes.items():
            lines += [f"  - {t}.{i}" for i in idxs]

    if report.orphan_columns:
        lines.append("")
        lines.append("[孤儿列] 库有 / 模型无 (仅报告, 不算漂移):")
        for t, cols in report.orphan_columns.items():
            lines += [f"  - {t}.{c}" for c in cols]

    n_mc = sum(len(v) for v in report.missing_columns.values())
    n_mi = sum(len(v) for v in report.missing_indexes.values())
    n_oc = sum(len(v) for v in report.orphan_columns.values())
    lines += [
        "",
        f"汇总: 缺表 {len(report.missing_tables)} / 缺列 {n_mc} / 缺索引 {n_mi} / 孤儿列 {n_oc}",
    ]
    return "\n".join(lines)


def run_check(url: Optional[str], metadata: Optional[MetaData] = None) -> tuple[int, str]:
    """执行检测, 返回 (exit_code, report_text)。

    metadata 默认从 app.models 的 Base.metadata 取 (延迟 import, 避免无谓副作用)。
    """
    if not url:
        return 2, "ERROR: 未提供数据库 URL (用 --url 或设置 DATABASE_URL 环境变量)"

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            if metadata is None:
                import app.models  # noqa: F401 — 触发全部模型注册到 Base.metadata
                from app.core.database import Base
                metadata = Base.metadata
            report = detect_drift(inspector, metadata)
    except Exception as e:
        return 2, f"连接失败: {type(e).__name__}: {e}"

    code = 1 if report.has_blocking_drift() else 0
    return code, render_report(report, url)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="只读检测 SQLAlchemy 模型与目标库的 schema 漂移 (缺表/缺列/缺索引)。",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("DATABASE_URL"),
        help="目标库 URL; 缺省时读 DATABASE_URL 环境变量。禁硬编码凭据。",
    )
    args = parser.parse_args(argv)

    code, text = run_check(args.url)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
