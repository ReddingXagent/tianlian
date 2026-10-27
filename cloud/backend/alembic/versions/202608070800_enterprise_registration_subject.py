"""enterprise_registration: 企业注册申请单 + 主体 (工作卡 c8f7be6f)

Revision ID: 202608070800
Revises: 202608070700
Create Date: 2026-08-07 08:00:00.000000

企业注册审批:
- subjects: 企业主体表 (Team.owner_subject_id 的逻辑指向, 同主体多角色);
- registration_applications: 企业注册申请单 (pending → approved/rejected)。

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的测试环境 (与 cf614348 / c7523ad8 同模式)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608070800"
down_revision: Union[str, Sequence[str], None] = "202608070700"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 枚举字面值 (与 app.models.registration 一致)
_APPLY_SCOPE_VALUES = ("ops", "maintenance", "both")
_REG_STATUS_VALUES = ("pending", "approved", "rejected")


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # ── subjects: 企业主体 ──
    if not _has_table(bind, "subjects"):
        op.create_table(
            "subjects",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("company_name", sa.String(length=200), nullable=False),
            sa.Column("credit_code", sa.String(length=18), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_subjects_id", "subjects", ["id"])
        op.create_index("ix_subjects_company_name", "subjects", ["company_name"])
        op.create_index("ix_subjects_credit_code", "subjects", ["credit_code"])

    # ── registration_applications: 企业注册申请单 ──
    if not _has_table(bind, "registration_applications"):
        op.create_table(
            "registration_applications",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("company_name", sa.String(length=200), nullable=False),
            sa.Column("credit_code", sa.String(length=18), nullable=False),
            sa.Column("license_file_path", sa.String(length=500), nullable=True),
            sa.Column("legal_person", sa.String(length=100), nullable=True),
            sa.Column("contact_name", sa.String(length=100), nullable=False),
            sa.Column("contact_phone", sa.String(length=20), nullable=False),
            sa.Column("contact_email", sa.String(length=120), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "apply_scope",
                sa.Enum(*_APPLY_SCOPE_VALUES, name="applyscope"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.Enum(*_REG_STATUS_VALUES, name="registrationstatus"),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("agreed_to_terms", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("agreement_version", sa.String(length=50), nullable=True),
            sa.Column("reviewer_id", sa.Integer(), nullable=True),
            sa.Column("review_remark", sa.Text(), nullable=True),
            sa.Column("subject_id", sa.Integer(), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_registration_applications_id", "registration_applications", ["id"])
        op.create_index("ix_registration_applications_credit_code", "registration_applications", ["credit_code"])
        op.create_index("ix_registration_applications_contact_phone", "registration_applications", ["contact_phone"])
        op.create_index("ix_registration_applications_status", "registration_applications", ["status"])
        op.create_index("ix_registration_applications_subject_id", "registration_applications", ["subject_id"])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if _has_table(bind, "registration_applications"):
        for idx in (
            "ix_registration_applications_subject_id",
            "ix_registration_applications_status",
            "ix_registration_applications_contact_phone",
            "ix_registration_applications_credit_code",
            "ix_registration_applications_id",
        ):
            try:
                op.drop_index(idx, table_name="registration_applications")
            except Exception:
                pass
        op.drop_table("registration_applications")
        # SQLite 不持久化 enum type; PG 下清理 (忽略失败以兼容 SQLite)
        bind.execute(sa.text("DROP TYPE IF EXISTS registrationstatus"))
        bind.execute(sa.text("DROP TYPE IF EXISTS applyscope"))

    if _has_table(bind, "subjects"):
        for idx in (
            "ix_subjects_credit_code",
            "ix_subjects_company_name",
            "ix_subjects_id",
        ):
            try:
                op.drop_index(idx, table_name="subjects")
            except Exception:
                pass
        op.drop_table("subjects")
