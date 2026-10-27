"""add_team_id_to_knowledge

Revision ID: d1e2f3a4b5c6
Revises: merge_001
Create Date: 2026-07-24 15:30:00.000000

天链助手账户数据隔离: 给知识库表补 team_id 列。

背景: 模型层 (app/models/knowledge.py) 已为 KnowledgeArticle / KnowledgeFAQ
新增 team_id 字段(Integer, default=0, index=True), 但 knowledge_* 表由
Base.metadata.create_all() 在运行时创建, 不在 baseline migration 内,
故已存在的持久库(开发 SQLite / 生产 Postgres)的这两张表仍缺 team_id 列。
运行时 ai_chat._query_knowledge_base 按 team_id 过滤会抛
"no such column: knowledge_articles.team_id" 并被 except 吞掉 -> RAG 静默失效。

本 migration 幂等地补齐该列(已有则跳过), 保证 schema 与模型一致。
向后兼容: server_default='0' 使旧行归为平台共享(team_id=0, 全平台可见)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "merge_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TEAM_TABLES = ("knowledge_articles", "knowledge_faq")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in _TEAM_TABLES:
        if not inspector.has_table(table):
            # 表尚未创建(create_all 会按最新模型建, 已含 team_id) -> 无需补列
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if "team_id" not in existing_cols:
            op.add_column(
                table,
                sa.Column("team_id", sa.Integer(), nullable=False, server_default="0",
                          comment="数据隔离: 0=平台共享, >0=企业专属"),
            )
        # 幂等建索引
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        idx_name = f"ix_{table}_team_id"
        if idx_name not in existing_indexes:
            op.create_index(idx_name, table, ["team_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in _TEAM_TABLES:
        if not inspector.has_table(table):
            continue
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        idx_name = f"ix_{table}_team_id"
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name=table)
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if "team_id" in existing_cols:
            op.drop_column(table, "team_id")
