"""add_enterprise_extended_fields

Revision ID: a1b2c3d4e5f6
Revises: f0e1d2c3b4a5
Create Date: 2026-07-23 22:30:00.000000

Enterprise 表新增字段:
- default_vehicle_config (JSON): 默认车辆配置
- address (VARCHAR 500): 企业地址
- description (TEXT): 企业描述
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f0e1d2c3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("enterprises"):
        existing_cols = {c['name'] for c in inspector.get_columns("enterprises")}
        if "default_vehicle_config" not in existing_cols:
            op.add_column("enterprises", sa.Column("default_vehicle_config", sa.JSON(), nullable=True, comment="默认车辆配置(JSON)"))
        if "address" not in existing_cols:
            op.add_column("enterprises", sa.Column("address", sa.String(500), nullable=True, comment="企业地址"))
        if "description" not in existing_cols:
            op.add_column("enterprises", sa.Column("description", sa.Text(), nullable=True, comment="企业描述"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("enterprises"):
        existing_cols = {c['name'] for c in inspector.get_columns("enterprises")}
        if "description" in existing_cols:
            op.drop_column("enterprises", "description")
        if "address" in existing_cols:
            op.drop_column("enterprises", "address")
        if "default_vehicle_config" in existing_cols:
            op.drop_column("enterprises", "default_vehicle_config")
