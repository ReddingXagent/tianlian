"""add missing production columns (team_id/approval/interconnect/supervision)

Revision ID: 0658b3b78147
Revises: 0c60e5c087e0
Create Date: 2026-07-28 02:30:00.000000

修复生产 PG schema_validator 每次启动报 14 条缺列 WARNING: 这些列在模型层
(app/models/admin_supervision.py, admin_interconnect.py, enterprise_vehicle.py)
已定义, 但持久库缺失。

根因: municipal_supervision_configs / regulatory_reports / compliance_checks /
interconnect_configs / interconnect_orders / enterprise_vehicles 六张表均由
Base.metadata.create_all() 在运行时建表, 不在 baseline migration 内; 模型后续
新增的列不会 ALTER 进已存在的持久库 (create_all 只建不补), 故开发 SQLite 与
生产 Postgres 的旧库仍缺这些列。

本迁移幂等地补齐 14 列 + interconnect_configs.idx_iconfig_team 索引, PG/SQLite
双方言均可跑。

team_id 类 NOT NULL default=0 列采用三步法 (生产友好, 避免 PG 大表
ADD COLUMN NOT NULL 触发全表重写/长锁):
  1) nullable 加列
  2) UPDATE 回填默认值
  3) PG: ALTER COLUMN SET DEFAULT + SET NOT NULL
     SQLite: 不支持 ALTER 改约束 -> 跳过约束步 (数据已回填, 新行靠 ORM default)

approval_status (SAEnum(ApprovalStatus), native_enum=True, NOT NULL default=PENDING):
  - PG: 幂等 CREATE TYPE approvalstatus; labels 取枚举 NAME (PENDING/CONFIRMED/
    REJECTED), 与 SQLAlchemy 默认存储一致; 用原生 SQL 加列, 避免 op.add_column
    重复 emit CREATE TYPE 撞名 (参考 k8f9a0b1c2d3 的 enum 治理)
  - SQLite: SAEnum 退化为 VARCHAR, 用 String(20) 加列 + 回填, 跳过约束步

可逆: downgrade 按反序 drop 索引 -> approval_status(列+type) -> nullable 列 ->
team_id 列, 全程判存。先 drop idx_iconfig_team 再 drop interconnect_configs.team_id
(SQLite DROP COLUMN 不允许列仍被索引引用)。
"""
from typing import Optional, Sequence, Set, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0658b3b78147"
down_revision: Union[str, Sequence[str], None] = "0c60e5c087e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---- team_id 类 NOT NULL Integer default=0 列 (table, column, comment) ----
_TEAM_ID_COLUMNS = (
    ("municipal_supervision_configs", "team_id", "运营团队ID (0=平台默认模板)"),
    ("regulatory_reports", "team_id", "运营团队ID (冗余)"),
    ("compliance_checks", "team_id", "运营团队ID (冗余)"),
    ("interconnect_configs", "team_id", "运营团队ID (0=平台默认模板)"),
    ("interconnect_orders", "team_id", "运营团队ID (冗余,便于按团队筛选)"),
)

# ---- nullable 列 (table, column, SA type, comment) ----
_NULLABLE_COLUMNS = (
    ("municipal_supervision_configs", "city_code", sa.String(20), "城市编码"),
    ("municipal_supervision_configs", "platform_name", sa.String(100),
     "平台名称(粤易充/联联/浙里充等)"),
    ("municipal_supervision_configs", "platform_type", sa.String(50),
     "平台类型 yueyichong/lianlian/zhelichong/generic/other"),
    ("municipal_supervision_configs", "protocol_type", sa.String(30),
     "协议类型 http_push/http_pull/mqtt/websocket"),
    ("interconnect_configs", "protocol_version", sa.String(20),
     "中电联协议版本 V1.0/V1.6/V2.0"),
    ("interconnect_configs", "sync_direction", sa.String(20),
     "同步方向 push/pull/bidirectional"),
    ("enterprise_vehicles", "confirmed_at", sa.DateTime(), "确认时间"),
    ("enterprise_vehicles", "confirmed_by", sa.String(100), "确认人"),
)

# enterprise_vehicles.approval_status: SAEnum(ApprovalStatus), native PG enum
_APPROVAL_TABLE = "enterprise_vehicles"
_APPROVAL_COLUMN = "approval_status"
_APPROVAL_ENUM_NAME = "approvalstatus"
_APPROVAL_LABELS = ("PENDING", "CONFIRMED", "REJECTED")  # 枚举 NAME, 与模型存储一致
_APPROVAL_DEFAULT = "PENDING"

