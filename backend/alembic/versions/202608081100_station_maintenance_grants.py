"""station_maintenance_grants: 场站运维授权表 (任务卡 00d7d49a)

Revision ID: 202608081100
Revises: 202608081000
Create Date: 2026-08-08 11:00:00.000000

运维分离架构: 运营公司 (ops_company) 把某场站的运维工作授权给独立第三方运维团队
(maintenance_team)。表式建模授权关系 (station ↔ maintenance_team), 带 scope/status。

字段:
- station_id / maintenance_team_id / granted_by_team_id: 授权三方 (FK teams/stations)
- scope:    full / monitoring_only / maintenance_only
- status:   active / revoked / expired
- granted_at / revoked_at / expires_at / remark: 时间线 + 备注

索引: (station_id, maintenance_team_id) 唯一 + station_id / maintenance_team_id /
      granted_by_team_id / status 单列。

幂等建表: inspector 判表存在再建, 兼容已 create_all 的测试环境
(与 edge_gateway / parking_integration 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608081100"
down_revision: Union[str, Sequence[str], None] = "202608081000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCOPE_VALUES = ("full", "monitoring_only", "maintenance_only")
_STATUS_VALUES = ("active", "revoked", "expired")


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, "station_maintenance_grants"):
        return

    op.create_table(
        "station_maintenance_grants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("maintenance_team_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_team_id", sa.Integer(), nullable=False),
        sa.Column(
            "scope",
            sa.Enum("full", "monitoring_only", "maintenance_only", name="grantscope"),
            nullable=False,
            server_default="full",
        ),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "expired", name="grantstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["maintenance_team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "scope IN ('full', 'monitoring_only', 'maintenance_only')",
            name="ck_smg_scope",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="ck_smg_status",
        ),
    )
    op.create_index(
        "ix_smg_station_maint_team", "station_maintenance_grants",
        ["station_id", "maintenance_team_id"], unique=True,
    )
    op.create_index(
        "ix_smg_granted_by", "station_maintenance_grants", ["granted_by_team_id"],
    )
    op.create_index(
        "ix_smg_status", "station_maintenance_grants", ["status"],
    )
    op.create_index(
        "ix_smg_maintenance_team_id", "station_maintenance_grants", ["maintenance_team_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, "station_maintenance_grants"):
        return
    op.drop_index("ix_smg_maintenance_team_id", table_name="station_maintenance_grants")
    op.drop_index("ix_smg_status", table_name="station_maintenance_grants")
    op.drop_index("ix_smg_granted_by", table_name="station_maintenance_grants")
    op.drop_index("ix_smg_station_maint_team", table_name="station_maintenance_grants")
    op.drop_table("station_maintenance_grants")
    # 枚举类型在 SQLite 无独立对象; PG 下 sa.Enum 会建独立 type, 这里尝试清理 (幂等)
    sa.Enum(name="grantscope").drop(bind, checkfirst=True)
    sa.Enum(name="grantstatus").drop(bind, checkfirst=True)
