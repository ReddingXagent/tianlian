"""add tenant_brand (工作卡 28546b66 — 云端配套① 租户品牌服务)

Revision ID: 202608070100
Revises: 202608010200
Create Date: 2026-08-07 01:00:00.000000

租户动态品牌 (契约 backend/docs/contracts/user-client-contract.md §1):
- tenant_brands: 每租户一条品牌 (tenant_id 唯一)，供场站响应 branding 解析。
  列: tenant_id(unique FK→tenants) / team_id(FK→teams, ops team scoping) /
      operator_name / logo_url / service_phone / theme_color + 时间戳。

幂等: 用 inspector 判表存在再建，兼容已 create_all 的环境 (与 h5c6d7e8f9a0 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608070100"
down_revision: Union[str, Sequence[str], None] = "202608010200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, "tenant_brands"):
        op.create_table(
            "tenant_brands",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=True),
            sa.Column("operator_name", sa.String(length=100), nullable=False),
            sa.Column("logo_url", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("service_phone", sa.String(length=50), nullable=False, server_default=""),
            sa.Column(
                "theme_color", sa.String(length=20), nullable=False, server_default="#00A86B",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tenant_brands_id", "tenant_brands", ["id"])
        op.create_index(
            "ix_tenant_brands_tenant_id", "tenant_brands", ["tenant_id"], unique=True,
        )
        op.create_index("idx_tenant_brand_team", "tenant_brands", ["team_id"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, "tenant_brands"):
        op.drop_index("idx_tenant_brand_team", table_name="tenant_brands")
        op.drop_index("ix_tenant_brands_tenant_id", table_name="tenant_brands")
        op.drop_index("ix_tenant_brands_id", table_name="tenant_brands")
        op.drop_table("tenant_brands")
