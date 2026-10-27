"""add fleet_recharge_requests table (卡 4144ef1b)

Revision ID: 202609272130
Revises: 202609020900
Create Date: 2026-09-27 21:30:00.000000

车队充值申请表 — 凭证上传 → 运营商审核 → 余额入账
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202609272130"
down_revision: Union[str, None] = "202609020900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fleet_recharge_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enterprise_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, comment="充值金额(元)"),
        sa.Column("voucher_url", sa.String(500), nullable=False, comment="凭证文件路径"),
        # 卡 15a07d0f: 独立 type 名 —— baseline 已为 enterprise_recharge_
        # applications 建 rechargestatus('PENDING','APPROVED','REJECTED')
        # (NAME 大写), 本表值集是小写 value, 同名异值集在 PG 上 ADD
        # COLUMN ... DEFAULT 'pending' 会 InvalidTextRepresentation。
        sa.Column("status", sa.Enum("pending", "approved", "rejected", name="fleetrechargestatus"), nullable=False, server_default="pending"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fleet_recharge_status", "fleet_recharge_requests", ["status"])
    op.create_index("idx_fleet_recharge_enterprise", "fleet_recharge_requests", ["enterprise_id"])


def downgrade() -> None:
    op.drop_index("idx_fleet_recharge_enterprise", table_name="fleet_recharge_requests")
    op.drop_index("idx_fleet_recharge_status", table_name="fleet_recharge_requests")
    op.drop_table("fleet_recharge_requests")
    # enum type 在 PG 下保留（alembic 不自动删 enum），SQLite 无 enum 无影响
