"""rename order_fee_items enum to order_fee_type (PG 枚举撞名修复)

Revision ID: k8f9a0b1c2d3
Revises: j7e8f9a0b1c2
Create Date: 2026-07-25 22:00:00.000000

修复生产 PG 500 bug: order_fee_items 插入报
`invalid input value for enum feetype: "ELECTRICITY"`。

根因: app/models/order_fee_item.py 的 FeeType(8 成员) 与
app/models/pricing_v2.py 的 FeeType(FIXED/PERCENT) 都用 SAEnum(FeeType) 未指定
name -> SQLAlchemy 推断的 PG 命名 enum 类型都是 `feetype`。PG 同名类型只创建一次,
service_fee_prices 先建, feetype 仅含 FIXED/PERCENT; order_fee_items.fee_type 复用
该类型, 插入 ELECTRICITY/SERVICE/... 时校验失败。

模型层已将 order_fee_item 的列改为 SAEnum(FeeType, name="order_fee_type")
(SQLAlchemy 默认存枚举 NAME, 故 PG label 为大写: ELECTRICITY/SERVICE/PARKING/
OCCUPANCY/RESERVATION/DISCOUNT/COUPON/POINTS)。本迁移把持久库的列类型同步过去,
pricing_v2 的 feetype 不动。

- 仅 PostgreSQL 执行: CREATE TYPE order_fee_type + ALTER COLUMN ... USING。
- SQLite 无独立命名 enum 类型(SAEnum 退化为 VARCHAR+CHECK), 直接跳过。
- order_fee_items 生产 0 行, 无需数据值映射; ALTER 仅做类型重写。
- 幂等: CREATE TYPE 前查 pg_type; ALTER COLUMN 到同类型 PG 接受, 无副作用。
- 可降级: 退化为 VARCHAR(64)(order_fee_type 的 8 label 无法装回 feetype 的
  FIXED/PERCENT, 故不回退到 feetype 以免丢数据), 并 DROP TYPE order_fee_type。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k8f9a0b1c2d3"
down_revision: Union[str, None] = "j7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "order_fee_items"
_COLUMN = "fee_type"
_NEW_ENUM = "order_fee_type"

# 与 SAEnum(FeeType) 默认存储的枚举 NAME 一致(大写), 见 order_fee_item.FeeType
_LABELS = (
    "ELECTRICITY", "SERVICE", "PARKING", "OCCUPANCY",
    "RESERVATION", "DISCOUNT", "COUPON", "POINTS",
)


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _enum_type_exists(bind, name: str) -> bool:
    """PG: 判断命名 enum 类型是否已存在(查 pg_type)"""
    return bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :n"),
        {"n": name},
    ).scalar() is not None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _is_postgresql(bind):
        # SQLite: 无命名 enum, SAEnum 退化为 VARCHAR + CHECK, 无需迁移
        return
    if not _has_table(bind, _TABLE):
        # 表尚未存在(create_all 会按最新模型建, 已用 order_fee_type)
        return

    if not _enum_type_exists(bind, _NEW_ENUM):
        labels_sql = ", ".join(f"'{lbl}'" for lbl in _LABELS)
        op.execute(f"CREATE TYPE {_NEW_ENUM} AS ENUM ({labels_sql})")

    # 列类型从 feetype 转为 order_fee_type; 生产 0 行, USING 仅做类型重写
    # (PG 允许 ALTER COLUMN TYPE 到相同类型, 故对已迁移的环境幂等无副作用)
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COLUMN} "
        f"TYPE {_NEW_ENUM} USING {_COLUMN}::text::{_NEW_ENUM}"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _is_postgresql(bind):
        return
    if not _has_table(bind, _TABLE):
        return

    # order_fee_type 的 8 个 label 无法装回 feetype(仅 FIXED/PERCENT),
    # 退化为 VARCHAR(64) 保数据; 代码若同时回滚, 模型恢复 SAEnum(FeeType) 无 name,
    # 再次建表/迁移时会重建对应 enum 类型。
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COLUMN} "
        f"TYPE VARCHAR(64) USING {_COLUMN}::text"
    )
    if _enum_type_exists(bind, _NEW_ENUM):
        op.execute(f"DROP TYPE {_NEW_ENUM}")
