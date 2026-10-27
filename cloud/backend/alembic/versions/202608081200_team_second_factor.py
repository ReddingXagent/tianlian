"""team_second_factor: 团队级二次验证(2FA)开关 (任务卡 78c7404b)

Revision ID: 202608081200
Revises: 202608081100
Create Date: 2026-08-08 12:00:00.000000

为 teams 表新增两列, 支持两步登录(密码 + 短信验证码):
- second_factor_enabled: Boolean, 默认 False (server_default='0'), 存量团队不受影响
- second_factor_method:  String(20), 默认 'sms', 预留扩展位

幂等加列: inspector 判列存在再加, 兼容已 create_all 的测试环境(测试不走 alembic,
create_all 已含新列; 生产 upgrade 时才执行, 重复 upgrade 安全)。与 edge_gateway /
parking_integration 同模式。

设计: 2FA 是团队级开关而非用户级 —— 企业 admin 在团队配置中开启后, 该团队所有成员
密码登录都需额外短信验证码。向后兼容: 默认关闭, login 端点对关闭的团队直接返回 token,
现有登录路径零回归。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608081200"
down_revision: Union[str, Sequence[str], None] = "202608081100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("teams"):
        # 表缺失(单表隔离库) -> 优雅跳过
        return
    if not _has_column(bind, "teams", "second_factor_enabled"):
        op.add_column(
            "teams",
            sa.Column(
                "second_factor_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
        )
    if not _has_column(bind, "teams", "second_factor_method"):
        op.add_column(
            "teams",
            sa.Column(
                "second_factor_method",
                sa.String(length=20),
                nullable=False,
                server_default="sms",
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("teams"):
        # 表缺失 -> 无列可删, 优雅跳过
        return
    if _has_column(bind, "teams", "second_factor_method"):
        op.drop_column("teams", "second_factor_method")
    if _has_column(bind, "teams", "second_factor_enabled"):
        op.drop_column("teams", "second_factor_enabled")
