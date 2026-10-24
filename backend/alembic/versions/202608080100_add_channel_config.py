"""add_channel_config

Revision ID: 202608080100
Revises: 202608071000
Create Date: 2026-08-08 01:00:00.000000

通知渠道真实化 (卡 8d98ebe3): channel_configs 表存团队级真实发送渠道凭证
(im/wecom/webhook/sms/voice/email), 与 notification_configs (渠道开关) 正交。

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的环境 (测试库走 create_all,
生产库走 alembic upgrade)。SQLite 对 SQLEnum 存储字面值, 与模型 values_callable 一致。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608080100"
down_revision: Union[str, Sequence[str], None] = "202608071000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not _has_table(bind, "channel_configs"):
        op.create_table(
            "channel_configs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column(
                "team_id", sa.Integer(),
                nullable=True,
            ),
            sa.Column(
                "channel",
                sa.Enum("im", "wecom", "webhook", "sms", "voice", "email", name="channeltype"),
                nullable=False,
            ),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team_id", "channel", name="uq_channel_config_team_channel"),
        )
        op.create_index("ix_channel_configs_id", "channel_configs", ["id"])
        op.create_index("ix_channel_configs_team_id", "channel_configs", ["team_id"])
        op.create_index(
            "ix_channel_config_team_channel", "channel_configs", ["team_id", "channel"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if _has_table(bind, "channel_configs"):
        op.drop_index("ix_channel_config_team_channel", table_name="channel_configs")
        op.drop_index("ix_channel_configs_team_id", table_name="channel_configs")
        op.drop_index("ix_channel_configs_id", table_name="channel_configs")
        op.drop_table("channel_configs")
