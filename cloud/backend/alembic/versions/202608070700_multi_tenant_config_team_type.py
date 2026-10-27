"""multi_tenant_config: Team 三层组织 + 配置表 team_id 隔离 (工作卡 cf614348)

Revision ID: 202608070700
Revises: 202608070600
Create Date: 2026-08-07 07:00:00.000000

配置多租户化 — 组织层级: 平台 → 运营公司(ops_company) → 运维团队/车队。
- teams 加 type(parent+owner_subject_id): type 默认 ops_company (存量回填);
- system_configs / notification_configs 加 team_id (NULL=平台级/弱归属);
- 幂等: 用 inspector 判列/索引存在再改, 兼容已 create_all 的环境 (与 c7523ad8 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608070700"
down_revision: Union[str, Sequence[str], None] = "202608070600"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# TeamType 字面值 (与 app.models.user.TeamType 一致)
_TEAM_TYPE_VALUES = ("ops_company", "maintenance_team", "fleet")


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _columns(bind, table: str) -> list:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return []
    return [c["name"] for c in inspector.get_columns(table)]


def _index_names(bind, table: str) -> list:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return []
    return [ix["name"] for ix in inspector.get_indexes(table)]


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # ── teams: type / parent_team_id / owner_subject_id ──
    if _has_table(bind, "teams"):
        cols = _columns(bind, "teams")
        if "type" not in cols:
            # 卡 15a07d0f: op.add_column 不触发 Enum 的 create_type 钩子 (仅
            # create_table/metadata 路径生效), PG 上须先建 enum type 再加列,
            # 否则 ALTER TABLE teams ADD COLUMN type teamtype → UndefinedObject。
            # checkfirst 兼容手工/历史已建 type 的库, 与本迁移判存幂等哲学一致。
            if bind.dialect.name == "postgresql":
                sa.Enum(*_TEAM_TYPE_VALUES, name="teamtype").create(bind, checkfirst=True)
            # server_default='ops_company' 同时回填存量行 (NOT NULL 列加 server_default
            # 在 PG/SQLite 均就地填值), 与「存量默认 ops_company」契约一致。
            op.add_column(
                "teams",
                sa.Column(
                    "type",
                    sa.Enum(*_TEAM_TYPE_VALUES, name="teamtype"),
                    nullable=False,
                    server_default="ops_company",
                ),
            )
        else:
            # 列已存在但仍可能为 NULL (早期建表无 server_default) → 兜底回填
            bind.execute(sa.text("UPDATE teams SET type = 'ops_company' WHERE type IS NULL"))

        if "parent_team_id" not in cols:
            op.add_column(
                "teams",
                sa.Column("parent_team_id", sa.Integer(), nullable=True),
            )
        if "owner_subject_id" not in cols:
            op.add_column(
                "teams",
                sa.Column("owner_subject_id", sa.Integer(), nullable=True),
            )

        idxs = _index_names(bind, "teams")
        if "ix_teams_type" not in idxs:
            op.create_index("ix_teams_type", "teams", ["type"])
        if "ix_teams_parent_team_id" not in idxs:
            op.create_index("ix_teams_parent_team_id", "teams", ["parent_team_id"])
        if "ix_teams_owner_subject_id" not in idxs:
            op.create_index("ix_teams_owner_subject_id", "teams", ["owner_subject_id"])

    # ── system_configs: team_id ──
    if _has_table(bind, "system_configs"):
        if "team_id" not in _columns(bind, "system_configs"):
            op.add_column(
                "system_configs",
                sa.Column("team_id", sa.Integer(), nullable=True),
            )
        if "ix_system_configs_team_id" not in _index_names(bind, "system_configs"):
            op.create_index("ix_system_configs_team_id", "system_configs", ["team_id"])

    # ── notification_configs: team_id ──
    if _has_table(bind, "notification_configs"):
        if "team_id" not in _columns(bind, "notification_configs"):
            op.add_column(
                "notification_configs",
                sa.Column("team_id", sa.Integer(), nullable=True),
            )
        if "ix_notification_configs_team_id" not in _index_names(bind, "notification_configs"):
            op.create_index("ix_notification_configs_team_id", "notification_configs", ["team_id"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    for table, col, idx in [
        ("notification_configs", "team_id", "ix_notification_configs_team_id"),
        ("system_configs", "team_id", "ix_system_configs_team_id"),
    ]:
        if _has_table(bind, table):
            if idx in _index_names(bind, table):
                op.drop_index(idx, table_name=table)
            if col in _columns(bind, table):
                op.drop_column(table, col)

    if _has_table(bind, "teams"):
        idxs = _index_names(bind, "teams")
        for idx in ("ix_teams_owner_subject_id", "ix_teams_parent_team_id", "ix_teams_type"):
            if idx in idxs:
                op.drop_index(idx, table_name="teams")
        cols = _columns(bind, "teams")
        for col in ("owner_subject_id", "parent_team_id", "type"):
            if col in cols:
                op.drop_column("teams", col)
