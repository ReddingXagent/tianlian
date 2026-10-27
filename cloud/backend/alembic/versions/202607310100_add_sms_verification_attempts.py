"""add attempts column to sms_verification_codes

Revision ID: 202607310100
Revises: 765db93fa1b2
Create Date: 2026-07-31 01:00:00.000000

短信验证码防爆破: 新增 attempts 列记录错误尝试次数 (≥5 则失效)。

⚠️ 2026-07-31 06:55 大圣修正: 原迁移被误放在孤儿目录 app/migrations/versions/
(alembic.ini script_location=alembic, deploy.sh `alembic upgrade head` 永不读取),
且 down_revision 误接旧孤儿链 202606230300。本文件放入正确目录 alembic/versions/
并将 down_revision 接到真实 head 765db93fa1b2, 确保生产 upgrade head 能 apply。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202607310100'
down_revision = '765db93fa1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等守卫(与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    # 全新库已含此列 → 跳过; 生产库列不存在 → add。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('sms_verification_codes'):
        return
    existing_cols = {c['name'] for c in inspector.get_columns('sms_verification_codes')}
    if 'attempts' not in existing_cols:
        op.add_column(
            'sms_verification_codes',
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        )


def downgrade() -> None:
    op.drop_column('sms_verification_codes', 'attempts')