# interconnect_configs 团队索引 (模型 __table_args__ 定义)
_ICONFIG_INDEX = ("idx_iconfig_team", "interconnect_configs", ["team_id"])


# ---------- helpers ----------

def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _enum_type_exists(bind, name: str) -> bool:
    """PG: 判断命名 enum 类型是否已存在 (查 pg_type)。非 PG 方言返回 False。"""
    if not _is_postgresql(bind):
        return False
    return bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :n"),
        {"n": name},
    ).scalar() is not None


def _existing_columns(bind, table: str) -> Optional[Set[str]]:
    """返回表已有列名集合; 表不存在返回 None。"""
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return None
    return {c["name"] for c in inspector.get_columns(table)}


def _drop_indexes_referencing(table: str, column: str) -> None:
    """Drop 所有引用 column 的索引 (判存)。

    SQLite 的 ALTER TABLE DROP COLUMN 不允许列被索引引用 -> 必须先解除;
    PG 的 DROP COLUMN 本会级联 drop 依赖索引, 显式 drop 同样安全且让两方言
    行为一致。回滚语义: drop 列即回到"无该列"状态, 引用它的索引 (如
    enterprise_vehicles.idx_ev_approval) 在该状态下本就不应存在, 故不重建。
    生产缺列库无这些索引, 不受影响。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return
    for idx in inspector.get_indexes(table):
        if column in (idx.get("column_names") or []):
            op.drop_index(idx["name"], table_name=table)


def _add_not_null_int_column(table: str, column: str, comment: str,
                             default: int = 0) -> None:
    """三步法加 NOT NULL Integer 列 (team_id 类)。

    PG: nullable 加列 -> 回填 -> SET DEFAULT + SET NOT NULL。
    SQLite: nullable 加列 + 回填, 跳过 ALTER 约束步 (不支持改约束)。
    幂等: 表不存在或列已存在则跳过。
    """
    bind = op.get_bind()
    cols = _existing_columns(bind, table)
    if cols is None or column in cols:
        return
    # step 1: nullable 加列
    op.add_column(
        table,
        sa.Column(column, sa.Integer(), nullable=True, comment=comment),
    )
    # step 2: 回填已有行
    op.execute(
        sa.text(
            f"UPDATE {table} SET {column} = :v WHERE {column} IS NULL"
        ).bindparams(v=default)
    )
    # step 3: PG 设默认 + NOT NULL
    if _is_postgresql(bind):
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default}"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"
            )
        )


def _add_nullable_column(table: str, column: str, sa_type, comment: str) -> None:
    """加 nullable 列 (无 server_default, 与模型层一致: 仅 ORM 端 default)。幂等。"""
    bind = op.get_bind()
    cols = _existing_columns(bind, table)
    if cols is None or column in cols:
        return
    op.add_column(
        table,
        sa.Column(column, sa_type, nullable=True, comment=comment),
    )


def _add_approval_status() -> None:
    """enterprise_vehicles.approval_status: SAEnum, NOT NULL default=PENDING。

    PG: 幂等 CREATE TYPE approvalstatus -> ADD COLUMN -> 回填 -> SET DEFAULT+NOT NULL。
    SQLite: String(20) 加列 + 回填 (跳过约束步)。
    幂等: 列已存在则跳过。
    """
    bind = op.get_bind()
    cols = _existing_columns(bind, _APPROVAL_TABLE)
    if cols is None or _APPROVAL_COLUMN in cols:
        return

    if _is_postgresql(bind):
        labels_sql = ", ".join(f"'{lbl}'" for lbl in _APPROVAL_LABELS)
        if not _enum_type_exists(bind, _APPROVAL_ENUM_NAME):
            op.execute(
                sa.text(
                    f"CREATE TYPE {_APPROVAL_ENUM_NAME} AS ENUM ({labels_sql})"
                )
            )
        # 原生 SQL 加列, 复用上面 ensure 过的 enum type (避免 op.add_column 重复 CREATE TYPE)
        op.execute(
            sa.text(
                f"ALTER TABLE {_APPROVAL_TABLE} "
                f"ADD COLUMN {_APPROVAL_COLUMN} {_APPROVAL_ENUM_NAME}"
            )
        )
        op.execute(
            sa.text(
                f"UPDATE {_APPROVAL_TABLE} SET {_APPROVAL_COLUMN} = :v "
                f"WHERE {_APPROVAL_COLUMN} IS NULL"
            ).bindparams(v=_APPROVAL_DEFAULT)
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {_APPROVAL_TABLE} ALTER COLUMN {_APPROVAL_COLUMN} "
                f"SET DEFAULT '{_APPROVAL_DEFAULT}'"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {_APPROVAL_TABLE} ALTER COLUMN {_APPROVAL_COLUMN} "
                f"SET NOT NULL"
            )
        )
        op.execute(
            sa.text(
                f"COMMENT ON COLUMN {_APPROVAL_TABLE}.{_APPROVAL_COLUMN} "
                f"IS '确认状态'"
            )
        )
    else:
        # SQLite: SAEnum 退化为 VARCHAR(20); 加 nullable 列 + 回填
        op.add_column(
            _APPROVAL_TABLE,
            sa.Column(_APPROVAL_COLUMN, sa.String(20), nullable=True,
                      comment="确认状态"),
        )
        op.execute(
            sa.text(
                f"UPDATE {_APPROVAL_TABLE} SET {_APPROVAL_COLUMN} = :v "
                f"WHERE {_APPROVAL_COLUMN} IS NULL"
            ).bindparams(v=_APPROVAL_DEFAULT)
        )


def _ensure_iconfig_index(create: bool) -> None:
    """幂等建/删 interconnect_configs.idx_iconfig_team。表不存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table = _ICONFIG_INDEX[1]
    if not inspector.has_table(table):
        return
    idx_name = _ICONFIG_INDEX[0]
    existing = {i["name"] for i in inspector.get_indexes(table)}
    if create and idx_name not in existing:
        op.create_index(idx_name, table, _ICONFIG_INDEX[2])
    elif not create and idx_name in existing:
        op.drop_index(idx_name, table_name=table)


