"""add_device_provision_and_station_approval

Revision ID: 202608080200
Revises: 202608080100
Create Date: 2026-08-08 02:00:00.000000

建站加设备自助闭环 (卡 1256e7fa): 给 devices / stations 补入网状态 + 接入凭证列。

devices:
- provision_status  : SAEnum(unprovisioned/provisioning/online) NOT NULL default=unprovisioned, index
- charge_box_id     : String(100), index  (OCPP chargeBoxId, 创建时默认=sn)
- mqtt_username     : String(100), index  (MQTT 接入用户名)
- mqtt_password     : String(200)         (一次性下发, 网关校验连接)
- auth_token        : String(200)         (通用接入令牌, 一次性下发)

stations:
- approval_status   : SAEnum(approved/pending/rejected) NOT NULL default=approved, index

幂等: 用 inspector 判列已存在则跳过, 兼容已 create_all 的测试库与 alembic upgrade 的生产库。
PG: CREATE TYPE -> 原生 ALTER COLUMN ADD/SET DEFAULT/SET NOT NULL; SQLite: String(20) 退化 +
回填默认值 (SQLEnum 在 SQLite 存字面值, 与模型一致)。

可逆: downgrade 反序 (index -> 列 -> enum type)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608080200"
down_revision: Union[str, Sequence[str], None] = "202608080100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── 枚举定义 ──
_PROVISION_ENUM_NAME = "provisionstatus"
_PROVISION_LABELS = ["unprovisioned", "provisioning", "online"]
_PROVISION_DEFAULT = "unprovisioned"

# 卡 15a07d0f: 独立 type 名, 不得与 baseline enterprise_vehicles 的
# approvalstatus('PENDING','CONFIRMED','REJECTED') 同名 —— 值集不同
# (本列 approved/pending/rejected 小写), PG 上同名异值集 type 复用会在
# ADD COLUMN ... DEFAULT 'approved' 时 InvalidTextRepresentation;
# 原 downgrade 的 DROP TYPE 还会误删 baseline 的同名 type。
# 模型侧 station.ApprovalStatus 与 enterprise_vehicle.ApprovalStatus
# 本就是两个独立无名枚举类, 无共享 type 语义。
_APPROVAL_ENUM_NAME = "stationapprovalstatus"
_APPROVAL_LABELS = ["approved", "pending", "rejected"]
_APPROVAL_DEFAULT = "approved"

_DEVICES = "devices"
_STATIONS = "stations"

# (table, column, sa_type, comment, index?) —— 纯标量列
_SCALAR_COLUMNS = [
    (_DEVICES, "charge_box_id", sa.String(length=100), "OCPP chargeBoxId", True),
    (_DEVICES, "mqtt_username", sa.String(length=100), "MQTT 接入用户名", True),
    (_DEVICES, "mqtt_password", sa.String(length=200), "MQTT 接入密码(一次性下发)", False),
    (_DEVICES, "auth_token", sa.String(length=200), "通用接入令牌(一次性下发)", False),
]


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _existing_columns(bind, table: str):
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return None
    return {c["name"] for c in inspector.get_columns(table)}


def _enum_type_exists(bind, name: str) -> bool:
    if not _is_postgresql(bind):
        return False
    res = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :n").bindparams(n=name)
    )
    return res.first() is not None


def _existing_indexes(bind, table: str) -> set:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return set()
    return {i["name"] for i in inspector.get_indexes(table)}


def _ensure_index(table: str, column: str, create: bool) -> None:
    bind = op.get_bind()
    idx_name = f"ix_{table}_{column}"
    existing = _existing_indexes(bind, table)
    if create and idx_name not in existing:
        op.create_index(idx_name, table, [column])
    elif not create and idx_name in existing:
        op.drop_index(idx_name, table_name=table)


def _add_enum_column(
    table: str, column: str, enum_name: str, labels: list, default: str, comment: str
) -> None:
    """加一个 SAEnum NOT NULL default 列 (PG native enum / SQLite VARCHAR 回填)。"""
    bind = op.get_bind()
    cols = _existing_columns(bind, table)
    if cols is None or column in cols:
        return

    if _is_postgresql(bind):
        labels_sql = ", ".join(f"'{lbl}'" for lbl in labels)
        if not _enum_type_exists(bind, enum_name):
            op.execute(
                sa.text(f"CREATE TYPE {enum_name} AS ENUM ({labels_sql})")
            )
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ADD COLUMN {column} {enum_name}"
            )
        )
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = :v WHERE {column} IS NULL"
            ).bindparams(v=default)
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL"
            )
        )
        op.execute(
            sa.text(
                f"COMMENT ON COLUMN {table}.{column} IS '{comment}'"
            )
        )
    else:
        # SQLite: SAEnum 退化为 VARCHAR(20); 加列带 server_default
        # (回填存量行 + 新行自动取默认值; PG 路径已 SET DEFAULT, 此处对齐)。
        op.add_column(
            table,
            sa.Column(
                column, sa.String(20),
                nullable=True,
                server_default=sa.text(f"'{default}'"),
                comment=comment,
            ),
        )
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = :v WHERE {column} IS NULL"
            ).bindparams(v=default)
        )


def _add_scalar_column(table: str, column: str, sa_type, comment: str) -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind, table)
    if cols is None or column in cols:
        return
    op.add_column(
        table,
        sa.Column(column, sa_type, nullable=True, comment=comment),
    )


def upgrade() -> None:
    """补 devices 5 列 + stations 1 列, 含两个 enum 列与索引。"""
    # A. devices.provision_status (SAEnum NOT NULL default=unprovisioned)
    _add_enum_column(
        _DEVICES, "provision_status", _PROVISION_ENUM_NAME,
        _PROVISION_LABELS, _PROVISION_DEFAULT,
        "入网状态: unprovisioned/provisioning/online",
    )
    _ensure_index(_DEVICES, "provision_status", create=True)

    # B. devices 4 个标量列
    for table, column, sa_type, comment, indexed in _SCALAR_COLUMNS:
        _add_scalar_column(table, column, sa_type, comment)
        if indexed:
            _ensure_index(table, column, create=True)

    # C. stations.approval_status (SAEnum NOT NULL default=approved)
    _add_enum_column(
        _STATIONS, "approval_status", _APPROVAL_ENUM_NAME,
        _APPROVAL_LABELS, _APPROVAL_DEFAULT,
        "审核状态: approved/pending/rejected",
    )
    _ensure_index(_STATIONS, "approval_status", create=True)


def downgrade() -> None:
    """反序回滚: 索引 -> 列 -> enum type (仅 PG drop type)。"""
    bind = op.get_bind()

    # C. stations.approval_status
    _ensure_index(_STATIONS, "approval_status", create=False)
    cols = _existing_columns(bind, _STATIONS)
    if cols is not None and "approval_status" in cols:
        op.drop_column(_STATIONS, "approval_status")

    # B. devices 标量列 (反序, 先删其索引)
    for table, column, _sa_type, _comment, indexed in reversed(_SCALAR_COLUMNS):
        if indexed:
            _ensure_index(table, column, create=False)
        cols = _existing_columns(bind, table)
        if cols is not None and column in cols:
            op.drop_column(table, column)

    # A. devices.provision_status
    _ensure_index(_DEVICES, "provision_status", create=False)
    cols = _existing_columns(bind, _DEVICES)
    if cols is not None and "provision_status" in cols:
        op.drop_column(_DEVICES, "provision_status")

    # PG: drop enum types
    if _is_postgresql(bind):
        for enum_name in (_APPROVAL_ENUM_NAME, _PROVISION_ENUM_NAME):
            if _enum_type_exists(bind, enum_name):
                op.execute(sa.text(f"DROP TYPE {enum_name}"))
