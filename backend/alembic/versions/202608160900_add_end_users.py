"""C端用户与设备token表 (契约§8 P1, 卡 d95dafd3)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608160900"
down_revision: Union[str, Sequence[str], None] = "c4b8e2f9a1d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等守卫(与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    # 全新库已含此表 → 跳过建表; 生产库表不存在 → create。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("end_users"):
        return
    op.create_table(
        "end_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("wx_openid", sa.String(length=128), nullable=False),
        sa.Column("wx_unionid", sa.String(length=128), nullable=True),
        sa.Column("nickname", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column(
            "user_type",
            sa.Enum(
                "app",
                "card",
                "vin",
                "interconnect",
                "enterprise",
                name="endusertype",
            ),
            nullable=False,
            server_default="app",
        ),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="enduserstatus"),
            nullable=False,
            server_default="active",
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wx_openid"),
    )
    op.create_index(op.f("ix_end_users_wx_openid"), "end_users", ["wx_openid"], unique=True)
    op.create_index(op.f("ix_end_users_wx_unionid"), "end_users", ["wx_unionid"], unique=False)
    op.create_index(op.f("ix_end_users_phone"), "end_users", ["phone"], unique=False)

    op.create_table(
        "end_user_device_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("end_user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("device_token", sa.String(length=512), nullable=False),
        sa.Column("app_version", sa.String(length=50), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["end_user_id"], ["end_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("end_user_id", "platform", name="uq_end_user_device_platform"),
    )
    op.create_index(
        op.f("ix_end_user_device_tokens_end_user_id"),
        "end_user_device_tokens",
        ["end_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_end_user_device_tokens_end_user_id"),
        table_name="end_user_device_tokens",
    )
    op.drop_table("end_user_device_tokens")
    op.drop_index(op.f("ix_end_users_phone"), table_name="end_users")
    op.drop_index(op.f("ix_end_users_wx_unionid"), table_name="end_users")
    op.drop_index(op.f("ix_end_users_wx_openid"), table_name="end_users")
    op.drop_table("end_users")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS enduserstatus")
        op.execute("DROP TYPE IF EXISTS endusertype")
