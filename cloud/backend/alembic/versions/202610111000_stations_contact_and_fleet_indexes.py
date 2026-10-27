"""stations 联系人/光伏储能列 + fleet_recharge_requests ix 索引 (卡 2520e93d)

Revision ID: 202610111000
Revises: 202610082100
Create Date: 2026-10-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202610111000"
down_revision: Union[str, Sequence[str], None] = "202610082100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATION_COLUMNS = (
    sa.Column("contact_person", sa.String(50), nullable=True, comment="联系人"),
    sa.Column("contact_phone", sa.String(30), nullable=True, comment="联系电话"),
    sa.Column("description", sa.Text(), nullable=True, comment="描述"),
    sa.Column("pv_capacity", sa.Float(), nullable=True, comment="光伏装机量(kWp)"),
    sa.Column("ess_capacity", sa.Float(), nullable=True, comment="储能装机量(kWh)"),
)

_FLEET_INDEXES = (
    ("ix_fleet_recharge_requests_enterprise_id", ("enterprise_id",)),
    ("ix_fleet_recharge_requests_status", ("status",)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # 反射点须 has_table 守卫 (对齐 03513c1f1): 单表隔离验证库走链不炸
    if inspector.has_table("stations"):
        existing_cols = {c["name"] for c in inspector.get_columns("stations")}
        for column in _STATION_COLUMNS:
            if column.name in existing_cols:
                continue
            op.add_column("stations", column)
    if inspector.has_table("fleet_recharge_requests"):
        existing_idx = {
            ix["name"] for ix in inspector.get_indexes("fleet_recharge_requests")
        }
        for name, cols in _FLEET_INDEXES:
            if name in existing_idx:
                continue
            op.create_index(name, "fleet_recharge_requests", list(cols))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("fleet_recharge_requests"):
        existing_idx = {
            ix["name"] for ix in inspector.get_indexes("fleet_recharge_requests")
        }
        for name, _cols in reversed(_FLEET_INDEXES):
            if name in existing_idx:
                op.drop_index(name, table_name="fleet_recharge_requests")
    if inspector.has_table("stations"):
        existing_cols = {c["name"] for c in inspector.get_columns("stations")}
        for column in reversed(_STATION_COLUMNS):
            if column.name in existing_cols:
                op.drop_column("stations", column.name)
