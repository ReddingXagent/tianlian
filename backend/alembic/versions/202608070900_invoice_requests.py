"""invoice_requests: 手动开票申请表 (工作卡 a09f8a21)

Revision ID: 202608070900
Revises: 202608070800
Create Date: 2026-08-07 09:00:00.000000

用户端云端契约 §5 手动开票流程:
- C 端用户对已支付订单提交开票申请 (PENDING)
- 运营上传发票文件 → ISSUED (触发通知), 或拒绝 → REJECTED (用户可重申)

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的测试环境
(与 c8f7be6f / cf614348 / c7523ad8 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608070900"
down_revision: Union[str, Sequence[str], None] = "202608070800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 枚举字面值 (与 app.models.invoice_request 一致)
_STATUS_VALUES = ("pending", "issued", "rejected")
_MODE_VALUES = ("manual", "auto")
_TITLE_TYPE_VALUES = ("personal", "company")
_FILE_TYPE_VALUES = ("pdf", "ofd", "image")


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "invoice_requests"):
        op.create_table(
            "invoice_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("order_ids", sa.Text(), nullable=False, comment="关联订单号列表(JSON 数组)"),
            sa.Column("user_id", sa.Integer(), nullable=True, comment="申请人用户ID"),
            sa.Column("team_id", sa.Integer(), nullable=True, comment="归属团队(订单站点team)"),
            sa.Column(
                "title_type",
                sa.Enum(*_TITLE_TYPE_VALUES, name="invoicetitletype"),
                nullable=False,
                server_default="personal",
            ),
            sa.Column("title_name", sa.String(length=200), nullable=False),
            sa.Column("tax_number", sa.String(length=50), nullable=True),
            sa.Column("email", sa.String(length=120), nullable=True),
            sa.Column("remark", sa.String(length=500), nullable=True),
            sa.Column("amount", sa.Integer(), nullable=False, server_default="0", comment="开票金额(分)"),
            sa.Column(
                "invoice_mode",
                sa.Enum(*_MODE_VALUES, name="invoicemode"),
                nullable=False,
                server_default="manual",
            ),
            sa.Column(
                "status",
                sa.Enum(*_STATUS_VALUES, name="invoicerequeststatus"),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("invoice_file_path", sa.String(length=500), nullable=True),
            sa.Column("invoice_file_name", sa.String(length=255), nullable=True),
            sa.Column(
                "invoice_file_type",
                sa.Enum(*_FILE_TYPE_VALUES, name="invoicefiletype"),
                nullable=True,
            ),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reject_reason", sa.String(length=500), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_invoice_requests_id", "invoice_requests", ["id"])
        op.create_index("ix_invoice_requests_user", "invoice_requests", ["user_id"])
        op.create_index("ix_invoice_requests_team", "invoice_requests", ["team_id"])
        op.create_index("ix_invoice_requests_status", "invoice_requests", ["status"])
        op.create_index("ix_invoice_requests_applied", "invoice_requests", ["applied_at"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if _has_table(bind, "invoice_requests"):
        for idx in (
            "ix_invoice_requests_applied",
            "ix_invoice_requests_status",
            "ix_invoice_requests_team",
            "ix_invoice_requests_user",
            "ix_invoice_requests_id",
        ):
            try:
                op.drop_index(idx, table_name="invoice_requests")
            except Exception:
                pass
        op.drop_table("invoice_requests")
        # SQLite 不持久化 enum type; PG 下清理 (忽略失败以兼容 SQLite)
        for t in ("invoicefiletype", "invoicerequeststatus", "invoicemode", "invoicetitletype"):
            bind.execute(sa.text(f"DROP TYPE IF EXISTS {t}"))
