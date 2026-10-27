"""add_agent_memory_tables

Revision ID: a9b1c2d3e4f5
Revises: 202608081200
Create Date: 2026-08-09 14:00:00.000000

天链智能体 P1 记忆 (设计文档 §5.2): 两张表
- agent_memory: 巡检发现 / 诊断结论 / 经验积累 (智能体长期记忆)
- agent_conversation: 三板块助手对话历史 (短期对话上下文)

类型说明: 设计文档示例用 JSONB, 但实现统一用 sa.JSON():
- 模型层 (app/models/agent_memory.py) 用 JSON (SQLite 测试必须, PG 同样支持);
- 迁移层与模型层保持一致用 JSON, 避免后续 autogenerate 的类型 drift;
- 当前需求为关键词 ILIKE 搜索, 不依赖 JSONB 的 GIN 索引/运算符, JSON 足够。
  后续若上 pgvector 语义搜索再统一升级为 JSONB。

metadata 列名: 与设计文档列名一致为 `metadata`; Python 属性用 meta_info
(SQLAlchemy 声明类保留 `metadata`, 不可作属性名)。

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的环境 (测试库)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "202608081200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """建 agent_memory + agent_conversation 两表及索引。"""
    bind = op.get_bind()

    if not _has_table(bind, "agent_memory"):
        op.create_table(
            "agent_memory",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("board", sa.String(length=20), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("source", sa.String(length=100), nullable=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("importance", sa.Float(), nullable=True),
            sa.Column("related_type", sa.String(length=50), nullable=True),
            sa.Column("related_id", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_memory_id", "agent_memory", ["id"])
        op.create_index("ix_agent_memory_team_id", "agent_memory", ["team_id"])
        op.create_index(
            "idx_memory_team_board",
            "agent_memory",
            ["team_id", "board", sa.text("created_at DESC")],
        )
        op.create_index("idx_memory_team_status", "agent_memory", ["team_id", "status"])

    if not _has_table(bind, "agent_conversation"):
        op.create_table(
            "agent_conversation",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("board", sa.String(length=20), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("tool_calls", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_conversation_id", "agent_conversation", ["id"])
        op.create_index("ix_agent_conversation_team_id", "agent_conversation", ["team_id"])
        op.create_index(
            "idx_convo_team_board",
            "agent_conversation",
            ["team_id", "board", sa.text("created_at DESC")],
        )


def downgrade() -> None:
    """删 agent_conversation + agent_memory 两表。"""
    bind = op.get_bind()

    if _has_table(bind, "agent_conversation"):
        op.drop_index("idx_convo_team_board", table_name="agent_conversation")
        op.drop_index("ix_agent_conversation_team_id", table_name="agent_conversation")
        op.drop_index("ix_agent_conversation_id", table_name="agent_conversation")
        op.drop_table("agent_conversation")

    if _has_table(bind, "agent_memory"):
        op.drop_index("idx_memory_team_status", table_name="agent_memory")
        op.drop_index("idx_memory_team_board", table_name="agent_memory")
        op.drop_index("ix_agent_memory_team_id", table_name="agent_memory")
        op.drop_index("ix_agent_memory_id", table_name="agent_memory")
        op.drop_table("agent_memory")
