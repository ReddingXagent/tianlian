"""users 登录失败锁定字段 (D8 爆破防护, spec admin§2.1)

Revision ID: 202607310400
Revises: 202607310300
Create Date: 2026-07-31 04:00:00.000000

新增三列支撑登录失败锁定机制:
- login_fail_count: 连续密码错误计数, 达 5 触发锁定 (NOT NULL, 默认 0)
- last_login_ip:    最近一次成功登录 IP (IPv6 最长 45 字符)
- locked_until:     锁定截止时间 (naive UTC, 与 datetime.utcnow() 对齐);
                    now >= locked_until 即自动解锁

NOT NULL 列在 PG 上对已有行加列需 server_default, 故 login_fail_count
带 server_default='0'; batch_alter_table 在 PG 退化为原生 ALTER, SQLite
走表重建, 两 dialect 均安全。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202607310400"
down_revision: Union[str, Sequence[str], None] = "202607310300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users 加 login_fail_count / last_login_ip / locked_until 三列。"""
    # 幂等守卫(与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    # 全新库已含此列 → 跳过; 生产库列不存在 → add。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    existing_cols = {c['name'] for c in inspector.get_columns("users")}
    with op.batch_alter_table("users", schema=None) as batch_op:
        if "login_fail_count" not in existing_cols:
            batch_op.add_column(
                sa.Column(
                    "login_fail_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "last_login_ip" not in existing_cols:
            batch_op.add_column(
                sa.Column("last_login_ip", sa.String(length=45), nullable=True)
            )
        if "locked_until" not in existing_cols:
            batch_op.add_column(
                sa.Column("locked_until", sa.DateTime(), nullable=True)
            )


def downgrade() -> None:
    """回滚: 移除登录失败锁定三列。"""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("locked_until")
        batch_op.drop_column("last_login_ip")
        batch_op.drop_column("login_fail_count")
