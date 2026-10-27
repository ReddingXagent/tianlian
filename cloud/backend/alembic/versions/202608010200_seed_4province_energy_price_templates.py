"""4 省购电价模板种子数据 — P1-4 任务A (卡片 P1-4)

Revision ID: 202608010200
Revises: 202608010100
Create Date: 2026-08-01 02:00:00.000000

数据迁移 (非 schema): 插入川/浙/粤/甘 4 省平台级购电价模板 + 时段明细。
权威数据源: app/seed/energy_price_seed.py (与 tests/test_energy_strategy_api.py 同源)。

⚠️ 时段/价差为预研示意值, 上线前须按最新电网文件校准 (SPEC §5 明示)。

幂等: 已存在同名平台级模板则跳过 (见 seed_energy_price_templates)。
downgrade: 仅删 team_id IS NULL 的 4 省 seed 模板 + 关联时段, 不影响团队级模板。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608010200"
down_revision: Union[str, Sequence[str], None] = "202608010100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade data: 4 省购电价模板 + 时段。"""
    bind = op.get_bind()
    # 防御: P1-1 (down_revision) 已建表; 缺表则跳过避免报错。
    if not (_has_table(bind, "energy_price_template")
            and _has_table(bind, "energy_price_period")):
        return

    from sqlalchemy.orm import Session
    from app.seed.energy_price_seed import seed_energy_price_templates

    session = Session(bind=bind)
    try:
        seed_energy_price_templates(session)
    finally:
        session.close()


def downgrade() -> None:
    """Downgrade data: 删除 4 省 seed 模板 + 时段。"""
    bind = op.get_bind()
    if not (_has_table(bind, "energy_price_template")
            and _has_table(bind, "energy_price_period")):
        return

    from sqlalchemy.orm import Session
    from app.seed.energy_price_seed import unseed_energy_price_templates

    session = Session(bind=bind)
    try:
        unseed_energy_price_templates(session)
    finally:
        session.close()
