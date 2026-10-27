"""add security_policies table + seed

Revision ID: 202607310200
Revises: 202607310100
Create Date: 2026-07-31 02:00:00.000000

admin-platform-spec §2.7 安全管理: 新增 security_policies 表存放各类安全策略
(password/login/session/ip) 的 JSON 配置, 并插入默认策略种子数据 [D8-spec-gap]。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '202607310200'
down_revision = '202607310100'
branch_labels = None
depends_on = None


# 默认安全策略种子 (与 app.models.security_policy.default_security_policies 对齐;
# 此处硬编码以保持迁移历史自包含, 不依赖可能变化的 model 代码)
_SEED_POLICIES = [
    {
        "policy_key": "password",
        "policy_config": {"min_length": 8, "require_upper": True, "require_digit": True, "expire_days": 90},
        "description": "密码强度与过期策略",
        "status": "active",
    },
    {
        "policy_key": "login",
        "policy_config": {"fail_lock_count": 5, "lock_duration_minutes": 30},
        "description": "登录失败锁定策略",
        "status": "active",
    },
    {
        "policy_key": "session",
        "policy_config": {"session_timeout_minutes": 480, "concurrent_session_limit": 3},
        "description": "会话超时与并发限制策略",
        "status": "active",
    },
    {
        "policy_key": "ip",
        "policy_config": {"whitelist": [], "blacklist": [], "enable_ip_restrict": False},
        "description": "IP 访问控制策略",
        "status": "active",
    },
]


def upgrade() -> None:
    # 幂等守卫(与 0c60e5c087e0 一致): baseline 用 metadata.create_all 建表的
    # 全新库已含此表 → 跳过建表; 生产库表不存在 → create。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('security_policies'):
        op.create_table(
            'security_policies',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('policy_key', sa.String(length=50), nullable=False),
            sa.Column('policy_config', sa.JSON(), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            op.f('ix_security_policies_policy_key'),
            'security_policies',
            ['policy_key'],
            unique=True,
        )

    # 插入默认策略种子数据 (policy_config 绑定为 JSON, 由 SQLAlchemy 按方言序列化)。
    # baseline 建的表无种子 → 表空时仍需插入。
    security_policies = sa.table(
        'security_policies',
        sa.Column('policy_key', sa.String),
        sa.Column('policy_config', sa.JSON),
        sa.Column('description', sa.String),
        sa.Column('status', sa.String),
    )
    existing_keys = {
        row[0] for row in bind.execute(sa.select(security_policies.c.policy_key))
    }
    missing = [p for p in _SEED_POLICIES if p['policy_key'] not in existing_keys]
    if missing:
        op.bulk_insert(security_policies, missing)


def downgrade() -> None:
    op.drop_index(op.f('ix_security_policies_policy_key'), table_name='security_policies')
    op.drop_table('security_policies')