# ---------- migration ----------

def upgrade() -> None:
    """补 14 缺列 + idx_iconfig_team。"""
    # A. team_id 类 NOT NULL Integer 列 (5)
    for table, column, comment in _TEAM_ID_COLUMNS:
        _add_not_null_int_column(table, column, comment)

    # B. nullable 列 (8)
    for table, column, sa_type, comment in _NULLABLE_COLUMNS:
        _add_nullable_column(table, column, sa_type, comment)

    # C. enterprise_vehicles.approval_status (SAEnum NOT NULL) (1)
    _add_approval_status()

    # D. interconnect_configs.idx_iconfig_team 索引
    _ensure_iconfig_index(create=True)


def downgrade() -> None:
    """反序回滚: idx_iconfig_team -> approval_status(列+type) -> nullable 列 -> team_id 列。

    每个 drop column 前先 drop 引用它的索引 (_drop_indexes_referencing):
    SQLite 的 ALTER TABLE DROP COLUMN 不允许列被索引引用; PG 级联 drop 等价。
    生产缺列库本就无这些依赖索引, 不受影响。
    """
    bind = op.get_bind()

    # D. 先 drop 我建的 idx_iconfig_team (引用 interconnect_configs.team_id)
    _ensure_iconfig_index(create=False)

    # C. approval_status: 解除索引依赖 -> drop 列 -> drop enum type
    _drop_indexes_referencing(_APPROVAL_TABLE, _APPROVAL_COLUMN)
    cols = _existing_columns(bind, _APPROVAL_TABLE)
    if cols is not None and _APPROVAL_COLUMN in cols:
        if _is_postgresql(bind):
            op.execute(
                sa.text(
                    f"ALTER TABLE {_APPROVAL_TABLE} "
                    f"ALTER COLUMN {_APPROVAL_COLUMN} DROP DEFAULT"
                )
            )
        op.drop_column(_APPROVAL_TABLE, _APPROVAL_COLUMN)
    if _enum_type_exists(bind, _APPROVAL_ENUM_NAME):
        op.execute(sa.text(f"DROP TYPE {_APPROVAL_ENUM_NAME}"))

    # B. drop nullable 列 (反序)
    for table, column, _sa_type, _comment in reversed(_NULLABLE_COLUMNS):
        _drop_indexes_referencing(table, column)
        cols = _existing_columns(bind, table)
        if cols is not None and column in cols:
            op.drop_column(table, column)

    # A. drop team_id 列 (反序)
    for table, column, _comment in reversed(_TEAM_ID_COLUMNS):
        _drop_indexes_referencing(table, column)
        cols = _existing_columns(bind, table)
        if cols is not None and column in cols:
            op.drop_column(table, column)
