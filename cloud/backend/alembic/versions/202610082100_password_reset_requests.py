"""password_reset_requests 忘记密码申请表 (卡 922b2fba)

Revision ID: 202610082100
Revises: 202610080900
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202610082100"
down_revision: Union[str, Sequence[str], None] = "202610080900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "password_reset_requests"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_password_reset_requests_id"), _TABLE, ["id"])
    op.create_index(op.f("ix_password_reset_requests_account"), _TABLE, ["account"])


def downgrade() -> None:
    op.drop_index(op.f("ix_password_reset_requests_account"), table_name=_TABLE)
    op.drop_index(op.f("ix_password_reset_requests_id"), table_name=_TABLE)
    op.drop_table(_TABLE)
