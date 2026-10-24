"""C端车辆与收藏场站表 (契约§8 P2, 卡 36396f29)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608161400"
down_revision: Union[str, Sequence[str], None] = "202608160900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等守卫(与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    # 全新库已含此表 → 跳过建表; 生产库表不存在 → create。
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("end_user_vehicles"):
        return
    # C端车辆: (end_user_id, plate_number) 复合唯一 — 同用户不重复, 跨用户允许
    op.create_table(
        "end_user_vehicles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("end_user_id", sa.Integer(), nullable=False),
        sa.Column("plate_number", sa.String(length=20), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=True),
        sa.Column("brand", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["end_user_id"], ["end_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("end_user_id", "plate_number", name="uq_end_user_vehicle_plate"),
    )
    op.create_index(
        op.f("ix_end_user_vehicles_end_user_id"),
        "end_user_vehicles",
        ["end_user_id"],
        unique=False,
    )

    # C端收藏: (end_user_id, station_id) 复合唯一 — 一人一站一条
    op.create_table(
        "end_user_favorites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("end_user_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["end_user_id"], ["end_users.id"]),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("end_user_id", "station_id", name="uq_end_user_favorite_station"),
    )
    op.create_index(
        op.f("ix_end_user_favorites_end_user_id"),
        "end_user_favorites",
        ["end_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_end_user_favorites_station_id"),
        "end_user_favorites",
        ["station_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_end_user_favorites_station_id"), table_name="end_user_favorites")
    op.drop_index(op.f("ix_end_user_favorites_end_user_id"), table_name="end_user_favorites")
    op.drop_table("end_user_favorites")
    op.drop_index(op.f("ix_end_user_vehicles_end_user_id"), table_name="end_user_vehicles")
    op.drop_table("end_user_vehicles")
