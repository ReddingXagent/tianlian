"""notifications 站内消息中心收件箱 (admin-platform-spec §2.8)

Revision ID: 202607310500
Revises: 202607310400
Create Date: 2026-07-31 05:00:00.000000

新建 notifications 表 — 站内消息中心:
- 收件箱/已读未读状态, 按 team_id 做服务端隔离 (与 Station.team_id 同契约)。
- team_id 为隔离键 (User 无 tenant_id, 已注释禁用; 用户实际携带 team_id)。
- id 为 UUID(String36), 由应用层 default 生成 (与模型对齐)。

幂等: 用 inspector 判表存在再建, 兼容已 create_all 的环境 (与 g4b5c6d7e8f9 同模式)。
PG/SQLite 双 dialect: create_table 原生支持, FK 内联定义在 SQLite 亦安全。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202607310500"
down_revision: Union[str, Sequence[str], None] = "202607310400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema: 建 notifications 表。"""
    bind = op.get_bind()
    if _has_table(bind, "notifications"):
        return
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True, comment="所属团队(隔离键), NULL=平台广播"),
        sa.Column("title", sa.String(length=200), nullable=False, comment="消息标题"),
        sa.Column("content", sa.Text(), nullable=True, comment="消息内容"),
        sa.Column(
            "type", sa.String(length=20), nullable=False, server_default="system",
            comment="消息类型: alarm/order/work_order/system",
        ),
        sa.Column(
            "sender", sa.String(length=100), nullable=False, server_default="system",
            comment="发送者, 系统消息=system",
        ),
        sa.Column(
            "recipient_type", sa.String(length=20), nullable=False, server_default="user",
            comment="接收者类型: role/user",
        ),
        sa.Column(
            "recipient_id", sa.String(length=100), nullable=False,
            comment="接收者ID (用户ID字符串或角色名)",
        ),
        sa.Column(
            "channel", sa.String(length=20), nullable=False, server_default="app_push",
            comment="渠道, 站内默认 app_push",
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending",
            comment="发送状态: pending/sent/failed",
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True, comment="已读时间"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True, comment="发送时间"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_team_id", "notifications", ["team_id"])
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index(
        "ix_notifications_recipient", "notifications", ["recipient_type", "recipient_id"]
    )


def downgrade() -> None:
    """Downgrade schema: 删 notifications 表。"""
    bind = op.get_bind()
    if not _has_table(bind, "notifications"):
        return
    op.drop_index("ix_notifications_recipient", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_index("ix_notifications_team_id", table_name="notifications")
    op.drop_index("ix_notifications_id", table_name="notifications")
    op.drop_table("notifications")
