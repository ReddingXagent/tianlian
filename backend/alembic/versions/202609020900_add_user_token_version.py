"""users.token_version 会话固定防护 (卡 5d6a978b)

Revision ID: 202609020900
Revises: 202608301300
Create Date: 2026-09-02 09:00:00.000000

密码重置时递增 users.token_version, JWT 签发内嵌 tv claim, 每请求鉴权
比对不一致即 401 → 改密后旧 token 立即驱逐 (原 ACCESS_TOKEN 24h 存活缺口)。

- nullable=False + server_default='0': 存量行迁移后即 0, 存量 token 无 tv
  claim 视为 0, 向后兼容零影响。
- inspector 判存幂等; PG/SQLite 双兼容 (纯加列, 无方言差异)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202609020900"
down_revision: Union[str, Sequence[str], None] = "202608301300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "users"
COLUMN = "token_version"


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLE):
        return

    if not _has_column(inspector, TABLE, COLUMN):
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(TABLE) and _has_column(inspector, TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
